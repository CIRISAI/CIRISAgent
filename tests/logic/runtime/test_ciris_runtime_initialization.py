"""
Tests for ciris_runtime.py initialization flow to reach 80% coverage.

Focuses on:
- Runtime __init__ with adapter loading
- Full initialize() method flow
- Initialization phases and steps
- Agent processor creation (_create_agent_processor_when_ready)
- Internal initialization methods
"""

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from tests.fixtures.runtime import real_runtime_with_mock, runtime_with_full_initialization_mocks

# ============================================================================
# RUNTIME __INIT__ TESTS
# ============================================================================


class TestRuntimeInit:
    """Test runtime __init__ with adapter loading and error handling."""

    @pytest.mark.asyncio
    async def test_init_with_adapter_configs(self, real_runtime_with_mock):
        """Test __init__ applies adapter_configs to adapters."""
        # The real_runtime_with_mock fixture already loads CLI adapter
        runtime = real_runtime_with_mock

        # Verify adapter was loaded
        assert len(runtime.adapters) > 0
        assert runtime._initialized == False
        assert runtime._shutdown_complete == False

    @pytest.mark.asyncio
    async def test_init_adapter_load_exception_handling(self):
        """Test __init__ handles adapter load exceptions gracefully."""
        # Set environment to allow runtime creation
        original_import = os.environ.get("CIRIS_IMPORT_MODE")
        original_mock = os.environ.get("CIRIS_MOCK_LLM")
        os.environ["CIRIS_IMPORT_MODE"] = "false"
        os.environ["CIRIS_MOCK_LLM"] = "true"

        try:
            # Mock load_adapter to raise exception (imported inside bootstrap_helpers)
            with patch("ciris_engine.logic.adapters.load_adapter", side_effect=Exception("Load failed")):
                # Should still create runtime but log error
                runtime = CIRISRuntime(adapter_types=["fake_adapter"], modules=["mock_llm"])

                # Runtime created but with empty adapters due to exception
                # Actually, it will raise RuntimeError because no valid adapters
                assert False, "Should have raised RuntimeError"
        except RuntimeError as e:
            # Expected - no valid adapters
            assert "No valid adapters" in str(e)
        finally:
            # Restore environment
            if original_import is not None:
                os.environ["CIRIS_IMPORT_MODE"] = original_import
            else:
                os.environ.pop("CIRIS_IMPORT_MODE", None)

            if original_mock is not None:
                os.environ["CIRIS_MOCK_LLM"] = original_mock
            else:
                os.environ.pop("CIRIS_MOCK_LLM", None)


# ============================================================================
# INITIALIZE() METHOD TESTS
# ============================================================================


