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
        await run_dma_with_retries(_timing_out(clock, granted), retry_limit=3, timeout_seconds=45.0, deadline=deadline)
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
        await run_dma_with_retries(_timing_out(clock, granted), retry_limit=2, timeout_seconds=90.0, deadline=deadline)
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


# --- attempts follow the deadline; one retry policy ---------------------------


@pytest.mark.asyncio
async def test_attempts_follow_the_deadline_up_to_the_cap(budget_env, granted) -> None:
    """REMOTE floor is 2 attempts; a deadline that affords more buys up to the cap (3)."""
    clock = FakeClock()
    with pytest.raises(DMAFailure) as ei:
        await run_dma_with_retries(_timing_out(clock, granted), deadline=Deadline(1000.0, clock=clock))
    assert granted == [90.0, 90.0, 90.0]
    assert "failed after 3 attempts" in str(ei.value)


@pytest.mark.asyncio
async def test_extra_attempt_only_while_the_deadline_affords_it(budget_env, granted) -> None:
    clock = FakeClock()
    # 2 x 90 = 180 spent, 5 left: below a useful attempt, so no third.
    with pytest.raises(DMAFailure) as ei:
        await run_dma_with_retries(_timing_out(clock, granted), deadline=Deadline(185.0, clock=clock))
    assert granted == [90.0, 90.0]
    # The real failure is reported, not a manufactured "deadline exhausted".
    assert "deadline exhausted" not in str(ei.value)


@pytest.mark.asyncio
async def test_local_profile_never_buys_extra_attempts(budget_env, granted) -> None:
    budget_env["CIRIS_LLM_BUDGET_PROFILE"] = "local"
    clock = FakeClock()
    with pytest.raises(DMAFailure):
        await run_dma_with_retries(_timing_out(clock, granted), deadline=Deadline(5000.0, clock=clock))
    assert granted == [300.0]


@pytest.mark.parametrize(
    "message",
    [
        "Error code: 401 - unauthorized",
        "Error code: 404 - Unable to access model qwen-x",
        "Input too long: maximum context length is 32768 tokens",
        "HTTP 500 Insufficient credits: 0 available",
        "Error code: 429 - rate limit exceeded",
        "circuit breaker open for p (5 failures, last: LLM API timeout, retry in 40s)",
    ],
)
@pytest.mark.asyncio
async def test_non_transport_failures_fail_fast(budget_env, granted, message) -> None:
    calls = {"n": 0}

    async def run(**_: Any) -> Any:
        calls["n"] += 1
        raise RuntimeError(message)

    with pytest.raises(DMAFailure, match="failed after 1 attempts"):
        await run_dma_with_retries(run, retry_limit=3, timeout_seconds=30.0)
    assert calls["n"] == 1


def _connection_error() -> Exception:
    import httpx
    from openai import APIConnectionError

    return APIConnectionError(request=httpx.Request("POST", "https://api.example.invalid/v1"))


@pytest.mark.parametrize(
    "make_error",
    [
        lambda: RuntimeError("All LLM services failed for X. Last error: LLM API timeout"),
        _connection_error,
        lambda: RuntimeError("Error code: 503 - service unavailable"),
    ],
    ids=["timeout", "connection", "5xx"],
)
@pytest.mark.asyncio
async def test_transport_failures_are_retried(budget_env, granted, make_error) -> None:
    calls = {"n": 0}

    async def run(**_: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise make_error()
        return "ok"

    assert await run_dma_with_retries(run, retry_limit=2, timeout_seconds=30.0) == "ok"
    assert calls["n"] == 2


# --- schema-invalid model output is re-drawn, like transport -------------------


def _pydantic_validation_error() -> Exception:
    from pydantic import BaseModel, ValidationError

    class Reply(BaseModel):
        selected_action: str

    try:
        Reply.model_validate({"selected_action": None})
    except ValidationError as e:
        return e
    raise AssertionError("unreachable")


def _instructor_retry_exception() -> Exception:
    # Named like instructor's, message deliberately free of the categorizer's
    # keywords: the type alone must mark it as a schema failure.
    class InstructorRetryException(Exception):
        pass

    return InstructorRetryException("reply did not parse after reasks")


@pytest.mark.parametrize(
    "make_error",
    [
        # What the LLM service raises for a schema failure after instructor's reasks.
        lambda: RuntimeError(
            "LLM response validation failed for ActionSelectionDMAResult - circuit breaker activated for failover"
        ),
        _pydantic_validation_error,
        _instructor_retry_exception,
    ],
    ids=["service-wrapped", "pydantic", "instructor"],
)
@pytest.mark.asyncio
async def test_schema_invalid_first_reply_is_redrawn(budget_env, granted, make_error) -> None:
    """Stochastic schema noise: the first reply fails validation, the re-draw succeeds."""
    calls = {"n": 0}

    async def run(**_: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise make_error()
        return "ok"

    assert await run_dma_with_retries(run, retry_limit=2, timeout_seconds=30.0) == "ok"
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_schema_redraws_stay_within_the_deadline_and_cap(budget_env, granted) -> None:
    clock = FakeClock()

    async def run(**_: Any) -> Any:
        clock.now += 5.0
        raise RuntimeError("LLM response validation failed for CSDMAResult")

    with pytest.raises(DMAFailure, match="failed after 3 attempts"):
        await run_dma_with_retries(run, deadline=Deadline(1000.0, clock=clock))
    assert len(granted) == 3  # REMOTE dma_attempt_cap, never more
