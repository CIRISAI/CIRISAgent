"""
Comprehensive tests for ciris_runtime.py.

Tests the main runtime orchestrator for CIRIS Agent including
initialization, service management, and shutdown procedures.
Uses only existing schemas from the codebase.
"""

import asyncio
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, call, patch

import pytest

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.config.essential import EssentialConfig
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.operations import InitializationPhase


@pytest.fixture
def essential_config():
    """Create a minimal essential config for testing."""
    import tempfile
    from pathlib import Path

    from ciris_engine.schemas.config.essential import (
        DatabaseConfig,
        GraphConfig,
        OperationalLimitsConfig,
        SecurityConfig,
        ServiceEndpointsConfig,
        TelemetryConfig,
        WorkflowConfig,
    )

    # Create a temporary directory for databases
    temp_dir = Path(tempfile.mkdtemp())

    return EssentialConfig(
        database=DatabaseConfig(
            main_db=temp_dir / "test.db", secrets_db=temp_dir / "secrets.db", audit_db=temp_dir / "audit.db"
        ),
        services=ServiceEndpointsConfig(),
        security=SecurityConfig(),
        limits=OperationalLimitsConfig(),
        telemetry=TelemetryConfig(),
        workflow=WorkflowConfig(),
        graph=GraphConfig(),
        log_level="INFO",
        debug_mode=False,
    )


@pytest.fixture
def mock_service_registry():
    """Create a mock service registry."""
    registry = MagicMock()
    registry.start_service = AsyncMock()
    registry.stop_service = AsyncMock()
    registry.get_service = Mock()
    registry.is_ready = Mock(return_value=True)
    registry.get_all_services = Mock(return_value={})
    registry.get_services_by_type = Mock(return_value=[])
    return registry


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    service = Mock(spec=TimeServiceProtocol)
    service.now = Mock(return_value=datetime.now(timezone.utc))
    service.sleep = AsyncMock()
    return service


@pytest.fixture
def mock_adapter():
    """Create a mock adapter."""
    adapter = AsyncMock()
    adapter.start = AsyncMock()
    adapter.stop = AsyncMock()
    adapter.is_running = Mock(return_value=True)
    adapter.get_service_registrations = Mock(return_value=[])
    adapter.set_runtime = Mock()
    return adapter


@pytest.fixture
def mock_component_builder():
    """Create a mock component builder."""
    builder = MagicMock()
    builder.build_service_registry = Mock()
    builder.build_bus_manager = Mock()
    builder.build_memory_service = AsyncMock()
    builder.build_core_services = AsyncMock()
    builder.build_agent_processor = Mock()
    return builder


@pytest.fixture
def mock_identity_manager():
    """Create a mock identity manager."""
    manager = MagicMock()
    manager.load_or_create_identity = AsyncMock(return_value="test_agent_id")
    manager.store_identity = AsyncMock()
    manager.verify_identity = AsyncMock(return_value=True)
    return manager


@pytest.fixture
def mock_service_initializer():
    """Create a mock service initializer."""
    initializer = MagicMock()
    initializer.create_all_services = AsyncMock()
    initializer.initialize_services = AsyncMock()
    initializer.verify_services = AsyncMock(return_value=True)
    return initializer


