"""
Comprehensive unit tests for agent.py helper functions.

Tests all refactored helper functions to achieve 80%+ coverage.
"""

import asyncio
from datetime import datetime, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import WebSocket

from ciris_engine.logic.adapters.api.routes.agent import (
    AgentStatus,
    ConversationHistory,
    ConversationMessage,
    _apply_message_limit,
    _authenticate_websocket_user,
    _build_agent_status,
    _build_channels_to_query,
    _convert_service_message_to_conversation,
    _convert_timestamp,
    _create_conversation_message_from_mock,
    _expand_mock_messages,
    _fetch_messages_from_channels,
    _get_admin_channels,
    _get_current_task_info,
    _get_history_from_communication_service,
    _get_history_from_memory,
    _get_history_from_mock,
    _get_memory_usage,
    _get_version_info,
    _handle_websocket_subscription_action,
    _register_websocket_client,
    _safe_convert_message_timestamp,
    _sort_and_filter_messages,
    _unregister_websocket_client,
    _validate_websocket_authorization,
)
from ciris_engine.schemas.api.auth import AuthContext, UserRole


class TestChannelHelpers:
    """Test helper functions for channel management."""

    def test_get_admin_channels_for_admin_user(self):
        """Test admin channel creation for admin users."""
        auth = Mock()
        auth.role = "ADMIN"
        request = Mock()
        request.app.state.api_host = "localhost"
        request.app.state.api_port = "8080"

        channels = _get_admin_channels(auth, request)

        expected = [
            "api_localhost_8080",
            "api_0.0.0.0_8080",
            "api_127.0.0.1_8080",
            "api_localhost_8080",  # hostname variant
        ]
        assert channels == expected

    def test_get_admin_channels_for_authority_user(self):
        """Test admin channel creation for authority users."""
        auth = Mock()
        auth.role = "AUTHORITY"
        request = Mock()
        request.app.state.api_host = "example.com"
        request.app.state.api_port = "9000"

        channels = _get_admin_channels(auth, request)

        assert "api_example.com_9000" in channels
        assert "api_0.0.0.0_9000" in channels
        assert "api_127.0.0.1_9000" in channels
        assert "api_localhost_9000" in channels

    def test_get_admin_channels_for_system_admin(self):
        """Test admin channel creation for system admin users."""
        auth = Mock()
        auth.role = "SYSTEM_ADMIN"
        request = Mock()
        request.app.state.api_host = "192.168.1.100"
        request.app.state.api_port = "3000"

        channels = _get_admin_channels(auth, request)

        assert "api_192.168.1.100_3000" in channels
        assert len(channels) == 4

    def test_get_admin_channels_for_observer_user(self):
        """Test admin channel creation for non-admin users."""
        auth = Mock()
        auth.role = "OBSERVER"
        request = Mock()

        channels = _get_admin_channels(auth, request)

        assert channels == []

    def test_get_admin_channels_with_default_values(self):
        """Test admin channel creation with default host/port values."""
        auth = Mock()
        auth.role = "ADMIN"
        request = Mock()
        # Mock getattr to return defaults
        with patch("ciris_engine.logic.adapters.api.routes.agent.getattr") as mock_getattr:
            mock_getattr.side_effect = lambda obj, attr, default=None: default

            channels = _get_admin_channels(auth, request)

            assert "api_127.0.0.1_8080" in channels  # defaults
            assert len(channels) == 4

    def test_build_channels_to_query_for_admin(self):
        """Test building complete channel list for admin user."""
        auth = Mock()
        auth.user_id = "admin_user"
        auth.role = "ADMIN"
        request = Mock()
        request.app.state.api_host = "localhost"
        request.app.state.api_port = "8080"

        channels = _build_channels_to_query(auth, request)

        assert f"api_{auth.user_id}" in channels
        assert "api_localhost_8080" in channels
        assert len(channels) >= 5  # user channel + 4 admin channels

    def test_build_channels_to_query_for_observer(self):
        """Test building channel list for observer user."""
        auth = Mock()
        auth.user_id = "observer_user"
        auth.role = "OBSERVER"
        request = Mock()

        channels = _build_channels_to_query(auth, request)

        assert channels == [f"api_{auth.user_id}"]


