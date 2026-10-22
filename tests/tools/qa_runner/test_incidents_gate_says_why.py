"""The QA incidents gate must say WHY it failed a run, not just that it did.

Run 39664086947 passed 38/38 tests and was red with "INCIDENTS DETECTED" and
nothing else: the gate returned on the first unexpected ERROR line without
naming it, and the CI classifier read UNKNOWN.
"""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from tools.qa_runner.runner import QARunner


def _gate(tmp_path: Path, text: str) -> QARunner:
    log = tmp_path / "incidents_latest.log"
    log.write_text(text)
    runner = QARunner.__new__(QARunner)
    runner.console = Console(record=True, width=200)
    runner._startup_incidents_position = 0
    runner._incident_reasons = []
    runner._incident_reason_counts = {}
    runner._incidents_log_path = lambda: log  # type: ignore[method-assign]
    return runner


MSASPDMA = (
    "2026-10-21 19:58:{s:02d}.511 - ERROR    - ciris_engine.logic.processors.core.thought_processor.main - "
    "main.py:823 - MSASPDMA: Failed for thought th_seed_dea828cf_ef8f60fc-e{s:02d}: no attribute 'final_action'\n"
)


def test_the_gate_names_the_lines_that_failed_it(tmp_path):
    text = (
        "2026-10-21 19:58:10.511 - CRITICAL - ciris_engine.logic.runtime.module_loader - module_loader.py:88 - "
        "MOCK_MODULE_LOADED: mock_llm - Production services disabled for types: ['llm']\n"
        + "".join(MSASPDMA.format(s=s) for s in range(13))
        + "2026-10-21 19:59:00.000 - ERROR    - some.module - x.py:1 - something else broke\n"
    )
    runner = _gate(tmp_path, text)
    assert runner._has_incidents_occurred() is True

    report = runner.incident_gate_report()
    assert report["failed"] is True and report["unverifiable"] is False
    lines = {entry["line"]: entry["count"] for entry in report["lines"]}
    # 13 identical errors collapse to one reason with its count; the mock's
    # expected CRITICAL is not a reason.
    assert len(lines) == 2, lines
    msaspdma = next(k for k in lines if "MSASPDMA: Failed" in k)
    assert lines[msaspdma] == 13
    assert any("something else broke" in k for k in lines)
    assert not any("MOCK_MODULE_LOADED" in k for k in lines)


def test_only_expected_lines_is_clean(tmp_path):
    runner = _gate(
        tmp_path,
        "2026-10-21 19:58:10.511 - CRITICAL - x - y.py:1 - MOCK_MODULE_LOADED: mock_llm - Production services disabled\n",
    )
    assert runner._has_incidents_occurred() is False
    assert runner.incident_gate_report() == {"failed": False, "unverifiable": False, "lines": []}


def test_an_unreadable_log_fails_closed(tmp_path):
    runner = _gate(tmp_path, "x")
    runner._incidents_log_path = lambda: tmp_path  # a directory: open() raises  # type: ignore[method-assign]
    runner._startup_incidents_position = -1
    assert runner._has_incidents_occurred() is True
    assert runner.incident_gate_report()["unverifiable"] is True
