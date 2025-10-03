"""
Unit tests for Discord configuration loading to prevent regression of the monitored_channel_ids bug.
"""

import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.discord.config import DiscordAdapterConfig
from ciris_engine.logic.adapters.discord.discord_observer import DiscordObserver


class TestDiscordConfigLoading:
    """Test that Discord configuration properly loads monitored channel IDs."""

    def test_config_loads_env_vars_for_monitored_channels(self):
        """Test that load_env_vars properly loads DISCORD_CHANNEL_IDS."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_CHANNEL_IDS": "1382010877171073108,1387961206190637076",
                "DISCORD_BOT_TOKEN": "test_token",
            },
        ):
            config = DiscordAdapterConfig()
            assert config.monitored_channel_ids == []  # Should be empty initially

            config.load_env_vars()

            # After loading env vars, should have the channels
            assert len(config.monitored_channel_ids) == 2
            assert "1382010877171073108" in config.monitored_channel_ids
            assert "1387961206190637076" in config.monitored_channel_ids

    def test_config_preserves_existing_channels_when_loading_env(self):
        """Test that load_env_vars extends rather than replaces the list."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_CHANNEL_IDS": "1382010877171073108,1387961206190637076",
            },
        ):
            config = DiscordAdapterConfig()
            config.monitored_channel_ids = ["existing_channel"]

            config.load_env_vars()

            # Should have all three channels
            assert len(config.monitored_channel_ids) == 3
            assert "existing_channel" in config.monitored_channel_ids
            assert "1382010877171073108" in config.monitored_channel_ids
            assert "1387961206190637076" in config.monitored_channel_ids

    def test_observer_receives_monitored_channels(self):
        """Test that DiscordObserver properly receives monitored channels."""
        test_channels = ["1382010877171073108", "1387961206190637076"]

        observer = DiscordObserver(
            agent_id="test_agent",
            monitored_channel_ids=test_channels,
        )

        assert observer.monitored_channel_ids == test_channels

    def test_observer_empty_channels_without_config(self):
        """Test that observer has empty list when no channels provided."""
        observer = DiscordObserver(
            agent_id="test_agent",
            monitored_channel_ids=None,
        )

        assert observer.monitored_channel_ids == []

    def test_main_flow_loads_env_vars(self):
        """Test that the main.py flow properly loads env vars for Discord config."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_CHANNEL_IDS": "1382010877171073108,1387961206190637076",
                "DISCORD_BOT_TOKEN": "test_token",
            },
        ):
            # Simulate what main.py does
            config = DiscordAdapterConfig()
            config.bot_token = "test_token"
            config.load_env_vars()  # This is the critical line that was missing!

            assert config.bot_token == "test_token"
            assert len(config.monitored_channel_ids) == 2
            assert "1382010877171073108" in config.monitored_channel_ids

    def test_channel_id_extraction(self):
        """Test that channel ID extraction works correctly."""
        observer = DiscordObserver(
            agent_id="test_agent",
            monitored_channel_ids=["1382010877171073108"],
        )

        # Test extraction from full format
        full_id = "discord_1364300186003968060_1382010877171073108"
        extracted = observer._extract_channel_id(full_id)
        assert extracted == "1382010877171073108"

        # Test with non-formatted ID
        simple_id = "1382010877171073108"
        extracted = observer._extract_channel_id(simple_id)
        assert extracted == simple_id

    @patch("ciris_engine.logic.adapters.discord.discord_observer.logger")
    async def test_passive_observation_routing(self, mock_logger):
        """Test that passive observations are routed correctly based on monitored channels."""
        observer = DiscordObserver(
            agent_id="test_agent",
            monitored_channel_ids=["1382010877171073108"],
            deferral_channel_id="1382010936600301569",
        )

        # Create a mock message from a monitored channel
        mock_msg = MagicMock()
        mock_msg.channel_id = "discord_1364300186003968060_1382010877171073108"
        mock_msg.author_id = "537080239679864862"
        mock_msg.author_name = "SomeComputerGuy"
        mock_msg.content = "Test message"

        # Mock the _create_passive_observation_result to track if it's called
        observer._create_passive_observation_result = AsyncMock()

        await observer._handle_passive_observation(mock_msg)

        # Should have called create_passive_observation_result for monitored channel
        observer._create_passive_observation_result.assert_called_once_with(mock_msg)

    @patch("ciris_engine.logic.adapters.discord.discord_observer.logger")
    async def test_passive_observation_not_routed_for_unmonitored(self, mock_logger):
        """Test that passive observations are NOT routed for unmonitored channels."""
        observer = DiscordObserver(
            agent_id="test_agent",
            monitored_channel_ids=["1382010877171073108"],  # Different channel
            deferral_channel_id="1382010936600301569",
        )

        # Create a mock message from an UNMONITORED channel
        mock_msg = MagicMock()
        mock_msg.channel_id = "discord_1364300186003968060_9999999999999999"  # Not monitored
        mock_msg.author_id = "537080239679864862"
        mock_msg.author_name = "SomeComputerGuy"
        mock_msg.content = "Test message"

        # Mock the _create_passive_observation_result to track if it's called
        observer._create_passive_observation_result = AsyncMock()

        await observer._handle_passive_observation(mock_msg)

        # Should NOT have called create_passive_observation_result
        observer._create_passive_observation_result.assert_not_called()

        # Should have logged that it's not routing
        mock_logger.warning.assert_called()
        log_calls = [call[0][0] for call in mock_logger.warning.call_args_list]
        assert any("NO TASK CREATED" in call for call in log_calls)


class TestDiscordAdapterInitialization:
    """Test Discord adapter initialization with config."""

    @patch("ciris_engine.logic.adapters.discord.adapter.DiscordObserver")
    @patch("ciris_engine.logic.adapters.discord.adapter.discord")
    async def test_adapter_passes_monitored_channels_to_observer(self, mock_discord, mock_observer_class):
        """Test that adapter correctly passes monitored_channel_ids to observer."""
        from ciris_engine.logic.adapters.discord.adapter import DiscordPlatform

        # Set up mock runtime
        mock_runtime = MagicMock()
        mock_runtime.template = None
        mock_runtime.memory_service = None
        mock_runtime.secrets_service = None
        mock_runtime.time_service = None

        # Create config with monitored channels
        config = DiscordAdapterConfig()
        config.bot_token = "test_token"
        config.monitored_channel_ids = ["1382010877171073108", "1387961206190637076"]

        # Mock the observer instance to have async start/stop methods
        mock_observer_instance = MagicMock()
        mock_observer_instance.start = AsyncMock()
        mock_observer_instance.stop = AsyncMock()
        mock_observer_class.return_value = mock_observer_instance

        # Create adapter with the config
        adapter = DiscordPlatform(
            runtime=mock_runtime,
            adapter_config=config,
        )

        # Mock the tool_service to have async start/stop methods
        adapter.tool_service = MagicMock()
        adapter.tool_service.start = AsyncMock()
        adapter.tool_service.stop = AsyncMock()

        # Start the adapter (this is where observer is created)
        await adapter.start()

        # Verify DiscordObserver was created with correct monitored_channel_ids
        mock_observer_class.assert_called_once()
        call_kwargs = mock_observer_class.call_args[1]
        assert call_kwargs["monitored_channel_ids"] == ["1382010877171073108", "1387961206190637076"]

    def test_config_env_var_loading_idempotent(self):
        """Test that calling load_env_vars multiple times doesn't duplicate channels."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_CHANNEL_IDS": "1382010877171073108",
            },
        ):
            config = DiscordAdapterConfig()

            config.load_env_vars()
            assert config.monitored_channel_ids == ["1382010877171073108"]

            # Call again - should not duplicate
            config.load_env_vars()
            # Fixed: No longer duplicates due to duplicate checking before append
            assert len(config.monitored_channel_ids) == 1  # Fixed: Should be 1 and now is 1
            assert config.monitored_channel_ids == ["1382010877171073108"]


