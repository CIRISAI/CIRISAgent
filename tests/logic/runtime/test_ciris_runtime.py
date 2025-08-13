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
    original_import = os.environ.get("CIRIS_IMPORT_MODE")
    original_mock = os.environ.get("CIRIS_MOCK_LLM")

    os.environ["CIRIS_IMPORT_MODE"] = "false"
    os.environ["CIRIS_MOCK_LLM"] = "true"  # Always use mock LLM in tests
    os.environ["OPENAI_API_KEY"] = "test-key"

    yield

    # Restore original values
    if original_import is not None:
        os.environ["CIRIS_IMPORT_MODE"] = original_import
    else:
        os.environ.pop("CIRIS_IMPORT_MODE", None)

    if original_mock is not None:
        os.environ["CIRIS_MOCK_LLM"] = original_mock
    else:
        os.environ.pop("CIRIS_MOCK_LLM", None)

    os.environ.pop("OPENAI_API_KEY", None)


class TestCIRISRuntimeCreation:
    """Test runtime creation with real components."""

    @pytest.mark.asyncio
    async def test_create_runtime_with_config(self, essential_config, allow_runtime_creation):
        """Test creating runtime with proper config."""
        # Create runtime with mock LLM to avoid external dependencies
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
        )

        assert runtime.essential_config == essential_config
        assert runtime.startup_channel_id == ""
        assert len(runtime.adapters) == 1
        assert runtime._initialized is False

        # Runtime is created successfully - no cleanup needed for this test

    def test_create_runtime_without_import_mode_fails(self, essential_config):
        """Test that runtime creation fails without proper environment."""
        # Save original value
        original = os.environ.get("CIRIS_IMPORT_MODE")

        try:
            # Set import mode to prevent runtime creation
            os.environ["CIRIS_IMPORT_MODE"] = "true"

            with pytest.raises(RuntimeError) as exc_info:
                CIRISRuntime(
                    adapter_types=["cli"],
                    essential_config=essential_config,
                )

            assert "Cannot create CIRISRuntime during module imports" in str(exc_info.value)
        finally:
            # Restore original value
            if original is not None:
                os.environ["CIRIS_IMPORT_MODE"] = original
            else:
                os.environ.pop("CIRIS_IMPORT_MODE", None)

    @pytest.mark.asyncio
    async def test_create_runtime_with_mock_llm(self, essential_config, allow_runtime_creation):
        """Test runtime creation with mock LLM environment variable."""
        os.environ["CIRIS_MOCK_LLM"] = "true"

        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            timeout=2,
        )

        assert "mock_llm" in runtime.modules_to_load

        # Clean up
        os.environ.pop("CIRIS_MOCK_LLM", None)


class TestCIRISRuntimeInitialization:
    """Test runtime initialization process."""

    @pytest.mark.asyncio
    async def test_initialize_runtime_mock_llm(self, essential_config, allow_runtime_creation):
        """Test the initialization process with mock LLM."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=5,
        )

        # Initialize runtime
        await runtime.initialize()

        # Check that runtime was initialized
        assert runtime._initialized is True
        assert runtime.agent_processor is not None
        assert runtime.service_initializer is not None

        # Clean up
        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_properties_after_init(self, essential_config, allow_runtime_creation):
        """Test accessing services after initialization."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=5,
        )

        await runtime.initialize()

        # Check service properties are accessible
        assert runtime.service_registry is not None
        assert runtime.memory_service is not None
        assert runtime.telemetry_service is not None

        await runtime.shutdown()


class TestCIRISRuntimeLifecycle:
    """Test runtime lifecycle management."""

    @pytest.mark.asyncio
    async def test_request_shutdown(self, essential_config, allow_runtime_creation):
        """Test requesting shutdown."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # Request shutdown
        runtime.request_shutdown("Test shutdown")

        assert runtime._shutdown_event.is_set()
        assert runtime._shutdown_reason == "Test shutdown"

        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_run_with_immediate_shutdown(self, essential_config, allow_runtime_creation):
        """Test running the runtime with immediate shutdown."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # Request shutdown immediately
        runtime.request_shutdown("Test shutdown")

        # Run should return immediately when shutdown is already requested
        await runtime.run(num_rounds=1)  # Should exit on first round check

        # Verify shutdown was processed
        assert runtime._shutdown_event.is_set()

        await runtime.shutdown()


class TestCIRISRuntimeServices:
    """Test runtime service management."""

    @pytest.mark.asyncio
    async def test_service_properties(self, essential_config, allow_runtime_creation):
        """Test accessing services through properties."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # Check all service properties
        assert runtime.memory_service is not None
        assert runtime.service_registry is not None
        assert runtime.bus_manager is not None
        assert runtime.resource_monitor is not None
        assert runtime.secrets_service is not None
        assert runtime.telemetry_service is not None
        assert runtime.llm_service is not None

        await runtime.shutdown()


class TestCIRISRuntimeAdapters:
    """Test runtime adapter management."""

    @pytest.mark.asyncio
    async def test_load_single_adapter(self, essential_config, allow_runtime_creation):
        """Test loading a single adapter."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        assert len(runtime.adapters) == 1
        assert runtime.adapters[0].__class__.__name__ == "CliPlatform"

    @pytest.mark.asyncio
    async def test_adapter_failure_handling(self, essential_config, allow_runtime_creation):
        """Test handling of adapter loading failures."""
        # Try to load a non-existent adapter
        with patch("ciris_engine.logic.runtime.ciris_runtime.logger") as mock_logger:
            runtime = CIRISRuntime(
                adapter_types=["nonexistent", "cli"],
                essential_config=essential_config,
                modules=["mock_llm"],
                timeout=2,
            )

            # Should have only loaded the CLI adapter
            assert len(runtime.adapters) == 1
            assert runtime.adapters[0].__class__.__name__ == "CliPlatform"

            # Check that error was logged
            assert any("Failed to load" in str(call) for call in mock_logger.error.call_args_list)


class TestCIRISRuntimeIntegration:
    """Integration tests for the full runtime."""

    @pytest.mark.asyncio
    async def test_minimal_lifecycle(self, essential_config, allow_runtime_creation):
        """Test minimal runtime lifecycle: init -> shutdown."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        # Initialize
        await runtime.initialize()
        assert runtime._initialized is True

        # Shutdown
        await runtime.shutdown()
        assert runtime._shutdown_complete is True
