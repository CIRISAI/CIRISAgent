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
