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
    # Note: Not all steps appear in current_step field, some are only in step_summaries
    EXPECTED_STEPS = {
        "start_round",  # May only appear in step_summaries
        "gather_context",
        "perform_dmas",
        "perform_aspdma",
        "conscience_execution",
        "finalize_action",
        "perform_action",  # May only appear in step_summaries
        "action_complete",  # May only appear in step_summaries
        "round_complete",
    }

    # Conditional steps that may not always fire
    CONDITIONAL_STEPS = {"recursive_aspdma", "recursive_conscience"}

    @staticmethod
    def verify_streaming_steps(base_url: str, token: str, timeout: int = 20) -> Dict[str, Any]:
        """
        Connect to SSE stream and verify step points are received.

        Returns:
            Dict with verification results including received steps and any issues.
        """
        received_steps: Set[str] = set()
        step_details: List[Dict[str, Any]] = []
        errors: List[str] = []
        start_time = time.time()

        # Track task_id propagation
        task_ids_by_thought: Dict[str, str] = {}  # thought_id -> task_id
        task_id_issues: List[str] = []  # Track any task_id problems
        initial_task_id: Optional[str] = None  # Track the original task_id

        # Flag to stop the stream monitoring thread
        stop_monitoring = threading.Event()

        def monitor_stream():
            """Monitor SSE stream in a separate thread."""
            try:
                headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

                # Connect to SSE stream
                print(f"[DEBUG] Connecting to SSE stream at {base_url}/v1/system/runtime/reasoning-stream")
                response = requests.get(
                    f"{base_url}/v1/system/runtime/reasoning-stream", headers=headers, stream=True, timeout=5
                )

                if response.status_code != 200:
                    errors.append(f"Stream connection failed: {response.status_code}")
                    print(f"[ERROR] Stream connection failed with status {response.status_code}")
                    return

                print(f"[DEBUG] SSE stream connected successfully")

                # Parse SSE stream manually
                current_event = None
                for line in response.iter_lines():
                    if stop_monitoring.is_set():
                        break

                    if not line:
                        continue

                    line = line.decode("utf-8") if isinstance(line, bytes) else line

                    if line.startswith("event:"):
                        current_event = line[6:].strip()
                        continue
                    elif line.startswith("data:") and current_event == "step_update":
                        try:
                            data = json.loads(line[6:])  # Skip "data: " prefix

                            # Debug: print raw data structure
                            print(f"[DEBUG] Raw SSE data keys: {list(data.keys())}")

                            # Extract step information from updated thoughts (and new_thoughts)
                            thoughts_to_check = data.get("updated_thoughts", []) + data.get("new_thoughts", [])
                            for thought in thoughts_to_check:
                                thought_id = thought.get("thought_id")
                                task_id = thought.get("task_id")
                                step_point = thought.get("current_step")

                                # Track task_id propagation
                                if thought_id and task_id:
                                    # Store the first task_id we see
                                    if not initial_task_id:
                                        initial_task_id = task_id
                                        print(f"[TASK_ID] Initial task_id: {task_id}")

                                    # Check if this thought has a different task_id
                                    if thought_id in task_ids_by_thought:
                                        if task_ids_by_thought[thought_id] != task_id:
                                            msg = f"Task ID changed for thought {thought_id}: {task_ids_by_thought[thought_id]} -> {task_id}"
                                            task_id_issues.append(msg)
                                            print(f"[TASK_ID ERROR] {msg}")
                                    else:
                                        task_ids_by_thought[thought_id] = task_id
                                        # Check if this is a different thought with missing/wrong task_id
                                        if task_id != initial_task_id:
                                            msg = f"Different task_id for thought {thought_id}: expected {initial_task_id}, got {task_id}"
                                            task_id_issues.append(msg)
                                            print(f"[TASK_ID WARNING] {msg}")
                                elif thought_id and (not task_id or task_id == ""):
                                    # Empty string or None both count as missing
                                    msg = f"Missing task_id for thought {thought_id} at step {step_point}"
                                    task_id_issues.append(msg)
                                    print(f"[TASK_ID ERROR] {msg}")

                                print(f"[DEBUG] Thought {thought_id} has step: {step_point}, task_id: '{task_id}'")
                                if step_point:
                                    received_steps.add(step_point)
                                    step_details.append(
                                        {
                                            "step": step_point,
                                            "timestamp": datetime.now().isoformat(),
                                            "thought_id": thought_id,
                                            "task_id": task_id,
                                            "status": thought.get("status"),
                                            "progress": thought.get("progress_percentage"),
                                        }
                                    )

                            # Also check step summaries for completed steps
                            for summary in data.get("step_summaries", []):
                                step_point = summary.get("step_point")
                                processing_count = summary.get("processing_count", 0)
                                completed_count = summary.get("completed_count", 0)

                                # A step has been executed if it has either processing or completed thoughts
                                if step_point and (processing_count > 0 or completed_count > 0):
                                    print(
                                        f"[DEBUG] Step summary: {step_point} (processing={processing_count}, completed={completed_count})"
                                    )
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

        # Give the stream a moment to connect before creating task
        time.sleep(2)

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
        # We need to see all expected steps (9) to pass
        elapsed = 0
        last_step_count = 0
        no_progress_time = 0
        while elapsed < timeout:
            current_step_count = len(received_steps)

            # Check if we have all required steps
            if current_step_count >= len(StreamingVerificationModule.EXPECTED_STEPS):
                print(f"[DEBUG] All {current_step_count} steps received, stopping early")
                break

            # Check for progress
            if current_step_count > last_step_count:
                last_step_count = current_step_count
                no_progress_time = 0
                print(
                    f"[DEBUG] Progress: {current_step_count}/{len(StreamingVerificationModule.EXPECTED_STEPS)} steps received"
                )
            else:
                no_progress_time += 0.5
                # If no progress for 3 seconds, assume we're done
                if no_progress_time > 3:
                    print(f"[DEBUG] No progress for 3s, stopping at {current_step_count} steps")
                    break

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

        # Analyze task_id propagation
        unique_task_ids = set(task_ids_by_thought.values())
        unique_thoughts = len(task_ids_by_thought)

        return {
            "success": len(missing_required) == 0 and len(task_id_issues) == 0,
            "received_steps": sorted(list(received_steps)),
            "missing_required_steps": sorted(list(missing_required)),
            "received_conditional_steps": sorted(list(received_conditional)),
            "unexpected_steps": sorted(list(unexpected_steps)),
            "total_steps_received": len(received_steps),
            "expected_steps_count": len(StreamingVerificationModule.EXPECTED_STEPS),
            "step_details": step_details[-20:],  # Last 20 step events
            "errors": errors,
            "duration": time.time() - start_time,
            # Task ID tracking results
            "task_id_tracking": {
                "initial_task_id": initial_task_id,
                "unique_task_ids": len(unique_task_ids),
                "unique_thoughts": unique_thoughts,
                "task_ids_by_thought": task_ids_by_thought,
                "task_id_issues": task_id_issues,
                "all_thoughts_have_task_id": all(tid for tid in task_ids_by_thought.values()),
                "all_same_task_id": len(unique_task_ids) <= 1,
            },
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
                description="Verify all 9 required H3ERE pipeline steps stream correctly",
                timeout=20,
                custom_handler="verify_streaming_steps",
            ),
        ]

    @staticmethod
    def run_custom_test(test_case: QATestCase, config: QAConfig, token: str) -> Dict[str, Any]:
        """Run custom streaming verification test."""
        if test_case.custom_handler == "verify_streaming_steps":
            result = StreamingVerificationModule.verify_streaming_steps(config.base_url, token, test_case.timeout)

            # Format result for QA runner
            task_tracking = result.get("task_id_tracking", {})
            task_id_message = ""

            if task_tracking.get("task_id_issues"):
                task_id_message = f"\n⚠️ Task ID Issues: {len(task_tracking['task_id_issues'])} problems found"
            elif not task_tracking.get("all_thoughts_have_task_id"):
                task_id_message = "\n⚠️ Some thoughts missing task_id"
            elif not task_tracking.get("all_same_task_id"):
                task_id_message = f"\n⚠️ Multiple task IDs found: {task_tracking['unique_task_ids']} unique IDs"
            else:
                task_id_message = f"\n✅ Task ID propagation OK: {task_tracking.get('initial_task_id', 'N/A')}"

            if result["success"]:
                return {
                    "success": True,
                    "message": f"✅ All {len(result['received_steps'])} required steps received{task_id_message}",
                    "details": {
                        "received_steps": result["received_steps"],
                        "conditional_steps": result["received_conditional_steps"],
                        "duration": f"{result['duration']:.2f}s",
                        "task_id_tracking": task_tracking,
                    },
                }
            else:
                return {
                    "success": False,
                    "message": f"❌ Missing {len(result['missing_required_steps'])} required steps{task_id_message}",
                    "details": {
                        "missing_steps": result["missing_required_steps"],
                        "received_steps": result["received_steps"],
                        "errors": result["errors"],
                        "task_id_tracking": task_tracking,
                    },
                }

        return {"success": False, "message": "Unknown custom handler", "details": {}}


# Module registration
def get_module_tests() -> List[QATestCase]:
    """Get all streaming verification tests for registration."""
    return StreamingVerificationModule.get_streaming_verification_tests()
