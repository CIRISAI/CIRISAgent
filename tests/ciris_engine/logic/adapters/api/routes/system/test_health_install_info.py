"""/v1/system/health says which install answered and how to upgrade THAT install.

2026-11-27: a Windows user had CIRIS under Python 3.14 and 3.15. ``pip install -U``
upgraded 3.15's copy while his shortcut kept starting 3.14's, so his node stayed
on 2.23.1 and nothing showed it.
"""

from __future__ import annotations

import platform
import sys

import pytest

from ciris_engine.constants import CIRIS_VERSION
from ciris_engine.logic.adapters.api.routes.system import health
from ciris_engine.logic.adapters.api.routes.system.schemas import SystemHealthResponse


def test_a_signed_in_caller_gets_the_interpreter_and_the_command(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "executable", "/opt/py314/bin/python3")
    info = health.collect_install_info(signed_in=True)
    assert info is not None
    assert info.agent_version == CIRIS_VERSION
    assert info.python_version == platform.python_version()
    assert info.python_executable == "/opt/py314/bin/python3"
    assert info.upgrade_argv == ["/opt/py314/bin/python3", "-m", "ciris_engine.cli", "upgrade"]
    assert info.upgrade_command and "ciris_engine.cli upgrade" in info.upgrade_command


def test_an_anonymous_caller_gets_versions_but_no_paths() -> None:
    info = health.collect_install_info(signed_in=False)
    assert info is not None
    assert info.agent_version == CIRIS_VERSION
    # The interpreter path carries the OS user name (C:\Users\<name>\...).
    assert info.python_executable is None
    assert info.upgrade_argv is None
    assert info.upgrade_command is None


def test_an_unreadable_dist_is_null_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from importlib import metadata

    def _missing(name: str) -> str:
        raise metadata.PackageNotFoundError(name)

    monkeypatch.setattr(metadata, "version", _missing)
    info = health.collect_install_info(signed_in=True)
    assert info is not None and info.server_version is None and info.client_version is None


def test_health_still_answers_if_install_info_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    import ciris_engine.upgrade as up

    def _boom(*_a: object, **_k: object) -> list:
        raise RuntimeError("no")

    monkeypatch.setattr(up, "upgrade_argv", _boom)
    assert health.collect_install_info(signed_in=True) is None


def test_the_field_is_on_the_wire_model() -> None:
    assert "install" in SystemHealthResponse.model_fields
