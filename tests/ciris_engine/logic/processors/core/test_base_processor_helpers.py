"""Unit tests for BaseProcessor helper methods."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.core.base_processor import BaseProcessor
from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor


class ConcreteProcessor(BaseProcessor):
    """Concrete implementation of BaseProcessor for testing."""

    def get_supported_states(self):
        """Return empty list - not testing state support."""
        return []

    async def can_process(self, state):
        """Return True - not testing state processing."""
        return True

    async def process(self, round_number: int):
        """Return empty dict - not testing processing logic."""
        from ciris_engine.schemas.processors.results import ProcessingResult

        return ProcessingResult(success=True, round_number=round_number)


@pytest.fixture
def base_processor(mock_time_service, mock_services):
    """Create a ConcreteProcessor instance for testing BaseProcessor methods."""
    config = Mock(spec=ConfigAccessor)
    thought_processor = Mock(spec=ThoughtProcessor)
    action_dispatcher = Mock()

    processor = ConcreteProcessor(
        config_accessor=config,
        thought_processor=thought_processor,
        action_dispatcher=action_dispatcher,
        services=mock_services,
    )

    return processor


@pytest.fixture
def dispatch_context():
    """Create a valid DispatchContext for testing."""
    from datetime import datetime, timezone

    from ciris_engine.schemas.runtime.contexts import ChannelContext, DispatchContext
    from ciris_engine.schemas.runtime.enums import HandlerActionType

    channel_ctx = ChannelContext(
        channel_id="test_channel_123",
        channel_name="test-channel",
        channel_type="text",
        created_at=datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
    )

    return DispatchContext(
        channel_context=channel_ctx,
        author_id="user_123",
        author_name="TestUser",
        origin_service="test_service",
        handler_name="test_handler",
        action_type=HandlerActionType.SPEAK,
        thought_id="thought_123",
        task_id="task_123",
        source_task_id="task_123",
        event_summary="Test event",
        event_timestamp="2024-01-01T12:00:00Z",
    )


class TestGetTimeService:
    """Test _get_time_service helper method."""

    def test_get_time_service_from_time_service_attribute(self, base_processor):
        """Test getting time service from time_service attribute."""
        result = base_processor._get_time_service()
        assert result is base_processor.time_service

    def test_get_time_service_from_private_attribute(self, base_processor, mock_time_service):
        """Test getting time service from _time_service attribute (fallback)."""
        # Remove time_service, add _time_service
        delattr(base_processor, "time_service")
        base_processor._time_service = mock_time_service

        result = base_processor._get_time_service()
        assert result is mock_time_service

    def test_get_time_service_returns_none_when_missing(self, base_processor):
        """Test that _get_time_service returns None when no time service exists."""
        # Remove both attributes
        delattr(base_processor, "time_service")

        result = base_processor._get_time_service()
        assert result is None


class TestCalculateDispatchTime:
    """Test _calculate_dispatch_time helper method."""

    def test_calculate_dispatch_time_with_valid_timestamps(self, base_processor):
        """Test calculating dispatch time with valid start and end times."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)  # 5 seconds later

        result = base_processor._calculate_dispatch_time(start, end)

        assert isinstance(result, float)
        assert result == 5000.0  # 5 seconds = 5000 milliseconds

    def test_calculate_dispatch_time_with_milliseconds(self, base_processor):
        """Test calculating dispatch time with sub-second precision."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        end = start + timedelta(milliseconds=150)

        result = base_processor._calculate_dispatch_time(start, end)

        assert isinstance(result, float)
        assert result == 150.0

    def test_calculate_dispatch_time_with_none_start(self, base_processor):
        """Test that _calculate_dispatch_time returns 0.0 when start is None."""
        end = datetime(2024, 1, 1, 12, 0, 5, tzinfo=timezone.utc)

        result = base_processor._calculate_dispatch_time(None, end)

        assert result == 0.0

    def test_calculate_dispatch_time_with_none_end(self, base_processor):
        """Test that _calculate_dispatch_time returns 0.0 when end is None."""
        start = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        result = base_processor._calculate_dispatch_time(start, None)

        assert result == 0.0

    def test_calculate_dispatch_time_with_both_none(self, base_processor):
        """Test that _calculate_dispatch_time returns 0.0 when both are None."""
        result = base_processor._calculate_dispatch_time(None, None)

        assert result == 0.0


class TestExtractActionName:
    """Test _extract_action_name helper method."""

    def test_extract_action_name_from_dict_result(self, base_processor):
        """Test extracting action name from dict dispatch result."""
        dispatch_result = {"action_type": "SPEAK", "success": True}
        action_selection_result = Mock()

        result = base_processor._extract_action_name(dispatch_result, action_selection_result)

        assert result == "SPEAK"

    def test_extract_action_name_from_dict_with_missing_key(self, base_processor):
        """Test extracting action name from dict without action_type key."""
        dispatch_result = {"success": True}  # No action_type
        action_selection_result = Mock()

        result = base_processor._extract_action_name(dispatch_result, action_selection_result)

        assert result == "UNKNOWN"

    def test_extract_action_name_from_conscience_result(self, base_processor):
        """Test extracting action name from ConscienceApplicationResult."""
        dispatch_result = Mock()  # Not a dict
        action_selection_result = Mock()
        # Configure Mock to not have __getitem__ (so isinstance(dict) is False)
        action_selection_result.__class__ = Mock
        action_selection_result.final_action = Mock()
        action_selection_result.final_action.selected_action = "RECALL"

        result = base_processor._extract_action_name(dispatch_result, action_selection_result)

        assert result == "RECALL"

    def test_extract_action_name_from_dma_result(self, base_processor):
        """Test extracting action name from ActionSelectionDMAResult directly."""
        dispatch_result = Mock()  # Not a dict
        action_selection_result = Mock()
        action_selection_result.__class__ = Mock
        # No final_action attribute (will raise AttributeError)
        del action_selection_result.final_action
        action_selection_result.selected_action = "MEMORIZE"

        result = base_processor._extract_action_name(dispatch_result, action_selection_result)

        assert result == "MEMORIZE"

    def test_extract_action_name_fallback_to_unknown(self, base_processor):
        """Test that _extract_action_name returns UNKNOWN when all extraction fails."""
        dispatch_result = Mock()  # Not a dict
        action_selection_result = Mock(spec=[])  # Empty spec - no attributes
        action_selection_result.__class__ = Mock

        result = base_processor._extract_action_name(dispatch_result, action_selection_result)

        assert result == "UNKNOWN"


class TestStreamPerformActionStep:
    """Test _stream_perform_action_step helper method."""

    @pytest.mark.asyncio
    async def test_stream_perform_action_when_streaming_enabled(
        self, base_processor, mock_time_service, dispatch_context
    ):
        """Test streaming PERFORM_ACTION step when _stream_step_point is available."""
        # Add _stream_step_point method
        base_processor._stream_step_point = AsyncMock()

        result_mock = Mock()
        result_mock.selected_action = "SPEAK"
        result_mock.action_parameters = {"text": "Hello"}

        thought_mock = Mock()
        thought_mock.thought_id = "thought_123"

        await base_processor._stream_perform_action_step(result_mock, thought_mock, dispatch_context)

        # Verify _stream_step_point was called
        base_processor._stream_step_point.assert_called_once()
        call_args = base_processor._stream_step_point.call_args

        # Check StepPoint enum
        from ciris_engine.schemas.services.runtime_control import StepPoint

        assert call_args[0][0] == StepPoint.PERFORM_ACTION
        assert call_args[0][1] == "thought_123"

        # Check step data
        step_data = call_args[0][2]
        assert step_data["thought_id"] == "thought_123"
        assert step_data["selected_action"] == "SPEAK"
        assert "timestamp" in step_data

    @pytest.mark.asyncio
    async def test_stream_perform_action_when_streaming_disabled(self, base_processor, dispatch_context):
        """Test that _stream_perform_action_step does nothing when streaming not available."""
        # No _stream_step_point attribute
        result_mock = Mock()
        thought_mock = Mock()
        thought_mock.thought_id = "thought_123"

        # Should not raise, just return early
        await base_processor._stream_perform_action_step(result_mock, thought_mock, dispatch_context)

    @pytest.mark.asyncio
    async def test_stream_perform_action_with_missing_time_service(self, base_processor, dispatch_context):
        """Test streaming when time service is not available."""
        base_processor._stream_step_point = AsyncMock()
        delattr(base_processor, "time_service")

        result_mock = Mock()
        result_mock.selected_action = "SPEAK"

        thought_mock = Mock()
        thought_mock.thought_id = "thought_123"

        await base_processor._stream_perform_action_step(result_mock, thought_mock, dispatch_context)

        # Should still call _stream_step_point with None timestamp
        base_processor._stream_step_point.assert_called_once()
        step_data = base_processor._stream_step_point.call_args[0][2]
        assert step_data["timestamp"] is None


class TestDispatchActionIntegration:
    """Integration tests for dispatch_action using helper methods."""

    @pytest.mark.asyncio
    async def test_dispatch_action_success_flow(self, base_processor, mock_time_service, dispatch_context):
        """Test successful dispatch_action flow using all helper methods."""
        # Set up action dispatcher
        base_processor.action_dispatcher.dispatch = AsyncMock(return_value={"action_type": "SPEAK", "success": True})

        result_mock = Mock()
        result_mock.selected_action = "SPEAK"

        thought_mock = Mock()
        thought_mock.thought_id = "thought_123"

        # Pass dispatch_context as dict (will be converted to DispatchContext inside dispatch_action)
        context = dispatch_context.model_dump()

        success = await base_processor.dispatch_action(result_mock, thought_mock, context)

        assert success is True
        base_processor.action_dispatcher.dispatch.assert_called_once()

    @pytest.mark.asyncio
    async def test_dispatch_action_with_none_result(self, base_processor, mock_time_service, dispatch_context):
        """Test dispatch_action when dispatcher returns None."""
        base_processor.action_dispatcher.dispatch = AsyncMock(return_value=None)

        result_mock = Mock()
        thought_mock = Mock()
        thought_mock.thought_id = "thought_123"

        context = dispatch_context.model_dump()

        success = await base_processor.dispatch_action(result_mock, thought_mock, context)

        assert success is True

    @pytest.mark.asyncio
    async def test_dispatch_action_handles_exception(self, base_processor, mock_time_service, dispatch_context):
        """Test that dispatch_action handles exceptions gracefully."""
        base_processor.action_dispatcher.dispatch = AsyncMock(side_effect=RuntimeError("Test error"))

        result_mock = Mock()
        thought_mock = Mock()
        thought_mock.thought_id = "thought_123"

        context = dispatch_context.model_dump()

        success = await base_processor.dispatch_action(result_mock, thought_mock, context)

        assert success is False
        assert base_processor.metrics.errors == 1

    @pytest.mark.asyncio
    async def test_dispatch_action_fails_fast_without_time_service(self, base_processor, dispatch_context):
        """Test that dispatch_action fails fast when time service is missing."""
        # Remove time service
        delattr(base_processor, "time_service")

        base_processor.action_dispatcher.dispatch = AsyncMock(return_value={"success": True})

        result_mock = Mock()
        thought_mock = Mock()
        thought_mock.thought_id = "thought_123"

        context = dispatch_context.model_dump()

        # Should fail fast with RuntimeError
        success = await base_processor.dispatch_action(result_mock, thought_mock, context)

        assert success is False
        assert base_processor.metrics.errors == 1
