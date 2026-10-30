"""The conscience facility owns its own LLM budget, and reads verbs for what they mean.

Two findings from the 2026-09-04 five-platform RCA, each pinned here:

1. llama-4-scout answered the epistemic-humility check with
   recommended_action="speak" -- the evaluated action's name, i.e. "go ahead" --
   and a bare `str` field accepted it, so `== "proceed"` failed a reply the
   model had just called ethically unremarkable. On the next thought it omitted
   a required field, instructor gave up, and the fail-closed fallback recorded
   "abort". Both turned a correct SPEAK into a forced PONDER.

2. Four conscience calls then hung in parallel for ~5 minutes. Below the
   conscience a single call can run 3 provider attempts x (1 + 2 reasks) x 60s;
   above it there was nothing (round_timeout_seconds is applied nowhere). The
   facility now has a budget sized to one honest call, retried once.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from ciris_engine.logic.conscience import core as conscience_core
from ciris_engine.logic.conscience.core import ConscienceConfig, EpistemicHumilityConscience, _BaseConscience
from ciris_engine.logic.conscience.transport import is_transport_failure
from ciris_engine.schemas.conscience.core import EpistemicHumilityResult, OptimizationVetoResult


def _humility(**kw: Any) -> EpistemicHumilityResult:
    base = dict(epistemic_certainty=0.9, reflective_justification="fine", recommended_action="proceed")
    base.update(kw)
    return EpistemicHumilityResult(**base)


# --- 1. the verb is read for what it means ---------------------------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("speak", "proceed"),  # the observed failure: an echo of the evaluated action is approval
        ("HandlerActionType.SPEAK", "proceed"),
        ("tool", "proceed"),
        (" Proceed.", "proceed"),
        ("continue", "proceed"),
        ("reconsider", "ponder"),
        ("escalate", "defer"),
        ("reject", "abort"),
        ("abort", "abort"),  # accepted: the conscience's own fail-closed fallback constructs it
    ],
)
def test_humility_verb_is_normalised(raw: str, expected: str) -> None:
    assert _humility(recommended_action=raw).recommended_action == expected


def test_humility_unknown_verb_is_a_validation_error_that_names_only_offered_verbs() -> None:
    """Unknown -> ValidationError -> instructor reasks with this message. 'abort'
    is accepted above but must not be advertised here."""
    with pytest.raises(ValidationError) as ei:
        _humility(recommended_action="banana")
    msg = str(ei.value)
    assert "proceed, ponder, defer" in msg
    assert "abort" not in msg.split("got")[0]


def test_humility_required_fields_are_still_required() -> None:
    """The normaliser widens what counts as a verb, never what counts as a result."""
    with pytest.raises(ValidationError):
        EpistemicHumilityResult(epistemic_certainty=0.9, recommended_action="proceed")  # no justification


@pytest.mark.parametrize("raw, expected", [("speak", "proceed"), ("veto", "abort"), ("Defer", "defer")])
def test_veto_decision_is_normalised(raw: str, expected: str) -> None:
    assert OptimizationVetoResult(decision=raw, entropy_reduction_ratio=0.0).decision == expected


@pytest.mark.parametrize("raw", ["ponder", "modify", "reconsider"])
def test_veto_reads_a_reconsider_verb_as_proceed(raw: str) -> None:
    """The veto has no reconsider verb and has always passed anything that was
    not abort/defer; a reconsider-word therefore means proceed there, and only
    there (the humility gate reads the same word as ponder)."""
    assert OptimizationVetoResult(decision=raw, entropy_reduction_ratio=0.0).decision == "proceed"


def test_veto_rejects_a_verb_it_cannot_read() -> None:
    with pytest.raises(ValidationError):
        OptimizationVetoResult(decision="banana", entropy_reduction_ratio=0.0)


# --- 2. the facility budget ------------------------------------------------


class _Shard(_BaseConscience):
    """Minimal concrete shard to exercise the helper in isolation."""

    async def check(self, action: Any, context: Any) -> Any:  # pragma: no cover - not used
        raise NotImplementedError


def _shard(timeout: float = 0.05, retries: int = 1) -> _Shard:
    cfg = ConscienceConfig(llm_call_timeout_seconds=timeout, llm_call_retries=retries)
    ts = MagicMock()
    ts.now.return_value = datetime.now(timezone.utc)
    return _Shard(MagicMock(), cfg, sink=MagicMock(), time_service=ts)


def _sink(side_effect: Any) -> MagicMock:
    sink = MagicMock()
    sink.llm.call_llm_structured = AsyncMock(side_effect=side_effect)
    return sink


async def _hang(**_: Any) -> Any:
    await asyncio.sleep(10)


@pytest.mark.asyncio
async def test_a_hung_call_is_cancelled_and_retried_once_with_a_fresh_call() -> None:
    answered = (_humility(), None)
    calls = {"n": 0}

    async def first_hangs_then_answers(**_: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            await asyncio.sleep(10)
        return answered

    result = await _shard()._call_llm_with_budget(
        _sink(first_hangs_then_answers), handler_name="epistemic_humility_conscience"
    )
    assert result is answered
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_budget_exhausted_by_timeouts_surfaces_as_transport() -> None:
    """Exhausted -> TimeoutError, categorised TIMEOUT, so the caller's transport
    branch returns unavailable_result: fail-closed, check_ran=False, no further
    retry -- the #1049 contract, reached only after the facility tried."""
    sink = _sink(_hang)
    with pytest.raises(TimeoutError) as ei:
        await _shard()._call_llm_with_budget(sink, handler_name="epistemic_humility_conscience")
    assert sink.llm.call_llm_structured.await_count == 2
    assert is_transport_failure(ei.value), "a facility timeout must read as TIMEOUT to the transport categoriser"


