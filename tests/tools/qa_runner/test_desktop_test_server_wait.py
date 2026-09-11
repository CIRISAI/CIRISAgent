"""The test-server wait must name WHICH fault it hit, not just that it waited.

Nightly 34596459034's Windows leg printed "desktop test server didn't come up
within 60s" while the app's own log said `[TestAutomation] Server started on
http://localhost:9091` and the UI had already reached the Setup screen. One
sentence covered three different faults, the orphaned app was left running, and
three downstream legs then failed looking like product defects (CIRISAgent#1172).
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Optional

import pytest

web_ui = importlib.import_module("tools.qa_runner.modules.web_ui.__main__")


class FakeProc:
    """A Popen stand-in: `rc=None` is alive, an int is an exit code."""

    def __init__(self, rc: Optional[int] = None) -> None:
        self._rc = rc
        self.killed = False
        self.waited = False

    def poll(self) -> Optional[int]:
        return self._rc

    def kill(self) -> None:
        self.killed = True
        self._rc = -9

    def wait(self, timeout: float | None = None) -> int:
        self.waited = True
        return self._rc if self._rc is not None else 0


class Resp:
    def __init__(self, code: int) -> None:
        self.status_code = code


def _answer_on(monkeypatch, *hosts: str) -> list[str]:
    """Make /health answer only for the given hosts; record every URL tried."""
    tried: list[str] = []

    def fake_get(url: str, timeout: float = 0):  # noqa: ANN202
        tried.append(url)
        if any(f"http://{h}:" in url for h in hosts):
            return Resp(200)
        raise OSError("connection refused")

    monkeypatch.setattr(web_ui.requests, "get", fake_get)
    return tried


def test_returns_the_url_that_answered_on_127(monkeypatch, tmp_path):
    _answer_on(monkeypatch, "127.0.0.1")
    log = tmp_path / "c.log"
    log.write_text("")
    url = web_ui._await_desktop_test_server(FakeProc(), log, 9091, budget_s=5)
    assert url == "http://127.0.0.1:9091"


def test_tries_localhost_too_when_127_refuses(monkeypatch, tmp_path):
    """The Windows IPv6/IPv4 split: a server on one spelling is unreachable at
    the other, and probing only one turns reachability into a false 'never came up'."""
    tried = _answer_on(monkeypatch, "localhost")
    log = tmp_path / "c.log"
    log.write_text("")
    url = web_ui._await_desktop_test_server(FakeProc(), log, 9091, budget_s=5)
    assert url == "http://localhost:9091"
    assert any("127.0.0.1" in u for u in tried), "must try 127.0.0.1 as well"


def test_a_dead_jvm_is_reported_as_exited_and_does_not_wait_out_the_budget(monkeypatch, tmp_path, capsys):
    _answer_on(monkeypatch)  # nothing answers
    log = tmp_path / "c.log"
    log.write_text("Exception in thread main java.lang.NoClassDefFoundError\n")
    import time as _t

    t0 = _t.monotonic()
    assert web_ui._await_desktop_test_server(FakeProc(rc=1), log, 9091, budget_s=30) is None
    assert _t.monotonic() - t0 < 10, "a dead JVM must not burn the whole budget"
    out = capsys.readouterr().out
    assert "EXITED rc=1" in out
    assert "the app exited" in out
    assert "NoClassDefFoundError" in out, "the tail must be shown"


def test_serving_but_unreachable_is_called_reachability_not_startup(monkeypatch, tmp_path, capsys):
    """THE WINDOWS CASE. The app is alive and its log says the server started, so
    this is not a startup failure and must not be reported as one."""
    _answer_on(monkeypatch)
    log = tmp_path / "c.log"
    log.write_text("[TestAutomation] Server started on http://localhost:9091\n")
    assert web_ui._await_desktop_test_server(FakeProc(), log, 9091, budget_s=3) is None
    out = capsys.readouterr().out
    assert "REACHABILITY, not startup" in out
    assert "NOT a client or product fault" in out
    assert "jvm: ALIVE" in out


def test_alive_and_silent_is_called_still_starting(monkeypatch, tmp_path, capsys):
    _answer_on(monkeypatch)
    log = tmp_path / "c.log"
    log.write_text("[Desktop] Found localization directory\n")
    assert web_ui._await_desktop_test_server(FakeProc(), log, 9091, budget_s=3) is None
    out = capsys.readouterr().out
    assert "still starting" in out
    assert "REACHABILITY" not in out


def test_a_missing_log_does_not_crash_the_diagnosis(monkeypatch, tmp_path, capsys):
    _answer_on(monkeypatch)
    assert web_ui._await_desktop_test_server(FakeProc(), tmp_path / "nope.log", 9091, budget_s=2) is None
    assert "not reachable" in capsys.readouterr().out


def test_the_orphan_is_killed_so_the_next_leg_starts_clean(capsys):
    proc = FakeProc()
    web_ui._kill_desktop_app(proc)
    assert proc.killed and proc.waited
    assert "stopped the app" in capsys.readouterr().out


def test_killing_an_already_dead_app_is_a_no_op():
    proc = FakeProc(rc=0)
    web_ui._kill_desktop_app(proc)
    assert not proc.killed