class TestTimestampHelpers:
    """Test helper functions for timestamp conversion."""

    def test_convert_timestamp_from_string(self):
        """Test converting ISO format string to datetime."""
        timestamp_str = "2025-09-27T16:30:00+00:00"
        result = _convert_timestamp(timestamp_str)

        assert isinstance(result, datetime)
        assert result.year == 2025
        assert result.month == 9
        assert result.day == 27

    def test_convert_timestamp_from_datetime(self):
        """Test converting existing datetime object."""
        original_dt = datetime(2025, 9, 27, 16, 30, 0, tzinfo=timezone.utc)
        result = _convert_timestamp(original_dt)

        assert result == original_dt

    def test_convert_timestamp_from_invalid_input(self):
        """Test converting invalid timestamp input."""
        result = _convert_timestamp(12345)  # invalid type

        assert isinstance(result, datetime)
        # Should return current time as fallback

    def test_safe_convert_message_timestamp_with_datetime(self):
        """Test safe timestamp conversion with datetime object."""
        msg = Mock()
        msg.timestamp = datetime(2025, 9, 27, 16, 30, 0, tzinfo=timezone.utc)

        result = _safe_convert_message_timestamp(msg)

        assert result == msg.timestamp

    def test_safe_convert_message_timestamp_with_string(self):
        """Test safe timestamp conversion with string."""
        msg = Mock()
        msg.timestamp = "2025-09-27T16:30:00+00:00"

        result = _safe_convert_message_timestamp(msg)

        assert isinstance(result, datetime)
        assert result.year == 2025

    def test_safe_convert_message_timestamp_with_invalid_string(self):
        """Test safe timestamp conversion with invalid string."""
        msg = Mock()
        msg.timestamp = "invalid_timestamp"

        result = _safe_convert_message_timestamp(msg)

        assert isinstance(result, datetime)
        # Should return current time as fallback

    def test_safe_convert_message_timestamp_with_none(self):
        """Test safe timestamp conversion with None."""
        msg = Mock()
        msg.timestamp = None

        result = _safe_convert_message_timestamp(msg)

        assert isinstance(result, datetime)


class TestMessageHelpers:
    """Test helper functions for message processing."""

    def test_create_conversation_message_from_mock_user_message(self):
        """Test creating conversation message from mock user data."""
        mock_msg = {
            "message_id": "msg123",
            "author_id": "user456",
            "content": "Hello there",
            "timestamp": "2025-09-27T16:30:00+00:00",
        }

        result = _create_conversation_message_from_mock(mock_msg)

        assert result.id == "msg123"
        assert result.author == "user456"
        assert result.content == "Hello there"
        assert result.is_agent is False

    def test_create_conversation_message_from_mock_response_message(self):
        """Test creating conversation message from mock response data."""
        mock_msg = {"message_id": "msg123", "response": "Hello back!", "timestamp": "2025-09-27T16:30:00+00:00"}

        result = _create_conversation_message_from_mock(mock_msg, is_response=True)

        assert result.id == "msg123_response"
        assert result.author == "Scout"
        assert result.content == "Hello back!"
        assert result.is_agent is True

    def test_expand_mock_messages_with_responses(self):
        """Test expanding mock messages with responses."""
        mock_messages = [
            {
                "message_id": "msg1",
                "author_id": "user1",
                "content": "First message",
                "timestamp": "2025-09-27T16:30:00+00:00",
                "response": "First response",
            },
            {
                "message_id": "msg2",
                "author_id": "user1",
                "content": "Second message",
                "timestamp": "2025-09-27T16:31:00+00:00",
                # No response
            },
        ]

        result = _expand_mock_messages(mock_messages)

        assert len(result) == 3  # 2 user messages + 1 response
        assert result[0].id == "msg1"
        assert result[0].is_agent is False
        assert result[1].id == "msg1_response"
        assert result[1].is_agent is True
        assert result[2].id == "msg2"
        assert result[2].is_agent is False

    def test_expand_mock_messages_without_responses(self):
        """Test expanding mock messages without responses."""
        mock_messages = [
            {
                "message_id": "msg1",
                "author_id": "user1",
                "content": "Only message",
                "timestamp": "2025-09-27T16:30:00+00:00",
            }
        ]

        result = _expand_mock_messages(mock_messages)

        assert len(result) == 1
        assert result[0].id == "msg1"
        assert result[0].is_agent is False

    def test_apply_message_limit_within_limit(self):
        """Test applying message limit when under limit."""
        messages = [
            ConversationMessage(
                id="1", author="user", content="msg1", timestamp=datetime.now(timezone.utc), is_agent=False
            ),
            ConversationMessage(
                id="2", author="user", content="msg2", timestamp=datetime.now(timezone.utc), is_agent=False
            ),
        ]

        result = _apply_message_limit(messages, 5)

        assert len(result) == 2
        assert result == messages

    def test_apply_message_limit_over_limit(self):
        """Test applying message limit when over limit."""
        messages = [
            ConversationMessage(
                id=str(i), author="user", content=f"msg{i}", timestamp=datetime.now(timezone.utc), is_agent=False
            )
            for i in range(10)
        ]

        result = _apply_message_limit(messages, 3)

        assert len(result) == 3
        assert result[0].id == "7"  # Last 3 messages
        assert result[1].id == "8"
        assert result[2].id == "9"

    def test_convert_service_message_to_conversation(self):
        """Test converting service message to conversation message."""
        service_msg = Mock()
        service_msg.message_id = "service_msg_123"
        service_msg.author_name = "Test User"
        service_msg.author_id = "user123"
        service_msg.content = "Service message content"
        service_msg.timestamp = datetime(2025, 9, 27, 16, 30, 0, tzinfo=timezone.utc)
        service_msg.is_agent_message = False
        service_msg.is_bot = False

        result = _convert_service_message_to_conversation(service_msg)

        assert result.id == "service_msg_123"
        assert result.author == "Test User"
        assert result.content == "Service message content"
        assert result.is_agent is False

    def test_convert_service_message_with_agent_flags(self):
        """Test converting service message with agent flags set."""
        service_msg = Mock()
        service_msg.message_id = "agent_msg_123"
        service_msg.author_name = None
        service_msg.author_id = "agent"
        service_msg.content = "Agent response"
        service_msg.timestamp = datetime(2025, 9, 27, 16, 30, 0, tzinfo=timezone.utc)
        service_msg.is_agent_message = True
        service_msg.is_bot = False

        result = _convert_service_message_to_conversation(service_msg)

        assert result.author == "agent"  # falls back to author_id
        assert result.is_agent is True


