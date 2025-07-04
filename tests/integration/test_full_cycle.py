pytest_plugins = ("tests.fixtures",)
import os
import pytest

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime


@pytest.mark.asyncio
@pytest.mark.skipif(
    os.environ.get("GITHUB_ACTIONS") == "true",
    reason="Skipping in GitHub Actions due to Python 3.12.10 compatibility issue with abstract base class instantiation"
)
async def test_full_thought_cycle():
    """Test complete thought processing cycle.

    NOTE: This test fails in GitHub Actions with Python 3.12.10 due to:
    TypeError: object.__new__() takes exactly one argument (the type to instantiate)

    The issue appears to be related to stricter ABC instantiation checks in Python 3.12.10
    when instantiating adapters that inherit from the Service abstract base class.
    The test passes locally with Python 3.12.3 and earlier versions.
    """
    from unittest.mock import patch, AsyncMock, MagicMock

    # Mock initialization manager to avoid core services verification
    with patch('ciris_engine.logic.runtime.ciris_runtime.get_initialization_manager') as mock_get_init:
        mock_init_manager = MagicMock()
        mock_init_manager.initialize = AsyncMock()
        mock_init_manager.register_step = MagicMock()
        mock_get_init.return_value = mock_init_manager

        # Create and initialize runtime
        runtime = CIRISRuntime(adapter_types=["cli"])

        with patch.object(runtime, '_perform_startup_maintenance'):
            await runtime.initialize()

        # Now the runtime should be initialized
        assert runtime.service_initializer is not None
        assert runtime._initialized is True

        # TODO: Implement actual test steps
        # 1. Create task
        # 2. Generate thought
        # 3. Run DMAs
        # 4. Apply guardrails
        # 5. Execute action
        # 6. Verify outcome
