"""RSASPDMA and FSASPDMA: the recall and forget second passes (#1027).

ASPDMA selects RECALL / FORGET as a verb with nothing attached. These two
evaluators are where the read is addressed and the node to remove is named,
with the same graph guide and candidate nodes MSASPDMA gives a MEMORIZE.

Asserted here, for each:
  1. ASPDMA really does hand over nothing — the placeholder is what arrives.
  2. The prompt carries the shared graph guide and the nodes that exist.
  3. A usable verdict becomes the typed action; an unusable one becomes PONDER,
     never a guessed query or a guessed node (no healing, as in MSASPDMA).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List

import pytest

from ciris_engine.logic.dma.fsaspdma import FSASPDMAEvaluator, FSASPDMALLMResult
from ciris_engine.logic.dma.msaspdma import MSASPDMAEvaluator
from ciris_engine.logic.dma.rsaspdma import RSASPDMAEvaluator, RSASPDMALLMResult
from ciris_engine.logic.processors.support.processing_queue import (
    ProcessingQueueItem,
    ThoughtContent,
)
from ciris_engine.schemas.actions.parameters import (
    DeferParams,
    ForgetParams,
    MemorizeParams,
    PonderParams,
    RecallParams,
    SpeakParams,
)
from ciris_engine.schemas.dma.results import (
    UNADDRESSED_NODE_ID,
    ActionSelectionDMAResult,
    ASPDMALLMResult,
    convert_llm_result_to_action_result,
)
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType


def _context() -> SimpleNamespace:
    return SimpleNamespace(
        preferred_language="en",
        system_snapshot=SimpleNamespace(
            user_profiles=[
                SimpleNamespace(
                    user_id="alice",
                    display_name="Alice",
                    memorized_attributes={"favorite_color": "x"},
                )
            ],
            channel_id="api_x",
        ),
    )


def _thought(text: str) -> ProcessingQueueItem:
    return ProcessingQueueItem(
        thought_id="th-1",
        source_task_id="task-1",
        thought_type=ThoughtType.STANDARD,
        thought_depth=0,
        content=ThoughtContent(text=text),
    )


def _evaluator(cls: Any) -> Any:
    evaluator = cls.__new__(cls)  # no service registry needed to compose or convert
    evaluator._explicit_language = "en"
    evaluator._prompt_template_name = {
        RSASPDMAEvaluator: "rsaspdma",
        FSASPDMAEvaluator: "fsaspdma",
    }[cls]
    return evaluator


def _selected(verb: HandlerActionType) -> ActionSelectionDMAResult:
    """The verb exactly as ASPDMA leaves it."""
    return convert_llm_result_to_action_result(
        ASPDMALLMResult(selected_action=verb, reasoning="the user asked about their favorite color"),
        channel_id="api_x",
    )


def _system_and_user(messages: List[Any]) -> tuple[str, str]:
    return messages[-2]["content"], messages[-1]["content"]


# ------------------------------------------------- what ASPDMA hands over


def test_aspdma_hands_a_recall_over_with_nothing_to_read() -> None:
    params = _selected(HandlerActionType.RECALL).action_parameters
    assert isinstance(params, RecallParams)
    assert (params.query, params.node_id, params.node_type, params.scope) == (
        None,
        None,
        None,
        None,
    )


def test_aspdma_hands_a_forget_over_with_no_node() -> None:
    params = _selected(HandlerActionType.FORGET).action_parameters
    assert isinstance(params, ForgetParams)
    assert params.node.id == UNADDRESSED_NODE_ID


def test_aspdma_hands_a_memorize_over_with_its_scope_and_no_node() -> None:
    """The scope survives because the #1320 identity gate reads it before any model does."""
    result = convert_llm_result_to_action_result(
        ASPDMALLMResult(
            selected_action=HandlerActionType.MEMORIZE,
            reasoning="r",
            memorize_scope="identity",
        )
    )
    params = result.action_parameters
    assert isinstance(params, MemorizeParams)
    assert params.node.id == UNADDRESSED_NODE_ID
    assert params.node.scope == GraphScope.IDENTITY


def test_aspdma_hands_a_defer_over_with_its_reasoning_as_the_provisional_reason() -> None:
    params = _selected(HandlerActionType.DEFER).action_parameters
    assert isinstance(params, DeferParams)
    assert params.reason == "the user asked about their favorite color"
    assert params.defer_until is None


def test_a_model_that_still_emits_a_dropped_field_is_tolerated() -> None:
    """Old habits and other locales' templates must not turn into a parse failure."""
    result = ASPDMALLMResult.model_validate(
        {
            "selected_action": "recall",
            "reasoning": "r",
            "recall_query": "favorite color",
            "defer_until": "x",
        }
    )
    assert result.selected_action == HandlerActionType.RECALL
    assert not hasattr(result, "recall_query")


# ------------------------------------------------------------ the prompts