class TestMessageFetching:
    """Test helper functions for fetching messages."""

    @pytest.mark.asyncio
    async def test_fetch_messages_from_channels_success(self):
        """Test successful message fetching from channels."""
        comm_service = Mock()
        comm_service.fetch_messages = AsyncMock(
            return_value=[Mock(message_id="msg1", content="content1"), Mock(message_id="msg2", content="content2")]
        )

        channels = ["channel1", "channel2"]

        result = await _fetch_messages_from_channels(comm_service, channels, 10)

        assert len(result) == 4  # 2 messages from each channel
        assert comm_service.fetch_messages.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_messages_from_channels_with_failure(self, caplog):
        """Test message fetching with some channel failures."""
        comm_service = Mock()
        comm_service.fetch_messages = AsyncMock(
            side_effect=[
                [Mock(message_id="msg1")],  # First channel succeeds
                Exception("Channel not found"),  # Second channel fails
            ]
        )

        channels = ["channel1", "channel2"]

        result = await _fetch_messages_from_channels(comm_service, channels, 10)

        assert len(result) == 1  # Only messages from successful channel
        assert "Failed to fetch from channel channel2" in caplog.text

    @pytest.mark.asyncio
    async def test_fetch_messages_with_none_service(self, caplog):
        """Test message fetching with None communication service."""
        channels = ["channel1"]

        result = await _fetch_messages_from_channels(None, channels, 10)

        assert len(result) == 0
        assert "Communication service is not available" in caplog.text

    def test_sort_and_filter_messages_without_filter(self):
        """Test sorting messages without time filter."""
        messages = [
            Mock(timestamp=datetime(2025, 9, 27, 16, 30, 0, tzinfo=timezone.utc)),
            Mock(timestamp=datetime(2025, 9, 27, 16, 25, 0, tzinfo=timezone.utc)),
            Mock(timestamp=datetime(2025, 9, 27, 16, 35, 0, tzinfo=timezone.utc)),
        ]

        result = _sort_and_filter_messages(messages, None)

        # Should be sorted newest first
        assert len(result) == 3
        assert result[0].timestamp.minute == 35
        assert result[1].timestamp.minute == 30
        assert result[2].timestamp.minute == 25

    def test_sort_and_filter_messages_with_time_filter(self):
        """Test sorting and filtering messages by time."""
        cutoff_time = datetime(2025, 9, 27, 16, 30, 0, tzinfo=timezone.utc)
        messages = [
            Mock(timestamp=datetime(2025, 9, 27, 16, 25, 0, tzinfo=timezone.utc)),  # Before cutoff
            Mock(timestamp=datetime(2025, 9, 27, 16, 35, 0, tzinfo=timezone.utc)),  # After cutoff
        ]

        result = _sort_and_filter_messages(messages, cutoff_time)

        # Should only include message before cutoff
        assert len(result) == 1
        assert result[0].timestamp.minute == 25


