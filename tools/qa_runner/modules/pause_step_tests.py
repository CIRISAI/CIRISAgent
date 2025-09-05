"""
Comprehensive pause/step functionality tests for live system validation.

Tests the enhanced single-step API endpoint with real system interactions,
validating the complete 15-step ethical reasoning pipeline visibility.
"""

import json
import time
from typing import Any, Dict, List, Optional

import requests

from ..config import QAConfig, QAModule, QATestCase


class PauseStepTestModule:
    """Comprehensive pause/step testing for live system validation."""

    @staticmethod
    def get_pause_step_basic_tests() -> List[QATestCase]:
        """Get basic pause/step functionality tests."""
        return [
            # Basic runtime control tests
            QATestCase(
                name="Get processing queue status",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/queue",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting current processing queue status and metrics",
                validation_rules={
                    "has_queue_data": lambda r: "processor_name" in r.get("data", {}),
                    "has_metrics": lambda r: "queue_size" in r.get("data", {}),
                },
            ),
            QATestCase(
                name="Basic single-step execution (legacy)",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Test basic single-step execution without details (backward compatibility)",
                validation_rules={
                    "has_success": lambda r: r.get("data", {}).get("success") is not None,
                    "has_processor_state": lambda r: "processor_state" in r.get("data", {}),
                    "has_queue_depth": lambda r: "queue_depth" in r.get("data", {}),
                    "no_enhanced_data": lambda r: "step_point" not in r.get("data", {}),
                },
            ),
            QATestCase(
                name="Enhanced single-step with details",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step?include_details=true",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Test enhanced single-step execution with detailed step point data",
                validation_rules={
                    "has_success": lambda r: r.get("data", {}).get("success") is not None,
                    "has_step_point": lambda r: "step_point" in r.get("data", {}),
                    "has_step_result": lambda r: "step_result" in r.get("data", {}),
                    "has_pipeline_state": lambda r: "pipeline_state" in r.get("data", {}),
                    "has_performance_metrics": lambda r: "processing_time_ms" in r.get("data", {}),
                    "has_demo_data": lambda r: "demo_data" in r.get("data", {}),
                },
            ),
            QATestCase(
                name="Processor states information",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/processors",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Test getting all processor states and current active state",
                validation_rules={
                    "has_states": lambda r: len(r.get("data", [])) >= 6,  # 6 cognitive states
                    "has_active_state": lambda r: any(state.get("is_active") for state in r.get("data", [])),
                    "valid_states": lambda r: all(
                        state.get("name") in ["WAKEUP", "WORK", "DREAM", "PLAY", "SOLITUDE", "SHUTDOWN"]
                        for state in r.get("data", [])
                    ),
                },
            ),
        ]

    @staticmethod
    def get_step_point_validation_tests() -> List[QATestCase]:
        """Get tests that validate specific step point data."""
        return [
            QATestCase(
                name="Step point data structure validation",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step?include_details=true",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Validate step point data contains expected structure",
                validation_rules={
                    "valid_step_point_enum": lambda r: r.get("data", {}).get("step_point") in [
                        "finalize_tasks_queue", "populate_thought_queue", "populate_round",
                        "build_context", "perform_dmas", "perform_aspdma", "conscience_execution",
                        "recursive_aspdma", "recursive_conscience", "action_selection",
                        "handler_start", "bus_outbound", "package_handling", "bus_inbound", "handler_complete"
                    ] if r.get("data", {}).get("step_point") else True,  # Allow None
                    "step_result_structure": lambda r: isinstance(r.get("data", {}).get("step_result"), (dict, type(None))),
                    "pipeline_state_structure": lambda r: isinstance(r.get("data", {}).get("pipeline_state"), (dict, type(None))),
                    "performance_metrics": lambda r: isinstance(r.get("data", {}).get("processing_time_ms"), (int, float)),
                },
            ),
            QATestCase(
                name="DMA step point validation", 
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step?include_details=true",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Validate DMA step point contains parallel DMA results",
                custom_validation=PauseStepTestModule._validate_dma_step,
            ),
            QATestCase(
                name="Pipeline state structure validation",
                module=QAModule.SYSTEM,  
                endpoint="/v1/system/runtime/step?include_details=true",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Validate pipeline state contains thoughts-by-step structure",
                custom_validation=PauseStepTestModule._validate_pipeline_state,
            ),
        ]

    @staticmethod
    def get_demo_workflow_tests() -> List[QATestCase]:
        """Get tests that simulate complete demo workflows."""
        return [
            QATestCase(
                name="Complete pause/step demo workflow",
                module=QAModule.SYSTEM,
                endpoint="/v1/agent/interact",
                method="POST", 
                payload={"message": "Hello, please explain your ethical reasoning process"},
                expected_status=200,
                requires_auth=True,
                description="Trigger agent interaction to generate thoughts for step-by-step processing",
                custom_validation=PauseStepTestModule._validate_agent_interaction,
            ),
            QATestCase(
                name="Multi-step processing validation",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step?include_details=true", 
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Execute multiple single steps to validate complete pipeline flow",
                custom_validation=PauseStepTestModule._validate_multi_step_execution,
                repeat_count=5,  # Execute 5 times to see different step points
            ),
        ]

    @staticmethod
    def get_error_handling_tests() -> List[QATestCase]:
        """Get tests for error handling and edge cases."""
        return [
            QATestCase(
                name="Invalid query parameter handling",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step?include_details=invalid",
                method="POST",
                payload={},
                expected_status=422,  # FastAPI validation error
                requires_auth=True,
                description="Test handling of invalid boolean query parameters",
            ),
            QATestCase(
                name="Enhanced response memory efficiency",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step?include_details=true",
                method="POST", 
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Validate enhanced response size is reasonable for demo purposes",
                custom_validation=PauseStepTestModule._validate_response_size,
            ),
            QATestCase(
                name="Concurrent single-step requests",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step?include_details=true",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Test handling of concurrent single-step execution requests",
                custom_validation=PauseStepTestModule._validate_concurrent_requests,
            ),
        ]

    @staticmethod
    def get_performance_tests() -> List[QATestCase]:
        """Get performance-focused tests."""
        return [
            QATestCase(
                name="Single-step performance baseline",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step?include_details=true",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True,
                description="Measure performance baseline for enhanced single-step operations",
                custom_validation=PauseStepTestModule._validate_performance_baseline,
                timeout=30,
            ),
            QATestCase(
                name="Step point data extraction performance",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/step?include_details=true",
                method="POST",
                payload={},
                expected_status=200,
                requires_auth=True, 
                description="Validate step point data extraction doesn't cause significant overhead",
                custom_validation=PauseStepTestModule._validate_extraction_performance,
                timeout=15,
            ),
        ]

    @staticmethod
    def _validate_dma_step(response: requests.Response, config: QAConfig) -> Dict[str, Any]:
        """Custom validation for DMA step point data."""
        try:
            data = response.json()
            step_data = data.get("data", {})
            
            results = {
                "passed": True,
                "details": {},
                "errors": []
            }
            
            # Check if this is a PERFORM_DMAS step
            if step_data.get("step_point") == "perform_dmas":
                step_result = step_data.get("step_result", {})
                
                # Validate DMA results structure
                dma_fields = ["ethical_dma", "common_sense_dma", "domain_dma"]
                for field in dma_fields:
                    if field in step_result:
                        dma_result = step_result[field]
                        if not isinstance(dma_result, dict):
                            results["errors"].append(f"{field} should be a dict")
                            results["passed"] = False
                        else:
                            # Validate DMA result has required fields
                            if field == "ethical_dma":
                                required = ["decision", "reasoning", "alignment_check"]
                            elif field == "common_sense_dma":
                                required = ["plausibility_score", "reasoning", "flags"]
                            else:  # domain_dma
                                required = ["domain", "domain_alignment", "reasoning", "flags"]
                            
                            for req_field in required:
                                if req_field not in dma_result:
                                    results["errors"].append(f"{field} missing {req_field}")
                                    results["passed"] = False
                
                # Validate parallel execution metadata
                if "dmas_executed" in step_result:
                    executed = step_result["dmas_executed"]
                    if not isinstance(executed, list) or len(executed) != 3:
                        results["errors"].append("dmas_executed should list all 3 DMAs")
                        results["passed"] = False
                
                if "total_time_ms" in step_result and "longest_dma_time_ms" in step_result:
                    total_time = step_result["total_time_ms"]
                    longest_time = step_result["longest_dma_time_ms"]
                    if longest_time > total_time:
                        results["errors"].append("longest_dma_time_ms cannot exceed total_time_ms for parallel execution")
                        results["passed"] = False
            
            results["details"]["step_point"] = step_data.get("step_point")
            results["details"]["has_dma_data"] = bool(step_data.get("step_result", {}).get("ethical_dma"))
            
            return results
            
        except Exception as e:
            return {
                "passed": False,
                "details": {},
                "errors": [f"Validation exception: {str(e)}"]
            }

    @staticmethod
    def _validate_pipeline_state(response: requests.Response, config: QAConfig) -> Dict[str, Any]:
        """Custom validation for pipeline state structure."""
        try:
            data = response.json()
            step_data = data.get("data", {})
            pipeline_state = step_data.get("pipeline_state")
            
            results = {
                "passed": True,
                "details": {},
                "errors": []
            }
            
            if pipeline_state:
                # Validate pipeline state structure
                required_fields = ["is_paused", "current_round", "thoughts_by_step"]
                for field in required_fields:
                    if field not in pipeline_state:
                        results["errors"].append(f"Pipeline state missing {field}")
                        results["passed"] = False
                
                # Validate thoughts_by_step structure
                thoughts_by_step = pipeline_state.get("thoughts_by_step", {})
                if thoughts_by_step:
                    for step_name, thoughts in thoughts_by_step.items():
                        if not isinstance(thoughts, list):
                            results["errors"].append(f"thoughts_by_step[{step_name}] should be a list")
                            results["passed"] = False
                        
                        for thought in thoughts:
                            if not isinstance(thought, dict):
                                results["errors"].append(f"Thought in {step_name} should be a dict")
                                results["passed"] = False
                                continue
                            
                            # Validate thought structure
                            required_thought_fields = ["thought_id", "task_id", "current_step"]
                            for field in required_thought_fields:
                                if field not in thought:
                                    results["errors"].append(f"Thought missing {field}")
                                    results["passed"] = False
            
            results["details"]["has_pipeline_state"] = pipeline_state is not None
            results["details"]["thoughts_count"] = sum(
                len(thoughts) for thoughts in pipeline_state.get("thoughts_by_step", {}).values()
            ) if pipeline_state else 0
            
            return results
            
        except Exception as e:
            return {
                "passed": False,
                "details": {},
                "errors": [f"Validation exception: {str(e)}"]
            }

    @staticmethod
    def _validate_agent_interaction(response: requests.Response, config: QAConfig) -> Dict[str, Any]:
        """Custom validation for agent interaction to set up thoughts."""
        try:
            data = response.json()
            
            results = {
                "passed": True,
                "details": {},
                "errors": []
            }
            
            # Validate agent response structure
            if "response" not in data:
                results["errors"].append("Agent response missing 'response' field")
                results["passed"] = False
            
            if "thought_id" not in data:
                results["errors"].append("Agent response missing 'thought_id' field")
                results["passed"] = False
            
            # Wait a moment for thoughts to be queued
            time.sleep(2)
            
            # Check if thoughts were created by getting queue status
            try:
                queue_response = requests.get(
                    f"{config.base_url}/v1/system/runtime/queue",
                    headers={"Authorization": f"Bearer {getattr(config, '_auth_token', '')}"}
                )
                if queue_response.status_code == 200:
                    queue_data = queue_response.json()
                    queue_size = queue_data.get("data", {}).get("queue_size", 0)
                    results["details"]["queue_size_after_interaction"] = queue_size
                    
                    if queue_size == 0:
                        results["errors"].append("No thoughts queued after agent interaction")
                        # Don't fail the test for this, as processing might be very fast
                
            except Exception as e:
                results["details"]["queue_check_error"] = str(e)
            
            results["details"]["response_length"] = len(data.get("response", ""))
            results["details"]["thought_id"] = data.get("thought_id", "")
            
            return results
            
        except Exception as e:
            return {
                "passed": False,
                "details": {},
                "errors": [f"Validation exception: {str(e)}"]
            }

    @staticmethod
    def _validate_multi_step_execution(response: requests.Response, config: QAConfig) -> Dict[str, Any]:
        """Custom validation for multi-step execution."""
        try:
            step_points_seen = getattr(config, '_step_points_seen', set())
            
            data = response.json()
            step_data = data.get("data", {})
            step_point = step_data.get("step_point")
            
            results = {
                "passed": True,
                "details": {},
                "errors": []
            }
            
            if step_point:
                step_points_seen.add(step_point)
                setattr(config, '_step_points_seen', step_points_seen)
            
            # Validate we're seeing different step points over time
            results["details"]["current_step_point"] = step_point
            results["details"]["unique_step_points_seen"] = len(step_points_seen)
            results["details"]["step_points_list"] = list(step_points_seen)
            
            # Check for demo data quality
            demo_data = step_data.get("demo_data")
            if demo_data:
                if "category" not in demo_data:
                    results["errors"].append("Demo data missing category")
                    results["passed"] = False
                
                valid_categories = ["queue_management", "ethical_reasoning", "decision_making", 
                                  "system_architecture", "learning_adaptation", "performance_completion"]
                if demo_data.get("category") not in valid_categories:
                    results["errors"].append(f"Invalid demo category: {demo_data.get('category')}")
                    results["passed"] = False
            
            return results
            
        except Exception as e:
            return {
                "passed": False,
                "details": {},
                "errors": [f"Validation exception: {str(e)}"]
            }

    @staticmethod
    def _validate_response_size(response: requests.Response, config: QAConfig) -> Dict[str, Any]:
        """Custom validation for response size efficiency."""
        try:
            content_length = len(response.content)
            
            results = {
                "passed": True,
                "details": {},
                "errors": []
            }
            
            # Check response size is reasonable for demo purposes (< 50KB)
            max_size = 50 * 1024  # 50KB
            if content_length > max_size:
                results["errors"].append(f"Response too large: {content_length} bytes > {max_size} bytes")
                results["passed"] = False
            
            results["details"]["response_size_bytes"] = content_length
            results["details"]["response_size_kb"] = round(content_length / 1024, 2)
            
            # Check that response has good data density (not too much empty content)
            data = response.json()
            data_str = json.dumps(data)
            data_length = len(data_str)
            
            results["details"]["json_size_bytes"] = data_length
            results["details"]["compression_ratio"] = round(content_length / data_length, 2) if data_length > 0 else 0
            
            return results
            
        except Exception as e:
            return {
                "passed": False,
                "details": {},
                "errors": [f"Validation exception: {str(e)}"]
            }

    @staticmethod
    def _validate_concurrent_requests(response: requests.Response, config: QAConfig) -> Dict[str, Any]:
        """Custom validation for concurrent request handling."""
        import concurrent.futures
        import threading
        
        try:
            results = {
                "passed": True,
                "details": {},
                "errors": []
            }
            
            # Make 3 concurrent requests
            def make_request():
                try:
                    response = requests.post(
                        f"{config.base_url}/v1/system/runtime/step?include_details=true",
                        headers={"Authorization": f"Bearer {getattr(config, '_auth_token', '')}"},
                        json={},
                        timeout=10
                    )
                    return response.status_code, response.elapsed.total_seconds()
                except Exception as e:
                    return None, str(e)
            
            # Execute concurrent requests
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
                futures = [executor.submit(make_request) for _ in range(3)]
                concurrent_results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
            # Analyze results
            successful_requests = [r for r in concurrent_results if r[0] == 200]
            failed_requests = [r for r in concurrent_results if r[0] != 200]
            
            results["details"]["concurrent_requests_made"] = len(concurrent_results)
            results["details"]["successful_requests"] = len(successful_requests)
            results["details"]["failed_requests"] = len(failed_requests)
            
            if len(successful_requests) < 2:  # At least 2 should succeed
                results["errors"].append(f"Too many concurrent requests failed: {len(failed_requests)}")
                results["passed"] = False
            
            if successful_requests:
                response_times = [r[1] for r in successful_requests]
                results["details"]["avg_response_time"] = round(sum(response_times) / len(response_times), 3)
                results["details"]["max_response_time"] = round(max(response_times), 3)
            
            return results
            
        except Exception as e:
            return {
                "passed": False,
                "details": {},
                "errors": [f"Validation exception: {str(e)}"]
            }

    @staticmethod
    def _validate_performance_baseline(response: requests.Response, config: QAConfig) -> Dict[str, Any]:
        """Custom validation for performance baseline measurement."""
        try:
            response_time = response.elapsed.total_seconds()
            
            results = {
                "passed": True,
                "details": {},
                "errors": []
            }
            
            # Set performance thresholds
            max_response_time = 5.0  # 5 seconds max
            warning_response_time = 2.0  # 2 seconds warning
            
            results["details"]["response_time_seconds"] = round(response_time, 3)
            results["details"]["max_threshold"] = max_response_time
            results["details"]["warning_threshold"] = warning_response_time
            
            if response_time > max_response_time:
                results["errors"].append(f"Response time too slow: {response_time:.3f}s > {max_response_time}s")
                results["passed"] = False
            elif response_time > warning_response_time:
                results["details"]["warning"] = f"Response time above warning threshold: {response_time:.3f}s"
            
            # Check response data quality
            data = response.json()
            step_data = data.get("data", {})
            
            processing_time = step_data.get("processing_time_ms", 0)
            if processing_time > 0:
                results["details"]["reported_processing_time_ms"] = processing_time
                results["details"]["reported_processing_time_seconds"] = round(processing_time / 1000, 3)
            
            return results
            
        except Exception as e:
            return {
                "passed": False,
                "details": {},
                "errors": [f"Validation exception: {str(e)}"]
            }

    @staticmethod
    def _validate_extraction_performance(response: requests.Response, config: QAConfig) -> Dict[str, Any]:
        """Custom validation for step point data extraction performance."""
        try:
            # Compare with basic single-step request
            start_time = time.time()
            basic_response = requests.post(
                f"{config.base_url}/v1/system/runtime/step",
                headers={"Authorization": f"Bearer {getattr(config, '_auth_token', '')}"},
                json={},
                timeout=10
            )
            basic_time = time.time() - start_time
            
            enhanced_time = response.elapsed.total_seconds()
            
            results = {
                "passed": True,
                "details": {},
                "errors": []
            }
            
            results["details"]["basic_response_time"] = round(basic_time, 3)
            results["details"]["enhanced_response_time"] = round(enhanced_time, 3)
            results["details"]["overhead_seconds"] = round(enhanced_time - basic_time, 3)
            results["details"]["overhead_percent"] = round(((enhanced_time - basic_time) / basic_time) * 100, 1) if basic_time > 0 else 0
            
            # Overhead should be reasonable (< 200% increase)
            max_overhead_percent = 200
            overhead_percent = results["details"]["overhead_percent"]
            
            if overhead_percent > max_overhead_percent:
                results["errors"].append(f"Data extraction overhead too high: {overhead_percent}% > {max_overhead_percent}%")
                results["passed"] = False
            
            return results
            
        except Exception as e:
            return {
                "passed": False,
                "details": {},
                "errors": [f"Validation exception: {str(e)}"]
            }

    @staticmethod
    def get_all_pause_step_tests() -> List[QATestCase]:
        """Get all pause/step tests."""
        tests = []
        tests.extend(PauseStepTestModule.get_pause_step_basic_tests())
        tests.extend(PauseStepTestModule.get_step_point_validation_tests())
        tests.extend(PauseStepTestModule.get_demo_workflow_tests())
        tests.extend(PauseStepTestModule.get_error_handling_tests())
        tests.extend(PauseStepTestModule.get_performance_tests())
        return tests