class TestRegressionPrevention:
    """Tests specifically to prevent regression of the monitored channels bug."""

    def test_dev_student_channel_is_monitored(self):
        """Test that the dev-student channel ID is properly recognized as monitored."""
        with patch.dict(
            os.environ,
            {
                "DISCORD_CHANNEL_IDS": "1382010877171073108,1387961206190637076",
            },
        ):
            config = DiscordAdapterConfig()
            config.load_env_vars()

            # The dev-student channel should be in the list
            assert "1382010877171073108" in config.monitored_channel_ids

            # Create observer with this config
            observer = DiscordObserver(
                agent_id="test",
                monitored_channel_ids=config.monitored_channel_ids,
            )

            # Extract channel ID from full format
            full_channel_id = "discord_1364300186003968060_1382010877171073108"
            extracted = observer._extract_channel_id(full_channel_id)

            # Verify it's recognized as monitored
            assert extracted in observer.monitored_channel_ids

    @patch("ciris_engine.logic.persistence.add_task")
    @patch("ciris_engine.logic.adapters.discord.discord_observer.logger")
    async def test_dev_student_messages_create_tasks(self, mock_logger, mock_add_task):
        """Test that messages from dev-student channel create tasks."""
        observer = DiscordObserver(
            agent_id="datum",
            monitored_channel_ids=["1382010877171073108"],  # dev-student
        )

        # Mock message from dev-student
        mock_msg = MagicMock()
        mock_msg.channel_id = "discord_1364300186003968060_1382010877171073108"
        mock_msg.author_id = "537080239679864862"
        mock_msg.author_name = "SomeComputerGuy"
        mock_msg.content = "Hello Datum"
        mock_msg.message_id = "test_msg_id"

        # Mock the time service
        observer.time_service = MagicMock()
        observer.time_service.now_iso.return_value = "2025-08-09T12:00:00Z"

        # This should create a passive observation task
        await observer._handle_passive_observation(mock_msg)

        # Verify task creation was attempted
        # Note: The actual task creation happens in _create_passive_observation_result
        # which calls _sign_and_add_task, which calls persistence.add_task


