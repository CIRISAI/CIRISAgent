"""
Comprehensive unit tests for CIRISDiscordClient.

This test suite focuses on the Discord client class itself, testing:
- Initialization
- Event handlers (on_ready, on_disconnect, on_message, on_reaction, on_thread_*)
- Thread monitoring and fetching
- Error handling and edge cases
- Integration with platform components
"""

import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import discord
import pytest

from ciris_engine.logic.adapters.discord.ciris_discord_client import \
    CIRISDiscordClient

logger = logging.getLogger(__name__)


class TestCIRISDiscordClientInit:
    """Test CIRISDiscordClient initialization."""

    def test_init_with_platform(self):
        """Test client initialization with platform."""
        mock_platform = Mock()

        # Mock discord.Client.__init__ to avoid Discord connection
        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        assert client.platform is mock_platform

    def test_init_with_args_and_kwargs(self):
        """Test client initialization with additional args and kwargs."""
        mock_platform = Mock()

        with patch("discord.Client.__init__", return_value=None) as mock_init:
            client = CIRISDiscordClient(
                platform=mock_platform, intents=discord.Intents.default(), activity=discord.Game(name="test")
            )

        assert client.platform is mock_platform
        # Verify args were passed to parent
        assert mock_init.called


class TestCIRISDiscordClientOnReady:
    """Test on_ready event handler."""

    @pytest.mark.asyncio
    async def test_on_ready_calls_connection_manager(self):
        """Test on_ready calls connection manager's _handle_connected."""
        mock_platform = Mock()
        mock_conn_mgr = Mock()
        mock_conn_mgr._handle_connected = AsyncMock()
        mock_platform.discord_adapter = Mock()
        mock_platform.discord_adapter._connection_manager = mock_conn_mgr

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        # Mock _fetch_threads_in_monitored_channels
        client._fetch_threads_in_monitored_channels = AsyncMock()

        await client.on_ready()

        mock_conn_mgr._handle_connected.assert_awaited_once()
        client._fetch_threads_in_monitored_channels.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_ready_no_adapter(self):
        """Test on_ready when discord_adapter is missing."""
        mock_platform = Mock()
        mock_platform.discord_adapter = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        client._fetch_threads_in_monitored_channels = AsyncMock()

        # Should not crash
        await client.on_ready()

        client._fetch_threads_in_monitored_channels.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_ready_no_connection_manager(self):
        """Test on_ready when connection manager is missing."""
        mock_platform = Mock()
        mock_platform.discord_adapter = Mock()
        mock_platform.discord_adapter._connection_manager = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        client._fetch_threads_in_monitored_channels = AsyncMock()

        # Should not crash
        await client.on_ready()

        client._fetch_threads_in_monitored_channels.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_on_ready_connection_manager_missing_method(self):
        """Test on_ready when connection manager lacks _handle_connected."""
        mock_platform = Mock()
        mock_conn_mgr = Mock(spec=[])  # Empty spec - no methods
        mock_platform.discord_adapter = Mock()
        mock_platform.discord_adapter._connection_manager = mock_conn_mgr

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        client._fetch_threads_in_monitored_channels = AsyncMock()

        # Should not crash
        await client.on_ready()

        client._fetch_threads_in_monitored_channels.assert_awaited_once()


