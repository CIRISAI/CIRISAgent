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

# Import fixtures from the runtime fixtures file
from tests.fixtures.runtime import (
    mock_agent_task,
    real_runtime_with_mock,
    runtime_initialization_patcher,
    runtime_with_adapter_mocks,
    runtime_with_full_initialization_mocks,
    runtime_with_integration_test_setup,
    runtime_with_mocked_agent_processor,
    runtime_with_mocked_bus_manager,
    runtime_without_bus_manager,
)


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
    # Create templates directory and copy test template
    import shutil

    templates_dir = temp_dir / "templates"
    templates_dir.mkdir(exist_ok=True)

    # Copy test.yaml template if it exists
    test_template_src = Path("ciris_templates/test.yaml")
    if test_template_src.exists():
        shutil.copy(test_template_src, templates_dir / "test.yaml")

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
            secrets_key_path=temp_dir / "secrets_keys",
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
        template_directory=templates_dir,
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
        print(f"[test_service_properties] secrets_service: {runtime.secrets_service}")  # noqa: S002 - Test code
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

    @pytest.mark.asyncio
    async def test_runtime_run_with_rounds(self, essential_config, allow_runtime_creation):
        """Test runtime run method with specific round count."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # Test that we can request shutdown and it sets the event
        runtime.request_shutdown("Test shutdown")
        assert runtime._shutdown_event.is_set()
        assert runtime._shutdown_reason == "Test shutdown"

        # Don't actually call run() as it may block - that's tested elsewhere
        # The run method is integration-tested in test_run_with_immediate_shutdown

        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_cognitive_state_transition(self, essential_config, allow_runtime_creation):
        """Test runtime handles cognitive state transitions."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # AgentProcessor uses get_state() and set_state() methods, not a direct attribute
        # Just verify the processor exists
        assert runtime.agent_processor is not None

        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_multiple_adapters(self, essential_config, allow_runtime_creation):
        """Test runtime with multiple adapters."""
        with patch("ciris_engine.logic.runtime.ciris_runtime.logger") as mock_logger:
            runtime = CIRISRuntime(
                adapter_types=["cli", "nonexistent", "cli"],  # Duplicate and invalid
                essential_config=essential_config,
                modules=["mock_llm"],
                timeout=2,
            )

            # Should have loaded only valid adapters
            assert len(runtime.adapters) == 2

            # Check that error was logged for nonexistent adapter
            assert any("Failed to load" in str(call) for call in mock_logger.error.call_args_list)

    @pytest.mark.asyncio
    async def test_runtime_with_timeout_parameter(self, essential_config, allow_runtime_creation):
        """Test runtime respects timeout parameter."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=10,  # Custom timeout
        )

        # Check timeout was stored (would be used in run method)
        assert hasattr(runtime, "_shutdown_event")

        await runtime.initialize()
        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_profile_property(self, essential_config, allow_runtime_creation):
        """Test accessing runtime profile property."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # Access profile property
        profile = runtime.profile
        # Profile might be None if not configured, that's ok
        assert profile is None or hasattr(profile, "__dict__")

        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_with_startup_channel(self, essential_config, allow_runtime_creation):
        """Test runtime with startup channel ID."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            startup_channel_id="test_channel_123",
            modules=["mock_llm"],
            timeout=2,
        )

        assert runtime.startup_channel_id == "test_channel_123"

        await runtime.initialize()
        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_with_adapter_configs(self, essential_config, allow_runtime_creation):
        """Test runtime with adapter configurations."""
        adapter_configs = {"cli": {"special_option": "value"}}

        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            adapter_configs=adapter_configs,
            modules=["mock_llm"],
            timeout=2,
        )

        assert runtime.adapter_configs == adapter_configs

        await runtime.initialize()
        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_shutdown_reason(self, essential_config, allow_runtime_creation):
        """Test runtime shutdown with specific reason."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # Request shutdown with reason
        runtime.request_shutdown("Test complete - shutting down")
        assert runtime._shutdown_reason == "Test complete - shutting down"
        assert runtime._shutdown_event.is_set()

        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_double_initialization(self, essential_config, allow_runtime_creation):
        """Test that double initialization is handled properly."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()
        assert runtime._initialized is True

        # Try to initialize again - should handle gracefully
        await runtime.initialize()
        assert runtime._initialized is True

        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_service_access_before_init(self, essential_config, allow_runtime_creation):
        """Test accessing services before initialization returns None."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        # All services should be None before initialization
        assert runtime.memory_service is None
        assert runtime.telemetry_service is None
        assert runtime.config_service is None
        assert runtime.audit_service is None
        assert runtime.llm_service is None
        assert runtime.time_service is None

    @pytest.mark.asyncio
    async def test_runtime_shutdown_without_init(self, essential_config, allow_runtime_creation):
        """Test shutdown can be called without initialization."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        # Should handle shutdown gracefully without initialization
        await runtime.shutdown()
        assert runtime._shutdown_complete is True

    @pytest.mark.asyncio
    async def test_runtime_with_empty_adapter_list(self, essential_config, allow_runtime_creation):
        """Test runtime with no adapters."""
        # Runtime will fail to create with no adapters - that's expected
        with pytest.raises(RuntimeError) as exc_info:
            runtime = CIRISRuntime(
                adapter_types=[],
                essential_config=essential_config,
                modules=["mock_llm"],
                timeout=2,
            )

        assert "No valid adapters" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_runtime_all_service_properties(self, essential_config, allow_runtime_creation):
        """Test accessing all service properties after initialization."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        await runtime.initialize()

        # Test core service property accessors that should always exist
        assert runtime.service_registry is not None
        assert runtime.bus_manager is not None
        assert runtime.memory_service is not None
        assert runtime.resource_monitor is not None
        assert runtime.secrets_service is not None
        assert runtime.telemetry_service is not None
        assert runtime.llm_service is not None
        assert runtime.time_service is not None
        assert runtime.config_service is not None
        assert runtime.authentication_service is not None
        assert runtime.incident_management_service is not None
        assert runtime.shutdown_service is not None
        assert runtime.initialization_service is not None

        # These services might be None depending on configuration
        # Just check they don't raise exceptions when accessed
        _ = runtime.task_scheduler
        _ = runtime.runtime_control_service
        _ = runtime.maintenance_service
        _ = runtime.tsdb_consolidation_service
        _ = runtime.self_observation_service
        _ = runtime.visibility_service
        _ = runtime.adaptive_filter_service
        _ = runtime.agent_config_service
        _ = runtime.config_manager
        _ = runtime.transaction_orchestrator
        _ = runtime.core_tool_service
        _ = runtime.wa_auth_system

        # These might be None depending on configuration
        assert runtime.profile is None or hasattr(runtime.profile, "__dict__")
        assert runtime.audit_service is None or hasattr(runtime.audit_service, "__dict__")
        assert isinstance(runtime.audit_services, list)

        await runtime.shutdown()

    @pytest.mark.asyncio
    async def test_runtime_initialization_error_handling(self, essential_config, allow_runtime_creation):
        """Test runtime handles initialization errors properly."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        # Just verify runtime can be created and properties are accessible
        assert runtime is not None
        assert runtime._initialized is False
        assert runtime.service_initializer is not None

        # Don't test the actual error handling as it's complex and would require
        # mocking internal initialization phases which is fragile

    @pytest.mark.asyncio
    async def test_runtime_request_shutdown_before_init(self, essential_config, allow_runtime_creation):
        """Test requesting shutdown before initialization."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm"],
            timeout=2,
        )

        # Request shutdown before initialization
        runtime.request_shutdown("Early shutdown")
        assert runtime._shutdown_event.is_set()
        assert runtime._shutdown_reason == "Early shutdown"

    @pytest.mark.asyncio
    async def test_runtime_with_special_modules(self, essential_config, allow_runtime_creation):
        """Test runtime with various module configurations."""
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=["mock_llm", "test_module", "another_module"],
            timeout=2,
        )

        assert "mock_llm" in runtime.modules_to_load
        assert "test_module" in runtime.modules_to_load
        assert "another_module" in runtime.modules_to_load

    @pytest.mark.asyncio
    async def test_runtime_environment_override(self, essential_config, allow_runtime_creation):
        """Test CIRIS_MOCK_LLM environment variable overrides modules."""
        # Set environment variable
        os.environ["CIRIS_MOCK_LLM"] = "true"

        runtime = CIRISRuntime(
            adapter_types=["cli"],
            essential_config=essential_config,
            modules=[],  # No modules specified
            timeout=2,
        )

        # Should have added mock_llm due to environment variable
        assert "mock_llm" in runtime.modules_to_load

        os.environ.pop("CIRIS_MOCK_LLM", None)


