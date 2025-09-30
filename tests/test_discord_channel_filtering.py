"""
Regression test for Discord channel filtering.

Ensures that Discord only creates correlations for monitored channels,
not every single message from every channel the bot can see.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.adapters.discord.discord_channel_manager import DiscordChannelManager


class TestDiscordChannelFiltering:
    """Test Discord channel filtering for correlations."""

    @pytest.fixture
    def mock_message(self):
        """Create a mock Discord message."""
        message = MagicMock()
        message.id = 123456789
        message.content = "Test message"
        message.author.id = 987654321
        message.author.display_name = "TestUser"
        message.author.bot = False
        message.channel.id = 111222333
        message.guild.id = 444555666
        return message

    @pytest.mark.asyncio
    async def test_correlation_created_for_monitored_channel(self, mock_message):
        """Test that correlations are created for monitored channels."""
        monitored_channels = ["discord_444555666_111222333", "111222333"]

        channel_manager = DiscordChannelManager(
            token="test_token", client=None, on_message_callback=None, monitored_channel_ids=monitored_channels
        )

        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation:
            await channel_manager.on_message(mock_message)

            # Correlation should be created for monitored channel
            assert mock_add_correlation.called, "Correlation should be created for monitored channel"

            # Verify the correlation details
            correlation = mock_add_correlation.call_args[0][0]
            assert correlation.service_type == "discord"
            assert correlation.action_type == "observe"
            assert "discord_444555666_111222333" in correlation.request_data.channel_id

    @pytest.mark.asyncio
    async def test_no_correlation_for_unmonitored_channel(self, mock_message):
        """Test that correlations are NOT created for unmonitored channels."""
        monitored_channels = ["999888777"]  # Different channel ID

        channel_manager = DiscordChannelManager(
            token="test_token", client=None, on_message_callback=None, monitored_channel_ids=monitored_channels
        )

        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation:
            await channel_manager.on_message(mock_message)

            # Correlation should NOT be created for unmonitored channel
            assert not mock_add_correlation.called, "Correlation should NOT be created for unmonitored channel"

    @pytest.mark.asyncio
    async def test_monitor_all_when_no_channels_specified(self, mock_message):
        """Test that all channels are monitored when no specific channels are configured."""
        channel_manager = DiscordChannelManager(
            token="test_token",
            client=None,
            on_message_callback=None,
            monitored_channel_ids=[],  # Empty list = monitor all
        )

        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation:
            await channel_manager.on_message(mock_message)

            # Correlation should be created when monitoring all channels
            assert mock_add_correlation.called, "Correlation should be created when monitoring all channels"

    @pytest.mark.asyncio
    async def test_bot_own_messages_ignored(self, mock_message):
        """Test that the bot's own messages never create correlations."""
        # Set up mock client with bot user
        mock_client = MagicMock()
        mock_client.user = MagicMock()
        mock_client.user.id = 987654321  # Same as message author

        mock_message.author.bot = True
        mock_message.author.id = 987654321  # Bot's own message

        channel_manager = DiscordChannelManager(
            token="test_token", client=mock_client, on_message_callback=None, monitored_channel_ids=[]  # Monitor all
        )

        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation:
            await channel_manager.on_message(mock_message)

            # Correlation should NOT be created for bot's own messages
            assert not mock_add_correlation.called, "Correlation should NOT be created for bot's own messages"

    @pytest.mark.asyncio
    async def test_other_bot_messages_observed(self, mock_message):
        """Test that other bots' messages DO create correlations."""
        # Set up mock client with bot user
        mock_client = MagicMock()
        mock_client.user = MagicMock()
        mock_client.user.id = 111111111  # Different from message author

        mock_message.author.bot = True
        mock_message.author.id = 987654321  # Different bot

        channel_manager = DiscordChannelManager(
            token="test_token", client=mock_client, on_message_callback=None, monitored_channel_ids=[]  # Monitor all
        )

        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation:
            await channel_manager.on_message(mock_message)

            # Correlation SHOULD be created for other bots' messages
            assert mock_add_correlation.called, "Correlation should be created for other bots' messages"

    @pytest.mark.asyncio
    async def test_callback_still_invoked_for_unmonitored(self, mock_message):
        """Test that message callback is still invoked even for unmonitored channels."""
        monitored_channels = ["999888777"]  # Different channel
        callback_invoked = False

        async def test_callback(message):
            nonlocal callback_invoked
            callback_invoked = True

        channel_manager = DiscordChannelManager(
            token="test_token", client=None, on_message_callback=test_callback, monitored_channel_ids=monitored_channels
        )

        with patch("ciris_engine.logic.persistence.add_correlation"):
            await channel_manager.on_message(mock_message)

            # Callback should still be invoked
            assert callback_invoked, "Message callback should be invoked regardless of monitoring"

    @pytest.mark.asyncio
    async def test_channel_id_formats_supported(self, mock_message):
        """Test that both raw and formatted channel IDs are supported."""
        # Test with raw channel ID
        monitored_channels = ["111222333"]  # Raw channel ID

        channel_manager = DiscordChannelManager(
            token="test_token", client=None, on_message_callback=None, monitored_channel_ids=monitored_channels
        )

        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation:
            await channel_manager.on_message(mock_message)
            assert mock_add_correlation.called, "Should match on raw channel ID"

        # Test with formatted channel ID
        monitored_channels = ["discord_444555666_111222333"]  # Formatted

        channel_manager = DiscordChannelManager(
            token="test_token", client=None, on_message_callback=None, monitored_channel_ids=monitored_channels
        )

        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation:
            await channel_manager.on_message(mock_message)
            assert mock_add_correlation.called, "Should match on formatted channel ID"

    @pytest.mark.asyncio
    async def test_dm_channel_handling(self, mock_message):
        """Test that DM channels are handled correctly."""
        # Simulate a DM (no guild)
        mock_message.guild = None

        channel_manager = DiscordChannelManager(
            token="test_token", client=None, on_message_callback=None, monitored_channel_ids=[]  # Monitor all
        )

        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation:
            await channel_manager.on_message(mock_message)

            # Should still create correlation for DMs when monitoring all
            assert mock_add_correlation.called

            # Check that channel ID is formatted correctly for DM
            correlation = mock_add_correlation.call_args[0][0]
            assert "discord_dm_" in correlation.request_data.channel_id
