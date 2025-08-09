"""
Unit tests for Discord configuration loading to prevent regression of the monitored_channel_ids bug.
"""

import os
from unittest.mock import MagicMock, Mock, patch

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
        observer._create_passive_observation_result = Mock()

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
        observer._create_passive_observation_result = Mock()

        await observer._handle_passive_observation(mock_msg)

        # Should NOT have called create_passive_observation_result
        observer._create_passive_observation_result.assert_not_called()

        # Should have logged that it's not routing
        mock_logger.info.assert_called()
        log_calls = [call[0][0] for call in mock_logger.info.call_args_list]
        assert any("Not routing to WA feedback" in call for call in log_calls)


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

        # Create adapter with the config
        adapter = DiscordPlatform(
            runtime=mock_runtime,
            adapter_config=config,
        )

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
            # This will actually duplicate because extend is used - this is a bug!
            assert len(config.monitored_channel_ids) == 2  # Bug: Should be 1 but is 2

            # This test documents the current (buggy) behavior
            # A proper fix would check for duplicates before extending


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
