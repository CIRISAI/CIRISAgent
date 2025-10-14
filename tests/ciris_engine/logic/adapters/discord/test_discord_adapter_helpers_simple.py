"""
Simplified tests for Discord adapter helper methods focusing on coverage.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.discord.adapter import DiscordPlatform, DiscordTaskErrorContext


@pytest.fixture
def platform():
    """Create a Discord platform with minimal mocking."""
    mock_runtime = Mock()

    # Create a proper mock config with bot_token to avoid validation errors
    mock_config = Mock()
    mock_config.bot_token = "test_bot_token_123456"
    mock_config.monitored_channel_ids = ["123456789"]

    # Mock the entire DiscordPlatform initialization to avoid real Discord setup
    with patch("ciris_engine.logic.adapters.discord.adapter.DiscordAdapter"):
        with patch.object(DiscordPlatform, "__init__", return_value=None):
            platform = DiscordPlatform.__new__(DiscordPlatform)

    # Manually set up the platform attributes we need for testing
    platform.client = Mock()
    platform.client.is_closed = Mock(return_value=False)
    platform.client.user = "TestBot#1234"
    platform.client.close = AsyncMock()

    platform.token = "test_token_123"
    platform._reconnect_attempts = 2
    platform._max_reconnect_attempts = 10
    platform._initialize_discord_client = AsyncMock()
    platform._discord_client_task = None

    return platform


class TestDiscordHelpers:
    """Test Discord adapter helper methods for coverage."""

    def test_build_error_context_basic(self, platform):
        """Test basic error context building."""
        agent_task = Mock()
        agent_task.get_name.return_value = "TestTask"
        agent_task.done.return_value = False

        # Mock Discord task
        discord_task = Mock()
        discord_task.done.return_value = True
        discord_task.cancelled.return_value = False
        discord_task.exception.return_value = Exception("test error")
        platform._discord_client_task = discord_task

        context = platform._build_error_context(agent_task)

        # Context is now a DiscordTaskErrorContext Pydantic model, use attribute access
        assert context.agent_task_name == "TestTask"
        assert context.reconnect_attempts == 2
        assert context.task_exists is True

    def test_build_error_context_none_task(self, platform):
        """Test error context when Discord task is None."""
        agent_task = Mock()
        agent_task.get_name.return_value = "TestTask"
        agent_task.done.return_value = False

        platform._discord_client_task = None

        context = platform._build_error_context(agent_task)

        # Context is now a DiscordTaskErrorContext Pydantic model, use attribute access
        assert context.task_exists is False
        assert context.task_done is None

    @pytest.mark.asyncio
    async def test_recreate_discord_task_success(self, platform):
        """Test successful task recreation."""
        context = DiscordTaskErrorContext(
            task_exists=True,
            task_done=True,
            reconnect_attempts=0,
            agent_task_name="TestTask",
            agent_task_done=False,
        )

        with patch("asyncio.create_task") as mock_create:
            mock_task = Mock()
            mock_create.return_value = mock_task

            result = await platform._recreate_discord_task(context)

            assert result is True
            assert platform._discord_client_task == mock_task

    @pytest.mark.asyncio
    async def test_recreate_discord_task_failure(self, platform):
        """Test task recreation failure."""
        context = DiscordTaskErrorContext(
            task_exists=True,
            task_done=True,
            reconnect_attempts=0,
            agent_task_name="TestTask",
            agent_task_done=False,
        )

        with patch("asyncio.create_task", side_effect=Exception("failed")):
            with patch("asyncio.sleep") as mock_sleep:
                result = await platform._recreate_discord_task(context)

                assert result is False
                mock_sleep.assert_called_once()

    def test_check_task_health_healthy(self, platform):
        """Test healthy task check."""
        agent_task = Mock()

        discord_task = Mock()
        discord_task.done.return_value = False
        platform._discord_client_task = discord_task

        result = platform._check_task_health(agent_task)

        assert result is True

    def test_check_task_health_unhealthy(self, platform):
        """Test unhealthy task check."""
        agent_task = Mock()
        agent_task.get_name.return_value = "TestTask"
        agent_task.done.return_value = False  # Agent task is still running

        discord_task = Mock()
        discord_task.done.return_value = True  # Discord task died
        discord_task.cancelled.return_value = False
        platform._discord_client_task = discord_task

        result = platform._check_task_health(agent_task)

        assert result is False

    def test_handle_timeout_healthy(self, platform):
        """Test timeout handling with healthy client logs at debug level."""
        with patch("ciris_engine.logic.adapters.discord.adapter.logger") as mock_logger:
            result = platform._handle_timeout_scenario()

            assert result is True
            # Should log at debug level when client is healthy
            mock_logger.debug.assert_called_once_with(
                "No tasks completed within 30s timeout - Discord client appears healthy, continuing..."
            )
            # Should not log any warnings when healthy
            mock_logger.warning.assert_not_called()

    def test_handle_timeout_unresponsive(self, platform):
        """Test timeout handling with unresponsive client logs warning."""
        platform.client.is_closed.return_value = True

        discord_task = Mock()
        discord_task.done.return_value = False
        platform._discord_client_task = discord_task

        with patch("ciris_engine.logic.adapters.discord.adapter.logger") as mock_logger:
            result = platform._handle_timeout_scenario()

            assert result is False
            discord_task.cancel.assert_called_once()
            assert platform._discord_client_task is None
            # Should log warning when client is unresponsive
            mock_logger.warning.assert_called_once_with(
                "No tasks completed within 30s timeout - Discord client appears closed/unresponsive, will recreate task on next iteration"
            )

    def test_handle_timeout_no_client(self, platform):
        """Test timeout handling when client is None."""
        platform.client = None

        with patch("ciris_engine.logic.adapters.discord.adapter.logger") as mock_logger:
            result = platform._handle_timeout_scenario()

            assert result is False
            # Should log warning when no client exists
            mock_logger.warning.assert_called_once_with(
                "No tasks completed within 30s timeout - Discord client appears closed/unresponsive, will recreate task on next iteration"
            )

    @pytest.mark.asyncio
    async def test_handle_discord_task_failure_non_retryable(self, platform):
        """Test handling non-retryable errors."""
        exc = Exception("auth failed")
        agent_task = Mock()
        agent_task.get_name.return_value = "TestTask"
        agent_task.done.return_value = False

        discord_task = Mock()
        discord_task.get_name.return_value = "DiscordTask"
        discord_task.cancelled.return_value = False
        platform._discord_client_task = discord_task

        # Mock the error classifier to return non-retryable
        with patch(
            "ciris_engine.logic.adapters.discord.discord_error_classifier.DiscordErrorClassifier"
        ) as mock_classifier:
            mock_classification = Mock()
            mock_classification.should_retry = False
            mock_classification.description = "Non-retryable"
            mock_classifier.classify_error.return_value = mock_classification
            mock_classifier.log_error_classification = Mock()

            result = await platform._handle_discord_task_failure(exc, agent_task)

            assert result is False

    @pytest.mark.asyncio
    async def test_handle_top_level_exception_max_attempts(self, platform):
        """Test top-level exception when max attempts reached."""
        exc = Exception("top level error")
        agent_task = Mock()
        agent_task.done.return_value = False

        platform._reconnect_attempts = 15  # > max attempts

        await platform._handle_top_level_exception(exc, agent_task)

        agent_task.cancel.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_discord_resources_basic(self, platform):
        """Test basic resource cleanup."""
        discord_task = Mock()
        discord_task.done.return_value = False
        discord_task.cancel = Mock()
        platform._discord_client_task = discord_task

        await platform._cleanup_discord_resources()

        discord_task.cancel.assert_called_once()
        platform.client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_discord_resources_no_task(self, platform):
        """Test cleanup when no Discord task exists."""
        platform._discord_client_task = None

        await platform._cleanup_discord_resources()

        # Should not raise errors
        platform.client.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_discord_resources_closed_client(self, platform):
        """Test cleanup with already closed client."""
        platform._discord_client_task = None
        platform.client.is_closed.return_value = True

        await platform._cleanup_discord_resources()

        # Should not call close on already closed client
        platform.client.close.assert_not_called()
