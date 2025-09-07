#!/usr/bin/env python3
"""
Test that thoughts queued during paused interactions get processed when stepping.
"""
import asyncio
from ciris_sdk import CIRISClient

async def test_paused_then_step():
    """Test that paused interactions create thoughts that get processed during stepping."""
    
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
            print(f"📍 Ready to execute: {pause_response.current_step}")
            
            # Send multiple interactions while paused to queue up thoughts
            print("\n💬 Sending interactions while paused...")
            
            messages = [
                "Hello, how are you?",
                "What's the weather like?", 
                "Tell me a joke please",
            ]
            
            for i, message in enumerate(messages, 1):
                print(f"   📝 Message {i}: '{message}'")
                interact_response = await client.agent.interact(message)
                print(f"      ⚡ Response: {interact_response.response}")
                print(f"      🧠 State: {interact_response.state}")
                print(f"      ⏱️ Time: {interact_response.processing_time_ms}ms")
            
            # Now step through to see if the thoughts get processed
            print("\n🔄 Stepping through pipeline to process queued thoughts...")
            
            for step_num in range(8):  # Step through several steps
                print(f"\n--- Step {step_num + 1} ---")
                step_response = await client.system.single_step()
                
                print(f"Step Point: {step_response.step_point}")
                print(f"Success: {step_response.success}")
                print(f"Processing time: {step_response.processing_time_ms}ms")
                
                if step_response.step_result:
                    print(f"Step Result keys: {list(step_response.step_result.keys())}")
                    
                    # Look for evidence of thought processing
                    if 'thoughts_processed' in step_response.step_result:
                        print(f"🧠 Thoughts processed: {step_response.step_result['thoughts_processed']}")
                    
                    if 'round_started' in step_response.step_result:
                        print(f"🚀 Round started: {step_response.step_result['round_started']}")
                    
                    if 'context_gathered' in step_response.step_result:
                        print(f"📚 Context gathered: {step_response.step_result['context_gathered']}")
                        
                    if 'dmas_executed' in step_response.step_result:
                        print(f"🎯 DMAs executed: {step_response.step_result['dmas_executed']}")
                else:
                    print("Step Result: null")
                
                # Show pipeline state buckets
                if hasattr(step_response, 'pipeline_state') and step_response.pipeline_state:
                    thoughts_by_step = step_response.pipeline_state.get('thoughts_by_step', {})
                    non_empty_buckets = {k: v for k, v in thoughts_by_step.items() if v}
                    if non_empty_buckets:
                        print(f"📋 Non-empty buckets: {list(non_empty_buckets.keys())}")
                        for bucket, thoughts in non_empty_buckets.items():
                            print(f"   {bucket}: {len(thoughts)} thought(s)")
                    else:
                        print("📋 All pipeline buckets empty")
                else:
                    print("📋 No pipeline state available")
                
                # If we see evidence of processing, great!
                if step_response.step_result and any(key in step_response.step_result for key in 
                    ['thoughts_processed', 'context_gathered', 'dmas_executed']):
                    print("🎉 Found evidence of thought processing!")
            
            print("\n✅ Stepping test completed!")
            
        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_paused_then_step())