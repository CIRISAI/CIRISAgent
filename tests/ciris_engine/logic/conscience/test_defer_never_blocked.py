"""A DEFER is never blocked (Eric, 2026-11-27).

Deferring is how a veto reaches a Wise Authority, who can always overrule it.
RATCHET 46040465835 (sh-un-07): a banned DEFER was turned into a PONDER every
round, and a guidance task pondered at depth 7 for 31 rounds with no exit.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List, Optional
from unittest.mock import patch

import pytest

from ciris_engine.logic.conscience.veto_contract import action_equivalence_key, banned_entry_for
from ciris_engine.schemas.actions.parameters import DeferParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.veto_record import ObjectionType, VetoRecordEntry, coerce_objection_type
from tests.ciris_engine.logic.conscience.test_veto_contract_1366 import (
    _STEP,
    Scripted,
    _english,  # noqa: F401 - autouse fixture
    _ok,
    _phase,
    _speak,
    _task,
    _veto,
)


def _defer(reason: str = "This needs a Wise Authority.") -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.DEFER,
        action_parameters=DeferParams(reason=reason, context={"why": "asked"}),
        rationale="defer",
    )


def _entry(action: ActionSelectionDMAResult, objection: ObjectionType = ObjectionType.SUBSTANTIVE) -> VetoRecordEntry:
    key = action_equivalence_key(action)
    return VetoRecordEntry(
        veto_id="veto_old",
        action_fingerprint=key,
        equivalence_key=key,
        objection_type=objection,
        conscience="entropy",
        reason="hallucinates a governance requirement",
        banned=True,
    )


async def _run(phase: Any, action: ActionSelectionDMAResult, *, task: Any = None, retry: bool = False) -> tuple:
    written: List[List[VetoRecordEntry]] = []
    item = SimpleNamespace(thought_id="th1", source_task_id="task1", conscience_feedback=None, deadline=None)
    thought = SimpleNamespace(thought_id="th1", source_task_id="task1")
    with patch("ciris_engine.logic.persistence.get_task_by_id_any_occurrence", return_value=task or _task()), patch(
        "ciris_engine.logic.persistence.models.tasks.append_task_vetoes",
        side_effect=lambda task_id, entries: written.append(list(entries)) or True,
    ):
        result = await _STEP(
            phase,
            item,
            action,
            thought=thought,
            dma_results=None,
            processing_context=SimpleNamespace(wa_authorization=None, is_conscience_retry=retry),
        )
    return result, written


def test_the_ban_never_matches_a_defer() -> None:
    defer = _defer()
    assert banned_entry_for(action_equivalence_key(defer), [_entry(defer)]) is None
    speak = _speak("hello")
    assert banned_entry_for(action_equivalence_key(speak), [_entry(speak)]) is not None  # others still banned


@pytest.mark.asyncio
async def test_a_defer_matching_a_banned_record_is_not_replaced() -> None:
    defer = _defer()
    entropy = Scripted(_ok())
    result, _ = await _run(_phase(entropy=entropy), defer, task=_task([_entry(defer)]))
    assert result.repeated_veto_id is None
    assert result.final_action.selected_action == HandlerActionType.DEFER
    assert not result.overridden


@pytest.mark.asyncio
async def test_a_vetoed_defer_stands_and_carries_the_objection_to_the_wa() -> None:
    coherence = Scripted(_veto(ObjectionType.SUBSTANTIVE, reason="a dodge dressed as a refusal"))
    result, written = await _run(_phase(coherence=coherence), _defer())
    assert coherence.calls == 1, "the consciences still review a DEFER"
    assert not result.overridden
    assert result.final_action.selected_action == HandlerActionType.DEFER
    params = result.final_action.action_parameters
    assert isinstance(params, DeferParams)
    assert params.context["why"] == "asked"  # the drafter's context is kept
    assert params.context["conscience_objections"] == ["coherence (substantive): a dodge dressed as a refusal"]
    assert written == [], "a veto of a DEFER is not recorded as a ban"


@pytest.mark.asyncio
async def test_the_retry_does_not_force_a_passing_defer_into_ponder() -> None:
    result, _ = await _run(_phase(coherence=Scripted(_ok())), _defer(), retry=True)
    assert result.final_action.selected_action == HandlerActionType.DEFER
    assert not result.overridden


@pytest.mark.asyncio
async def test_a_vetoed_speak_is_still_overridden() -> None:
    result, _ = await _run(_phase(coherence=Scripted(_veto(ObjectionType.SUBSTANTIVE))), _speak("hello"))
    assert result.overridden and result.final_action.selected_action == HandlerActionType.PONDER


@pytest.mark.parametrize("answer", [None, "", "nonsense", 7])
def test_an_unreadable_objection_type_is_justification(answer: Optional[object]) -> None:
    assert coerce_objection_type(answer) == ObjectionType.JUSTIFICATION


# --- F6 (RATCHET TLA+): the retry pass's DEFER is not replaced by the first pass's PONDER ---


def _cr(original: ActionSelectionDMAResult, final: ActionSelectionDMAResult, overridden: bool = True) -> Any:
    from ciris_engine.schemas.conscience.core import EpistemicData
    from ciris_engine.schemas.processors.core import ConscienceApplicationResult

    return ConscienceApplicationResult(
        original_action=original,
        final_action=final,
        overridden=overridden,
        override_reason="test",
        epistemic_data=EpistemicData(
            entropy_level=0.1, coherence_level=0.9, uncertainty_acknowledged=True, reasoning_transparency=1.0
        ),
    )


def _ponder() -> ActionSelectionDMAResult:
    from ciris_engine.schemas.actions.parameters import PonderParams

    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.PONDER,
        action_parameters=PonderParams(questions=["why?"]),
        rationale="ponder",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("benchmark", [False, True], ids=["normal", "benchmark"])
async def test_a_retry_pass_that_ends_in_defer_defers(benchmark: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    """The depth guardrail can force DEFER on the retry pass. That DEFER ends the thought."""
    from unittest.mock import AsyncMock

    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

    if benchmark:
        monkeypatch.setenv("CIRIS_BENCHMARK_MODE", "true")
        monkeypatch.setenv("CIRIS_TEMPLATE", "he-300-benchmark")
    retry = _speak()
    forced = _defer("Maximum thought depth reached.")
    proc = ThoughtProcessor.__new__(ThoughtProcessor)
    proc._conscience_execution_step = AsyncMock(return_value=_cr(retry, forced))  # type: ignore[method-assign]
    original = _cr(_speak(), _ponder())
    item = SimpleNamespace(thought_id="th1", source_task_id="task1", conscience_feedback=None, deadline=None)
    thought = SimpleNamespace(thought_id="th1", source_task_id="task1")

    action, result = await proc._process_conscience_retry_result(item, thought, None, SimpleNamespace(), retry, original)

    assert action.selected_action == HandlerActionType.DEFER
    assert result.final_action.selected_action == HandlerActionType.DEFER


@pytest.mark.asyncio
async def test_a_retry_pass_that_ends_in_ponder_still_ponders() -> None:
    """Negative control: the fall-through is unchanged for a vetoed retry that is not a DEFER."""
    from unittest.mock import AsyncMock

    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

    retry = _speak()
    proc = ThoughtProcessor.__new__(ThoughtProcessor)
    proc._conscience_execution_step = AsyncMock(return_value=_cr(retry, _ponder()))  # type: ignore[method-assign]
    original = _cr(_speak(), _ponder())
    item = SimpleNamespace(thought_id="th1", source_task_id="task1", conscience_feedback=None, deadline=None)
    thought = SimpleNamespace(thought_id="th1", source_task_id="task1")

    _, result = await proc._process_conscience_retry_result(item, thought, None, SimpleNamespace(), retry, original)

    assert result is original
    assert result.final_action.selected_action == HandlerActionType.PONDER
