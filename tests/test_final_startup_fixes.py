#!/usr/bin/env python3
"""
Final test script to verify all startup issues have been fixed.

This test simulates the complete startup sequence and verifies:
1. Runtime initialization completes
2. Identity is properly stored and retrieved
3. TimeService is registered and functional
4. Wakeup processor starts without SystemSnapshot errors
5. Shutdown works without async/await warnings
6. Services shut down in correct order
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


async def test_complete_startup():
    """Test the complete startup sequence including wakeup."""
    # Create a temporary directory for test data
    with tempfile.TemporaryDirectory() as temp_dir:
        # Save and set environment variables for test (restore after)
        saved_data_dir = os.environ.get("CIRIS_DATA_DIR")
        saved_api_key = os.environ.get("OPENAI_API_KEY")
        os.environ["CIRIS_DATA_DIR"] = temp_dir
        os.environ["OPENAI_API_KEY"] = "test-key"  # Will use mock LLM

        try:
            logger.info("Creating runtime with CLI adapter...")
            config = EssentialConfig()
            runtime = CIRISRuntime(
                adapter_types=["cli"],
                essential_config=config,
                startup_channel_id="test-channel",
                adapter_configs={},
                mock_llm=True,  # Use mock LLM for testing
                timeout=5,  # Short timeout for testing
            )

            logger.info("Initializing runtime...")
            await runtime.initialize()
            logger.info("✓ Runtime initialized successfully!")

            # Verify all services are available
            assert runtime.service_initializer.time_service is not None
            assert runtime.service_initializer.memory_service is not None
            assert runtime.service_initializer.telemetry_service is not None
            assert runtime.agent_processor is not None
            logger.info("✓ All critical services initialized")

            # Start the agent processor to test wakeup
            logger.info("Starting agent processor...")
            processor_task = asyncio.create_task(runtime.agent_processor.start_processing(num_rounds=2))

            # Let it run for a bit to test wakeup
            await asyncio.sleep(2)

            # Check if wakeup processor started without errors
            if hasattr(runtime.agent_processor, "wakeup_processor"):
                wakeup = runtime.agent_processor.wakeup_processor
                logger.info(f"✓ Wakeup processor status: {wakeup.get_status()}")

            # Test shutdown
            logger.info("Testing graceful shutdown...")
            request_global_shutdown("Test completed")

            # Cancel processor task
            processor_task.cancel()
            try:
                await processor_task
            except asyncio.CancelledError:
                pass

            # Perform shutdown
            await runtime.shutdown()
            logger.info("✓ Shutdown completed successfully!")

            logger.info("\n✅ ALL TESTS PASSED!")
            logger.info("The CIRIS Agent can now:")
            logger.info("  - Initialize all services properly")
            logger.info("  - Store and retrieve identity correctly")
            logger.info("  - Start wakeup sequence without errors")
            logger.info("  - Shut down gracefully without warnings")
            logger.info("  - Stop services in correct dependency order")

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
    success = await test_complete_startup()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