@pytest.mark.asyncio
async def test_a_schema_failure_gets_one_fresh_attempt_then_is_reraised() -> None:
    boom = RuntimeError(
        "LLM response validation failed for EpistemicHumilityResult - reflective_justification Field required"
    )
    sink = _sink([boom, boom])
    with patch.object(conscience_core, "categorize_conscience_error", return_value="VALIDATION_ERROR"):
        with pytest.raises(RuntimeError):
            await _shard()._call_llm_with_budget(sink, handler_name="epistemic_humility_conscience")
    assert sink.llm.call_llm_structured.await_count == 2


@pytest.mark.asyncio
async def test_a_schema_failure_then_success_returns_the_answer() -> None:
    answered = (_humility(), None)
    sink = _sink([RuntimeError("validation failed"), answered])
    with patch.object(conscience_core, "categorize_conscience_error", return_value="VALIDATION_ERROR"):
        assert await _shard()._call_llm_with_budget(sink, handler_name="x") is answered


#: What the conscience actually receives when the provider times out: the
#: LLM service raises TimeoutError("LLM API timeout - circuit breaker
#: activated") on the first occurrence (#1186), and the bus -- one attempt
#: per provider -- wraps it (llm_bus.py, "All LLM services failed for ...").
#: This is the exact shape #1247 counted 44 times.
_BUS_TIMEOUT = (
    "All LLM services failed for epistemic_humility_conscience. "
    "Last error: LLM API timeout - circuit breaker activated"
)


@pytest.mark.asyncio
async def test_a_provider_reported_timeout_gets_a_fresh_attempt() -> None:
    """CIRISAgent#1247, the dominant root cause.

    Nothing below the conscience retries a timeout since #1186, so this loop is
    the only retry layer. It used to re-raise any transport failure at once
    ("the provider already retried") -- true before #1186, false after -- so a
    provider-reported timeout got ONE attempt against a budget profile that
    promises four. One slow draw = a faculty that did not run.
    """
    answered = (_humility(), None)
    sink = _sink([RuntimeError(_BUS_TIMEOUT), answered])
    result = await _shard(retries=3)._call_llm_with_budget(sink, handler_name="epistemic_humility_conscience")
    assert result is answered
    assert sink.llm.call_llm_structured.await_count == 2


