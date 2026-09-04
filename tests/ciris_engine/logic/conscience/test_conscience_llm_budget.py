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

    result = await _shard()._call_llm_with_budget(_sink(first_hangs_then_answers), handler_name="epistemic_humility_conscience")
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
    boom = RuntimeError("LLM response validation failed for EpistemicHumilityResult - reflective_justification Field required")
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


@pytest.mark.asyncio
async def test_transport_failures_are_not_retried_here() -> None:
    """The provider retried, the bus failed over; spending the budget again is
    what #1049 removed."""
    sink = _sink(ConnectionError("provider unreachable"))
    with patch.object(conscience_core, "categorize_conscience_error", return_value="CONNECTION_ERROR"):
        with pytest.raises(ConnectionError):
            await _shard()._call_llm_with_budget(sink, handler_name="x")
    assert sink.llm.call_llm_structured.await_count == 1


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
    sink = _sink(lambda **_: (_humility(recommended_action="speak", reflective_justification="no potential ethical concerns"), None))
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
