"""The run-kind marker reaches mobile app processes (CIRISAgent#1245, Codex P1).

The five-platform gates set ``CIRIS_TRACE_RUN_KIND=qa`` in the runner env, but
mobile app processes inherit nothing from the runner:

* iOS: ``simctl launch`` forwards only ``SIMCTL_CHILD_``-prefixed vars (the
  same path ``CIRIS_TEST_MODE`` takes), and the embedded Python inherits the
  app process env.
* Android: ``am start`` extras reach the Kotlin activity, not Chaquopy's
  Python. The harness writes the ``debug.ciris.trace_run_kind`` system property
  (beside ``debug.CIRIS_TEST_MODE``) and the agent's resolver reads it.
"""

from __future__ import annotations

import subprocess
from typing import Any, Dict, List

import pytest

from ciris_engine.logic.utils import mock_llm_guard
from ciris_engine.logic.utils.mock_llm_guard import ANDROID_RUN_KIND_PROP, TraceRunKind, trace_run_kind
from tools.qa_runner.modules.web_ui import __main__ as web_ui


def test_ios_launch_env_forwards_the_run_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CIRIS_TRACE_RUN_KIND", "qa")
    env: Dict[str, str] = {}
    web_ui._forward_run_kind_ios(env)
    assert env == {"SIMCTL_CHILD_CIRIS_TRACE_RUN_KIND": "qa"}


def test_ios_launch_env_untouched_without_a_declaration(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CIRIS_TRACE_RUN_KIND", raising=False)
    env: Dict[str, str] = {}
    web_ui._forward_run_kind_ios(env)
    assert env == {}


@pytest.mark.parametrize("declared,expected", [("qa", "qa"), ("", "''")])
def test_android_sets_the_property(monkeypatch: pytest.MonkeyPatch, declared: str, expected: str) -> None:
    calls: List[List[str]] = []
    monkeypatch.setattr(web_ui, "_adb", lambda args, **_: calls.append(list(args)))
    monkeypatch.setenv("CIRIS_TRACE_RUN_KIND", declared)
    web_ui._forward_run_kind_android("emulator-5554")
    assert calls == [["shell", "setprop", ANDROID_RUN_KIND_PROP, expected]]


def test_the_harness_and_the_resolver_agree_on_the_property_name() -> None:
    import inspect

    assert ANDROID_RUN_KIND_PROP in inspect.getsource(web_ui._forward_run_kind_android)


class TestResolverSources:
    def test_dotenv_declaration(self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
        from ciris_engine.logic.config import env_utils

        monkeypatch.setitem(env_utils._ENV_VALUES, "CIRIS_TRACE_RUN_KIND", "battery")
        monkeypatch.setattr(env_utils, "_ENV_LOADED", True)
        assert trace_run_kind() == TraceRunKind.BATTERY

    def test_android_property(self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: List[Any] = []

        def _getprop(cmd: List[str], **_: Any) -> subprocess.CompletedProcess:
            seen.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="qa\n", stderr="")

        monkeypatch.setenv("ANDROID_ROOT", "/system")
        monkeypatch.setattr(subprocess, "run", _getprop)
        assert trace_run_kind() == TraceRunKind.QA
        assert seen == [["getprop", ANDROID_RUN_KIND_PROP]]
        trace_run_kind()
        assert len(seen) == 1, "the property is read once per process"

    def test_no_property_off_android(self, real_llm_mode: None, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("ANDROID_ROOT", raising=False)
        monkeypatch.delenv("ANDROID_DATA", raising=False)
        monkeypatch.setattr(subprocess, "run", lambda *a, **k: pytest.fail("getprop called off Android"))
        assert trace_run_kind() == TraceRunKind.PRODUCTION
        mock_llm_guard._reset_for_tests()
