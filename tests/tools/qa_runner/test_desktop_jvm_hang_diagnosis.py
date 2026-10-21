"""A live JVM that never wrote a byte is HUNG, not slow -- and we keep the stacks.

The desktop-ui job's JVM was alive but wrote 0 bytes in 90 s, so it was wedged
before Main.kt's first println. The harness reported "still starting when the
budget expired: raise it", killed the app, and left no record of where it was
stuck. Its port check printed "(could not tell)" although netstat had run and
answered, because the lookup could not say "free" apart from "unknown".

Every failure is a gift only if the run keeps the evidence. These tests pin:

  * alive + 0-byte log  -> the hung verdict, a jcmd Thread.print taken BEFORE
    the kill, and a dump file the CI collectors carry out;
  * alive + some output -> the old "still starting" advice, unchanged;
  * pids_listening_on   -> None when the lookup failed, [] when it ran empty;
  * jcmd absent / failing / hanging -> reported, never fatal.

No real JVM: processes, logs, and subprocess.run are all fakes.
"""

from __future__ import annotations

import fnmatch
import importlib
import re
import subprocess
from pathlib import Path
from typing import List, Optional

import pytest

web_ui = importlib.import_module("tools.qa_runner.modules.web_ui.__main__")
platform_procs = importlib.import_module("tools.qa_runner.platform_procs")

REPO = Path(__file__).resolve().parents[3]

#: Workflows that launch the desktop app through the harness and ship its log.
COLLECTOR_WORKFLOWS = [
    ".github/workflows/windows-desktop-ui.yml",
    ".github/workflows/five-platform-live-qa.yml",
    ".github/workflows/five-platform-modular-qa.yml",
]


class FakeProc:
    """Popen stand-in: `rc=None` is alive."""

    pid = 4242

    def __init__(self, rc: Optional[int] = None) -> None:
        self._rc = rc
        self.killed = False

    def poll(self) -> Optional[int]:
        return self._rc

    def kill(self) -> None:
        self.killed = True
        self._rc = -9

    def wait(self, timeout: float | None = None) -> int:
        return self._rc if self._rc is not None else 0


class Completed:
    def __init__(self, rc: int = 0, stdout: str = "", stderr: str = "") -> None:
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


@pytest.fixture
def nothing_answers(monkeypatch):
    def fake_get(url: str, timeout: float = 0):  # noqa: ANN202
        raise OSError("connection refused")

    monkeypatch.setattr(web_ui.requests, "get", fake_get)
    monkeypatch.setattr(web_ui.time, "sleep", lambda s: None)


@pytest.fixture
def fake_jcmd(monkeypatch, tmp_path):
    """A jcmd under a fake JAVA_HOME, and a recorder for every subprocess.run."""
    java_home = tmp_path / "jdk"
    (java_home / "bin").mkdir(parents=True)
    exe = java_home / "bin" / ("jcmd.exe" if web_ui.sys.platform == "win32" else "jcmd")
    exe.write_text("")
    monkeypatch.setenv("JAVA_HOME", str(java_home))
    calls: List[List[str]] = []

    def fake_run(cmd, **kw):  # noqa: ANN001, ANN202
        calls.append([str(c) for c in cmd])
        if "Thread.print" in cmd:
            return Completed(0, '"main" #1 prio=5\n   java.lang.Thread.State: RUNNABLE\n\tat sun.awt.windows...\n')
        return Completed(0, "")

    monkeypatch.setattr(web_ui.subprocess, "run", fake_run)
    # Keep the port lookup out of it: these tests are about the verdict.
    monkeypatch.setattr(platform_procs, "pids_listening_on", lambda port: [])
    return exe, calls


def _jcmd_calls(calls: List[List[str]]) -> List[List[str]]:
    return [c for c in calls if "Thread.print" in c]


# ---- 1 + 2: hung verdict, thread dump, collection ---------------------------


def test_alive_with_an_empty_log_is_hung_not_slow_and_is_thread_dumped(nothing_answers, fake_jcmd, tmp_path, capsys):
    exe, calls = fake_jcmd
    log = tmp_path / "ciris_desktop_setup.20261015T120000.log"
    log.write_text("")
    assert web_ui._await_desktop_test_server(FakeProc(), log, 9091, budget_s=1) is None
    out = capsys.readouterr().out

    assert "JVM hung before main's first output (not slow startup)" in out
    assert "see thread dump" in out
    assert "still starting" not in out, "a 0-byte log must not be advised as a short budget"
    assert "log bytes: 0" in out
    assert "time to first byte: never" in out

    jc = _jcmd_calls(calls)
    assert jc == [[str(exe), "4242", "Thread.print"]], "jcmd from JAVA_HOME/bin against the app's pid"

    dump = tmp_path / "ciris_desktop_setup.20261015T120000.jstack.txt"
    assert dump.is_file(), "the thread dump must be on disk next to the log"
    assert "java.lang.Thread.State" in dump.read_text(encoding="utf-8")
    assert str(dump) in out


