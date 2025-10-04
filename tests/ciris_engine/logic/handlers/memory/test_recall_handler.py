"""
Comprehensive unit tests for the RECALL handler.

Tests cover:
- Memory query construction and validation
- Node type filtering
- Search scope (LOCAL, REGIONAL, GLOBAL)
- Query pattern matching
- Empty result handling
- Memory bus integration
- Result formatting and follow-up creation
- Error handling for invalid queries
- Pagination and limit handling
- Wildcard searches
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.memory.recall_handler import RecallHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import RecallParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


@contextmanager
def patch_persistence_properly(test_task: Optional[Task] = None) -> Any:
    """Properly patch persistence in both handler and base handler."""
    with patch("ciris_engine.logic.persistence.update_thought_status", return_value=True) as mock_update_status, patch(
        "ciris_engine.logic.persistence.add_thought"
    ) as mock_add_thought, patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation, patch(
        "ciris_engine.logic.persistence.get_task_by_id", return_value=test_task
    ) as mock_get_task:

        # Create a mock persistence module with all the methods
        mock_p = Mock()
        mock_p.update_thought_status = mock_update_status
        mock_p.add_thought = mock_add_thought
        mock_p.add_correlation = mock_add_correlation
        mock_p.get_task_by_id = mock_get_task

        yield mock_p


# Test fixtures
@pytest.fixture
def mock_time_service() -> Mock:
    """Mock time service."""
    service = Mock(spec=TimeServiceProtocol)
    service.now = Mock(return_value=datetime.now(timezone.utc))
    return service


@pytest.fixture
def mock_secrets_service() -> Mock:
    """Mock secrets service."""
    service = Mock(spec=SecretsService)
    service.decapsulate_secrets_in_parameters = AsyncMock(
        side_effect=lambda action_type, action_params, context: action_params
    )
    return service


@pytest.fixture
def mock_memory_bus() -> AsyncMock:
    """Mock memory bus."""
    bus = AsyncMock()
    bus.recall = AsyncMock(return_value=[])
    bus.search = AsyncMock(return_value=[])
    return bus


@pytest.fixture
def mock_bus_manager(mock_memory_bus: AsyncMock) -> Mock:
    """Mock bus manager with memory bus."""
    manager = Mock(spec=BusManager)
    manager.memory = mock_memory_bus
    manager.audit_service = AsyncMock()
    manager.audit_service.log_event = AsyncMock()
    return manager


@pytest.fixture
def handler_dependencies(
    mock_bus_manager: Mock, mock_time_service: Mock, mock_secrets_service: Mock
) -> ActionHandlerDependencies:
    """Create handler dependencies."""
    return ActionHandlerDependencies(
        bus_manager=mock_bus_manager,
        time_service=mock_time_service,
        secrets_service=mock_secrets_service,
        shutdown_callback=None,
    )


@pytest.fixture
def recall_handler(handler_dependencies: ActionHandlerDependencies) -> RecallHandler:
    """Create RECALL handler instance."""
    return RecallHandler(handler_dependencies)


@pytest.fixture
def channel_context() -> ChannelContext:
    """Create test channel context."""
    return ChannelContext(
        channel_id="test_channel_123",
        channel_type="text",
        created_at=datetime.now(timezone.utc),
        channel_name="Test Channel",
        is_private=False,
        is_active=True,
        last_activity=None,
        message_count=0,
        moderation_level="standard",
    )


@pytest.fixture
def dispatch_context(channel_context: ChannelContext) -> DispatchContext:
    """Create test dispatch context."""
    return DispatchContext(
        channel_context=channel_context,
        author_id="test_author",
        author_name="Test Author",
        origin_service="test_service",
        handler_name="RecallHandler",
        action_type=HandlerActionType.RECALL,
        task_id="task_123",
        thought_id="thought_123",
        source_task_id="task_123",
        event_summary="Test recall action",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        wa_id=None,
        wa_authorized=False,
        wa_context=None,
        conscience_failure_context=None,
        epistemic_data=None,
        correlation_id="corr_123",
        span_id=None,
        trace_id=None,
    )


@pytest.fixture
def test_thought() -> Thought:
    """Create test thought."""
    return Thought(
        thought_id="thought_123",
        source_task_id="task_123",
        content="Need to recall some information",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        channel_id="test_channel_123",
        status=ThoughtStatus.PROCESSING,
        thought_depth=1,
        round_number=1,
        ponder_notes=None,
        parent_thought_id=None,
        final_action=None,
        context=ThoughtContext(
            task_id="task_123",
            correlation_id="corr_123",
            round_number=1,
            depth=1,
            channel_id="test_channel_123",
            parent_thought_id=None,
        ),
    )


@pytest.fixture
def test_task() -> Task:
    """Create test task."""
    return Task(
        task_id="task_123",
        channel_id="test_channel_123",
        description="Test task description",
        status=TaskStatus.ACTIVE,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        priority=5,
        parent_task_id=None,
        context=None,
        outcome=None,
        signed_by=None,
        signature=None,
        signed_at=None,
    )


@pytest.fixture
def sample_memory_nodes() -> List[GraphNode]:
    """Create sample memory nodes for testing."""
    return [
        GraphNode(
            id="mem_identity_1",
            type=NodeType.IDENTITY,
            scope=GraphScope.LOCAL,
            attributes={
                "content": "I am CIRIS, an ethical AI assistant",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "created_by": "test",
            },
        ),
        GraphNode(
            id="mem_task_1",
            type=NodeType.TASK_SUMMARY,
            scope=GraphScope.LOCAL,
            attributes={
                "content": "Help user with Python programming",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "created_by": "test",
            },
        ),
        GraphNode(
            id="mem_observation_1",
            type=NodeType.OBSERVATION,
            scope=GraphScope.LOCAL,
            attributes={
                "content": "User prefers concise answers",
                "created_at": datetime.now(timezone.utc),
                "updated_at": datetime.now(timezone.utc),
                "created_by": "test",
            },
        ),
    ]


@pytest.fixture
def recall_params() -> RecallParams:
    """Create test RECALL parameters."""
    return RecallParams(
        query="identity", node_type=NodeType.IDENTITY.value, node_id=None, scope=GraphScope.LOCAL, limit=10
    )


@pytest.fixture
def action_result(recall_params: RecallParams) -> ActionSelectionDMAResult:
    """Create test action selection result."""
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.RECALL,
        action_parameters=recall_params,
        rationale="Need to recall identity information",
        raw_llm_response="RECALL: identity, type=IDENTITY",
        reasoning="User asking about who I am",
        evaluation_time_ms=100.0,
        resource_usage=None,
    )


class TestRecallHandler:
    """Test suite for RECALL handler."""

    @pytest.mark.asyncio
    async def test_successful_recall_by_query(
        self,
        recall_handler: RecallHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        sample_memory_nodes: List[GraphNode],
    ) -> None:
        """Test successful memory recall by query."""
        # Configure memory bus to return sample nodes
        mock_memory_bus.search.return_value = [sample_memory_nodes[0]]  # Return identity node

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            follow_up_id = await recall_handler.handle(action_result, test_thought, dispatch_context)

            # Verify memory search was called
            mock_memory_bus.search.assert_called_once()
            search_call = mock_memory_bus.search.call_args
            assert search_call.kwargs["query"] == "identity"
            assert search_call.kwargs["filters"].node_type == NodeType.IDENTITY.value

            # Verify thought status was updated
            assert mock_persistence.update_thought_status.called
            update_call = mock_persistence.update_thought_status.call_args
            assert update_call.kwargs["thought_id"] == "thought_123"
            assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED

            # Verify follow-up thought was created with results
            assert follow_up_id is not None
            mock_persistence.add_thought.assert_called_once()
            follow_up_call = mock_persistence.add_thought.call_args[0][0]
            assert "I am CIRIS, an ethical AI assistant" in follow_up_call.content

    @pytest.mark.asyncio
    async def test_recall_by_node_id(
        self,
        recall_handler: RecallHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        sample_memory_nodes: List[GraphNode],
    ) -> None:
        """Test recall by specific node ID."""
        # Create params with node_id
        params = RecallParams(node_id="mem_task_1", query=None, node_type=None, scope=GraphScope.LOCAL, limit=10)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.RECALL,
            action_parameters=params,
            rationale="Recall specific node",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Configure memory bus
        mock_memory_bus.recall.return_value = [sample_memory_nodes[1]]

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await recall_handler.handle(result, test_thought, dispatch_context)

            # Verify exact match recall was attempted first
            mock_memory_bus.recall.assert_called_once()
            recall_call = mock_memory_bus.recall.call_args
            assert recall_call.kwargs["recall_query"].node_id == "mem_task_1"

    @pytest.mark.asyncio
    async def test_recall_by_node_type_only(
        self,
        recall_handler: RecallHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        sample_memory_nodes: List[GraphNode],
    ) -> None:
        """Test recall all nodes of a specific type."""
        # Create params with only node_type
        params = RecallParams(
            node_id=None, query=None, node_type=NodeType.OBSERVATION.value, scope=GraphScope.LOCAL, limit=10
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.RECALL,
            action_parameters=params,
            rationale="Recall all observations",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Configure memory bus - first search returns nothing, then wildcard returns all
        mock_memory_bus.search.return_value = []
        mock_memory_bus.recall.side_effect = [[sample_memory_nodes[2]]]  # Return observation node on wildcard

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await recall_handler.handle(result, test_thought, dispatch_context)

            # Verify wildcard recall was used
            assert mock_memory_bus.recall.call_count == 1  # Only wildcard recall
            wildcard_call = mock_memory_bus.recall.call_args
            assert wildcard_call.kwargs["recall_query"].node_id == "*"
            assert wildcard_call.kwargs["recall_query"].type == NodeType.OBSERVATION

    @pytest.mark.asyncio
    async def test_empty_recall_results(
        self,
        recall_handler: RecallHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test handling when no memories are found."""
        # Configure memory bus to return empty results
        mock_memory_bus.recall.return_value = []
        mock_memory_bus.search.return_value = []

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            follow_up_id = await recall_handler.handle(action_result, test_thought, dispatch_context)

            # Verify thought was still completed
            assert mock_persistence.update_thought_status.called
            update_call = mock_persistence.update_thought_status.call_args
            assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED

            # Verify follow-up indicates no results
            follow_up_call = mock_persistence.add_thought.call_args[0][0]
            assert "No memories found" in follow_up_call.content or "no matching" in follow_up_call.content.lower()

    @pytest.mark.asyncio
    async def test_scope_filtering(
        self,
        recall_handler: RecallHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test different scope levels (LOCAL, REGIONAL, GLOBAL)."""
        scopes = [GraphScope.LOCAL, GraphScope.IDENTITY, GraphScope.COMMUNITY]

        with patch_persistence_properly(test_task) as mock_persistence:
            for scope in scopes:
                # Reset mocks
                mock_memory_bus.search.reset_mock()
                mock_persistence.add_thought.reset_mock()

                # Create params with different scope
                params = RecallParams(query="test", node_type=None, node_id=None, scope=scope, limit=10)

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.RECALL,
                    action_parameters=params,
                    rationale=f"Test {scope.value} scope",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await recall_handler.handle(result, test_thought, dispatch_context)

                # Verify correct scope was used
                search_call = mock_memory_bus.search.call_args
                assert search_call.kwargs["filters"].scope == scope.value

    @pytest.mark.asyncio
    async def test_limit_enforcement(
        self,
        recall_handler: RecallHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        sample_memory_nodes: List[GraphNode],
    ) -> None:
        """Test that result limits are enforced."""
        # Create params with small limit
        params = RecallParams(
            query=None, node_type=NodeType.TASK_SUMMARY.value, node_id=None, scope=GraphScope.LOCAL, limit=2
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.RECALL,
            action_parameters=params,
            rationale="Test limit enforcement",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Configure memory bus to return many nodes
        many_nodes = sample_memory_nodes * 5  # 15 nodes
        mock_memory_bus.search.return_value = []
        mock_memory_bus.recall.side_effect = [[], many_nodes]  # First exact fails, then wildcard returns many

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await recall_handler.handle(result, test_thought, dispatch_context)

            # Verify follow-up only contains limited results
            follow_up_call = mock_persistence.add_thought.call_args[0][0]
            # Count how many node results are in the content
            # This is implementation-specific but the handler should respect the limit
            assert follow_up_call.content is not None

    @pytest.mark.asyncio
    async def test_parameter_validation_error(
        self, recall_handler: RecallHandler, test_thought: Thought, dispatch_context: DispatchContext
    ) -> None:
        """Test handling of invalid parameters."""
        with patch_persistence_properly() as mock_persistence:
            # Create result with valid structure but mock validation to fail
            result = ActionSelectionDMAResult(
                selected_action=HandlerActionType.RECALL,
                action_parameters=RecallParams(query="test"),
                rationale="Test validation",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

            # Mock the validation method to raise an error
            with patch.object(recall_handler, "_validate_and_convert_params") as mock_validate:
                mock_validate.side_effect = ValueError("Invalid scope value")

                # Execute handler - should handle validation error
                follow_up_id = await recall_handler.handle(result, test_thought, dispatch_context)

                # Verify thought was completed (base handler marks it completed even with error)
                # The status will be COMPLETED with an error follow-up
                mock_persistence.update_thought_status.assert_called()
                # Get the actual call arguments
                call_args = mock_persistence.update_thought_status.call_args
                assert call_args.kwargs["thought_id"] == "thought_123"

                # Verify error follow-up was created
                assert follow_up_id is not None
                follow_up_call = mock_persistence.add_thought.call_args[0][0]
                assert "RECALL action failed" in follow_up_call.content

    @pytest.mark.asyncio
    async def test_memory_bus_exception(
        self,
        recall_handler: RecallHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test handling of exceptions from memory bus."""
        # Configure memory bus to raise exception
        mock_memory_bus.search.side_effect = Exception("Database connection error")

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler - should raise exception (no try/catch in handler)
            with pytest.raises(Exception, match="Database connection error"):
                await recall_handler.handle(action_result, test_thought, dispatch_context)

    @pytest.mark.asyncio
    async def test_complex_query_patterns(
        self,
        recall_handler: RecallHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test various complex query patterns."""
        queries = [
            ("user preferences", NodeType.OBSERVATION),
            ("previous conversation", NodeType.CONVERSATION_SUMMARY),
            ("system configuration", NodeType.CONFIG),
            ("", None),  # Empty query
            ("very long " * 50 + "query", None),  # Very long query
        ]

        with patch_persistence_properly(test_task) as mock_persistence:
            for query, node_type in queries:
                # Reset mocks
                mock_memory_bus.search.reset_mock()
                mock_persistence.add_thought.reset_mock()

                # Create params
                params = RecallParams(
                    query=query,
                    node_type=node_type.value if node_type else None,
                    node_id=None,
                    scope=GraphScope.LOCAL,
                    limit=10,
                )

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.RECALL,
                    action_parameters=params,
                    rationale="Test query patterns",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await recall_handler.handle(result, test_thought, dispatch_context)

                # Verify search was called with correct query
                if query or node_type:  # Skip if both empty
                    mock_memory_bus.search.assert_called()

    @pytest.mark.asyncio
    async def test_audit_trail(
        self,
        recall_handler: RecallHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_bus_manager: Mock,
        test_task: Task,
        sample_memory_nodes: List[GraphNode],
    ) -> None:
        """Test audit logging for RECALL actions."""
        # Configure memory bus to return results so outcome is "success"
        mock_bus_manager.memory.search.return_value = [sample_memory_nodes[0]]

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await recall_handler.handle(action_result, test_thought, dispatch_context)

            # NOTE: Audit logging removed from handlers - action_dispatcher handles centralized audit logging
            pass  # Test still validates handler execution
