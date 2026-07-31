"""
Decision-preservation tests for the parallel conscience dispatch (issue #889).

The four epistemic conscience LLM checks (Entropy, Coherence,
OptimizationVeto, EpistemicHumility) are dispatched concurrently via
``asyncio.gather`` in ``_conscience_execution_step`` and their results are
folded in registry PRIORITY order. This is an ethical gate — these tests
pin the decision-preserving contract:

1. All four checks genuinely run CONCURRENTLY (barrier proof: no check can
   complete until every other check has entered ``check()`` — a serial
   dispatch deadlocks and times out).
2. Override precedence is priority order, NOT completion order: when a
   lower-priority check fails faster than a higher-priority one, the
   higher-priority failure wins (identical override decision +
   override_reason as the old serial break-on-first-failure loop).
3. An exception in one check maps to the same final decision as the serial
   code (exception -> skip that check -> next failing check in priority
   order wins, or no override if the rest pass).
4. The intended #889 delta: every completed check's results fold into
   epistemic_data / per-check fields even when an early check fails
   (the serial loop broke early and dropped them).

The step function is tested unwrapped (below the @streaming_step /
@step_point envelope): these tests target the dispatch/fold semantics; the
streaming envelope is covered by test_step_decorators.py.
"""

import asyncio
from types import SimpleNamespace
from typing import List, Optional
from unittest.mock import Mock

import pytest


@pytest.fixture(autouse=True)
def reset_language_to_english(monkeypatch):
    """Reset language to English before each test to avoid test pollution."""
    monkeypatch.setenv("CIRIS_PREFERRED_LANGUAGE", "en")

    try:
        from ciris_engine.logic.utils.localization import clear_cache

        clear_cache()
    except ImportError:
        pass

    yield

    try:
        from ciris_engine.logic.utils.localization import clear_cache

        clear_cache()
    except ImportError:
        pass


from ciris_engine.logic.conscience.registry import conscienceRegistry
from ciris_engine.logic.processors.core.thought_processor.conscience_execution import ConscienceExecutionPhase
from ciris_engine.schemas.actions.parameters import SpeakParams
from ciris_engine.schemas.conscience.core import (
    ConscienceCheckResult,
    ConscienceStatus,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType

# Unwrap @streaming_step -> @step_point -> original coroutine function.
_UNWRAPPED_STEP = ConscienceExecutionPhase._conscience_execution_step.__wrapped__.__wrapped__
assert _UNWRAPPED_STEP.__name__ == "_conscience_execution_step"


class ScriptedConscience:
    """Conscience double with scripted result, delay, exception, and an
    optional all-peers-entered barrier for the concurrency-overlap proof."""

    def __init__(
        self,
        result: Optional[ConscienceCheckResult] = None,
        delay: float = 0.0,
        exc: Optional[BaseException] = None,
        wait_for_peers: bool = False,
    ) -> None:
        self.result = result
        self.delay = delay
        self.exc = exc
        self.wait_for_peers = wait_for_peers
        self.peers: List["ScriptedConscience"] = []
        self.entered = asyncio.Event()
        self.calls = 0

    async def check(self, action, context) -> ConscienceCheckResult:
        self.calls += 1
        self.entered.set()
        if self.wait_for_peers:
            # Refuse to complete until EVERY peer has entered check().
            # Under serial dispatch the first check would wait forever for
            # peers that haven't been started yet — only concurrent
            # dispatch can satisfy this barrier before the timeout.
            await asyncio.wait_for(
                asyncio.gather(*(p.entered.wait() for p in self.peers)),
                timeout=2.0,
            )
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.exc is not None:
            raise self.exc
        assert self.result is not None
        return self.result


def entropy_result(passed: bool = True, reason: Optional[str] = None) -> ConscienceCheckResult:
    return ConscienceCheckResult(
        status=ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED,
        passed=passed,
        reason=reason,
        entropy_score=0.2,
        entropy_prompt="entropy-prompt",
    )


def coherence_result(passed: bool = True, reason: Optional[str] = None) -> ConscienceCheckResult:
    return ConscienceCheckResult(
        status=ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED,
        passed=passed,
        reason=reason,
        coherence_score=0.9,
        coherence_prompt="coherence-prompt",
    )


def veto_result(passed: bool = True, reason: Optional[str] = None) -> ConscienceCheckResult:
    return ConscienceCheckResult(
        status=ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED,
        passed=passed,
        reason=reason,
        optimization_veto_check=OptimizationVetoResult(
            decision="proceed" if passed else "abort",
            justification="scripted",
            entropy_reduction_ratio=0.1,
        ),
    )


def humility_result(passed: bool = True, reason: Optional[str] = None) -> ConscienceCheckResult:
    return ConscienceCheckResult(
        status=ConscienceStatus.PASSED if passed else ConscienceStatus.FAILED,
        passed=passed,
        reason=reason,
        epistemic_humility_check=EpistemicHumilityResult(
            epistemic_certainty=0.8,
            reflective_justification="scripted",
            recommended_action="proceed" if passed else "ponder",
        ),
    )


def make_phase(*consciences: ScriptedConscience) -> ConscienceExecutionPhase:
    """Build a phase with the given consciences registered at priorities
    0..n-1 under the canonical names (entropy first = highest priority)."""
    names = ["entropy", "coherence", "optimization_veto", "epistemic_humility"]
    registry = conscienceRegistry()
    for priority, (name, conscience) in enumerate(zip(names, consciences)):
        registry.register_conscience(name=name, conscience=conscience, priority=priority)

    phase = ConscienceExecutionPhase.__new__(ConscienceExecutionPhase)
    phase.conscience_registry = registry
    phase._describe_action = Mock(return_value="speak 'hello'")
    return phase


def make_action() -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="hello"),
        rationale="test action",
        raw_llm_response=None,
        reasoning=None,
        evaluation_time_ms=None,
        resource_usage=None,
    )


