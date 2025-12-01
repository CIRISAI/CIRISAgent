"""
Comprehensive coverage tests for ciris_runtime.py uncovered paths.

Focuses on:
- Runtime properties (profile, service accessors)
- Initialization flow details
- Adapter lifecycle
- Main execution loop
- Shutdown orchestration

Uses existing fixtures from tests/fixtures/runtime.py
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.schemas.config.agent import AgentTemplate, DSDMAConfiguration
from ciris_engine.schemas.processors.states import AgentState
from tests.fixtures.runtime import (
    real_runtime_with_mock,
    runtime_with_full_initialization_mocks,
    runtime_with_mocked_agent_processor,
    runtime_with_mocked_bus_manager,
)

# ============================================================================
# RUNTIME PROPERTIES TESTS
# ============================================================================


class TestRuntimeProperties:
    """Test runtime property accessors for coverage."""

    @pytest.mark.asyncio
    async def test_profile_property_with_no_identity(self, real_runtime_with_mock):
        """Test profile property returns None when no agent identity."""
        runtime = real_runtime_with_mock
        runtime.agent_identity = None

        assert runtime.profile is None

    @pytest.mark.asyncio
    async def test_profile_property_with_identity_and_dsdma(self, real_runtime_with_mock):
        """Test profile property creates AgentTemplate with DSDMA config."""
        runtime = real_runtime_with_mock

        # Create mock agent identity with DSDMA configuration
        mock_identity = Mock()
        mock_identity.agent_id = "test_agent"
        mock_identity.permitted_actions = ["read", "write"]

        mock_profile = Mock()
        mock_profile.description = "Test agent description"
        mock_profile.role_description = "Test role"
        mock_profile.domain_specific_knowledge = {"medical": "knowledge"}  # Must be dict
        mock_profile.dsdma_prompt_template = "Custom DSDMA template"
        mock_profile.csdma_overrides = {}  # Empty dict - schema may not allow extras
        mock_profile.action_selection_pdma_overrides = {}

        mock_identity.core_profile = mock_profile
        runtime.agent_identity = mock_identity

        # Get profile
        profile = runtime.profile

        # Verify AgentTemplate was created correctly
        assert isinstance(profile, AgentTemplate)
        assert profile.name == "test_agent"
        assert profile.description == "Test agent description"
        assert profile.role_description == "Test role"
        assert profile.permitted_actions == ["read", "write"]
        assert profile.dsdma_kwargs is not None
        assert isinstance(profile.dsdma_kwargs, DSDMAConfiguration)
        assert profile.dsdma_kwargs.domain_specific_knowledge == {"medical": "knowledge"}
        assert profile.dsdma_kwargs.prompt_template == "Custom DSDMA template"

    @pytest.mark.asyncio
    async def test_profile_property_with_identity_no_dsdma(self, real_runtime_with_mock):
        """Test profile property creates AgentTemplate without DSDMA config."""
        runtime = real_runtime_with_mock

        # Create mock agent identity WITHOUT DSDMA configuration
        mock_identity = Mock()
        mock_identity.agent_id = "test_agent"
        mock_identity.permitted_actions = ["read"]

        mock_profile = Mock()
        mock_profile.description = "Test description"
        mock_profile.role_description = "Test role"
        mock_profile.domain_specific_knowledge = None  # No DSDMA
        mock_profile.dsdma_prompt_template = None
        mock_profile.csdma_overrides = {}
        mock_profile.action_selection_pdma_overrides = {}

        mock_identity.core_profile = mock_profile
        runtime.agent_identity = mock_identity

        # Get profile
        profile = runtime.profile

        # Verify AgentTemplate was created without DSDMA
        assert isinstance(profile, AgentTemplate)
        assert profile.name == "test_agent"
        assert profile.dsdma_kwargs is None

    @pytest.mark.asyncio
    async def test_maintenance_service_property(self, real_runtime_with_mock):
        """Test maintenance_service property accessor."""
        runtime = real_runtime_with_mock

        mock_service = Mock()
        runtime.service_initializer = Mock()
        runtime.service_initializer.maintenance_service = mock_service

        assert runtime.maintenance_service == mock_service

    @pytest.mark.asyncio
    async def test_maintenance_service_property_no_initializer(self, real_runtime_with_mock):
        """Test maintenance_service property returns None without initializer."""
        runtime = real_runtime_with_mock
        runtime.service_initializer = None

        assert runtime.maintenance_service is None

    @pytest.mark.asyncio
    async def test_shutdown_service_property(self, real_runtime_with_mock):
        """Test shutdown_service property accessor."""
        runtime = real_runtime_with_mock

        mock_service = Mock()
        runtime.service_initializer = Mock()
        runtime.service_initializer.shutdown_service = mock_service

        assert runtime.shutdown_service == mock_service

    @pytest.mark.asyncio
    async def test_initialization_service_property(self, real_runtime_with_mock):
        """Test initialization_service property accessor."""
        runtime = real_runtime_with_mock

        mock_service = Mock()
        runtime.service_initializer = Mock()
        runtime.service_initializer.initialization_service = mock_service

        assert runtime.initialization_service == mock_service

    @pytest.mark.asyncio
    async def test_tsdb_consolidation_service_property(self, real_runtime_with_mock):
        """Test tsdb_consolidation_service property accessor."""
        runtime = real_runtime_with_mock

        mock_service = Mock()
        runtime.service_initializer = Mock()
        runtime.service_initializer.tsdb_consolidation_service = mock_service

        assert runtime.tsdb_consolidation_service == mock_service

    @pytest.mark.asyncio
    async def test_self_observation_service_property(self, real_runtime_with_mock):
        """Test self_observation_service property accessor."""
        runtime = real_runtime_with_mock

        mock_service = Mock()
        runtime.service_initializer = Mock()
        runtime.service_initializer.self_observation_service = mock_service

        assert runtime.self_observation_service == mock_service

    @pytest.mark.asyncio
    async def test_visibility_service_property(self, real_runtime_with_mock):
        """Test visibility_service property accessor."""
        runtime = real_runtime_with_mock

        mock_service = Mock()
        runtime.service_initializer = Mock()
        runtime.service_initializer.visibility_service = mock_service

        assert runtime.visibility_service == mock_service


# ============================================================================
# SHUTDOWN AND EVENT MANAGEMENT TESTS
# ============================================================================


class TestShutdownManagement:
    """Test shutdown event and request management."""

    @pytest.mark.asyncio
    async def test_ensure_shutdown_event_creates_event(self, real_runtime_with_mock):
        """Test _ensure_shutdown_event creates event when None."""
        runtime = real_runtime_with_mock
        runtime._shutdown_event = None

        runtime._ensure_shutdown_event()

        assert runtime._shutdown_event is not None
        assert isinstance(runtime._shutdown_event, asyncio.Event)

    @pytest.mark.asyncio
    async def test_ensure_shutdown_event_no_loop(self, real_runtime_with_mock):
        """Test _ensure_shutdown_event handles no event loop gracefully."""
        runtime = real_runtime_with_mock
        runtime._shutdown_event = None

        # Mock asyncio.Event to raise RuntimeError (no event loop)
        with patch("asyncio.Event", side_effect=RuntimeError("No event loop")):
            runtime._ensure_shutdown_event()

        # Should log warning but not crash
        assert runtime._shutdown_event is None

    @pytest.mark.asyncio
    async def test_ensure_config_raises_without_config(self, real_runtime_with_mock):
        """Test _ensure_config raises when essential_config is None."""
        runtime = real_runtime_with_mock
        runtime.essential_config = None

        with pytest.raises(RuntimeError, match="Essential config not initialized"):
            runtime._ensure_config()

    @pytest.mark.asyncio
    async def test_ensure_config_returns_config(self, real_runtime_with_mock):
        """Test _ensure_config returns essential_config when present."""
        runtime = real_runtime_with_mock
        mock_config = Mock()
        runtime.essential_config = mock_config

        result = runtime._ensure_config()

        assert result == mock_config

    @pytest.mark.asyncio
    async def test_request_shutdown_first_time(self, real_runtime_with_mock):
        """Test request_shutdown sets event and logs first time."""
        runtime = real_runtime_with_mock
        runtime._shutdown_event = None

        with patch("ciris_engine.logic.utils.shutdown_manager.request_global_shutdown") as mock_global:
            runtime.request_shutdown("Test reason")

        # Should create event and set it
        assert runtime._shutdown_event is not None
        assert runtime._shutdown_event.is_set()
        assert runtime._shutdown_reason == "Test reason"
        mock_global.assert_called_once()

    @pytest.mark.asyncio
    async def test_request_shutdown_duplicate_ignored(self, real_runtime_with_mock):
        """Test duplicate request_shutdown calls are ignored."""
        runtime = real_runtime_with_mock
        runtime._shutdown_event = asyncio.Event()
        runtime._shutdown_event.set()  # Already set

        with patch("ciris_engine.logic.utils.shutdown_manager.request_global_shutdown") as mock_global:
            runtime.request_shutdown("Duplicate reason")

        # Should not call global shutdown again
        mock_global.assert_not_called()


# ============================================================================
# ADAPTER LIFECYCLE TESTS
# ============================================================================


class TestAdapterLifecycle:
    """Test adapter connection startup and lifecycle management."""

    @pytest.mark.asyncio
    async def test_start_adapter_connections_success(self, runtime_with_full_initialization_mocks):
        """Test successful adapter connection startup."""
        runtime = runtime_with_full_initialization_mocks

        # Mock the helper functions - they're imported from ciris_runtime_helpers
        # Mock is_first_run to return False so normal mode path is taken
        with patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.log_adapter_configuration_details"
        ) as mock_log, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.create_adapter_lifecycle_tasks", return_value=[]
        ) as mock_create, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.wait_for_adapter_readiness", return_value=True
        ) as mock_wait, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.verify_adapter_service_registration", return_value=True
        ) as mock_verify, patch(
            "ciris_engine.logic.setup.first_run.is_first_run", return_value=False
        ):

            await runtime._start_adapter_connections()

            # Verify all helper functions were called
            mock_log.assert_called_once_with(runtime.adapters)
            mock_create.assert_called_once()
            mock_wait.assert_called_once_with(runtime.adapters)
            mock_verify.assert_called_once_with(runtime)
            runtime._wait_for_critical_services.assert_called_once_with(timeout=5.0)

    @pytest.mark.asyncio
    async def test_start_adapter_connections_adapters_not_ready(self, runtime_with_full_initialization_mocks):
        """Test adapter connection startup when adapters fail to become ready."""
        runtime = runtime_with_full_initialization_mocks

        # Mock adapters not ready
        with patch("ciris_engine.logic.runtime.ciris_runtime_helpers.log_adapter_configuration_details"), patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.create_adapter_lifecycle_tasks", return_value=[]
        ), patch("ciris_engine.logic.runtime.ciris_runtime_helpers.wait_for_adapter_readiness", return_value=False):

            with pytest.raises(RuntimeError, match="Adapters failed to become ready"):
                await runtime._start_adapter_connections()

    @pytest.mark.asyncio
    async def test_start_adapter_connections_services_not_available(self, runtime_with_full_initialization_mocks):
        """Test adapter connection startup when service registration fails."""
        runtime = runtime_with_full_initialization_mocks

        # Mock services not available
        # Mock is_first_run to return False so normal mode path is taken
        with patch("ciris_engine.logic.runtime.ciris_runtime_helpers.log_adapter_configuration_details"), patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.create_adapter_lifecycle_tasks", return_value=[]
        ), patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.wait_for_adapter_readiness", return_value=True
        ), patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.verify_adapter_service_registration", return_value=False
        ), patch(
            "ciris_engine.logic.setup.first_run.is_first_run", return_value=False
        ):

            with pytest.raises(RuntimeError, match="Failed to establish adapter connections"):
                await runtime._start_adapter_connections()


# ============================================================================
# MAIN EXECUTION LOOP TESTS
# ============================================================================


class TestMainExecutionLoop:
    """Test the main runtime execution loop."""

    @pytest.mark.asyncio
    async def test_run_initializes_if_not_initialized(self, runtime_with_full_initialization_mocks):
        """Test run() calls initialize() if not already initialized."""
        runtime = runtime_with_full_initialization_mocks
        runtime._initialized = False
        runtime.initialize = AsyncMock()
        runtime.shutdown = AsyncMock()  # Add shutdown mock to prevent it running

        # Mock the setup to return no agent task (early exit)
        with patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.setup_runtime_monitoring_tasks",
            return_value=(None, [], []),
        ):
            await runtime.run()

        runtime.initialize.assert_called_once()
        runtime.shutdown.assert_called_once()  # Should still call shutdown in finally

    @pytest.mark.asyncio
    async def test_run_handles_keyboard_interrupt(self, runtime_with_mocked_agent_processor):
        """Test run() handles KeyboardInterrupt gracefully."""
        runtime = runtime_with_mocked_agent_processor
        runtime._initialized = True
        runtime.shutdown = AsyncMock()

        # Mock setup to raise KeyboardInterrupt
        with patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.setup_runtime_monitoring_tasks",
            side_effect=KeyboardInterrupt,
        ):
            await runtime.run()

        # Should have requested shutdown
        assert runtime._shutdown_reason == "KeyboardInterrupt"
        runtime.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_handles_general_exception(self, runtime_with_mocked_agent_processor):
        """Test run() handles general exceptions gracefully."""
        runtime = runtime_with_mocked_agent_processor
        runtime._initialized = True
        runtime.shutdown = AsyncMock()

        # Mock setup to raise general exception
        with patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.setup_runtime_monitoring_tasks",
            side_effect=RuntimeError("Test error"),
        ):
            await runtime.run()

        # Should still call shutdown
        runtime.shutdown.assert_called_once()


# ============================================================================
# SHUTDOWN ORCHESTRATION TESTS
# ============================================================================


class TestShutdownOrchestration:
    """Test the complete shutdown orchestration flow."""

    @pytest.mark.asyncio
    async def test_shutdown_full_sequence(self, runtime_with_full_initialization_mocks):
        """Test complete shutdown sequence calls all helpers in order."""
        runtime = runtime_with_full_initialization_mocks
        runtime._shutdown_complete = False
        runtime._shutdown_event = asyncio.Event()

        # Mock all helper functions
        with patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.validate_shutdown_preconditions", return_value=True
        ) as mock_validate, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.prepare_shutdown_maintenance_tasks"
        ) as mock_prepare, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.execute_final_maintenance_tasks"
        ) as mock_maintenance, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.preserve_critical_system_state"
        ) as mock_preserve, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.handle_agent_processor_shutdown"
        ) as mock_agent, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.handle_adapter_shutdown_cleanup"
        ) as mock_adapter, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.execute_service_shutdown_sequence"
        ) as mock_services, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.finalize_shutdown_logging"
        ) as mock_logging, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.cleanup_runtime_resources"
        ) as mock_cleanup, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.validate_shutdown_completion"
        ) as mock_complete:

            await runtime.shutdown()

            # Verify all steps were called in sequence
            mock_validate.assert_called_once_with(runtime)
            mock_prepare.assert_called_once_with(runtime)
            mock_maintenance.assert_called_once_with(runtime)
            mock_preserve.assert_called_once_with(runtime)
            mock_agent.assert_called_once_with(runtime)
            mock_adapter.assert_called_once_with(runtime)
            mock_services.assert_called_once_with(runtime)
            mock_logging.assert_called_once_with(runtime)
            mock_cleanup.assert_called_once_with(runtime)
            mock_complete.assert_called_once_with(runtime)

            # Verify shutdown event was set
            assert runtime._shutdown_event.is_set()

    @pytest.mark.asyncio
    async def test_shutdown_early_exit_on_validation_failure(self, runtime_with_full_initialization_mocks):
        """Test shutdown exits early if preconditions fail."""
        runtime = runtime_with_full_initialization_mocks

        # Mock validation to return False
        with patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.validate_shutdown_preconditions", return_value=False
        ) as mock_validate, patch(
            "ciris_engine.logic.runtime.ciris_runtime_helpers.prepare_shutdown_maintenance_tasks"
        ) as mock_prepare:

            await runtime.shutdown()

            # Validation should be called
            mock_validate.assert_called_once_with(runtime)

            # But no other shutdown steps should run
            mock_prepare.assert_not_called()


# ============================================================================
# TICKETS CONFIG MIGRATION TESTS
# ============================================================================


class TestTicketsConfigMigration:
    """Test the _migrate_tickets_config_to_graph method."""

    @pytest.mark.asyncio
    async def test_migrate_tickets_no_service_initializer(self, real_runtime_with_mock):
        """Test migration returns early when service_initializer not available."""
        runtime = real_runtime_with_mock
        runtime.service_initializer = None

        # Should not raise, just return early
        await runtime._migrate_tickets_config_to_graph()

    @pytest.mark.asyncio
    async def test_migrate_tickets_no_config_service(self, real_runtime_with_mock):
        """Test migration returns early when config_service not available."""
        runtime = real_runtime_with_mock
        runtime.service_initializer = Mock()
        runtime.service_initializer.config_service = None

        # Should not raise, just return early
        await runtime._migrate_tickets_config_to_graph()

    @pytest.mark.asyncio
    async def test_migrate_tickets_config_already_exists(self, real_runtime_with_mock):
        """Test migration skips when tickets config already exists in graph."""
        runtime = real_runtime_with_mock

        # Mock config_service with existing config
        mock_config_service = AsyncMock()
        mock_existing_config = Mock()
        mock_existing_config.value = Mock()
        mock_existing_config.value.dict_value = {"enabled": True, "sops": {}}
        mock_config_service.get_config = AsyncMock(return_value=mock_existing_config)

        runtime.service_initializer = Mock()
        runtime.service_initializer.config_service = mock_config_service

        await runtime._migrate_tickets_config_to_graph()

        # Should check for existing config but not set new one
        mock_config_service.get_config.assert_called_once_with("tickets")
        mock_config_service.set_config.assert_not_called()

    @pytest.mark.asyncio
    async def test_migrate_tickets_from_template(self, real_runtime_with_mock):
        """Test migration uses template tickets config when available."""
        runtime = real_runtime_with_mock

        # Mock config_service with no existing config
        mock_config_service = AsyncMock()
        mock_config_service.get_config = AsyncMock(return_value=None)
        mock_config_service.set_config = AsyncMock()

        runtime.service_initializer = Mock()
        runtime.service_initializer.config_service = mock_config_service

        # Mock identity_manager with template that has tickets config
        from ciris_engine.schemas.config.tickets import TicketsConfig

        mock_tickets_config = TicketsConfig(enabled=True, sops=[])
        runtime.identity_manager = Mock()
        runtime.identity_manager.agent_template = Mock()
        runtime.identity_manager.agent_template.tickets = mock_tickets_config

        await runtime._migrate_tickets_config_to_graph()

        # Should set config from template
        mock_config_service.set_config.assert_called_once()
        call_args = mock_config_service.set_config.call_args
        assert call_args.kwargs["key"] == "tickets"
        assert call_args.kwargs["updated_by"] == "system_bootstrap"

    @pytest.mark.asyncio
    async def test_migrate_tickets_creates_default_dsar_sops(self, real_runtime_with_mock):
        """Test migration creates default DSAR SOPs for pre-1.7.0 agents."""
        runtime = real_runtime_with_mock

        # Mock config_service with no existing config
        mock_config_service = AsyncMock()
        mock_config_service.get_config = AsyncMock(return_value=None)
        mock_config_service.set_config = AsyncMock()

        runtime.service_initializer = Mock()
        runtime.service_initializer.config_service = mock_config_service

        # No identity_manager or template - simulates pre-1.7.0 agent
        runtime.identity_manager = None

        await runtime._migrate_tickets_config_to_graph()

        # Should set config with default DSAR SOPs
        mock_config_service.set_config.assert_called_once()
        call_args = mock_config_service.set_config.call_args
        assert call_args.kwargs["key"] == "tickets"
        assert call_args.kwargs["updated_by"] == "system_bootstrap"
        # Value should have the default SOPs
        assert "sops" in call_args.kwargs["value"]

    @pytest.mark.asyncio
    async def test_migrate_tickets_handles_set_config_error(self, real_runtime_with_mock):
        """Test migration handles errors when setting config."""
        runtime = real_runtime_with_mock

        # Mock config_service that fails on set_config
        mock_config_service = AsyncMock()
        mock_config_service.get_config = AsyncMock(return_value=None)
        mock_config_service.set_config = AsyncMock(side_effect=Exception("Database error"))

        runtime.service_initializer = Mock()
        runtime.service_initializer.config_service = mock_config_service
        runtime.identity_manager = None

        # Should not raise, just log error
        await runtime._migrate_tickets_config_to_graph()

    @pytest.mark.asyncio
    async def test_migrate_tickets_handles_get_config_exception(self, real_runtime_with_mock):
        """Test migration handles exceptions when checking existing config."""
        runtime = real_runtime_with_mock

        # Mock config_service that raises on get_config
        mock_config_service = AsyncMock()
        mock_config_service.get_config = AsyncMock(side_effect=Exception("Query failed"))
        mock_config_service.set_config = AsyncMock()

        runtime.service_initializer = Mock()
        runtime.service_initializer.config_service = mock_config_service
        runtime.identity_manager = None

        # Should continue with migration after get_config fails
        await runtime._migrate_tickets_config_to_graph()

        # Should still try to set config
        mock_config_service.set_config.assert_called_once()

    @pytest.mark.asyncio
    async def test_migrate_tickets_template_without_tickets(self, real_runtime_with_mock):
        """Test migration uses defaults when template has no tickets config."""
        runtime = real_runtime_with_mock

        # Mock config_service with no existing config
        mock_config_service = AsyncMock()
        mock_config_service.get_config = AsyncMock(return_value=None)
        mock_config_service.set_config = AsyncMock()

        runtime.service_initializer = Mock()
        runtime.service_initializer.config_service = mock_config_service

        # Mock identity_manager with template but no tickets
        runtime.identity_manager = Mock()
        runtime.identity_manager.agent_template = Mock()
        runtime.identity_manager.agent_template.tickets = None

        await runtime._migrate_tickets_config_to_graph()

        # Should set default DSAR SOPs
        mock_config_service.set_config.assert_called_once()
        call_args = mock_config_service.set_config.call_args
        assert "sops" in call_args.kwargs["value"]
