"""
Simplified tests for Discord adapter helper methods focusing on coverage.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.discord.adapter import DiscordPlatform, DiscordTaskErrorContext
from ciris_engine.logic.adapters.discord.config import DiscordAdapterConfig


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


class TestDiscordPlatformConfigHelpers:
    """Test Discord platform configuration helper methods."""

    @pytest.fixture
    def mock_runtime(self):
        """Create a minimal mock runtime."""
        runtime = Mock()
        runtime.template = None
        return runtime

    def test_load_config_from_adapter_config_instance(self, mock_runtime):
        """Test loading config from DiscordAdapterConfig instance."""
        config = DiscordAdapterConfig(bot_token="test_token_123", monitored_channel_ids=["123"])

        with patch.object(DiscordPlatform, "_initialize_discord_client"), patch.object(
            DiscordPlatform, "_initialize_discord_adapter"
        ), patch.object(DiscordAdapterConfig, "load_env_vars"):
            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform._load_config_from_adapter_config(config)

            assert platform.config == config
            assert platform.config.bot_token == "test_token_123"

    def test_load_config_from_adapter_config_dict(self, mock_runtime):
        """Test loading config from dictionary."""
        config_dict = {"bot_token": "test_token_456", "monitored_channel_ids": ["456"]}

        with patch.object(DiscordPlatform, "_initialize_discord_client"), patch.object(
            DiscordPlatform, "_initialize_discord_adapter"
        ), patch.object(DiscordAdapterConfig, "load_env_vars"):
            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform._load_config_from_adapter_config(config_dict)

            assert isinstance(platform.config, DiscordAdapterConfig)
            assert platform.config.bot_token == "test_token_456"

    def test_load_config_from_adapter_config_invalid(self, mock_runtime):
        """Test loading config from invalid type falls back to default."""
        invalid_config = "not_a_config"

        with patch.object(DiscordPlatform, "_initialize_discord_client"), patch.object(
            DiscordPlatform, "_initialize_discord_adapter"
        ), patch.object(DiscordAdapterConfig, "load_env_vars"):
            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform._load_config_from_adapter_config(invalid_config)

            assert isinstance(platform.config, DiscordAdapterConfig)

    def test_has_direct_config_kwargs_with_bot_token(self):
        """Test detecting direct config kwargs with bot_token."""
        platform = DiscordPlatform.__new__(DiscordPlatform)
        kwargs = {"bot_token": "test_token"}

        result = platform._has_direct_config_kwargs(kwargs)

        assert result is True

    def test_has_direct_config_kwargs_with_channel_id(self):
        """Test detecting direct config kwargs with channel_id."""
        platform = DiscordPlatform.__new__(DiscordPlatform)
        kwargs = {"channel_id": "123456"}

        result = platform._has_direct_config_kwargs(kwargs)

        assert result is True

    def test_has_direct_config_kwargs_with_server_id(self):
        """Test detecting direct config kwargs with server_id."""
        platform = DiscordPlatform.__new__(DiscordPlatform)
        kwargs = {"server_id": "789"}

        result = platform._has_direct_config_kwargs(kwargs)

        assert result is True

    def test_has_direct_config_kwargs_none_present(self):
        """Test detecting no direct config kwargs."""
        platform = DiscordPlatform.__new__(DiscordPlatform)
        kwargs = {"other_param": "value"}

        result = platform._has_direct_config_kwargs(kwargs)

        assert result is False

    def test_build_config_from_direct_kwargs_full(self):
        """Test building config from complete kwargs."""
        platform = DiscordPlatform.__new__(DiscordPlatform)
        kwargs = {
            "bot_token": "test_token",
            "channel_id": "123",
            "server_id": "456",  # server_id is passed but not used by DiscordAdapterConfig
            "deferral_channel_id": "789",
            "admin_user_ids": ["user1", "user2"],
        }

        config = platform._build_config_from_direct_kwargs(kwargs)

        assert isinstance(config, DiscordAdapterConfig)
        assert config.bot_token == "test_token"
        assert config.monitored_channel_ids == ["123"]
        assert config.home_channel_id == "123"
        assert config.deferral_channel_id == "789"
        assert config.admin_user_ids == ["user1", "user2"]

    def test_build_config_from_direct_kwargs_partial(self):
        """Test building config from partial kwargs."""
        platform = DiscordPlatform.__new__(DiscordPlatform)
        kwargs = {"bot_token": "test_token", "channel_id": "123"}

        config = platform._build_config_from_direct_kwargs(kwargs)

        assert isinstance(config, DiscordAdapterConfig)
        assert config.bot_token == "test_token"
        assert config.monitored_channel_ids == ["123"]

    def test_build_config_from_direct_kwargs_minimal(self):
        """Test building config from minimal kwargs."""
        platform = DiscordPlatform.__new__(DiscordPlatform)
        kwargs = {}

        config = platform._build_config_from_direct_kwargs(kwargs)

        assert isinstance(config, DiscordAdapterConfig)

    def test_load_config_from_kwargs_or_default_with_direct_kwargs(self):
        """Test loading config from direct kwargs."""
        with patch.object(DiscordPlatform, "_has_direct_config_kwargs", return_value=True), patch.object(
            DiscordPlatform, "_build_config_from_direct_kwargs"
        ) as mock_build:
            mock_config = DiscordAdapterConfig(bot_token="test")
            mock_build.return_value = mock_config

            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform._load_config_from_kwargs_or_default({"bot_token": "test"})

            assert platform.config == mock_config

    def test_load_config_from_kwargs_or_default_no_direct_kwargs(self):
        """Test loading default config when no direct kwargs."""
        with patch.object(DiscordPlatform, "_has_direct_config_kwargs", return_value=False):
            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform._load_config_from_kwargs_or_default({})

            assert isinstance(platform.config, DiscordAdapterConfig)

    def test_load_config_from_kwargs_or_default_with_discord_bot_token(self):
        """Test loading config with legacy discord_bot_token parameter."""
        with patch.object(DiscordPlatform, "_has_direct_config_kwargs", return_value=False):
            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform._load_config_from_kwargs_or_default({"discord_bot_token": "legacy_token"})

            assert platform.config.bot_token == "legacy_token"

    def test_load_config_from_template_no_template(self):
        """Test loading config when runtime has no template."""
        runtime = Mock()
        runtime.template = None

        with patch.object(DiscordAdapterConfig, "load_env_vars"):
            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform.config = DiscordAdapterConfig()
            platform._load_config_from_template(runtime)

            platform.config.load_env_vars.assert_called_once()

    def test_load_config_from_template_with_template(self):
        """Test loading config from runtime template."""
        runtime = Mock()
        runtime.template = Mock()
        runtime.template.discord_config = Mock()
        runtime.template.discord_config.model_dump.return_value = {
            "bot_token": "template_token",
            "monitored_channel_ids": ["template_channel"],
        }

        with patch.object(DiscordAdapterConfig, "load_env_vars"):
            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform.config = DiscordAdapterConfig()
            platform._load_config_from_template(runtime)

            assert platform.config.bot_token == "template_token"
            assert platform.config.monitored_channel_ids == ["template_channel"]

    def test_load_config_from_template_exception(self):
        """Test loading config from template with exception."""
        runtime = Mock()
        runtime.template = Mock()
        runtime.template.discord_config = Mock()
        runtime.template.discord_config.model_dump.side_effect = Exception("Template error")

        with patch.object(DiscordAdapterConfig, "load_env_vars"):
            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform.config = DiscordAdapterConfig()
            platform._load_config_from_template(runtime)

            # Should not raise, just log and continue
            platform.config.load_env_vars.assert_called_once()

    def test_finalize_config_with_bot_token(self):
        """Test finalizing config with valid bot token."""
        platform = DiscordPlatform.__new__(DiscordPlatform)
        platform.config = DiscordAdapterConfig(bot_token="final_token")

        platform._finalize_config()

        assert platform.token == "final_token"

    def test_finalize_config_without_bot_token(self):
        """Test finalizing config without bot token raises error."""
        platform = DiscordPlatform.__new__(DiscordPlatform)
        platform.config = DiscordAdapterConfig()

        with pytest.raises(ValueError, match=".*bot_token.*configuration.*"):
            platform._finalize_config()

    def test_initialize_config_with_adapter_config(self, mock_runtime):
        """Test full _initialize_config flow with adapter_config."""
        config = DiscordAdapterConfig(bot_token="init_token")

        with patch.object(DiscordPlatform, "_initialize_discord_client"), patch.object(
            DiscordPlatform, "_initialize_discord_adapter"
        ), patch.object(DiscordPlatform, "_load_config_from_adapter_config") as mock_load_adapter, patch.object(
            DiscordPlatform, "_finalize_config"
        ) as mock_finalize:
            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform._initialize_config(mock_runtime, {"adapter_config": config})

            mock_load_adapter.assert_called_once_with(config)
            mock_finalize.assert_called_once()

    def test_initialize_config_without_adapter_config(self, mock_runtime):
        """Test full _initialize_config flow without adapter_config."""
        with patch.object(DiscordPlatform, "_initialize_discord_client"), patch.object(
            DiscordPlatform, "_initialize_discord_adapter"
        ), patch.object(DiscordPlatform, "_load_config_from_kwargs_or_default") as mock_load_kwargs, patch.object(
            DiscordPlatform, "_load_config_from_template"
        ) as mock_load_template, patch.object(
            DiscordPlatform, "_finalize_config"
        ) as mock_finalize:
            platform = DiscordPlatform.__new__(DiscordPlatform)
            platform._initialize_config(mock_runtime, {})

            mock_load_kwargs.assert_called_once()
            mock_load_template.assert_called_once_with(mock_runtime)
            mock_finalize.assert_called_once()
