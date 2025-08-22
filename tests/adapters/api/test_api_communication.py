"""
Test suite for APICommunicationService.

Tests:
- Message sending and tracking
- Channel management
- Message history fetching
- Correlation handling
- Error scenarios
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.api_communication import APICommunicationService
from ciris_engine.schemas.telemetry.core import ServiceCorrelation, ServiceCorrelationStatus, ServiceRequestData


# Mock persistence.add_correlation for all tests to avoid database issues
@pytest.fixture(autouse=True)
def mock_add_correlation():
    with patch("ciris_engine.logic.persistence.add_correlation") as mock:
        mock.return_value = "test-correlation-id"
        yield mock


@pytest.fixture
def time_service():
    """Create mock time service."""
    service = Mock()
    service.now.return_value = datetime.now(timezone.utc)
    return service


@pytest.fixture
def app_state():
    """Create mock app state for message tracking."""
    state = Mock()
    state.sent_messages = {}
    state.message_channel_map = {}
    return state


@pytest.fixture
def communication_service(time_service, app_state):
    """Create APICommunicationService instance."""
    service = APICommunicationService()
    service._time_service = time_service
    service._app_state = app_state
    return service


class TestAPICommunicationMessageSending:
    """Test message sending functionality."""

    @pytest.mark.asyncio
    async def test_send_message_success(self, communication_service, app_state):
        """Test successful message sending."""
        # Start the service first
        await communication_service.start()

        # Mock persistence to avoid database access
        with patch("ciris_engine.logic.persistence") as mock_persistence:
            # Send message
            result = await communication_service.send_message(channel_id="api_127.0.0.1_8080", content="Test response")

            # Verify message was queued
            assert result is True
            assert communication_service._response_queue.qsize() > 0

            # Verify correlation was created
            mock_persistence.add_correlation.assert_called_once()

    @pytest.mark.asyncio
    async def test_send_message_with_correlation(self, communication_service, app_state):
        """Test sending message with correlation tracking."""
        # Start the service
        await communication_service.start()

        with patch("ciris_engine.logic.persistence") as mock_persistence:
            # Send message
            await communication_service.send_message(channel_id="api_127.0.0.1_8080", content="Correlated response")

            # Verify correlation was created
            mock_persistence.add_correlation.assert_called_once()
            correlation = mock_persistence.add_correlation.call_args[0][0]
            assert correlation.service_type == "api"
            assert correlation.action_type == "speak"
            assert correlation.request_data.parameters["content"] == "Correlated response"

    @pytest.mark.asyncio
    async def test_send_message_channel_tracking(self, communication_service):
        """Test message queueing for different channels."""
        # Start the service
        await communication_service.start()

        # Send messages to different channels
        channels = ["api_127.0.0.1_8080", "api_192.168.1.1_8080", "api_10.0.0.1_8080"]

        with patch("ciris_engine.logic.persistence"):
            for channel in channels:
                await communication_service.send_message(channel_id=channel, content=f"Message to {channel}")

            # Verify messages were queued
            assert communication_service._response_queue.qsize() == 3

            # Verify metrics were updated
            assert communication_service._request_count == 3

    @pytest.mark.asyncio
    async def test_send_message_error_handling(self, communication_service, app_state):
        """Test error handling during message sending."""
        # Start the service
        await communication_service.start()

        # Mock persistence to raise an error
        with patch("ciris_engine.logic.persistence") as mock_persistence:
            mock_persistence.add_correlation.side_effect = Exception("Database error")

            # Should handle error gracefully
            result = await communication_service.send_message(channel_id="api_127.0.0.1_8080", content="Test message")
            assert result is False
            assert communication_service._error_count == 1


class TestAPICommunicationMessageFetching:
    """Test message history fetching."""

    @pytest.mark.asyncio
    async def test_fetch_messages_from_correlations(self, communication_service):
        """Test fetching messages from service correlations."""
        # Mock correlations with proper structure
        now = datetime.now(timezone.utc)
        mock_observe_corr = ServiceCorrelation(
            correlation_id="corr-1",
            service_type="api",
            handler_name="APIAdapter",
            action_type="observe",
            status=ServiceCorrelationStatus.COMPLETED,
            created_at=now,
            updated_at=now,
            timestamp=now,
            request_data=ServiceRequestData(
                service_type="api",
                method_name="observe",
                request_timestamp=now,
                parameters={"content": "User message 1", "author_id": "user1", "author_name": "User One"},
            ),
        )

        mock_speak_corr = ServiceCorrelation(
            correlation_id="corr-2",
            service_type="api",
            handler_name="APIAdapter",
            action_type="speak",
            status=ServiceCorrelationStatus.COMPLETED,
            created_at=now,
            updated_at=now,
            timestamp=now,
            request_data=ServiceRequestData(
                service_type="api",
                method_name="speak",
                request_timestamp=now,
                parameters={"content": "Bot response 1", "channel_id": "api_127.0.0.1_8080"},
            ),
        )

        with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get:
            mock_get.return_value = [mock_observe_corr, mock_speak_corr]

            # Fetch messages
            messages = await communication_service.fetch_messages(channel_id="api_127.0.0.1_8080", limit=10)

            # Verify messages were constructed correctly
            assert len(messages) == 2

            # Check observe message
            assert messages[0].content == "User message 1"
            assert messages[0].author_id == "user1"
            assert messages[0].author_name == "User One"
            assert messages[0].is_bot is False

            # Check speak message
            assert messages[1].content == "Bot response 1"
            assert messages[1].author_id == "ciris"
            assert messages[1].author_name == "CIRIS"
            assert messages[1].is_bot is True

    @pytest.mark.asyncio
    async def test_fetch_messages_with_before_timestamp(self, communication_service):
        """Test fetching messages before specific timestamp."""
        cutoff_time = datetime.now(timezone.utc)

        with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get:
            mock_get.return_value = []

            await communication_service.fetch_messages(channel_id="api_127.0.0.1_8080", before=cutoff_time, limit=5)

            # Verify function was called with correct parameters
            mock_get.assert_called_once_with(channel_id="api_127.0.0.1_8080", limit=5, before=cutoff_time)

    @pytest.mark.asyncio
    async def test_fetch_messages_empty_channel(self, communication_service):
        """Test fetching from channel with no messages."""
        with patch("ciris_engine.logic.persistence.get_correlations_by_channel") as mock_get:
            mock_get.return_value = []

            messages = await communication_service.fetch_messages(channel_id="api_127.0.0.1_8080")

            assert messages == []


class TestAPICommunicationChannelManagement:
    """Test channel management functionality."""

    def test_get_status(self, communication_service):
        """Test getting service status."""
        # Start the service to set start time
        asyncio.run(communication_service.start())

        # Get status
        status = communication_service.get_status()

        assert status.service_name == "APICommunicationService"
        assert status.service_type == "communication"
        assert status.is_healthy is True
        assert "requests_handled" in status.metrics
        assert "error_count" in status.metrics
        assert "avg_response_time_ms" in status.metrics

    @pytest.mark.asyncio
    async def test_websocket_message_send(self, communication_service):
        """Test sending messages through WebSocket."""
        # Start the service
        await communication_service.start()

        # Mock WebSocket client
        mock_ws = Mock()
        mock_ws.send_json = AsyncMock()

        # Register WebSocket
        communication_service.register_websocket("client123", mock_ws)

        # Send message to WebSocket channel
        result = await communication_service.send_message(channel_id="ws:client123", content="WebSocket message")

        assert result is True
        mock_ws.send_json.assert_called_once()
        call_args = mock_ws.send_json.call_args[0][0]
        assert call_args["type"] == "message"
        assert call_args["data"]["content"] == "WebSocket message"

        # Unregister
        communication_service.unregister_websocket("client123")
        assert "client123" not in communication_service._websocket_clients


class TestAPICommunicationMetadata:
    """Test metadata handling in messages."""

    @pytest.mark.asyncio
    async def test_send_message_with_response_notification(self, communication_service, app_state):
        """Test sending messages with response notification."""
        # Start the service
        await communication_service.start()

        # Set up message channel mapping
        app_state.message_channel_map = {"api_127.0.0.1_8080": "msg-123"}

        # Mock notify function
        with patch("ciris_engine.logic.adapters.api.routes.agent.store_message_response") as mock_notify:
            with patch("ciris_engine.logic.persistence"):
                await communication_service.send_message(
                    channel_id="api_127.0.0.1_8080", content="Message with notification"
                )

                # Verify notification was attempted
                mock_notify.assert_called_once_with("msg-123", "Message with notification")

    @pytest.mark.asyncio
    async def test_service_health_check(self, communication_service):
        """Test service health check."""
        # Initially not started
        assert await communication_service.is_healthy() is False

        # Start service
        await communication_service.start()
        assert await communication_service.is_healthy() is True

        # Stop service
        await communication_service.stop()
        assert await communication_service.is_healthy() is False