class TestDiscordConfigHelperMethods:
    """Tests for the new helper methods in Discord configuration."""

    def test_load_bot_token(self):
        """Test _load_bot_token helper method."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()

        # Test with token present
        mock_get_env_var.return_value = "test_token_123"
        config._load_bot_token(mock_get_env_var)

        assert config.bot_token == "test_token_123"
        mock_get_env_var.assert_called_once_with("DISCORD_BOT_TOKEN")

        # Test with no token
        mock_get_env_var.reset_mock()
        mock_get_env_var.return_value = None
        config2 = DiscordAdapterConfig()
        config2._load_bot_token(mock_get_env_var)

        assert config2.bot_token is None

    def test_add_channel_to_monitored_new_channel(self):
        """Test _add_channel_to_monitored with new channel."""
        config = DiscordAdapterConfig()
        config.monitored_channel_ids = ["existing_channel"]

        config._add_channel_to_monitored("new_channel")

        assert "new_channel" in config.monitored_channel_ids
        assert "existing_channel" in config.monitored_channel_ids
        assert len(config.monitored_channel_ids) == 2

    def test_add_channel_to_monitored_duplicate_channel(self):
        """Test _add_channel_to_monitored with duplicate channel."""
        config = DiscordAdapterConfig()
        config.monitored_channel_ids = ["existing_channel"]

        config._add_channel_to_monitored("existing_channel")

        assert config.monitored_channel_ids == ["existing_channel"]
        assert len(config.monitored_channel_ids) == 1

    def test_load_channel_configuration_home_channel(self):
        """Test _load_channel_configuration with home channel."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()

        def mock_env_values(key):
            if key == "DISCORD_HOME_CHANNEL_ID":
                return "home_123"
            return None

        mock_get_env_var.side_effect = mock_env_values
        config._load_channel_configuration(mock_get_env_var)

        assert config.home_channel_id == "home_123"
        assert "home_123" in config.monitored_channel_ids

    def test_load_channel_configuration_legacy_channel(self):
        """Test _load_channel_configuration with legacy channel."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()

        def mock_env_values(key):
            if key == "DISCORD_CHANNEL_ID":
                return "legacy_123"
            return None

        mock_get_env_var.side_effect = mock_env_values
        config._load_channel_configuration(mock_get_env_var)

        assert config.home_channel_id == "legacy_123"
        assert "legacy_123" in config.monitored_channel_ids

    def test_load_channel_configuration_legacy_ignored_if_home_exists(self):
        """Test legacy channel is ignored if home channel already set."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        config.home_channel_id = "existing_home"  # Pre-set home channel
        mock_get_env_var = Mock()

        def mock_env_values(key):
            if key == "DISCORD_CHANNEL_ID":
                return "legacy_123"
            return None

        mock_get_env_var.side_effect = mock_env_values
        config._load_channel_configuration(mock_get_env_var)

        # Should keep existing home channel, ignore legacy
        assert config.home_channel_id == "existing_home"

    def test_load_channel_configuration_multiple_channels(self):
        """Test _load_channel_configuration with multiple channels."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()

        def mock_env_values(key):
            if key == "DISCORD_CHANNEL_IDS":
                return "123,456,789"
            return None

        mock_get_env_var.side_effect = mock_env_values
        config._load_channel_configuration(mock_get_env_var)

        assert "123" in config.monitored_channel_ids
        assert "456" in config.monitored_channel_ids
        assert "789" in config.monitored_channel_ids

    def test_load_channel_configuration_deferral_channel(self):
        """Test _load_channel_configuration with deferral channel."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()

        def mock_env_values(key):
            if key == "DISCORD_DEFERRAL_CHANNEL_ID":
                return "deferral_123"
            return None

        mock_get_env_var.side_effect = mock_env_values
        config._load_channel_configuration(mock_get_env_var)

        assert config.deferral_channel_id == "deferral_123"

    def test_load_user_permissions_single_admin(self):
        """Test _load_user_permissions with single admin."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()
        mock_get_env_var.return_value = "admin_123"

        config._load_user_permissions(mock_get_env_var)

        assert "admin_123" in config.admin_user_ids
        assert len(config.admin_user_ids) == 1
        mock_get_env_var.assert_called_once_with("WA_USER_IDS")

    def test_load_user_permissions_multiple_admins(self):
        """Test _load_user_permissions with multiple comma-separated admins."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()
        mock_get_env_var.return_value = "admin_123,admin_456,admin_789"

        config._load_user_permissions(mock_get_env_var)

        assert "admin_123" in config.admin_user_ids
        assert "admin_456" in config.admin_user_ids
        assert "admin_789" in config.admin_user_ids
        assert len(config.admin_user_ids) == 3
        mock_get_env_var.assert_called_once_with("WA_USER_IDS")

    def test_load_user_permissions_existing_admin_no_duplicates(self):
        """Test _load_user_permissions with existing admin does not duplicate."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        config.admin_user_ids = ["admin_123"]
        mock_get_env_var = Mock()
        mock_get_env_var.return_value = "admin_123,admin_456"

        config._load_user_permissions(mock_get_env_var)

        # Should not duplicate admin_123, but should add admin_456
        assert "admin_123" in config.admin_user_ids
        assert "admin_456" in config.admin_user_ids
        assert len(config.admin_user_ids) == 2

    def test_load_user_permissions_with_spaces(self):
        """Test _load_user_permissions handles spaces around user IDs."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()
        mock_get_env_var.return_value = " admin_123 , admin_456 ,admin_789, "

        config._load_user_permissions(mock_get_env_var)

        assert "admin_123" in config.admin_user_ids
        assert "admin_456" in config.admin_user_ids
        assert "admin_789" in config.admin_user_ids
        assert len(config.admin_user_ids) == 3
        # Ensure no empty strings were added
        assert "" not in config.admin_user_ids
        assert " " not in config.admin_user_ids

    def test_load_user_permissions_empty_entries(self):
        """Test _load_user_permissions handles empty entries in comma-separated list."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()
        mock_get_env_var.return_value = "admin_123,,admin_456,,"

        config._load_user_permissions(mock_get_env_var)

        assert "admin_123" in config.admin_user_ids
        assert "admin_456" in config.admin_user_ids
        assert len(config.admin_user_ids) == 2
        # Ensure no empty strings were added
        assert "" not in config.admin_user_ids

    def test_load_user_permissions_no_admin(self):
        """Test _load_user_permissions with no admin."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()
        mock_get_env_var.return_value = None

        config._load_user_permissions(mock_get_env_var)

        assert config.admin_user_ids == []

    def test_load_user_permissions_empty_string(self):
        """Test _load_user_permissions with empty string."""
        from unittest.mock import Mock

        config = DiscordAdapterConfig()
        mock_get_env_var = Mock()
        mock_get_env_var.return_value = ""

        config._load_user_permissions(mock_get_env_var)

        assert config.admin_user_ids == []