class TestHistoryFunctions:
    """Test main history retrieval functions."""

    @pytest.mark.asyncio
    async def test_get_history_from_mock(self):
        """Test getting history from mock data."""
        message_history = [
            {
                "message_id": "msg1",
                "author_id": "user1",
                "content": "Hello",
                "timestamp": "2025-09-27T16:30:00+00:00",
                "channel_id": "api_user1",
                "response": "Hi there!",
            },
            {
                "message_id": "msg2",
                "author_id": "user2",
                "content": "Different user",
                "timestamp": "2025-09-27T16:31:00+00:00",
                "channel_id": "api_user2",
            },
        ]

        channels_to_query = ["api_user1"]

        result = await _get_history_from_mock(message_history, channels_to_query, 10)

        assert isinstance(result, ConversationHistory)
        assert len(result.messages) == 2  # User message + response
        assert result.total_count == 1  # Only 1 original user message matched
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_get_history_from_memory(self):
        """Test getting history from memory service."""
        memory_service = Mock()
        node1 = Mock()
        node1.id = "node1"
        node1.attributes = {
            "message_id": "msg1",
            "author": "user1",
            "content": "Memory content",
            "timestamp": "2025-09-27T16:30:00+00:00",
            "is_agent": False,
        }
        node1.created_at = "2025-09-27T16:30:00+00:00"

        memory_service.recall = AsyncMock(return_value=[node1])

        result = await _get_history_from_memory(memory_service, "test_channel", 10)

        assert isinstance(result, ConversationHistory)
        assert len(result.messages) == 1
        assert result.messages[0].id == "msg1"
        assert result.messages[0].author == "user1"
        assert result.messages[0].content == "Memory content"

    @pytest.mark.asyncio
    async def test_get_history_from_communication_service(self):
        """Test getting history from communication service."""
        comm_service = Mock()
        comm_service.fetch_messages = AsyncMock(
            return_value=[
                Mock(
                    message_id="msg1",
                    author_name="Test User",
                    author_id="user1",
                    content="Service content",
                    timestamp=datetime(2025, 9, 27, 16, 30, 0, tzinfo=timezone.utc),
                    is_agent_message=False,
                    is_bot=False,
                )
            ]
        )

        channels = ["channel1"]

        result = await _get_history_from_communication_service(comm_service, channels, 10, None)

        assert isinstance(result, ConversationHistory)
        assert len(result.messages) == 1
        assert result.messages[0].id == "msg1"
        assert result.messages[0].author == "Test User"


