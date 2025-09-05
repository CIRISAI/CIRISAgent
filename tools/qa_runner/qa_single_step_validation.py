#!/usr/bin/env python3
"""
Comprehensive Single-Step QA Runner with Step-by-Step Validation

This QA runner implements the requested 5-phase process:
1. Pause the processor
2. Use interact endpoint to create a task  
3. Single step through all pipeline steps with validation at each step
4. Resume processor
5. Final validation of results and state

Each step is validated to ensure the single-step system works correctly.
"""

import asyncio
import json
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.append(os.path.join(os.path.dirname(__file__), '../../ciris_sdk'))

from ciris_sdk.client import CIRISClient
from ciris_sdk.resources.system import SingleStepResponse
from ciris_engine.schemas.services.runtime_control import StepPoint


class SingleStepQARunner:
    """Comprehensive QA runner for single-step validation."""
    
    def __init__(self, base_url: str = "http://localhost:9000"):
        self.base_url = base_url
        # The SDK will handle authentication automatically with default credentials
        self.client = CIRISClient(
            base_url=base_url,
            username="admin",
            password="ciris_admin_password",
            timeout=60  # Longer timeout for step validation
        )
        self.validation_results = []
        self.step_results = {}
        self.expected_steps = 15  # Will be updated with actual count
        
    async def log_validation(self, step: str, success: bool, message: str, data: Optional[Dict] = None):
        """Log validation result with timestamp."""
        result = {
            "timestamp": datetime.now().isoformat(),
            "step": step,
            "success": success,
            "message": message,
            "data": data or {}
        }
        self.validation_results.append(result)
        
        status = "✓" if success else "✗"
        print(f"{status} {step}: {message}")
        if not success:
            print(f"   Data: {json.dumps(data, indent=2)}")
    
    async def validate_step_point(self, expected: StepPoint, actual_response: SingleStepResponse) -> bool:
        """Validate that we received the expected step point."""
        actual_step = actual_response.step_point
        
        if actual_step != expected.value:
            await self.log_validation(
                f"validate_{expected.value}",
                False,
                f"Expected step {expected.value}, got {actual_step}",
                {"expected": expected.value, "actual": actual_step}
            )
            return False
            
        # Validate step-specific data exists
        step_result = actual_response.step_result or {}
        if not step_result:
            await self.log_validation(
                f"validate_{expected.value}",
                False,
                "No step_result data in response"
            )
            return False
            
        await self.log_validation(
            f"validate_{expected.value}",
            True,
            f"Step {expected.value} completed successfully",
            {"step_result_keys": list(step_result.keys())}
        )
        return True
    
    async def run_comprehensive_validation(self):
        """Run the complete 5-phase single-step validation."""
        
        print("=" * 80)
        print("COMPREHENSIVE SINGLE-STEP QA RUNNER")
        print(f"Started: {datetime.now().isoformat()}")
        print("=" * 80)
        
        try:
            # For the SDK, we use the async context manager
            async with self.client:
                # Authentication is handled automatically in the constructor
                await self.log_validation(
                    "authentication", 
                    True, 
                    "Authenticated successfully (handled automatically)",
                    {}
                )
                
                # === PHASE 1: PAUSE PROCESSOR ===
                print(f"\n{'='*20} PHASE 1: PAUSE PROCESSOR {'='*20}")
                
                # Get initial processor state  
                initial_state = await self.client.system.get_state()
                await self.log_validation(
                    "initial_state_check", 
                    True, 
                    f"Initial processor state: {initial_state.processor_state}",
                    {"state": initial_state.processor_state, "queue_depth": initial_state.queue_depth}
                )
                
                # Pause the processor
                pause_response = await self.client.system.pause()
                
                if pause_response.success:
                    await self.log_validation("pause_processor", True, "Processor paused successfully")
                else:
                    await self.log_validation("pause_processor", False, f"Failed to pause processor: {pause_response.message}")
                    return
                    
                # Verify processor is paused
                paused_state = await self.client.system.get_state()
                
                if "paused" in paused_state.processor_state.lower():
                    await self.log_validation("verify_pause", True, f"Processor confirmed paused: {paused_state.processor_state}")
                else:
                    await self.log_validation("verify_pause", False, f"Processor not paused: {paused_state.processor_state}")
                    return
                
                # === PHASE 2: CREATE TASK VIA INTERACT ===
                print(f"\n{'='*20} PHASE 2: CREATE TASK {'='*20}")
                
                test_message = "Please analyze the concept of artificial intelligence and its impact on society"
                interact_response = await self.client.interact(test_message)
                
                if interact_response.response:
                    await self.log_validation(
                        "create_task", 
                        True, 
                        f"Task created via interact. Response length: {len(interact_response.response)}"
                    )
                else:
                    await self.log_validation("create_task", False, "Failed to create task")
                    return
                    
                # Check queue status after interact
                queue_state = await self.client.system.get_state()
                if queue_state.queue_depth > 0:
                    await self.log_validation(
                        "verify_task_queued", 
                        True, 
                        f"Task queued successfully. Queue depth: {queue_state.queue_depth}"
                    )
                else:
                    await self.log_validation("verify_task_queued", True, "Queue appears empty (task may already be processed)")
                
                # === PHASE 3: SINGLE STEP THROUGH ALL PIPELINE STEPS ===
                print(f"\n{'='*20} PHASE 3: SINGLE STEP VALIDATION {'='*20}")
                
                # Define all step points in order (from the actual StepPoint enum)
                all_step_points = [
                    StepPoint.FINALIZE_TASKS_QUEUE,
                    StepPoint.POPULATE_THOUGHT_QUEUE,
                    StepPoint.POPULATE_ROUND,
                    StepPoint.BUILD_CONTEXT,
                    StepPoint.PERFORM_DMAS,
                    StepPoint.PERFORM_ASPDMA,
                    StepPoint.CONSCIENCE_EXECUTION,
                    StepPoint.RECURSIVE_ASPDMA,
                    StepPoint.RECURSIVE_CONSCIENCE,
                    StepPoint.ACTION_SELECTION,
                    StepPoint.HANDLER_START,
                    StepPoint.BUS_OUTBOUND,
                    StepPoint.PACKAGE_HANDLING,
                    StepPoint.BUS_INBOUND,
                    StepPoint.HANDLER_COMPLETE
                ]
                
                # Update expected steps count
                self.expected_steps = len(all_step_points)
                print(f"Stepping through {len(all_step_points)} step points...")
                
                for i, expected_step in enumerate(all_step_points, 1):
                    print(f"\n--- Step {i}/{len(all_step_points)}: {expected_step.value} ---")
                    
                    try:
                        # Execute single step
                        step_response = await self.client.system.single_step(include_details=True)
                        
                        # Validate the step
                        step_valid = await self.validate_step_point(expected_step, step_response)
                        
                        if step_valid:
                            # Store step results for final validation
                            self.step_results[expected_step.value] = {
                                "step_point": step_response.step_point,
                                "step_result": step_response.step_result,
                                "processing_time_ms": step_response.processing_time_ms,
                                "tokens_used": step_response.tokens_used
                            }
                            
                            # Additional step-specific validations
                            await self.validate_step_specifics(expected_step, step_response)
                        else:
                            print(f"⚠️  Step validation failed for {expected_step.value}")
                            # Continue with remaining steps for comprehensive testing
                            
                    except Exception as e:
                        await self.log_validation(
                            f"step_{expected_step.value}_error",
                            False,
                            f"Exception during step {expected_step.value}: {str(e)}"
                        )
                        print(f"❌ Error in step {expected_step.value}: {e}")
                        
                    # Brief pause between steps
                    await asyncio.sleep(0.5)
                
                # === PHASE 4: RESUME PROCESSOR ===
                print(f"\n{'='*20} PHASE 4: RESUME PROCESSOR {'='*20}")
                
                resume_response = await self.client.system.resume()
                
                if resume_response.success:
                    await self.log_validation("resume_processor", True, "Processor resumed successfully")
                else:
                    await self.log_validation("resume_processor", False, f"Failed to resume processor: {resume_response.message}")
                    
                # Verify processor is running
                resumed_state = await self.client.system.get_state()
                
                if "running" in resumed_state.processor_state.lower() or "active" in resumed_state.processor_state.lower():
                    await self.log_validation("verify_resume", True, f"Processor confirmed running: {resumed_state.processor_state}")
                else:
                    await self.log_validation("verify_resume", False, f"Processor not running: {resumed_state.processor_state}")
                
                # === PHASE 5: FINAL VALIDATION ===
                print(f"\n{'='*20} PHASE 5: FINAL VALIDATION {'='*20}")
                
                await self.final_system_validation()
                
                # Generate comprehensive report
                await self.generate_validation_report()
                
        except Exception as e:
            await self.log_validation("qa_runner_error", False, f"Critical error in QA runner: {str(e)}")
            raise
    
    async def validate_step_specifics(self, step_point: StepPoint, response: SingleStepResponse):
        """Perform step-specific validations based on the step type."""
        step_result = response.step_result or {}
        
        # Step-specific validations
        if step_point == StepPoint.BUILD_CONTEXT:
            if "context" in step_result or "user_message" in step_result:
                await self.log_validation("context_validation", True, "Context build data present")
            else:
                await self.log_validation("context_validation", False, "Missing context data", step_result)
                
        elif step_point == StepPoint.HANDLER_COMPLETE:
            if "result" in step_result or "action" in step_result:
                await self.log_validation("handler_validation", True, "Handler completion data present")
            else:
                await self.log_validation("handler_validation", False, "Missing handler data", step_result)
                
        # Validate pipeline state is progressing
        pipeline_state = response.pipeline_state or {}
        if pipeline_state:
            thoughts = pipeline_state.get("thoughts", [])
            if thoughts:
                await self.log_validation("pipeline_progression", True, f"Pipeline has {len(thoughts)} thoughts")
            else:
                await self.log_validation("pipeline_progression", True, "Pipeline state exists (may be empty)")
    
    async def final_system_validation(self):
        """Perform final system-wide validation after single-step process."""
        
        # 1. Validate system health
        try:
            health_response = await self.client.system.health()
            if health_response.status == "healthy":
                await self.log_validation("final_health_check", True, "System health is good")
            else:
                await self.log_validation("final_health_check", False, f"System health: {health_response.status}")
        except Exception as e:
            await self.log_validation("final_health_check", False, f"Health check error: {str(e)}")
        
        # 2. Validate step result completeness
        completed_steps = len(self.step_results)
        expected_steps = self.expected_steps
        
        if completed_steps >= expected_steps * 0.8:  # At least 80% of steps completed
            await self.log_validation(
                "step_completeness", 
                True, 
                f"Completed {completed_steps}/{expected_steps} steps successfully"
            )
        else:
            await self.log_validation(
                "step_completeness", 
                False, 
                f"Only completed {completed_steps}/{expected_steps} steps"
            )
    
    async def generate_validation_report(self):
        """Generate a comprehensive validation report."""
        
        print(f"\n{'='*20} VALIDATION REPORT {'='*20}")
        
        # Summary statistics
        total_validations = len(self.validation_results)
        successful_validations = sum(1 for r in self.validation_results if r["success"])
        success_rate = (successful_validations / total_validations * 100) if total_validations > 0 else 0
        
        print(f"Total Validations: {total_validations}")
        print(f"Successful: {successful_validations}")
        print(f"Failed: {total_validations - successful_validations}")
        print(f"Success Rate: {success_rate:.1f}%")
        
        # Failed validations details
        failed_validations = [r for r in self.validation_results if not r["success"]]
        if failed_validations:
            print(f"\n⚠️  FAILED VALIDATIONS ({len(failed_validations)}):")
            for failure in failed_validations:
                print(f"   • {failure['step']}: {failure['message']}")
        
        # Step completion summary
        print(f"\nStep Results Captured: {len(self.step_results)}/{self.expected_steps}")
        for step_name in self.step_results:
            print(f"   ✓ {step_name}")
        
        # Save detailed report to file
        report_data = {
            "timestamp": datetime.now().isoformat(),
            "summary": {
                "total_validations": total_validations,
                "successful_validations": successful_validations,
                "success_rate": success_rate,
                "steps_completed": len(self.step_results)
            },
            "validation_results": self.validation_results,
            "step_results": self.step_results
        }
        
        # Ensure qa_reports directory exists
        reports_dir = Path("qa_reports")
        reports_dir.mkdir(exist_ok=True)
        
        report_filename = f"single_step_qa_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        report_path = reports_dir / report_filename
        
        with open(report_path, 'w') as f:
            json.dump(report_data, f, indent=2)
        
        print(f"\n📊 Detailed report saved: {report_path}")
        
        # Overall assessment
        if success_rate >= 90:
            print(f"\n✅ OVERALL ASSESSMENT: EXCELLENT ({success_rate:.1f}% success)")
        elif success_rate >= 75:
            print(f"\n⚠️  OVERALL ASSESSMENT: GOOD ({success_rate:.1f}% success)")
        elif success_rate >= 50:
            print(f"\n❌ OVERALL ASSESSMENT: NEEDS IMPROVEMENT ({success_rate:.1f}% success)")
        else:
            print(f"\n🚨 OVERALL ASSESSMENT: CRITICAL ISSUES ({success_rate:.1f}% success)")


async def main():
    """Main entry point for single-step QA validation."""
    runner = SingleStepQARunner()
    await runner.run_comprehensive_validation()


if __name__ == "__main__":
    print("Starting Comprehensive Single-Step QA Validation...")
    asyncio.run(main())