@pytest.mark.parametrize("cls", [RSASPDMAEvaluator, FSASPDMAEvaluator])
def test_the_prompt_carries_the_shared_graph_guide_and_the_nodes_that_exist(
    cls: Any,
) -> None:
    verb = HandlerActionType.RECALL if cls is RSASPDMAEvaluator else HandlerActionType.FORGET
    evaluator = _evaluator(cls)
    system, user = _system_and_user(
        evaluator.compose_messages(_thought("what is my favorite color?"), _selected(verb), context=_context())
    )

    # One description of the graph for all three memory verbs: MSASPDMA's own blocks.
    memorize = MSASPDMAEvaluator.__new__(MSASPDMAEvaluator)
    memorize._explicit_language = "en"
    memorize._prompt_template_name = "msaspdma"
    for key in ("memory_model", "addressing_convention", "scope_convention"):
        assert memorize._require_prompt_value(key) in system

    assert f"You have selected {verb.value.upper()}" in system
    assert "user/alice" in user and "channel/api_x" in user
    assert "favorite_color" in user  # what is already stored on the candidate
    assert "the user asked about their favorite color" in user
    assert UNADDRESSED_NODE_ID not in system + user


def test_the_forget_prompt_says_a_whole_node_goes_and_states_the_approval_facts() -> None:
    system, _ = _system_and_user(
        _evaluator(FSASPDMAEvaluator).compose_messages(
            _thought("forget my favorite color"),
            _selected(HandlerActionType.FORGET),
            context=_context(),
        )
    )
    assert "ONE WHOLE NODE" in system
    assert "Wise Authority" in system


# ------------------------------------------------------------ the verdicts


def test_recall_by_node_id() -> None:
    result = _evaluator(RSASPDMAEvaluator)._convert_recall(
        RSASPDMALLMResult(
            final_action="RECALL",
            node_id="user/alice",
            node_scope="local",
            reasoning="on her node",
        ),
        "api_x",
    )
    params = result.action_parameters
    assert result.selected_action == HandlerActionType.RECALL
    assert isinstance(params, RecallParams)
    assert (params.node_id, params.scope, params.channel_id) == (
        "user/alice",
        GraphScope.LOCAL,
        "api_x",
    )


def test_recall_by_query_with_an_unknown_scope_searches_every_scope() -> None:
    result = _evaluator(RSASPDMAEvaluator)._convert_recall(
        RSASPDMALLMResult(
            final_action="recall",
            query="favorite color",
            node_scope="everywhere",
            limit=0,
        ),
        None,
    )
    params = result.action_parameters
    assert isinstance(params, RecallParams)
    assert (params.query, params.scope, params.limit) == ("favorite color", None, 10)


def test_a_recall_with_nothing_to_read_ponders() -> None:
    result = _evaluator(RSASPDMAEvaluator)._convert_recall(RSASPDMALLMResult(final_action="RECALL"), None)
    assert result.selected_action == HandlerActionType.PONDER
    assert isinstance(result.action_parameters, PonderParams)


def test_recall_can_switch_to_speak_or_ponder() -> None:
    evaluator = _evaluator(RSASPDMAEvaluator)
    speak = evaluator._convert_recall(RSASPDMALLMResult(final_action="SPEAK", message="It is chartreuse."), "api_x")
    assert isinstance(speak.action_parameters, SpeakParams)
    assert speak.action_parameters.content == "It is chartreuse."
    ponder = evaluator._convert_recall(RSASPDMALLMResult(final_action="PONDER", questions=["which user?"]), None)
    assert isinstance(ponder.action_parameters, PonderParams)
    assert ponder.action_parameters.questions == ["which user?"]


def test_forget_takes_type_and_scope_from_the_node_that_exists() -> None:
    """The verdict's scope is advisory when the snapshot already knows the node."""
    evaluator = _evaluator(FSASPDMAEvaluator)
    candidates = MSASPDMAEvaluator.candidate_nodes_from_context(_context())
    result = evaluator._convert_forget(
        FSASPDMALLMResult(
            final_action="FORGET",
            node_id="user/alice",
            node_scope="identity",
            reason="she asked",
        ),
        "api_x",
        candidates,
    )
    params = result.action_parameters
    assert isinstance(params, ForgetParams)
    assert (params.node.id, params.node.type, params.node.scope) == (
        "user/alice",
        NodeType.USER,
        GraphScope.LOCAL,
    )
    assert params.reason == "she asked"


def test_forget_can_reach_a_node_outside_local_scope() -> None:
    """ASPDMA's conversion hardcoded scope=local, so such a node could not be forgotten at all."""
    result = _evaluator(FSASPDMAEvaluator)._convert_forget(
        FSASPDMALLMResult(
            final_action="FORGET",
            node_id="concept/x",
            node_scope="community",
            reason="stale",
        ),
        None,
        [],
    )
    params = result.action_parameters
    assert isinstance(params, ForgetParams)
    assert params.node.scope == GraphScope.COMMUNITY


def test_a_forget_with_no_node_ponders_rather_than_guessing_one() -> None:
    result = _evaluator(FSASPDMAEvaluator)._convert_forget(
        FSASPDMALLMResult(final_action="FORGET", reason="she asked"), None, []
    )
    assert result.selected_action == HandlerActionType.PONDER


def test_forget_can_switch_to_speak() -> None:
    result = _evaluator(FSASPDMAEvaluator)._convert_forget(
        FSASPDMALLMResult(
            final_action="SPEAK",
            message="That would also remove your pronouns. Go ahead?",
        ),
        "api_x",
        [],
    )
    assert result.selected_action == HandlerActionType.SPEAK
