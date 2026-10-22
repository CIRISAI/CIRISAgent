"""The reasoning trace records the prompts the model was actually sent, for THIS thought.

Two failures, one cause. Prompts lived on the evaluator (``last_user_prompt`` /
``last_system_prompt``) and were read back after the call. DSDMA stored them
before prepending the identity block, so the trace never showed CORE IDENTITY;
and one evaluator serves every concurrent thought, with an ``await`` on the
model between store and read, so a follow-up thought's DMA_RESULTS carried the
CSDMA, DSDMA and PDMA prompts of a different task (RATCHET run 39853438022).

The record is now derived from the exact messages of one call and travels on
the object that call returned (schemas/dma/sent_prompts.py).
"""

from __future__ import annotations

import ast
import asyncio
import pathlib
from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.schemas.dma.sent_prompts import attach_sent_prompts, sent_prompts_from_messages, sent_prompts_of
from tests.ciris_engine.logic.dma import compose_golden as cg

REPO = pathlib.Path(__file__).resolve().parents[4]


def _sink(result_for, sent: List[Any], delay_for=None):
    """A fake LLM bus at the real boundary: BaseDMA.call_llm_structured runs."""

    async def call_llm_structured(*, messages, response_model, **_kw):
        sent.append(messages)
        if delay_for:
            await asyncio.sleep(delay_for(messages))
        return result_for(response_model, messages), None

    return SimpleNamespace(llm=SimpleNamespace(call_llm_structured=call_llm_structured))


def _queue_item(thought_id: str, text: str):
    item = cg.make_queue_item()
    item.thought_id = thought_id
    item.content = type(item.content)(text=text, metadata={})
    return item


@pytest.mark.asyncio
async def test_concurrent_thoughts_never_see_each_others_prompts():
    """Two thoughts on ONE evaluator, interleaved: each result carries only its own prompts."""
    from ciris_engine.logic.dma.csdma import CSDMAEvaluator

    sent: List[Any] = []
    dma = CSDMAEvaluator(service_registry=Mock())
    # The slow call finishes LAST, so it is the one a shared-state read would clobber.
    dma.sink = _sink(
        lambda model, _m: model(plausibility_score=0.9, flags=[], reasoning="r"),
        sent,
        delay_for=lambda m: 0.05 if "ALPHA-THOUGHT" in str(m) else 0.0,
    )
    alpha, beta = await asyncio.gather(
        dma.evaluate_thought(_queue_item("t-alpha", "ALPHA-THOUGHT about weather")),
        dma.evaluate_thought(_queue_item("t-beta", "BETA-THOUGHT about tides")),
    )
    assert "ALPHA-THOUGHT" in sent_prompts_of(alpha).user and "BETA-THOUGHT" not in sent_prompts_of(alpha).user
    assert "BETA-THOUGHT" in sent_prompts_of(beta).user and "ALPHA-THOUGHT" not in sent_prompts_of(beta).user


@pytest.mark.asyncio
async def test_dsdma_records_the_system_prompt_with_its_identity_block():
    from ciris_engine.logic.dma.dsdma_base import BaseDSDMA

    sent: List[Any] = []
    dma = BaseDSDMA(
        domain_name="golden_domain",
        service_registry=Mock(),
        domain_specific_knowledge={"rules_summary": "r", "escalation_paths": ["wise_authority"]},
    )
    dma.fetch_original_task = AsyncMock(return_value=cg.make_task())  # type: ignore[method-assign]
    dma.sink = _sink(lambda _model, _m: cg.make_dsdma_result(), sent)
    result = await dma.evaluate(cg.make_dsdma_queue_item())

    record = sent_prompts_of(result)
    assert record is not None and "CORE IDENTITY" in (record.system or "")
    assert record == sent_prompts_from_messages(sent[-1]), "the recorded prompt is the one that was sent"


@pytest.mark.asyncio
async def test_aspdma_result_carries_the_prompts_it_was_sent():
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator

    sent: List[Any] = []
    registry = Mock()
    registry.get_services_by_type.return_value = []
    dma = ActionSelectionPDMAEvaluator(service_registry=registry)
    cg.pin_aspdma_context_builder(dma)
    dma.sink = _sink(
        lambda _model, _m: cg.ASPDMALLMResult(selected_action=cg.HandlerActionType.SPEAK, reasoning="r", speak_content="c"),
        sent,
    )
    result = await dma.evaluate(cg.make_enhanced_inputs())

    expected = sent_prompts_from_messages(sent[-1])
    assert result.system_prompt == expected.system and "CORE IDENTITY" in (result.system_prompt or "")
    assert result.user_prompt == expected.user