def test_the_dump_is_taken_before_the_app_is_killed(nothing_answers, fake_jcmd, monkeypatch, tmp_path):
    """Order is the whole point: after the kill there is nothing to attach to."""
    _, calls = fake_jcmd
    proc = FakeProc()
    events: List[str] = []
    real_run = web_ui.subprocess.run

    def tracking_run(cmd, **kw):  # noqa: ANN001, ANN202
        if "Thread.print" in cmd:
            events.append("dump" if not proc.killed else "dump-after-kill")
        return real_run(cmd, **kw)

    monkeypatch.setattr(web_ui.subprocess, "run", tracking_run)
    log = tmp_path / "ciris_desktop_setup.x.log"
    log.write_text("")
    # The desktop-setup path: await, then kill on None.
    if web_ui._await_desktop_test_server(proc, log, 9091, budget_s=1) is None:
        web_ui._kill_desktop_app(proc)
    assert events == ["dump"]
    assert proc.killed


@pytest.mark.parametrize(
    "log_name", ["ciris_desktop_setup.20261015T120000.log", "ciris_desktop_up.20261015T120000.log"]
)
@pytest.mark.parametrize("workflow", COLLECTOR_WORKFLOWS)
def test_the_thread_dump_is_carried_out_by_every_collector(workflow: str, log_name: str) -> None:
    """A dump nobody uploads is not evidence. The collectors used to glob only
    ciris_desktop*.log, which a .jstack.txt does not match."""
    y = (REPO / workflow).read_text(encoding="utf-8")
    globs = set(re.findall(r"ciris_desktop\*[A-Za-z0-9_.*]*", y))
    dump_name = web_ui._jstack_path(Path(log_name)).name
    assert any(fnmatch.fnmatch(dump_name, g) for g in globs), f"{workflow} collects {sorted(globs)}, not {dump_name}"


def test_alive_with_some_output_keeps_the_still_starting_advice(nothing_answers, fake_jcmd, tmp_path, capsys):
    _, calls = fake_jcmd
    log = tmp_path / "ciris_desktop_setup.x.log"
    log.write_text("[Desktop] main entered\n[Desktop] Found localization directory\n")
    assert web_ui._await_desktop_test_server(FakeProc(), log, 9091, budget_s=1) is None
    out = capsys.readouterr().out
    assert "still starting when the budget expired" in out
    assert "JVM hung before main" not in out
    assert re.search(r"log bytes: [1-9]\d*", out)
    assert re.search(r"time to first byte: \d+\.\ds", out)


def test_a_serving_app_is_not_thread_dumped(nothing_answers, fake_jcmd, tmp_path, capsys):
    _, calls = fake_jcmd
    log = tmp_path / "ciris_desktop_setup.x.log"
    log.write_text("[TestAutomation] Server started on http://localhost:9091\n")
    web_ui._await_desktop_test_server(FakeProc(), log, 9091, budget_s=1)
    assert _jcmd_calls(calls) == []
    assert "REACHABILITY, not startup" in capsys.readouterr().out


def test_an_exited_app_is_not_thread_dumped(nothing_answers, fake_jcmd, tmp_path):
    _, calls = fake_jcmd
    log = tmp_path / "ciris_desktop_setup.x.log"
    log.write_text("")
    web_ui._await_desktop_test_server(FakeProc(rc=1), log, 9091, budget_s=1)
    assert _jcmd_calls(calls) == []


# ---- 3: honest port check ---------------------------------------------------


def test_lookup_failure_is_none(monkeypatch):
    def boom(*a, **k):  # noqa: ANN002, ANN003, ANN202
        raise FileNotFoundError(2, "no such tool")

    monkeypatch.setattr(platform_procs.subprocess, "run", boom)
    for windows in (True, False):
        monkeypatch.setattr(platform_procs, "IS_WINDOWS", windows)
        assert platform_procs.pids_listening_on(9091) is None


def test_windows_netstat_that_ran_and_found_nothing_is_empty_not_unknown(monkeypatch):
    """THE RCA CASE: netstat ran and answered, so the port is free -- say so."""
    netstat = (
        "Active Connections\n\n  Proto  Local Address  Foreign Address  State  PID\n"
        "  TCP    0.0.0.0:135    0.0.0.0:0        LISTENING  948\n"
    )
    monkeypatch.setattr(platform_procs, "IS_WINDOWS", True)
    monkeypatch.setattr(platform_procs.subprocess, "run", lambda *a, **k: Completed(0, netstat))
    assert platform_procs.pids_listening_on(9091) == []
    assert platform_procs.pids_listening_on(135) == [948]
    # ...and a netstat that FAILED says nothing about the port. The old helper
    # returned [] here too, which is why [] could never be printed as "free".
    monkeypatch.setattr(platform_procs.subprocess, "run", lambda *a, **k: Completed(1, "", "access denied"))
    assert platform_procs.pids_listening_on(9091) is None


