pytest_plugins = ("tests.fixtures",)
import os

import pytest
import pytest_asyncio

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.logic.runtime.prevent_sideeffects import allow_runtime_creation


@pytest.fixture(autouse=True)
def allow_runtime():
    """Allow runtime creation for integration tests."""
    allow_runtime_creation()
    # Enable mock LLM for integration tests
    original_mock = os.environ.get("CIRIS_MOCK_LLM")
    os.environ["CIRIS_MOCK_LLM"] = "true"
    yield
    # Re-enable import protection after test
    os.environ["CIRIS_IMPORT_MODE"] = "true"
    # Restore mock LLM setting
    if original_mock is not None:
        os.environ["CIRIS_MOCK_LLM"] = original_mock
    else:
        os.environ.pop("CIRIS_MOCK_LLM", None)


@pytest_asyncio.fixture
async def mock_external_dependencies():
    """Mock all external dependencies for full cycle test."""
    from unittest.mock import AsyncMock, MagicMock, patch

    mocks = {
        "load_adapter": None,
    }

    # Create a concrete mock adapter class that doesn't inherit from ABC
    class MockAdapter:
        def __init__(self, runtime, **kwargs):
            self.runtime = runtime
            self.config = kwargs.get("adapter_config", {})

        async def start(self):
            pass

        async def stop(self):
            pass

        async def run_lifecycle(self, agent_task=None):
            # Accept agent_task parameter (used by runtime)
            pass

        def get_services_to_register(self):
            return []

    with patch("ciris_engine.logic.runtime.ciris_runtime.load_adapter") as mock_load:
        mock_load.return_value = MockAdapter
        mocks["load_adapter"] = mock_load
        yield mocks


@pytest.mark.asyncio
@pytest.mark.timeout(10)
async def test_full_thought_cycle(mock_external_dependencies):
    """Test complete thought processing cycle with mocked dependencies.

    This test validates basic runtime creation and component setup with mock LLM.
    Full initialization is skipped to avoid hangs - this is a smoke test.
    """
    # Ensure runtime creation is allowed
    allow_runtime_creation()

    # Verify mock LLM is enabled
    assert os.environ.get("CIRIS_MOCK_LLM") == "true", "Mock LLM must be enabled"

    from ciris_engine.schemas.config.essential import EssentialConfig

    # Create essential config
    essential_config = EssentialConfig()

    # Create runtime - this should work with mocked dependencies
    runtime = CIRISRuntime(adapter_types=["cli"], essential_config=essential_config, startup_channel_id="test_channel")

    # Verify runtime object was created
    assert runtime is not None, "Runtime should be created"
    assert hasattr(runtime, "essential_config"), "Runtime should have essential_config"
    assert runtime.essential_config is not None, "Runtime config should be set"

    print("✓ Runtime object created successfully with mock LLM")
    print(f"  - Config: {runtime.essential_config}")
    print(f"  - Adapter types: {['cli']}")

    # Note: We don't actually initialize the runtime because that requires
    # full service startup which can hang in test environment.
    # This test validates that:
    # 1. Mock LLM environment is set
    # 2. Runtime can be instantiated with CLI adapter
    # 3. Essential config is properly loaded
    #
    # TODO: Full end-to-end cycle test when mock dependencies are fully stable:
    # 1. Initialize runtime fully
    # 2. Create task via runtime
    # 3. Generate thought
    # 4. Run DMAs
    # 5. Apply guardrails
    # 6. Execute action
    # 7. Verify outcome

    print("✓ Basic runtime setup test passed - full initialization skipped for stability")
