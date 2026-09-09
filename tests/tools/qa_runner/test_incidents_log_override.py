"""`--incidents-log` says where to look; it never says whether to look."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tools.qa_runner.config import QAConfig
from tools.qa_runner.runner import QARunner


def _runner(tmp_path: Path, explicit: Path | None) -> QARunner:
    runner = QARunner.__new__(QARunner)  # no __init__: we only need the path logic
    runner.config = QAConfig(incidents_log_path=explicit, report_dir=tmp_path)
    runner.console = MagicMock()
    runner.server_manager = MagicMock(database_backend="sqlite")
    return runner


def test_explicit_path_wins_over_backend_default(tmp_path):
    explicit = tmp_path / "pulled" / "incidents_latest.log"
    assert _runner(tmp_path, explicit)._incidents_log_path() == explicit


def test_without_override_the_backend_default_is_unchanged(tmp_path):
    assert _runner(tmp_path, None)._incidents_log_path() == Path("logs/sqlite/incidents_latest.log")


def test_missing_explicit_file_still_fails_closed(tmp_path):
    runner = _runner(tmp_path, tmp_path / "nope" / "incidents_latest.log")
    runner._startup_incidents_position = 0
    assert runner._has_incidents_occurred() is True
    assert getattr(runner, "_incidents_unverifiable", False) is True


def test_present_clean_explicit_file_passes(tmp_path):
    log = tmp_path / "incidents_latest.log"
    log.write_text("2026-09-09 INFO nothing to see\n")
    runner = _runner(tmp_path, log)
    runner._startup_incidents_position = 0
    assert runner._has_incidents_occurred() is False


def test_error_after_baseline_in_explicit_file_is_detected(tmp_path):
    """The override must not weaken the gate: an ERROR written after the
    baseline still fails the run, and is reported as found, not unverifiable."""
    log = tmp_path / "incidents_latest.log"
    log.write_text("2026-09-09 INFO boot\n")
    runner = _runner(tmp_path, log)
    runner._startup_incidents_position = log.stat().st_size
    with log.open("a") as handle:
        handle.write("2026-09-09 ERROR something broke during the test\n")
    assert runner._has_incidents_occurred() is True
    assert getattr(runner, "_incidents_unverifiable", False) is False
