"""The conscience stage spends from the thought's deadline (CIRISAgent#1186).

`_call_llm_with_budget` clamps every attempt to what is left of the thought's
Deadline and stops starting attempts once the remainder cannot buy a useful
one. Running out ends in the same "LLM API timeout" TimeoutError, so the
fail-closed classification (TIMEOUT -> unavailable_result, check_ran=False)
is unchanged. Without a deadline it behaves exactly as per-try x attempts.

Everything runs on a fake clock: a "timed-out attempt" is an LLM double that
advances the clock by the timeout it was given and raises TimeoutError, so no
test sleeps.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest
from pydantic import ValidationError

from ciris_engine.logic.config.llm_budget import Deadline
from ciris_engine.logic.conscience import core as conscience_core
from ciris_engine.logic.conscience.core import (
    MIN_USEFUL_ATTEMPT_S,
    ConscienceConfig,
    EpistemicHumilityConscience,
    _BaseConscience,
    attempt_timeout,
    deadline_of,
)
from ciris_engine.logic.conscience.transport import is_transport_failure
from ciris_engine.schemas.config.llm_budget import LOCAL_PROFILE, REMOTE_PROFILE
from ciris_engine.schemas.conscience.context import ConscienceCheckContext


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class _Shard(_BaseConscience):
    async def check(self, action: Any, context: Any) -> Any:  # pragma: no cover - not used
        raise NotImplementedError


def _shard(per_try: float = 45.0, retries: int = 3) -> _Shard:
    cfg = ConscienceConfig(llm_call_timeout_seconds=per_try, llm_call_retries=retries)
    ts = MagicMock()
    ts.now.return_value = datetime.now(timezone.utc)
    return _Shard(MagicMock(), cfg, sink=MagicMock(), time_service=ts)


def _timing_out_sink(clock: FakeClock, used: List[float], monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    """Every attempt 'hangs' for exactly its timeout: the clock advances by the
    timeout the facility granted, then the attempt times out."""
    granted: List[float] = []
    real_attempt_timeout = conscience_core.attempt_timeout

    def spy(per_try_s: float, deadline: Any) -> Any:
        t = real_attempt_timeout(per_try_s, deadline)
        if t is not None:
            granted.append(t)
        return t

    monkeypatch.setattr(conscience_core, "attempt_timeout", spy)

    async def hang(**_: Any) -> Any:
        t = granted[-1]
        used.append(t)
        clock.now += t
        raise asyncio.TimeoutError()

    sink = MagicMock()
    sink.llm.call_llm_structured = AsyncMock(side_effect=hang)
    return sink


# --- config: the knobs are reachable and the defaults are the shipped REMOTE profile


def test_default_config_is_the_remote_profile() -> None:
    cfg = ConscienceConfig()
    assert cfg.llm_call_timeout_seconds == REMOTE_PROFILE.conscience_per_try_s == 45.0
    assert cfg.llm_call_retries + 1 == REMOTE_PROFILE.conscience_attempts == 4


@pytest.mark.parametrize("profile, per_try, retries", [(REMOTE_PROFILE, 45.0, 3), (LOCAL_PROFILE, 240.0, 0)])
def test_from_budget(profile: Any, per_try: float, retries: int) -> None:
    cfg = ConscienceConfig.from_budget(profile)
    assert (cfg.llm_call_timeout_seconds, cfg.llm_call_retries) == (per_try, retries)


def test_retry_bound_matches_the_profile_bound() -> None:
    """LLMBudgetProfile allows 1..5 conscience attempts, so retries 0..4."""
    assert ConscienceConfig(llm_call_retries=4).llm_call_retries == 4
    with pytest.raises(ValidationError):
        ConscienceConfig(llm_call_retries=5)


# --- attempt_timeout ----------------------------------------------------------


def test_attempt_timeout_without_deadline_is_the_static_per_try() -> None:
    assert attempt_timeout(45.0, None) == 45.0


def test_attempt_timeout_clamps_and_refuses() -> None:
    clock = FakeClock()
    d = Deadline(30.0, clock=clock)
    assert attempt_timeout(45.0, d) == 30.0
    clock.now = 20.0  # exactly MIN_USEFUL_ATTEMPT_S left
    assert attempt_timeout(45.0, d) == MIN_USEFUL_ATTEMPT_S
    clock.now = 20.5
    assert attempt_timeout(45.0, d) is None
    # A per-try shorter than the floor is its own floor.
    assert attempt_timeout(5.0, d) == 5.0


# --- (a) + (b): attempts stop at the deadline; the last one is clamped ----------


@pytest.mark.asyncio
async def test_attempts_stop_when_the_remainder_is_gone_and_the_last_is_clamped(monkeypatch) -> None:
    clock = FakeClock()
    used: List[float] = []
    sink = _timing_out_sink(clock, used, monkeypatch)
    deadline = Deadline(100.0, clock=clock)

    with pytest.raises(TimeoutError) as ei:
        await _shard()._call_llm_with_budget(sink, deadline=deadline, handler_name="entropy_conscience")

    # 45 + 45 + (10 left, clamped) = 100; the fourth attempt never starts.
    assert used == [45.0, 45.0, 10.0]
    assert sink.llm.call_llm_structured.await_count == 3
    assert "LLM API timeout" in str(ei.value)
    assert "thought deadline exhausted" in str(ei.value)
    assert is_transport_failure(ei.value)


@pytest.mark.asyncio
async def test_no_attempt_starts_on_an_exhausted_deadline(monkeypatch) -> None:
    clock = FakeClock()
    used: List[float] = []
    sink = _timing_out_sink(clock, used, monkeypatch)
    deadline = Deadline(5.0, clock=clock)  # < MIN_USEFUL_ATTEMPT_S

    with pytest.raises(TimeoutError) as ei:
        await _shard()._call_llm_with_budget(sink, deadline=deadline, handler_name="x")
    assert sink.llm.call_llm_structured.await_count == 0
    assert is_transport_failure(ei.value)


@pytest.mark.asyncio
async def test_a_schema_fault_followed_by_an_exhausted_deadline_reads_as_timeout(monkeypatch) -> None:
    """Out of time is out of time, whatever the previous try failed on."""
    clock = FakeClock()
    deadline = Deadline(50.0, clock=clock)

    async def slow_schema_fault(**_: Any) -> Any:
        clock.now += 45.0
        raise RuntimeError("LLM response validation failed")

    sink = MagicMock()
    sink.llm.call_llm_structured = AsyncMock(side_effect=slow_schema_fault)
    monkeypatch.setattr(conscience_core, "categorize_conscience_error", lambda e: "VALIDATION_ERROR")
    with pytest.raises(TimeoutError) as ei:
        await _shard()._call_llm_with_budget(sink, deadline=deadline, handler_name="x")
    assert sink.llm.call_llm_structured.await_count == 1
    assert "LLM API timeout" in str(ei.value)


# --- (c) no deadline -> unchanged -------------------------------------------------


@pytest.mark.asyncio
async def test_no_deadline_runs_every_attempt_at_the_full_per_try(monkeypatch) -> None:
    clock = FakeClock()
    used: List[float] = []
    sink = _timing_out_sink(clock, used, monkeypatch)
    with pytest.raises(TimeoutError) as ei:
        await _shard()._call_llm_with_budget(sink, handler_name="x")
    assert used == [45.0, 45.0, 45.0, 45.0]
    assert "4 of 4 attempts x 45s" in str(ei.value)
    assert "deadline" not in str(ei.value)


@pytest.mark.asyncio
async def test_an_ample_deadline_changes_nothing(monkeypatch) -> None:
    clock = FakeClock()
    used: List[float] = []
    sink = _timing_out_sink(clock, used, monkeypatch)
    with pytest.raises(TimeoutError):
        await _shard()._call_llm_with_budget(sink, deadline=Deadline(1000.0, clock=clock), handler_name="x")
    assert used == [45.0, 45.0, 45.0, 45.0]


# --- context plumbing -------------------------------------------------------------


def test_deadline_rides_the_conscience_context_but_is_not_serialised() -> None:
    d = Deadline(10.0)
    ctx = ConscienceCheckContext(thought=MagicMock(), deadline=d)
    assert deadline_of(ctx) is d
    assert "deadline" not in ctx.model_dump()


def test_deadline_of_ignores_anything_that_is_not_a_deadline() -> None:
    assert deadline_of(MagicMock()) is None  # a Mock's auto-attribute is not a deadline
    assert deadline_of(ConscienceCheckContext(thought=MagicMock())) is None


# --- (e) end to end through a shard: still fail-closed, still check_ran=False -----


def _humility_shard(sink: MagicMock) -> EpistemicHumilityConscience:
    ts = MagicMock()
    ts.now.return_value = datetime.now(timezone.utc)
    shard = EpistemicHumilityConscience(MagicMock(), ConscienceConfig(), sink=sink, time_service=ts)
    shard._create_trace_correlation = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
    shard._update_trace_correlation = MagicMock()  # type: ignore[method-assign]
    shard._create_epistemic_humility_messages = MagicMock(return_value=([], "prompt"))  # type: ignore[method-assign]
    shard._resolve_language = MagicMock(return_value="en")  # type: ignore[method-assign]
    shard._extract_user_message = MagicMock(return_value="Hello")  # type: ignore[method-assign]
    shard._get_image_context_info = MagicMock(return_value=None)  # type: ignore[method-assign]
    return shard


@pytest.mark.asyncio
async def test_shard_on_an_exhausted_deadline_is_unavailable_not_a_verdict() -> None:
    clock = FakeClock()
    sink = MagicMock()
    sink.llm.call_llm_structured = AsyncMock()
    thought = MagicMock()
    thought.thought_id = "th_deadline"
    thought.source_task_id = "task_deadline"
    ctx = ConscienceCheckContext(thought=thought, deadline=Deadline(1.0, clock=clock))

    action = MagicMock()
    action.selected_action = "speak"
    action.action_parameters = {"content": "Hello!"}
    result = await _humility_shard(sink).check(action, ctx)

    assert sink.llm.call_llm_structured.await_count == 0
    assert result.passed is False
    assert getattr(result, "check_ran", None) is False
    assert "DID NOT RUN" in (result.reason or "")