class TestCIRISDiscordClientFetchThreads:
    """Test _fetch_threads_in_monitored_channels method."""

    @pytest.mark.asyncio
    async def test_fetch_threads_no_config(self):
        """Test _fetch_threads_in_monitored_channels when config is missing."""
        mock_platform = Mock()
        mock_platform.config = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        # Should return early without error
        await client._fetch_threads_in_monitored_channels()

    @pytest.mark.asyncio
    async def test_fetch_threads_no_platform_config_attr(self):
        """Test _fetch_threads_in_monitored_channels when platform lacks config."""
        mock_platform = Mock(spec=[])  # No config attribute

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        # Should return early without error
        await client._fetch_threads_in_monitored_channels()

    @pytest.mark.asyncio
    async def test_fetch_threads_adds_threads_to_monitoring(self):
        """Test _fetch_threads_in_monitored_channels adds threads to observer."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        # Create mock channel with threads
        mock_thread1 = Mock(spec=discord.Thread)
        mock_thread1.id = 111111111
        mock_thread2 = Mock(spec=discord.Thread)
        mock_thread2.id = 222222222

        mock_channel = Mock(spec=discord.TextChannel)
        mock_channel.threads = [mock_thread1, mock_thread2]

        client.get_channel = Mock(return_value=mock_channel)

        await client._fetch_threads_in_monitored_channels()

        # Both threads should be added
        assert "111111111" in mock_platform.discord_observer.monitored_channel_ids
        assert "222222222" in mock_platform.discord_observer.monitored_channel_ids

    @pytest.mark.asyncio
    async def test_fetch_threads_skips_already_monitored(self):
        """Test _fetch_threads_in_monitored_channels skips already monitored threads."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = ["111111111"]  # Already monitored

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread1 = Mock(spec=discord.Thread)
        mock_thread1.id = 111111111  # Already in list
        mock_thread2 = Mock(spec=discord.Thread)
        mock_thread2.id = 222222222  # New

        mock_channel = Mock(spec=discord.TextChannel)
        mock_channel.threads = [mock_thread1, mock_thread2]

        client.get_channel = Mock(return_value=mock_channel)

        await client._fetch_threads_in_monitored_channels()

        # Should only add the new one
        assert mock_platform.discord_observer.monitored_channel_ids.count("111111111") == 1
        assert "222222222" in mock_platform.discord_observer.monitored_channel_ids

    @pytest.mark.asyncio
    async def test_fetch_threads_handles_channel_not_found(self):
        """Test _fetch_threads_in_monitored_channels handles missing channels."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        client.get_channel = Mock(return_value=None)  # Channel not found

        # Should not crash
        await client._fetch_threads_in_monitored_channels()

        assert mock_platform.discord_observer.monitored_channel_ids == []

    @pytest.mark.asyncio
    async def test_fetch_threads_handles_non_text_channel(self):
        """Test _fetch_threads_in_monitored_channels handles non-text channels."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        # Return a voice channel instead
        mock_channel = Mock(spec=discord.VoiceChannel)
        client.get_channel = Mock(return_value=mock_channel)

        # Should not crash
        await client._fetch_threads_in_monitored_channels()

        assert mock_platform.discord_observer.monitored_channel_ids == []

    @pytest.mark.asyncio
    async def test_fetch_threads_handles_exception(self):
        """Test _fetch_threads_in_monitored_channels handles exceptions gracefully."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        client.get_channel = Mock(side_effect=Exception("API error"))

        # Should not crash, just log warning
        await client._fetch_threads_in_monitored_channels()

        assert mock_platform.discord_observer.monitored_channel_ids == []

    @pytest.mark.asyncio
    async def test_fetch_threads_multiple_channels(self):
        """Test _fetch_threads_in_monitored_channels with multiple channels."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["111", "222", "333"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        # Create threads for each channel
        channels = {}
        for i, channel_id in enumerate(["111", "222", "333"]):
            mock_thread = Mock(spec=discord.Thread)
            mock_thread.id = int(f"{i}00000000")

            mock_channel = Mock(spec=discord.TextChannel)
            mock_channel.threads = [mock_thread]
            channels[channel_id] = mock_channel

        client.get_channel = lambda cid: channels.get(str(cid))

        await client._fetch_threads_in_monitored_channels()

        # Should have 3 threads
        assert len(mock_platform.discord_observer.monitored_channel_ids) == 3

    @pytest.mark.asyncio
    async def test_fetch_threads_no_observer(self):
        """Test _fetch_threads_in_monitored_channels when observer is missing."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 111111111

        mock_channel = Mock(spec=discord.TextChannel)
        mock_channel.threads = [mock_thread]

        client.get_channel = Mock(return_value=mock_channel)

        # Should not crash
        await client._fetch_threads_in_monitored_channels()


class TestCIRISDiscordClientOnDisconnect:
    """Test on_disconnect event handler."""

    @pytest.mark.asyncio
    async def test_on_disconnect_calls_connection_manager(self):
        """Test on_disconnect calls connection manager's _handle_disconnected."""
        mock_platform = Mock()
        mock_conn_mgr = Mock()
        mock_conn_mgr._handle_disconnected = AsyncMock()
        mock_platform.discord_adapter = Mock()
        mock_platform.discord_adapter._connection_manager = mock_conn_mgr

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        await client.on_disconnect()

        mock_conn_mgr._handle_disconnected.assert_awaited_once_with(None)

    @pytest.mark.asyncio
    async def test_on_disconnect_no_adapter(self):
        """Test on_disconnect when discord_adapter is missing."""
        mock_platform = Mock()
        mock_platform.discord_adapter = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        # Should not crash
        await client.on_disconnect()

    @pytest.mark.asyncio
    async def test_on_disconnect_no_connection_manager(self):
        """Test on_disconnect when connection manager is missing."""
        mock_platform = Mock()
        mock_platform.discord_adapter = Mock()
        mock_platform.discord_adapter._connection_manager = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        # Should not crash
        await client.on_disconnect()

    @pytest.mark.asyncio
    async def test_on_disconnect_connection_manager_missing_method(self):
        """Test on_disconnect when connection manager lacks _handle_disconnected."""
        mock_platform = Mock()
        mock_conn_mgr = Mock(spec=[])  # Empty spec - no methods
        mock_platform.discord_adapter = Mock()
        mock_platform.discord_adapter._connection_manager = mock_conn_mgr

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        # Should not crash
        await client.on_disconnect()


