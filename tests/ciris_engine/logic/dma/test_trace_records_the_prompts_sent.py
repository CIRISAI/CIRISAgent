"""The reasoning trace records the prompts the model was actually sent.

RATCHET runs 39844408349 and 39845804302: the LLM_CALL prompts held the CORE
IDENTITY and the approved amendments, but the pipeline events could not show
it. DSDMA stored last_system_prompt BEFORE prepending the identity block, so
DMA_RESULTS.dsdma_system_prompt never held it; and ASPDMA_RESULT carried only
the user prompt, while the system message (identity, amendments, WA approval)
was never streamed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock

import pytest

from tests.ciris_engine.logic.dma import compose_golden as cg


@pytest.mark.asyncio
async def test_dsdma_records_the_system_prompt_with_its_identity_block():
    from ciris_engine.logic.dma.dsdma_base import BaseDSDMA

    dma = BaseDSDMA(
        domain_name="golden_domain",
        service_registry=Mock(),
        domain_specific_knowledge={"rules_summary": "r", "escalation_paths": ["wise_authority"]},
    )
    dma.fetch_original_task = AsyncMock(return_value=cg.make_task())  # type: ignore[method-assign]
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = cg._recording_llm(captured, cg.make_dsdma_result())  # type: ignore[method-assign]
    await dma.evaluate(cg.make_dsdma_queue_item())

    assert "CORE IDENTITY" in (dma.last_system_prompt or "")
    sent = [m["content"] for m in captured["messages"] if m.get("role") == "system"]
    assert any(dma.last_system_prompt == s for s in sent), "the recorded prompt is the one that was sent"


@pytest.mark.asyncio
async def test_aspdma_result_carries_the_system_prompt_it_was_sent():
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    cg.pin_aspdma_context_builder(dma)
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = cg._recording_llm(  # type: ignore[method-assign]
        captured, cg.ASPDMALLMResult(selected_action=cg.HandlerActionType.SPEAK, reasoning="r", speak_content="c")
    )
    result = await dma.evaluate(cg.make_enhanced_inputs())

    assert result.system_prompt and "CORE IDENTITY" in result.system_prompt
    sent = [m["content"] for m in captured["messages"] if m.get("role") == "system"]
    assert result.system_prompt in sent


def test_the_aspdma_event_streams_the_system_prompt():
    from ciris_engine.logic.processors.core.step_decorators import _create_aspdma_result_event
    from ciris_engine.schemas.streaming.reasoning_stream import create_reasoning_event

    step = SimpleNamespace(
        thought_id="t1",
        task_id="task1",
        selected_action="speak",
        action_rationale="r",
        aspdma_prompt="user prompt",
        aspdma_system_prompt="=== CORE IDENTITY === ...",
    )
    event = _create_aspdma_result_event(step, "2026-10-22T00:00:00Z", False, create_reasoning_event)
    assert event.aspdma_system_prompt == "=== CORE IDENTITY === ..."
    assert event.aspdma_prompt == "user prompt"


def test_egress_ships_the_system_prompt_only_at_full_traces():
    from ciris_adapters.ciris_accord_metrics.egress_schema import TraceLevel, enforce_egress_schema

    data = {"selected_action": "speak", "aspdma_system_prompt": "=== CORE IDENTITY === ..."}
    full = enforce_egress_schema("ASPDMA_RESULT", TraceLevel.FULL_TRACES, data).data
    generic = enforce_egress_schema("ASPDMA_RESULT", TraceLevel.GENERIC, data).data
    assert full["aspdma_system_prompt"] == "=== CORE IDENTITY === ..."
    assert "aspdma_system_prompt" not in generic


@pytest.mark.asyncio
async def test_a_verb_second_pass_keeps_the_action_selection_prompts():
    """RATCHET run 39851060130: the approved MEMORIZE's ASPDMA_RESULT had both prompts empty."""
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult

    original = cg.make_memorize_aspdma_result().model_copy(
        update={"user_prompt": "the user prompt", "system_prompt": "=== CORE IDENTITY === ..."}
    )

    async def second_pass(_self: Any, _item: Any, result: Any, _ctx: Any) -> ActionSelectionDMAResult:
        return cg.make_memorize_aspdma_result()  # a fresh result, as MSASPDMA returns

    processor = object.__new__(ThoughtProcessor)
    processor._VERB_SECOND_PASS = {original.selected_action: second_pass}  # type: ignore[misc]
    out = await processor._run_verb_second_pass(cg.make_queue_item(), original, None)

    assert out.user_prompt == "the user prompt"
    assert out.system_prompt == "=== CORE IDENTITY === ..."


@pytest.mark.asyncio
async def test_the_second_pass_event_records_the_prompts_its_evaluator_was_sent(monkeypatch):
    """The MSASPDMA guide carries the WA approval; its trace event must show it."""
    from ciris_engine.logic.infrastructure import step_streaming
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor

    seen: list = []

    class _Stream:
        _subscribers = [object()]
        _recent_events: list = []

        async def broadcast_reasoning_event(self, event: Any) -> None:
            seen.append(event)

    monkeypatch.setattr(step_streaming, "reasoning_event_stream", _Stream())
    evaluator = SimpleNamespace(last_user_prompt="second-pass user", last_system_prompt="=== WISE AUTHORITY APPROVAL ===")
    processor = object.__new__(ThoughtProcessor)
    await processor._emit_verb_second_pass_result_event(
        thought_item=cg.make_queue_item(),
        verb="memorize",
        original_action="memorize",
        original_reasoning="r",
        second_pass_result=cg.make_memorize_aspdma_result(),
        verb_specific_data={},
        evaluator=evaluator,
    )
    (event,) = seen
    assert event.second_pass_prompt == "second-pass user"
    assert event.second_pass_system_prompt == "=== WISE AUTHORITY APPROVAL ==="


def test_egress_ships_the_second_pass_system_prompt_only_at_full_traces():
    from ciris_adapters.ciris_accord_metrics.egress_schema import TraceLevel, enforce_egress_schema

    data = {"verb": "memorize", "second_pass_system_prompt": "=== WISE AUTHORITY APPROVAL ==="}
    assert enforce_egress_schema("VERB_SECOND_PASS_RESULT", TraceLevel.FULL_TRACES, data).data["second_pass_system_prompt"]
    assert "second_pass_system_prompt" not in enforce_egress_schema("VERB_SECOND_PASS_RESULT", TraceLevel.GENERIC, data).data
