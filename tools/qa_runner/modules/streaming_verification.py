"""
H3ERE Pipeline Streaming Verification Module.

This module verifies that all 11 H3ERE pipeline steps are properly streaming
via Server-Sent Events (SSE) to the reasoning-stream endpoint.

Expected Steps:
1. START_ROUND - Initialize processing round
2. GATHER_CONTEXT - Build context for analysis
3. PERFORM_DMAS - Multi-perspective analysis
4. PERFORM_ASPDMA - LLM action selection
5. CONSCIENCE_EXECUTION - Ethical validation
6. RECURSIVE_ASPDMA (conditional) - Re-run if conscience fails
7. RECURSIVE_CONSCIENCE (conditional) - Re-validate recursive action
8. FINALIZE_ACTION - Final action determination
9. PERFORM_ACTION - Dispatch to handler
10. ACTION_COMPLETE - Execution finished
11. ROUND_COMPLETE - Round cleanup

The test creates a task, monitors the SSE stream, and verifies all expected
steps are received with proper data.
"""

import asyncio
import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests

from ..config import QAConfig, QAModule, QATestCase


class StreamingVerificationModule:
    """Verify all 11 H3ERE pipeline steps are streaming correctly."""

    # All possible step points in the H3ERE pipeline (lowercase to match actual streaming)
    EXPECTED_STEPS = {
        "start_round",
        "gather_context",
        "perform_dmas",
        "perform_aspdma",
        "conscience_execution",
        "finalize_action",
        "perform_action",
        "action_complete",
        "round_complete",
    }

    # Conditional steps that may not always fire
    CONDITIONAL_STEPS = {"recursive_aspdma", "recursive_conscience"}

    @staticmethod
    def verify_streaming_steps(base_url: str, token: str, timeout: int = 30) -> Dict[str, Any]:
        """
        Connect to SSE stream and verify step points are received.

        Returns:
            Dict with verification results including received steps and any issues.
        """
        received_steps: Set[str] = set()
        step_details: List[Dict[str, Any]] = []
        errors: List[str] = []
        start_time = time.time()

        # Flag to stop the stream monitoring thread
        stop_monitoring = threading.Event()

        def monitor_stream():
            """Monitor SSE stream in a separate thread."""
            try:
                headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

                # Connect to SSE stream
                response = requests.get(
                    f"{base_url}/v1/system/runtime/reasoning-stream", headers=headers, stream=True, timeout=5
                )

                if response.status_code != 200:
                    errors.append(f"Stream connection failed: {response.status_code}")
                    return

                # Parse SSE stream manually
                for line in response.iter_lines():
                    if stop_monitoring.is_set():
                        break

                    if not line:
                        continue

                    line = line.decode("utf-8") if isinstance(line, bytes) else line

                    if line.startswith("event: step_update"):
                        # Next line should be the data
                        continue
                    elif line.startswith("data: "):
                        try:
                            data = json.loads(line[6:])  # Skip "data: " prefix

                            # Debug: print raw data structure
                            print(f"[DEBUG] Raw SSE data keys: {list(data.keys())}")

                            # Extract step information from updated thoughts
                            for thought in data.get("updated_thoughts", []):
                                step_point = thought.get("current_step")
                                print(f"[DEBUG] Thought {thought.get('thought_id')} has step: {step_point}")
                                if step_point:
                                    received_steps.add(step_point)
                                    step_details.append(
                                        {
                                            "step": step_point,
                                            "timestamp": datetime.now().isoformat(),
                                            "thought_id": thought.get("thought_id"),
                                            "status": thought.get("status"),
                                            "progress": thought.get("progress_percentage"),
                                        }
                                    )

                            # Also check step summaries
                            for summary in data.get("step_summaries", []):
                                step_point = summary.get("step_point")
                                count = summary.get("processing_count", 0)
                                print(f"[DEBUG] Step summary: {step_point} with count: {count}")
                                if step_point and count > 0:
                                    received_steps.add(step_point)

                        except json.JSONDecodeError as e:
                            errors.append(f"Failed to parse step_update: {e}")
                    elif line.startswith("event: error"):
                        errors.append(f"Stream error event received")

            except requests.exceptions.Timeout:
                errors.append("Stream connection timeout")
            except Exception as e:
                errors.append(f"Stream monitoring error: {e}")

        # Start monitoring in background thread
        monitor_thread = threading.Thread(target=monitor_stream)
        monitor_thread.daemon = True
        monitor_thread.start()

        # Create a task to trigger pipeline processing
        try:
            task_response = requests.post(
                f"{base_url}/v1/agent/interact",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"message": "Test H3ERE pipeline streaming verification"},
                timeout=timeout,
            )

            if task_response.status_code != 200:
                errors.append(f"Failed to create test task: {task_response.status_code}")

        except requests.exceptions.Timeout:
            # Expected - task may timeout while processing
            pass
        except Exception as e:
            errors.append(f"Task creation error: {e}")

        # Wait for streaming data or timeout
        elapsed = 0
        while elapsed < timeout and len(received_steps) < len(StreamingVerificationModule.EXPECTED_STEPS):
            time.sleep(0.5)
            elapsed = time.time() - start_time

        # Stop monitoring
        stop_monitoring.set()
        monitor_thread.join(timeout=2)

        # Analyze results
        missing_required = StreamingVerificationModule.EXPECTED_STEPS - received_steps
        unexpected_steps = (
            received_steps - StreamingVerificationModule.EXPECTED_STEPS - StreamingVerificationModule.CONDITIONAL_STEPS
        )

        # Check if conditional steps were received
        received_conditional = received_steps & StreamingVerificationModule.CONDITIONAL_STEPS

        return {
            "success": len(missing_required) == 0,
            "received_steps": sorted(list(received_steps)),
            "missing_required_steps": sorted(list(missing_required)),
            "received_conditional_steps": sorted(list(received_conditional)),
            "unexpected_steps": sorted(list(unexpected_steps)),
            "total_steps_received": len(received_steps),
            "expected_steps_count": len(StreamingVerificationModule.EXPECTED_STEPS),
            "step_details": step_details[-20:],  # Last 20 step events
            "errors": errors,
            "duration": time.time() - start_time,
        }

    @staticmethod
    def get_streaming_verification_tests() -> List[QATestCase]:
        """Get streaming verification test cases."""
        return [
            # Basic connectivity test
            QATestCase(
                name="SSE Stream Connectivity",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/reasoning-stream",
                method="GET",
                expected_status=200,
                requires_auth=True,
                description="Verify SSE stream endpoint is accessible",
                timeout=5,
            ),
            # Custom streaming verification test
            QATestCase(
                name="H3ERE Pipeline Streaming Verification",
                module=QAModule.SYSTEM,
                endpoint="/v1/system/runtime/reasoning-stream",
                method="CUSTOM",  # Special handling needed
                expected_status=200,
                requires_auth=True,
                description="Verify all 11 H3ERE pipeline steps stream correctly",
                timeout=30,
                custom_handler="verify_streaming_steps",
            ),
        ]

    @staticmethod
    def run_custom_test(test_case: QATestCase, config: QAConfig, token: str) -> Dict[str, Any]:
        """Run custom streaming verification test."""
        if test_case.custom_handler == "verify_streaming_steps":
            result = StreamingVerificationModule.verify_streaming_steps(config.base_url, token, test_case.timeout)

            # Format result for QA runner
            if result["success"]:
                return {
                    "success": True,
                    "message": f"✅ All {result['expected_steps_count']} required steps received",
                    "details": {
                        "received_steps": result["received_steps"],
                        "conditional_steps": result["received_conditional_steps"],
                        "duration": f"{result['duration']:.2f}s",
                    },
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Missing {len(result['missing_required_steps'])} required steps",
                    "details": {
                        "missing_steps": result["missing_required_steps"],
                        "received_steps": result["received_steps"],
                        "errors": result["errors"],
                    },
                }

        return {"success": False, "message": "Unknown custom handler", "details": {}}


# Module registration
def get_module_tests() -> List[QATestCase]:
    """Get all streaming verification tests for registration."""
    return StreamingVerificationModule.get_streaming_verification_tests()
