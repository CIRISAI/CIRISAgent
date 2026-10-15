"""THE CLAIM PIN IS A FILE ON DISK, NEVER THE LOG (user ruling).

The node writes its one-time claim PIN to `<CIRIS_HOME>/claim_pin`. The agent
may say that a PIN was minted and where the file is; no agent log record and
no line on stdout ever carries the PIN value.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Iterator

import pytest

from ciris_engine.logic.runtime import node_fold
from ciris_engine.logic.utils import path_resolution

PIN = "7QK4-ZX9M"
REPO = Path(__file__).resolve().parents[4]


@pytest.fixture
def ciris_server_with_pin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

    (tmp_path / "claim_pin").write_text(PIN, encoding="utf-8")
    monkeypatch.setattr(path_resolution, "get_ciris_home", lambda: tmp_path)
    monkeypatch.setattr(ciris_server, "first_run_claim_pin", lambda: PIN, raising=False)
    yield tmp_path


def _all_text(caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]) -> str:
    out = capsys.readouterr()
    return "\n".join([r.getMessage() for r in caplog.records] + [out.out, out.err])


def test_a_minted_pin_is_announced_by_file_location_never_by_value(
    ciris_server_with_pin: Path, caplog: pytest.LogCaptureFixture, capsys: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)
    node_fold._surface_first_run_claim_pin()
    text = _all_text(caplog, capsys)

    assert PIN not in text and PIN.replace("-", "") not in text
    assert str(ciris_server_with_pin / "claim_pin") in text, "the line names the file"
    assert "/v1/setup/claim-remote" in text
    # The marker the mobile order/RCA checks key on survives.
    assert re.search(r"one-time CLAIM PIN", text)


def test_a_failing_accessor_does_not_leak_the_pin_either(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

    def boom() -> str:
        raise RuntimeError(f"pin {PIN} unreadable")

    monkeypatch.setattr(ciris_server, "first_run_claim_pin", boom, raising=False)
    caplog.set_level(logging.DEBUG)
    node_fold._surface_first_run_claim_pin()
    assert PIN not in _all_text(caplog, capsys)


def test_no_pin_means_no_line(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

    monkeypatch.setattr(ciris_server, "first_run_claim_pin", lambda: None, raising=False)
    caplog.set_level(logging.DEBUG)
    node_fold._surface_first_run_claim_pin()
    assert "CLAIM PIN" not in _all_text(caplog, capsys)


def test_nothing_in_the_agent_reads_the_pin_value_except_as_a_truth_test() -> None:
    """The in-process PIN accessor is consulted in one place, and nothing opens the PIN file."""
    callers = []
    readers = []
    for path in (REPO / "ciris_engine").rglob("*.py"):
        src = path.read_text(encoding="utf-8", errors="replace")
        if re.search(r"[\"']first_run_claim_pin[\"']|\.first_run_claim_pin\(", src):
            callers.append(path.relative_to(REPO).as_posix())
        if re.search(r"claim_pin[\"')]*\)?\.(read_text|read_bytes|open)\(|open\([^)]*claim_pin", src):
            readers.append(path.relative_to(REPO).as_posix())
    assert callers == ["ciris_engine/logic/runtime/node_fold.py"], callers
    assert readers == [], f"agent code reads the claim PIN file: {readers}"
