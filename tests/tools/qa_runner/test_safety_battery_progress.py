"""Per-question progress for the safety battery (CIRISAgent#1264).

Run 38492155330 printed "(1/9) ru_mh_v4_q01" and then nothing for 29 minutes
per question. The module now prints a heartbeat while a question is in flight,
with the agent's completed and failed LLM calls since the question started.
"""

import asyncio
import io

import pytest
from rich.console import Console

from tools.qa_runner.modules import safety_battery as sb

pytestmark = pytest.mark.timeout(60)

OK = "2026-10-14 09:27:21.435 - ciris_engine.logic.buses.llm_bus - INFO - [LLM-TIMING] CSDMAEvaluator th_1: 5537ms\n"
FAILED = "2026-09-25 01:36:39.918 - llm_service - ERROR - LLM call FAILED — model=Qwen/Qwen3.6-35B-A3B\n"
OTHER = "2026-10-14 09:27:22.000 - edge_runtime - INFO - [DELIVERY-STATUS] phase=kex-present-await-ship\n"


class TestLLMCallCounter:
    def test_counts_only_lines_appended_after_it_started(self, tmp_path):
        log = tmp_path / "latest.log"
        log.write_text(OK * 3, encoding="utf-8")  # an earlier question's calls

        counter = sb.LLMCallCounter(log)
        assert counter.poll() == (0, 0)

        with open(log, "a", encoding="utf-8") as fh:
            fh.write(OK + OTHER + FAILED + OK)
        assert counter.poll() == (2, 1)

        with open(log, "a", encoding="utf-8") as fh:
            fh.write(FAILED)
        assert counter.poll() == (2, 2)

    def test_an_unterminated_line_is_counted_once_it_completes(self, tmp_path):
        log = tmp_path / "latest.log"
        log.write_text("", encoding="utf-8")
        counter = sb.LLMCallCounter(log)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(OK[:40])
        assert counter.poll() == (0, 0)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(OK[40:])
        assert counter.poll() == (1, 0)

    def test_missing_log_counts_zero(self, tmp_path):
        assert sb.LLMCallCounter(tmp_path / "absent.log").poll() == (0, 0)
        assert sb.LLMCallCounter(None).poll() == (0, 0)


def test_agent_log_path_picks_the_newest_backend_log(tmp_path):
    for backend in ("postgres", "sqlite"):
        (tmp_path / backend).mkdir()
        (tmp_path / backend / "latest.log").write_text("x", encoding="utf-8")
    import os

    os.utime(tmp_path / "postgres" / "latest.log", (1, 1))
    assert sb.agent_log_path(tmp_path) == tmp_path / "sqlite" / "latest.log"
    assert sb.agent_log_path(tmp_path / "nowhere") is None


def test_a_question_in_flight_prints_a_heartbeat_with_llm_calls(tmp_path, monkeypatch):
    log = tmp_path / "latest.log"
    log.write_text("", encoding="utf-8")
    monkeypatch.setattr(sb, "PROGRESS_INTERVAL_S", 0.05)

    buf = io.StringIO()
    module = sb.SafetyBatteryTests.__new__(sb.SafetyBatteryTests)
    module.console = Console(file=buf, width=200, force_terminal=False)
    counter = sb.LLMCallCounter(log)

    async def slow_request():
        with open(log, "a", encoding="utf-8") as fh:
            fh.write(FAILED)
        await asyncio.sleep(0.2)
        return "reply"

    import time

    result = asyncio.run(module._await_with_progress("ru_mh_v4_q01", time.time(), counter, slow_request()))

    assert result == "reply"
    out = buf.getvalue()
    assert "ru_mh_v4_q01 in flight" in out
    assert "llm_calls ok=0 failed=1" in out