class TestCIRISDiscordClientOnMessage:
    """Test on_message event handler."""

    @pytest.mark.asyncio
    async def test_on_message_calls_channel_manager(self):
        """Test on_message calls channel manager's on_message."""
        mock_platform = Mock()
        mock_channel_mgr = Mock()
        mock_channel_mgr.on_message = AsyncMock()
        mock_platform.discord_adapter = Mock()
        mock_platform.discord_adapter._channel_manager = mock_channel_mgr

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_message = Mock(spec=discord.Message)

        await client.on_message(mock_message)

        mock_channel_mgr.on_message.assert_awaited_once_with(mock_message)

    @pytest.mark.asyncio
    async def test_on_message_no_adapter(self):
        """Test on_message when discord_adapter is missing."""
        mock_platform = Mock()
        mock_platform.discord_adapter = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_message = Mock(spec=discord.Message)

        # Should not crash
        await client.on_message(mock_message)

    @pytest.mark.asyncio
    async def test_on_message_no_channel_manager(self):
        """Test on_message when channel manager is missing."""
        mock_platform = Mock()
        mock_platform.discord_adapter = Mock()
        mock_platform.discord_adapter._channel_manager = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_message = Mock(spec=discord.Message)

        # Should not crash
        await client.on_message(mock_message)

    @pytest.mark.asyncio
    async def test_on_message_channel_manager_missing_method(self):
        """Test on_message when channel manager lacks on_message method."""
        mock_platform = Mock()
        mock_channel_mgr = Mock(spec=[])  # Empty spec - no methods
        mock_platform.discord_adapter = Mock()
        mock_platform.discord_adapter._channel_manager = mock_channel_mgr

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_message = Mock(spec=discord.Message)

        # Should not crash
        await client.on_message(mock_message)


class TestCIRISDiscordClientOnReactionAdd:
    """Test on_raw_reaction_add event handler."""

    @pytest.mark.asyncio
    async def test_on_raw_reaction_add_calls_adapter(self):
        """Test on_raw_reaction_add calls adapter's on_raw_reaction_add."""
        mock_platform = Mock()
        mock_platform.discord_adapter = Mock()
        mock_platform.discord_adapter.on_raw_reaction_add = AsyncMock()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_payload = Mock(spec=discord.RawReactionActionEvent)

        await client.on_raw_reaction_add(mock_payload)

        mock_platform.discord_adapter.on_raw_reaction_add.assert_awaited_once_with(mock_payload)

    @pytest.mark.asyncio
    async def test_on_raw_reaction_add_no_adapter(self):
        """Test on_raw_reaction_add when discord_adapter is missing."""
        mock_platform = Mock()
        mock_platform.discord_adapter = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_payload = Mock(spec=discord.RawReactionActionEvent)

        # Should not crash
        await client.on_raw_reaction_add(mock_payload)


