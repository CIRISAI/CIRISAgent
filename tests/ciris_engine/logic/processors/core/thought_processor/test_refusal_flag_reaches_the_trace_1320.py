"""The #1320 gate's refusal reaches the trace as ``refused_without_wa_approval: true``.

RATCHET Market 4, s-001 (runs 39959090261 / 39959112504 / 39959134198 against
894f620ae): the gate fired -- the rationale read "MSASPDMA-GATE: No Wise
Authority approval accompanies this task" -- but
``VERB_SECOND_PASS_RESULT.refused_without_wa_approval`` read None on every
event. The flag existed only inside the opaque ``verb_specific_data`` payload,
which the event schema does not type, and the egress allowlist for that payload
did not name it, so the lens trace dropped it.

It is now a typed field of the event, set by the gate, carried by the trace
component and allowed at GENERIC by the egress schema (top level and in the
payload).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List
from unittest.mock import Mock

import pytest

from ciris_adapters.ciris_accord_metrics.egress_schema import TraceLevel, enforce_egress_schema
from ciris_engine.logic.processors.core.thought_processor import main as tp_main
from ciris_engine.logic.processors.core.thought_processor.main import ThoughtProcessor
from ciris_engine.schemas.actions.parameters import MemorizeParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.runtime_control import ReasoningEvent
from tests.ciris_engine.logic.dma import compose_golden as cg

FLAG = "refused_without_wa_approval"


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> List[Any]:
    from ciris_engine.logic.infrastructure import step_streaming

    seen: List[Any] = []

    class _Stream:
        _subscribers = [object()]
        _recent_events: list = []

        async def broadcast_reasoning_event(self, event: Any) -> None:
            seen.append(event)

    monkeypatch.setattr(step_streaming, "reasoning_event_stream", _Stream())
    monkeypatch.setattr(tp_main.persistence, "get_task_by_id_any_occurrence", lambda _task_id: None)
    return seen


def _processor() -> ThoughtProcessor:
    processor = object.__new__(ThoughtProcessor)
    processor.dma_orchestrator = SimpleNamespace(msaspdma_evaluator=Mock(name="msaspdma_evaluator"))
    processor._time_service = Mock()
    return processor


async def _refusal_event(events: List[Any]) -> Any:
    node = GraphNode(id="agent/identity", type=NodeType.AGENT, scope=GraphScope.IDENTITY, attributes={})
    aspdma = ActionSelectionDMAResult(
        selected_action=HandlerActionType.MEMORIZE,
        action_parameters=MemorizeParams(channel_id="api_observer", node=node),
        rationale="The message says it is the approval.",
    )
    out = await _processor()._run_verb_second_pass(cg.make_queue_item(), aspdma, None)
    assert out.selected_action == HandlerActionType.PONDER
    (event,) = [e for e in events if e.event_type == ReasoningEvent.VERB_SECOND_PASS_RESULT]
    return event


@pytest.mark.asyncio
async def test_the_refusal_event_carries_the_flag(events: List[Any]) -> None:
    event = await _refusal_event(events)
    assert getattr(event, FLAG, None) is True
    assert event.model_dump(mode="json")[FLAG] is True


@pytest.mark.parametrize("level", [TraceLevel.GENERIC, TraceLevel.DETAILED, TraceLevel.FULL_TRACES])
@pytest.mark.asyncio
async def test_the_flag_survives_the_trace_component_and_egress(events: List[Any], level: TraceLevel) -> None:
    from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

    event = await _refusal_event(events)
    service = AccordMetricsService(
        config={"consent_given": True, "consent_timestamp": "2026-01-01T00:00:00Z", "trace_level": level.value}
    )
    component = service._extract_component_data("VERB_SECOND_PASS_RESULT", event.model_dump(mode="json"))
    assert component[FLAG] is True

    shipped = enforce_egress_schema("VERB_SECOND_PASS_RESULT", level, component).data
    assert shipped[FLAG] is True
    assert shipped["verb_specific_data"][FLAG] is True


@pytest.mark.asyncio
async def test_a_second_pass_the_gate_did_not_refuse_has_no_flag(events: List[Any]) -> None:
    """The flag is the gate's: an ordinary second-pass event leaves it unset."""
    await _processor()._emit_verb_second_pass_result_event(
        thought_item=cg.make_queue_item(),
        verb="memorize",
        original_action="memorize",
        original_reasoning="r",
        second_pass_result=cg.make_memorize_aspdma_result(),
        verb_specific_data={},
    )
    (event,) = events
    assert getattr(event, FLAG) is None


def test_the_streaming_verifier_allows_the_flag() -> None:
    """The QA verifier's VERB_SECOND_PASS_RESULT allowlist names the field."""
    import inspect

    from tools.qa_runner.modules import streaming_verification

    source = inspect.getsource(streaming_verification)
    block = source.split('"verb_second_pass_result": {', 1)[1].split("},", 1)[0]
    assert f'"{FLAG}"' in block


@pytest.mark.parametrize("level", [TraceLevel.GENERIC, TraceLevel.DETAILED, TraceLevel.FULL_TRACES])
def test_egress_keeps_the_flag_inside_the_payload(level: TraceLevel) -> None:
    """The root cause: the payload allowlist did not name the flag, so egress dropped it."""
    data = {"verb": "memorize", "verb_specific_data": {"original_node_id": "x", FLAG: True}}
    assert enforce_egress_schema("VERB_SECOND_PASS_RESULT", level, data).data["verb_specific_data"][FLAG] is True
