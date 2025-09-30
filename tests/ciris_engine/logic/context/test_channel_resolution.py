"""
Tests for centralized channel resolution logic.

Tests all helper functions and the main resolution cascade to ensure
100% coverage of the refactored code.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.context.channel_resolution import (
    _try_app_config_home_channel,
    _try_mode_based_fallback,
    _try_mode_specific_config,
    _try_task_channel_id,
    resolve_channel_id_and_context,
)


class TestHelperFunctions:
    """Test individual helper functions."""

    def test_try_task_channel_id_with_valid_task(self):
        """Test extracting channel_id from task."""
        task = MagicMock()
        task.channel_id = "123456"

        result = _try_task_channel_id(task)

        assert result == "123456"

    def test_try_task_channel_id_with_none_task(self):
        """Test with None task."""
        result = _try_task_channel_id(None)
        assert result is None

    def test_try_task_channel_id_with_no_channel_id(self):
        """Test with task missing channel_id."""
        task = MagicMock()
        delattr(task, "channel_id")

        result = _try_task_channel_id(task)
        assert result is None

    def test_try_task_channel_id_with_empty_channel_id(self):
        """Test with empty channel_id."""
        task = MagicMock()
        task.channel_id = ""

        result = _try_task_channel_id(task)
        assert result is None

    def test_try_app_config_home_channel_with_valid_config(self):
        """Test extracting home_channel from app_config."""
        app_config = MagicMock()
        app_config.home_channel = "HOME_123"

        result = _try_app_config_home_channel(app_config)

        assert result == "HOME_123"

    def test_try_app_config_home_channel_with_none_config(self):
        """Test with None app_config."""
        result = _try_app_config_home_channel(None)
        assert result is None

    def test_try_app_config_home_channel_with_no_home_channel(self):
        """Test with app_config missing home_channel."""
        app_config = MagicMock(spec=[])

        result = _try_app_config_home_channel(app_config)
        assert result is None

    def test_try_mode_specific_config_discord_channel_id(self):
        """Test extracting discord_channel_id from app_config."""
        app_config = MagicMock()
        app_config.discord_channel_id = "DISCORD_123"

        result = _try_mode_specific_config(app_config)

        assert result == "DISCORD_123"

    def test_try_mode_specific_config_cli_channel_id(self):
        """Test extracting cli_channel_id from app_config."""
        app_config = MagicMock()
        delattr(app_config, "discord_channel_id")
        app_config.cli_channel_id = "CLI_123"

        result = _try_mode_specific_config(app_config)

        assert result == "CLI_123"

    def test_try_mode_specific_config_api_channel_id(self):
        """Test extracting api_channel_id from app_config."""
        app_config = MagicMock(spec=["api_channel_id"])
        app_config.api_channel_id = "API_123"

        result = _try_mode_specific_config(app_config)

        assert result == "API_123"

    def test_try_mode_specific_config_with_none_config(self):
        """Test with None app_config."""
        result = _try_mode_specific_config(None)
        assert result is None

    def test_try_mode_specific_config_with_no_matching_attrs(self):
        """Test with app_config having no mode-specific channels."""
        app_config = MagicMock(spec=[])

        result = _try_mode_specific_config(app_config)
        assert result is None

    def test_try_mode_based_fallback_cli(self):
        """Test CLI mode fallback."""
        app_config = MagicMock()
        app_config.agent_mode = "cli"

        result = _try_mode_based_fallback(app_config)

        assert result == "CLI"

    def test_try_mode_based_fallback_api(self):
        """Test API mode fallback."""
        app_config = MagicMock()
        app_config.agent_mode = "API"  # Test case insensitivity

        result = _try_mode_based_fallback(app_config)

        assert result == "API"

    def test_try_mode_based_fallback_discord(self):
        """Test Discord mode fallback."""
        app_config = MagicMock()
        app_config.agent_mode = "discord"

        result = _try_mode_based_fallback(app_config)

        assert result == "DISCORD_DEFAULT"

    def test_try_mode_based_fallback_with_none_config(self):
        """Test with None app_config."""
        result = _try_mode_based_fallback(None)
        assert result is None

    def test_try_mode_based_fallback_with_unknown_mode(self):
        """Test with unknown agent_mode."""
        app_config = MagicMock()
        app_config.agent_mode = "unknown"

        result = _try_mode_based_fallback(app_config)
        assert result is None

    def test_try_mode_based_fallback_with_empty_mode(self):
        """Test with empty agent_mode."""
        app_config = MagicMock()
        app_config.agent_mode = ""

        result = _try_mode_based_fallback(app_config)
        assert result is None


class TestResolutionCascade:
    """Test the main resolution cascade function."""

    @pytest.mark.asyncio
    async def test_resolve_from_memory_with_context(self):
        """Test resolution from memory with full context."""
        task = MagicMock()
        thought = MagicMock()
        memory_service = MagicMock()

        with patch("ciris_engine.logic.context.channel_resolution._resolve_channel_context") as mock_resolve:
            mock_resolve.return_value = ("MEM_123", MagicMock())

            channel_id, context = await resolve_channel_id_and_context(task, thought, memory_service)

            assert channel_id == "MEM_123"
            assert context is not None

    @pytest.mark.asyncio
    async def test_resolve_from_memory_without_context(self):
        """Test resolution from memory without context."""
        task = MagicMock()
        thought = MagicMock()
        memory_service = MagicMock()

        with patch("ciris_engine.logic.context.channel_resolution._resolve_channel_context") as mock_resolve:
            mock_resolve.return_value = ("MEM_123", None)

            channel_id, context = await resolve_channel_id_and_context(task, thought, memory_service)

            assert channel_id == "MEM_123"
            assert context is None

    @pytest.mark.asyncio
    async def test_resolve_from_task_channel_id(self):
        """Test resolution from task.channel_id when memory fails."""
        task = MagicMock()
        task.channel_id = "TASK_123"
        thought = MagicMock()
        memory_service = MagicMock()

        with patch("ciris_engine.logic.context.channel_resolution._resolve_channel_context") as mock_resolve:
            mock_resolve.return_value = (None, None)

            channel_id, context = await resolve_channel_id_and_context(task, thought, memory_service)

            assert channel_id == "TASK_123"
            assert context is None

    @pytest.mark.asyncio
    async def test_resolve_from_app_config_home_channel(self):
        """Test resolution from app_config.home_channel."""
        task = MagicMock()
        task.channel_id = None
        thought = MagicMock()
        memory_service = MagicMock()
        app_config = MagicMock()
        app_config.home_channel = "HOME_123"

        with patch("ciris_engine.logic.context.channel_resolution._resolve_channel_context") as mock_resolve:
            mock_resolve.return_value = (None, None)

            channel_id, context = await resolve_channel_id_and_context(task, thought, memory_service, app_config)

            assert channel_id == "HOME_123"
            assert context is None

    @pytest.mark.asyncio
    async def test_resolve_from_env_var(self):
        """Test resolution from DISCORD_CHANNEL_ID environment variable."""
        task = MagicMock()
        task.channel_id = None
        thought = MagicMock()
        memory_service = MagicMock()
        app_config = MagicMock(spec=[])

        with patch("ciris_engine.logic.context.channel_resolution._resolve_channel_context") as mock_resolve:
            mock_resolve.return_value = (None, None)
            with patch("ciris_engine.logic.context.channel_resolution.get_env_var") as mock_env:
                mock_env.return_value = "ENV_123"

                channel_id, context = await resolve_channel_id_and_context(task, thought, memory_service, app_config)

                assert channel_id == "ENV_123"
                assert context is None

    @pytest.mark.asyncio
    async def test_resolve_from_mode_specific_config(self):
        """Test resolution from mode-specific config attributes."""
        task = None
        thought = MagicMock()
        memory_service = MagicMock()
        app_config = MagicMock(spec=["discord_channel_id"])
        app_config.discord_channel_id = "DISCORD_123"

        with patch("ciris_engine.logic.context.channel_resolution._resolve_channel_context") as mock_resolve:
            mock_resolve.return_value = (None, None)
            with patch("ciris_engine.logic.context.channel_resolution.get_env_var") as mock_env:
                mock_env.return_value = None

                channel_id, context = await resolve_channel_id_and_context(task, thought, memory_service, app_config)

                assert channel_id == "DISCORD_123"
                assert context is None

    @pytest.mark.asyncio
    async def test_resolve_from_mode_based_fallback(self):
        """Test resolution from mode-based fallback."""
        task = None
        thought = MagicMock()
        memory_service = MagicMock()
        app_config = MagicMock(spec=["agent_mode"])
        app_config.agent_mode = "cli"

        with patch("ciris_engine.logic.context.channel_resolution._resolve_channel_context") as mock_resolve:
            mock_resolve.return_value = (None, None)
            with patch("ciris_engine.logic.context.channel_resolution.get_env_var") as mock_env:
                mock_env.return_value = None

                channel_id, context = await resolve_channel_id_and_context(task, thought, memory_service, app_config)

                assert channel_id == "CLI"
                assert context is None

    @pytest.mark.asyncio
    async def test_resolve_emergency_fallback(self):
        """Test emergency fallback when all sources fail."""
        task = None
        thought = MagicMock()
        memory_service = MagicMock()
        app_config = None

        with patch("ciris_engine.logic.context.channel_resolution._resolve_channel_context") as mock_resolve:
            mock_resolve.return_value = (None, None)
            with patch("ciris_engine.logic.context.channel_resolution.get_env_var") as mock_env:
                mock_env.return_value = None

                channel_id, context = await resolve_channel_id_and_context(task, thought, memory_service, app_config)

                assert channel_id == "UNKNOWN"
                assert context is None
