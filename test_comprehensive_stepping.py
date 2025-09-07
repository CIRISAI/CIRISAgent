#!/usr/bin/env python3
"""Comprehensive test for paused interaction + stepping workflow using SDK."""

import asyncio
import sys
from pathlib import Path

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

from ciris_sdk.client import CIRISClient

async def test_comprehensive_stepping():
    """Test the complete paused interaction -> stepping workflow."""
    async with CIRISClient(base_url="http://localhost:8000") as client:
        print("🚀 Starting comprehensive stepping test")
        
        # Login
        try:
            login_response = await client.auth.login("admin", "ciris_admin_password")
            client._transport.set_api_key(login_response.access_token)
            print("✓ Logged in successfully")
        except Exception as e:
            print(f"✗ Login failed: {e}")
            return
        
        # Step 1: Pause the processor
        try:
            pause_result = await client.system.pause("Testing stepping workflow")
            print(f"✓ Paused processor: {pause_result.message}")
            print(f"  Processor state: {pause_result.processor_state}")
            print(f"  Queue depth: {pause_result.queue_depth}")
        except Exception as e:
            print(f"✗ Failed to pause: {e}")
            return
        
        # Step 2: Send some interactions while paused (should get immediate responses)
        messages = ["Hello there!", "How are you?", "What's the weather like?"]
        
        for i, message in enumerate(messages, 1):
            try:
                print(f"\n📨 Sending message {i}: '{message}'")
                start_time = asyncio.get_event_loop().time()
                
                response = await client.agent.interact(message)
                
                end_time = asyncio.get_event_loop().time()
                elapsed_ms = (end_time - start_time) * 1000
                
                print(f"✓ Response received in {elapsed_ms:.1f}ms:")
                print(f"  Response: {response.response}")
                print(f"  State: {response.state}")
                print(f"  Processing time: {response.processing_time_ms}ms")
            except Exception as e:
                print(f"✗ Failed to send message {i}: {e}")
        
        # Step 3: Check queue depth after adding messages
        try:
            state = await client.system.get_state()
            print(f"\n📊 State after adding messages:")
            print(f"   Processor state: {state.processor_state}")
            print(f"   Queue depth: {state.queue_depth}")
            print(f"   Current step: {state.current_step}")
        except Exception as e:
            print(f"✗ Failed to get state: {e}")
        
        # Step 4: Step through the pipeline one step at a time
        print(f"\n🔄 Starting single-step execution...")
        step_count = 0
        max_steps = 10  # Safety limit
        
        while step_count < max_steps:
            step_count += 1
            try:
                print(f"\n--- Step {step_count} ---")
                result = await client.system.single_step()
                
                print(f"Step Point: {result.step_point}")
                print(f"Success: {result.success}")
                print(f"Message: {result.message}")
                print(f"Processing time: {result.processing_time_ms}ms")
                
                if result.step_result:
                    print(f"Step result keys: {list(result.step_result.keys())}")
                    
                if result.pipeline_state:
                    print(f"Pipeline state keys: {list(result.pipeline_state.keys())}")
                    # Look for bucket information
                    if 'buckets' in result.pipeline_state:
                        buckets = result.pipeline_state['buckets']
                        for bucket_name, bucket_content in buckets.items():
                            if bucket_content:  # Only show non-empty buckets
                                print(f"  {bucket_name}: {len(bucket_content)} items")
                
                # If step failed or no more work to do, break
                if not result.success:
                    if "Nothing to process" in result.message or "no pending thoughts" in result.message:
                        print("✓ All processing complete - no more pending thoughts")
                        break
                    elif "not implemented" in result.message.lower():
                        print(f"⚠️  Hit unimplemented step: {result.message}")
                        break
                    else:
                        print(f"⚠️  Step failed: {result.message}")
                        break
                        
            except Exception as e:
                print(f"✗ Step {step_count} failed: {e}")
                break
        
        # Step 5: Check final state
        try:
            final_state = await client.system.get_state()
            print(f"\n📊 Final state:")
            print(f"   Processor state: {final_state.processor_state}")
            print(f"   Queue depth: {final_state.queue_depth}")
            print(f"   Current step: {final_state.current_step}")
        except Exception as e:
            print(f"✗ Failed to get final state: {e}")

        print(f"\n🏁 Test completed after {step_count} steps")

if __name__ == "__main__":
    asyncio.run(test_comprehensive_stepping())