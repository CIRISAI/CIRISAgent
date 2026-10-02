"""The agent declares the node's device class (server 0.5.220 / persist v53, CC 3.3.7).

A server-class node no longer receives a person's SELF and FAMILY content, and the
server defaults to `server` unless CIRIS_DEVICE_CLASS says otherwise. A person's
desktop running the agent must therefore say `laptop`.
"""

from __future__ import annotations

import sys

import pytest

from ciris_engine.logic.runtime import device_class as dc
from ciris_engine.logic.runtime.device_class import DEVICE_CLASS_ENV, HostDeviceClass, declare_device_class


@pytest.fixture(autouse=True)
def _clean(monkeypatch):
    monkeypatch.delenv(DEVICE_CLASS_ENV, raising=False)
    monkeypatch.setattr(dc, "is_android", lambda: False)
    monkeypatch.setattr(dc, "is_ios", lambda: False)


def test_unset_takes_the_default(monkeypatch):
    import os

    assert declare_device_class(HostDeviceClass.LAPTOP) == "laptop"
    assert os.environ[DEVICE_CLASS_ENV] == "laptop"


def test_an_existing_value_wins(monkeypatch):
    """The client's own desktop spawn (CIRISClient#153) or an operator decides first."""
    import os

    monkeypatch.setenv(DEVICE_CLASS_ENV, "laptop")
    assert declare_device_class(HostDeviceClass.SERVER) == "laptop"
    assert os.environ[DEVICE_CLASS_ENV] == "laptop"


@pytest.mark.parametrize("platform", ["is_android", "is_ios"])
def test_mobile_is_left_to_the_server(monkeypatch, platform):
    """The server resolves Android/iOS builds to `phone` itself."""
    import os

    monkeypatch.setattr(dc, platform, lambda: True)
    assert declare_device_class(HostDeviceClass.LAPTOP) is None
    assert DEVICE_CLASS_ENV not in os.environ


def _run_cli_main(monkeypatch, argv):
    import os

    import ciris_engine.cli as cli
    from ciris_engine import node_only

    seen = {}
    monkeypatch.setattr(sys, "argv", ["ciris-agent", *argv])
    monkeypatch.setattr(node_only, "node_only_config", lambda: None)
    monkeypatch.setattr(cli, "_run_desktop_mode", lambda: seen.setdefault("cls", os.environ.get(DEVICE_CLASS_ENV)))
    monkeypatch.setattr(cli, "_run_server_mode", lambda: seen.setdefault("cls", os.environ.get(DEVICE_CLASS_ENV)))
    cli.main()
    return seen["cls"]


def test_the_desktop_install_starts_its_node_as_a_laptop(monkeypatch):
    assert _run_cli_main(monkeypatch, []) == "laptop"


@pytest.mark.parametrize("flag", ["--server", "--headless", "--adapter"])
def test_headless_starts_its_node_as_a_server(monkeypatch, flag):
    assert _run_cli_main(monkeypatch, [flag]) == "server"


def test_the_node_fold_declares_server_when_nothing_did(monkeypatch):
    """`main.py` in a container reaches the fold without the CLI."""
    import os

    from ciris_engine.logic.runtime import node_fold

    monkeypatch.setenv("CIRIS_NODE_FOLD", "false")  # stop right after the declaration
    node_fold.start_node_fold(8080)
    assert os.environ[DEVICE_CLASS_ENV] == "server"