@pytest.mark.asyncio
async def test_provider_timeouts_exhaust_the_budget_then_read_as_transport() -> None:
    sink = _sink([RuntimeError(_BUS_TIMEOUT)] * 4)
    with pytest.raises(RuntimeError) as ei:
        await _shard(retries=3)._call_llm_with_budget(sink, handler_name="epistemic_humility_conscience")
    assert sink.llm.call_llm_structured.await_count == 4, "attempts are bounded by llm_call_retries + 1"
    assert is_transport_failure(ei.value)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "All LLM services failed for x. Last error: Connection error.",
        "All LLM services failed for x. Last error: Error code: 503 - Service Unavailable",
    ],
)
async def test_transient_transport_is_retried(message: str) -> None:
    answered = (_humility(), None)
    sink = _sink([RuntimeError(message), answered])
    with patch.object(
        conscience_core,
        "categorize_conscience_error",
        return_value="CONNECTION_ERROR" if "Connection" in message else "INTERNAL_ERROR",
    ):
        assert await _shard(retries=3)._call_llm_with_budget(sink, handler_name="x") is answered
    assert sink.llm.call_llm_structured.await_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category, message",
    [
        ("AUTH_ERROR", "Error code: 401 - Invalid API Key"),
        ("MODEL_NOT_AVAILABLE", "Error code: 404 - model_not_found"),
        ("RATE_LIMIT", "Error code: 429 - rate limited"),  # the bus already waited out the cooldown
        ("INTERNAL_ERROR", "HTTP 500 Insufficient credits: 0 available"),  # seen in #1247
        ("CONTEXT_LENGTH_EXCEEDED", "Error code: 400 - Input too long: 55321 input tokens, limit is 32768"),
        ("UNKNOWN", "something we have never seen"),
    ],
)
async def test_failures_a_retry_cannot_change_are_not_retried(category: str, message: str) -> None:
    """Config faults, an unfunded account, rate limits (already waited out
    below), and context overflow (the facility re-sends the identical payload)
    fail fast -- retrying them is pure latency against the thought deadline."""
    sink = _sink(RuntimeError(message))
    with patch.object(conscience_core, "categorize_conscience_error", return_value=category):
        with pytest.raises(RuntimeError):
            await _shard(retries=3)._call_llm_with_budget(sink, handler_name="x")
    assert sink.llm.call_llm_structured.await_count == 1


@pytest.mark.asyncio
async def test_the_real_categoriser_reads_the_bus_timeout_as_retryable() -> None:
    """No patching: the production categoriser must classify the bus's wrapped
    timeout as TIMEOUT, or the retry above never fires in production."""
    from ciris_engine.logic.conscience.transport import categorize_conscience_error, is_retryable_by_facility

    exc = RuntimeError(_BUS_TIMEOUT)
    assert categorize_conscience_error(exc) == "TIMEOUT"
    assert is_retryable_by_facility(exc)
    assert not is_retryable_by_facility(RuntimeError("HTTP 500 Insufficient credits: 0 available"))


@pytest.mark.asyncio
async def test_zero_retries_means_exactly_one_attempt() -> None:
    sink = _sink(_hang)
    with pytest.raises(TimeoutError):
        await _shard(retries=0)._call_llm_with_budget(sink, handler_name="x")
    assert sink.llm.call_llm_structured.await_count == 1


# --- 3. end to end through the humility shard --------------------------------


def _ctx() -> MagicMock:
    ctx = MagicMock()
    ctx.thought.thought_id = "th_test"
    ctx.thought.source_task_id = "task_test"
    return ctx


def _action() -> MagicMock:
    a = MagicMock()
    a.selected_action = "speak"
    a.action_parameters = {"content": "Hello! I can hear you."}
    return a