@pytest.mark.asyncio
async def test_a_verb_second_pass_keeps_the_action_selection_prompts_and_its_own():
    """RATCHET run 39851060130: the approved MEMORIZE's ASPDMA_RESULT had both prompts empty."""
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
    from ciris_engine.schemas.dma.sent_prompts import SentPrompts

    original = cg.make_memorize_aspdma_result().model_copy(
        update={"user_prompt": "aspdma user", "system_prompt": "=== CORE IDENTITY === ..."}
    )
    own = SentPrompts(system="msaspdma system", user="msaspdma user")

    async def second_pass(_self: Any, _item: Any, _result: Any, _ctx: Any) -> ActionSelectionDMAResult:
        fresh = cg.make_memorize_aspdma_result().model_copy(update={"user_prompt": "msaspdma user"})
        return attach_sent_prompts(fresh, own)

    processor = object.__new__(ThoughtProcessor)
    processor._VERB_SECOND_PASS = {original.selected_action: second_pass}  # type: ignore[misc]
    out = await processor._run_verb_second_pass(cg.make_queue_item(), original, None)

    assert (out.user_prompt, out.system_prompt) == ("aspdma user", "=== CORE IDENTITY === ...")
    assert sent_prompts_of(out) == own, "the second pass's own prompts survive the copy"


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


@pytest.mark.asyncio
async def test_the_second_pass_event_records_its_own_calls_prompts(monkeypatch):
    from ciris_engine.logic.infrastructure import step_streaming
    from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
    from ciris_engine.schemas.dma.sent_prompts import SentPrompts

    seen: list = []

    class _Stream:
        _subscribers = [object()]
        _recent_events: list = []

        async def broadcast_reasoning_event(self, event: Any) -> None:
            seen.append(event)

    monkeypatch.setattr(step_streaming, "reasoning_event_stream", _Stream())
    result = attach_sent_prompts(
        cg.make_memorize_aspdma_result(), SentPrompts(system="=== WISE AUTHORITY APPROVAL ===", user="second-pass user")
    )
    processor = object.__new__(ThoughtProcessor)
    await processor._emit_verb_second_pass_result_event(
        thought_item=cg.make_queue_item(),
        verb="memorize",
        original_action="memorize",
        original_reasoning="r",
        second_pass_result=result,
        verb_specific_data={},
    )
    (event,) = seen
    assert event.second_pass_prompt == "second-pass user"
    assert event.second_pass_system_prompt == "=== WISE AUTHORITY APPROVAL ==="


def test_the_record_never_enters_a_response_schema():
    from ciris_engine.schemas.dma.results import EthicalDMAResult

    assert "sent_prompts" not in str(EthicalDMAResult.model_json_schema())


def test_no_evaluator_stores_prompts_on_itself():
    """The by-construction rule: shared evaluator state is how prompts crossed tasks."""
    offenders = []
    for path in sorted((REPO / "ciris_engine").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("last_user_prompt", "last_system_prompt"):
                offenders.append(f"{path.relative_to(REPO)}:{node.lineno}")
    assert not offenders, f"prompts read from or stored on an evaluator: {offenders}"


def test_egress_ships_the_system_prompts_only_at_full_traces():
    from ciris_adapters.ciris_accord_metrics.egress_schema import TraceLevel, enforce_egress_schema

    for event, field in (("ASPDMA_RESULT", "aspdma_system_prompt"), ("VERB_SECOND_PASS_RESULT", "second_pass_system_prompt")):
        data = {field: "=== CORE IDENTITY === ..."}
        assert enforce_egress_schema(event, TraceLevel.FULL_TRACES, data).data[field]
        assert field not in enforce_egress_schema(event, TraceLevel.GENERIC, data).data


def test_the_conscience_event_keeps_the_prompts_it_is_given():
    """step_decorators passed them all along; the event model dropped them as unknown."""
    from ciris_engine.schemas.conscience.core import EpistemicData
    from ciris_engine.schemas.services.runtime_control import ReasoningEvent
    from ciris_engine.schemas.streaming.reasoning_stream import create_reasoning_event

    event = create_reasoning_event(
        event_type=ReasoningEvent.CONSCIENCE_RESULT,
        thought_id="t1",
        task_id="task1",
        timestamp="2026-10-22T00:00:00Z",
        conscience_passed=True,
        final_action="memorize",
        is_recursive=False,
        epistemic_data=EpistemicData(uncertainty_acknowledged=False, reasoning_transparency=1.0),
        action_was_overridden=False,
        optimization_veto_prompt="=== WISE AUTHORITY APPROVAL === ...",
        entropy_prompt="e",
    )
    assert event.optimization_veto_prompt == "=== WISE AUTHORITY APPROVAL === ..."
    assert event.entropy_prompt == "e"
