"""Runtime fixtures for agent processor testing."""

import asyncio
import logging
import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime

logger = logging.getLogger(__name__)


@pytest_asyncio.fixture
async def real_runtime_with_mock():
    """Provide a real CIRISRuntime instance with environment properly configured.

    This fixture is for tests that need an actual runtime instance, not a mock.
    It handles the CIRIS_IMPORT_MODE environment variable to allow runtime creation.
    """
    # Save original environment state
    original_import = os.environ.get("CIRIS_IMPORT_MODE")
    original_mock = os.environ.get("CIRIS_MOCK_LLM")

    # Allow runtime creation and use mock LLM
    os.environ["CIRIS_IMPORT_MODE"] = "false"
    os.environ["CIRIS_MOCK_LLM"] = "true"

    try:
        # Create runtime with mock LLM module
        runtime = CIRISRuntime(
            adapter_types=["cli"],
            modules=["mock_llm"],
        )
        yield runtime
    finally:
        # Restore original environment
        if original_import is not None:
            os.environ["CIRIS_IMPORT_MODE"] = original_import
        else:
            os.environ.pop("CIRIS_IMPORT_MODE", None)

        if original_mock is not None:
            os.environ["CIRIS_MOCK_LLM"] = original_mock
        else:
            os.environ.pop("CIRIS_MOCK_LLM", None)


@pytest_asyncio.fixture
async def runtime_with_mocked_agent_processor(real_runtime_with_mock):
    """Provide a runtime with a fully mocked agent processor for testing."""
    runtime = real_runtime_with_mock

    # Mock the agent processor
    mock_agent_processor = AsyncMock()
    mock_agent_processor.start_processing = AsyncMock()
    runtime.agent_processor = mock_agent_processor

    # Mock critical services wait
    runtime._wait_for_critical_services = AsyncMock()

    return runtime


@pytest_asyncio.fixture
async def runtime_with_mocked_bus_manager(runtime_with_mocked_agent_processor):
    """Provide a runtime with mocked bus manager for agent processor testing."""
    runtime = runtime_with_mocked_agent_processor

    # Mock the service initializer and bus manager
    mock_service_initializer = MagicMock()
    mock_bus_manager = MagicMock()
    mock_bus_manager.start = AsyncMock()
    mock_service_initializer.bus_manager = mock_bus_manager
    runtime.service_initializer = mock_service_initializer

    return runtime


@pytest_asyncio.fixture
async def runtime_without_bus_manager(runtime_with_mocked_agent_processor):
    """Provide a runtime without bus manager for testing edge cases."""
    runtime = runtime_with_mocked_agent_processor

    # Mock service initializer with no bus manager
    mock_service_initializer = MagicMock()
    mock_service_initializer.bus_manager = None
    runtime.service_initializer = mock_service_initializer

    return runtime


@pytest_asyncio.fixture
async def runtime_with_adapter_mocks(real_runtime_with_mock):
    """Provide a runtime with mocked adapters for initialization testing."""
    runtime = real_runtime_with_mock

    # Mock adapters
    mock_adapter = MagicMock()
    mock_adapter.__class__.__name__ = "TestAdapter"
    mock_adapter.run_lifecycle = AsyncMock()
    runtime.adapters = [mock_adapter]

    # Mock service registry through service_initializer
    mock_service_initializer = MagicMock()
    mock_service_registry = MagicMock()
    mock_service_registry.get_service = AsyncMock(return_value=MagicMock())
    mock_service_initializer.service_registry = mock_service_registry
    runtime.service_initializer = mock_service_initializer

    # Mock register adapter services
    runtime._register_adapter_services = AsyncMock()
    runtime._wait_for_critical_services = AsyncMock()

    return runtime


@pytest_asyncio.fixture
async def runtime_with_full_initialization_mocks(real_runtime_with_mock):
    """Provide a runtime with full initialization chain mocked for integration testing."""
    runtime = real_runtime_with_mock

    # Mock the agent processor
    mock_agent_processor = AsyncMock()
    mock_agent_processor.start_processing = AsyncMock()
    runtime.agent_processor = mock_agent_processor

    # Mock adapters with lifecycle support
    mock_adapter = MagicMock()
    mock_adapter.__class__.__name__ = "TestAdapter"
    mock_adapter.run_lifecycle = AsyncMock()
    runtime.adapters = [mock_adapter]

    # Mock service initializer with all required components
    mock_service_initializer = MagicMock()
    mock_service_registry = MagicMock()
    mock_service_registry.get_service = AsyncMock(return_value=MagicMock())
    mock_service_initializer.service_registry = mock_service_registry
    mock_service_initializer.bus_manager = None  # Default to no bus manager
    runtime.service_initializer = mock_service_initializer

    # Mock critical methods used during initialization
    runtime._register_adapter_services = AsyncMock()
    runtime._wait_for_critical_services = AsyncMock()

    # Store adapter tasks for testing
    runtime._adapter_tasks = []

    return runtime