def test_posix_lookup_that_ran_and_found_nothing_is_empty(monkeypatch):
    monkeypatch.setattr(platform_procs, "IS_WINDOWS", False)

    def run(cmd, **k):  # noqa: ANN001, ANN202
        return Completed(1, "") if cmd[0] == "lsof" else Completed(0, "")

    monkeypatch.setattr(platform_procs.subprocess, "run", run)
    assert platform_procs.pids_listening_on(9091) == []

    # lsof erroring and ss failing is NOT the same answer.
    def broken(cmd, **k):  # noqa: ANN001, ANN202
        return Completed(1, "", "lsof: WARNING: can't stat()") if cmd[0] == "lsof" else Completed(1, "", "ss: error")

    monkeypatch.setattr(platform_procs.subprocess, "run", broken)
    assert platform_procs.pids_listening_on(9091) is None


def test_a_listener_ss_will_not_name_is_unknown_not_free(monkeypatch):
    monkeypatch.setattr(platform_procs, "IS_WINDOWS", False)

    def run(cmd, **k):  # noqa: ANN001, ANN202
        if cmd[0] == "lsof":
            raise FileNotFoundError(2, "no lsof")
        return Completed(0, "LISTEN 0 50 127.0.0.1:9091 0.0.0.0:*\n")

    monkeypatch.setattr(platform_procs.subprocess, "run", run)
    assert platform_procs.pids_listening_on(9091) is None


@pytest.mark.parametrize(
    "answer, expected",
    [(None, "(could not tell)"), ([], "free (lookup ran, no listener)"), ([77], "[77]")],
)
def test_the_report_prints_free_vs_could_not_tell(
    nothing_answers, monkeypatch, tmp_path, capsys, answer, expected
):  # noqa: ANN001
    monkeypatch.setattr(platform_procs, "pids_listening_on", lambda port: answer)
    monkeypatch.setattr(web_ui, "_dump_jvm_threads", lambda proc, log: None)
    log = tmp_path / "c.log"
    log.write_text("x\n")
    web_ui._await_desktop_test_server(FakeProc(), log, 9091, budget_s=1)
    assert f"pids listening on 9091: {expected}" in capsys.readouterr().out


# ---- 4: jcmd missing / failing is non-fatal ---------------------------------


def test_no_jcmd_anywhere_is_reported_and_non_fatal(nothing_answers, monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("JAVA_HOME", raising=False)
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(platform_procs, "pids_listening_on", lambda port: [])
    log = tmp_path / "ciris_desktop_setup.x.log"
    log.write_text("")
    assert web_ui._await_desktop_test_server(FakeProc(), log, 9091, budget_s=1) is None
    out = capsys.readouterr().out
    assert "thread dump: skipped (no jcmd" in out
    assert "JVM hung before main" in out, "the verdict must not depend on the dump"


def test_jcmd_from_path_when_java_home_has_none(monkeypatch, tmp_path):
    monkeypatch.setenv("JAVA_HOME", str(tmp_path / "empty-jdk"))
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/jcmd" if name == "jcmd" else None)
    assert web_ui._find_jcmd() == "/usr/bin/jcmd"


@pytest.mark.parametrize(
    "behaviour",
    [
        lambda: Completed(1, "", "com.sun.tools.attach.AttachNotSupportedException: Unable to open socket file"),
        lambda: (_ for _ in ()).throw(subprocess.TimeoutExpired(["jcmd"], 15)),
        lambda: (_ for _ in ()).throw(PermissionError(13, "denied")),
    ],
    ids=["attach-fails", "times-out", "raises"],
)
def test_a_failing_jcmd_is_non_fatal(nothing_answers, fake_jcmd, monkeypatch, tmp_path, capsys, behaviour):
    seen: dict = {}

    def run(cmd, **kw):  # noqa: ANN001, ANN202
        seen["timeout"] = kw.get("timeout")
        return behaviour()

    monkeypatch.setattr(web_ui.subprocess, "run", run)
    log = tmp_path / "ciris_desktop_setup.x.log"
    log.write_text("")
    assert web_ui._await_desktop_test_server(FakeProc(), log, 9091, budget_s=1) is None
    out = capsys.readouterr().out
    assert "thread dump:" in out
    assert "JVM hung before main" in out
    assert seen["timeout"] is not None and seen["timeout"] <= 20, "jcmd must be bounded"