class TestCIRISDiscordClientOnThreadCreate:
    """Test on_thread_create event handler."""

    @pytest.mark.asyncio
    async def test_on_thread_create_monitored_parent(self):
        """Test on_thread_create adds thread when parent is monitored."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []
        mock_platform.discord_adapter = Mock()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 999999999
        mock_thread.parent_id = 123456789
        mock_thread.name = "Test Thread"

        await client.on_thread_create(mock_thread)

        assert "999999999" in mock_platform.discord_observer.monitored_channel_ids

    @pytest.mark.asyncio
    async def test_on_thread_create_unmonitored_parent(self):
        """Test on_thread_create ignores thread when parent is not monitored."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []
        mock_platform.discord_adapter = Mock()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 999999999
        mock_thread.parent_id = 111111111  # Not monitored
        mock_thread.name = "Test Thread"

        await client.on_thread_create(mock_thread)

        assert "999999999" not in mock_platform.discord_observer.monitored_channel_ids

    @pytest.mark.asyncio
    async def test_on_thread_create_already_monitored(self):
        """Test on_thread_create skips already monitored thread."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = ["999999999"]
        mock_platform.discord_adapter = Mock()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 999999999
        mock_thread.parent_id = 123456789
        mock_thread.name = "Test Thread"

        await client.on_thread_create(mock_thread)

        # Should not be added twice
        assert mock_platform.discord_observer.monitored_channel_ids.count("999999999") == 1

    @pytest.mark.asyncio
    async def test_on_thread_create_no_config(self):
        """Test on_thread_create when config is missing."""
        mock_platform = Mock()
        mock_platform.config = None
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []
        mock_platform.discord_adapter = Mock()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 999999999
        mock_thread.parent_id = 123456789
        mock_thread.name = "Test Thread"

        # Should not crash
        await client.on_thread_create(mock_thread)

    @pytest.mark.asyncio
    async def test_on_thread_create_no_observer(self):
        """Test on_thread_create when observer is missing."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = None
        mock_platform.discord_adapter = Mock()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 999999999
        mock_thread.parent_id = 123456789
        mock_thread.name = "Test Thread"

        # Should not crash
        await client.on_thread_create(mock_thread)

    @pytest.mark.asyncio
    async def test_on_thread_create_no_adapter(self):
        """Test on_thread_create when adapter is missing."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []
        mock_platform.discord_adapter = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 999999999
        mock_thread.parent_id = 123456789
        mock_thread.name = "Test Thread"

        # Should not crash
        await client.on_thread_create(mock_thread)


class TestCIRISDiscordClientOnThreadJoin:
    """Test on_thread_join event handler."""

    @pytest.mark.asyncio
    async def test_on_thread_join_delegates_to_create(self):
        """Test on_thread_join delegates to on_thread_create."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []
        mock_platform.discord_adapter = Mock()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        # Mock on_thread_create to verify it's called
        client.on_thread_create = AsyncMock()

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 888888888
        mock_thread.parent_id = 123456789
        mock_thread.name = "Joined Thread"

        await client.on_thread_join(mock_thread)

        client.on_thread_create.assert_awaited_once_with(mock_thread)

    @pytest.mark.asyncio
    async def test_on_thread_join_adds_thread_to_monitoring(self):
        """Test on_thread_join adds thread to monitoring (via on_thread_create)."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []
        mock_platform.discord_adapter = Mock()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 888888888
        mock_thread.parent_id = 123456789
        mock_thread.name = "Joined Thread"

        await client.on_thread_join(mock_thread)

        # Should be added via on_thread_create
        assert "888888888" in mock_platform.discord_observer.monitored_channel_ids


class TestCIRISDiscordClientOnThreadDelete:
    """Test on_thread_delete event handler."""

    @pytest.mark.asyncio
    async def test_on_thread_delete_removes_from_monitoring(self):
        """Test on_thread_delete removes thread from monitoring."""
        mock_platform = Mock()
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = ["777777777", "888888888"]

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 777777777
        mock_thread.name = "Deleted Thread"

        await client.on_thread_delete(mock_thread)

        assert "777777777" not in mock_platform.discord_observer.monitored_channel_ids
        assert "888888888" in mock_platform.discord_observer.monitored_channel_ids

    @pytest.mark.asyncio
    async def test_on_thread_delete_handles_not_monitored(self):
        """Test on_thread_delete handles thread not in monitoring."""
        mock_platform = Mock()
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = ["888888888"]

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 999999999  # Not in list
        mock_thread.name = "Unknown Thread"

        # Should not crash
        await client.on_thread_delete(mock_thread)

        # List unchanged
        assert mock_platform.discord_observer.monitored_channel_ids == ["888888888"]

    @pytest.mark.asyncio
    async def test_on_thread_delete_no_observer(self):
        """Test on_thread_delete when observer is missing."""
        mock_platform = Mock()
        mock_platform.discord_observer = None

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 777777777
        mock_thread.name = "Deleted Thread"

        # Should not crash
        await client.on_thread_delete(mock_thread)

    @pytest.mark.asyncio
    async def test_on_thread_delete_empty_monitoring_list(self):
        """Test on_thread_delete with empty monitoring list."""
        mock_platform = Mock()
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 777777777
        mock_thread.name = "Deleted Thread"

        # Should not crash
        await client.on_thread_delete(mock_thread)

        assert mock_platform.discord_observer.monitored_channel_ids == []


class TestCIRISDiscordClientEdgeCases:
    """Test edge cases and error scenarios."""

    def test_platform_type_checking(self):
        """Test client works with different platform types."""
        # Test with a completely minimal platform
        minimal_platform = type("MinimalPlatform", (), {})()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=minimal_platform)

        assert client.platform is minimal_platform

    @pytest.mark.asyncio
    async def test_all_handlers_with_minimal_platform(self):
        """Test all event handlers work with minimal platform."""
        minimal_platform = type("MinimalPlatform", (), {})()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=minimal_platform)

        # All these should not crash
        await client.on_ready()
        await client.on_disconnect()
        await client.on_message(Mock(spec=discord.Message))
        await client.on_raw_reaction_add(Mock(spec=discord.RawReactionActionEvent))
        await client.on_thread_create(Mock(spec=discord.Thread, id=123, parent_id=456, name="test"))
        await client.on_thread_join(Mock(spec=discord.Thread, id=123, parent_id=456, name="test"))
        await client.on_thread_delete(Mock(spec=discord.Thread, id=123, name="test"))

    @pytest.mark.asyncio
    async def test_fetch_threads_with_empty_channel_list(self):
        """Test _fetch_threads_in_monitored_channels with empty channel list."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = []
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        await client._fetch_threads_in_monitored_channels()

        # Should complete without adding anything
        assert mock_platform.discord_observer.monitored_channel_ids == []

    @pytest.mark.asyncio
    async def test_fetch_threads_with_empty_threads_list(self):
        """Test _fetch_threads_in_monitored_channels when channel has no threads."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_channel = Mock(spec=discord.TextChannel)
        mock_channel.threads = []  # No threads

        client.get_channel = Mock(return_value=mock_channel)

        await client._fetch_threads_in_monitored_channels()

        assert mock_platform.discord_observer.monitored_channel_ids == []

    @pytest.mark.asyncio
    async def test_thread_id_string_conversion(self):
        """Test that thread IDs are properly converted to strings."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []
        mock_platform.discord_adapter = Mock()

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 999999999  # Integer
        mock_thread.parent_id = 123456789  # Integer
        mock_thread.name = "Test Thread"

        await client.on_thread_create(mock_thread)

        # Should be stored as string
        assert "999999999" in mock_platform.discord_observer.monitored_channel_ids
        assert 999999999 not in mock_platform.discord_observer.monitored_channel_ids

    @pytest.mark.asyncio
    async def test_channel_id_string_conversion_in_fetch(self):
        """Test that channel IDs are properly converted to integers in get_channel."""
        mock_platform = Mock()
        mock_platform.config = Mock()
        mock_platform.config.monitored_channel_ids = ["123456789"]  # String
        mock_platform.discord_observer = Mock()
        mock_platform.discord_observer.monitored_channel_ids = []

        with patch("discord.Client.__init__", return_value=None):
            client = CIRISDiscordClient(platform=mock_platform)

        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 111111111

        mock_channel = Mock(spec=discord.TextChannel)
        mock_channel.threads = [mock_thread]

        get_channel_calls = []

        def track_get_channel(channel_id):
            get_channel_calls.append((channel_id, type(channel_id)))
            return mock_channel

        client.get_channel = track_get_channel

        await client._fetch_threads_in_monitored_channels()

        # Verify get_channel was called with integer
        assert len(get_channel_calls) == 1
        assert get_channel_calls[0][1] == int
        assert get_channel_calls[0][0] == 123456789
