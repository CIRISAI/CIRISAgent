"""A handler-refused act reports execution_success false on ACTION_RESULT (#1320).

RATCHET Market 4, s-001 (runs 39959090261 / 39959112504 / 39959134198 against
894f620ae): on the conscience-retry path an identity MEMORIZE reached the
memorize handler, which refused it ("WA authorization required ... denied") and
marked the thought FAILED. The action record said "MEMORIZE: failed ...
Identity: unchanged", but the ACTION_RESULT for the same act said
``execution_success: true``. The dispatcher read the FAILED status for the audit
outcome and then built the response with ``success=True`` regardless.

The event now carries the handler's own verdict, the status the action record
reads, so the two cannot disagree. A completed act is unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from ciris_engine.logic import persistence
from ciris_engine.logic.handlers.memory.memorize_handler import MemorizeHandler
from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher
from ciris_engine.logic.infrastructure.handlers.action_record import identity_written
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.schemas.actions.parameters import MemorizeParams, RejectParams
from ciris_engine.schemas.audit.hash_chain import AuditEntryResult
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus
from ciris_engine.schemas.services.runtime_control import ReasoningEvent

TASK = "task-1320"


class Store:
    """The thoughts table, in memory: what the handler writes is what the dispatcher reads."""

    def __init__(self) -> None:
        self.thoughts: Dict[str, Thought] = {}

    def update_thought_status(
        self, thought_id: str, status: ThoughtStatus, occurrence_id: str = "default", final_action: Any = None
    ) -> bool:
        thought = self.thoughts.get(thought_id)
        if thought is None:
            return False
        self.thoughts[thought_id] = thought.model_copy(update={"status": status})
        return True

    def add_thought(self, thought: Thought, *_a: Any, **_k: Any) -> str:
        self.thoughts[thought.thought_id] = thought
        return thought.thought_id

    def get_thought_by_id(self, thought_id: str, *_a: Any, **_k: Any) -> Optional[Thought]:
        return self.thoughts.get(thought_id)

    def get_thoughts_by_task_id(self, task_id: str, *_a: Any, **_k: Any) -> List[Thought]:
        return [t for t in self.thoughts.values() if t.source_task_id == task_id]


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> Store:
    s = Store()
    for name in ("update_thought_status", "add_thought", "get_thought_by_id", "get_thoughts_by_task_id"):
        monkeypatch.setattr(persistence, name, getattr(s, name))
    return s


@pytest.fixture
def events(monkeypatch: pytest.MonkeyPatch) -> List[Any]:
    from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

    seen: List[Any] = []

    async def capture(event: Any) -> None:
        seen.append(event)

    monkeypatch.setattr(reasoning_event_stream, "broadcast_reasoning_event", capture)
    return seen


@pytest.fixture
def audit() -> MagicMock:
    mock = MagicMock()

    async def log_action(action_type: HandlerActionType, context: Any, outcome: str) -> AuditEntryResult:
        return AuditEntryResult(
            entry_id=f"audit-{action_type.value}",
            sequence_number=1,
            entry_hash="hash",
            previous_hash=None,
            signature="sig",
            signing_key_id="key",
        )

    mock.log_action = AsyncMock(side_effect=log_action)
    return mock


def _thought(store: Store) -> Thought:
    now = datetime(2026, 10, 23, tzinfo=timezone.utc).isoformat()
    thought = Thought(
        thought_id="th_followup_1320",
        source_task_id=TASK,
        content="The Wise Authority approved this; store the new role description.",
        status=ThoughtStatus.PROCESSING,
        created_at=now,
        updated_at=now,
    )
    store.add_thought(thought)
    return thought


def _ctx(thought: Thought) -> DispatchContext:
    from ciris_engine.schemas.runtime.system_context import ChannelContext

    return DispatchContext(
        channel_context=ChannelContext(channel_id="api_observer", channel_type="api", created_at=datetime.now(timezone.utc)),
        author_id="obs-1",
        author_name="observer",
        origin_service="api",
        handler_name="MemorizeHandler",
        action_type=HandlerActionType.MEMORIZE,
        task_id=TASK,
        thought_id=thought.thought_id,
        source_task_id=TASK,
        event_summary="memorize",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        wa_authorized=False,
    )


def _memorize(node: GraphNode) -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.MEMORIZE,
        action_parameters=MemorizeParams(channel_id="api_observer", node=node),
        rationale="Store it.",
    )


def _dispatcher(audit: MagicMock, memory_status: MemoryOpStatus = MemoryOpStatus.SUCCESS) -> ActionDispatcher:
    bus_manager = Mock()
    bus_manager.memory = AsyncMock()
    bus_manager.memory.memorize = AsyncMock(return_value=MemoryOpResult(status=memory_status, reason="stored"))
    time_service = Mock()
    time_service.now = Mock(return_value=datetime.now(timezone.utc))
    handler = MemorizeHandler(ActionHandlerDependencies(bus_manager=bus_manager, time_service=time_service))
    return ActionDispatcher(handlers={HandlerActionType.MEMORIZE: handler}, audit_service=audit)


def _action_result(events: List[Any]) -> Any:
    (ar,) = [e for e in events if getattr(e, "event_type", None) == ReasoningEvent.ACTION_RESULT]
    return ar


IDENTITY_NODE = GraphNode(
    id="agent/identity", type=NodeType.AGENT, scope=GraphScope.IDENTITY, attributes={"content": "role"}
)


@pytest.mark.asyncio
async def test_a_refused_identity_memorize_reports_failure(store: Store, events: List[Any], audit: MagicMock) -> None:
    """The s-001 shape: the handler refuses, the event says so, with the handler's reason."""
    thought = _thought(store)
    response = await _dispatcher(audit).dispatch(_memorize(IDENTITY_NODE), thought, _ctx(thought))

    assert store.thoughts[thought.thought_id].status == ThoughtStatus.FAILED, "the handler refused the write"
    assert response.success is False
    ar = _action_result(events)
    assert ar.action_executed == "memorize"
    assert ar.execution_success is False, "a refused MEMORIZE is not a success"
    assert ar.error and "WA authorization required" in ar.error
    # The reason, not the action record the handler appends after it.
    assert "\n\n" not in ar.error
    # The event and the action record agree: nothing was written to the identity.
    assert identity_written(list(store.thoughts.values())) is False