class TestRuntimeInitialize:
    """Test the full initialize() method flow."""

    @pytest.mark.asyncio
    async def test_initialize_skips_if_already_initialized(self, runtime_with_full_initialization_mocks):
        """Test initialize() returns early if already initialized."""
        runtime = runtime_with_full_initialization_mocks
        runtime._initialized = True

        # Mock service initializer to verify it's not called
        runtime.service_initializer.initialize_infrastructure_services = AsyncMock()

        await runtime.initialize()

        # Should not call service initializer since already initialized
        runtime.service_initializer.initialize_infrastructure_services.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_directory_setup_development(self, runtime_with_full_initialization_mocks):
        """Test initialize() sets up directories in development environment."""
        runtime = runtime_with_full_initialization_mocks
        runtime._initialized = False

        with patch("ciris_engine.logic.utils.directory_setup.setup_application_directories") as mock_setup, patch(
            "ciris_engine.logic.utils.directory_setup.validate_directories"
        ) as mock_validate, patch.dict(os.environ, {"CIRIS_ENV": "dev"}):

            # Mock the rest of initialization to focus on directory setup
            mock_init_service = Mock()
            mock_init_service.initialize = AsyncMock(return_value=True)
            runtime.service_initializer.initialize_infrastructure_services = AsyncMock()
            runtime.service_initializer.initialization_service = mock_init_service
            runtime._register_initialization_steps = Mock()
            runtime.agent_identity = Mock()
            runtime.agent_identity.agent_id = "test_agent"

            await runtime.initialize()

            # Should call setup_application_directories for dev environment
            mock_setup.assert_called_once()
            mock_validate.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_directory_setup_production(self, runtime_with_full_initialization_mocks):
        """Test initialize() validates directories in production environment."""
        runtime = runtime_with_full_initialization_mocks
        runtime._initialized = False

        with patch("ciris_engine.logic.utils.directory_setup.setup_application_directories") as mock_setup, patch(
            "ciris_engine.logic.utils.directory_setup.validate_directories"
        ) as mock_validate, patch.dict(os.environ, {"CIRIS_ENV": "prod"}):

            # Mock the rest of initialization
            mock_init_service = Mock()
            mock_init_service.initialize = AsyncMock(return_value=True)
            runtime.service_initializer.initialize_infrastructure_services = AsyncMock()
            runtime.service_initializer.initialization_service = mock_init_service
            runtime._register_initialization_steps = Mock()
            runtime.agent_identity = Mock()
            runtime.agent_identity.agent_id = "test_agent"

            await runtime.initialize()

            # Should call validate_directories for production
            mock_validate.assert_called_once()
            mock_setup.assert_not_called()

    @pytest.mark.asyncio
    async def test_initialize_directory_setup_failure(self, runtime_with_full_initialization_mocks):
        """Test initialize() handles directory setup failure."""
        runtime = runtime_with_full_initialization_mocks
        runtime._initialized = False

        from ciris_engine.logic.utils.directory_setup import DirectorySetupError

        with patch(
            "ciris_engine.logic.utils.directory_setup.setup_application_directories",
            side_effect=DirectorySetupError("Setup failed"),
        ):

            with pytest.raises(RuntimeError, match="Cannot start: Directory setup failed"):
                await runtime.initialize()

            # Should not be marked as initialized
            assert runtime._initialized == False

    @pytest.mark.asyncio
    async def test_initialize_no_initialization_service(self, runtime_with_full_initialization_mocks):
        """Test initialize() raises error when initialization service not available."""
        runtime = runtime_with_full_initialization_mocks
        runtime._initialized = False

        with patch("ciris_engine.logic.utils.directory_setup.setup_application_directories"):
            # Mock infrastructure services to initialize but return None for init service
            runtime.service_initializer.initialize_infrastructure_services = AsyncMock()
            runtime.service_initializer.initialization_service = None

            with pytest.raises(RuntimeError, match="InitializationService not available"):
                await runtime.initialize()

    @pytest.mark.asyncio
    async def test_initialize_sequence_failure(self, runtime_with_full_initialization_mocks):
        """Test initialize() handles initialization sequence failure."""
        runtime = runtime_with_full_initialization_mocks
        runtime._initialized = False

        with patch("ciris_engine.logic.utils.directory_setup.setup_application_directories"):
            # Mock initialization service that returns False (failure)
            mock_init_service = Mock()
            mock_init_service.initialize = AsyncMock(return_value=False)
            runtime.service_initializer.initialize_infrastructure_services = AsyncMock()
            runtime.service_initializer.initialization_service = mock_init_service
            runtime._register_initialization_steps = Mock()

            with pytest.raises(RuntimeError, match="Initialization sequence failed"):
                await runtime.initialize()

            assert runtime._initialized == False

    @pytest.mark.asyncio
    async def test_initialize_timeout_error(self, runtime_with_full_initialization_mocks):
        """Test initialize() handles timeout errors."""
        runtime = runtime_with_full_initialization_mocks
        runtime._initialized = False

        with patch("ciris_engine.logic.utils.directory_setup.setup_application_directories"):
            # Mock initialization to timeout
            runtime.service_initializer.initialize_infrastructure_services = AsyncMock(
                side_effect=asyncio.TimeoutError("Init timeout")
            )

            with pytest.raises(asyncio.TimeoutError):
                await runtime.initialize()

            assert runtime._initialized == False

    @pytest.mark.asyncio
    async def test_initialize_maintenance_failure(self, runtime_with_full_initialization_mocks):
        """Test initialize() handles maintenance-related failures."""
        runtime = runtime_with_full_initialization_mocks
        runtime._initialized = False

        with patch("ciris_engine.logic.utils.directory_setup.setup_application_directories"):
            # Mock initialization to raise maintenance error
            runtime.service_initializer.initialize_infrastructure_services = AsyncMock(
                side_effect=Exception("Database maintenance failure")
            )

            with pytest.raises(Exception, match="maintenance"):
                await runtime.initialize()

            assert runtime._initialized == False


