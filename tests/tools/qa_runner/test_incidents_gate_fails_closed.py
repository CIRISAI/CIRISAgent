"""The incidents gate must FAIL when it cannot look (2.9.13 Staged QA race).

`_has_incidents_occurred` used to `return False` when the incidents log was
absent — no log, therefore no incidents, therefore PASS. That made the gate a coin
flip on file existence, and it was observed twice on the same commit:

    2.9.13 main run : sqlite   found the log -> FAILED
                      postgres "NO INCIDENTS LOG FOUND" -> PASSED
    re-run          : postgres found the log -> FAILED
                      sqlite   "NO INCIDENTS LOG FOUND" -> PASSED

Both runs had **100% test success on both backends** and identical expected,
test-induced errors (invalid-state transitions, adapter loads without credentials,
SIGTERM teardown). Which leg failed depended only on which leg's file existed.

The dangerous half is not the flaky red — it is the green. A leg that passes
because the log is absent certifies a run nobody checked, and after the fact there
is no way to tell which historical greens were real.

So: absent log ⇒ fail, loudly, and distinguishably from "incidents were found",
because the two need different debugging.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from tools.qa_runner.runner import QARunner


class _Console:
    def __init__(self) -> None:
        self.lines: list[str] = []

    def print(self, msg: Any = "", *a: Any, **k: Any) -> None:
        self.lines.append(str(msg))

    @property
    def text(self) -> str:
        return "\n".join(self.lines)


def _runner(backend: str, tmp_path: Path) -> Any:
    r = QARunner.__new__(QARunner)
    r.console = _Console()
    r.server_manager = SimpleNamespace(database_backend=backend)
    r._startup_incidents_position = 0
    return r


def test_missing_log_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The exact 2.9.13 race: no file must NOT mean clean."""
    monkeypatch.chdir(tmp_path)  # logs/<backend>/ does not exist here
    r = _runner("postgres", tmp_path)

    assert r._has_incidents_occurred() is True, (
        "a missing incidents log reported 'no incidents' and PASSED the leg — this "
        "is the coin flip that made two runs of the same commit fail on opposite backends"
    )


def test_missing_log_is_reported_as_uncertifiable_not_as_incidents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """'Could not check' and 'found incidents' need different debugging."""
    monkeypatch.chdir(tmp_path)
    r = _runner("sqlite", tmp_path)
    r._has_incidents_occurred()

    out = r.console.text
    assert "CANNOT CERTIFY" in out, "must say the run is uncertified"
    assert "sqlite" in out, "must name the backend whose log is missing"
    assert "incidents_latest.log" in out, "must name the expected path"
    assert "FIX:" in out, "must state the remedy"
    # And it must be flagged so the summary does not claim incidents were detected.
    assert getattr(r, "_incidents_unverifiable", False) is True


def test_present_but_unchanged_log_is_genuinely_clean(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail-closed must not turn every clean run red.

    A log that exists and has not grown since startup is a real pass — that is the
    steady state, and it is distinguishable from absence.
    """
    monkeypatch.chdir(tmp_path)
    log = tmp_path / "logs" / "sqlite" / "incidents_latest.log"
    log.parent.mkdir(parents=True)
    log.write_text("=== header ===\n")

    r = _runner("sqlite", tmp_path)
    r._startup_incidents_position = log.stat().st_size  # nothing new since startup

    assert r._has_incidents_occurred() is False
    assert getattr(r, "_incidents_unverifiable", False) is False
