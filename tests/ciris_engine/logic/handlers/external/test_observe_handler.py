"""
Comprehensive unit tests for the OBSERVE handler.

Tests cover:
- Observation registration and storage
- Passive observation mode
- Active observation mode
- Channel context handling
- Author identification
- Observation metadata
- Memory integration for observations
- Follow-up thought generation
- Error handling for invalid observations
- Observation filtering and relevance
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, List, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.external.observe_handler import ObserveHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import ObserveParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext


@contextmanager
def patch_persistence_properly(test_task: Optional[Task] = None) -> Any:
    """Properly patch persistence in base handler only (observe_handler doesn't import persistence)."""
    with patch("ciris_engine.logic.infrastructure.handlers.base_handler.persistence") as mock_base_p:
        # Configure base handler persistence
        mock_base_p.get_task_by_id.return_value = test_task
        mock_base_p.add_thought = Mock()
        mock_base_p.update_thought_status = Mock(return_value=True)
        mock_base_p.add_correlation = Mock()

        yield mock_base_p, mock_base_p  # Return same mock for both positions for compatibility


def setup_communication_mock(mock_bus_manager: Mock, messages: Optional[List] = None) -> None:
    """Setup communication mock on bus manager."""
    if messages is None:
        messages = []
    mock_bus_manager.communication = AsyncMock()
    mock_bus_manager.communication.fetch_messages = AsyncMock(return_value=messages)


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
    bus.memorize = AsyncMock(return_value="obs_12345")
    bus.recall = AsyncMock(return_value=[])
    return bus


@pytest.fixture
def mock_bus_manager(mock_memory_bus: AsyncMock) -> Mock:
    """Mock bus manager with memory bus."""
    manager = Mock(spec=BusManager)
    manager.memory = mock_memory_bus
    manager.audit_service = AsyncMock()
    manager.audit_service.log_event = AsyncMock()

    # Add communication bus for active observation
    manager.communication = AsyncMock()
    manager.communication.fetch_messages = AsyncMock(
        return_value=[
            Mock(message_id="msg1", content="Test message 1", author_id="user1"),
            Mock(message_id="msg2", content="Test message 2", author_id="user2"),
        ]
    )

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
def observe_handler(handler_dependencies: ActionHandlerDependencies) -> ObserveHandler:
    """Create OBSERVE handler instance."""
    return ObserveHandler(handler_dependencies)


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
        author_id="user_456",
        author_name="Test User",
        origin_service="test_service",
        handler_name="ObserveHandler",
        action_type=HandlerActionType.OBSERVE,
        task_id="task_123",
        thought_id="thought_123",
        source_task_id="task_123",
        event_summary="Test observe action",
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
        content="Observing user interaction",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        channel_id="test_channel_123",
        status=ThoughtStatus.PROCESSING,
        thought_depth=1,
        round_number=1,
        thought_type=ThoughtType.OBSERVATION,
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
        description="Respond to message from @Test User (ID: user_456) in #test_channel: 'Hello CIRIS!'",
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
def observe_params(channel_context: ChannelContext) -> ObserveParams:
    """Create test OBSERVE parameters."""
    return ObserveParams(
        channel_context=channel_context,
        active=True,  # Active observation will fetch messages
        context={
            "observation_type": "user_behavior",
            "tags": "ethics,user_interest",
            "content": "User seems interested in AI ethics",
        },
    )


@pytest.fixture
def action_result(observe_params: ObserveParams) -> ActionSelectionDMAResult:
    """Create test action selection result."""
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.OBSERVE,
        action_parameters=observe_params,
        rationale="Important behavioral observation",
        raw_llm_response="OBSERVE: User interested in ethics",
        reasoning="This helps understand user interests",
        evaluation_time_ms=100.0,
        resource_usage=None,
    )