@pytest.fixture
def runtime_initialization_patcher():
    """Provide a context manager for patching runtime initialization methods."""

    class InitializationPatcher:
        def __init__(self):
            self.patches = {}
            self.mocks = {}

        def patch_method(self, runtime, method_name, return_value=None, side_effect=None):
            """Patch a method on the runtime instance."""
            if hasattr(runtime, method_name):
                original_method = getattr(runtime, method_name)
                mock_method = AsyncMock(return_value=return_value, side_effect=side_effect)
                setattr(runtime, method_name, mock_method)
                self.patches[method_name] = (runtime, method_name, original_method)
                self.mocks[method_name] = mock_method
                return mock_method
            else:
                # Create a new mock method
                mock_method = AsyncMock(return_value=return_value, side_effect=side_effect)
                setattr(runtime, method_name, mock_method)
                self.patches[method_name] = (runtime, method_name, None)
                self.mocks[method_name] = mock_method
                return mock_method

        def patch_initialize_adapters(self, runtime):
            """Patch the adapter initialization flow to track task creation."""
            created_tasks = []

            async def mock_initialize_adapters():
                # Simulate the real logic from the production code
                logger.info("Creating agent processor task...")
                agent_task = asyncio.create_task(
                    runtime._create_agent_processor_when_ready(), name="AgentProcessorTask"
                )
                created_tasks.append(("AgentProcessorTask", agent_task))

                # Start adapter lifecycles with the real agent task
                runtime._adapter_tasks = []
                for adapter in runtime.adapters:
                    adapter_name = adapter.__class__.__name__
                    if hasattr(adapter, "run_lifecycle"):
                        lifecycle_task = asyncio.create_task(
                            adapter.run_lifecycle(agent_task), name=f"{adapter_name}LifecycleTask"
                        )
                        runtime._adapter_tasks.append(lifecycle_task)
                        created_tasks.append((f"{adapter_name}LifecycleTask", lifecycle_task))

                # Mock the service registration and waiting
                await runtime._register_adapter_services()
                await runtime._wait_for_critical_services(timeout=5.0)

            mock_method = self.patch_method(runtime, "_initialize_adapters", side_effect=mock_initialize_adapters)
            mock_method.created_tasks = created_tasks
            return mock_method

        def get_mock(self, method_name):
            """Get a mock by method name."""
            return self.mocks.get(method_name)

        def restore_all(self):
            """Restore all patched methods."""
            for method_name, (runtime, attr_name, original) in self.patches.items():
                if original is not None:
                    setattr(runtime, attr_name, original)
                else:
                    delattr(runtime, attr_name)
            self.patches.clear()
            self.mocks.clear()

    return InitializationPatcher()


@pytest_asyncio.fixture
async def runtime_with_integration_test_setup(runtime_with_full_initialization_mocks, runtime_initialization_patcher):
    """Provide a runtime fully set up for integration testing of initialization flows."""
    runtime = runtime_with_full_initialization_mocks
    patcher = runtime_initialization_patcher

    # Set up the initialization adapter mocking
    mock_init_adapters = patcher.patch_initialize_adapters(runtime)

    yield runtime, patcher, mock_init_adapters

    # Cleanup
    patcher.restore_all()


@pytest.fixture
def mock_agent_task():
    """Provide a mock agent task for run() method testing."""
    mock_task = MagicMock()
    mock_task.get_name.return_value = "AgentProcessorTask"
    mock_task.done.return_value = False
    return mock_task


@pytest.fixture
def fast_mock_runtime():
    """Provide a fast, lightweight mock runtime for logging tests.

    This fixture avoids real file system operations and initialization
    for maximum test speed while providing configurable behavior.
    """
    from tests.fixtures.mocks import MockRuntime

    runtime = MockRuntime(include_logging_mocks=True, include_time_service=True)
    return runtime


@pytest.fixture
def mock_essential_config(tmp_path):
    """Provide a minimal EssentialConfig using tmp_path for fast testing."""
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

    # Use tmp_path for all database files to avoid filesystem conflicts
    return EssentialConfig(
        database=DatabaseConfig(
            main_db=tmp_path / "test.db",
            secrets_db=tmp_path / "secrets.db",
            audit_db=tmp_path / "audit.db",
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
            secrets_key_path=tmp_path / "secrets_keys",
            audit_key_path=tmp_path / "audit_keys",
            enable_signed_audit=False,
            max_thought_depth=5,
        ),
        limits=OperationalLimitsConfig(
            max_active_tasks=5,
            max_active_thoughts=10,
            round_delay_seconds=0.01,  # Fast for testing
            mock_llm_round_delay=0.001,  # Very fast for testing
            dma_retry_limit=1,  # Reduce retries for speed
            dma_timeout_seconds=1.0,  # Fast timeout
            conscience_retry_limit=1,
        ),
        telemetry=TelemetryConfig(
            enabled=False,  # Disable for speed
            export_interval_seconds=60,
            retention_hours=1,
        ),
        workflow=WorkflowConfig(
            max_rounds=2,  # Reduce for speed
            round_timeout_seconds=5.0,  # Fast timeout
            enable_auto_defer=True,
        ),
        graph=GraphConfig(
            tsdb_profound_target_mb_per_day=1.0,  # Small for testing
            tsdb_raw_retention_hours=1,
            consolidation_timezone="UTC",
        ),
        log_level="DEBUG",
        debug_mode=True,
        template_directory=tmp_path / "templates",
        default_template="test",
    )


@pytest.fixture
def mock_logging_components():
    """Provide mocks for all logging-related components."""

    class LoggingMocks:
        def __init__(self):
            self.setup_basic_logging = MagicMock(return_value=None)
            self.time_service = MagicMock()
            self.time_service.now.return_value = MagicMock()
            self.time_service.format_timestamp.return_value = "20250927_143000"

            # Mock ServiceRegistry for TimeService lookup
            self.service_registry = MagicMock()
            self.service_registry.get_service.return_value = self.time_service

            # Mock file operations
            self.log_files_created = []
            self.symlinks_created = []

        def configure_success(self):
            """Configure mocks for successful logging setup."""
            self.setup_basic_logging.return_value = None
            self.setup_basic_logging.side_effect = None

        def configure_failure(self, error_message="Mock setup failed"):
            """Configure mocks for failed logging setup."""
            self.setup_basic_logging.side_effect = Exception(error_message)

        def configure_time_service_failure(self):
            """Configure TimeService to be unavailable."""
            self.service_registry.get_service.return_value = None

    return LoggingMocks()
