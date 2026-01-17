"""Tests for config_migration.py module."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch


class TestConfigMigration:
    """Tests for configuration migration utilities."""

    def test_should_skip_cognitive_migration_in_first_run(self) -> None:
        """Test that cognitive migration is skipped in first-run mode without force."""
        from ciris_engine.logic.runtime.config_migration import should_skip_cognitive_migration

        runtime = MagicMock()

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=True):
            result = should_skip_cognitive_migration(runtime, force_from_template=False)
            assert result is True

    def test_should_not_skip_cognitive_migration_when_forced(self) -> None:
        """Test that cognitive migration proceeds when forced even in first-run."""
        from ciris_engine.logic.runtime.config_migration import should_skip_cognitive_migration

        runtime = MagicMock()

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=True):
            result = should_skip_cognitive_migration(runtime, force_from_template=True)
            assert result is False

    def test_should_not_skip_cognitive_migration_not_first_run(self) -> None:
        """Test that cognitive migration proceeds when not in first-run mode."""
        from ciris_engine.logic.runtime.config_migration import should_skip_cognitive_migration

        runtime = MagicMock()

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            result = should_skip_cognitive_migration(runtime, force_from_template=False)
            assert result is False

    @pytest.mark.asyncio
    async def test_check_existing_cognitive_config_exists(self) -> None:
        """Test detection of existing cognitive config in graph."""
        from ciris_engine.logic.runtime.config_migration import check_existing_cognitive_config

        config_service = AsyncMock()
        mock_config = MagicMock()
        mock_config.value.dict_value = {"wakeup": {"enabled": True}}
        config_service.get_config.return_value = mock_config

        result = await check_existing_cognitive_config(config_service)
        assert result is True

    @pytest.mark.asyncio
    async def test_check_existing_cognitive_config_not_exists(self) -> None:
        """Test when cognitive config doesn't exist in graph."""
        from ciris_engine.logic.runtime.config_migration import check_existing_cognitive_config

        config_service = AsyncMock()
        config_service.get_config.side_effect = Exception("Config not found")

        result = await check_existing_cognitive_config(config_service)
        assert result is False

    def test_get_cognitive_behaviors_from_template_with_template(self) -> None:
        """Test getting cognitive behaviors when template is available."""
        from ciris_engine.logic.runtime.config_migration import get_cognitive_behaviors_from_template

        runtime = MagicMock()
        mock_behaviors = MagicMock()
        runtime.identity_manager.agent_template.cognitive_state_behaviors = mock_behaviors

        result = get_cognitive_behaviors_from_template(runtime)
        assert result is mock_behaviors

    def test_get_cognitive_behaviors_from_template_no_template(self) -> None:
        """Test getting cognitive behaviors when no template is available."""
        from ciris_engine.logic.runtime.config_migration import get_cognitive_behaviors_from_template

        runtime = MagicMock()
        runtime.identity_manager = None

        result = get_cognitive_behaviors_from_template(runtime)
        assert result is None

    def test_create_legacy_cognitive_behaviors(self) -> None:
        """Test creation of legacy-compatible cognitive behaviors."""
        from ciris_engine.logic.runtime.config_migration import create_legacy_cognitive_behaviors

        behaviors = create_legacy_cognitive_behaviors()

        # Verify legacy behaviors are disabled
        assert behaviors.play.enabled is False
        assert behaviors.dream.enabled is False
        assert behaviors.solitude.enabled is False
        # State preservation should be enabled
        assert behaviors.state_preservation.enabled is True

    @pytest.mark.asyncio
    async def test_save_cognitive_behaviors_to_graph(self) -> None:
        """Test saving cognitive behaviors to graph."""
        from ciris_engine.logic.runtime.config_migration import save_cognitive_behaviors_to_graph
        from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors

        config_service = AsyncMock()
        behaviors = CognitiveStateBehaviors()

        await save_cognitive_behaviors_to_graph(config_service, behaviors)

        config_service.set_config.assert_called_once()
        call_kwargs = config_service.set_config.call_args.kwargs
        assert call_kwargs["key"] == "cognitive_state_behaviors"
        assert call_kwargs["updated_by"] == "system_bootstrap"