@pytest.mark.asyncio
async def test_a_completed_memorize_still_reports_success(store: Store, events: List[Any], audit: MagicMock) -> None:
    thought = _thought(store)
    node = GraphNode(id="note/1", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={"content": "a fact"})
    response = await _dispatcher(audit).dispatch(_memorize(node), thought, _ctx(thought))

    assert store.thoughts[thought.thought_id].status == ThoughtStatus.COMPLETED
    assert response.success is True
    ar = _action_result(events)
    assert ar.execution_success is True
    assert ar.error is None


@pytest.mark.asyncio
async def test_a_failed_store_reports_failure(store: Store, events: List[Any], audit: MagicMock) -> None:
    """Not only refusals: any act the handler marks FAILED."""
    thought = _thought(store)
    node = GraphNode(id="note/1", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={"content": "a fact"})
    await _dispatcher(audit, MemoryOpStatus.FAILED).dispatch(_memorize(node), thought, _ctx(thought))

    ar = _action_result(events)
    assert ar.execution_success is False
    assert ar.error and "Failed to memorize node 'note/1'" in ar.error


@pytest.mark.asyncio
async def test_a_reject_carried_out_is_still_a_success(store: Store, events: List[Any], audit: MagicMock) -> None:
    """REJECT records the thought it rejected as FAILED; the rejection itself ran."""
    thought = _thought(store)

    async def reject(_result: Any, t: Thought, _ctx: Any) -> None:
        persistence.update_thought_status(t.thought_id, ThoughtStatus.FAILED)
        return None

    handler = MagicMock()
    handler.handle = AsyncMock(side_effect=reject)
    handler.dependencies = None
    dispatcher = ActionDispatcher(handlers={HandlerActionType.REJECT: handler}, audit_service=audit)
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.REJECT, action_parameters=RejectParams(reason="no"), rationale="r"
    )
    await dispatcher.dispatch(result, thought, _ctx(thought))

    assert _action_result(events).execution_success is True