async def run_step(phase: ConscienceExecutionPhase, action: ActionSelectionDMAResult):
    return await _UNWRAPPED_STEP(
        phase,
        SimpleNamespace(thought_id="th_parallel_test"),
        action,
        thought=None,
        dma_results=None,
        processing_context=None,
    )


class TestConcurrentDispatch:
    """(a) Proof the four checks are in flight simultaneously."""

    @pytest.mark.asyncio
    async def test_all_four_checks_overlap_in_flight(self):
        consciences = [
            ScriptedConscience(result=entropy_result(), wait_for_peers=True),
            ScriptedConscience(result=coherence_result(), wait_for_peers=True),
            ScriptedConscience(result=veto_result(), wait_for_peers=True),
            ScriptedConscience(result=humility_result(), wait_for_peers=True),
        ]
        for c in consciences:
            c.peers = [p for p in consciences if p is not c]

        phase = make_phase(*consciences)
        result = await run_step(phase, make_action())

        assert all(c.calls == 1 for c in consciences)
        assert result.overridden is False
        assert result.override_reason is None
        assert result.final_action.selected_action == HandlerActionType.SPEAK
        # All four folded in.
        assert result.entropy_check is not None
        assert result.coherence_check is not None
        assert result.optimization_veto_check is not None
        assert result.epistemic_humility_check is not None
        assert result.epistemic_data.entropy_level == pytest.approx(0.2)
        assert result.epistemic_data.coherence_level == pytest.approx(0.9)
        assert result.epistemic_data.uncertainty_acknowledged is True
        assert result.epistemic_data.reasoning_transparency == pytest.approx(1.0)


class TestPriorityOrderOverride:
    """(b) Priority order, not completion order, decides the override."""

    @pytest.mark.asyncio
    async def test_slower_higher_priority_failure_beats_faster_lower_priority_failure(self):
        # Entropy (priority 0) fails SLOWLY; Coherence (priority 1) fails
        # INSTANTLY. Completion order is coherence-first, but the fold must
        # apply the serial loop's precedence: entropy wins.
        phase = make_phase(
            ScriptedConscience(result=entropy_result(passed=False, reason="entropy: too random"), delay=0.2),
            ScriptedConscience(result=coherence_result(passed=False, reason="coherence: incoherent")),
            ScriptedConscience(result=veto_result()),
            ScriptedConscience(result=humility_result()),
        )
        result = await run_step(phase, make_action())

        assert result.overridden is True
        assert result.override_reason == "entropy: too random"
        assert result.final_action.selected_action == HandlerActionType.PONDER
        # The PONDER rationale names the winning (priority-first) conscience.
        assert "entropy" in result.final_action.rationale
        assert "coherence" not in result.final_action.rationale
        # The failing reason lands in the ponder questions, as in serial code.
        assert "entropy: too random" in result.final_action.action_parameters.questions
        assert result.original_action.selected_action == HandlerActionType.SPEAK

    @pytest.mark.asyncio
    async def test_lower_priority_failure_wins_when_higher_priority_passes(self):
        phase = make_phase(
            ScriptedConscience(result=entropy_result()),
            ScriptedConscience(result=coherence_result(passed=False, reason="coherence: incoherent")),
            ScriptedConscience(result=veto_result()),
            ScriptedConscience(result=humility_result()),
        )
        result = await run_step(phase, make_action())

        assert result.overridden is True
        assert result.override_reason == "coherence: incoherent"
        assert result.final_action.selected_action == HandlerActionType.PONDER
        assert "coherence" in result.final_action.rationale