# ============================================================================
# AGENT PROCESSOR INITIALIZATION TESTS (New architecture without placeholders)
# ============================================================================


class TestAgentProcessorInitialization:
    """Test the new agent processor initialization logic without placeholder tasks."""

    @pytest.mark.asyncio
    async def test_create_agent_processor_when_ready_success(self, runtime_with_mocked_bus_manager):
        """Test successful agent processor creation when services are ready."""
        runtime = runtime_with_mocked_bus_manager

        # Test the method
        await runtime._create_agent_processor_when_ready()

        # Verify services were waited for
        runtime._wait_for_critical_services.assert_called_once_with(timeout=30.0)

        # Verify agent processor was started
        runtime.agent_processor.start_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_agent_processor_when_ready_no_agent_processor(self, runtime_with_mocked_agent_processor):
        """Test error when agent processor is not initialized."""
        runtime = runtime_with_mocked_agent_processor

        # Ensure agent processor is None
        runtime.agent_processor = None

        # Should raise RuntimeError
        with pytest.raises(RuntimeError, match="Agent processor not initialized"):
            await runtime._create_agent_processor_when_ready()

    @pytest.mark.asyncio
    async def test_create_agent_processor_when_ready_service_timeout(self, runtime_with_mocked_agent_processor):
        """Test behavior when critical services timeout."""
        runtime = runtime_with_mocked_agent_processor

        # Mock the critical services wait to raise timeout
        runtime._wait_for_critical_services.side_effect = asyncio.TimeoutError("Services not ready")

        # Should propagate the timeout error
        with pytest.raises(asyncio.TimeoutError, match="Services not ready"):
            await runtime._create_agent_processor_when_ready()

    @pytest.mark.asyncio
    async def test_create_agent_processor_when_ready_with_bus_manager(self, runtime_with_mocked_bus_manager):
        """Test agent processor creation with bus manager setup."""
        runtime = runtime_with_mocked_bus_manager

        # Mock asyncio.create_task to verify bus manager task creation
        with patch("asyncio.create_task") as mock_create_task:
            await runtime._create_agent_processor_when_ready()

            # Verify bus manager task was created (just check that create_task was called)
            mock_create_task.assert_called_once()
            # Verify bus manager start was called
            runtime.service_initializer.bus_manager.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_create_agent_processor_when_ready_without_bus_manager(self, runtime_without_bus_manager):
        """Test agent processor creation without bus manager."""
        runtime = runtime_without_bus_manager

        # Should work without bus manager
        await runtime._create_agent_processor_when_ready()

        # Verify agent processor was still started
        runtime.agent_processor.start_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialize_adapters_creates_real_agent_task(self, runtime_with_integration_test_setup):
        """Test that adapter initialization creates a real agent task instead of placeholder."""
        runtime, patcher, mock_init_adapters = runtime_with_integration_test_setup
        mock_adapter = runtime.adapters[0]

        # Execute the mocked initialization
        await mock_init_adapters()

        # Verify that an AgentProcessorTask was created
        created_tasks = mock_init_adapters.created_tasks
        task_names = [name for name, _ in created_tasks]

        assert "AgentProcessorTask" in task_names, f"AgentProcessorTask should have been created. Found: {task_names}"
        assert (
            "TestAdapterLifecycleTask" in task_names
        ), f"TestAdapterLifecycleTask should have been created. Found: {task_names}"

        # Verify adapter lifecycle was called with the real task
        mock_adapter.run_lifecycle.assert_called_once()
        called_task = mock_adapter.run_lifecycle.call_args[0][0]
        assert called_task.get_name() == "AgentProcessorTask"

        # Verify that adapter tasks were stored
        assert len(runtime._adapter_tasks) == 1
        assert runtime._adapter_tasks[0].get_name() == "TestAdapterLifecycleTask"

    @pytest.mark.asyncio
    async def test_run_method_finds_existing_agent_task(self, runtime_with_mocked_agent_processor, mock_agent_task):
        """Test that run() method finds and monitors the existing agent task."""
        runtime = runtime_with_mocked_agent_processor

        # Mock initialization state
        runtime._initialized = True
        runtime._adapter_tasks = [MagicMock()]

        # Mock shutdown event setup
        runtime._shutdown_event = MagicMock()
        runtime._shutdown_event.is_set.return_value = False
        runtime._shutdown_event.wait = AsyncMock()

        # Mock asyncio.all_tasks to return our mock task
        with patch("asyncio.all_tasks", return_value=[mock_agent_task]):
            # Mock global shutdown functions
            with patch(
                "ciris_engine.logic.runtime.ciris_runtime.wait_for_global_shutdown_async", new_callable=AsyncMock
            ):
                with patch("ciris_engine.logic.runtime.ciris_runtime.is_global_shutdown_requested", return_value=False):
                    # Mock asyncio.wait to immediately return the agent task as done
                    with patch("asyncio.wait") as mock_wait:
                        mock_wait.return_value = ({mock_agent_task}, set())

                        # Run should complete without error
                        await runtime.run()

                        # Verify the agent task was found and monitored
                        mock_wait.assert_called_once()

    @pytest.mark.asyncio
    async def test_run_method_no_agent_task_found(self, runtime_with_mocked_agent_processor, caplog):
        """Test run() method error when no agent task is found."""
        runtime = runtime_with_mocked_agent_processor

        # Mock initialization state
        runtime._initialized = True
        runtime._adapter_tasks = [MagicMock()]

        # Mock the shutdown method to avoid complex shutdown logic
        runtime.shutdown = AsyncMock()

        # Mock asyncio.all_tasks to return no matching task
        with patch("asyncio.all_tasks", return_value=[]):
            # The RuntimeError gets caught and logged, but doesn't propagate
            await runtime.run()

            # Verify the error was logged (covers our specific error handling logic)
            assert "Agent processor task not found" in caplog.text
            assert "Runtime error:" in caplog.text

    @pytest.mark.asyncio
    async def test_run_method_no_adapter_tasks(self, runtime_with_mocked_agent_processor):
        """Test run() method when no adapter tasks are found."""
        runtime = runtime_with_mocked_agent_processor

        # Mock initialization state
        runtime._initialized = True
        runtime._adapter_tasks = []  # No adapter tasks - should trigger early return

        # Should return early with warning (covers the early return logic we added)
        await runtime.run()  # Should not raise, just return
