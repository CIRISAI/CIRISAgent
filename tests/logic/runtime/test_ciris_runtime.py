"""
Integration tests for ciris_runtime.py.

Tests the real CIRISRuntime initialization and lifecycle.
Uses ONLY existing schemas from the codebase - no new schemas!
"""

import asyncio
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Import the SUT
from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

# Import EXISTING schemas - no new ones!
from ciris_engine.schemas.config.essential import (
    DatabaseConfig,
    EssentialConfig,
    GraphConfig,
    OperationalLimitsConfig,
    SecurityConfig,
    ServiceEndpointsConfig,
    TelemetryConfig,
    WorkflowConfig,
)
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import ServiceType


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test databases."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def essential_config(temp_dir):
    """Create a real EssentialConfig using existing schema."""
    return EssentialConfig(
        database=DatabaseConfig(
            main_db=temp_dir / "test.db",
            secrets_db=temp_dir / "secrets.db",
            audit_db=temp_dir / "audit.db",
        ),
        services=ServiceEndpointsConfig(
            llm_endpoint="https://test.api.com",
            llm_model="test-model",
            llm_timeout=30,
            llm_max_retries=3,
        ),
        security=SecurityConfig(
            audit_retention_days=7,
            secrets_encryption_key_env="TEST_KEY",
            audit_key_path=temp_dir / "audit_keys",
            enable_signed_audit=False,
            max_thought_depth=5,
        ),
        limits=OperationalLimitsConfig(
            max_active_tasks=5,
            max_active_thoughts=10,
            round_delay_seconds=0.1,  # Fast for tests
            mock_llm_round_delay=0.01,
            dma_retry_limit=2,
            dma_timeout_seconds=10.0,
            conscience_retry_limit=1,
        ),
        telemetry=TelemetryConfig(
            enabled=False,
            export_interval_seconds=60,
            retention_hours=1,
        ),
        workflow=WorkflowConfig(
            max_rounds=5,
            round_timeout_seconds=30.0,
            enable_auto_defer=True,
        ),
        graph=GraphConfig(
            tsdb_profound_target_mb_per_day=10.0,
            tsdb_raw_retention_hours=1,
            consolidation_timezone="UTC",
        ),
        log_level="DEBUG",
        debug_mode=True,
        template_directory=temp_dir / "templates",
        default_template="test",
    )


@pytest.fixture
def allow_runtime_creation():
    """Allow runtime creation in tests by setting the environment variable."""
    original = os.environ.get("CIRIS_IMPORT_MODE")
    os.environ["CIRIS_IMPORT_MODE"] = "false"
    yield
    # Restore original value
    if original is not None:
        os.environ["CIRIS_IMPORT_MODE"] = original
    else:
        os.environ.pop("CIRIS_IMPORT_MODE", None)


class TestCIRISRuntimeCreation:
    """Test runtime creation with real components."""

    def test_create_runtime_with_config(self, essential_config, allow_runtime_creation):
        """Test creating runtime with proper config."""
        # Mock adapter loading since adapters may not be available
        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            mock_adapter_class = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_class.return_value = mock_adapter_instance
            mock_load.return_value = mock_adapter_class

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
            )

            assert runtime.essential_config == essential_config
            assert runtime.startup_channel_id == ""
            assert len(runtime.adapters) == 1
            assert runtime._initialized is False

    def test_create_runtime_without_import_mode_fails(self, essential_config):
        """Test that runtime creation fails without proper environment."""
        # Set import mode to prevent runtime creation
        os.environ["CIRIS_IMPORT_MODE"] = "true"

        with pytest.raises(RuntimeError) as exc_info:
            CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
            )

        assert "Cannot create CIRISRuntime during module imports" in str(exc_info.value)

    def test_create_runtime_with_mock_llm(self, essential_config, allow_runtime_creation):
        """Test runtime creation with mock LLM environment variable."""
        os.environ["CIRIS_MOCK_LLM"] = "true"

        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            mock_adapter_class = MagicMock()
            mock_load.return_value = mock_adapter_class

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
            )

            assert "mock_llm" in runtime.modules_to_load

        # Clean up
        os.environ.pop("CIRIS_MOCK_LLM", None)


class TestCIRISRuntimeInitialization:
    """Test runtime initialization process."""

    @pytest.mark.asyncio
    async def test_initialize_runtime(self, essential_config, allow_runtime_creation):
        """Test the initialization process with real components."""
        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            mock_adapter_class = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.start = MagicMock()
            mock_adapter_instance.get_service_registrations = MagicMock(return_value=[])
            mock_adapter_class.return_value = mock_adapter_instance
            mock_load.return_value = mock_adapter_class

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
            )

            # Mock the various initialization steps
            with patch.object(runtime, "_initialize_identity", new_callable=AsyncMock) as mock_identity:
                mock_identity.return_value = None

                with patch.object(runtime, "_initialize_infrastructure", new_callable=AsyncMock) as mock_infra:
                    mock_infra.return_value = None

                    with patch.object(runtime, "_initialize_services", new_callable=AsyncMock) as mock_services:
                        mock_services.return_value = None

                        with patch.object(runtime, "_start_adapters", new_callable=AsyncMock) as mock_adapters:
                            mock_adapters.return_value = None

                            with patch.object(runtime, "_final_verification", new_callable=AsyncMock) as mock_verify:
                                mock_verify.return_value = None

                                await runtime.initialize()

                                # Verify all initialization steps were called
                                mock_identity.assert_called_once()
                                mock_infra.assert_called_once()
                                mock_services.assert_called_once()
                                mock_adapters.assert_called_once()
                                mock_verify.assert_called_once()