def _humility_shard(sink: MagicMock, timeout: float = 0.05) -> EpistemicHumilityConscience:
    cfg = ConscienceConfig(llm_call_timeout_seconds=timeout, llm_call_retries=1)
    ts = MagicMock()
    ts.now.return_value = datetime.now(timezone.utc)
    shard = EpistemicHumilityConscience(MagicMock(), cfg, sink=sink, time_service=ts)
    # persistence + prompt plumbing are not under test
    shard._create_trace_correlation = MagicMock(return_value=MagicMock())  # type: ignore[method-assign]
    shard._update_trace_correlation = MagicMock()  # type: ignore[method-assign]
    shard._create_epistemic_humility_messages = MagicMock(return_value=([], "prompt"))  # type: ignore[method-assign]
    shard._resolve_language = MagicMock(return_value="en")  # type: ignore[method-assign]
    shard._extract_user_message = MagicMock(return_value="Hello, can you hear me?")  # type: ignore[method-assign]
    shard._get_image_context_info = MagicMock(return_value=None)  # type: ignore[method-assign]
    return shard


@pytest.mark.asyncio
async def test_the_observed_scout_answer_now_passes() -> None:
    """recommended_action='speak' with a justification saying 'no concerns' is
    exactly what scout returned; it is an approval and the gate now reads it so."""
    sink = _sink(
        lambda **_: (
            _humility(recommended_action="speak", reflective_justification="no potential ethical concerns"),
            None,
        )
    )
    result = await _humility_shard(sink).check(_action(), _ctx())
    assert result.passed is True


@pytest.mark.asyncio
async def test_hung_humility_check_ends_as_did_not_run_not_as_a_veto() -> None:
    sink = _sink(_hang)
    result = await _humility_shard(sink).check(_action(), _ctx())
    assert result.passed is False
    assert getattr(result, "check_ran", None) is False
    assert "DID NOT RUN" in (result.reason or "")
    assert sink.llm.call_llm_structured.await_count == 2


@pytest.mark.asyncio
async def test_humility_check_survives_one_provider_timeout() -> None:
    """End to end, the #1247 shape: the first draw times out at the provider,
    the second answers. Before the fix this returned DID NOT RUN and forced a
    PONDER; now the faculty runs and judges."""
    answered = (_humility(), None)
    sink = _sink([RuntimeError(_BUS_TIMEOUT), answered])
    result = await _humility_shard(sink).check(_action(), _ctx())
    assert result.check_ran is True
    assert result.passed is True
    assert sink.llm.call_llm_structured.await_count == 2


@pytest.mark.asyncio
async def test_humility_non_transport_failure_fails_closed_as_did_not_run() -> None:
    """A context overflow used to become 'Epistemic humility concern: abort -
    LLM error: ...' with check_ran=True -- a fabricated judgement that also sent
    the processor into a retry of the same overflow."""
    sink = _sink(RuntimeError("Error code: 400 - Input too long: 55321 input tokens, limit is 32768 for this model"))
    result = await _humility_shard(sink).check(_action(), _ctx())
    assert result.passed is False
    assert result.check_ran is False
    assert "DID NOT RUN" in (result.reason or "")
    assert "concern: abort" not in (result.reason or "")
    assert sink.llm.call_llm_structured.await_count == 1


@pytest.mark.asyncio
async def test_a_slow_call_is_hedged_and_its_late_answer_is_taken(monkeypatch: pytest.MonkeyPatch) -> None:
    """2.18.0: past the shard's p95 a second call starts beside the slow one; the
    first answer wins and the other is cancelled, instead of the slow call being
    thrown away at the per-try limit."""
    from ciris_engine.logic.utils import hedging

    monkeypatch.setattr(hedging, "hedge_after_s", lambda name: 0.05)
    hedging.reset()
    answered = (_humility(), None)
    calls = {"n": 0, "cancelled": 0}

    async def slow_first(**_: Any) -> Any:
        calls["n"] += 1
        try:
            await asyncio.sleep(0.3 if calls["n"] == 1 else 5.0)
        except asyncio.CancelledError:
            calls["cancelled"] += 1
            raise
        return answered

    loop = asyncio.get_running_loop()
    began = loop.time()
    result = await _shard(timeout=2.0, retries=1)._call_llm_with_budget(_sink(slow_first), handler_name="x")
    assert result is answered
    assert loop.time() - began < 1.0, "the first call's answer was not taken when it arrived"
    assert calls == {"n": 2, "cancelled": 1}
