"""
Integration tests for ciris_runtime.py.

Tests the real CIRISRuntime initialization and lifecycle.
Uses ONLY existing schemas from the codebase - no new schemas!
"""

import asyncio
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Add extensive logging to debug CI issues
print(f"[test_ciris_runtime] Starting imports - Python {sys.version}")
print(f"[test_ciris_runtime] __name__ = {__name__}")
print(f"[test_ciris_runtime] Current working directory: {os.getcwd()}")
print(f"[test_ciris_runtime] CIRIS_IMPORT_MODE before import: {os.environ.get('CIRIS_IMPORT_MODE', 'NOT SET')}")
print(f"[test_ciris_runtime] CIRIS_MOCK_LLM before import: {os.environ.get('CIRIS_MOCK_LLM', 'NOT SET')}")

# Import the SUT
try:
    from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

    print(f"[test_ciris_runtime] Successfully imported CIRISRuntime: {CIRISRuntime}")
    print(f"[test_ciris_runtime] CIRISRuntime type: {type(CIRISRuntime)}")
    print(f"[test_ciris_runtime] CIRISRuntime module: {CIRISRuntime.__module__}")
    print(f"[test_ciris_runtime] CIRISRuntime __class__: {CIRISRuntime.__class__}")
    print(f"[test_ciris_runtime] CIRISRuntime __new__: {CIRISRuntime.__new__}")
    print(f"[test_ciris_runtime] CIRISRuntime __init__: {CIRISRuntime.__init__}")
except Exception as e:
    print(f"[test_ciris_runtime] ERROR importing CIRISRuntime: {e}")
    print(f"[test_ciris_runtime] Exception type: {type(e)}")
    import traceback

    traceback.print_exc()
    raise

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


