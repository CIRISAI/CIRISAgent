"""
Comprehensive test suite for refactored APICommunicationService helper methods.

Tests coverage for the newly extracted helper methods that reduce cognitive complexity:
- _create_speak_correlation
- _send_websocket_message
- _handle_api_interaction_response
- _track_response_time
- _extract_parameters
- _create_speak_message
- _create_observe_message
- _format_timestamp
- _process_correlation

These tests ensure robust coverage of all helper methods and edge cases.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.api_communication import APICommunicationService
from ciris_engine.schemas.runtime.messages import FetchedMessage
from ciris_engine.schemas.telemetry.core import ServiceCorrelation, ServiceRequestData


class TestCreateSpeakCorrelation:
    """Test _create_speak_correlation helper method."""

    @patch("uuid.uuid4")
    def test_create_speak_correlation_success(self, mock_uuid, api_communication_service, mock_persistence):
        """Test successful correlation creation."""
        mock_uuid.return_value = Mock()
        mock_uuid.return_value.__str__ = Mock(return_value="test-correlation-id")

        api_communication_service._create_speak_correlation("api_test_8080", "Test message")

        # Verify correlation was stored
        mock_persistence["add_correlation"].assert_called_once()
        correlation = mock_persistence["add_correlation"].call_args[0][0]

        assert correlation.correlation_id == "test-correlation-id"
        assert correlation.service_type == "api"
        assert correlation.action_type == "speak"
        assert correlation.request_data.parameters["content"] == "Test message"
        assert correlation.request_data.parameters["channel_id"] == "api_test_8080"

    def test_create_speak_correlation_with_time_service(
        self, api_communication_service, mock_time_service, mock_persistence
    ):
        """Test correlation creation uses time service when available."""
        api_communication_service._create_speak_correlation("api_test", "Message")

        # Verify time service was passed to persistence
        mock_persistence["add_correlation"].assert_called_once()
        time_service_arg = mock_persistence["add_correlation"].call_args[0][1]
        assert time_service_arg == mock_time_service

    def test_create_speak_correlation_handles_persistence_error(self, api_communication_service, mock_persistence):
        """Test correlation creation handles persistence errors gracefully."""
        mock_persistence["add_correlation"].side_effect = Exception("DB error")

        # Should raise exception as helper doesn't handle it
        with pytest.raises(Exception, match="DB error"):
            api_communication_service._create_speak_correlation("api_test", "Message")
        mock_persistence["add_correlation"].assert_called_once()


class TestSendWebSocketMessage:
    """Test _send_websocket_message helper method."""

    @pytest.mark.asyncio
    async def test_send_websocket_message_success(self, api_communication_service, mock_websocket_client):
        """Test successful WebSocket message sending."""
        # Register WebSocket client
        api_communication_service._websocket_clients["client123"] = mock_websocket_client

        result = await api_communication_service._send_websocket_message("ws:client123", "WebSocket test")

        assert result is True
        mock_websocket_client.send_json.assert_called_once()
        call_data = mock_websocket_client.send_json.call_args[0][0]
        assert call_data["type"] == "message"
        assert call_data["data"]["content"] == "WebSocket test"
        assert "timestamp" in call_data["data"]

    @pytest.mark.asyncio
    async def test_send_websocket_message_not_websocket_channel(self, api_communication_service):
        """Test returns False for non-WebSocket channels."""
        result = await api_communication_service._send_websocket_message("api_test", "Message")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_websocket_message_client_not_found(self, api_communication_service):
        """Test returns False when WebSocket client not found."""
        result = await api_communication_service._send_websocket_message("ws:unknown", "Message")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_websocket_message_empty_channel_id(self, api_communication_service):
        """Test handles empty channel ID gracefully."""
        result = await api_communication_service._send_websocket_message("", "Message")
        assert result is False

    @pytest.mark.asyncio
    async def test_send_websocket_message_websocket_error(self, api_communication_service, mock_websocket_client):
        """Test handles WebSocket send errors."""
        mock_websocket_client.send_json.side_effect = Exception("WebSocket error")
        api_communication_service._websocket_clients["client123"] = mock_websocket_client

        # Should raise exception (not handled at this level)
        with pytest.raises(Exception, match="WebSocket error"):
            await api_communication_service._send_websocket_message("ws:client123", "Message")


class TestHandleApiInteractionResponse:
    """Test _handle_api_interaction_response helper method."""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.agent.store_message_response")
    async def test_handle_api_interaction_response_success(self, mock_store, api_communication_service, mock_app_state):
        """Test successful API interaction response handling."""
        # Setup message channel mapping
        mock_app_state.message_channel_map = {"api_test": "msg-123"}

        await api_communication_service._handle_api_interaction_response("api_test", "Response content")

        mock_store.assert_called_once_with("msg-123", "Response content")
        assert "api_test" not in mock_app_state.message_channel_map  # Should be cleaned up

    @pytest.mark.asyncio
    async def test_handle_api_interaction_response_not_api_channel(self, api_communication_service):
        """Test ignores non-API channels."""
        await api_communication_service._handle_api_interaction_response("ws:test", "Message")
        # Should complete without error and do nothing

    @pytest.mark.asyncio
    async def test_handle_api_interaction_response_no_app_state(self, api_communication_service):
        """Test handles missing app state gracefully."""
        delattr(api_communication_service, "_app_state")

        await api_communication_service._handle_api_interaction_response("api_test", "Message")
        # Should complete without error

    @pytest.mark.asyncio
    async def test_handle_api_interaction_response_no_message_id(self, api_communication_service, mock_app_state):
        """Test handles missing message ID in mapping."""
        mock_app_state.message_channel_map = {}  # Empty mapping

        await api_communication_service._handle_api_interaction_response("api_test", "Message")
        # Should complete without error

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.agent.store_message_response", side_effect=Exception("Store error"))
    async def test_handle_api_interaction_response_store_error(
        self, mock_store, api_communication_service, mock_app_state
    ):
        """Test handles store_message_response errors gracefully."""
        mock_app_state.message_channel_map = {"api_test": "msg-123"}

        # Should not raise exception
        await api_communication_service._handle_api_interaction_response("api_test", "Message")
        mock_store.assert_called_once()


class TestTrackResponseTime:
    """Test _track_response_time helper method."""

    def test_track_response_time_success(self, api_communication_service):
        """Test successful response time tracking."""
        start_time = datetime(2025, 9, 8, 12, 0, 0, tzinfo=timezone.utc)

        # Mock the current time to be 100ms later
        with patch("ciris_engine.logic.adapters.api.api_communication.datetime") as mock_dt:
            mock_dt.now.return_value = datetime(2025, 9, 8, 12, 0, 0, 100000, tzinfo=timezone.utc)  # 100ms later
            mock_dt.timezone = timezone

            api_communication_service._track_response_time(start_time)

        assert len(api_communication_service._response_times) == 1
        assert api_communication_service._response_times[0] == 100.0  # 100ms

    def test_track_response_time_limit_enforcement(self, api_communication_service):
        """Test response times list is limited to max size."""
        api_communication_service._max_response_times = 2
        start_time = datetime.now(timezone.utc)

        # Add 3 response times
        for i in range(3):
            api_communication_service._track_response_time(start_time)

        # Should only keep the last 2
        assert len(api_communication_service._response_times) == 2


class TestExtractParameters:
    """Test _extract_parameters helper method."""

    def test_extract_parameters_dict_format(self, api_communication_service):
        """Test parameter extraction from dict-like request data."""
        request_data = {"parameters": {"content": "test", "author_id": "user1"}}

        params = api_communication_service._extract_parameters(request_data)

        assert params == {"content": "test", "author_id": "user1"}

    def test_extract_parameters_pydantic_format(self, api_communication_service):
        """Test parameter extraction from Pydantic model-like request data."""
        request_data = Mock()
        request_data.parameters = {"content": "test", "author_id": "user1"}
        # Ensure hasattr works correctly
        del request_data.get  # Remove get method to force pydantic path

        params = api_communication_service._extract_parameters(request_data)

        assert params == {"content": "test", "author_id": "user1"}

    def test_extract_parameters_no_parameters(self, api_communication_service):
        """Test parameter extraction when no parameters exist."""
        request_data = Mock(spec=[])  # Mock with no attributes

        params = api_communication_service._extract_parameters(request_data)

        assert params == {}

    def test_extract_parameters_none_parameters(self, api_communication_service):
        """Test parameter extraction when parameters is None."""
        request_data = Mock(spec=["parameters"])
        request_data.parameters = None

        params = api_communication_service._extract_parameters(request_data)

        assert params == {}

    def test_extract_parameters_empty_dict(self, api_communication_service):
        """Test parameter extraction from dict without parameters key."""
        request_data = {}

        params = api_communication_service._extract_parameters(request_data)

        assert params == {}


class TestCreateSpeakMessage:
    """Test _create_speak_message helper method."""

    def test_create_speak_message_success(self, api_communication_service, sample_speak_correlation):
        """Test successful speak message creation."""
        message = api_communication_service._create_speak_message(sample_speak_correlation)

        assert isinstance(message, FetchedMessage)
        assert message.message_id == "speak-corr-123"
        assert message.author_id == "ciris"
        assert message.author_name == "CIRIS"
        assert message.content == "Hello from CIRIS!"
        assert message.is_bot is True
        assert message.timestamp == sample_speak_correlation.timestamp.isoformat()

    def test_create_speak_message_empty_content(self, api_communication_service):
        """Test speak message creation with empty content."""
        correlation = Mock()
        correlation.correlation_id = "test-id"
        correlation.timestamp = datetime.now(timezone.utc)
        correlation.created_at = None
        correlation.request_data = Mock(spec=["parameters"])
        correlation.request_data.parameters = {}
        # Remove get method to force pydantic path
        delattr(correlation.request_data, "get") if hasattr(correlation.request_data, "get") else None

        message = api_communication_service._create_speak_message(correlation)

        assert message.content == ""
        assert message.author_id == "ciris"
        assert message.is_bot is True


class TestCreateObserveMessage:
    """Test _create_observe_message helper method."""

    def test_create_observe_message_success(self, api_communication_service, sample_observe_correlation):
        """Test successful observe message creation."""
        message = api_communication_service._create_observe_message(sample_observe_correlation)

        assert isinstance(message, FetchedMessage)
        assert message.message_id == "msg-456"  # Now uses original message_id from parameters
        assert message.author_id == "user123"
        assert message.author_name == "Test User"
        assert message.content == "Hello CIRIS!"
        assert message.is_bot is False
        assert message.timestamp == sample_observe_correlation.timestamp.isoformat()

    def test_create_observe_message_defaults(self, api_communication_service):
        """Test observe message creation with default values."""
        correlation = Mock()
        correlation.correlation_id = "test-id"
        correlation.timestamp = datetime.now(timezone.utc)
        correlation.created_at = None
        correlation.request_data = Mock(spec=["parameters"])
        correlation.request_data.parameters = {"content": "test message"}  # Missing author info
        # Remove get method to force pydantic path
        delattr(correlation.request_data, "get") if hasattr(correlation.request_data, "get") else None

        message = api_communication_service._create_observe_message(correlation)

        assert message.content == "test message"
        assert message.author_id == "unknown"
        assert message.author_name == "User"
        assert message.is_bot is False


class TestFormatTimestamp:
    """Test _format_timestamp helper method."""

    def test_format_timestamp_with_timestamp(self, api_communication_service):
        """Test timestamp formatting when timestamp is present."""
        correlation = Mock()
        correlation.timestamp = datetime(2025, 9, 8, 12, 0, 0, tzinfo=timezone.utc)
        correlation.created_at = datetime(2025, 9, 8, 11, 0, 0, tzinfo=timezone.utc)

        result = api_communication_service._format_timestamp(correlation)

        assert result == "2025-09-08T12:00:00+00:00"  # Uses timestamp, not created_at

    def test_format_timestamp_fallback_to_created_at(self, api_communication_service):
        """Test timestamp formatting falls back to created_at."""
        correlation = Mock()
        correlation.timestamp = None
        correlation.created_at = datetime(2025, 9, 8, 11, 0, 0, tzinfo=timezone.utc)

        result = api_communication_service._format_timestamp(correlation)

        assert result == "2025-09-08T11:00:00+00:00"

    def test_format_timestamp_none_values(self, api_communication_service):
        """Test timestamp formatting with None values."""
        correlation = Mock()
        correlation.timestamp = None
        correlation.created_at = None

        result = api_communication_service._format_timestamp(correlation)

        assert result is None


class TestProcessCorrelation:
    """Test _process_correlation helper method."""

    def test_process_correlation_speak_type(self, api_communication_service, sample_speak_correlation):
        """Test processing speak correlation."""
        message = api_communication_service._process_correlation(sample_speak_correlation)

        assert message is not None
        assert message.author_id == "ciris"
        assert message.is_bot is True

    def test_process_correlation_observe_type(self, api_communication_service, sample_observe_correlation):
        """Test processing observe correlation."""
        message = api_communication_service._process_correlation(sample_observe_correlation)

        assert message is not None
        assert message.author_id == "user123"
        assert message.is_bot is False

    def test_process_correlation_unknown_action_type(self, api_communication_service):
        """Test processing correlation with unknown action type."""
        correlation = Mock()
        correlation.action_type = "unknown"
        correlation.request_data = Mock()

        message = api_communication_service._process_correlation(correlation)

        assert message is None

    def test_process_correlation_no_request_data(self, api_communication_service):
        """Test processing correlation without request data."""
        correlation = Mock()
        correlation.action_type = "speak"
        correlation.request_data = None

        message = api_communication_service._process_correlation(correlation)

        assert message is None


class TestRefactoredSendMessage:
    """Test the refactored send_message method integration."""

    @pytest.mark.asyncio
    async def test_send_message_integration(self, api_communication_service, mock_websocket_client, mock_persistence):
        """Test complete send_message flow with refactored helpers."""
        # Setup WebSocket client
        api_communication_service._websocket_clients["client123"] = mock_websocket_client

        result = await api_communication_service.send_message("ws:client123", "Integration test")

        assert result is True
        # Verify correlation was created
        mock_persistence["add_correlation"].assert_called_once()
        # Verify WebSocket message was sent
        mock_websocket_client.send_json.assert_called_once()


class TestRefactoredFetchMessages:
    """Test the refactored fetch_messages method integration."""

    @pytest.mark.asyncio
    async def test_fetch_messages_integration(self, api_communication_service, sample_correlations, mock_persistence):
        """Test complete fetch_messages flow with refactored helpers."""
        mock_persistence["get_correlations_by_channel"].return_value = sample_correlations

        messages = await api_communication_service.fetch_messages("api_test")

        assert len(messages) == 2
        # Verify both message types are processed
        user_msg = next((m for m in messages if not m.is_bot), None)
        bot_msg = next((m for m in messages if m.is_bot), None)

        assert user_msg is not None
        assert user_msg.author_id == "user123"
        assert bot_msg is not None
        assert bot_msg.author_id == "ciris"
