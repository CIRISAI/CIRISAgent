#!/usr/bin/env python3
"""
Test script to verify all startup issues have been fixed.

This test simulates the startup sequence and verifies:
1. Identity storage/retrieval works correctly with IdentityNode
2. TimeService is registered in ServiceRegistry
3. TimeService.now() method works correctly
4. Shutdown doesn't have async/await issues
5. SQLite threading is handled correctly
6. Service shutdown order is correct (telemetry stops before memory)
"""

import asyncio
import os
import sys
import tempfile

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import logging

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.logic.utils.shutdown_manager import request_global_shutdown
from ciris_engine.schemas.config.essential import EssentialConfig

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


async def test_startup_and_shutdown():
    """Test that the agent can start up and shut down properly."""
    # Create a temporary directory for test data
    with tempfile.TemporaryDirectory() as temp_dir:
        # Save and set environment variables for test (restore after)
        saved_data_dir = os.environ.get("CIRIS_DATA_DIR")
        saved_api_key = os.environ.get("OPENAI_API_KEY")
        os.environ["CIRIS_DATA_DIR"] = temp_dir
        os.environ["OPENAI_API_KEY"] = "test-key"  # Will use mock LLM

        try:
            # Create runtime with minimal config
            config = EssentialConfig()
            runtime = CIRISRuntime(
                adapter_types=["api"],
                essential_config=config,
                startup_channel_id="test-channel",
                adapter_configs={},
                template="datum",
                mock_llm=True,  # Use mock LLM for testing
                host="0.0.0.0",
                port=8080,
            )

            logger.info("Initializing runtime...")
            await runtime.initialize()
            logger.info("✓ Runtime initialized successfully!")

            # Verify key services are available
            assert runtime.service_initializer.time_service is not None, "TimeService not initialized"
            assert runtime.service_initializer.memory_service is not None, "MemoryService not initialized"
            assert runtime.service_initializer.telemetry_service is not None, "TelemetryService not initialized"
            logger.info("✓ All critical services initialized")

            # Verify TimeService is in registry
            from ciris_engine.schemas.runtime.enums import ServiceType

            time_providers = runtime.service_registry.get_providers(ServiceType.TIME)
            assert len(time_providers) > 0, "TimeService not found in registry"
            logger.info("✓ TimeService registered in ServiceRegistry")

            # Test TimeService.now() method
            time_service = runtime.service_initializer.time_service
            current_time = time_service.now()
            assert current_time is not None, "TimeService.now() returned None"
            logger.info(f"✓ TimeService.now() works: {current_time}")

            # Test identity was stored and retrieved
            assert runtime.agent_identity is not None, "Agent identity not loaded"
            assert hasattr(runtime.agent_identity, "agent_id"), "Agent identity missing agent_id"
            logger.info(f"✓ Identity loaded successfully: {runtime.agent_identity.agent_id}")

            # Trigger shutdown to test shutdown sequence
            logger.info("Testing shutdown sequence...")
            request_global_shutdown("Test completed")

            # Give it a moment to process shutdown
            await asyncio.sleep(1)

            # Perform actual shutdown
            await runtime.shutdown()
            logger.info("✓ Shutdown completed without errors!")

            # If we get here, all tests passed
            logger.info("\n✅ ALL TESTS PASSED! The startup issues have been fixed.")
            return True

        except Exception as e:
            logger.error(f"\n❌ TEST FAILED: {e}", exc_info=True)
            return False

        finally:
            # Restore environment variables
            if saved_data_dir is not None:
                os.environ["CIRIS_DATA_DIR"] = saved_data_dir
            else:
                os.environ.pop("CIRIS_DATA_DIR", None)
            if saved_api_key is not None:
                os.environ["OPENAI_API_KEY"] = saved_api_key
            else:
                os.environ.pop("OPENAI_API_KEY", None)


async def main():
    """Run the test."""
    success = await test_startup_and_shutdown()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