def _diagnose_ciris_runtime():
    """Diagnostic function to understand CIRISRuntime state."""
    print("\n" + "=" * 60)
    print("[DIAGNOSTIC] Checking CIRISRuntime state")
    print("=" * 60)

    # Check if we can import it fresh
    try:
        import importlib
        import sys

        # Check if it's already in sys.modules
        if "ciris_engine.logic.runtime.ciris_runtime" in sys.modules:
            print(f"[DIAGNOSTIC] Module already in sys.modules")
            existing = sys.modules["ciris_engine.logic.runtime.ciris_runtime"]
            print(f"[DIAGNOSTIC] Existing module: {existing}")
            if hasattr(existing, "CIRISRuntime"):
                print(f"[DIAGNOSTIC] Existing CIRISRuntime: {existing.CIRISRuntime}")
                print(f"[DIAGNOSTIC] Is it a type? {isinstance(existing.CIRISRuntime, type)}")

        # Try fresh import
        print(f"[DIAGNOSTIC] Attempting fresh import...")
        mod = importlib.import_module("ciris_engine.logic.runtime.ciris_runtime")
        cls = getattr(mod, "CIRISRuntime")
        print(f"[DIAGNOSTIC] Fresh CIRISRuntime: {cls}")
        print(f"[DIAGNOSTIC] Fresh type: {type(cls)}")
        print(f"[DIAGNOSTIC] Fresh __new__: {cls.__new__}")

        # Compare with what we have
        print(f"[DIAGNOSTIC] Comparing with test's CIRISRuntime...")
        print(f"[DIAGNOSTIC] Are they the same? {cls is CIRISRuntime}")

    except Exception as e:
        print(f"[DIAGNOSTIC] Error during diagnosis: {e}")
        import traceback

        traceback.print_exc()

    print("=" * 60 + "\n")


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
    print(f"[allow_runtime_creation] Starting fixture")
    print(f"[allow_runtime_creation] CIRIS_IMPORT_MODE before: {os.environ.get('CIRIS_IMPORT_MODE', 'NOT SET')}")
    print(f"[allow_runtime_creation] CIRIS_MOCK_LLM before: {os.environ.get('CIRIS_MOCK_LLM', 'NOT SET')}")

    original_import = os.environ.get("CIRIS_IMPORT_MODE")
    original_mock = os.environ.get("CIRIS_MOCK_LLM")

    os.environ["CIRIS_IMPORT_MODE"] = "false"
    os.environ["CIRIS_MOCK_LLM"] = "true"  # Always use mock LLM in tests
    os.environ["OPENAI_API_KEY"] = "test-key"

    print(f"[allow_runtime_creation] CIRIS_IMPORT_MODE after: {os.environ.get('CIRIS_IMPORT_MODE')}")
    print(f"[allow_runtime_creation] CIRIS_MOCK_LLM after: {os.environ.get('CIRIS_MOCK_LLM')}")
    print(f"[allow_runtime_creation] CIRISRuntime is: {CIRISRuntime}")
    print(f"[allow_runtime_creation] CIRISRuntime type: {type(CIRISRuntime)}")

    yield

    print(f"[allow_runtime_creation] Cleaning up fixture")
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
        print(f"[test_create_runtime_with_config] Starting test")
        print(f"[test_create_runtime_with_config] CIRISRuntime is: {CIRISRuntime}")
        print(f"[test_create_runtime_with_config] CIRISRuntime type: {type(CIRISRuntime)}")
        print(f"[test_create_runtime_with_config] CIRISRuntime module: {CIRISRuntime.__module__}")
        print(f"[test_create_runtime_with_config] CIRISRuntime __new__: {CIRISRuntime.__new__}")
        print(f"[test_create_runtime_with_config] CIRISRuntime __init__: {CIRISRuntime.__init__}")
        print(
            f"[test_create_runtime_with_config] CIRISRuntime __dict__ keys: {list(CIRISRuntime.__dict__.keys())[:10]}"
        )  # First 10 keys
        print(f"[test_create_runtime_with_config] Is CIRISRuntime a class? {isinstance(CIRISRuntime, type)}")

        # Check if CIRISRuntime has been replaced or mocked
        print(f"[test_create_runtime_with_config] Checking for mock attributes...")
        if hasattr(CIRISRuntime, "_mock_name"):
            print(f"[test_create_runtime_with_config] WARNING: CIRISRuntime has _mock_name: {CIRISRuntime._mock_name}")
        if hasattr(CIRISRuntime, "_spec_class"):
            print(
                f"[test_create_runtime_with_config] WARNING: CIRISRuntime has _spec_class: {CIRISRuntime._spec_class}"
            )

        print(f"[test_create_runtime_with_config] Environment check:")
        print(f"  CIRIS_IMPORT_MODE: {os.environ.get('CIRIS_IMPORT_MODE')}")
        print(f"  CIRIS_MOCK_LLM: {os.environ.get('CIRIS_MOCK_LLM')}")

        # Try to create runtime with extensive error catching
        print(f"[test_create_runtime_with_config] About to instantiate CIRISRuntime...")
        try:
            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=essential_config,
                modules=["mock_llm"],
            )
            print(f"[test_create_runtime_with_config] Successfully created runtime: {runtime}")
            print(f"[test_create_runtime_with_config] Runtime type: {type(runtime)}")
        except TypeError as e:
            print(f"[test_create_runtime_with_config] TypeError during instantiation: {e}")
            print(f"[test_create_runtime_with_config] TypeError args: {e.args}")
            print(f"[test_create_runtime_with_config] Attempting to call CIRISRuntime.__new__ directly...")
            try:
                # Try calling __new__ directly to see what happens
                instance = CIRISRuntime.__new__(CIRISRuntime)
                print(f"[test_create_runtime_with_config] __new__ succeeded: {instance}")
            except Exception as new_error:
                print(f"[test_create_runtime_with_config] __new__ failed: {new_error}")

            # Re-raise to fail the test
            raise
        except Exception as e:
            print(f"[test_create_runtime_with_config] Unexpected error: {e}")
            print(f"[test_create_runtime_with_config] Error type: {type(e)}")
            import traceback

            traceback.print_exc()
            raise

        assert runtime.essential_config == essential_config
        assert runtime.startup_channel_id == ""
        assert len(runtime.adapters) == 1
        assert runtime._initialized is False

        print(f"[test_create_runtime_with_config] Test completed successfully")

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
        print("[test_initialize_runtime_mock_llm] Creating runtime...")
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=30,  # Increased timeout for CI
        )
        print(f"[test_initialize_runtime_mock_llm] Runtime created: {runtime}")

        # Initialize runtime
        print("[test_initialize_runtime_mock_llm] Starting initialization...")
        await runtime.initialize()
        print("[test_initialize_runtime_mock_llm] Initialization complete")

        # Check that runtime was initialized
        print(f"[test_initialize_runtime_mock_llm] _initialized: {runtime._initialized}")
        print(f"[test_initialize_runtime_mock_llm] agent_processor: {runtime.agent_processor}")
        print(f"[test_initialize_runtime_mock_llm] service_initializer: {runtime.service_initializer}")

        assert runtime._initialized is True
        assert runtime.agent_processor is not None, "agent_processor is None after initialization"
        assert runtime.service_initializer is not None, "service_initializer is None after initialization"

        # Clean up
        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_properties_after_init(self, essential_config, allow_runtime_creation):
        """Test accessing services after initialization."""
        print("[test_runtime_properties_after_init] Creating runtime...")
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=30,  # Increased timeout for CI
        )
        print(f"[test_runtime_properties_after_init] Runtime created: {runtime}")

        print("[test_runtime_properties_after_init] Starting initialization...")
        await runtime.initialize()
        print("[test_runtime_properties_after_init] Initialization complete")

        # Check service properties are accessible
        print(f"[test_runtime_properties_after_init] service_registry: {runtime.service_registry}")
        print(f"[test_runtime_properties_after_init] memory_service: {runtime.memory_service}")
        print(f"[test_runtime_properties_after_init] telemetry_service: {runtime.telemetry_service}")

        assert runtime.service_registry is not None, "service_registry is None after initialization"
        assert runtime.memory_service is not None, "memory_service is None after initialization"
        assert runtime.telemetry_service is not None, "telemetry_service is None after initialization"

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
        print("[test_service_properties] Creating runtime...")
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=30,  # Increased timeout for CI
        )
        print(f"[test_service_properties] Runtime created: {runtime}")

        print("[test_service_properties] Starting initialization...")
        await runtime.initialize()
        print("[test_service_properties] Initialization complete")

        # Check all service properties
        print(f"[test_service_properties] memory_service: {runtime.memory_service}")
        print(f"[test_service_properties] service_registry: {runtime.service_registry}")
        print(f"[test_service_properties] bus_manager: {runtime.bus_manager}")
        print(f"[test_service_properties] resource_monitor: {runtime.resource_monitor}")
        print(f"[test_service_properties] secrets_service: {runtime.secrets_service}")
        print(f"[test_service_properties] telemetry_service: {runtime.telemetry_service}")
        print(f"[test_service_properties] llm_service: {runtime.llm_service}")

        assert runtime.memory_service is not None, "memory_service is None after initialization"
        assert runtime.service_registry is not None, "service_registry is None after initialization"
        assert runtime.bus_manager is not None, "bus_manager is None after initialization"
        assert runtime.resource_monitor is not None, "resource_monitor is None after initialization"
        assert runtime.secrets_service is not None, "secrets_service is None after initialization"
        assert runtime.telemetry_service is not None, "telemetry_service is None after initialization"
        assert runtime.llm_service is not None, "llm_service is None after initialization"

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
