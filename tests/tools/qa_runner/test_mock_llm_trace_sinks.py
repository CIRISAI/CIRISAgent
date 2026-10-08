"""The QA runner refuses a remote trace sink under the mock LLM (CIRISAgent#1244).

Mock is the runner's default (no --live, no --no-mock-llm), so ``--live-lens``
or ``--federation-delivery`` on their own are mock-LLM runs that ask for the
production lens or canonical. That must fail before anything is wiped or
started, with a message that says why.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import List

import pytest

from tools.qa_runner.__main__ import trace_sink_flag_error

REPO_ROOT = Path(__file__).resolve().parents[3]


@pytest.mark.parametrize(
    "mock,live_lens,fed,refused",
    [
        (True, True, False, True),
        (True, False, True, True),
        (True, True, True, True),
        (True, False, False, False),
        (False, True, False, False),
        (False, True, True, False),
    ],
)
def test_flag_matrix(mock: bool, live_lens: bool, fed: bool, refused: bool) -> None:
    error = trace_sink_flag_error(mock, live_lens, fed)
    assert (error is not None) is refused
    if error:
        assert "CIRISAgent#1244" in error and "mock LLM" in error


@pytest.mark.parametrize(
    "argv",
    [
        ["auth", "--live-lens"],
        ["auth", "--mock-llm", "--live-lens"],
        ["auth", "--federation-delivery"],
    ],
)
def test_cli_exits_before_doing_anything(tmp_path: Path, argv: List[str]) -> None:
    # Run from an empty dir so a regression that got past the check could not
    # wipe or touch the checkout's data/ directory.
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.run(
        [sys.executable, "-m", "tools.qa_runner", *argv],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 2, proc.stdout[-2000:] + proc.stderr[-2000:]
    assert "cannot be combined with the mock LLM" in proc.stdout
    assert list(tmp_path.iterdir()) == []


def test_mock_llm_flag_conflicts_with_live(tmp_path: Path) -> None:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    proc = subprocess.run(
        [sys.executable, "-m", "tools.qa_runner", "auth", "--mock-llm", "--no-mock-llm"],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 2
    assert "--mock-llm conflicts" in proc.stdout
