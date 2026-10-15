"""The capture gate fails an incomplete safety-battery capture (vacuous-green fix)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))

from safety_battery_capture_gate import check_summary, main  # noqa: E402


def _bundle(tmp_path: Path, **summary: object) -> Path:
    (tmp_path / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    return tmp_path


def test_complete_capture_passes(tmp_path: Path) -> None:
    assert main([str(_bundle(tmp_path, n_questions=9, n_responses_captured=9, n_errors=0))]) == 0


@pytest.mark.parametrize("captured", [0, 1, 8])
def test_incomplete_capture_fails(tmp_path: Path, captured: int, capsys: pytest.CaptureFixture[str]) -> None:
    """Negative control: the exact 2026-10-15 shapes (0/9 and 1/9) and a single miss all fail."""
    rc = main([str(_bundle(tmp_path, n_questions=9, n_responses_captured=captured, n_errors=9 - captured))])
    assert rc == 1
    assert f"{captured}/9" in capsys.readouterr().out


def test_missing_or_malformed_summary_fails(tmp_path: Path) -> None:
    assert main([str(tmp_path)]) == 2
    ok, _ = check_summary({"n_questions": 9})
    assert not ok


def test_empty_battery_fails() -> None:
    ok, reason = check_summary({"n_questions": 0, "n_responses_captured": 0})
    assert not ok and "nothing was asked" in reason


def test_real_vacuous_bundle_shape_fails() -> None:
    """The summary.json the qa_runner wrote for run 38756521230 (am, 1.3 arm)."""
    summary = {"run_id": "20261015T154400Z", "n_questions": 9, "n_responses_captured": 0, "n_errors": 9}
    ok, reason = check_summary(summary)
    assert not ok and "0/9" in reason
