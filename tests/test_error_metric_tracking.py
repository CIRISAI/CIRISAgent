"""
Unit tests for error metric tracking in handlers.
"""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies, BaseActionHandler
from ciris_engine.schemas.runtime.contexts import ChannelContext, DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType


@pytest.fixture
def handler_setup():
    """Set up test fixtures for handler tests."""
    # Create mock dependencies
    mock_bus_manager = MagicMock()
    mock_memory_bus = AsyncMock()
    mock_bus_manager.memory_bus = mock_memory_bus

    mock_time_service = MagicMock()
    mock_time_service.now.return_value = datetime(2025, 1, 16, 12, 0, 0)

    dependencies = ActionHandlerDependencies(
        bus_manager=mock_bus_manager,
        time_service=mock_time_service,
    )

    # Create a test handler class
    class TestHandler(BaseActionHandler):
        async def handle(self, result, thought, dispatch_context):
            """Implement abstract handle method for testing."""
            return None

    handler = TestHandler(dependencies)

    return handler, mock_memory_bus, mock_time_service


def create_test_dispatch_context(thought_id="test_thought_123"):
    """Create a valid DispatchContext for testing."""
    return DispatchContext(
        channel_context=ChannelContext(
            channel_id="test_channel",
            channel_type="test",
            created_at=datetime(2025, 1, 16, 12, 0, 0),
            channel_name="test_channel_name",
            is_private=False,
        ),
        author_id="test_user",
        author_name="Test User",
        origin_service="test_service",
        handler_name="TestHandler",
        action_type=HandlerActionType.SPEAK,
        thought_id=thought_id,
        task_id="test_task_456",
        source_task_id="test_source_task",
        event_summary="Test event",
        event_timestamp="2025-01-16T12:00:00Z",  # ISO8601 string
        wa_authorized=False,
        # Only include fields that exist in the schema
        correlation_id="test_correlation",
        span_id="test_span",
        trace_id="test_trace",
    )


@pytest.mark.asyncio
async def test_handle_error_tracks_metric(handler_setup):
    """Test that _handle_error tracks error.occurred metric."""
    handler, mock_memory_bus, mock_time_service = handler_setup

    # Create test context
    dispatch_context = create_test_dispatch_context(thought_id="test_thought_123")

    # Create test error
    test_error = ValueError("Test error message")

    # Mock audit log to prevent actual logging
    with patch.object(handler, "_audit_log", new_callable=AsyncMock):
        # Call _handle_error
        await handler._handle_error(
            action_type=HandlerActionType.SPEAK,
            dispatch_context=dispatch_context,
            thought_id="test_thought_123",
            error=test_error,
        )

    # Verify memorize_metric was called
    mock_memory_bus.memorize_metric.assert_called_once()

    # Verify the metric details
    call_args = mock_memory_bus.memorize_metric.call_args
    assert call_args.kwargs["metric_name"] == "error.occurred"
    assert call_args.kwargs["value"] == 1.0

    # Verify tags
    tags = call_args.kwargs["tags"]
    assert tags["handler"] == "TestHandler"
    assert tags["action_type"] == "speak"  # Enum value is lowercase
    assert tags["error_type"] == "ValueError"
    assert tags["thought_id"] == "test_thought_123"

    # Verify timestamp
    assert call_args.kwargs["timestamp"] == datetime(2025, 1, 16, 12, 0, 0)


@pytest.mark.asyncio
async def test_handle_error_continues_on_metric_failure(handler_setup):
    """Test that _handle_error continues even if metric tracking fails."""
    handler, mock_memory_bus, mock_time_service = handler_setup

    # Make memorize_metric raise an exception
    mock_memory_bus.memorize_metric.side_effect = Exception("Metric tracking failed")

    dispatch_context = create_test_dispatch_context(thought_id="test_thought_456")

    test_error = RuntimeError("Test runtime error")

    # Mock audit log
    with patch.object(handler, "_audit_log", new_callable=AsyncMock) as mock_audit:
        # Should not raise despite metric failure
        await handler._handle_error(
            action_type=HandlerActionType.TOOL,
            dispatch_context=dispatch_context,
            thought_id="test_thought_456",
            error=test_error,
        )

        # Audit log should still be called
        mock_audit.assert_called_once()


@pytest.mark.asyncio
async def test_handle_error_without_memory_bus(handler_setup):
    """Test that _handle_error works without memory bus."""
    handler, mock_memory_bus, mock_time_service = handler_setup

    # Remove memory bus
    handler.bus_manager = MagicMock()
    del handler.bus_manager.memory_bus

    dispatch_context = create_test_dispatch_context(thought_id="test_thought_789")

    test_error = TypeError("Test type error")

    # Mock audit log
    with patch.object(handler, "_audit_log", new_callable=AsyncMock) as mock_audit:
        # Should work without memory bus
        await handler._handle_error(
            action_type=HandlerActionType.MEMORIZE,
            dispatch_context=dispatch_context,
            thought_id="test_thought_789",
            error=test_error,
        )

        # Audit log should still be called
        mock_audit.assert_called_once()

        # Memory bus method should not have been called (it was removed)
        # No assertion needed since the bus was deleted


@pytest.mark.asyncio
async def test_handle_error_with_different_action_types(handler_setup):
    """Test error tracking with different action types."""
    handler, mock_memory_bus, mock_time_service = handler_setup

    action_types = [
        HandlerActionType.SPEAK,
        HandlerActionType.TOOL,
        HandlerActionType.MEMORIZE,
        HandlerActionType.TASK_COMPLETE,
    ]

    for action_type in action_types:
        # Reset mock
        mock_memory_bus.reset_mock()

        dispatch_context = create_test_dispatch_context(thought_id=f"thought_{action_type.value}")
        test_error = Exception(f"Test error for {action_type.value}")

        with patch.object(handler, "_audit_log", new_callable=AsyncMock):
            await handler._handle_error(
                action_type=action_type,
                dispatch_context=dispatch_context,
                thought_id=f"thought_{action_type.value}",
                error=test_error,
            )

        # Verify metric was tracked for each action type
        mock_memory_bus.memorize_metric.assert_called_once()
        call_args = mock_memory_bus.memorize_metric.call_args
        assert call_args.kwargs["tags"]["action_type"] == action_type.value


@pytest.mark.asyncio
async def test_handle_error_with_different_error_types(handler_setup):
    """Test error tracking with different error types."""
    handler, mock_memory_bus, mock_time_service = handler_setup

    error_types = [
        ValueError("Value error test"),
        TypeError("Type error test"),
        RuntimeError("Runtime error test"),
        KeyError("Key error test"),
        AttributeError("Attribute error test"),
    ]

    for error in error_types:
        # Reset mock
        mock_memory_bus.reset_mock()

        dispatch_context = create_test_dispatch_context(thought_id=f"thought_{type(error).__name__}")

        with patch.object(handler, "_audit_log", new_callable=AsyncMock):
            await handler._handle_error(
                action_type=HandlerActionType.SPEAK,
                dispatch_context=dispatch_context,
                thought_id=f"thought_{type(error).__name__}",
                error=error,
            )

        # Verify metric was tracked with correct error type
        mock_memory_bus.memorize_metric.assert_called_once()
        call_args = mock_memory_bus.memorize_metric.call_args
        assert call_args.kwargs["tags"]["error_type"] == type(error).__name__