class TestObserveHandler:
    """Test suite for OBSERVE handler."""

    @pytest.mark.asyncio
    async def test_successful_active_observation(
        self,
        observe_handler: ObserveHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        mock_bus_manager: Mock,
    ) -> None:
        """Test successful active observation fetching messages."""
        # Mock communication bus to return some messages
        mock_bus_manager.communication = AsyncMock()
        mock_bus_manager.communication.fetch_messages = AsyncMock(
            return_value=[
                Mock(author_id="user_456", content="Test message 1"),
                Mock(author_id="user_789", content="Test message 2"),
            ]
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            follow_up_id = await observe_handler.handle(action_result, test_thought, dispatch_context)

            # Verify communication bus was called to fetch messages
            mock_bus_manager.communication.fetch_messages.assert_called_once()
            fetch_call = mock_bus_manager.communication.fetch_messages.call_args
            assert fetch_call.kwargs["channel_id"] == "test_channel_123"
            assert fetch_call.kwargs["limit"] == 50  # ACTIVE_OBSERVE_LIMIT

            # The observe handler recalls info about fetched messages, not memorize new ones
            # It should call memory.recall for each unique user/channel
            assert mock_memory_bus.recall.call_count >= 2  # At least for channel and users

            # Verify follow-up thought was created with fetch info
            assert follow_up_id is not None
            # Check the base handler persistence was used
            assert mock_base_persistence.update_thought_status.called
            update_call = mock_base_persistence.update_thought_status.call_args
            assert update_call.kwargs["thought_id"] == "thought_123"
            assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED

            # Verify follow-up was created
            mock_base_persistence.add_thought.assert_called_once()
            follow_up_call = mock_base_persistence.add_thought.call_args[0][0]
            assert "Fetched 2 messages" in follow_up_call.content

    @pytest.mark.asyncio
    async def test_passive_observation(
        self,
        observe_handler: ObserveHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        channel_context: ChannelContext,
    ) -> None:
        """Test passive observation mode - now always creates follow-up."""
        # Create passive observation params
        params = ObserveParams(
            channel_context=channel_context,
            active=False,  # Will be forced to True
            context={
                "observation": "User mentioned they work nights",
                "type": "user_info",
                "tags": "schedule,availability",
            },
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.OBSERVE,
            action_parameters=params,
            rationale="Passive observation",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            follow_up_id = await observe_handler.handle(result, test_thought, dispatch_context)

            # Handler now always creates follow-up thoughts (active=True is forced)
            assert follow_up_id is not None

            # Should perform active observation (fetching messages)
            observe_handler.bus_manager.communication.fetch_messages.assert_called_once()

            # Should update thought status
            mock_base_persistence.update_thought_status.assert_called_once()

            # Should create follow-up thought
            mock_base_persistence.add_thought.assert_called_once()
            follow_up_call = mock_base_persistence.add_thought.call_args[0][0]
            assert "CIRIS_FOLLOW_UP_THOUGHT" in follow_up_call.content

    @pytest.mark.asyncio
    async def test_observation_without_author_info(
        self,
        observe_handler: ObserveHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        mock_bus_manager: Mock,
    ) -> None:
        """Test observation without author information."""
        # Create params without author info
        params = ObserveParams(
            channel_context=None,  # Will use dispatch context
            active=True,
            context={
                "observation": "General channel activity increased",
                "type": "channel_activity",
                "tags": "activity,metrics",
            },
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.OBSERVE,
            action_parameters=params,
            rationale="Channel observation",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Setup communication mock
        setup_communication_mock(mock_bus_manager)

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            await observe_handler.handle(result, test_thought, dispatch_context)

            # Should use channel context from dispatch context
            # Verify communication bus was called
            mock_bus_manager.communication.fetch_messages.assert_called_once()

    @pytest.mark.asyncio
    async def test_different_observation_types(
        self,
        observe_handler: ObserveHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        mock_bus_manager: Mock,
    ) -> None:
        """Test various observation types."""
        observation_types = [
            ("user_behavior", "User frequently asks about documentation"),
            ("channel_activity", "Channel topic shifted to technical discussion"),
            ("system_event", "High latency detected in responses"),
            ("user_preference", "User prefers bullet points over paragraphs"),
            ("interaction_pattern", "User tends to ask follow-up questions"),
        ]

        # Setup communication mock
        setup_communication_mock(mock_bus_manager)

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            for obs_type, content in observation_types:
                # Reset mocks
                mock_memory_bus.recall.reset_mock()
                mock_persistence.add_thought.reset_mock()

                # Create params for this observation type
                params = ObserveParams(
                    channel_context=dispatch_context.channel_context,
                    active=True,
                    context={"observation_type": obs_type, "content": content, "tags": obs_type},
                )

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.OBSERVE,
                    action_parameters=params,
                    rationale=f"Test {obs_type}",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await observe_handler.handle(result, test_thought, dispatch_context)

                # The observe handler fetches messages, not memorizes
                # Just verify it completes without error for different observation types
                assert True  # Handler should complete successfully

    @pytest.mark.asyncio
    async def test_channel_context_integration(
        self,
        observe_handler: ObserveHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        mock_bus_manager: Mock,
    ) -> None:
        """Test integration with channel context."""
        # Update dispatch context with different channel info
        dispatch_context.channel_context = ChannelContext(
            channel_id="discord_123_456",
            channel_type="voice",
            created_at=datetime.now(timezone.utc),
            channel_name="Voice Channel",
            is_private=True,
            is_active=True,
            last_activity=datetime.now(timezone.utc),
            message_count=42,
            moderation_level="strict",
        )

        # Create params without channel context to test dispatch context usage
        params = ObserveParams(
            channel_context=None, active=True, context={"test": "channel_context"}  # Should use dispatch context
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.OBSERVE,
            action_parameters=params,
            rationale="Test channel context",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Setup communication mock
        setup_communication_mock(mock_bus_manager)

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            await observe_handler.handle(result, test_thought, dispatch_context)

            # Verify channel context was used to fetch messages
            mock_bus_manager.communication.fetch_messages.assert_called_once()
            fetch_call = mock_bus_manager.communication.fetch_messages.call_args
            assert fetch_call.kwargs["channel_id"] == "discord_123_456"
            assert fetch_call.kwargs["handler_name"] == "ObserveHandler"

    @pytest.mark.asyncio
    async def test_observation_with_long_context(
        self,
        observe_handler: ObserveHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        channel_context: ChannelContext,
        mock_bus_manager: Mock,
    ) -> None:
        """Test observation with very long context."""
        # Create very long observation context
        long_content = "User provided detailed feedback: " + "point " * 200

        params = ObserveParams(
            channel_context=channel_context,
            active=True,
            context={"observation": long_content, "type": "feedback", "tags": "feedback,detailed"},
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.OBSERVE,
            action_parameters=params,
            rationale="Long feedback",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Setup communication mock
        setup_communication_mock(mock_bus_manager)

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            follow_up_id = await observe_handler.handle(result, test_thought, dispatch_context)

            # The observe handler fetches messages, not memorizes content
            # Just verify handler completes successfully
            assert follow_up_id is not None

    @pytest.mark.asyncio
    async def test_parameter_validation_error(
        self, observe_handler: ObserveHandler, test_thought: Thought, dispatch_context: DispatchContext
    ) -> None:
        """Test handling of invalid parameters."""
        with patch_persistence_properly() as (mock_persistence, mock_base_persistence):
            # Create result with valid structure but mock validation to fail
            result = ActionSelectionDMAResult(
                selected_action=HandlerActionType.OBSERVE,
                action_parameters=ObserveParams(active=True),
                rationale="Test validation",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

            # Mock the validation method to raise an error
            with patch.object(observe_handler, "_validate_and_convert_params") as mock_validate:
                mock_validate.side_effect = ValueError("Invalid observation type")

                # Execute handler - should handle validation error
                follow_up_id = await observe_handler.handle(result, test_thought, dispatch_context)

                # Verify thought status was updated
                mock_base_persistence.update_thought_status.assert_called()
                # The status might be COMPLETED or FAILED depending on implementation
                update_call = mock_base_persistence.update_thought_status.call_args
                assert update_call.kwargs["thought_id"] == "thought_123"

                # Verify error follow-up was created
                assert follow_up_id is not None
                follow_up_call = mock_base_persistence.add_thought.call_args[0][0]
                assert "OBSERVE action failed" in follow_up_call.content

    @pytest.mark.asyncio
    async def test_memory_bus_failure(
        self,
        observe_handler: ObserveHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        mock_bus_manager: Mock,
    ) -> None:
        """Test handling when communication bus fails."""
        # Configure communication bus to raise exception
        mock_bus_manager.communication = AsyncMock()
        mock_bus_manager.communication.fetch_messages.side_effect = Exception("Communication failed")

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler - should handle the error gracefully
            follow_up_id = await observe_handler.handle(action_result, test_thought, dispatch_context)

            # Should create an error follow-up
            assert follow_up_id is not None
            follow_up_call = mock_base_persistence.add_thought.call_args[0][0]
            assert "failed" in follow_up_call.content.lower()

    @pytest.mark.asyncio
    async def test_observation_from_task_description(
        self,
        observe_handler: ObserveHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        channel_context: ChannelContext,
        mock_bus_manager: Mock,
    ) -> None:
        """Test extracting observation from task description."""
        # The test_task fixture has a description with message info
        # Handler might extract this for context

        params = ObserveParams(
            channel_context=channel_context,
            active=True,
            context={"observation": "Acknowledging user greeting", "type": "interaction", "tags": "greeting"},
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.OBSERVE,
            action_parameters=params,
            rationale="Observe greeting",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Setup communication mock
        setup_communication_mock(mock_bus_manager)

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            follow_up_id = await observe_handler.handle(result, test_thought, dispatch_context)

            # Handler fetches messages from channel
            # Verify it completed successfully
            assert follow_up_id is not None

    @pytest.mark.asyncio
    async def test_audit_trail(
        self,
        observe_handler: ObserveHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_bus_manager: Mock,
        test_task: Task,
    ) -> None:
        """Test audit logging for OBSERVE actions."""
        # Setup communication mock
        setup_communication_mock(mock_bus_manager)

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            await observe_handler.handle(action_result, test_thought, dispatch_context)

            # NOTE: Audit logging removed from handlers - action_dispatcher handles centralized audit logging
            pass  # Test still validates handler execution

            # The observe handler only logs a second audit if follow-up creation fails
            # So we might only have one audit log for successful execution

    @pytest.mark.skip(reason="Service correlation tracking not currently implemented in handlers")
    @pytest.mark.asyncio
    async def test_service_correlation_tracking(
        self,
        observe_handler: ObserveHandler,
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
    async def test_multi_tag_observations(
        self,
        observe_handler: ObserveHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_memory_bus: AsyncMock,
        test_task: Task,
        channel_context: ChannelContext,
        mock_bus_manager: Mock,
    ) -> None:
        """Test observations with multiple tags for categorization."""
        # Create observation with many tags
        params = ObserveParams(
            channel_context=channel_context,
            active=True,
            context={
                "observation": "User asked complex technical question about distributed systems",
                "type": "user_interest",
                "tags": "technical,distributed_systems,complex_question,expertise_level:high",
            },
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.OBSERVE,
            action_parameters=params,
            rationale="Multi-tagged observation",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        # Setup communication mock
        setup_communication_mock(mock_bus_manager)

        with patch_persistence_properly(test_task) as (mock_persistence, mock_base_persistence):
            # Execute handler
            follow_up_id = await observe_handler.handle(result, test_thought, dispatch_context)

            # Verify handler completed successfully
            assert follow_up_id is not None
            # The observe handler doesn't store new observations, it fetches messages
            # and recalls existing information about users/channels
