import os
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime


@pytest_asyncio.fixture
async def service_registry() -> Any:
    """Provide a configured service registry with mock services."""
    registry = ServiceRegistry()
    # Register mock services here when needed
    return registry


@pytest_asyncio.fixture
async def runtime():
    """Provide a CIRISRuntime instance with proper initialization."""
    runtime = CIRISRuntime(adapter_types=["cli"])
    # The runtime will initialize its own service registry during initialization
    # No need to set it externally - this violates encapsulation
    return runtime


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


@pytest.fixture(autouse=True)
def ensure_pydantic_models_rebuilt():
    """Ensure Pydantic models are properly rebuilt before each test.

    This prevents issues with forward references when tests run in different orders.
    """
    # Import and rebuild models
    try:
        # Models are now automatically rebuilt - no manual rebuild needed
        pass
    except ImportError:
        pass  # Schema module may not be imported yet

    yield

    # No cleanup needed - models will be rebuilt for next test


# ============================================================================
# AGENT PROCESSOR TESTING FIXTURES
# ============================================================================


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

    # Mock service registry
    runtime.service_registry = MagicMock()
    runtime.service_registry.get_service = AsyncMock(return_value=MagicMock())

    # Mock register adapter services
    runtime._register_adapter_services = AsyncMock()
    runtime._wait_for_critical_services = AsyncMock()

    return runtime


@pytest.fixture
def mock_agent_task():
    """Provide a mock agent task for run() method testing."""
    mock_task = MagicMock()
    mock_task.get_name.return_value = "AgentProcessorTask"
    mock_task.done.return_value = False
    return mock_task
