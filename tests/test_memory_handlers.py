from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.memory.memorize_handler import MemorizeHandler
from ciris_engine.logic.handlers.memory.recall_handler import RecallHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.schemas.actions.parameters import MemorizeParams, RecallParams

# Import ActionSelectionDMAResult last to avoid circular import issues
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext, SystemSnapshot
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType

# Rebuild DispatchContext to resolve forward references
DispatchContext.model_rebuild()


def create_channel_context(channel_id: str) -> ChannelContext:
    """Helper to create a valid ChannelContext for tests."""
    return ChannelContext(
        channel_id=channel_id,
        channel_name=f"Channel {channel_id}",
        channel_type="text",
        created_at=datetime.now(timezone.utc),
        is_private=False,
        is_active=True,
        participants=[],
        last_activity=None,
        message_count=0,
        allowed_actions=[],
        moderation_level="standard",
    )


def create_dispatch_context(thought_id: str, task_id: str, channel_id: str = "test_channel") -> DispatchContext:
    """Helper to create a valid DispatchContext for tests."""
    return DispatchContext(
        channel_context=create_channel_context(channel_id),
        author_id="test_author",
        author_name="Test Author",
        origin_service="test_service",
        handler_name="test_handler",
        action_type=HandlerActionType.MEMORIZE,
        task_id=task_id,
        thought_id=thought_id,
        source_task_id=task_id,
        event_summary="Test action",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        correlation_id="test_correlation_id",
        wa_id=None,
        wa_authorized=False,
        wa_context=None,
        conscience_failure_context=None,
        epistemic_data=None,
        span_id=None,
        trace_id=None,
    )


def create_test_system_snapshot() -> SystemSnapshot:
    """Helper to create a valid SystemSnapshot for tests."""
    return SystemSnapshot(
        timestamp=datetime.now(timezone.utc),
        runtime_phase="WAKEUP",
        active_services={"memory": True, "llm": True},
        memory_usage_mb=100.0,
        cpu_usage_percent=10.0,
        active_thoughts=1,
        active_tasks=1,
        avg_response_time_ms=50.0,
        error_rate=0.0,
        queue_depth=0,
    )


def create_test_thought(thought_id: str = "test_thought", task_id: str = "test_task") -> Thought:
    """Helper to create a valid Thought for tests."""
    return Thought(
        thought_id=thought_id,
        source_task_id=task_id,
        content="Test thought content",
        status=ThoughtStatus.PROCESSING,
        thought_depth=1,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        context=ThoughtContext(task_id=task_id, round_number=1, depth=1, correlation_id="test_correlation"),
    )


@pytest.mark.asyncio
async def test_memorize_handler_with_graph_node(monkeypatch, persist_engine):
    """Test memorize handler with proper GraphNode schema.

    `persist_engine` fixture wires a fresh persist Engine so
    `persistence.update_thought_status` (called via base_handler) doesn't
    raise "engine not initialized".
    """
    # Mock persistence to avoid database operations
    mock_persistence = Mock()
    mock_persistence.add_thought = Mock()
    mock_persistence.update_thought_status = Mock()
    monkeypatch.setattr("ciris_engine.logic.handlers.memory.memorize_handler.persistence", mock_persistence)
    # base_handler reads `persistence` via its own import; patch there too.
    monkeypatch.setattr("ciris_engine.logic.infrastructure.handlers.base_handler.persistence", mock_persistence)

    # Setup
    memory_service = Mock()
    memory_service.memorize = AsyncMock(return_value=Mock(status=Mock(value="ok")))

    mock_service_registry = AsyncMock()
    mock_time_service = Mock()
    mock_time_service.now = Mock(return_value=datetime.now(timezone.utc))

    # Mock the audit service
    mock_audit_service = AsyncMock()
    mock_audit_service.log_event = AsyncMock()

    bus_manager = BusManager(mock_service_registry, time_service=mock_time_service, audit_service=mock_audit_service)

    # Mock the memory bus to use our memory_service
    mock_memory_bus = AsyncMock()
    mock_memory_bus.memorize = memory_service.memorize
    bus_manager.memory = mock_memory_bus

    deps = ActionHandlerDependencies(
        bus_manager=bus_manager, time_service=mock_time_service, secrets_service=None, shutdown_callback=None
    )

    handler = MemorizeHandler(deps)

    # Create proper GraphNode
    node_attrs = GraphNodeAttributes(
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        created_by="test_user",
        tags=["test", "memory"],
    )

    node = GraphNode(
        id="test_node_id",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes=node_attrs,
        updated_by="test_user",
        updated_at=datetime.now(timezone.utc),
    )

    # Create parameters
    params = MemorizeParams(node=node)

    # Create DMA result
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.MEMORIZE,
        action_parameters=params,
        rationale="Testing memorize action",
        reasoning="This is a test memorization",
        evaluation_time_ms=100.0,
    )

    # Create thought and dispatch context
    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    # Execute handler
    handler_result = await handler.handle(result, thought, dispatch_context)

    # Verify memory service was called correctly
    assert memory_service.memorize.called
    call_args = memory_service.memorize.call_args
    assert call_args is not None
    assert call_args.kwargs["node"] == node  # Check keyword argument
    assert call_args.kwargs["handler_name"] == "MemorizeHandler"


