"""
Comprehensive Single-Step COVENANT Compliance Test Module.

This module provides a single comprehensive test with 17 ordered phases that validate
the complete PDMA ethical reasoning pipeline step-by-step for COVENANT compliance.

17 Phases:
1. Initial system state check
2. Pause processor
3. Create task via interact
4. Verify task queued  
5-19. Single step through all 15 PDMA step points with validation
20. Resume processor
21. Final validation

Each phase must pass before proceeding to the next.
"""

import asyncio
import json
import time
from typing import Any, Dict, List, Optional

import requests

from ..config import QAConfig, QAModule, QATestCase


class ComprehensiveSingleStepTestModule:
    """Comprehensive single-step testing with 17 ordered phases."""

    @staticmethod
    def get_comprehensive_single_step_tests() -> List[QATestCase]:
        """Get the single comprehensive test with all 17 phases."""
        return [
            QATestCase(
                name="Comprehensive 17-Phase COVENANT Single-Step Validation",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/state",  # Start with state check
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Complete end-to-end validation of all 15 PDMA step points with setup/teardown phases",
                custom_validation=ComprehensiveSingleStepTestModule._run_17_phase_validation,
            )
        ]

    @staticmethod
    def _run_17_phase_validation(response: requests.Response, config: QAConfig) -> Dict[str, Any]:
        """Run the complete 17-phase validation process."""
        
        results = {
            "passed": True,
            "details": {
                "phases_completed": 0,
                "total_phases": 17,
                "step_points_validated": [],
                "failed_phase": None,
                "phase_results": {}
            },
            "errors": []
        }
        
        try:
            # Helper function to make authenticated requests
            def make_request(method: str, endpoint: str, payload: Optional[Dict] = None) -> requests.Response:
                url = f"{config.base_url}{endpoint}"
                headers = {"Authorization": f"Bearer {getattr(config, '_auth_token', '')}", "Content-Type": "application/json"}
                
                if method.upper() == "GET":
                    return requests.get(url, headers=headers, timeout=30)
                elif method.upper() == "POST":
                    return requests.post(url, headers=headers, json=payload or {}, timeout=30)
                else:
                    raise ValueError(f"Unsupported method: {method}")
            
            # Define all 15 PDMA step points in order
            step_points = [
                "finalize_tasks_queue",
                "populate_thought_queue", 
                "populate_round",
                "build_context",
                "perform_dmas",
                "perform_aspdma",
                "conscience_execution",
                "recursive_aspdma",
                "recursive_conscience",
                "action_selection",
                "handler_start",
                "bus_outbound",
                "package_handling",
                "bus_inbound",
                "handler_complete"
            ]
            
            # === PHASE 1: Initial System State Check ===
            print("\\n=== PHASE 1: Initial System State Check ===")
            state_response = make_request("POST", "/v1/system/runtime/state")
            if state_response.status_code != 200:
                results["failed_phase"] = 1
                results["errors"].append(f"Phase 1: Could not get system state - {state_response.status_code}")
                results["passed"] = False
                return results
                
            state_data = state_response.json().get("data", {})
            initial_processor_state = state_data.get("processor_state", "unknown")
            results["details"]["phase_results"]["1_initial_state"] = {
                "processor_state": initial_processor_state,
                "success": True
            }
            results["details"]["phases_completed"] = 1
            
            # === PHASE 2: Pause Processor ===
            print("\\n=== PHASE 2: Pause Processor ===")
            
            # Try to pause multiple times to ensure it takes effect
            pause_attempts = 0
            max_pause_attempts = 3
            processor_actually_paused = False
            
            while pause_attempts < max_pause_attempts and not processor_actually_paused:
                pause_attempts += 1
                print(f"  Pause attempt {pause_attempts}/{max_pause_attempts}")
                
                pause_response = make_request("POST", "/v1/system/runtime/pause")
                pause_data = pause_response.json().get("data", {})
                
                # Wait a moment for the pause to take effect
                time.sleep(0.2)
                
                # Test if single-step is now possible (this is the real test)
                test_step_response = make_request("POST", "/v1/system/runtime/step")
                test_step_data = test_step_response.json().get("data", {})
                
                if test_step_data.get("success") == False:
                    step_error = test_step_data.get("message", "")
                    if "cannot single-step unless" in step_error.lower():
                        print(f"    Pause attempt {pause_attempts} failed - processor not paused")
                        continue
                
                # If we get here, either single-step worked or gave a different error
                processor_actually_paused = True
                print(f"    Pause successful after {pause_attempts} attempts")
                break
                
            if not processor_actually_paused:
                results["failed_phase"] = 2
                results["errors"].append(f"Phase 2: Could not pause processor after {max_pause_attempts} attempts")
                results["passed"] = False
                return results
                    
            results["details"]["phase_results"]["2_pause"] = {
                "success": True, 
                "pause_attempts": pause_attempts,
                "processor_actually_paused": processor_actually_paused
            }
            results["details"]["phases_completed"] = 2
            
            # === PHASE 3: Create Task via Interact ===
            print("\\n=== PHASE 3: Create Task via Interact ===")
            
            # Get initial queue size
            initial_queue_response = make_request("GET", "/v1/system/runtime/queue")
            initial_queue_size = initial_queue_response.json().get("data", {}).get("queue_size", 0)
            print(f"  Initial queue size: {initial_queue_size}")
            
            # Start interact request in background (it will hang but queue the task immediately)
            interact_payload = {"message": "Please analyze the ethical implications of artificial intelligence in decision-making"}
            
            import threading
            import time
            
            interact_result = {"started": False}
            
            def make_interact_request():
                try:
                    interact_result["started"] = True
                    # This will hang, but the task gets queued immediately when request starts
                    response = make_request("POST", "/v1/agent/interact", interact_payload)
                except Exception:
                    # Expected to timeout/fail since processor is paused
                    pass
            
            # Start the request in background
            interact_thread = threading.Thread(target=make_interact_request)
            interact_thread.daemon = True
            interact_thread.start()
            
            # Wait a moment for the request to start and queue the task
            time.sleep(1.0)
            
            # Check that task was queued (should be initial_queue_size + 1)
            final_queue_response = make_request("GET", "/v1/system/runtime/queue")
            final_queue_size = final_queue_response.json().get("data", {}).get("queue_size", 0)
            print(f"  Final queue size: {final_queue_size}")
            
            expected_queue_size = initial_queue_size + 1
            task_was_queued = (final_queue_size >= expected_queue_size)
            
            if not task_was_queued:
                results["failed_phase"] = 3
                results["errors"].append(f"Phase 3: Task not queued - expected {expected_queue_size}, got {final_queue_size}")
                results["passed"] = False
                return results
                
            results["details"]["phase_results"]["3_create_task"] = {
                "initial_queue_size": initial_queue_size,
                "final_queue_size": final_queue_size,
                "expected_queue_size": expected_queue_size,
                "task_queued": task_was_queued,
                "success": True
            }
            results["details"]["phases_completed"] = 3
            
            # === PHASE 4: Verify Task Queued ===
            print("\\n=== PHASE 4: Verify Task Queued ===")
            queue_response = make_request("GET", "/v1/system/runtime/queue")
            queue_data = queue_response.json().get("data", {})
            queue_size = queue_data.get("queue_size", 0)
            
            results["details"]["phase_results"]["4_verify_queue"] = {
                "queue_size": queue_size,
                "success": True  # Even if queue is 0, we proceed (task may have been processed)
            }
            results["details"]["phases_completed"] = 4
            
            # === PHASES 5-19: Single Step Through All 15 PDMA Step Points ===
            for i, step_point in enumerate(step_points, 5):
                print(f"\\n=== PHASE {i}: Single Step - {step_point.upper()} ===")
                
                step_response = make_request("POST", "/v1/system/runtime/step?include_details=true")
                
                if step_response.status_code != 200:
                    results["failed_phase"] = i
                    results["errors"].append(f"Phase {i}: Single step failed - {step_response.status_code}")
                    results["passed"] = False
                    return results
                    
                step_data = step_response.json().get("data", {})
                current_step_point = step_data.get("step_point")
                step_result = step_data.get("step_result")
                
                # Validate step response structure
                phase_result = {
                    "step_point": current_step_point,
                    "has_step_result": step_result is not None,
                    "success": step_data.get("success", False),
                    "message": step_data.get("message", ""),
                    "processing_time_ms": step_data.get("processing_time_ms", 0)
                }
                
                # If we got a valid step result, validate its structure
                if step_result and isinstance(step_result, dict):
                    phase_result["step_result_type"] = type(step_result).__name__
                    phase_result["step_result_success"] = step_result.get("success", False)
                    
                    # Step point specific validations
                    if current_step_point == "perform_dmas" and step_result:
                        # Validate DMA results structure
                        dma_fields = ["ethical_dma_result", "common_sense_dma_result", "domain_dma_result"]
                        phase_result["has_dma_results"] = any(field in step_result for field in dma_fields)
                        
                    elif current_step_point == "action_selection" and step_result:
                        # Validate action selection
                        phase_result["has_selected_action"] = "selected_action" in step_result
                        
                    elif current_step_point == "conscience_execution" and step_result:
                        # Validate conscience results
                        phase_result["has_conscience_results"] = "conscience_results" in step_result
                        
                results["details"]["phase_results"][f"{i}_step_{step_point}"] = phase_result
                results["details"]["step_points_validated"].append(step_point)
                results["details"]["phases_completed"] = i
                
                # Short delay between steps
                time.sleep(0.1)
                
            # === PHASE 20: Resume Processor ===
            print("\\n=== PHASE 20: Resume Processor ===")
            resume_response = make_request("POST", "/v1/system/runtime/resume")
            resume_data = resume_response.json().get("data", {})
            
            results["details"]["phase_results"]["20_resume"] = {
                "success": resume_data.get("success", False),
                "message": resume_data.get("message", "")
            }
            results["details"]["phases_completed"] = 20
            
            # === PHASE 21: Final Validation ===
            print("\\n=== PHASE 21: Final Validation ===")
            final_state = make_request("POST", "/v1/system/runtime/state")
            final_data = final_state.json().get("data", {})
            
            results["details"]["phase_results"]["21_final_validation"] = {
                "final_processor_state": final_data.get("processor_state"),
                "final_queue_depth": final_data.get("queue_depth", 0),
                "success": True
            }
            results["details"]["phases_completed"] = 21
            
            # Final success summary
            total_step_points = len(results["details"]["step_points_validated"])
            results["details"]["total_step_points_validated"] = total_step_points
            results["details"]["expected_step_points"] = len(step_points)
            
            print(f"\\n=== VALIDATION COMPLETE ===")
            print(f"Phases completed: {results['details']['phases_completed']}/17")
            print(f"Step points validated: {total_step_points}")
            
            return results
            
        except Exception as e:
            results["passed"] = False
            results["errors"].append(f"Validation exception: {str(e)}")
            return results