class TestExceptionParity:
    """(c) An exception in one check yields the serial code's decision."""

    @pytest.mark.asyncio
    async def test_exception_in_higher_priority_check_defers_to_next_failure(self):
        # Serial semantics: exception -> log + record_failure + continue.
        # The next failing check in priority order provides the override.
        phase = make_phase(
            ScriptedConscience(exc=RuntimeError("LLM boom")),
            ScriptedConscience(result=coherence_result(passed=False, reason="coherence: incoherent")),
            ScriptedConscience(result=veto_result()),
            ScriptedConscience(result=humility_result()),
        )
        result = await run_step(phase, make_action())

        assert result.overridden is True
        assert result.override_reason == "coherence: incoherent"
        assert result.final_action.selected_action == HandlerActionType.PONDER
        assert "coherence" in result.final_action.rationale
        # The errored check contributed nothing, exactly like serial `continue`.
        assert result.entropy_check is None

    @pytest.mark.asyncio
    async def test_exception_with_all_others_passing_yields_no_override(self):
        phase = make_phase(
            ScriptedConscience(exc=RuntimeError("LLM boom")),
            ScriptedConscience(result=coherence_result()),
            ScriptedConscience(result=veto_result()),
            ScriptedConscience(result=humility_result()),
        )
        action = make_action()
        result = await run_step(phase, action)

        assert result.overridden is False
        assert result.override_reason is None
        assert result.final_action.selected_action == HandlerActionType.SPEAK
        assert result.entropy_check is None
        # Missing entropy falls back to the serial code's default safe value.
        assert result.epistemic_data.entropy_level == pytest.approx(0.1)
        assert result.epistemic_data.coherence_level == pytest.approx(0.9)


class TestCompleteFoldDelta:
    """(#889 intended delta) All completed checks fold in, even after an
    early failure — the serial loop broke early and dropped them."""

    @pytest.mark.asyncio
    async def test_all_checks_fold_even_when_highest_priority_fails(self):
        phase = make_phase(
            ScriptedConscience(result=entropy_result(passed=False, reason="entropy: too random")),
            ScriptedConscience(result=coherence_result()),
            ScriptedConscience(result=veto_result()),
            ScriptedConscience(result=humility_result()),
        )
        result = await run_step(phase, make_action())

        # Override decision identical to serial: entropy wins.
        assert result.overridden is True
        assert result.override_reason == "entropy: too random"
        assert result.final_action.selected_action == HandlerActionType.PONDER
        # Delta: the serial loop would have left these None/False.
        assert result.coherence_check is not None
        assert result.coherence_check.passed is True
        assert result.optimization_veto_check is not None
        assert result.epistemic_humility_check is not None
        assert result.epistemic_data.coherence_level == pytest.approx(0.9)
        assert result.epistemic_data.uncertainty_acknowledged is True
        assert result.epistemic_data.reasoning_transparency == pytest.approx(1.0)
        # And the entropy failure itself is still fully recorded.
        assert result.entropy_check is not None
        assert result.entropy_check.passed is False


class TestRunSingleConscienceHelper:
    """Per-check circuit-breaker/exception handling matches the serial loop."""

    @pytest.fixture
    def phase(self):
        return ConscienceExecutionPhase.__new__(ConscienceExecutionPhase)

    def _entry(self, check=None, side_effect=None):
        entry = Mock()
        entry.name = "TestConscience"
        entry.conscience = Mock()
        if side_effect is not None:
            entry.conscience.check = Mock(side_effect=side_effect)
        else:
            check_result = check if check is not None else entropy_result()

            async def _check(action, context):
                return check_result

            entry.conscience.check = _check
        entry.circuit_breaker = Mock()
        entry.circuit_breaker.check_and_raise = Mock()
        entry.circuit_breaker.record_success = Mock()
        entry.circuit_breaker.record_failure = Mock()
        return entry

    @pytest.mark.asyncio
    async def test_success_records_cb_success(self, phase):
        entry = self._entry()
        result = await phase._run_single_conscience(entry, Mock(), Mock())
        assert result is not None
        entry.circuit_breaker.record_success.assert_called_once()
        entry.circuit_breaker.record_failure.assert_not_called()

    @pytest.mark.asyncio
    async def test_exception_returns_none_and_records_cb_failure(self, phase):
        async def _boom(action, context):
            raise RuntimeError("LLM boom")

        entry = self._entry()
        entry.conscience.check = _boom
        result = await phase._run_single_conscience(entry, Mock(), Mock())
        assert result is None
        entry.circuit_breaker.record_failure.assert_called_once()
        entry.circuit_breaker.record_success.assert_not_called()

    @pytest.mark.asyncio
    async def test_open_circuit_breaker_returns_none_without_recording_failure(self, phase):
        from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerError

        entry = self._entry()
        entry.circuit_breaker.check_and_raise = Mock(side_effect=CircuitBreakerError("open"))
        result = await phase._run_single_conscience(entry, Mock(), Mock())
        assert result is None
        entry.circuit_breaker.record_failure.assert_not_called()
        entry.circuit_breaker.record_success.assert_not_called()
