"""The CC 4.2.1.1 act gate in `ActionDispatcher._dispatch_inner` (CIRISAgent#1231).

`test_latched_halt_stops_an_effectful_act_and_emits_its_action_result` is the
unit witness for evidence row CLM-halt-one-row: a latched halt stops the act AND
the act's terminal ACTION_RESULT is emitted, carrying the halt's invocation_id.
"""

from datetime import datetime, timezone
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.infrastructure.handlers import action_dispatcher as dispatcher_module
from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher
from ciris_engine.logic.utils import halt_latch
from ciris_engine.schemas.actions.parameters import DeferParams, SpeakParams, ToolParams
from ciris_engine.schemas.audit.hash_chain import AuditEntryResult
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.accord_halt import AccordHaltReading, AccordHaltState
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.runtime_control import ReasoningEvent

pytestmark = pytest.mark.real_halt_latch

INVOCATION = "inv-4211-witness"


def _state(halted: bool, reading: AccordHaltReading, invocation_id: Any = None) -> AccordHaltState:
    return AccordHaltState(
        halted=halted, reading=reading, invocation_id=invocation_id, read_at=datetime.now(timezone.utc)
    )


HALTED = _state(True, AccordHaltReading.IN_EFFECT, INVOCATION)
UNREACHABLE = _state(True, AccordHaltReading.NODE_UNREACHABLE)
NOT_HALTED = _state(False, AccordHaltReading.NOT_HALTED)


class Latch:
    """The node's answer, settable per test; counts reads."""

    def __init__(self, state: AccordHaltState) -> None:
        self.state = state
        self.reads = 0

    async def read(self) -> AccordHaltState:
        self.reads += 1
        return self.state


@pytest.fixture
def latch(monkeypatch):
    lt = Latch(NOT_HALTED)
    monkeypatch.setattr(halt_latch, "_read_from_node", lt.read)
    # Per act: no cache between the acts of one test.
    monkeypatch.setattr(halt_latch, "HALT_READ_CACHE_TTL_SECONDS", 0.0)
    return lt


@pytest.fixture
def audit():
    mock = MagicMock()

    async def log_action(action_type, context, outcome):
        return AuditEntryResult(
            entry_id=f"audit-{action_type.value}",
            sequence_number=7,
            entry_hash="hash",
            previous_hash=None,
            signature="sig",
            signing_key_id="key",
        )

    mock.log_action = AsyncMock(side_effect=log_action)
    return mock


@pytest.fixture
def handler():
    h = MagicMock()
    h.handle = AsyncMock(return_value=None)
    h.dependencies = None
    return h


@pytest.fixture
def events(monkeypatch) -> List[Any]:
    """Every reasoning event broadcast through the normal trace pipeline."""
    from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

    seen: List[Any] = []

    async def capture(event):
        seen.append(event)

    monkeypatch.setattr(reasoning_event_stream, "broadcast_reasoning_event", capture)
    return seen


@pytest.fixture
def thought_status(monkeypatch):
    """Records every status the dispatcher writes for the thought."""
    writes: List[Any] = []

    def update(thought_id, status, occurrence_id="default", final_action=None):
        writes.append((thought_id, status, final_action))
        return True

    monkeypatch.setattr(dispatcher_module.persistence, "update_thought_status", update)
    monkeypatch.setattr(dispatcher_module.persistence, "get_thought_by_id", lambda *a, **k: None)
    return writes


def _thought() -> Thought:
    now = datetime(2026, 10, 14, tzinfo=timezone.utc).isoformat()
    return Thought(
        thought_id="th-1",
        source_task_id="task-1",
        content="hello",
        status=ThoughtStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )


def _ctx():
    ctx = MagicMock()
    ctx.task_id = "task-1"
    ctx.model_dump.return_value = {"task_id": "task-1", "channel_id": "api_u1"}
    return ctx


def _result(action: HandlerActionType) -> ActionSelectionDMAResult:
    params = {
        HandlerActionType.SPEAK: SpeakParams(content="hi"),
        HandlerActionType.TOOL: ToolParams(name="lights_on", parameters={}),
        HandlerActionType.DEFER: DeferParams(reason="needs a human"),
    }[action]
    return ActionSelectionDMAResult(selected_action=action, action_parameters=params, rationale="r")


def _dispatcher(handler, audit, action=HandlerActionType.SPEAK) -> ActionDispatcher:
    return ActionDispatcher(handlers={action: handler}, audit_service=audit)


def _action_results(events: List[Any]) -> List[Any]:
    return [e for e in events if getattr(e, "event_type", None) == ReasoningEvent.ACTION_RESULT]


@pytest.mark.asyncio
async def test_latched_halt_stops_an_effectful_act_and_emits_its_action_result(
    latch, handler, audit, events, thought_status
):
    """WITNESS (CLM-halt-one-row): refused, recorded, traced, not FAILED."""
    latch.state = HALTED
    response = await _dispatcher(handler, audit).dispatch(_result(HandlerActionType.SPEAK), _thought(), _ctx())

    # The act did not run.
    handler.handle.assert_not_awaited()
    assert response.success is False
    assert response.error == f"accord_halt_in_effect:{INVOCATION}"

    # A signed audit row records the refusal.
    audit.log_action.assert_awaited_once()
    kwargs = audit.log_action.await_args.kwargs
    assert kwargs["outcome"] == f"refused:accord_halt_in_effect:{INVOCATION}"
    assert kwargs["context"].parameters["accord_halt_invocation_id"] == INVOCATION
    assert response.audit_data.signature == "sig"

    # The terminal ACTION_RESULT went through the normal trace pipeline. A
    # refusal with no ACTION_RESULT is a silent drop, and fails here.
    results = _action_results(events)
    assert len(results) == 1, "a refused act must emit exactly one terminal ACTION_RESULT"
    ar = results[0]
    assert ar.thought_id == "th-1"
    assert ar.action_executed == "speak"
    assert ar.execution_success is False
    assert ar.error == f"accord_halt_in_effect:{INVOCATION}"
    assert ar.action_parameters["accord_halt_invocation_id"] == INVOCATION
    assert ar.audit_entry_id == "audit-speak"

    # The thought is not FAILED: it goes back to PENDING with no saved action.
    assert thought_status == [("th-1", ThoughtStatus.PENDING, None)]