@pytest.mark.asyncio
async def test_recall_handler_with_query(monkeypatch):
    """Test recall handler with proper query parameters."""
    # Mock persistence
    mock_persistence = Mock()
    mock_persistence.add_thought = Mock()
    mock_persistence.update_thought_status = Mock()
    mock_persistence.add_correlation = Mock()
    mock_persistence.get_task_by_id = Mock(return_value=Mock(task_id="test_task", description="Test task"))
    monkeypatch.setattr("ciris_engine.logic.handlers.memory.recall_handler.persistence", mock_persistence)
    monkeypatch.setattr("ciris_engine.logic.infrastructure.handlers.base_handler.persistence", mock_persistence)

    # Setup
    memory_service = Mock()
    test_nodes = [
        GraphNode(
            id="node1",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes=GraphNodeAttributes(
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc), created_by="test_user"
            ),
            updated_by="test_user",
            updated_at=datetime.now(timezone.utc),
        ),
        GraphNode(
            id="node2",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes=GraphNodeAttributes(
                created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc), created_by="test_user"
            ),
            updated_by="test_user",
            updated_at=datetime.now(timezone.utc),
        ),
    ]
    memory_service.recall = AsyncMock(return_value=test_nodes)

    mock_service_registry = AsyncMock()
    mock_time_service = Mock()
    mock_time_service.now = Mock(return_value=datetime.now(timezone.utc))

    # Mock the audit service
    mock_audit_service = AsyncMock()
    mock_audit_service.log_event = AsyncMock()

    bus_manager = BusManager(mock_service_registry, time_service=mock_time_service, audit_service=mock_audit_service)

    # Mock the memory bus - RecallHandler uses bus_manager.memory
    mock_memory_bus = AsyncMock()
    mock_memory_bus.recall = memory_service.recall
    # RecallHandler uses search when query is provided instead of node_id
    mock_memory_bus.search = memory_service.recall  # Use same mock to return test_nodes
    bus_manager.memory = mock_memory_bus

    deps = ActionHandlerDependencies(
        bus_manager=bus_manager, time_service=mock_time_service, secrets_service=None, shutdown_callback=None
    )

    handler = RecallHandler(deps)

    # Create parameters
    params = RecallParams(query="test memory", node_type=NodeType.CONCEPT, limit=10)

    # Create DMA result
    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.RECALL,
        action_parameters=params,
        rationale="Testing recall action",
        reasoning="This is a test recall",
        evaluation_time_ms=100.0,
    )

    # Create thought and dispatch context
    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    # Execute handler
    handler_result = await handler.handle(result, thought, dispatch_context)

    # Debug
    print(f"\nHandler result: {handler_result}")
    print(f"Memory bus search called: {mock_memory_bus.search.called}")
    print(f"Memory bus recall called: {mock_memory_bus.recall.called}")

    # Verify memory service was called (via search since we provided query not node_id)
    assert mock_memory_bus.search.called or mock_memory_bus.recall.called

    # Since we're using query, it should call search
    if mock_memory_bus.search.called:
        call_args = mock_memory_bus.search.call_args
        assert call_args is not None
        assert call_args.kwargs["query"] == "test memory"
        assert "filters" in call_args.kwargs


@pytest.mark.asyncio
async def test_memorize_handler_error_handling(monkeypatch):
    """Test memorize handler when memory service returns error."""
    # Mock persistence
    mock_persistence = Mock()
    mock_persistence.add_thought = Mock()
    mock_persistence.update_thought_status = Mock()
    mock_persistence.add_correlation = Mock()
    mock_persistence.get_task_by_id = Mock(return_value=Mock(task_id="test_task", description="Test task"))
    monkeypatch.setattr("ciris_engine.logic.handlers.memory.memorize_handler.persistence", mock_persistence)
    monkeypatch.setattr("ciris_engine.logic.infrastructure.handlers.base_handler.persistence", mock_persistence)

    # Setup
    memory_service = Mock()
    memory_service.memorize = AsyncMock(
        return_value=Mock(status=Mock(value="error"), error="Memory service unavailable")
    )

    mock_service_registry = AsyncMock()
    mock_time_service = Mock()
    mock_time_service.now = Mock(return_value=datetime.now(timezone.utc))

    # Mock the audit service
    mock_audit_service = AsyncMock()
    mock_audit_service.log_event = AsyncMock()

    bus_manager = BusManager(mock_service_registry, time_service=mock_time_service, audit_service=mock_audit_service)

    # Mock the memory bus
    mock_memory_bus = AsyncMock()
    mock_memory_bus.memorize = memory_service.memorize
    bus_manager.memory = mock_memory_bus

    deps = ActionHandlerDependencies(
        bus_manager=bus_manager, time_service=mock_time_service, secrets_service=None, shutdown_callback=None
    )

    handler = MemorizeHandler(deps)

    # Create node
    node = GraphNode(
        id="error_test_node",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes=GraphNodeAttributes(
            created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc), created_by="test_user"
        ),
        updated_by="test_user",
        updated_at=datetime.now(timezone.utc),
    )

    params = MemorizeParams(node=node)

    result = ActionSelectionDMAResult(
        selected_action=HandlerActionType.MEMORIZE,
        action_parameters=params,
        rationale="Testing error handling",
        reasoning="This should fail",
        evaluation_time_ms=100.0,
    )

    thought = create_test_thought()
    dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

    # Execute handler - should handle error gracefully
    handler_result = await handler.handle(result, thought, dispatch_context)

    # Verify memory service was called
    assert memory_service.memorize.called
    # Handler should return a result even on error
    assert handler_result is not None
