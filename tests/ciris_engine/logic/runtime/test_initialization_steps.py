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


class TestLoadSavedAdaptersFromGraph:
    """Tests for the load_saved_adapters_from_graph function."""

    @pytest.mark.asyncio
    async def test_load_saved_adapters_skips_in_first_run_mode(self) -> None:
        """Test that saved adapter loading is skipped in first-run mode."""
        from ciris_engine.logic.runtime.initialization_steps import load_saved_adapters_from_graph

        runtime = MagicMock()

        with patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=True,
        ):
            await load_saved_adapters_from_graph(runtime)

            # Should not try to access services
            runtime.service_initializer.config_service.list_configs.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_saved_adapters_skips_without_config_service(self) -> None:
        """Test that saved adapter loading is skipped without config service."""
        from ciris_engine.logic.runtime.initialization_steps import load_saved_adapters_from_graph

        runtime = MagicMock()
        runtime.service_initializer.config_service = None

        with patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=False,
        ):
            await load_saved_adapters_from_graph(runtime)

            # Should not fail - just skip

    @pytest.mark.asyncio
    async def test_load_saved_adapters_loads_from_graph(self) -> None:
        """Test that saved adapters are loaded from graph config."""
        from ciris_engine.logic.runtime.initialization_steps import load_saved_adapters_from_graph

        runtime = MagicMock()
        runtime.adapters = []

        # Create mock config nodes with value attribute
        class MockConfigNode:
            def __init__(self, value: str | bool | dict) -> None:
                self.value = value

        mock_config_service = MagicMock()
        mock_config_service.list_configs = AsyncMock(
            return_value={
                "adapter.covenant_metrics.type": "ciris_covenant_metrics",
                "adapter.covenant_metrics.config": {},
                "adapter.covenant_metrics.persist": True,
            }
        )
        mock_config_service.get_config = AsyncMock(
            side_effect=lambda key: {
                "adapter.covenant_metrics.type": MockConfigNode("ciris_covenant_metrics"),
                "adapter.covenant_metrics.config": MockConfigNode({"enabled": True, "settings": {}}),
                "adapter.covenant_metrics.persist": MockConfigNode(True),
            }.get(key)
        )

        mock_adapter_manager = MagicMock()
        mock_adapter_manager.loaded_adapters = {}
        mock_adapter_manager.load_adapter = AsyncMock(return_value=MagicMock(success=True))

        runtime.service_initializer.config_service = mock_config_service
        # adapter_manager is accessed via runtime_control_service
        mock_runtime_control_service = MagicMock()
        mock_runtime_control_service.adapter_manager = mock_adapter_manager
        runtime.service_initializer.runtime_control_service = mock_runtime_control_service

        with patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=False,
        ):
            await load_saved_adapters_from_graph(runtime)

            # Should have called load_adapter
            mock_adapter_manager.load_adapter.assert_called_once()

    @pytest.mark.asyncio
    async def test_load_saved_adapters_skips_already_loaded(self) -> None:
        """Test that already-loaded adapters are skipped."""
        from ciris_engine.logic.runtime.initialization_steps import load_saved_adapters_from_graph

        runtime = MagicMock()

        # Mock an adapter that's already loaded
        mock_adapter = MagicMock()
        mock_adapter.adapter_id = "api"
        runtime.adapters = [mock_adapter]

        mock_config_service = MagicMock()
        mock_config_service.list_configs = AsyncMock(
            return_value={
                "adapter.api.type": "api",
            }
        )

        mock_adapter_manager = MagicMock()
        mock_adapter_manager.loaded_adapters = {}
        mock_adapter_manager.load_adapter = AsyncMock()

        runtime.service_initializer.config_service = mock_config_service
        # adapter_manager is accessed via runtime_control_service
        mock_runtime_control_service = MagicMock()
        mock_runtime_control_service.adapter_manager = mock_adapter_manager
        runtime.service_initializer.runtime_control_service = mock_runtime_control_service

        with patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=False,
        ):
            await load_saved_adapters_from_graph(runtime)

            # Should NOT call load_adapter since adapter is already loaded
            mock_adapter_manager.load_adapter.assert_not_called()

    @pytest.mark.asyncio
    async def test_load_saved_adapters_skips_non_persistent(self) -> None:
        """Test that adapters without persist=True are skipped."""
        from ciris_engine.logic.runtime.initialization_steps import load_saved_adapters_from_graph

        runtime = MagicMock()
        runtime.adapters = []

        # Create mock config nodes with value attribute
        class MockConfigNode:
            def __init__(self, value: str | bool | dict | None) -> None:
                self.value = value

        mock_config_service = MagicMock()
        mock_config_service.list_configs = AsyncMock(
            return_value={
                "adapter.test_adapter.type": "test_type",
                "adapter.test_adapter.config": {},
                # No persist=True flag
            }
        )
        mock_config_service.get_config = AsyncMock(
            side_effect=lambda key: {
                "adapter.test_adapter.type": MockConfigNode("test_type"),
                "adapter.test_adapter.config": MockConfigNode({"enabled": True}),
                "adapter.test_adapter.persist": None,  # Not persisted
            }.get(key)
        )

        mock_adapter_manager = MagicMock()
        mock_adapter_manager.loaded_adapters = {}
        mock_adapter_manager.load_adapter = AsyncMock(return_value=MagicMock(success=True))

        runtime.service_initializer.config_service = mock_config_service
        mock_runtime_control_service = MagicMock()
        mock_runtime_control_service.adapter_manager = mock_adapter_manager
        runtime.service_initializer.runtime_control_service = mock_runtime_control_service

        with patch(
            "ciris_engine.logic.setup.first_run.is_first_run",
            return_value=False,
        ):
            await load_saved_adapters_from_graph(runtime)

            # Should NOT call load_adapter since persist=False
            mock_adapter_manager.load_adapter.assert_not_called()


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