class TestCIRISRuntimeLifecycle:
    """Test runtime lifecycle management."""

    def test_request_shutdown(self, essential_config, allow_runtime_creation):
        """Test requesting shutdown."""
        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            mock_adapter_class = MagicMock()
            mock_load.return_value = mock_adapter_class

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
            )

            runtime._shutdown_event = asyncio.Event()

            runtime.request_shutdown("Test shutdown")

            assert runtime._shutdown_event.is_set()
            assert runtime._shutdown_reason == "Test shutdown"

    @pytest.mark.asyncio
    async def test_run_with_rounds(self, essential_config, allow_runtime_creation):
        """Test running the runtime for a specific number of rounds."""
        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            mock_adapter_class = MagicMock()
            mock_load.return_value = mock_adapter_class

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
            )

            # Mock the processor
            runtime.agent_processor = AsyncMock()
            runtime.agent_processor.process_round = AsyncMock()
            runtime._shutdown_event = asyncio.Event()

            # Make processor trigger shutdown after 2 rounds
            call_count = 0

            async def side_effect():
                nonlocal call_count
                call_count += 1
                if call_count >= 2:
                    runtime._shutdown_event.set()

            runtime.agent_processor.process_round.side_effect = side_effect

            await runtime.run(num_rounds=2)

            assert runtime.agent_processor.process_round.call_count == 2


class TestCIRISRuntimeServices:
    """Test runtime service management."""

    def test_service_properties(self, essential_config, allow_runtime_creation):
        """Test accessing services through properties."""
        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            mock_adapter_class = MagicMock()
            mock_load.return_value = mock_adapter_class

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
            )

            # Mock services on the service initializer
            mock_memory = MagicMock()
            runtime.service_initializer.memory_service = mock_memory

            mock_registry = MagicMock()
            runtime.service_initializer.service_registry = mock_registry

            # Access through properties
            assert runtime.memory_service == mock_memory
            assert runtime.service_registry == mock_registry

    def test_bus_manager_property(self, essential_config, allow_runtime_creation):
        """Test accessing bus manager."""
        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            mock_adapter_class = MagicMock()
            mock_load.return_value = mock_adapter_class

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
            )

            mock_bus = MagicMock()
            runtime.service_initializer.bus_manager = mock_bus

            assert runtime.bus_manager == mock_bus


class TestCIRISRuntimeAdapters:
    """Test runtime adapter management."""

    def test_load_multiple_adapters(self, essential_config, allow_runtime_creation):
        """Test loading multiple adapters."""
        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            # Create different mock adapters
            cli_adapter_class = MagicMock(name="CLIAdapter")
            api_adapter_class = MagicMock(name="APIAdapter")

            def load_side_effect(adapter_name):
                if adapter_name == "cli":
                    return cli_adapter_class
                elif adapter_name == "api":
                    return api_adapter_class
                return MagicMock()

            mock_load.side_effect = load_side_effect

            runtime = CIRISRuntime(
                adapter_types=["cli", "api"],
                essential_config=essential_config,
            )

            assert len(runtime.adapters) == 2
            mock_load.assert_any_call("cli")
            mock_load.assert_any_call("api")

    def test_adapter_failure_handling(self, essential_config, allow_runtime_creation):
        """Test handling of adapter loading failures."""
        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            # Make the first adapter fail
            mock_load.side_effect = [
                Exception("Failed to load CLI adapter"),
                MagicMock(),  # API adapter succeeds
            ]

            runtime = CIRISRuntime(
                adapter_types=["cli", "api"],
                essential_config=essential_config,
            )

            # Should have only loaded the successful adapter
            assert len(runtime.adapters) == 1


class TestCIRISRuntimeIntegration:
    """Integration tests for the full runtime."""

    @pytest.mark.asyncio
    async def test_full_lifecycle(self, essential_config, allow_runtime_creation):
        """Test complete runtime lifecycle: init -> run -> shutdown."""
        with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
            mock_adapter_class = MagicMock()
            mock_adapter_instance = MagicMock()
            mock_adapter_instance.start = MagicMock()
            mock_adapter_instance.stop = AsyncMock()
            mock_adapter_instance.get_service_registrations = MagicMock(return_value=[])
            mock_adapter_class.return_value = mock_adapter_instance
            mock_load.return_value = mock_adapter_class

            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
            )

            # Initialize with mocked components
            with patch.object(runtime, "_initialize_identity", new_callable=AsyncMock):
                with patch.object(runtime, "_initialize_infrastructure", new_callable=AsyncMock):
                    with patch.object(runtime, "_initialize_services", new_callable=AsyncMock):
                        with patch.object(runtime, "_start_adapters", new_callable=AsyncMock):
                            with patch.object(runtime, "_final_verification", new_callable=AsyncMock):
                                await runtime.initialize()

            # Mock processor for run
            runtime.agent_processor = AsyncMock()
            runtime.agent_processor.process_round = AsyncMock()
            runtime.agent_processor.stop = AsyncMock()
            runtime._shutdown_event = asyncio.Event()

            # Run for 1 round then trigger shutdown
            runtime.agent_processor.process_round.side_effect = lambda: runtime._shutdown_event.set()

            await runtime.run(num_rounds=1)

            # Shutdown
            with patch.object(runtime, "_preserve_shutdown_consciousness", new_callable=AsyncMock):
                await runtime.shutdown()

            # Verify adapter was stopped
            mock_adapter_instance.stop.assert_called_once()
            runtime.agent_processor.stop.assert_called_once()