@pytest.mark.asyncio
async def test_the_same_dispatch_runs_when_no_halt_stands(latch, handler, audit, events, thought_status):
    """Positive control: the gate is what stopped the act above, not the fixture."""
    latch.state = NOT_HALTED
    response = await _dispatcher(handler, audit).dispatch(_result(HandlerActionType.SPEAK), _thought(), _ctx())
    handler.handle.assert_awaited_once()
    assert response.success is True
    assert response.error is None
    assert _action_results(events)[0].error is None
    assert all(status != ThoughtStatus.PENDING for _, status, _ in thought_status)


@pytest.mark.asyncio
async def test_a_tool_call_is_refused(latch, handler, audit, events, thought_status):
    latch.state = HALTED
    response = await _dispatcher(handler, audit, HandlerActionType.TOOL).dispatch(
        _result(HandlerActionType.TOOL), _thought(), _ctx()
    )
    handler.handle.assert_not_awaited()
    assert response.success is False
    assert len(_action_results(events)) == 1


@pytest.mark.asyncio
async def test_the_deferral_write_runs_under_the_halt(latch, handler, audit, events, thought_status):
    """DEFER is the exempt deferral write; it runs, inside the exempt scope."""
    latch.state = HALTED
    seen_scope: List[Any] = []

    async def handle(*args):
        seen_scope.append(halt_latch.running_exempt_under_halt())
        return None

    handler.handle = AsyncMock(side_effect=handle)
    response = await _dispatcher(handler, audit, HandlerActionType.DEFER).dispatch(
        _result(HandlerActionType.DEFER), _thought(), _ctx()
    )
    assert response.success is True
    assert seen_scope and seen_scope[0] is not None and seen_scope[0].invocation_id == INVOCATION
    assert halt_latch.running_exempt_under_halt() is None  # the scope does not leak


@pytest.mark.asyncio
async def test_fail_closed_reading_refuses_too(latch, handler, audit, events, thought_status):
    latch.state = UNREACHABLE
    response = await _dispatcher(handler, audit).dispatch(_result(HandlerActionType.SPEAK), _thought(), _ctx())
    handler.handle.assert_not_awaited()
    assert response.error == "accord_halt_in_effect:node_unreachable"
    assert len(_action_results(events)) == 1


@pytest.mark.asyncio
async def test_the_gate_reads_the_latch_per_act_not_per_round(latch, handler, audit, events, thought_status):
    """Two acts in one round: the halt that lands between them stops the second."""
    dispatcher = _dispatcher(handler, audit)
    latch.state = NOT_HALTED
    first = await dispatcher.dispatch(_result(HandlerActionType.SPEAK), _thought(), _ctx())
    latch.state = HALTED
    second = await dispatcher.dispatch(_result(HandlerActionType.SPEAK), _thought(), _ctx())

    assert first.success is True and second.success is False
    assert handler.handle.await_count == 1
    assert latch.reads == 2


@pytest.mark.asyncio
async def test_the_gate_sits_after_the_registry_wait(latch, handler, audit, events, thought_status):
    """The latch is read as late as possible: a halt that lands during the wait still stops the act."""

    async def wait_registry_ready(timeout):
        latch.state = HALTED
        return True

    handler.dependencies = MagicMock(wait_registry_ready=AsyncMock(side_effect=wait_registry_ready))
    response = await _dispatcher(handler, audit).dispatch(_result(HandlerActionType.SPEAK), _thought(), _ctx())
    handler.handle.assert_not_awaited()
    assert response.success is False


@pytest.mark.asyncio
async def test_defer_handler_withholds_its_channel_notice_under_the_halt(monkeypatch):
    """Only the deferral WRITE is exempt; the channel notice is the agent speaking."""
    from ciris_engine.logic.handlers.control import defer_handler as defer_module
    from ciris_engine.logic.handlers.control.defer_handler import DeferHandler

    task = MagicMock(channel_id="api_u1", agent_occurrence_id="default", preferred_language="en")
    monkeypatch.setattr(defer_module.persistence, "get_task_by_id_any_occurrence", lambda _id: task)
    monkeypatch.setattr(defer_module.persistence, "update_task_status", lambda *a, **k: True)
    handler = DeferHandler.__new__(DeferHandler)
    handler.logger = MagicMock()
    handler._send_notification = AsyncMock()  # type: ignore[method-assign]

    with patch("asyncio.create_task") as create_task:
        with halt_latch.exempt_act_scope(HALTED):
            handler._mark_task_deferred(_thought())
        create_task.assert_not_called()

        handler._mark_task_deferred(_thought())
        create_task.assert_called_once()
        create_task.call_args.args[0].close()  # the un-awaited coroutine
