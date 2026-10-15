"""The QA runner and its sibling harnesses declare the run kind authoritatively (CIRISAgent#1245).

Ruling (2026-10-14): QA runs are valuable but must be identified as such, and
anything outside a harness is production. So no harness may forward an
inherited ``production``: H1 (qa_runner), H2 (mobile launchers), H3 (web_ui
standalone).
"""

from __future__ import annotations

import ast
import os
import pathlib
import subprocess
from typing import Any, Dict, List, MutableMapping, Optional

import pytest

from tools.qa_runner import run_kind
from tools.qa_runner.config import QAModule

REPO = pathlib.Path(__file__).resolve().parents[3]
VAR = run_kind.RUN_KIND_ENV_VAR


def _old_setdefault_behaviour(env: MutableMapping[str, str], kind: str) -> None:
    """What server.py did before H1: an inherited value won."""
    env.setdefault(VAR, kind)


def _contract_holds(env: MutableMapping[str, str]) -> bool:
    """H1's contract: a harness env never carries production."""
    return env.get(VAR) in ("qa", "battery")


# --------------------------------------------------------------------------- #
# H1: qa_runner is authoritative.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("inherited", ["production", "PRODUCTION", "", "typo"])
def test_an_inherited_production_becomes_qa(inherited: str) -> None:
    env = {VAR: inherited}
    warning = run_kind.declare_run_kind(env, run_kind.harness_run_kind([QAModule.AUTH]))
    assert env[VAR] == "qa"
    assert _contract_holds(env)
    assert (warning is not None) == bool(inherited)


def test_negative_the_old_setdefault_fails_this_contract() -> None:
    """The defect H1 fixes: setdefault let an inherited production through."""
    env = {VAR: "production"}
    _old_setdefault_behaviour(env, "qa")
    assert not _contract_holds(env), "the injected defect must be visible to the contract"


@pytest.mark.parametrize("explicit", ["qa", "battery"])
def test_an_explicit_harness_kind_is_kept(explicit: str) -> None:
    env = {VAR: explicit}
    assert run_kind.declare_run_kind(env, "battery" if explicit == "qa" else "qa") is None
    assert env[VAR] == explicit


@pytest.mark.parametrize(
    "modules,kind",
    [
        ([QAModule.SAFETY_BATTERY], "battery"),
        ([QAModule.MODEL_EVAL], "battery"),
        ([QAModule.HE300_BENCHMARK], "battery"),
        ([QAModule.AUTH, QAModule.HE300_BENCHMARK], "battery"),
        ([QAModule.AUTH], "qa"),
        ([], "qa"),
        (None, "qa"),
    ],
)
def test_battery_modules(modules: Any, kind: str) -> None:
    assert run_kind.harness_run_kind(modules) == kind


def test_server_no_longer_uses_setdefault_for_the_run_kind() -> None:
    src = (REPO / "tools" / "qa_runner" / "server.py").read_text(encoding="utf-8")
    assert f'setdefault("{VAR}"' not in src
    assert "declare_run_kind(env, harness_run_kind(self.modules))" in src


