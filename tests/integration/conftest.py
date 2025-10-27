"""Conftest for integration tests - imports runtime fixtures."""

# Import runtime fixtures directly to make them available to integration tests
from tests.fixtures.runtime import (  # noqa: F401
    real_runtime_with_mock,
    runtime_with_adapter_mocks,
    runtime_with_full_initialization_mocks,
    runtime_with_mocked_agent_processor,
    runtime_with_mocked_bus_manager,
    runtime_without_bus_manager,
)
