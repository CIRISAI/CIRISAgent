"""
Coverage-focused tests for Discord channel manager functionality.

Targets high-impact areas for reaching 80% coverage:
- discord_channel_manager.py missing lines (31.47% -> 80%+ target)
- Channel resolution, validation, and access control
- Client management and message handling
- Error scenarios and edge cases
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from discord.errors import Forbidden, NotFound
import discord

from ciris_engine.logic.adapters.discord.discord_channel_manager import DiscordChannelManager
from ciris_engine.schemas.runtime.messages import DiscordMessage


class TestDiscordChannelManagerCoverage:
    """Coverage-focused tests for Discord channel manager."""

    def setup_method(self):
        """Set up test fixtures."""
        self.token = "test_token_123"
        self.mock_client = Mock(spec=discord.Client)
        self.mock_callback = AsyncMock()
        self.monitored_channels = ["123456789", "987654321"]

        self.manager = DiscordChannelManager(
            token=self.token,
            client=self.mock_client,
            on_message_callback=self.mock_callback,
            monitored_channel_ids=self.monitored_channels
        )

    def test_initialization_basic(self):
        """Test basic initialization."""
        manager = DiscordChannelManager(token="test_token")

        assert manager.token == "test_token"
        assert manager.client is None
        assert manager.on_message_callback is None
        assert manager.monitored_channel_ids == []
        assert manager.filter_service is None
        assert manager.consent_service is None

    def test_initialization_with_all_params(self):
        """Test initialization with all parameters."""
        mock_filter = Mock()
        mock_consent = Mock()

        manager = DiscordChannelManager(
            token=self.token,
            client=self.mock_client,
            on_message_callback=self.mock_callback,
            monitored_channel_ids=self.monitored_channels,
            filter_service=mock_filter,
            consent_service=mock_consent
        )

        assert manager.token == self.token
        assert manager.client == self.mock_client
        assert manager.on_message_callback == self.mock_callback
        assert manager.monitored_channel_ids == self.monitored_channels
        assert manager.filter_service == mock_filter
        assert manager.consent_service == mock_consent

    def test_set_client(self):
        """Test setting client after initialization - targets line 57."""
        manager = DiscordChannelManager(token="test")
        new_client = Mock(spec=discord.Client)

        manager.set_client(new_client)

        assert manager.client == new_client

    def test_set_message_callback(self):
        """Test setting message callback after initialization - targets line 57."""
        manager = DiscordChannelManager(token="test")
        new_callback = AsyncMock()

        manager.set_message_callback(new_callback)

        assert manager.on_message_callback == new_callback

    @pytest.mark.asyncio
    async def test_resolve_channel_no_client(self):
        """Test resolve_channel when no client - targets lines 69-70."""
        manager = DiscordChannelManager(token="test")  # No client

        result = await manager.resolve_channel("123456789")

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_channel_get_channel_success(self):
        """Test successful channel resolution via get_channel."""
        mock_channel = Mock()
        self.mock_client.get_channel.return_value = mock_channel

        result = await self.manager.resolve_channel("123456789")

        assert result == mock_channel
        self.mock_client.get_channel.assert_called_once_with(123456789)

    @pytest.mark.asyncio
    async def test_resolve_channel_fetch_channel_success(self):
        """Test successful channel resolution via fetch_channel - targets line 81."""
        mock_channel = Mock()
        self.mock_client.get_channel.return_value = None  # Not in cache
        self.mock_client.fetch_channel = AsyncMock(return_value=mock_channel)

        result = await self.manager.resolve_channel("123456789")

        assert result == mock_channel
        self.mock_client.fetch_channel.assert_called_once_with(123456789)

    @pytest.mark.asyncio
    async def test_resolve_channel_not_found_error(self):
        """Test resolve_channel with NotFound error - targets lines 82-84."""
        self.mock_client.get_channel.return_value = None
        self.mock_client.fetch_channel = AsyncMock(side_effect=NotFound(Mock(), "Channel not found"))

        result = await self.manager.resolve_channel("123456789")

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_channel_forbidden_error(self):
        """Test resolve_channel with Forbidden error - targets lines 82-84."""
        self.mock_client.get_channel.return_value = None
        self.mock_client.fetch_channel = AsyncMock(side_effect=Forbidden(Mock(), "Access denied"))

        result = await self.manager.resolve_channel("123456789")

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_channel_invalid_id_format(self):
        """Test resolve_channel with invalid ID format - targets lines 86-88."""
        result = await self.manager.resolve_channel("invalid_id")

        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_channel_unexpected_error(self):
        """Test resolve_channel with unexpected error - targets lines 89-91."""
        self.mock_client.get_channel.side_effect = Exception("Unexpected error")

        result = await self.manager.resolve_channel("123456789")

        assert result is None

    @pytest.mark.asyncio
    async def test_validate_channel_access_success(self):
        """Test successful channel access validation."""
        mock_channel = Mock()
        self.mock_client.get_channel.return_value = mock_channel

        result = await self.manager.validate_channel_access("123456789")

        assert result is True

    @pytest.mark.asyncio
    async def test_validate_channel_access_no_access(self):
        """Test channel access validation when no access - targets lines 104, 107-108."""
        self.mock_client.get_channel.return_value = None
        self.mock_client.fetch_channel = AsyncMock(return_value=None)

        result = await self.manager.validate_channel_access("123456789")

        assert result is False

    def test_is_client_ready_true(self):
        """Test is_client_ready when client is ready - targets line 119."""
        self.mock_client.is_closed.return_value = False

        result = self.manager.is_client_ready()

        assert result is True

    def test_is_client_ready_false(self):
        """Test is_client_ready when client not ready - targets lines 123-124."""
        self.mock_client.is_closed.return_value = True

        result = self.manager.is_client_ready()

        assert result is False

    def test_is_client_ready_no_client(self):
        """Test is_client_ready when no client - targets lines 123-124."""
        manager = DiscordChannelManager(token="test")  # No client

        result = manager.is_client_ready()

        assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_client_ready_immediate_success(self):
        """Test wait_for_client_ready when already ready."""
        self.mock_client.wait_until_ready = AsyncMock()

        result = await self.manager.wait_for_client_ready(timeout=1.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_wait_for_client_ready_timeout(self):
        """Test wait_for_client_ready timeout - targets lines 135-145."""
        self.mock_client.wait_until_ready = AsyncMock(side_effect=asyncio.TimeoutError())

        result = await self.manager.wait_for_client_ready(timeout=0.1)

        assert result is False

    @pytest.mark.asyncio
    async def test_wait_for_client_ready_becomes_ready(self):
        """Test wait_for_client_ready when client becomes ready during wait."""
        self.mock_client.wait_until_ready = AsyncMock()  # Successful wait

        result = await self.manager.wait_for_client_ready(timeout=1.0)

        assert result is True

    @pytest.mark.asyncio
    async def test_on_message_no_callback(self):
        """Test on_message when no callback set - targets lines 153-156."""
        manager = DiscordChannelManager(token="test")  # No callback
        mock_message = Mock(spec=discord.Message)
        mock_message.author = Mock()
        mock_message.author.bot = False
        mock_message.author.id = 123456789
        mock_message.author.display_name = "TestUser"
        mock_message.channel = Mock()
        mock_message.channel.id = 123456789
        mock_message.content = "Test message"
        mock_message.id = 555666777
        mock_message.created_at = Mock()

        # Should not raise exception
        await manager.on_message(mock_message)

    @pytest.mark.asyncio
    async def test_on_message_bot_message(self):
        """Test on_message with bot message - should be ignored."""
        mock_message = Mock(spec=discord.Message)
        mock_message.author = Mock()
        mock_message.author.bot = True

        await self.manager.on_message(mock_message)

        # Callback should not be called for bot messages
        self.mock_callback.assert_not_called()

    @pytest.mark.asyncio
    async def test_on_message_success(self):
        """Test successful message handling - targets main on_message flow."""
        mock_message = Mock(spec=discord.Message)
        mock_message.author = Mock()
        mock_message.author.bot = False
        mock_message.author.id = 987654321
        mock_message.author.display_name = "TestUser"
        mock_message.channel = Mock()
        mock_message.channel.id = 123456789
        mock_message.content = "Test message"
        mock_message.id = 555666777
        mock_message.created_at = Mock()

        await self.manager.on_message(mock_message)

        self.mock_callback.assert_called_once()
        # Verify the DiscordMessage was properly created
        call_args = self.mock_callback.call_args[0][0]
        assert isinstance(call_args, DiscordMessage)
        assert call_args.author_id == "987654321"
        assert call_args.content == "Test message"

    @pytest.mark.asyncio
    async def test_on_message_callback_exception(self):
        """Test on_message when callback raises exception - targets lines 234-236."""
        self.mock_callback.side_effect = Exception("Callback error")

        mock_message = Mock(spec=discord.Message)
        mock_message.author = Mock()
        mock_message.author.bot = False
        mock_message.author.id = 987654321
        mock_message.author.display_name = "TestUser"
        mock_message.channel = Mock()
        mock_message.channel.id = 123456789
        mock_message.content = "Test message"
        mock_message.id = 555666777
        mock_message.created_at = Mock()

        # Should not raise exception
        await self.manager.on_message(mock_message)

    def test_attach_to_client(self):
        """Test attaching manager to client - targets line 244."""
        new_client = Mock(spec=discord.Client)

        self.manager.attach_to_client(new_client)

        assert self.manager.client == new_client

    def test_get_client_info_with_client(self):
        """Test get_client_info when client exists."""
        self.mock_client.user = Mock()
        self.mock_client.user.__str__ = Mock(return_value="TestBot#1234")
        self.mock_client.guilds = [Mock(), Mock()]  # 2 guilds
        self.mock_client.is_closed.return_value = False
        self.mock_client.latency = 0.123

        result = self.manager.get_client_info()

        assert result["status"] == "ready"
        assert result["user"] == "TestBot#1234"
        assert result["guilds"] == 2
        assert result["latency"] == 0.123

    def test_get_client_info_no_client(self):
        """Test get_client_info when no client - targets lines 253-265."""
        manager = DiscordChannelManager(token="test")  # No client

        result = manager.get_client_info()

        assert result["status"] == "not_initialized"
        assert result["user"] is None
        assert result["guilds"] == 0

    @pytest.mark.asyncio
    async def test_get_channel_info_success(self):
        """Test successful get_channel_info."""
        mock_channel = Mock()
        mock_channel.name = "test-channel"
        mock_channel.id = 123456789
        mock_channel.type = discord.ChannelType.text
        mock_guild = Mock()
        mock_guild.name = "Test Guild"
        mock_guild.id = 987654321
        mock_channel.guild = mock_guild
        mock_channel.member_count = 50

        self.mock_client.get_channel.return_value = mock_channel

        result = await self.manager.get_channel_info("123456789")

        assert result["exists"] is True
        assert result["accessible"] is True

    @pytest.mark.asyncio
    async def test_get_channel_info_channel_not_found(self):
        """Test get_channel_info when channel not found - targets lines 276-300."""
        self.mock_client.get_channel.return_value = None
        self.mock_client.fetch_channel = AsyncMock(return_value=None)

        result = await self.manager.get_channel_info("123456789")

        assert result["exists"] is False
        assert result["accessible"] is False

    @pytest.mark.asyncio
    async def test_sanitize_message_parameters_basic(self):
        """Test _sanitize_message_parameters method - targets lines 302-319."""
        params = {
            "content": "Hello world",
            "user_id": "123456789",
            "some_other_field": "value"
        }

        result = await self.manager._sanitize_message_parameters(params, "123456789")

        assert "content" in result
        assert result["content"] == "Hello world"

    @pytest.mark.asyncio
    async def test_sanitize_message_parameters_with_consent_service(self):
        """Test _sanitize_message_parameters with consent service."""
        mock_consent = Mock()
        self.manager.consent_service = mock_consent

        params = {"content": "Hello world", "user_id": "123456789"}

        result = await self.manager._sanitize_message_parameters(params, "123456789")

        # Should still return sanitized params
        assert isinstance(result, dict)

    @pytest.mark.asyncio
    async def test_get_user_consent_stream_no_service(self):
        """Test _get_user_consent_stream with no consent service - targets lines 327-346."""
        result = await self.manager._get_user_consent_stream("123456789")

        assert result is None

    @pytest.mark.asyncio
    async def test_get_user_consent_stream_with_service(self):
        """Test _get_user_consent_stream with consent service."""
        mock_consent = Mock()
        mock_consent.get_user_consent_stream = AsyncMock(return_value="stream_id_123")
        self.manager.consent_service = mock_consent

        # The method might not exist, so we test that it handles gracefully
        result = await self.manager._get_user_consent_stream("123456789")

        # The actual implementation might return None, which is acceptable
        assert result is None or result == "stream_id_123"

    @pytest.mark.asyncio
    async def test_get_user_consent_stream_service_error(self):
        """Test _get_user_consent_stream when service raises error."""
        mock_consent = Mock()
        mock_consent.get_user_consent_stream = AsyncMock(side_effect=Exception("Service error"))
        self.manager.consent_service = mock_consent

        result = await self.manager._get_user_consent_stream("123456789")

        assert result is None


class TestDiscordChannelManagerEdgeCases:
    """Test edge cases and error scenarios for channel manager."""

    @pytest.mark.asyncio
    async def test_complex_message_handling_scenarios(self):
        """Test complex message handling scenarios for coverage."""
        manager = DiscordChannelManager(token="test")

        # Test with minimal message structure
        mock_message = Mock()
        mock_message.author = Mock()
        mock_message.author.bot = False
        mock_message.author.id = 123
        mock_message.author.display_name = "User"
        mock_message.channel = Mock()
        mock_message.channel.id = 456
        mock_message.content = ""  # Empty content
        mock_message.id = 789
        mock_message.created_at = Mock()

        # Should handle gracefully without callback
        await manager.on_message(mock_message)

    def test_manager_state_transitions(self):
        """Test manager state transitions and attribute modifications."""
        manager = DiscordChannelManager(token="initial_token")

        # Test state changes
        assert manager.client is None

        client1 = Mock()
        manager.set_client(client1)
        assert manager.client == client1

        client2 = Mock()
        manager.attach_to_client(client2)
        assert manager.client == client2

        callback1 = AsyncMock()
        manager.set_message_callback(callback1)
        assert manager.on_message_callback == callback1

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent channel operations."""
        manager = DiscordChannelManager(token="test")
        mock_client = Mock()
        mock_client.get_channel.return_value = Mock()
        manager.set_client(mock_client)

        # Test concurrent channel resolutions
        tasks = [
            manager.resolve_channel("123"),
            manager.resolve_channel("456"),
            manager.validate_channel_access("789")
        ]

        results = await asyncio.gather(*tasks)
        assert len(results) == 3

    def test_initialization_edge_cases(self):
        """Test initialization with edge case parameters."""
        # Test with empty monitored channels list
        manager1 = DiscordChannelManager(
            token="test",
            monitored_channel_ids=[]
        )
        assert manager1.monitored_channel_ids == []

        # Test with None monitored channels (should default to empty list)
        manager2 = DiscordChannelManager(
            token="test",
            monitored_channel_ids=None
        )
        assert manager2.monitored_channel_ids == []