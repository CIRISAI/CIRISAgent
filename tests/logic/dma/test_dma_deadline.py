"""DMA attempts spend from the thought's deadline (CIRISAgent#1186).

`run_dma_with_retries` takes its per-try and attempt count from the active
budget profile at call time (not import time), clamps each try to the
thought's Deadline, and stops once the remainder cannot buy a useful try.
Fake clock throughout; nothing sleeps.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator, List
from unittest.mock import AsyncMock

import pytest

from ciris_engine.logic.config import llm_budget
from ciris_engine.logic.config.llm_budget import Deadline
from ciris_engine.logic.dma import dma_executor
from ciris_engine.logic.dma.dma_executor import MIN_USEFUL_ATTEMPT_S, run_dma_with_retries
from ciris_engine.logic.dma.exceptions import DMAFailure


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def budget_env(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    table: dict[str, str] = {}
    monkeypatch.setattr(llm_budget, "get_env_var", lambda name, default=None: table.get(name, default))
    return table


@pytest.fixture
def granted(monkeypatch: pytest.MonkeyPatch) -> List[float]:
    """Record the timeout each attempt ran under, without arming a real timer."""
    seen: List[float] = []

    @asynccontextmanager
    async def recording_timeout(delay: float) -> AsyncIterator[None]:
        seen.append(delay)
        yield

    monkeypatch.setattr(dma_executor, "_async_timeout", recording_timeout)
    from ciris_engine.logic.utils import error_emitter

    monkeypatch.setattr(error_emitter, "emit_dma_failure", AsyncMock())
    return seen


def _timing_out(clock: FakeClock, granted: List[float]) -> Any:
    async def run(**_: Any) -> Any:
        clock.now += granted[-1]
        raise TimeoutError()

    run.__name__ = "run_pdma"
    return run


@pytest.mark.asyncio
async def test_defaults_come_from_the_budget_at_call_time(budget_env, granted) -> None:
    clock = FakeClock()
    with pytest.raises(DMAFailure) as ei:
        await run_dma_with_retries(_timing_out(clock, granted))
    assert granted == [90.0, 90.0]  # REMOTE: 90s x 2
    assert "failed after 2 attempts" in str(ei.value)

    granted.clear()
    budget_env["CIRIS_LLM_BUDGET_PROFILE"] = "local"
    with pytest.raises(DMAFailure):
        await run_dma_with_retries(_timing_out(clock, granted))
    assert granted == [300.0]  # LOCAL: one long try


@pytest.mark.asyncio
async def test_env_override_is_read_at_call_time(budget_env, granted) -> None:
    budget_env["CIRIS_DMA_TIMEOUT"] = "120"
    with pytest.raises(DMAFailure):
        await run_dma_with_retries(_timing_out(FakeClock(), granted))
    assert granted == [120.0, 120.0]


@pytest.mark.asyncio
async def test_attempts_stop_at_the_deadline_and_the_last_is_clamped(budget_env, granted) -> None:
    clock = FakeClock()
    deadline = Deadline(100.0, clock=clock)
    with pytest.raises(DMAFailure) as ei:
        await run_dma_with_retries(
            _timing_out(clock, granted), retry_limit=3, timeout_seconds=45.0, deadline=deadline
        )
    # 45 + 45 + 10 (clamped to what was left); a 4th would not start anyway.
    assert granted == [45.0, 45.0, 10.0]
    assert "failed after 3 attempts" in str(ei.value)


@pytest.mark.asyncio
async def test_no_attempt_when_the_deadline_cannot_afford_one(budget_env, granted) -> None:
    clock = FakeClock()
    deadline = Deadline(MIN_USEFUL_ATTEMPT_S - 1, clock=clock)
    calls = {"n": 0}

    async def run(**_: Any) -> Any:
        calls["n"] += 1

    with pytest.raises(DMAFailure) as ei:
        await run_dma_with_retries(run, retry_limit=2, timeout_seconds=90.0, deadline=deadline)
    assert calls["n"] == 0
    assert "deadline exhausted" in str(ei.value)


@pytest.mark.asyncio
async def test_deadline_exhausted_mid_retry(budget_env, granted) -> None:
    clock = FakeClock()
    deadline = Deadline(95.0, clock=clock)
    with pytest.raises(DMAFailure) as ei:
        await run_dma_with_retries(
            _timing_out(clock, granted), retry_limit=2, timeout_seconds=90.0, deadline=deadline
        )
    # 5s left after the first try: below the 10s floor, so no second try.
    assert granted == [90.0]
    assert "failed after 1 attempts" in str(ei.value)


@pytest.mark.asyncio
async def test_no_deadline_is_unchanged(budget_env, granted) -> None:
    with pytest.raises(DMAFailure):
        await run_dma_with_retries(_timing_out(FakeClock(), granted), retry_limit=3, timeout_seconds=45.0)
    assert granted == [45.0, 45.0, 45.0]


@pytest.mark.asyncio
async def test_answer_within_the_deadline_is_returned(budget_env, granted) -> None:
    async def run(**_: Any) -> str:
        return "ok"

    assert await run_dma_with_retries(run, deadline=Deadline(100.0)) == "ok"
    assert granted == [90.0]
