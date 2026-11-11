"""A memory verb that its second pass did not fill in must not reach its handler (#1027).

ASPDMA selects MEMORIZE / RECALL / FORGET with no node and no query; the verb's
second pass supplies them. So "the second pass did not run" can no longer fall
back to "run what ASPDMA said" — there is nothing there. Before this change that
fallback wrote user facts to a freshly minted UUID nothing ever reads.

Also asserted: the conscience-retry path runs the second pass. It used to skip
it, so a retried TOOL ran with no parameters and a retried MEMORIZE went
straight to the handler.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.dma import dma_executor
from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.logic.processors.support.processing_queue import (
    ProcessingQueueItem,
    ThoughtContent,
)
from ciris_engine.schemas.actions.parameters import (
    ForgetParams,
    PonderParams,
    RecallParams,
    SpeakParams,
)
from ciris_engine.schemas.dma.results import (
    ActionSelectionDMAResult,
    ASPDMALLMResult,
    convert_llm_result_to_action_result,
)
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

MEMORY_VERBS = [
    HandlerActionType.MEMORIZE,
    HandlerActionType.RECALL,
    HandlerActionType.FORGET,
]


def _item() -> ProcessingQueueItem:
    return ProcessingQueueItem(
        thought_id="th-1",
        source_task_id="task-1",
        thought_type=ThoughtType.STANDARD,
        thought_depth=0,
        content=ThoughtContent(text="forget my favorite color"),
    )


def _selected(verb: HandlerActionType) -> ActionSelectionDMAResult:
    return convert_llm_result_to_action_result(
        ASPDMALLMResult(selected_action=verb, reasoning="selected by action selection"),
        user_prompt="ASPDMA USER",
        system_prompt="ASPDMA SYSTEM",
    )


def _processor(**evaluators: Any) -> ThoughtProcessor:
    processor = object.__new__(ThoughtProcessor)
    processor.dma_orchestrator = SimpleNamespace(**evaluators)
    processor._time_service = Mock()
    processor._emit_verb_second_pass_result_event = AsyncMock()  # type: ignore[method-assign]
    return processor


@pytest.mark.parametrize("verb", MEMORY_VERBS)
async def test_no_evaluator_configured_means_ponder_not_a_placeholder_action(
    verb: HandlerActionType,
) -> None:
    result = await _processor()._run_verb_second_pass(_item(), _selected(verb), SimpleNamespace())

    assert result.selected_action == HandlerActionType.PONDER
    assert isinstance(result.action_parameters, PonderParams)
    assert verb.value.upper() in result.action_parameters.questions[0]
    # The trace still shows the action-selection prompts that led here.
    assert (result.user_prompt, result.system_prompt) == (
        "ASPDMA USER",
        "ASPDMA SYSTEM",
    )


@pytest.mark.parametrize(
    "verb, attr, runner",
    [
        (HandlerActionType.MEMORIZE, "msaspdma_evaluator", "run_msaspdma"),
        (HandlerActionType.RECALL, "rsaspdma_evaluator", "run_rsaspdma"),
        (HandlerActionType.FORGET, "fsaspdma_evaluator", "run_fsaspdma"),
    ],
)
async def test_a_failed_second_pass_means_ponder(
    monkeypatch: pytest.MonkeyPatch, verb: HandlerActionType, attr: str, runner: str
) -> None:
    monkeypatch.setattr(dma_executor, runner, AsyncMock(side_effect=RuntimeError("LLM unavailable")))

    result = await _processor(**{attr: Mock()})._run_verb_second_pass(_item(), _selected(verb), SimpleNamespace())

    assert result.selected_action == HandlerActionType.PONDER


async def test_recall_runs_what_its_second_pass_addressed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    addressed = ActionSelectionDMAResult(
        selected_action=HandlerActionType.RECALL,
        action_parameters=RecallParams(node_id="user/alice"),
        rationale="RSASPDMA: on her node",
    )
    runner = AsyncMock(return_value=addressed)
    monkeypatch.setattr(dma_executor, "run_rsaspdma", runner)
    processor = _processor(rsaspdma_evaluator=Mock())

    result = await processor._run_verb_second_pass(_item(), _selected(HandlerActionType.RECALL), SimpleNamespace())

    assert result.selected_action == HandlerActionType.RECALL
    assert isinstance(result.action_parameters, RecallParams)
    assert result.action_parameters.node_id == "user/alice"
    runner.assert_awaited_once()
    event = processor._emit_verb_second_pass_result_event.await_args.kwargs  # type: ignore[attr-defined]
    assert (event["verb"], event["verb_specific_data"]["final_node_id"]) == (
        "recall",
        "user/alice",
    )


async def test_forget_runs_what_its_second_pass_named(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    named = ActionSelectionDMAResult(
        selected_action=HandlerActionType.FORGET,
        action_parameters=ForgetParams(
            node=GraphNode(
                id="user/alice",
                type=NodeType.USER,
                scope=GraphScope.LOCAL,
                attributes={},
            ),
            reason="she asked",
        ),
        rationale="FSASPDMA: her node",
    )
    monkeypatch.setattr(dma_executor, "run_fsaspdma", AsyncMock(return_value=named))
    processor = _processor(fsaspdma_evaluator=Mock())

    result = await processor._run_verb_second_pass(_item(), _selected(HandlerActionType.FORGET), SimpleNamespace())

    assert isinstance(result.action_parameters, ForgetParams)
    assert result.action_parameters.node.id == "user/alice"


async def test_a_second_pass_that_switches_to_speak_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    speak = ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content="That would also remove your pronouns. Go ahead?"),
        rationale="FSASPDMA: asking first",
    )
    monkeypatch.setattr(dma_executor, "run_fsaspdma", AsyncMock(return_value=speak))

    result = await _processor(fsaspdma_evaluator=Mock())._run_verb_second_pass(
        _item(), _selected(HandlerActionType.FORGET), SimpleNamespace()
    )

    assert result.selected_action == HandlerActionType.SPEAK


async def test_a_verb_with_no_second_pass_is_untouched() -> None:
    speak = _selected(HandlerActionType.SPEAK)
    assert await _processor()._run_verb_second_pass(_item(), speak, SimpleNamespace()) is speak


async def test_a_conscience_retry_goes_through_the_second_pass() -> None:
    """The retry is an ASPDMA result like the first: a verb awaiting its details."""
    processor = object.__new__(ThoughtProcessor)
    retried = _selected(HandlerActionType.FORGET)
    filled = ActionSelectionDMAResult(
        selected_action=HandlerActionType.PONDER,
        action_parameters=PonderParams(questions=["q"]),
        rationale="second pass ran",
    )
    processor._recursive_aspdma_step = AsyncMock(return_value=retried)  # type: ignore[method-assign]
    processor._run_verb_second_pass = AsyncMock(return_value=filled)  # type: ignore[method-assign]
    processor._recursive_conscience_step = AsyncMock(  # type: ignore[method-assign]
        return_value=SimpleNamespace(overridden=False, override_reason=None)
    )
    context = SimpleNamespace()

    attempt = await processor._execute_single_retry(_item(), SimpleNamespace(thought_id="th-1"), context, None, None, 1)

    processor._run_verb_second_pass.assert_awaited_once()
    assert processor._run_verb_second_pass.await_args.args[1] is retried
    assert attempt is not None and attempt.action_result is filled
    # The conscience judges what will actually run, not the bare verb.
    assert processor._recursive_conscience_step.await_args.args[1] is filled
