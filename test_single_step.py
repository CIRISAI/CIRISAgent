#!/usr/bin/env python3
"""
Test single-step pipeline functionality with SDK.
"""
import asyncio
import json
from ciris_sdk import CIRISClient

async def test_pipeline():
    """Test the single-step pipeline with START_ROUND logic."""
    
    # Connect to the server on port 8001
    async with CIRISClient(base_url="http://localhost:8001") as client:
        try:
            # Login with admin credentials
            print("🔐 Logging in...")
            await client.login("admin", "ciris_admin_password")
            print("✅ Logged in successfully")
            
            # Pause the processor 
            print("\n⏸️ Pausing processor...")
            pause_response = await client.system.pause()
            print(f"✅ Paused: {pause_response.processor_state}")
            
            if pause_response.current_step:
                print(f"📍 Ready to execute: {pause_response.current_step}")
            else:
                print("⚠️ Current step is None - this should show 'start_round'")
            
            # Skip interact for now - we already have a PENDING thought in the database
            print("\n💬 Using existing PENDING thought from database...")
            
            # Now execute single steps
            print("\n🔄 Testing single-step execution...")
            
            for i in range(3):
                print(f"\n--- Step {i+1} ---")
                step_response = await client.system.single_step()
                
                print(f"Step Point: {step_response.step_point}")
                print(f"Success: {step_response.success}")
                
                if step_response.step_result:
                    print(f"Step Result: {step_response.step_result}")
                else:
                    print("Step Result: null")
                
                # Show pipeline state buckets
                if hasattr(step_response, 'pipeline_state') and step_response.pipeline_state:
                    thoughts_by_step = step_response.pipeline_state.get('thoughts_by_step', {})
                    non_empty_buckets = {k: v for k, v in thoughts_by_step.items() if v}
                    if non_empty_buckets:
                        print(f"Non-empty buckets: {list(non_empty_buckets.keys())}")
                    else:
                        print("All pipeline buckets empty")
                
                print(f"Processing time: {step_response.processing_time_ms}ms")
            
            print("\n✅ Single-step test completed!")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_pipeline())