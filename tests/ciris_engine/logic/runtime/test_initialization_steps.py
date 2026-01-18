"""Tests for initialization_steps.py module."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


class TestInitializeIdentity:
    """Tests for the initialize_identity function."""

    @pytest.mark.asyncio
    async def test_initialize_identity_with_identity_update_flag(self) -> None:
        """Test that identity refresh is called when _identity_update is True."""
        from ciris_engine.logic.runtime.initialization_steps import initialize_identity

        runtime = MagicMock()
        runtime.essential_config = MagicMock()
        runtime.essential_config.default_template = "config_default"
        runtime.time_service = MagicMock()
        runtime._identity_update = True
        runtime._template_name = "scout"

        mock_identity_manager = MagicMock()
        mock_identity = MagicMock()
        mock_identity.agent_id = "test_agent"
        mock_identity_manager.initialize_identity = AsyncMock(return_value=mock_identity)
        mock_identity_manager.refresh_identity_from_template = AsyncMock(return_value=True)
        mock_identity_manager.agent_identity = mock_identity

        with patch(
            "ciris_engine.logic.runtime.identity_manager.IdentityManager",
            return_value=mock_identity_manager,
        ), patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=False,
        ):
            runtime._create_startup_node = AsyncMock()

            await initialize_identity(runtime)

            # Verify refresh was called with correct template
            mock_identity_manager.refresh_identity_from_template.assert_called_once_with(
                template_name="scout",
                updated_by="admin",
            )

    @pytest.mark.asyncio
    async def test_initialize_identity_without_identity_update_flag(self) -> None:
        """Test that identity refresh is NOT called when _identity_update is False."""
        from ciris_engine.logic.runtime.initialization_steps import initialize_identity

        runtime = MagicMock()
        runtime.essential_config = MagicMock()
        runtime.time_service = MagicMock()
        runtime._identity_update = False
        runtime._template_name = None

        mock_identity_manager = MagicMock()
        mock_identity = MagicMock()
        mock_identity.agent_id = "test_agent"
        mock_identity_manager.initialize_identity = AsyncMock(return_value=mock_identity)
        mock_identity_manager.refresh_identity_from_template = AsyncMock(return_value=True)

        with patch(
            "ciris_engine.logic.runtime.identity_manager.IdentityManager",
            return_value=mock_identity_manager,
        ), patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=False,
        ):
            runtime._create_startup_node = AsyncMock()

            await initialize_identity(runtime)

            # Verify refresh was NOT called
            mock_identity_manager.refresh_identity_from_template.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_identity_template_fallback_to_config(self) -> None:
        """Test that template_name falls back to config.default_template."""
        from ciris_engine.logic.runtime.initialization_steps import initialize_identity

        runtime = MagicMock()
        runtime.essential_config = MagicMock()
        runtime.essential_config.default_template = "config_template"
        runtime.time_service = MagicMock()
        runtime._identity_update = True
        runtime._template_name = None  # Not set via CLI

        mock_identity_manager = MagicMock()
        mock_identity = MagicMock()
        mock_identity.agent_id = "test_agent"
        mock_identity_manager.initialize_identity = AsyncMock(return_value=mock_identity)
        mock_identity_manager.refresh_identity_from_template = AsyncMock(return_value=True)
        mock_identity_manager.agent_identity = mock_identity

        with patch(
            "ciris_engine.logic.runtime.identity_manager.IdentityManager",
            return_value=mock_identity_manager,
        ), patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=False,
        ):
            runtime._create_startup_node = AsyncMock()

            await initialize_identity(runtime)

            # Verify refresh was called with config template
            mock_identity_manager.refresh_identity_from_template.assert_called_once_with(
                template_name="config_template",
                updated_by="admin",
            )

    @pytest.mark.asyncio
    async def test_initialize_identity_update_failure_raises(self) -> None:
        """Test that identity update failure raises RuntimeError."""
        from ciris_engine.logic.runtime.initialization_steps import initialize_identity

        runtime = MagicMock()
        runtime.essential_config = MagicMock()
        runtime.essential_config.default_template = "default"
        runtime.time_service = MagicMock()
        runtime._identity_update = True
        runtime._template_name = "scout"

        mock_identity_manager = MagicMock()
        mock_identity = MagicMock()
        mock_identity.agent_id = "test_agent"
        mock_identity_manager.initialize_identity = AsyncMock(return_value=mock_identity)
        mock_identity_manager.refresh_identity_from_template = AsyncMock(return_value=False)

        with patch(
            "ciris_engine.logic.runtime.identity_manager.IdentityManager",
            return_value=mock_identity_manager,
        ), patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=False,
        ):
            with pytest.raises(RuntimeError, match="Identity update failed"):
                await initialize_identity(runtime)

    @pytest.mark.asyncio
    async def test_initialize_identity_skips_in_first_run_mode(self) -> None:
        """Test that identity seeding is skipped in first-run mode."""
        from ciris_engine.logic.runtime.initialization_steps import initialize_identity

        runtime = MagicMock()
        runtime.essential_config = MagicMock()
        runtime.time_service = MagicMock()

        mock_identity_manager = MagicMock()

        with patch(
            "ciris_engine.logic.runtime.identity_manager.IdentityManager",
            return_value=mock_identity_manager,
        ), patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=True,
        ):
            await initialize_identity(runtime)

            # Verify identity was NOT initialized (first-run mode skips seeding)
            mock_identity_manager.initialize_identity.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_identity_no_time_service_raises(self) -> None:
        """Test that missing TimeService raises RuntimeError."""
        from ciris_engine.logic.runtime.initialization_steps import initialize_identity

        runtime = MagicMock()
        runtime.essential_config = MagicMock()
        runtime.time_service = None

        with pytest.raises(RuntimeError, match="TimeService not available"):
            await initialize_identity(runtime)


class TestVerifyIdentityIntegrity:
    """Tests for the verify_identity_integrity function."""

    @pytest.mark.asyncio
    async def test_verify_identity_integrity_first_run_mode(self) -> None:
        """Test that verification passes in first-run mode without seeding."""
        from ciris_engine.logic.runtime.initialization_steps import verify_identity_integrity

        runtime = MagicMock()
        runtime.identity_manager = MagicMock()

        with patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=True,
        ):
            result = await verify_identity_integrity(runtime)

            assert result is True
            runtime.identity_manager.verify_identity_integrity.assert_not_called()

    @pytest.mark.asyncio
    async def test_verify_identity_integrity_no_identity_manager(self) -> None:
        """Test that verification fails without identity manager."""
        from ciris_engine.logic.runtime.initialization_steps import verify_identity_integrity

        runtime = MagicMock()
        runtime.identity_manager = None

        result = await verify_identity_integrity(runtime)

        assert result is False
