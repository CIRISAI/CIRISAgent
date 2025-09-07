#!/usr/bin/env python3
"""
Test the immediate paused response functionality.
"""
import asyncio
from ciris_sdk import CIRISClient

async def test_paused_interaction():
    """Test that interactions return immediately when paused."""
    
    # Connect to the server on port 8001
    async with CIRISClient(base_url="http://localhost:8001") as client:
        try:
            # Login with admin credentials
            print("🔐 Logging in...")
            await client.login("admin", "ciris_admin_password")
            print("✅ Logged in successfully")
            
            # First, pause the processor 
            print("\n⏸️ Pausing processor...")
            pause_response = await client.system.pause()
            print(f"✅ Paused: {pause_response.processor_state}")
            print(f"📍 Ready to execute: {pause_response.current_step}")
            
            # Now test interaction while paused - should return immediately
            print("\n💬 Testing interaction while paused...")
            import time
            start_time = time.time()
            
            interact_response = await client.agent.interact("Hello, how are you?")
            
            end_time = time.time()
            duration_ms = (end_time - start_time) * 1000
            
            print(f"⚡ Response received in {duration_ms:.1f}ms")
            print(f"📝 Response: {interact_response.response}")
            print(f"🧠 State: {interact_response.state}")
            print(f"⏱️ Processing time: {interact_response.processing_time_ms}ms")
            
            # Test another interaction to make sure it's consistently fast
            print("\n💬 Testing second interaction while paused...")
            start_time = time.time()
            
            interact_response2 = await client.agent.interact("What's the weather like?")
            
            end_time = time.time()
            duration_ms2 = (end_time - start_time) * 1000
            
            print(f"⚡ Response received in {duration_ms2:.1f}ms")
            print(f"📝 Response: {interact_response2.response}")
            print(f"🧠 State: {interact_response2.state}")
            print(f"⏱️ Processing time: {interact_response2.processing_time_ms}ms")
            
            # Resume the processor and test normal interaction
            print("\n▶️ Resuming processor...")
            resume_response = await client.system.resume()
            print(f"✅ Resumed: {resume_response.processor_state}")
            
            print("\n💬 Testing interaction after resume (should take longer)...")
            start_time = time.time()
            
            interact_response3 = await client.agent.interact("Tell me a joke.")
            
            end_time = time.time()
            duration_ms3 = (end_time - start_time) * 1000
            
            print(f"⚡ Response received in {duration_ms3:.1f}ms")
            print(f"📝 Response: {interact_response3.response}")
            print(f"🧠 State: {interact_response3.state}")
            print(f"⏱️ Processing time: {interact_response3.processing_time_ms}ms")
            
            print("\n✅ Paused interaction test completed!")
            print(f"📊 Comparison:")
            print(f"   - Paused interaction 1: {duration_ms:.1f}ms")
            print(f"   - Paused interaction 2: {duration_ms2:.1f}ms") 
            print(f"   - Normal interaction:   {duration_ms3:.1f}ms")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_paused_interaction())