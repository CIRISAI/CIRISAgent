"""The conscience's veto reaches every verb second pass on a retry (#1366 item 1).

On a conscience retry the processor stores the veto on the queue item
(``failed_action``, ``failure_reason``, ``retry_guidance``) and ASPDMA renders
the CONSCIENCE OVERRIDE GUIDANCE block. The second pass then re-decides the
action -- and never saw that block: TSASPDMA got the veto reason in 0 of 162
retry calls and re-proposed the same vetoed ticket four times.

Driven from ``ThoughtProcessor._run_verb_second_pass`` down through
``dma_executor.run_*`` into each REAL evaluator's prompt composition; only the
LLM call is intercepted, to record the messages actually sent.

Also: ``_describe_action`` names the vetoed tool (it read ``tool_name``, which
ToolParams does not have, so the guidance always said "use a tool").
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.dma.dsaspdma import DSASPDMAEvaluator
from ciris_engine.logic.dma.fsaspdma import FSASPDMAEvaluator
from ciris_engine.logic.dma.msaspdma import MSASPDMAEvaluator
from ciris_engine.logic.dma.rsaspdma import RSASPDMAEvaluator
from ciris_engine.logic.dma.tsaspdma import TSASPDMAEvaluator
from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.actions.parameters import DeferParams, ToolParams
from ciris_engine.schemas.adapters.tools import ToolInfo, ToolParameterSchema
from ciris_engine.schemas.conscience.core import EpistemicData
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult, ASPDMALLMResult, convert_llm_result_to_action_result
from ciris_engine.schemas.processors.core import ConscienceApplicationResult
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtType

VETO_REASON = "VETO-7f3a: the ticket duplicates one the user already closed"


class _Captured(Exception):
    """Raised in place of the LLM call once the prompt has been recorded."""


def _evaluator(cls: Any, template: str, sent: List[List[Dict[str, Any]]]) -> Any:
    evaluator = cls.__new__(cls)  # no service registry needed to compose a prompt
    evaluator._prompt_template_name = template
    evaluator.prompt_overrides = {}

    async def call_llm_structured(*, messages: List[Dict[str, Any]], **_: Any) -> Any:
        sent.append(messages)
        raise _Captured()

    evaluator.call_llm_structured = call_llm_structured
    return evaluator


def _processor(sent: List[List[Dict[str, Any]]]) -> ThoughtProcessor:
    proc = ThoughtProcessor.__new__(ThoughtProcessor)
    proc._time_service = Mock(now=Mock(return_value=datetime.now(timezone.utc)))
    proc.dma_orchestrator = SimpleNamespace(
        tsaspdma_evaluator=_evaluator(TSASPDMAEvaluator, "tsaspdma", sent),
        dsaspdma_evaluator=_evaluator(DSASPDMAEvaluator, "dsaspdma", sent),
        msaspdma_evaluator=_evaluator(MSASPDMAEvaluator, "msaspdma", sent),
        rsaspdma_evaluator=_evaluator(RSASPDMAEvaluator, "rsaspdma", sent),
        fsaspdma_evaluator=_evaluator(FSASPDMAEvaluator, "fsaspdma", sent),
    )
    tool = ToolInfo(
        name="create_ticket",
        description="File a ticket",
        parameters=ToolParameterSchema(type="object", properties={"title": {"type": "string"}}, required=["title"]),
    )
    proc.dependencies = SimpleNamespace(
        bus_manager=SimpleNamespace(tool=SimpleNamespace(get_tool_info=AsyncMock(return_value=tool)))
    )
    proc._emit_verb_second_pass_result_event = AsyncMock()  # type: ignore[method-assign]
    proc._emit_tsaspdma_result_event = AsyncMock()  # type: ignore[method-assign]
    proc._refuse_unapproved_identity_memorize = AsyncMock(return_value=None)  # type: ignore[method-assign]
    return proc


def _item() -> ProcessingQueueItem:
    return ProcessingQueueItem(
        thought_id="th-veto",
        source_task_id="task-veto",
        thought_type=ThoughtType.STANDARD,
        thought_depth=0,
        content=ThoughtContent(text="please file a ticket about the login bug"),
    )


def _selected(verb: HandlerActionType) -> ActionSelectionDMAResult:
    if verb == HandlerActionType.TOOL:
        return ActionSelectionDMAResult(
            selected_action=verb,
            action_parameters=ToolParams(name="create_ticket", parameters={}),
            rationale="file it",
        )
    if verb == HandlerActionType.DEFER:
        return ActionSelectionDMAResult(
            selected_action=verb,
            action_parameters=DeferParams(reason="needs a human", context={}),
            rationale="defer it",
        )
    return convert_llm_result_to_action_result(
        ASPDMALLMResult(selected_action=verb, reasoning="the user asked about the login bug"),
        channel_id="api_x",
    )


def _feedback(proc: ThoughtProcessor) -> Dict[str, Any]:
    """The feedback the real retry path stores, guidance built by the real builder."""
    attempted = proc._describe_action(_selected(HandlerActionType.TOOL))
    return {
        "failed_action": attempted,
        "failure_reason": VETO_REASON,
        "retry_guidance": proc._build_retry_guidance(attempted, VETO_REASON, None, None, language="en"),
    }


def _user_prompt(messages: List[Dict[str, Any]]) -> str:
    return str([m for m in messages if m["role"] == "user"][-1]["content"])


VERBS = [
    HandlerActionType.TOOL,
    HandlerActionType.DEFER,
    HandlerActionType.MEMORIZE,
    HandlerActionType.RECALL,
    HandlerActionType.FORGET,
]


async def _run(verb: HandlerActionType, feedback: Optional[Dict[str, Any]]) -> str:
    sent: List[List[Dict[str, Any]]] = []
    proc = _processor(sent)
    with patch("ciris_engine.logic.dma.dma_executor.persistence"):
        if feedback is None:
            await proc._run_verb_second_pass(_item(), _selected(verb), None)
        else:
            await proc._run_verb_second_pass(_item(), _selected(verb), None, conscience_feedback=feedback)
    assert len(sent) == 1, f"{verb.value}: expected one second-pass LLM call, got {len(sent)}"
    return _user_prompt(sent[0])


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", VERBS, ids=lambda v: v.value)
async def test_retry_second_pass_prompt_carries_the_veto(verb: HandlerActionType) -> None:
    feedback = _feedback(_processor([]))
    prompt = await _run(verb, feedback)
    assert VETO_REASON in prompt
    assert "**CONSCIENCE OVERRIDE GUIDANCE:**" in prompt
    # The same text ASPDMA receives, verbatim -- not a rewording.
    assert feedback["retry_guidance"] in prompt


@pytest.mark.asyncio
@pytest.mark.parametrize("verb", VERBS, ids=lambda v: v.value)
async def test_first_pass_prompt_carries_no_veto(verb: HandlerActionType) -> None:
    prompt = await _run(verb, None)
    assert VETO_REASON not in prompt
    assert "CONSCIENCE OVERRIDE GUIDANCE" not in prompt


_EP = EpistemicData(entropy_level=0.1, coherence_level=0.9, uncertainty_acknowledged=True, reasoning_transparency=1.0)


@pytest.mark.asyncio
async def test_conscience_retry_hands_the_stored_feedback_to_the_second_pass() -> None:
    """``_handle_conscience_retry`` passes what it stored on the item, not None."""
    proc = ThoughtProcessor.__new__(ThoughtProcessor)
    proc.dma_orchestrator = SimpleNamespace(
        run_action_selection=AsyncMock(return_value=_selected(HandlerActionType.TOOL))
    )
    item = _item()
    stored = {"failed_action": "x", "failure_reason": VETO_REASON, "retry_guidance": "g"}

    def prepare(thought_item: Any, *_: Any, **__: Any) -> Any:
        thought_item.conscience_feedback = stored
        return SimpleNamespace()

    proc._prepare_conscience_retry_context = Mock(side_effect=prepare)  # type: ignore[method-assign]
    proc._run_verb_second_pass = AsyncMock(return_value=_selected(HandlerActionType.TOOL))  # type: ignore[method-assign]
    proc._process_conscience_retry_result = AsyncMock(return_value=(None, None))  # type: ignore[method-assign]
    overridden = ConscienceApplicationResult(
        original_action=_selected(HandlerActionType.TOOL),
        final_action=_selected(HandlerActionType.TOOL),
        overridden=True,
        override_reason=VETO_REASON,
        epistemic_data=_EP,
    )

    await proc._handle_conscience_retry(item, Mock(thought_id="th-veto"), {}, {}, overridden, "default")

    assert proc._run_verb_second_pass.await_args.kwargs.get("conscience_feedback") is stored


def test_retry_guidance_names_the_vetoed_tool() -> None:
    proc = ThoughtProcessor.__new__(ThoughtProcessor)
    action = ActionSelectionDMAResult(
        selected_action=HandlerActionType.TOOL,
        action_parameters=ToolParams(name="create_ticket", parameters={"title": "s3cr3t-value", "priority": "high"}),
        rationale="file it",
    )
    described = proc._describe_action(action)
    assert "create_ticket" in described
    assert "title" in described and "priority" in described
    # Argument names only: a value may be a secret.
    assert "s3cr3t-value" not in described
    guidance = proc._build_retry_guidance(described, VETO_REASON, None, None, language="en")
    assert "create_ticket" in guidance
