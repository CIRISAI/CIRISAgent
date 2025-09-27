"""
Comprehensive unit tests for the MEMORIZE handler.

Tests cover:
- Memory node creation with various content types
- Tag validation and processing
- Scope assignment (LOCAL, REGIONAL, GLOBAL)
- Node type inference
- Memory bus integration
- Duplicate detection
- Content validation
- Error handling for invalid memory operations
- Memory graph edge creation
- Metadata attachment
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.memory.memorize_handler import MemorizeHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import MemorizeParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@contextmanager
def patch_persistence_properly(test_task: Optional[Task] = None) -> Any:
    """Properly patch persistence in both handler and base handler."""
    with patch("ciris_engine.logic.handlers.memory.memorize_handler.persistence") as mock_p, patch(
        "ciris_engine.logic.infrastructure.handlers.base_handler.persistence"
    ) as mock_base_p:
        # Configure handler persistence
        mock_p.get_task_by_id.return_value = test_task
        mock_p.add_thought = Mock()
        mock_p.update_thought_status = Mock(return_value=True)
        mock_p.add_correlation = Mock()

        # Configure base handler persistence
        mock_base_p.add_thought = Mock()
        mock_base_p.update_thought_status = Mock(return_value=True)
        mock_base_p.add_correlation = Mock()

        # Return both mocks as a tuple
        yield mock_p, mock_base_p


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
    # Return a successful MemoryOpResult
    bus.memorize = AsyncMock(
        return_value=MemoryOpResult(
            status=MemoryOpStatus.SUCCESS, reason="Successfully memorized", data={"node_id": "test_memory_node_123"}
        )
    )
    bus.search = AsyncMock(return_value=[])
    bus.get_node = AsyncMock(return_value=None)
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
def memorize_handler(handler_dependencies: ActionHandlerDependencies) -> MemorizeHandler:
    """Create MEMORIZE handler instance."""
    return MemorizeHandler(handler_dependencies)


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
        handler_name="MemorizeHandler",
        action_type=HandlerActionType.MEMORIZE,
        task_id="task_123",
        thought_id="thought_123",
        source_task_id="task_123",
        event_summary="Test memorize action",
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
        content="Need to remember this information",
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
def memorize_params() -> MemorizeParams:
    """Create test MEMORIZE parameters."""
    # Create a GraphNode with attributes
    node = GraphNode(
        id="test_memory_node_123",
        type=NodeType.OBSERVATION,
        scope=GraphScope.LOCAL,
        attributes={
            "content": "User prefers detailed explanations",
            "created_by": "test_handler",
            "tags": ["user_preference", "communication_style"],
        },
    )
    return MemorizeParams(node=node)


@pytest.fixture
def action_result(memorize_params: MemorizeParams) -> ActionSelectionDMAResult:
    """Create test action selection result."""
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.MEMORIZE,
        action_parameters=memorize_params,
        rationale="Important user preference to remember",
        raw_llm_response="MEMORIZE: User prefers detailed explanations",
        reasoning="This will help tailor future responses",
        evaluation_time_ms=100.0,
        resource_usage=None,
    )


class TestMemorizeHandler:
    """Test suite for MEMORIZE handler."""

    @pytest.mark.asyncio
    async def test_successful_memorization(
        self,
        memorize_handler: MemorizeHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test successful memory creation."""
        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            follow_up_id = await memorize_handler.handle(action_result, test_thought, dispatch_context)

            # Verify memory bus was called
            mock_memory_bus.memorize.assert_called_once()
            memorize_call = mock_memory_bus.memorize.call_args

            # Check the memorize parameters
            assert memorize_call.kwargs["node"].id == "test_memory_node_123"
            assert memorize_call.kwargs["node"].type == NodeType.OBSERVATION
            assert memorize_call.kwargs["node"].scope == GraphScope.LOCAL
            assert memorize_call.kwargs["node"].attributes["content"] == "User prefers detailed explanations"
            assert memorize_call.kwargs["node"].attributes["tags"] == ["user_preference", "communication_style"]
            assert memorize_call.kwargs["handler_name"] == "MemorizeHandler"

            # Verify thought status was updated (in base handler)
            assert mock_base_persistence.update_thought_status.called
            update_call = mock_base_persistence.update_thought_status.call_args
            assert update_call.kwargs["thought_id"] == "thought_123"
            assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED

            # Verify follow-up thought was created
            assert follow_up_id is not None
            mock_base_persistence.add_thought.assert_called_once()
            follow_up_call = mock_base_persistence.add_thought.call_args[0][0]
            assert "memorize complete" in follow_up_call.content.lower()
            assert "test_memory_node_123" in follow_up_call.content

    @pytest.mark.asyncio
    async def test_memorize_different_node_types(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test memorizing different types of nodes."""
        node_types = [
            (NodeType.IDENTITY, "I am CIRIS, an ethical AI", {}),
            (NodeType.TASK_SUMMARY, "Help user debug Python code", {}),
            (NodeType.OBSERVATION, "User is frustrated", {}),
            (NodeType.BEHAVIORAL, "User likes concise answers", {}),
            (NodeType.CONVERSATION_SUMMARY, "Discussion about ethics", {}),
            (NodeType.CONFIG, "Temperature setting: 0.7", {"value": 0.7}),  # CONFIG needs value
        ]

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            for node_type, content, extra_attrs in node_types:
                # Reset mocks
                mock_memory_bus.memorize.reset_mock()
                mock_persistence.add_thought.reset_mock()

                # Create params for this node type
                attributes = {"content": content, "created_by": "test_handler", "tags": [node_type.value.lower()]}
                attributes.update(extra_attrs)  # Add any extra attributes (like value for CONFIG)

                node = GraphNode(
                    id=f"test_{node_type.value}_node",
                    type=node_type,
                    scope=GraphScope.LOCAL,
                    attributes=attributes,
                )
                params = MemorizeParams(node=node)

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.MEMORIZE,
                    action_parameters=params,
                    rationale=f"Test {node_type.value} memorization",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await memorize_handler.handle(result, test_thought, dispatch_context)

                # Verify correct node type was used
                memorize_call = mock_memory_bus.memorize.call_args
                assert memorize_call.kwargs["node"].type == node_type

                # For CONFIG nodes, the structure is transformed
                if node_type == NodeType.CONFIG:
                    # CONFIG nodes get special handling - check for the value
                    attrs = memorize_call.kwargs["node"].attributes
                    assert "key" in attrs
                    assert attrs["key"] == "test_config_node"
                    assert "value" in attrs
                    assert attrs["value"]["float_value"] == 0.7
                else:
                    assert memorize_call.kwargs["node"].attributes["content"] == content

    @pytest.mark.asyncio
    async def test_scope_assignment(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test different scope levels for memories."""
        scopes = [GraphScope.LOCAL, GraphScope.IDENTITY, GraphScope.ENVIRONMENT, GraphScope.COMMUNITY]

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            for scope in scopes:
                # Reset mocks
                mock_memory_bus.memorize.reset_mock()

                # Create params with different scope
                node = GraphNode(
                    id=f"test_scope_{scope.value}_node",
                    type=NodeType.OBSERVATION,
                    scope=scope,
                    attributes={
                        "content": f"Content for {scope.value} scope",
                        "created_by": "test_handler",
                        "tags": [f"scope_{scope.value}"],
                    },
                )
                params = MemorizeParams(node=node)

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.MEMORIZE,
                    action_parameters=params,
                    rationale=f"Test {scope.value} scope",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await memorize_handler.handle(result, test_thought, dispatch_context)

                # If scope is IDENTITY without WA auth, it should be rejected
                if scope == GraphScope.IDENTITY and not dispatch_context.wa_authorized:
                    # Handler should reject and not call memorize
                    assert not mock_memory_bus.memorize.called
                else:
                    # Verify correct scope was used
                    memorize_call = mock_memory_bus.memorize.call_args
                    assert memorize_call.kwargs["node"].scope == scope

    @pytest.mark.asyncio
    async def test_tag_processing(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test various tag configurations."""
        tag_sets = [
            [],  # No tags
            ["single_tag"],  # Single tag
            ["tag1", "tag2", "tag3"],  # Multiple tags
            ["very_long_tag_name_" * 10],  # Very long tag
            ["tag with spaces", "tag-with-dashes", "tag_with_underscores"],  # Various formats
        ]

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            for tags in tag_sets:
                # Reset mocks
                mock_memory_bus.memorize.reset_mock()

                # Create params with different tags
                node = GraphNode(
                    id=f"test_tags_node_{len(tags)}",
                    type=NodeType.OBSERVATION,
                    scope=GraphScope.LOCAL,
                    attributes={"content": "Test content", "created_by": "test_handler", "tags": tags},
                )
                params = MemorizeParams(node=node)

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.MEMORIZE,
                    action_parameters=params,
                    rationale="Test tag processing",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await memorize_handler.handle(result, test_thought, dispatch_context)

                # Verify tags were passed correctly
                memorize_call = mock_memory_bus.memorize.call_args
                assert memorize_call.kwargs["node"].attributes["tags"] == tags

    @pytest.mark.asyncio
    async def test_empty_content_handling(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        test_task: Task,
    ) -> None:
        """Test handling of empty content."""
        # Create params with empty content
        node = GraphNode(
            id="test_empty_content_node",
            type=NodeType.OBSERVATION,
            scope=GraphScope.LOCAL,
            attributes={"content": "", "created_by": "test_handler", "tags": ["empty"]},
        )
        params = MemorizeParams(node=node)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE,
            action_parameters=params,
            rationale="Test empty content",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # The handler might validate this - depends on implementation
            # For now, assume it processes empty content
            await memorize_handler.handle(result, test_thought, dispatch_context)

            # Should still complete, even with empty content
            assert mock_base_persistence.update_thought_status.called

    @pytest.mark.asyncio
    async def test_memorize_with_metadata(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test memorization with additional metadata."""
        # Create params with metadata in tags
        node = GraphNode(
            id="test_metadata_node",
            type=NodeType.OBSERVATION,
            scope=GraphScope.LOCAL,
            attributes={
                "content": "User mentioned they work in healthcare",
                "created_by": "test_handler",
                "tags": ["user_info", "profession:healthcare", "context:conversation"],
            },
        )
        params = MemorizeParams(node=node)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE,
            action_parameters=params,
            rationale="Store user profession info",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            await memorize_handler.handle(result, test_thought, dispatch_context)

            # Verify metadata was included
            memorize_call = mock_memory_bus.memorize.call_args
            assert "profession:healthcare" in memorize_call.kwargs["node"].attributes["tags"]
            assert "context:conversation" in memorize_call.kwargs["node"].attributes["tags"]

    @pytest.mark.asyncio
    async def test_parameter_validation_error(
        self, memorize_handler: MemorizeHandler, test_thought: Thought, dispatch_context: DispatchContext
    ) -> None:
        """Test handling of invalid parameters."""
        with patch_persistence_properly() as (mock_persistence, mock_base_persistence):
            # Create result with valid structure but mock validation to fail
            result = ActionSelectionDMAResult(
                selected_action=HandlerActionType.MEMORIZE,
                action_parameters=MemorizeParams(
                    node=GraphNode(
                        id="test_validation_node",
                        type=NodeType.OBSERVATION,
                        scope=GraphScope.LOCAL,
                        attributes={"content": "test", "created_by": "test_handler", "tags": []},
                    )
                ),
                rationale="Test validation",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

            # Mock the validation method to raise an error
            with patch.object(memorize_handler, "_validate_and_convert_params") as mock_validate:
                mock_validate.side_effect = ValueError("Invalid node type")

                # Execute handler - should handle validation error
                follow_up_id = await memorize_handler.handle(result, test_thought, dispatch_context)

                # Verify thought was marked as failed
                mock_base_persistence.update_thought_status.assert_called_with(
                    thought_id="thought_123", status=ThoughtStatus.FAILED, final_action=result
                )

                # Verify error follow-up was created
                assert follow_up_id is not None
                follow_up_call = mock_base_persistence.add_thought.call_args[0][0]
                assert "MEMORIZE action failed" in follow_up_call.content

    @pytest.mark.asyncio
    async def test_memory_bus_failure(
        self,
        memorize_handler: MemorizeHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test handling when memory bus operations fail."""
        # Configure memory bus to raise exception
        mock_memory_bus.memorize.side_effect = Exception("Memory storage failed")

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler - should raise FollowUpCreationError
            from ciris_engine.logic.infrastructure.handlers.exceptions import FollowUpCreationError

            with pytest.raises(FollowUpCreationError):
                await memorize_handler.handle(action_result, test_thought, dispatch_context)

    @pytest.mark.asyncio
    async def test_duplicate_detection(
        self,
        memorize_handler: MemorizeHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test detection of duplicate memories."""
        # Configure memory bus to indicate duplicate
        mock_memory_bus.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS,
            reason="Duplicate node detected, but stored anyway",
            data={"node_id": "test_memory_node_123", "duplicate": True},
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            follow_up_id = await memorize_handler.handle(action_result, test_thought, dispatch_context)

            # Should still complete successfully
            assert mock_base_persistence.update_thought_status.called
            update_call = mock_base_persistence.update_thought_status.call_args
            assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED

            # Follow-up might indicate duplicate or just success
            assert follow_up_id is not None

    @pytest.mark.asyncio
    async def test_very_long_content(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test memorizing very long content."""
        # Create very long content
        long_content = "This is a very detailed observation. " * 100

        node = GraphNode(
            id="test_long_content_node",
            type=NodeType.OBSERVATION,
            scope=GraphScope.LOCAL,
            attributes={"content": long_content, "created_by": "test_handler", "tags": ["long_content"]},
        )
        params = MemorizeParams(node=node)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE,
            action_parameters=params,
            rationale="Test long content",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            await memorize_handler.handle(result, test_thought, dispatch_context)

            # Verify full content was passed
            memorize_call = mock_memory_bus.memorize.call_args
            assert memorize_call.kwargs["node"].attributes["content"] == long_content

    @pytest.mark.asyncio
    async def test_audit_trail(
        self,
        memorize_handler: MemorizeHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_bus_manager: Mock,
        test_task: Task,
    ) -> None:
        """Test audit logging for MEMORIZE actions."""
        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            await memorize_handler.handle(action_result, test_thought, dispatch_context)

            # Verify audit logs were created
            audit_calls = mock_bus_manager.audit_service.log_event.call_args_list
            assert len(audit_calls) >= 2  # Start and completion

            # Check start audit
            start_call = audit_calls[0]
            assert "handler_action_memorize" in str(start_call[1]["event_type"]).lower()
            assert start_call[1]["event_data"]["outcome"] == "start"

            # Check completion audit
            end_call = audit_calls[-1]
            assert end_call[1]["event_data"]["outcome"] == "success"

    @pytest.mark.skip(reason="Service correlation tracking not currently implemented in handlers")
    @pytest.mark.asyncio
    async def test_service_correlation_tracking(
        self,
        memorize_handler: MemorizeHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        test_task: Task,
    ) -> None:
        """Test service correlation tracking for telemetry."""
        # This test is skipped because correlation tracking is not currently
        # implemented in the handler flow. The base handler has the methods
        # but they are not called automatically.
        pass

    @pytest.mark.asyncio
    async def test_special_characters_in_content(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test memorizing content with special characters."""
        special_contents = [
            "Content with 'quotes' and \"double quotes\"",
            "Content with\nnewlines\nand\ttabs",
            "Content with emojis 🎉 😊 🤖",
            "Content with <html> tags & entities",
            "Content with unicode: αβγδ АБВГ 中文",
            'Content with JSON: {"key": "value"}',
        ]

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            for content in special_contents:
                # Reset mocks
                mock_memory_bus.memorize.reset_mock()

                node = GraphNode(
                    id=f"test_special_chars_node_{special_contents.index(content)}",
                    type=NodeType.OBSERVATION,
                    scope=GraphScope.LOCAL,
                    attributes={"content": content, "created_by": "test_handler", "tags": ["special_chars"]},
                )
                params = MemorizeParams(node=node)

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.MEMORIZE,
                    action_parameters=params,
                    rationale="Test special characters",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await memorize_handler.handle(result, test_thought, dispatch_context)

                # Verify content was passed unchanged
                memorize_call = mock_memory_bus.memorize.call_args
                assert memorize_call.kwargs["node"].attributes["content"] == content

    # USER NODE CONSENT HANDLING TESTS
    @pytest.mark.asyncio
    async def test_user_node_with_valid_temporary_consent(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test USER node with valid TEMPORARY consent."""
        from datetime import timedelta

        from ciris_engine.logic.services.governance.consent import ConsentService
        from ciris_engine.schemas.consent.core import ConsentStatus, ConsentStream

        # Create USER node
        node = GraphNode(
            id="user/test_user_123",
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes={
                "content": "User prefers morning meetings",
                "created_by": "test_handler",
                "tags": ["preference"],
            },
        )
        params = MemorizeParams(node=node)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE,
            action_parameters=params,
            rationale="Store user preference",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Mock consent service with valid TEMPORARY consent
        future_date = datetime.now(timezone.utc) + timedelta(days=10)
        mock_consent_status = ConsentStatus(
            user_id="test_user_123",
            stream=ConsentStream.TEMPORARY,
            categories=[],
            granted_at=datetime.now(timezone.utc),
            expires_at=future_date,
            last_modified=datetime.now(timezone.utc),
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            with patch.object(ConsentService, "__init__", return_value=None):
                with patch.object(ConsentService, "get_consent", return_value=mock_consent_status) as mock_get_consent:
                    # Execute handler
                    follow_up_id = await memorize_handler.handle(result, test_thought, dispatch_context)

                    # Verify consent was checked
                    mock_get_consent.assert_called_once_with("test_user_123")

                    # Verify memory was stored with consent metadata
                    memorize_call = mock_memory_bus.memorize.call_args
                    node_attrs = memorize_call.kwargs["node"].attributes
                    assert node_attrs["consent_stream"] == ConsentStream.TEMPORARY
                    assert node_attrs["consent_expires_at"] == future_date.isoformat()
                    assert "consent_granted_at" in node_attrs

                    # Verify thought was completed successfully
                    mock_base_persistence.update_thought_status.assert_called_with(
                        thought_id="thought_123", status=ThoughtStatus.COMPLETED, final_action=result
                    )

    @pytest.mark.asyncio
    async def test_user_node_with_expired_temporary_consent(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test USER node with expired TEMPORARY consent - should be blocked."""
        from datetime import timedelta

        from ciris_engine.logic.services.governance.consent import ConsentService
        from ciris_engine.schemas.consent.core import ConsentStatus, ConsentStream

        # Create USER node
        node = GraphNode(
            id="user/expired_user_456",
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes={
                "content": "User's expired data",
                "created_by": "test_handler",
                "tags": ["expired"],
            },
        )
        params = MemorizeParams(node=node)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE,
            action_parameters=params,
            rationale="Attempt to store expired user data",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Mock consent service with expired TEMPORARY consent
        expired_date = datetime.now(timezone.utc) - timedelta(days=1)
        mock_consent_status = ConsentStatus(
            user_id="expired_user_456",
            stream=ConsentStream.TEMPORARY,
            categories=[],
            granted_at=datetime.now(timezone.utc) - timedelta(days=15),
            expires_at=expired_date,
            last_modified=datetime.now(timezone.utc) - timedelta(days=15),
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            with patch.object(ConsentService, "__init__", return_value=None):
                with patch.object(ConsentService, "get_consent", return_value=mock_consent_status) as mock_get_consent:
                    with patch.object(ConsentService, "revoke_consent", return_value=None) as mock_revoke_consent:
                        # Execute handler
                        follow_up_id = await memorize_handler.handle(result, test_thought, dispatch_context)

                        # Verify consent was checked
                        mock_get_consent.assert_called_once_with("expired_user_456")

                        # Verify consent was revoked due to expiration
                        mock_revoke_consent.assert_called_once_with(
                            "expired_user_456", "TEMPORARY consent expired (14 days)"
                        )

                        # Verify memory was NOT stored
                        mock_memory_bus.memorize.assert_not_called()

                        # Verify thought was marked as FAILED
                        mock_base_persistence.update_thought_status.assert_called_with(
                            thought_id="thought_123", status=ThoughtStatus.FAILED, final_action=result
                        )

                        # Verify error follow-up was created
                        assert follow_up_id is not None
                        follow_up_call = mock_base_persistence.add_thought.call_args[0][0]
                        assert "MEMORIZE BLOCKED: User consent expired" in follow_up_call.content
                        assert "expired_user_456" in follow_up_call.content
                        assert "Decay protocol initiated" in follow_up_call.content

    @pytest.mark.asyncio
    async def test_user_node_without_consent_creates_default_temporary(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test USER node without consent - should create default TEMPORARY consent."""
        from datetime import timedelta

        from ciris_engine.logic.services.governance.consent import ConsentNotFoundError, ConsentService
        from ciris_engine.schemas.consent.core import ConsentRequest, ConsentStatus, ConsentStream

        # Create USER node
        node = GraphNode(
            id="user/new_user_789",
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes={
                "content": "New user's first interaction",
                "created_by": "test_handler",
                "tags": ["first_interaction"],
            },
        )
        params = MemorizeParams(node=node)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE,
            action_parameters=params,
            rationale="Store new user data",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Mock consent service to raise ConsentNotFoundError first, then return created consent
        future_date = datetime.now(timezone.utc) + timedelta(days=14)
        mock_created_consent = ConsentStatus(
            user_id="new_user_789",
            stream=ConsentStream.TEMPORARY,
            categories=[],
            granted_at=datetime.now(timezone.utc),
            expires_at=future_date,
            last_modified=datetime.now(timezone.utc),
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            with patch.object(ConsentService, "__init__", return_value=None):
                with patch.object(
                    ConsentService, "get_consent", side_effect=ConsentNotFoundError("No consent found")
                ) as mock_get_consent:
                    with patch.object(
                        ConsentService, "grant_consent", return_value=mock_created_consent
                    ) as mock_grant_consent:
                        # Execute handler
                        follow_up_id = await memorize_handler.handle(result, test_thought, dispatch_context)

                        # Verify consent was checked
                        mock_get_consent.assert_called_once_with("new_user_789")

                        # Verify default TEMPORARY consent was created
                        mock_grant_consent.assert_called_once()
                        consent_request = mock_grant_consent.call_args[0][0]
                        assert consent_request.user_id == "new_user_789"
                        assert consent_request.stream == ConsentStream.TEMPORARY
                        assert consent_request.categories == []
                        assert "Default TEMPORARY consent on first interaction" in consent_request.reason

                        # Verify memory was stored with consent metadata
                        memorize_call = mock_memory_bus.memorize.call_args
                        node_attrs = memorize_call.kwargs["node"].attributes
                        assert node_attrs["consent_stream"] == ConsentStream.TEMPORARY
                        assert "consent_expires_at" in node_attrs
                        assert "consent_granted_at" in node_attrs
                        assert "We forget about you in 14 days unless you say otherwise" in node_attrs["consent_notice"]

                        # Verify thought was completed successfully
                        mock_base_persistence.update_thought_status.assert_called_with(
                            thought_id="thought_123", status=ThoughtStatus.COMPLETED, final_action=result
                        )

    @pytest.mark.asyncio
    async def test_user_node_with_user_prefix_variant(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test USER node with user_ prefix variant."""
        from datetime import timedelta

        from ciris_engine.logic.services.governance.consent import ConsentService
        from ciris_engine.schemas.consent.core import ConsentStatus, ConsentStream

        # Create USER node with user_ prefix
        node = GraphNode(
            id="user_variant_123",
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes={
                "content": "User data with underscore prefix",
                "created_by": "test_handler",
                "tags": ["variant_test"],
            },
        )
        params = MemorizeParams(node=node)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE,
            action_parameters=params,
            rationale="Store user variant data",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Mock consent service with valid consent
        future_date = datetime.now(timezone.utc) + timedelta(days=7)
        mock_consent_status = ConsentStatus(
            user_id="variant_123",
            stream=ConsentStream.TEMPORARY,
            categories=[],
            granted_at=datetime.now(timezone.utc),
            expires_at=future_date,
            last_modified=datetime.now(timezone.utc),
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            with patch.object(ConsentService, "__init__", return_value=None):
                with patch.object(ConsentService, "get_consent", return_value=mock_consent_status) as mock_get_consent:
                    # Execute handler
                    await memorize_handler.handle(result, test_thought, dispatch_context)

                    # Verify consent was checked with correct user_id (without prefix)
                    mock_get_consent.assert_called_once_with("variant_123")

                    # Verify memory was stored
                    assert mock_memory_bus.memorize.called

    @pytest.mark.asyncio
    async def test_user_node_with_partnered_consent(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test USER node with PARTNERED consent stream."""
        from ciris_engine.logic.services.governance.consent import ConsentService
        from ciris_engine.schemas.consent.core import ConsentCategory, ConsentStatus, ConsentStream

        # Create USER node
        node = GraphNode(
            id="user/partner_user_999",
            type=NodeType.USER,
            scope=GraphScope.LOCAL,
            attributes={
                "content": "Partner user's valuable feedback",
                "created_by": "test_handler",
                "tags": ["feedback", "partnership"],
            },
        )
        params = MemorizeParams(node=node)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE,
            action_parameters=params,
            rationale="Store partner feedback",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Mock consent service with PARTNERED consent (no expiration)
        mock_consent_status = ConsentStatus(
            user_id="partner_user_999",
            stream=ConsentStream.PARTNERED,
            categories=[ConsentCategory.INTERACTION, ConsentCategory.IMPROVEMENT],
            granted_at=datetime.now(timezone.utc),
            expires_at=None,  # PARTNERED consent doesn't expire
            last_modified=datetime.now(timezone.utc),
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            with patch.object(ConsentService, "__init__", return_value=None):
                with patch.object(ConsentService, "get_consent", return_value=mock_consent_status) as mock_get_consent:
                    # Execute handler
                    await memorize_handler.handle(result, test_thought, dispatch_context)

                    # Verify consent was checked
                    mock_get_consent.assert_called_once_with("partner_user_999")

                    # Verify memory was stored with PARTNERED consent metadata
                    memorize_call = mock_memory_bus.memorize.call_args
                    node_attrs = memorize_call.kwargs["node"].attributes
                    assert node_attrs["consent_stream"] == ConsentStream.PARTNERED
                    assert node_attrs["consent_expires_at"] is None  # PARTNERED doesn't expire
                    assert "consent_granted_at" in node_attrs

                    # Verify thought was completed successfully
                    mock_base_persistence.update_thought_status.assert_called_with(
                        thought_id="thought_123", status=ThoughtStatus.COMPLETED, final_action=result
                    )

    @pytest.mark.asyncio
    async def test_non_user_node_skips_consent_check(
        self,
        memorize_handler: MemorizeHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test that non-USER nodes skip consent checking entirely."""
        from ciris_engine.logic.services.governance.consent import ConsentService

        # Create non-USER node
        node = GraphNode(
            id="system/config_node",
            type=NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={
                "key": "test_config",
                "value": {"setting": "enabled"},
                "created_by": "test_handler",
                "tags": ["system"],
            },
        )
        params = MemorizeParams(node=node)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.MEMORIZE,
            action_parameters=params,
            rationale="Store system config",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            with patch.object(ConsentService, "__init__", return_value=None) as mock_init:
                with patch.object(ConsentService, "get_consent") as mock_get_consent:
                    # Execute handler
                    await memorize_handler.handle(result, test_thought, dispatch_context)

                    # Verify ConsentService was never instantiated or called
                    mock_init.assert_not_called()
                    mock_get_consent.assert_not_called()

                    # Verify memory was stored normally
                    assert mock_memory_bus.memorize.called

                    # Verify thought was completed successfully
                    mock_base_persistence.update_thought_status.assert_called_with(
                        thought_id="thought_123", status=ThoughtStatus.COMPLETED, final_action=result
                    )