class TestStatusHelpers:
    """Test helper functions for status endpoint."""

    def test_get_current_task_info_with_task_scheduler(self):
        """Test getting current task info with available task scheduler."""
        request = Mock()
        task_scheduler = Mock()
        task_scheduler.get_current_task = Mock(return_value="current_task")
        request.app.state.task_scheduler = task_scheduler

        result = _get_current_task_info(request)

        # Should return the result of calling get_current_task()
        assert result == "current_task"
        task_scheduler.get_current_task.assert_called_once()

    def test_get_current_task_info_without_scheduler(self):
        """Test getting current task info without task scheduler."""
        request = Mock()
        request.app.state.task_scheduler = None

        result = _get_current_task_info(request)

        assert result is None

    def test_get_current_task_info_without_method(self):
        """Test getting current task info with scheduler missing method."""
        request = Mock()
        task_scheduler = Mock(spec=[])  # Empty spec, no methods
        request.app.state.task_scheduler = task_scheduler

        result = _get_current_task_info(request)

        assert result is None

    def test_get_memory_usage_with_monitor(self):
        """Test getting memory usage with available resource monitor."""
        request = Mock()
        resource_monitor = Mock()
        resource_monitor.snapshot.memory_mb = 256.5
        request.app.state.resource_monitor = resource_monitor

        result = _get_memory_usage(request)

        assert result == 256.5

    def test_get_memory_usage_without_monitor(self):
        """Test getting memory usage without resource monitor."""
        request = Mock()
        request.app.state.resource_monitor = None

        result = _get_memory_usage(request)

        assert result == 0.0

    def test_get_memory_usage_without_snapshot(self):
        """Test getting memory usage with monitor missing snapshot."""
        request = Mock()
        resource_monitor = Mock()
        # No snapshot attribute
        del resource_monitor.snapshot
        request.app.state.resource_monitor = resource_monitor

        result = _get_memory_usage(request)

        assert result == 0.0

    def test_get_version_info_with_hash(self):
        """Test getting version info with code hash available."""
        with patch("ciris_engine.constants.CIRIS_VERSION", "v1.2.3"), patch(
            "ciris_engine.constants.CIRIS_CODENAME", "TestCode"
        ), patch.dict("sys.modules", {"version": Mock(__version__="abc123")}):
            version, codename, code_hash = _get_version_info()

            assert version == "v1.2.3"
            assert codename == "TestCode"
            assert code_hash == "abc123"

    def test_get_version_info_without_hash(self):
        """Test getting version info without code hash."""
        # Test the ImportError path in _get_version_info
        import sys

        original_modules = sys.modules.copy()
        try:
            # Remove version module if it exists
            if "version" in sys.modules:
                del sys.modules["version"]

            with patch("ciris_engine.constants.CIRIS_VERSION", "v1.2.3"), patch(
                "ciris_engine.constants.CIRIS_CODENAME", "TestCode"
            ):

                version, codename, code_hash = _get_version_info()

                assert version == "v1.2.3"
                assert codename == "TestCode"
                # code_hash should be None when import fails
        finally:
            # Restore original modules
            sys.modules.clear()
            sys.modules.update(original_modules)

    @pytest.mark.asyncio
    async def test_build_agent_status(self):
        """Test building complete agent status."""
        request = Mock()
        request.app.state.task_scheduler = None
        request.app.state.resource_monitor = None
        request.app.state.service_registry = None

        runtime = Mock()

        # Mock helper functions
        with patch("ciris_engine.logic.adapters.api.routes.agent._count_active_services", return_value=(5, {})), patch(
            "ciris_engine.logic.adapters.api.routes.agent._get_agent_identity_info",
            return_value=("agent1", "TestAgent"),
        ), patch("ciris_engine.constants.CIRIS_VERSION", "v1.0.0"), patch(
            "ciris_engine.constants.CIRIS_CODENAME", "Test"
        ):

            status = await _build_agent_status(request, "WORK", 3600.0, 10, runtime)

            assert isinstance(status, AgentStatus)
            assert status.agent_id == "agent1"
            assert status.name == "TestAgent"
            assert status.cognitive_state == "WORK"
            assert status.uptime_seconds == 3600.0
            assert status.messages_processed == 10
            assert status.services_active == 5


