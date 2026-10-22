"""A verified Wise Authority approval is in front of every step that decides on it.

RATCHET's Market 4 pilot (run 39812690788): 9 approved identity changes, 0
applied. Action selection chose MEMORIZE in 80 of 90 selections; the optimization
veto then sent 32 back for "Wise Authority review" the change had already had,
and the memorize second pass rewrote 8 into "I am a made thing ... I do not have
a name". The approval reached dispatch (#1304) but no prompt.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any, Dict, List

import pytest

from ciris_engine.logic.formatters.wa_approval import format_wa_approval_block, wa_authorization_of
from ciris_engine.schemas.runtime.models import WAAuthorization
from tests.ciris_engine.logic.dma import compose_golden as cg

GRANT = WAAuthorization(
    wa_id="wa-2026-test",
    deferral_id="defer_c5aaf93c",
    granted_at="2026-10-22T14:00:00+00:00",
    guidance="End every reply with 'Take care, from Ally.'",
)


def _text(messages: List[Dict[str, Any]]) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


def test_no_approval_renders_nothing():
    assert format_wa_approval_block(None) == ""


def test_the_block_states_the_approval_the_rule_and_the_identity():
    block = format_wa_approval_block(GRANT, language="en")
    for fact in ("wa-2026-test", "defer_c5aaf93c", "2026-10-22T14:00:00+00:00", "Take care, from Ally."):
        assert fact in block
    assert "choose the REJECT action" in block
    assert "Do not choose the DEFER action for this change again" in block
    assert "MEMORIZE action in the identity scope" in block
    assert "does not take away your name" in block
    assert "{" not in block, "every placeholder is filled"


@pytest.mark.parametrize(
    "context",
    [
        GRANT,
        SimpleNamespace(wa_authorization=GRANT),
        SimpleNamespace(context=SimpleNamespace(wa_authorization=GRANT)),
        SimpleNamespace(initial_task_context=SimpleNamespace(wa_authorization=GRANT)),
        {"initial_task_context": {"wa_authorization": GRANT.model_dump(mode="json")}},
        SimpleNamespace(task=SimpleNamespace(context=SimpleNamespace(wa_authorization=GRANT))),
    ],
)
def test_the_approval_is_found_on_every_context_shape(context):
    assert wa_authorization_of(context) == GRANT


@pytest.mark.parametrize("context", [None, {}, SimpleNamespace(), {"initial_task_context": {"wa_authorization": "junk"}}])
def test_no_or_malformed_approval_is_none(context):
    assert wa_authorization_of(context) is None


def test_an_old_grant_without_guidance_still_decodes():
    old = {"wa_id": "w", "deferral_id": "d", "granted_at": "t", "verification": "verified"}
    assert WAAuthorization.model_validate(old).guidance == ""


@pytest.mark.asyncio
async def test_action_selection_sees_the_approval():
    inputs = cg.make_enhanced_inputs()
    inputs.processing_context["initial_task_context"] = {"wa_authorization": GRANT.model_dump(mode="json")}
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
    from unittest.mock import Mock

    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    cg.pin_aspdma_context_builder(dma)
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = cg._recording_llm(  # type: ignore[method-assign]
        captured,
        cg.ASPDMALLMResult(selected_action=cg.HandlerActionType.SPEAK, reasoning="r", speak_content="c"),
    )
    await dma.evaluate(inputs)
    text = _text(captured["messages"])
    assert "=== WISE AUTHORITY APPROVAL ===" in text and "defer_c5aaf93c" in text


@pytest.mark.asyncio
async def test_action_selection_without_approval_is_unchanged():
    text = _text(await cg.capture_aspdma())
    assert "WISE AUTHORITY APPROVAL" not in text


@pytest.mark.asyncio
async def test_the_memorize_second_pass_sees_the_approval():
    from unittest.mock import Mock

    from ciris_engine.logic.dma.msaspdma import MSASPDMAEvaluator, MSASPDMALLMResult

    dma = MSASPDMAEvaluator(service_registry=Mock())
    captured: Dict[str, Any] = {}
    dma.call_llm_structured = cg._recording_llm(  # type: ignore[method-assign]
        captured, MSASPDMALLMResult(final_action="PONDER", questions=["q"], reasoning="r")
    )
    context = SimpleNamespace(initial_task_context=SimpleNamespace(wa_authorization=GRANT), preferred_language="en")
    await dma.evaluate(cg.make_queue_item(), aspdma_result=cg.make_memorize_aspdma_result(), context=context)
    assert "defer_c5aaf93c" in _text(captured["messages"])


@pytest.mark.asyncio
async def test_the_memorize_second_pass_without_approval_is_unchanged():
    assert "WISE AUTHORITY APPROVAL" not in _text(await cg.capture_msaspdma())


@pytest.mark.asyncio
async def test_the_optimization_veto_sees_the_approval():
    from unittest.mock import AsyncMock, Mock

    from ciris_engine.logic.conscience.core import OptimizationVetoConscience
    from ciris_engine.schemas.conscience.context import ConscienceCheckContext
    from ciris_engine.schemas.conscience.core import OptimizationVetoResult

    seen: Dict[str, Any] = {}

    async def _llm(_sink: Any, **kwargs: Any) -> Any:
        seen["messages"] = kwargs["messages"]
        return OptimizationVetoResult(
            decision="proceed", justification="j", entropy_reduction_ratio=0.0, affected_values=[]
        ), None

    conscience = object.__new__(OptimizationVetoConscience)
    conscience._time_service = Mock(now=Mock(return_value=__import__("datetime").datetime.now()))
    conscience._create_trace_correlation = Mock(return_value=None)
    conscience._update_trace_correlation = Mock()
    conscience._get_sink = AsyncMock(return_value=SimpleNamespace(llm=object()))
    conscience._call_llm_with_budget = _llm
    conscience._get_image_context_info = Mock(return_value=None)
    conscience._resolve_language = Mock(return_value="en")
    conscience.config = SimpleNamespace(optimization_veto_ratio=10.0)
    action = cg.make_memorize_aspdma_result()
    thought = SimpleNamespace(thought_id="t1", source_task_id="task1")

    checked = await conscience.check(action, ConscienceCheckContext(thought=thought, wa_authorization=GRANT))
    with_grant = json.dumps([getattr(m, "content", m) for m in seen["messages"]], default=str)
    # The recorded prompt is what the model read, approval included.
    assert "defer_c5aaf93c" in (checked.optimization_veto_prompt or "")
    await conscience.check(action, ConscienceCheckContext(thought=thought))
    without = json.dumps([getattr(m, "content", m) for m in seen["messages"]], default=str)

    assert "defer_c5aaf93c" in with_grant
    assert "WISE AUTHORITY APPROVAL" not in without