def _calls_in_function(path: pathlib.Path, function: str) -> List[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
            return [
                n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
                for n in ast.walk(node)
                if isinstance(n, ast.Call)
            ]
    raise AssertionError(f"{path}:{function} not found")


@pytest.mark.parametrize(
    "rel",
    [
        "tools/qa_runner/__main__.py",
        "tools/qa_runner/modules/web_ui/__main__.py",
        "tools/qa_runner/modules/mobile/__main__.py",
        "tools/qa_runner/modules/mobile/test_runner.py",
    ],
)
def test_each_harness_entry_point_declares_on_its_own_env(rel: str) -> None:
    """Sibling launchers inside a module read os.environ, not the server child's env."""
    assert "declare_process_run_kind" in _calls_in_function(REPO / rel, "main")


def test_process_declaration_overrides_production(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(VAR, "production")
    assert run_kind.declare_process_run_kind("battery") is not None
    assert os.environ[VAR] == "battery"


# --------------------------------------------------------------------------- #
# H2: the mobile QA runner forwards the run kind into the app process.
# --------------------------------------------------------------------------- #


def _setprop_precedes_launch(calls: List[List[str]], kind: str) -> bool:
    try:
        sp = calls.index(["shell", "setprop", run_kind.ANDROID_RUN_KIND_PROP, kind])
    except ValueError:
        return False
    return any(c[:3] == ["shell", "am", "start"] for c in calls[sp + 1 :])


@pytest.mark.parametrize("declared,kind", [("", "qa"), ("production", "qa"), ("battery", "battery")])
def test_android_launch_writes_the_property_first(monkeypatch: pytest.MonkeyPatch, declared: str, kind: str) -> None:
    from tools.qa_runner.modules.mobile.adb_helper import ADBHelper

    calls: List[List[str]] = []

    def _run_adb(args: List[str], timeout: int = 30) -> subprocess.CompletedProcess:
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, "", "")

    adb = object.__new__(ADBHelper)
    monkeypatch.setattr(adb, "_run_adb", _run_adb, raising=False)
    monkeypatch.setenv(VAR, declared)
    assert adb.launch_app("ai.ciris.mobile", ".MainActivity")
    assert _setprop_precedes_launch(calls, kind)


def test_negative_a_launch_without_the_forwarder_fails_the_check() -> None:
    assert not _setprop_precedes_launch([["shell", "am", "start", "-n", "ai.ciris.mobile/.MainActivity"]], "qa")
    assert not _setprop_precedes_launch(
        [["shell", "am", "start", "-n", "x"], ["shell", "setprop", run_kind.ANDROID_RUN_KIND_PROP, "qa"]], "qa"
    ), "a property written after the launch is too late"


def _simctl_child(env: Optional[Dict[str, str]]) -> Optional[str]:
    return (env or {}).get(f"SIMCTL_CHILD_{VAR}")


def test_ios_simulator_launch_forwards_the_run_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.qa_runner.modules.mobile.ios import xcrun_helper

    seen: List[Dict[str, Any]] = []

    def _run(cmd: List[str], **kw: Any) -> subprocess.CompletedProcess:
        seen.append({"cmd": cmd, "env": kw.get("env")})
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(xcrun_helper.subprocess, "run", _run)
    monkeypatch.delenv(VAR, raising=False)
    helper = object.__new__(xcrun_helper.XCRunHelper)
    helper.device_id = "SIM-1"
    helper.use_booted = True
    assert helper.launch_app("ai.ciris.mobile")
    assert seen[-1]["cmd"][:3] == ["xcrun", "simctl", "launch"]
    assert _simctl_child(seen[-1]["env"]) == "qa"


def test_ios_build_helper_simulator_launch_forwards_the_run_kind(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.qa_runner.modules.mobile.ios import build_helper

    seen: List[Dict[str, Any]] = []

    def _run_command(cmd: List[str], **kw: Any) -> subprocess.CompletedProcess:
        seen.append({"cmd": cmd, "env": kw.get("env")})
        return subprocess.CompletedProcess(cmd, 0, "", "")

    helper = object.__new__(build_helper.iOSBuildHelper)
    helper.config = build_helper.iOSBuildConfig(project_path=pathlib.Path("."))
    monkeypatch.setattr(helper, "_run_command", _run_command, raising=False)
    monkeypatch.setenv(VAR, "battery")
    device = type("D", (), {"identifier": "SIM-1"})()
    assert helper._launch_on_simulator(device)
    assert _simctl_child(seen[-1]["env"]) == "battery"


def test_negative_a_bare_simctl_env_fails_the_check() -> None:
    assert _simctl_child(None) is None
    assert _simctl_child({"SIMCTL_CHILD_CIRIS_TEST_MODE": "true"}) is None


# --------------------------------------------------------------------------- #
# H3: web_ui standalone declares qa for the backend it starts.
# --------------------------------------------------------------------------- #


def test_web_ui_backend_env_is_declared() -> None:
    assert "declare_run_kind" in _calls_in_function(
        REPO / "tools" / "qa_runner" / "modules" / "web_ui" / "server_manager.py", "start"
    )


def test_web_ui_forwards_qa_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.qa_runner.modules.web_ui import __main__ as web_ui

    monkeypatch.delenv(VAR, raising=False)
    assert web_ui._run_kind_to_forward() == "qa"
