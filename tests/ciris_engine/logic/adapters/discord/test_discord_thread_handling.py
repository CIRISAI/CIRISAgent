"""Unit tests for Discord thread handling in adapter.py"""

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest

logger = logging.getLogger(__name__)


class TestDiscordThreadHandling:
    """Test Discord thread event handlers."""

    @pytest.fixture
    def mock_platform(self):
        """Create a mock DiscordPlatform with all necessary attributes."""
        platform = Mock()

        # Mock config
        platform.config = Mock()
        platform.config.monitored_channel_ids = ["123456789", "987654321"]

        # Mock observer
        platform.discord_observer = Mock()
        platform.discord_observer.monitored_channel_ids = []

        # Mock adapter
        platform.discord_adapter = Mock()
        conn_mgr = Mock()
        conn_mgr._handle_connected = AsyncMock()
        platform.discord_adapter._connection_manager = conn_mgr

        return platform

    @pytest.fixture
    def mock_discord_client(self, mock_platform):
        """Create a mock CIRISDiscordClient."""
        # Import here to avoid circular dependency
        from ciris_engine.logic.adapters.discord.adapter import DiscordPlatform

        # Create the inner class
        class CIRISDiscordClient(discord.Client):
            def __init__(self, platform, *args, **kwargs):
                # Don't call super().__init__ as it needs real Discord connection
                self.platform = platform
                self._closed = False

            def get_channel(self, channel_id):
                """Mock get_channel method."""
                return None

        client = CIRISDiscordClient(platform=mock_platform)
        return client

    @pytest.mark.asyncio
    async def test_on_thread_create_monitored_parent(self, mock_discord_client, mock_platform):
        """Test on_thread_create when parent channel is monitored."""
        # Create a mock thread
        thread = Mock(spec=discord.Thread)
        thread.id = 555555555
        thread.parent_id = 123456789  # This is in monitored_channel_ids
        thread.name = "Test Thread"

        # Call the handler
        await mock_discord_client.on_thread_create(thread)

        # Verify thread was added to monitored channels
        assert "555555555" in mock_platform.discord_observer.monitored_channel_ids

    @pytest.mark.asyncio
    async def test_on_thread_create_unmonitored_parent(self, mock_discord_client, mock_platform):
        """Test on_thread_create when parent channel is NOT monitored."""
        # Create a mock thread
        thread = Mock(spec=discord.Thread)
        thread.id = 666666666
        thread.parent_id = 111111111  # This is NOT in monitored_channel_ids
        thread.name = "Unmonitored Thread"

        # Call the handler
        await mock_discord_client.on_thread_create(thread)

        # Verify thread was NOT added to monitored channels
        assert "666666666" not in mock_platform.discord_observer.monitored_channel_ids

    @pytest.mark.asyncio
    async def test_on_thread_create_stores_correlation(self, mock_discord_client, mock_platform):
        """Test that on_thread_create stores correlation for persistence."""
        thread = Mock(spec=discord.Thread)
        thread.id = 777777777
        thread.parent_id = 123456789
        thread.name = "Persistent Thread"

        with patch("ciris_engine.logic.adapters.discord.adapter.add_correlation") as mock_add_correlation:
            await mock_discord_client.on_thread_create(thread)

            # Verify correlation was stored
            mock_add_correlation.assert_called_once()
            correlation = mock_add_correlation.call_args[0][0]
            assert correlation.correlation_type == "discord_thread"
            assert correlation.source_id == "777777777"
            assert correlation.target_id == "123456789"
            assert correlation.metadata["monitored"] is True
            assert correlation.metadata["thread_name"] == "Persistent Thread"

    @pytest.mark.asyncio
    async def test_on_thread_join_calls_create(self, mock_discord_client):
        """Test that on_thread_join delegates to on_thread_create."""
        thread = Mock(spec=discord.Thread)
        thread.id = 888888888
        thread.parent_id = 123456789
        thread.name = "Joined Thread"

        # Mock on_thread_create
        mock_discord_client.on_thread_create = AsyncMock()

        await mock_discord_client.on_thread_join(thread)

        # Verify it called on_thread_create
        mock_discord_client.on_thread_create.assert_called_once_with(thread)

    @pytest.mark.asyncio
    async def test_on_thread_delete_removes_from_monitoring(self, mock_discord_client, mock_platform):
        """Test that on_thread_delete removes thread from monitoring."""
        # Add a thread to monitoring first
        mock_platform.discord_observer.monitored_channel_ids = ["999999999", "888888888"]

        thread = Mock(spec=discord.Thread)
        thread.id = 999999999
        thread.name = "Deleted Thread"

        await mock_discord_client.on_thread_delete(thread)

        # Verify thread was removed from monitored channels
        assert "999999999" not in mock_platform.discord_observer.monitored_channel_ids
        assert "888888888" in mock_platform.discord_observer.monitored_channel_ids  # Other thread remains

    @pytest.mark.asyncio
    async def test_on_thread_delete_handles_not_monitored(self, mock_discord_client, mock_platform):
        """Test that on_thread_delete handles threads not in monitoring gracefully."""
        mock_platform.discord_observer.monitored_channel_ids = ["111111111"]

        thread = Mock(spec=discord.Thread)
        thread.id = 222222222  # Not in monitored list
        thread.name = "Unknown Thread"

        # Should not raise an error
        await mock_discord_client.on_thread_delete(thread)

        # List should remain unchanged
        assert mock_platform.discord_observer.monitored_channel_ids == ["111111111"]

    @pytest.mark.asyncio
    async def test_fetch_threads_in_monitored_channels(self, mock_discord_client, mock_platform):
        """Test _fetch_threads_in_monitored_channels on startup."""
        # Create mock text channel with threads
        mock_channel = Mock(spec=discord.TextChannel)
        mock_thread1 = Mock(spec=discord.Thread)
        mock_thread1.id = 333333333
        mock_thread1.name = "Existing Thread 1"

        mock_thread2 = Mock(spec=discord.Thread)
        mock_thread2.id = 444444444
        mock_thread2.name = "Existing Thread 2"

        mock_channel.threads = [mock_thread1, mock_thread2]

        # Mock get_channel to return our mock channel
        def get_channel_side_effect(channel_id):
            if str(channel_id) == "123456789":
                return mock_channel
            return None

        mock_discord_client.get_channel = Mock(side_effect=get_channel_side_effect)

        # Mock persistence functions
        with patch("ciris_engine.logic.adapters.discord.adapter.get_correlations_by_type") as mock_get_correlations:
            with patch("ciris_engine.logic.adapters.discord.adapter.add_correlation") as mock_add_correlation:
                # No existing correlations
                mock_get_correlations.return_value = []

                await mock_discord_client._fetch_threads_in_monitored_channels()

                # Both threads should be added to monitoring
                assert "333333333" in mock_platform.discord_observer.monitored_channel_ids
                assert "444444444" in mock_platform.discord_observer.monitored_channel_ids

                # Correlations should be stored for both
                assert mock_add_correlation.call_count == 2

    @pytest.mark.asyncio
    async def test_fetch_threads_handles_existing_correlations(self, mock_discord_client, mock_platform):
        """Test that existing thread correlations are respected."""
        # Create mock text channel with threads
        mock_channel = Mock(spec=discord.TextChannel)
        mock_thread = Mock(spec=discord.Thread)
        mock_thread.id = 555555555
        mock_thread.name = "Known Thread"
        mock_channel.threads = [mock_thread]

        mock_discord_client.get_channel = Mock(return_value=mock_channel)

        # Mock existing correlation
        existing_correlation = Mock()
        existing_correlation.source_id = "555555555"
        existing_correlation.metadata = {"monitored": True}

        with patch("ciris_engine.logic.adapters.discord.adapter.get_correlations_by_type") as mock_get_correlations:
            with patch("ciris_engine.logic.adapters.discord.adapter.add_correlation") as mock_add_correlation:
                mock_get_correlations.return_value = [existing_correlation]

                await mock_discord_client._fetch_threads_in_monitored_channels()

                # Thread should be added to monitoring
                assert "555555555" in mock_platform.discord_observer.monitored_channel_ids

                # But no new correlation should be created (already exists)
                mock_add_correlation.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_threads_handles_no_config(self, mock_discord_client):
        """Test _fetch_threads_in_monitored_channels when no config exists."""
        # Remove config
        mock_discord_client.platform = Mock()
        mock_discord_client.platform.config = None

        # Should return early without error
        await mock_discord_client._fetch_threads_in_monitored_channels()

        # No exceptions should be raised

    @pytest.mark.asyncio
    async def test_fetch_threads_handles_channel_fetch_error(self, mock_discord_client, mock_platform):
        """Test that channel fetch errors are handled gracefully."""
        # Mock get_channel to raise an exception
        mock_discord_client.get_channel = Mock(side_effect=Exception("Channel fetch failed"))

        with patch("ciris_engine.logic.adapters.discord.adapter.logger") as mock_logger:
            await mock_discord_client._fetch_threads_in_monitored_channels()

            # Should log warning, not crash
            mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_on_ready_calls_fetch_threads(self, mock_discord_client):
        """Test that on_ready calls _fetch_threads_in_monitored_channels."""
        # Mock the fetch method
        mock_discord_client._fetch_threads_in_monitored_channels = AsyncMock()

        await mock_discord_client.on_ready()

        # Verify connection manager was notified
        mock_discord_client.platform.discord_adapter._connection_manager._handle_connected.assert_called_once()

        # Verify thread fetching was called
        mock_discord_client._fetch_threads_in_monitored_channels.assert_called_once()

    @pytest.mark.asyncio
    async def test_thread_handling_no_observer(self, mock_discord_client):
        """Test thread handling when observer doesn't exist."""
        # Remove observer
        mock_discord_client.platform.discord_observer = None

        thread = Mock(spec=discord.Thread)
        thread.id = 777777777
        thread.parent_id = 123456789
        thread.name = "No Observer Thread"

        # Should not crash
        await mock_discord_client.on_thread_create(thread)
        await mock_discord_client.on_thread_delete(thread)

    @pytest.mark.asyncio
    async def test_correlation_storage_failure_handled(self, mock_discord_client, mock_platform):
        """Test that correlation storage failures are handled gracefully."""
        thread = Mock(spec=discord.Thread)
        thread.id = 888888888
        thread.parent_id = 123456789
        thread.name = "Failed Correlation Thread"

        with patch("ciris_engine.logic.adapters.discord.adapter.add_correlation") as mock_add_correlation:
            with patch("ciris_engine.logic.adapters.discord.adapter.logger") as mock_logger:
                # Make add_correlation fail
                mock_add_correlation.side_effect = Exception("Database error")

                await mock_discord_client.on_thread_create(thread)

                # Thread should still be added to monitoring
                assert "888888888" in mock_platform.discord_observer.monitored_channel_ids

                # Warning should be logged
                mock_logger.warning.assert_called()
