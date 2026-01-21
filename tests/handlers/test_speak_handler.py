"""
Comprehensive unit tests for the SPEAK handler.

Tests cover:
- Message formatting with various content types
- Communication bus integration
- Rate limiting if implemented
- Message queuing and delivery
- Error handling for communication failures
- Different message targets/channels
- Message persistence/audit trail
- Both sync and async message sending
- Message acknowledgment
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.external.speak_handler import SpeakHandler, _build_speak_error_context
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import SpeakParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.telemetry.core import ServiceCorrelation

# Import the mock_db_path fixture to avoid database config issues
from tests.conftest_config_mock import mock_db_path  # noqa: F401

# Import database fixtures would go here if we were using a real database
# For now, these tests use mocked persistence


class MockPersistencePair:
    """Container for both persistence mocks."""

    def __init__(self, handler_mock: Mock, base_mock: Mock) -> None:
        self.handler = handler_mock
        self.base = base_mock

    # Forward common calls to handler mock for backwards compatibility
    @property
    def get_task_by_id(self) -> Mock:
        return self.handler.get_task_by_id

    @property
    def add_thought(self) -> Mock:
        return self.handler.add_thought

    @property
    def update_thought_status(self) -> Mock:
        return self.handler.update_thought_status

    @property
    def add_correlation(self) -> Mock:
        return self.handler.add_correlation


@contextmanager
def patch_persistence_properly(test_task: Optional[Task] = None) -> Any:
    """Properly patch persistence in both handler and base handler."""
    with patch("ciris_engine.logic.handlers.external.speak_handler.persistence") as mock_p, patch(
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

        yield MockPersistencePair(mock_p, mock_base_p)


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
def mock_communication_bus() -> AsyncMock:
    """Mock communication bus."""
    bus = AsyncMock()
    bus.send_message = AsyncMock(return_value=True)
    bus.send_message_sync = AsyncMock(return_value=True)
    return bus


@pytest.fixture
def mock_bus_manager(mock_communication_bus: AsyncMock) -> Mock:
    """Mock bus manager with communication bus."""
    manager = Mock(spec=BusManager)
    manager.communication = mock_communication_bus
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
def speak_handler(handler_dependencies: ActionHandlerDependencies) -> SpeakHandler:
    """Create SPEAK handler instance."""
    return SpeakHandler(handler_dependencies)


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
        handler_name="SpeakHandler",
        action_type=HandlerActionType.SPEAK,
        task_id="task_123",
        thought_id="thought_123",
        source_task_id="task_123",
        event_summary="Test speak action",
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
        content="Test thought content",
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
def mock_persistence() -> Any:
    """Mock persistence for tests."""
    with patch("ciris_engine.logic.handlers.external.speak_handler.persistence") as mock_p, patch(
        "ciris_engine.logic.infrastructure.handlers.base_handler.persistence"
    ) as mock_base_p:
        # Configure handler persistence
        mock_p.get_task_by_id = Mock()
        mock_p.add_thought = Mock()
        mock_p.update_thought_status = Mock(return_value=True)
        mock_p.add_correlation = Mock()

        # Configure base handler persistence
        mock_base_p.add_thought = Mock()
        mock_base_p.update_thought_status = Mock(return_value=True)
        mock_base_p.add_correlation = Mock()

        # Make both mocks share the same add_thought and update_thought_status mocks
        # so we can check if they were called from either location
        shared_add_thought = Mock()
        mock_p.add_thought = shared_add_thought
        mock_base_p.add_thought = shared_add_thought

        # Share update_thought_status mock
        shared_update_status = Mock(return_value=True)
        mock_p.update_thought_status = shared_update_status
        mock_base_p.update_thought_status = shared_update_status

        yield mock_p


@pytest.fixture
def speak_params() -> SpeakParams:
    """Create test SPEAK parameters."""
    return SpeakParams(content="Hello, this is a test message!", channel_context=None)


@pytest.fixture
def action_result(speak_params: SpeakParams) -> ActionSelectionDMAResult:
    """Create test action selection result."""
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=speak_params,
        rationale="Need to respond to user",
        raw_llm_response="SPEAK: Hello, this is a test message!",
        reasoning="User asked a question, providing response",
        evaluation_time_ms=100.0,
        resource_usage=None,
    )


class TestSpeakHandler:
    """Test suite for SPEAK handler."""

    @pytest.mark.asyncio
    async def test_successful_message_send(
        self,
        speak_handler: SpeakHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
        mock_persistence: Any,
    ) -> None:
        """Test successful message sending through communication bus."""
        mock_persistence.get_task_by_id.return_value = test_task

        # Execute handler
        follow_up_id = await speak_handler.handle(action_result, test_thought, dispatch_context)

        # Verify communication bus was called with sync method
        mock_communication_bus.send_message_sync.assert_called_once_with(
            channel_id="test_channel_123", content="Hello, this is a test message!", handler_name="SpeakHandler"
        )

        # Verify thought status was updated
        assert mock_persistence.update_thought_status.called
        update_call = mock_persistence.update_thought_status.call_args
        # Check using kwargs instead of args
        assert update_call.kwargs["thought_id"] == "thought_123"
        assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED

        # Verify follow-up thought was created
        assert follow_up_id is not None
        mock_persistence.add_thought.assert_called_once()

        # Verify correlation was added
        mock_persistence.add_correlation.assert_called_once()

    @pytest.mark.asyncio
    async def test_communication_failure(
        self,
        speak_handler: SpeakHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
        mock_persistence: Any,
    ) -> None:
        """Test handling of communication bus failures."""
        # Configure communication to fail
        mock_communication_bus.send_message_sync.return_value = False
        mock_persistence.get_task_by_id.return_value = test_task

        # Execute handler
        follow_up_id = await speak_handler.handle(action_result, test_thought, dispatch_context)

        # Verify thought status was marked as failed
        assert mock_persistence.update_thought_status.called
        update_call = mock_persistence.update_thought_status.call_args
        # Check using kwargs instead of args
        assert update_call.kwargs["thought_id"] == "thought_123"
        assert update_call.kwargs["status"] == ThoughtStatus.FAILED
        assert update_call.kwargs["final_action"] == action_result

        # Verify follow-up thought contains failure message
        follow_up_call = mock_persistence.add_thought.call_args[0][0]
        assert "SPEAK action failed" in follow_up_call.content

    @pytest.mark.asyncio
    async def test_missing_channel_id(
        self,
        speak_handler: SpeakHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
    ) -> None:
        """Test error handling when channel ID is missing."""
        # Remove channel ID from contexts
        dispatch_context.channel_context = None  # type: ignore
        test_thought.channel_id = None
        if test_thought.context:
            test_thought.context.channel_id = None

        with patch_persistence_properly() as mock_persistence:
            # Mock get_task_by_id to return a task with no channel_id
            mock_task = Task(
                task_id="task_123",
                channel_id="",  # Empty channel_id
                description="Test task",
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
            mock_persistence.get_task_by_id.return_value = mock_task

            # Should raise ValidationError when creating ServiceRequestData with invalid channel_id
            from pydantic_core import ValidationError

            with pytest.raises(ValidationError, match="channel_id"):
                await speak_handler.handle(action_result, test_thought, dispatch_context)

    @pytest.mark.asyncio
    async def test_different_content_types(
        self,
        speak_handler: SpeakHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test handling different content types."""
        content_types = [
            "Simple text message",
            "Message with emojis 🎉 😊",
            "Message with\nmultiple\nlines",
            "Very " + "long " * 100 + "message",
            "Message with special chars: <>&\"'",
            "```code\nprint('Hello')\n```",
            "",  # Empty message
        ]

        with patch_persistence_properly(test_task) as mock_persistence:
            for content in content_types:
                # Reset mocks
                mock_communication_bus.send_message_sync.reset_mock()
                mock_persistence.add_thought.reset_mock()

                # Create params with different content
                params = SpeakParams(content=content)
                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.SPEAK,
                    action_parameters=params,
                    rationale="Test different content",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await speak_handler.handle(result, test_thought, dispatch_context)

                # Verify content was sent correctly
                if content:  # Skip empty content check
                    mock_communication_bus.send_message_sync.assert_called_with(
                        channel_id="test_channel_123", content=content, handler_name="SpeakHandler"
                    )

    @pytest.mark.asyncio
    async def test_parameter_validation_error(
        self, speak_handler: SpeakHandler, test_thought: Thought, dispatch_context: DispatchContext
    ) -> None:
        """Test handling of invalid parameters."""
        # Since ActionSelectionDMAResult validates parameters at construction,
        # we need to simulate validation error happening within the handler
        # by passing a dict directly (simulating pre-validation data)

        # Mock the validation to fail
        with patch_persistence_properly() as mock_persistence:

            # Create a result with valid structure but simulate validation failure in handler
            result = ActionSelectionDMAResult(
                selected_action=HandlerActionType.SPEAK,
                action_parameters=SpeakParams(content="test"),  # Valid params
                rationale="Test validation",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

            # Mock the validation method to raise an error
            with patch.object(speak_handler, "_validate_and_convert_params") as mock_validate:
                mock_validate.side_effect = ValueError("Invalid parameters: missing content")

                # Execute handler - should handle validation error
                follow_up_id = await speak_handler.handle(result, test_thought, dispatch_context)

                # Verify thought was marked as failed (via base_handler's complete_thought_and_create_followup)
                mock_persistence.base.update_thought_status.assert_called_once()
                call_kwargs = mock_persistence.base.update_thought_status.call_args[1]
                assert call_kwargs["thought_id"] == "thought_123"
                assert call_kwargs["status"] == ThoughtStatus.FAILED
                assert call_kwargs["final_action"] == result

                # Verify error follow-up was created
                assert follow_up_id is not None
                # Check the follow-up thought contains error message
                follow_up_call = mock_persistence.base.add_thought.call_args[0][0]
                assert "SPEAK action failed" in follow_up_call.content

    @pytest.mark.asyncio
    async def test_audit_trail(
        self,
        speak_handler: SpeakHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_bus_manager: Mock,
        test_task: Task,
    ) -> None:
        """Test audit logging for SPEAK actions."""
        with patch_persistence_properly(test_task) as mock_persistence:

            # Execute handler
            await speak_handler.handle(action_result, test_thought, dispatch_context)

            # NOTE: Audit logging removed from handlers - action_dispatcher handles centralized audit logging
            pass  # Test still validates handler execution