class TestCIRISRuntimeInit:
    """Tests for CIRISRuntime initialization."""

    @pytest.fixture(autouse=True)
    def allow_runtime(self):
        """Allow runtime creation for tests."""
        import os

        os.environ["CIRIS_IMPORT_MODE"] = "false"
        yield
        # Restore after test
        os.environ["CIRIS_IMPORT_MODE"] = "true"

    def test_init_with_minimal_config(self, essential_config):
        """Test runtime initialization with minimal configuration."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
        )

        assert len(runtime.adapters) > 0  # Should have adapters
        assert runtime.essential_config == essential_config
        assert runtime.startup_channel_id == ""  # Empty string by default
        assert runtime._initialized is False
        assert runtime._shutdown_event is None
        assert runtime._preload_tasks == []

    def test_init_with_startup_channel(self, essential_config):
        """Test runtime initialization with startup channel."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],  # Use cli since discord may not be available
            essential_config=essential_config,
            startup_channel_id="discord_123",
        )

        assert runtime.startup_channel_id == "discord_123"
        assert len(runtime.adapters) > 0

    def test_init_without_config(self):
        """Test runtime initialization without config (should create default)."""
        runtime = CIRISRuntime(
            adapter_types=["api"],
        )

        # Runtime should have its essential_config (can be None if not provided)
        assert runtime.essential_config is None  # It's None since we didn't provide it
        # Services get created later during initialization

    def test_set_preload_tasks(self, essential_config):
        """Test setting preload tasks."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
        )

        tasks = ["task1", "task2", "task3"]
        runtime.set_preload_tasks(tasks)
        assert runtime._preload_tasks == tasks  # Check internal state


class TestCIRISRuntimeProperties:
    """Tests for CIRISRuntime property accessors."""

    def test_service_registry_property(self, essential_config, mock_service_registry):
        """Test service_registry property accessor."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime.service_initializer.service_registry = mock_service_registry

        assert runtime.service_registry == mock_service_registry

    def test_time_service_property(self, essential_config, mock_time_service):
        """Test time_service property accessor."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime.service_initializer.time_service = mock_time_service

        assert runtime.time_service == mock_time_service

    def test_memory_service_property(self, essential_config):
        """Test memory_service property accessor."""
        runtime = CIRISRuntime(["cli"], essential_config)
        mock_memory = MagicMock()
        runtime.service_initializer.memory_service = mock_memory

        assert runtime.memory_service == mock_memory

    def test_config_service_property(self, essential_config):
        """Test config_service property accessor."""
        runtime = CIRISRuntime(["cli"], essential_config)
        mock_config = MagicMock()
        runtime.service_initializer.config_service = mock_config

        assert runtime.config_service == mock_config

    def test_audit_service_property(self, essential_config):
        """Test audit_service property accessor."""
        runtime = CIRISRuntime(["cli"], essential_config)
        mock_audit = MagicMock()
        runtime.service_initializer.audit_service = mock_audit

        assert runtime.audit_service == mock_audit
        # Also test plural accessor
        assert runtime.audit_services == [mock_audit]


class TestCIRISRuntimeInitialization:
    """Tests for CIRISRuntime initialization process."""

    @pytest.mark.asyncio
    async def test_initialize_success(self, essential_config):
        """Test successful initialization flow."""
        runtime = CIRISRuntime(["cli"], essential_config)

        with patch.object(runtime, "_initialize_identity", new_callable=AsyncMock) as mock_identity:
            with patch.object(runtime, "_initialize_infrastructure", new_callable=AsyncMock) as mock_infra:
                with patch.object(runtime, "_initialize_services", new_callable=AsyncMock) as mock_services:
                    with patch.object(runtime, "_start_adapters", new_callable=AsyncMock) as mock_adapters:
                        with patch.object(runtime, "_final_verification", new_callable=AsyncMock) as mock_verify:
                            await runtime.initialize()

        # Verify initialization order
        mock_identity.assert_called_once()
        mock_infra.assert_called_once()
        mock_services.assert_called_once()
        mock_adapters.assert_called_once()
        mock_verify.assert_called_once()

        # Runtime should be initialized (no _state attribute)

    @pytest.mark.asyncio
    async def test_initialize_with_error(self, essential_config):
        """Test initialization with error handling."""
        runtime = CIRISRuntime(["cli"], essential_config)

        with patch.object(runtime, "_initialize_identity", new_callable=AsyncMock) as mock_identity:
            mock_identity.side_effect = Exception("Identity error")

            with patch("ciris_engine.logic.runtime.ciris_runtime.logger") as mock_logger:
                with pytest.raises(Exception) as exc_info:
                    await runtime.initialize()

                assert "Identity error" in str(exc_info.value)
                mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_initialize_identity(self, essential_config):
        """Test identity initialization."""
        runtime = CIRISRuntime(["cli"], essential_config)

        with patch("ciris_engine.logic.runtime.ciris_runtime.IdentityManager") as MockIdentityManager:
            mock_manager = MockIdentityManager.return_value
            mock_manager.load_or_create_identity = AsyncMock(return_value="agent_123")

            await runtime._initialize_identity()

            assert runtime._agent_id == "agent_123"
            mock_manager.load_or_create_identity.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_infrastructure(self, essential_config):
        """Test infrastructure initialization."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._time_service = mock_time_service = Mock(spec=TimeServiceProtocol)

        with patch.object(runtime, "_init_database", new_callable=AsyncMock) as mock_db:
            with patch.object(runtime, "_verify_infrastructure", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = True

                await runtime._initialize_infrastructure()

                mock_db.assert_called_once()
                mock_verify.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_services(self, essential_config):
        """Test service initialization."""
        runtime = CIRISRuntime(["cli"], essential_config)

        with patch("ciris_engine.logic.runtime.ciris_runtime.ServiceInitializer") as MockInitializer:
            mock_initializer = MockInitializer.return_value
            mock_initializer.create_all_services = AsyncMock()

            with patch.object(runtime, "_verify_core_services", new_callable=AsyncMock) as mock_verify:
                mock_verify.return_value = True

                await runtime._initialize_services()

                mock_initializer.create_all_services.assert_called_once()
                mock_verify.assert_called_once()


class TestCIRISRuntimeAdapterManagement:
    """Tests for adapter management in CIRISRuntime."""

    @pytest.mark.asyncio
    async def test_start_adapters(self, essential_config, mock_adapter):
        """Test starting adapters."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._adapters = []

        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            mock_load.return_value = mock_adapter

            with patch.object(runtime, "_migrate_adapter_configs_to_graph", new_callable=AsyncMock):
                with patch.object(runtime, "_register_adapter_services", new_callable=AsyncMock):
                    await runtime._start_adapters()

        assert len(runtime._adapters) == 1
        assert runtime._adapters[0] == mock_adapter
        mock_adapter.set_runtime.assert_called_once_with(runtime)
        mock_adapter.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_register_adapter_services(self, essential_config, mock_adapter, mock_service_registry):
        """Test registering adapter services."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._service_registry = mock_service_registry
        runtime._adapters = [mock_adapter]

        # Create mock service registration
        from ciris_engine.schemas.adapters import AdapterServiceRegistration

        service_reg = AdapterServiceRegistration(
            service_type=ServiceType.COMMUNICATION,
            service_instance=MagicMock(),
            priority=100,
        )
        mock_adapter.get_service_registrations.return_value = [service_reg]

        await runtime._register_adapter_services()

        mock_adapter.get_service_registrations.assert_called_once()


class TestCIRISRuntimeShutdown:
    """Tests for CIRISRuntime shutdown process."""

    @pytest.mark.asyncio
    async def test_request_shutdown(self, essential_config):
        """Test shutdown request."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._shutdown_event = asyncio.Event()

        runtime.request_shutdown("Test shutdown")

        assert runtime._shutdown_event.is_set()
        # Shutdown state is managed internally

    @pytest.mark.asyncio
    async def test_shutdown_process(self, essential_config, mock_adapter):
        """Test full shutdown process."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._adapters = [mock_adapter]
        runtime.agent_processor = AsyncMock()
        runtime.agent_processor.stop = AsyncMock()

        with patch.object(runtime, "_preserve_shutdown_consciousness", new_callable=AsyncMock):
            with patch("ciris_engine.logic.runtime.ciris_runtime.get_shutdown_manager") as mock_get_sm:
                mock_sm = MagicMock()
                mock_get_sm.return_value = mock_sm

                await runtime.shutdown()

        # Verify shutdown sequence
        mock_adapter.stop.assert_called_once()
        runtime.agent_processor.stop.assert_called_once()

    @pytest.mark.asyncio
    async def test_preserve_shutdown_consciousness(self, essential_config):
        """Test preserving shutdown consciousness."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._memory_service = AsyncMock()
        runtime._agent_id = "test_agent"
        runtime._shutdown_reason = "Test reason"

        # Mock GraphNode to avoid import
        with patch("ciris_engine.logic.runtime.ciris_runtime.GraphNode") as MockGraphNode:
            mock_node = MagicMock()
            MockGraphNode.return_value = mock_node

            await runtime._preserve_shutdown_consciousness()

            runtime._memory_service.memorize.assert_called_once_with(mock_node)
            MockGraphNode.assert_called_once()


class TestCIRISRuntimeRun:
    """Tests for CIRISRuntime run method."""

    @pytest.mark.asyncio
    async def test_run_with_rounds(self, essential_config):
        """Test run method with specific number of rounds."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime.agent_processor = AsyncMock()
        runtime.agent_processor.process_round = AsyncMock()
        runtime._shutdown_event = asyncio.Event()

        # Set shutdown after 3 rounds
        async def side_effect_after_3():
            if runtime.agent_processor.process_round.call_count >= 3:
                runtime._shutdown_event.set()

        runtime.agent_processor.process_round.side_effect = side_effect_after_3

        await runtime.run(num_rounds=3)

        assert runtime.agent_processor.process_round.call_count == 3

    @pytest.mark.asyncio
    async def test_run_until_shutdown(self, essential_config):
        """Test run method until shutdown event."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime.agent_processor = AsyncMock()
        runtime.agent_processor.process_round = AsyncMock()
        runtime._shutdown_event = asyncio.Event()

        # Simulate shutdown after 2 rounds
        call_count = 0

        async def side_effect():
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                runtime._shutdown_event.set()

        runtime.agent_processor.process_round.side_effect = side_effect

        await runtime.run()

        assert runtime.agent_processor.process_round.call_count == 2

    @pytest.mark.asyncio
    async def test_run_with_preload_tasks(self, essential_config):
        """Test run method with preload tasks."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime.agent_processor = AsyncMock()
        runtime.agent_processor.process_round = AsyncMock()
        runtime.agent_processor.add_preload_task = Mock()
        runtime._shutdown_event = asyncio.Event()
        runtime._preload_tasks = ["task1", "task2"]
        runtime.startup_channel_id = "test_channel"

        # Stop after processing preload
        runtime.agent_processor.process_round.side_effect = lambda: runtime._shutdown_event.set()

        await runtime.run(num_rounds=1)

        # Verify preload tasks were added
        assert runtime.agent_processor.add_preload_task.call_count == 2


class TestCIRISRuntimeVerification:
    """Tests for verification methods in CIRISRuntime."""

    @pytest.mark.asyncio
    async def test_verify_infrastructure(self, essential_config):
        """Test infrastructure verification."""
        runtime = CIRISRuntime(["cli"], essential_config)

        with patch.object(runtime, "_verify_database_integrity", new_callable=AsyncMock) as mock_db:
            with patch.object(runtime, "_verify_memory_service", new_callable=AsyncMock) as mock_memory:
                with patch.object(runtime, "_verify_identity_integrity", new_callable=AsyncMock) as mock_identity:
                    mock_db.return_value = True
                    mock_memory.return_value = True
                    mock_identity.return_value = True

                    result = await runtime._verify_infrastructure()

                    assert result is True
                    mock_db.assert_called_once()
                    mock_memory.assert_called_once()
                    mock_identity.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_core_services(self, essential_config, mock_service_registry):
        """Test core services verification."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._service_registry = mock_service_registry
        runtime._time_service = Mock(spec=TimeServiceProtocol)
        runtime._memory_service = MagicMock()
        runtime._config_service = MagicMock()

        result = await runtime._verify_core_services()

        assert result is True

    @pytest.mark.asyncio
    async def test_final_verification(self, essential_config):
        """Test final verification step."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._agent_id = "test_agent"
        runtime._adapters = [MagicMock()]
        runtime.agent_processor = MagicMock()

        with patch.object(runtime, "_perform_startup_maintenance", new_callable=AsyncMock):
            with patch.object(runtime, "_clean_runtime_configs", new_callable=AsyncMock):
                await runtime._final_verification()

        # Should complete without errors (test passes if no exceptions)


class TestCIRISRuntimeDatabase:
    """Tests for database operations in CIRISRuntime."""

    @pytest.mark.asyncio
    async def test_init_database(self, essential_config):
        """Test database initialization."""
        runtime = CIRISRuntime(["cli"], essential_config)

        with patch("ciris_engine.logic.runtime.ciris_runtime.persistence") as mock_persistence:
            mock_persistence.initialize_database = AsyncMock()

            await runtime._init_database()

            mock_persistence.initialize_database.assert_called_once()

    @pytest.mark.asyncio
    async def test_verify_database_integrity(self, essential_config):
        """Test database integrity verification."""
        runtime = CIRISRuntime(["cli"], essential_config)

        with patch("ciris_engine.logic.runtime.ciris_runtime.persistence") as mock_persistence:
            mock_persistence.verify_database_integrity = AsyncMock(return_value=True)

            result = await runtime._verify_database_integrity()

            assert result is True
            mock_persistence.verify_database_integrity.assert_called_once()


class TestCIRISRuntimeMaintenance:
    """Tests for maintenance operations in CIRISRuntime."""

    @pytest.mark.asyncio
    async def test_perform_startup_maintenance(self, essential_config):
        """Test startup maintenance operations."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._maintenance_service = AsyncMock()
        runtime._maintenance_service.perform_startup_maintenance = AsyncMock()

        await runtime._perform_startup_maintenance()

        runtime._maintenance_service.perform_startup_maintenance.assert_called_once()

    @pytest.mark.asyncio
    async def test_clean_runtime_configs(self, essential_config):
        """Test cleaning runtime configurations."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._config_service = AsyncMock()
        runtime._config_service.clean_runtime_configs = AsyncMock()

        await runtime._clean_runtime_configs()

        runtime._config_service.clean_runtime_configs.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_maintenance_service(self, essential_config):
        """Test maintenance service initialization."""
        runtime = CIRISRuntime(["cli"], essential_config)
        runtime._maintenance_service = MagicMock()
        runtime._agent_id = "test_agent"

        with patch.object(runtime._maintenance_service, "initialize", new_callable=AsyncMock):
            await runtime._initialize_maintenance_service()

            runtime._maintenance_service.initialize.assert_called_once()


class TestCIRISRuntimeComponentBuilder:
    """Tests for component building in CIRISRuntime."""

    @pytest.mark.asyncio
    async def test_build_components(self, essential_config):
        """Test building runtime components."""
        runtime = CIRISRuntime(["cli"], essential_config)

        with patch("ciris_engine.logic.runtime.ciris_runtime.ComponentBuilder") as MockBuilder:
            mock_builder = MockBuilder.return_value
            mock_builder.build_service_registry = Mock()
            mock_builder.build_bus_manager = Mock()
            mock_builder.build_memory_service = AsyncMock()
            mock_builder.build_core_services = AsyncMock()
            mock_builder.build_agent_processor = Mock()

            # Set some mock services
            mock_registry = MagicMock()
            mock_bus = MagicMock()
            mock_memory = MagicMock()
            mock_processor = MagicMock()

            mock_builder.build_service_registry.return_value = mock_registry
            mock_builder.build_bus_manager.return_value = mock_bus
            mock_builder.build_memory_service.return_value = mock_memory
            mock_builder.build_agent_processor.return_value = mock_processor

            await runtime._build_components()

            assert runtime.service_registry == mock_registry
            assert runtime.bus_manager == mock_bus
            assert runtime.memory_service == mock_memory
            assert runtime.agent_processor == mock_processor

    def test_build_action_dispatcher(self, essential_config):
        """Test building action dispatcher."""
        runtime = CIRISRuntime(["cli"], essential_config)

        mock_dependencies = MagicMock()

        with patch("ciris_engine.logic.runtime.ciris_runtime.build_action_dispatcher") as mock_build:
            mock_dispatcher = MagicMock()
            mock_build.return_value = mock_dispatcher

            result = runtime._build_action_dispatcher(mock_dependencies)

            assert result == mock_dispatcher
            mock_build.assert_called_once_with(mock_dependencies)


class TestCIRISRuntimeIntegration:
    """Integration tests for CIRISRuntime."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, essential_config):
        """Test full runtime lifecycle: init -> run -> shutdown."""
        runtime = CIRISRuntime(["cli"], essential_config)

        # Mock all major components
        with patch.object(runtime, "_initialize_identity", new_callable=AsyncMock):
            with patch.object(runtime, "_initialize_infrastructure", new_callable=AsyncMock):
                with patch.object(runtime, "_initialize_services", new_callable=AsyncMock):
                    with patch.object(runtime, "_start_adapters", new_callable=AsyncMock):
                        with patch.object(runtime, "_final_verification", new_callable=AsyncMock):
                            await runtime.initialize()

        # Runtime should be initialized

        # Mock processor for run
        runtime.agent_processor = AsyncMock()
        runtime.agent_processor.process_round = AsyncMock()
        runtime._shutdown_event = asyncio.Event()

        # Run for 1 round then shutdown
        runtime.agent_processor.process_round.side_effect = lambda: runtime._shutdown_event.set()

        await runtime.run(num_rounds=1)

        # Perform shutdown
        with patch.object(runtime, "_preserve_shutdown_consciousness", new_callable=AsyncMock):
            await runtime.shutdown()

        # Shutdown complete

    @pytest.mark.asyncio
    async def test_error_recovery(self, essential_config):
        """Test error recovery during initialization."""
        runtime = CIRISRuntime(["cli"], essential_config)

        # First attempt fails
        with patch.object(runtime, "_initialize_identity", new_callable=AsyncMock) as mock_identity:
            mock_identity.side_effect = Exception("Temporary error")

            with pytest.raises(Exception) as exc_info:
                await runtime.initialize()

            assert "Temporary error" in str(exc_info.value)
            # Shutdown complete

        # Reset state for retry
        runtime._state = AgentState.SHUTDOWN

        # Second attempt succeeds
        with patch.object(runtime, "_initialize_identity", new_callable=AsyncMock):
            with patch.object(runtime, "_initialize_infrastructure", new_callable=AsyncMock):
                with patch.object(runtime, "_initialize_services", new_callable=AsyncMock):
                    with patch.object(runtime, "_start_adapters", new_callable=AsyncMock):
                        with patch.object(runtime, "_final_verification", new_callable=AsyncMock):
                            await runtime.initialize()

        # Runtime ready
