#!/usr/bin/env python3
"""Test stepping through pipeline using the SDK."""

import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from ciris_sdk.client import CIRISClient

async def test_stepping():
    """Test stepping through the pipeline using the SDK."""
    async with CIRISClient(base_url="http://localhost:8000") as client:
        # Login
        try:
            login_response = await client.auth.login("admin", "ciris_admin_password")
            # Fix: The SDK doesn't automatically set the token, we need to do it manually
            client._transport.set_api_key(login_response.access_token)
            print("✓ Logged in successfully")
        except Exception as e:
            print(f"✗ Login failed: {e}")
            return
        
        # Get current state before stepping
        try:
            state = await client.system.get_state()
            print(f"\n📊 State before step:")
            print(f"   Processor state: {state.processor_state}")
            print(f"   Queue depth: {state.queue_depth}")
            print(f"   Current step: {state.current_step}")
        except Exception as e:
            print(f"✗ Failed to get state: {e}")
        
        # Execute a step
        try:
            print(f"\n🔄 Executing step...")
            result = await client.system.single_step()
            print(f"✓ Step completed:")
            print(f"   Step Point: {result.step_point}")
            print(f"   Success: {result.success}")
            print(f"   Message: {result.message}")
            print(f"   Processing time: {result.processing_time_ms}ms")
            if result.step_result:
                print(f"   Step result: {result.step_result}")
            if result.pipeline_state:
                print(f"   Pipeline state: {result.pipeline_state}")
        except Exception as e:
            print(f"✗ Step failed: {e}")
        
        # Get state after stepping
        try:
            state = await client.system.get_state()
            print(f"\n📊 State after step:")
            print(f"   Processor state: {state.processor_state}")
            print(f"   Queue depth: {state.queue_depth}")
            print(f"   Current step: {state.current_step}")
        except Exception as e:
            print(f"✗ Failed to get state: {e}")

if __name__ == "__main__":
    asyncio.run(test_stepping())