# ============================================================================
# INTERNAL INITIALIZATION METHOD TESTS
# ============================================================================


class TestInternalInitializationMethods:
    """Test internal initialization helper methods."""

    @pytest.mark.asyncio
    async def test_initialize_identity(self, runtime_with_full_initialization_mocks):
        """Test _initialize_identity creates IdentityManager and initializes identity."""
        runtime = runtime_with_full_initialization_mocks

        # Mock time service via service_initializer (time_service is a property)
        mock_time_service = Mock()
        runtime.service_initializer = Mock()
        runtime.service_initializer.time_service = mock_time_service

        # Mock essential config
        mock_config = Mock()
        runtime.essential_config = mock_config

        # Mock IdentityManager and first_run check
        with patch("ciris_engine.logic.runtime.ciris_runtime.IdentityManager") as MockIdentityManager, patch(
            "ciris_engine.logic.setup.first_run.is_first_run", return_value=False
        ):
            mock_identity_manager = Mock()
            mock_identity = Mock()
            mock_identity.agent_id = "test_agent"
            mock_identity_manager.initialize_identity = AsyncMock(return_value=mock_identity)
            MockIdentityManager.return_value = mock_identity_manager

            # Mock _create_startup_node since it's called after identity init
            runtime._create_startup_node = AsyncMock()

            await runtime._initialize_identity()

            # Verify IdentityManager was created with correct arguments
            MockIdentityManager.assert_called_once_with(mock_config, mock_time_service)
            mock_identity_manager.initialize_identity.assert_called_once()
            assert runtime.agent_identity == mock_identity

    @pytest.mark.asyncio
    async def test_initialize_identity_no_time_service(self, runtime_with_full_initialization_mocks):
        """Test _initialize_identity raises error when time service not available."""
        runtime = runtime_with_full_initialization_mocks
        runtime.service_initializer = Mock()
        runtime.service_initializer.time_service = None  # time_service property delegates here
        runtime.essential_config = Mock()

        with pytest.raises(RuntimeError, match="TimeService not available"):
            await runtime._initialize_identity()


# ============================================================================
# AGENT PROCESSOR CREATION TESTS
# ============================================================================


class TestAgentProcessorCreation:
    """Test _create_agent_processor_when_ready method."""

    @pytest.mark.asyncio
    async def test_create_agent_processor_when_ready_with_bus_manager(self, runtime_with_full_initialization_mocks):
        """Test agent processor creation with bus manager present."""
        runtime = runtime_with_full_initialization_mocks

        # Mock agent processor
        mock_agent_processor = AsyncMock()
        mock_agent_processor.start_processing = AsyncMock()
        runtime.agent_processor = mock_agent_processor

        # Mock bus manager
        mock_bus_manager = Mock()
        mock_bus_manager.start = AsyncMock()  # Must be AsyncMock
        runtime.service_initializer = Mock()
        runtime.service_initializer.bus_manager = mock_bus_manager

        # Mock wait for critical services
        runtime._wait_for_critical_services = AsyncMock()

        await runtime._create_agent_processor_when_ready()

        # Verify agent processor started
        mock_agent_processor.start_processing.assert_called_once()
        runtime._wait_for_critical_services.assert_called_once_with(timeout=30.0)

    @pytest.mark.asyncio
    async def test_create_agent_processor_when_ready_without_bus_manager(self, runtime_with_full_initialization_mocks):
        """Test agent processor creation without bus manager."""
        runtime = runtime_with_full_initialization_mocks

        # Mock agent processor
        mock_agent_processor = AsyncMock()
        mock_agent_processor.start_processing = AsyncMock()
        runtime.agent_processor = mock_agent_processor

        # No bus manager
        runtime.service_initializer = Mock()
        runtime.service_initializer.bus_manager = None

        # Mock wait for critical services
        runtime._wait_for_critical_services = AsyncMock()

        await runtime._create_agent_processor_when_ready()

        # Should still work without bus manager
        mock_agent_processor.start_processing.assert_called_once()
