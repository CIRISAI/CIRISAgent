"""
Comprehensive unit tests for the FORGET handler.

Tests cover:
- Parameter validation (ForgetParams)
- Permission checks (_can_forget)
- WA authorization requirements for IDENTITY/ENVIRONMENT scopes
- Memory bus forget operation
- Success and failure follow-up thought creation
- Error handling for invalid parameters
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.memory.forget_handler import ForgetHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import ForgetParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@contextmanager
def patch_persistence_properly(test_task: Optional[Task] = None) -> Any:
    """Properly patch persistence in the base handler."""
    with patch("ciris_engine.logic.infrastructure.handlers.base_handler.persistence") as mock_base_p:
        # Configure base handler persistence
        mock_base_p.get_task_by_id.return_value = test_task
        mock_base_p.add_thought = Mock()
        mock_base_p.update_thought_status = Mock(return_value=True)
        mock_base_p.add_correlation = Mock()

        yield mock_base_p


@pytest.fixture
def mock_time_service() -> Mock:
    """Mock time service."""
    service = Mock(spec=TimeServiceProtocol)
    service.now = Mock(return_value=datetime.now(timezone.utc))
    service.now_iso = Mock(return_value=datetime.now(timezone.utc).isoformat())
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
    bus.forget = AsyncMock(
        return_value=MemoryOpResult(
            status=MemoryOpStatus.OK,
            reason="Node forgotten successfully",
        )
    )
    return bus


@pytest.fixture
def mock_bus_manager(mock_memory_bus: AsyncMock) -> Mock:
    """Mock bus manager."""
    manager = Mock(spec=BusManager)
    manager.memory = mock_memory_bus
    manager.audit_service = AsyncMock()
    manager.audit_service.log_event = AsyncMock()
    return manager


@pytest.fixture
def handler_dependencies(
    mock_time_service: Mock,
    mock_secrets_service: Mock,
    mock_bus_manager: Mock,
) -> ActionHandlerDependencies:
    """Create handler dependencies."""
    return ActionHandlerDependencies(
        time_service=mock_time_service,
        secrets_service=mock_secrets_service,
        bus_manager=mock_bus_manager,
        shutdown_callback=None,
    )


@pytest.fixture
def forget_handler(handler_dependencies: ActionHandlerDependencies) -> ForgetHandler:
    """Create ForgetHandler instance."""
    return ForgetHandler(handler_dependencies)


@pytest.fixture
def test_thought() -> Thought:
    """Create a test thought."""
    return Thought(
        thought_id="thought_123",
        source_task_id="task_456",
        content="Test forget operation",
        thought_type="STANDARD",
        status=ThoughtStatus.PROCESSING,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        context=ThoughtContext(
            task_id="task_456",
            correlation_id="corr_123",
            channel_id="channel_1",
            round_number=1,
        ),
        thought_depth=0,
    )


@pytest.fixture
def test_task() -> Task:
    """Create a test task."""
    return Task(
        task_id="task_456",
        description="Test task",
        status=TaskStatus.ACTIVE,
        priority=5,
        channel_id="channel_1",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def channel_context() -> ChannelContext:
    """Create test channel context."""
    return ChannelContext(
        channel_id="channel_1",
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
    """Create dispatch context."""
    return DispatchContext(
        channel_context=channel_context,
        author_id="test_author",
        author_name="Test Author",
        origin_service="test_service",
        handler_name="ForgetHandler",
        action_type=HandlerActionType.FORGET,
        task_id="task_456",
        thought_id="thought_123",
        source_task_id="task_456",
        event_summary="Test forget action",
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
def local_graph_node() -> GraphNode:
    """Create a LOCAL scope graph node."""
    return GraphNode(
        id="test_node_1",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes={"content": "test content", "created_by": "test_user"},
    )


@pytest.fixture
def identity_graph_node() -> GraphNode:
    """Create an IDENTITY scope graph node."""
    return GraphNode(
        id="identity_node_1",
        type=NodeType.IDENTITY,
        scope=GraphScope.IDENTITY,
        attributes={"content": "identity content", "created_by": "test_user"},
    )


@pytest.fixture
def environment_graph_node() -> GraphNode:
    """Create an ENVIRONMENT scope graph node."""
    return GraphNode(
        id="env_node_1",
        type=NodeType.CONCEPT,
        scope=GraphScope.ENVIRONMENT,
        attributes={"content": "environment content", "created_by": "test_user"},
    )


class TestForgetHandler:
    """Test cases for ForgetHandler."""

    @pytest.mark.asyncio
    async def test_forget_local_scope_success(
        self,
        forget_handler: ForgetHandler,
        test_thought: Thought,
        test_task: Task,
        dispatch_context: DispatchContext,
        local_graph_node: GraphNode,
        mock_memory_bus: AsyncMock,
    ) -> None:
        """Test successful forget operation for LOCAL scope."""
        params = ForgetParams(node=local_graph_node, reason="Test forget operation")
        action_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.FORGET,
            action_parameters=params,
            rationale="Forgetting local node",
        )

        with patch_persistence_properly(test_task):
            result = await forget_handler.handle(action_result, test_thought, dispatch_context)

        # Verify memory bus was called
        mock_memory_bus.forget.assert_called_once_with(
            node=local_graph_node,
            handler_name="ForgetHandler",
        )

        # Verify follow-up thought was created
        assert result is not None

    @pytest.mark.asyncio
    async def test_forget_identity_scope_without_wa_denied(
        self,
        forget_handler: ForgetHandler,
        test_thought: Thought,
        test_task: Task,
        dispatch_context: DispatchContext,
        identity_graph_node: GraphNode,
        mock_memory_bus: AsyncMock,
    ) -> None:
        """Test that IDENTITY scope forget requires WA authorization."""
        params = ForgetParams(node=identity_graph_node, reason="Test forget operation")
        action_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.FORGET,
            action_parameters=params,
            rationale="Forgetting identity node",
        )

        # No WA authorization in dispatch_context
        with patch_persistence_properly(test_task):
            result = await forget_handler.handle(action_result, test_thought, dispatch_context)

        # Verify memory bus was NOT called (permission denied)
        mock_memory_bus.forget.assert_not_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_forget_identity_scope_with_wa_authorized(
        self,
        forget_handler: ForgetHandler,
        test_thought: Thought,
        test_task: Task,
        identity_graph_node: GraphNode,
        mock_memory_bus: AsyncMock,
        channel_context: ChannelContext,
    ) -> None:
        """Test IDENTITY scope forget succeeds with WA authorization."""
        params = ForgetParams(node=identity_graph_node, reason="Test forget operation")
        action_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.FORGET,
            action_parameters=params,
            rationale="Forgetting identity node with WA auth",
        )

        # Create dispatch context with WA authorization
        dispatch_context = DispatchContext(
            channel_context=channel_context,
            author_id="test_author",
            author_name="Test Author",
            origin_service="test_service",
            handler_name="ForgetHandler",
            action_type=HandlerActionType.FORGET,
            task_id="task_456",
            thought_id="thought_123",
            source_task_id="task_456",
            event_summary="Test forget action",
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            wa_id=None,
            wa_authorized=True,
            wa_context=None,
            conscience_failure_context=None,
            epistemic_data=None,
            correlation_id="corr_123",
            span_id=None,
            trace_id=None,
        )

        with patch_persistence_properly():
            result = await forget_handler.handle(action_result, test_thought, dispatch_context)

        # Verify memory bus was called
        mock_memory_bus.forget.assert_called_once()
        assert result is not None

    @pytest.mark.asyncio
    async def test_forget_environment_scope_without_wa_denied(
        self,
        forget_handler: ForgetHandler,
        test_thought: Thought,
        test_task: Task,
        dispatch_context: DispatchContext,
        environment_graph_node: GraphNode,
        mock_memory_bus: AsyncMock,
    ) -> None:
        """Test that ENVIRONMENT scope forget requires WA authorization."""
        params = ForgetParams(node=environment_graph_node, reason="Test forget operation")
        action_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.FORGET,
            action_parameters=params,
            rationale="Forgetting environment node",
        )

        with patch_persistence_properly(test_task):
            result = await forget_handler.handle(action_result, test_thought, dispatch_context)

        # Verify memory bus was NOT called
        mock_memory_bus.forget.assert_not_called()
        assert result is not None

    @pytest.mark.asyncio
    async def test_forget_failure_creates_failed_followup(
        self,
        forget_handler: ForgetHandler,
        test_thought: Thought,
        test_task: Task,
        dispatch_context: DispatchContext,
        local_graph_node: GraphNode,
        mock_memory_bus: AsyncMock,
    ) -> None:
        """Test that failed forget operation creates failed follow-up thought."""
        # Configure memory bus to return failure
        mock_memory_bus.forget.return_value = MemoryOpResult(
            status=MemoryOpStatus.ERROR,
            error="Node not found",
        )

        params = ForgetParams(node=local_graph_node, reason="Test forget operation")
        action_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.FORGET,
            action_parameters=params,
            rationale="Forgetting node",
        )

        with patch_persistence_properly(test_task) as mock_persistence:
            result = await forget_handler.handle(action_result, test_thought, dispatch_context)

            # Verify thought was marked as failed
            mock_persistence.update_thought_status.assert_called()

    @pytest.mark.asyncio
    async def test_invalid_params_type_creates_failed_followup(
        self,
        forget_handler: ForgetHandler,
        test_thought: Thought,
        test_task: Task,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
    ) -> None:
        """Test that invalid parameter type creates failed follow-up."""
        # Create action result with wrong params type (SpeakParams instead of ForgetParams)
        from ciris_engine.schemas.actions.parameters import SpeakParams

        wrong_params = SpeakParams(content="Wrong type of params")
        action_result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.FORGET,
            action_parameters=wrong_params,
            rationale="Invalid params",
        )

        with patch_persistence_properly(test_task):
            result = await forget_handler.handle(action_result, test_thought, dispatch_context)

        # Memory bus should not be called because params conversion will fail
        mock_memory_bus.forget.assert_not_called()
        assert result is not None


class TestForgetHandlerCanForget:
    """Test _can_forget permission checks."""

    @pytest.fixture
    def forget_handler_simple(self, handler_dependencies: ActionHandlerDependencies) -> ForgetHandler:
        """Create ForgetHandler for unit testing."""
        return ForgetHandler(handler_dependencies)

    def test_can_forget_local_scope(
        self,
        forget_handler_simple: ForgetHandler,
        local_graph_node: GraphNode,
        dispatch_context: DispatchContext,
    ) -> None:
        """Test LOCAL scope is always allowed."""
        params = ForgetParams(node=local_graph_node, reason="Test forget operation")
        assert forget_handler_simple._can_forget(params, dispatch_context) is True

    def test_can_forget_identity_without_wa(
        self,
        forget_handler_simple: ForgetHandler,
        identity_graph_node: GraphNode,
        dispatch_context: DispatchContext,
    ) -> None:
        """Test IDENTITY scope denied without WA auth."""
        params = ForgetParams(node=identity_graph_node, reason="Test forget operation")
        assert forget_handler_simple._can_forget(params, dispatch_context) is False

    def test_can_forget_identity_with_wa(
        self,
        forget_handler_simple: ForgetHandler,
        identity_graph_node: GraphNode,
        channel_context: ChannelContext,
    ) -> None:
        """Test IDENTITY scope allowed with WA auth."""
        params = ForgetParams(node=identity_graph_node, reason="Test forget operation")
        dispatch_context = DispatchContext(
            channel_context=channel_context,
            author_id="test_author",
            author_name="Test Author",
            origin_service="test_service",
            handler_name="ForgetHandler",
            action_type=HandlerActionType.FORGET,
            task_id="task_456",
            thought_id="thought_123",
            source_task_id="task_456",
            event_summary="Test forget action",
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            wa_id=None,
            wa_authorized=True,
            wa_context=None,
            conscience_failure_context=None,
            epistemic_data=None,
            correlation_id="corr_123",
            span_id=None,
            trace_id=None,
        )
        assert forget_handler_simple._can_forget(params, dispatch_context) is True

    def test_can_forget_environment_without_wa(
        self,
        forget_handler_simple: ForgetHandler,
        environment_graph_node: GraphNode,
        dispatch_context: DispatchContext,
    ) -> None:
        """Test ENVIRONMENT scope denied without WA auth."""
        params = ForgetParams(node=environment_graph_node, reason="Test forget operation")
        assert forget_handler_simple._can_forget(params, dispatch_context) is False

    def test_can_forget_environment_with_wa(
        self,
        forget_handler_simple: ForgetHandler,
        environment_graph_node: GraphNode,
        channel_context: ChannelContext,
    ) -> None:
        """Test ENVIRONMENT scope allowed with WA auth."""
        params = ForgetParams(node=environment_graph_node, reason="Test forget operation")
        dispatch_context = DispatchContext(
            channel_context=channel_context,
            author_id="test_author",
            author_name="Test Author",
            origin_service="test_service",
            handler_name="ForgetHandler",
            action_type=HandlerActionType.FORGET,
            task_id="task_456",
            thought_id="thought_123",
            source_task_id="task_456",
            event_summary="Test forget action",
            event_timestamp=datetime.now(timezone.utc).isoformat(),
            wa_id=None,
            wa_authorized=True,
            wa_context=None,
            conscience_failure_context=None,
            epistemic_data=None,
            correlation_id="corr_123",
            span_id=None,
            trace_id=None,
        )
        assert forget_handler_simple._can_forget(params, dispatch_context) is True
