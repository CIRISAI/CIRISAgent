"""
H3ERE Pipeline Streaming Verification Module - Fixed Version.

This module verifies that all 11 H3ERE pipeline steps are properly streaming
via Server-Sent Events (SSE) to the reasoning-stream endpoint.
"""

import json
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import requests

from ..config import QAConfig, QAModule, QATestCase


class StreamingVerificationModule:
    """Verify all 11 H3ERE pipeline steps are streaming correctly."""

    # All required steps in the H3ERE pipeline
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
        task_ids_seen: Set[str] = set()
        task_id_issues: List[str] = []
        thoughts_without_task_id = 0
        thoughts_with_task_id = 0

        # Shared state for thread communication
        stream_connected = threading.Event()
        stream_error = threading.Event()

        def monitor_stream():
            """Monitor SSE stream in a separate thread."""
            nonlocal thoughts_without_task_id, thoughts_with_task_id

            try:
                headers = {"Authorization": f"Bearer {token}", "Accept": "text/event-stream"}

                response = requests.get(
                    f"{base_url}/v1/system/runtime/reasoning-stream", headers=headers, stream=True, timeout=5
                )

                if response.status_code != 200:
                    errors.append(f"Stream connection failed: {response.status_code}")
                    stream_error.set()
                    return

                stream_connected.set()

                # Parse SSE stream
                for line in response.iter_lines():
                    if not line:
                        continue

                    line = line.decode("utf-8") if isinstance(line, bytes) else line

                    # Only process data lines
                    if line.startswith("data:"):
                        try:
                            data = json.loads(line[6:])

                            # Check both updated_thoughts and new_thoughts
                            all_thoughts = data.get("updated_thoughts", []) + data.get("new_thoughts", [])

                            for thought in all_thoughts:
                                thought_id = thought.get("thought_id")
                                task_id = thought.get("task_id")
                                step = thought.get("current_step")

                                if step:
                                    received_steps.add(step)
                                    step_details.append(
                                        {
                                            "step": step,
                                            "thought_id": thought_id,
                                            "task_id": task_id,
                                            "timestamp": datetime.now().isoformat(),
                                        }
                                    )

                                # Track task_id presence
                                if task_id:
                                    task_ids_seen.add(task_id)
                                    thoughts_with_task_id += 1
                                else:
                                    thoughts_without_task_id += 1
                                    if thought_id and step:
                                        task_id_issues.append(
                                            f"Missing task_id for thought {thought_id} at step {step}"
                                        )

                            # Also check step_summaries for completed steps
                            for summary in data.get("step_summaries", []):
                                step_point = summary.get("step_point")
                                completed = summary.get("completed_count", 0)
                                processing = summary.get("processing_count", 0)

                                if step_point and (completed > 0 or processing > 0):
                                    received_steps.add(step_point)

                        except json.JSONDecodeError:
                            pass  # Ignore parse errors
                        except Exception:
                            pass  # Ignore other errors in processing

            except Exception as e:
                errors.append(f"Stream error: {e}")
                stream_error.set()

        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_stream, daemon=True)
        monitor_thread.start()

        # Wait for stream connection
        if not stream_connected.wait(timeout=3) and not stream_error.is_set():
            errors.append("Stream connection timeout")
            return {
                "success": False,
                "error": "Failed to connect to SSE stream",
                "received_steps": [],
                "missing_required_steps": list(StreamingVerificationModule.EXPECTED_STEPS),
                "task_id_tracking": {"task_ids_seen": 0, "issues": ["Stream connection failed"]},
            }

        # Short delay to ensure stream is ready
        time.sleep(1)

        # Create a task to trigger pipeline
        def create_task():
            try:
                response = requests.post(
                    f"{base_url}/v1/agent/interact",
                    headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json={"message": "Test H3ERE pipeline streaming verification"},
                    timeout=10,
                )
                if response.status_code != 200:
                    errors.append(f"Task creation failed: {response.status_code}")
            except requests.exceptions.Timeout:
                pass  # Expected - task processing may timeout
            except Exception as e:
                errors.append(f"Task creation error: {e}")

        # Create task in background
        task_thread = threading.Thread(target=create_task, daemon=True)
        task_thread.start()

        # Wait for steps to be received
        last_count = 0
        no_progress_time = 0

        while time.time() - start_time < timeout:
            current_count = len(received_steps)

            # Check if we have all required steps
            if current_count >= len(StreamingVerificationModule.EXPECTED_STEPS):
                break

            # Check for progress
            if current_count > last_count:
                last_count = current_count
                no_progress_time = 0
            else:
                no_progress_time += 0.5
                # Stop if no progress for 5 seconds
                if no_progress_time > 5:
                    break

            time.sleep(0.5)

        # Analyze results
        missing_required = StreamingVerificationModule.EXPECTED_STEPS - received_steps
        unexpected_steps = (
            received_steps - StreamingVerificationModule.EXPECTED_STEPS - StreamingVerificationModule.CONDITIONAL_STEPS
        )
        received_conditional = received_steps & StreamingVerificationModule.CONDITIONAL_STEPS

        # Determine success
        all_steps_received = len(missing_required) == 0
        task_id_ok = len(task_ids_seen) > 0 and thoughts_without_task_id == 0

        return {
            "success": all_steps_received and task_id_ok,
            "received_steps": sorted(list(received_steps)),
            "missing_required_steps": sorted(list(missing_required)),
            "received_conditional_steps": sorted(list(received_conditional)),
            "unexpected_steps": sorted(list(unexpected_steps)),
            "total_steps_received": len(received_steps),
            "expected_steps_count": len(StreamingVerificationModule.EXPECTED_STEPS),
            "step_details": step_details[-20:],  # Last 20 events
            "errors": errors,
            "duration": time.time() - start_time,
            "task_id_tracking": {
                "task_ids_seen": len(task_ids_seen),
                "thoughts_with_task_id": thoughts_with_task_id,
                "thoughts_without_task_id": thoughts_without_task_id,
                "issues": task_id_issues[:10],  # First 10 issues
                "all_have_task_id": thoughts_without_task_id == 0,
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
                method="CUSTOM",
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

            # Build status message
            if result["success"]:
                message = f"✅ All {len(result['received_steps'])} required steps received"
                if task_tracking["all_have_task_id"]:
                    message += f"\n✅ Task ID propagation working ({task_tracking['task_ids_seen']} unique IDs)"
                return {
                    "success": True,
                    "message": message,
                    "details": {
                        "received_steps": result["received_steps"],
                        "conditional_steps": result["received_conditional_steps"],
                        "duration": f"{result['duration']:.2f}s",
                        "task_id_tracking": task_tracking,
                    },
                }
            else:
                message_parts = []
                if result["missing_required_steps"]:
                    message_parts.append(f"Missing {len(result['missing_required_steps'])} required steps")
                if not task_tracking.get("all_have_task_id", True):
                    message_parts.append(f"{task_tracking['thoughts_without_task_id']} thoughts missing task_id")

                return {
                    "success": False,
                    "message": "❌ " + " and ".join(message_parts),
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