class TestWebSocketHelpers:
    """Test helper functions for WebSocket operations."""

    def test_validate_websocket_authorization_valid(self):
        """Test validating valid WebSocket authorization."""
        websocket = Mock()
        websocket.headers = {"authorization": "Bearer abc123token"}

        result = _validate_websocket_authorization(websocket)

        assert result == "abc123token"

    def test_validate_websocket_authorization_missing(self):
        """Test validating missing WebSocket authorization."""
        websocket = Mock()
        websocket.headers = {}

        result = _validate_websocket_authorization(websocket)

        assert result is None

    def test_validate_websocket_authorization_invalid_format(self):
        """Test validating invalid WebSocket authorization format."""
        websocket = Mock()
        websocket.headers = {"authorization": "Basic abc123"}

        result = _validate_websocket_authorization(websocket)

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_websocket_user_success(self):
        """Test successful WebSocket user authentication."""
        websocket = Mock()
        auth_service = Mock()
        key_info = Mock()
        key_info.user_id = "user123"
        key_info.role = UserRole.ADMIN
        auth_service.validate_api_key.return_value = key_info
        auth_service._get_key_id.return_value = "key_id_123"
        websocket.app.state.auth_service = auth_service

        result = await _authenticate_websocket_user(websocket, "test_api_key")

        assert isinstance(result, AuthContext)
        assert result.user_id == "user123"
        assert result.role == UserRole.ADMIN

    @pytest.mark.asyncio
    async def test_authenticate_websocket_user_no_service(self):
        """Test WebSocket authentication without auth service."""
        websocket = Mock()
        websocket.app.state.auth_service = None

        result = await _authenticate_websocket_user(websocket, "test_api_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_websocket_user_invalid_key(self):
        """Test WebSocket authentication with invalid API key."""
        websocket = Mock()
        auth_service = Mock()
        auth_service.validate_api_key.return_value = None
        websocket.app.state.auth_service = auth_service

        result = await _authenticate_websocket_user(websocket, "invalid_key")

        assert result is None

    @pytest.mark.asyncio
    async def test_handle_websocket_subscription_action_subscribe(self):
        """Test handling WebSocket subscribe action."""
        websocket = Mock()
        websocket.send_json = AsyncMock()
        data = {"action": "subscribe", "channels": ["telemetry", "logs"]}
        subscribed_channels = {"messages"}

        await _handle_websocket_subscription_action(websocket, data, subscribed_channels)

        assert "telemetry" in subscribed_channels
        assert "logs" in subscribed_channels
        assert "messages" in subscribed_channels
        websocket.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_websocket_subscription_action_unsubscribe(self):
        """Test handling WebSocket unsubscribe action."""
        websocket = Mock()
        websocket.send_json = AsyncMock()
        data = {"action": "unsubscribe", "channels": ["messages"]}
        subscribed_channels = {"messages", "telemetry"}

        await _handle_websocket_subscription_action(websocket, data, subscribed_channels)

        assert "messages" not in subscribed_channels
        assert "telemetry" in subscribed_channels
        websocket.send_json.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_websocket_subscription_action_ping(self):
        """Test handling WebSocket ping action."""
        websocket = Mock()
        websocket.send_json = AsyncMock()
        data = {"action": "ping"}
        subscribed_channels = {"messages"}

        await _handle_websocket_subscription_action(websocket, data, subscribed_channels)

        # Ping should respond with pong, not subscription update
        call_args = websocket.send_json.call_args[0][0]
        assert call_args["type"] == "pong"
        assert "timestamp" in call_args

    def test_register_websocket_client(self):
        """Test registering WebSocket client."""
        websocket = Mock()
        comm_service = Mock()
        comm_service.register_websocket = Mock()
        websocket.app.state.communication_service = comm_service

        _register_websocket_client(websocket, "client123")

        comm_service.register_websocket.assert_called_once_with("client123", websocket)

    def test_register_websocket_client_no_service(self):
        """Test registering WebSocket client without communication service."""
        websocket = Mock()
        websocket.app.state.communication_service = None

        # Should not raise exception
        _register_websocket_client(websocket, "client123")

    def test_register_websocket_client_no_method(self):
        """Test registering WebSocket client with service missing method."""
        websocket = Mock()
        comm_service = Mock()
        # No register_websocket method
        del comm_service.register_websocket
        websocket.app.state.communication_service = comm_service

        # Should not raise exception
        _register_websocket_client(websocket, "client123")

    def test_unregister_websocket_client(self):
        """Test unregistering WebSocket client."""
        websocket = Mock()
        comm_service = Mock()
        comm_service.unregister_websocket = Mock()
        websocket.app.state.communication_service = comm_service

        _unregister_websocket_client(websocket, "client123")

        comm_service.unregister_websocket.assert_called_once_with("client123")

    def test_unregister_websocket_client_no_service(self):
        """Test unregistering WebSocket client without communication service."""
        websocket = Mock()
        websocket.app.state.communication_service = None

        # Should not raise exception
        _unregister_websocket_client(websocket, "client123")


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_convert_timestamp_with_invalid_iso_string(self):
        """Test timestamp conversion with invalid ISO string."""
        result = _convert_timestamp("not-a-timestamp")

        # Should fall back to current time
        assert isinstance(result, datetime)

    @pytest.mark.asyncio
    async def test_get_history_from_mock_empty_history(self):
        """Test getting history from empty mock data."""
        result = await _get_history_from_mock([], ["channel1"], 10)

        assert len(result.messages) == 0
        assert result.total_count == 0
        assert result.has_more is False

    @pytest.mark.asyncio
    async def test_get_history_from_memory_empty_nodes(self):
        """Test getting history from memory with no nodes."""
        memory_service = Mock()
        memory_service.recall = AsyncMock(return_value=[])

        result = await _get_history_from_memory(memory_service, "test_channel", 10)

        assert len(result.messages) == 0
        assert result.total_count == 0

    def test_sort_and_filter_messages_with_invalid_timestamps(self):
        """Test sorting messages with some invalid timestamps."""
        messages = [
            Mock(timestamp=datetime(2025, 9, 27, 16, 30, 0, tzinfo=timezone.utc)),
            Mock(timestamp="invalid"),
            Mock(timestamp=None),
        ]

        # Should not raise exception and handle gracefully
        result = _sort_and_filter_messages(messages, None)

        assert len(result) == 3
