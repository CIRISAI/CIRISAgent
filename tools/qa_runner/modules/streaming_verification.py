"""
Reasoning Event Streaming Verification Module.

Validates that the 5 simplified reasoning events are properly streaming
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
    """Verify all 5 reasoning events are streaming correctly."""

    # All 5 reasoning events expected (with 60s timeout for wakeup to complete)
    EXPECTED_EVENTS = {
        "snapshot_and_context",
        "dma_results",
        "aspdma_result",
        "conscience_result",
        "action_result",
    }

    @staticmethod
    def verify_streaming_events(base_url: str, token: str, timeout: int = 60) -> Dict[str, Any]:
        """
        Connect to SSE stream and verify reasoning events are received.

        Returns:
            Dict with verification results including received events and any issues.
        """
        received_events: Set[str] = set()
        event_details: List[Dict[str, Any]] = []
        errors: List[str] = []
        start_time = time.time()

        # Track event-specific data
        events_with_audit_data = 0
        events_with_recursive_flag = 0
        recursive_aspdma_count = 0
        recursive_conscience_count = 0

        # Shared state for thread communication
        stream_connected = threading.Event()
        stream_error = threading.Event()

        def monitor_stream():
            """Monitor SSE stream in a separate thread."""
            nonlocal events_with_audit_data, events_with_recursive_flag
            nonlocal recursive_aspdma_count, recursive_conscience_count

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

                            # Extract events from stream update
                            events = data.get("events", [])

                            for event in events:
                                event_type = event.get("event_type")

                                if not event_type:
                                    errors.append("Event missing event_type field")
                                    continue

                                # Track this event type
                                received_events.add(event_type)

                                # Validate event structure
                                event_detail = {
                                    "event_type": event_type,
                                    "thought_id": event.get("thought_id"),
                                    "task_id": event.get("task_id"),
                                    "timestamp": event.get("timestamp"),
                                    "issues": [],
                                }

                                # Event-specific validation
                                if event_type == "snapshot_and_context":
                                    if "system_snapshot" not in event:
                                        event_detail["issues"].append("Missing system_snapshot")
                                    if "context" not in event:
                                        event_detail["issues"].append("Missing context")
                                    if "context_size" not in event:
                                        event_detail["issues"].append("Missing context_size")

                                elif event_type == "dma_results":
                                    # Should have csdma, dsdma, aspdma_options
                                    if (
                                        event.get("csdma") is None
                                        and event.get("dsdma") is None
                                        and event.get("aspdma_options") is None
                                    ):
                                        event_detail["issues"].append("All DMA results are None")

                                elif event_type == "aspdma_result":
                                    if "selected_action" not in event:
                                        event_detail["issues"].append("Missing selected_action")
                                    if "action_rationale" not in event:
                                        event_detail["issues"].append("Missing action_rationale")
                                    if "is_recursive" in event:
                                        events_with_recursive_flag += 1
                                        if event["is_recursive"]:
                                            recursive_aspdma_count += 1

                                elif event_type == "conscience_result":
                                    if "conscience_passed" not in event:
                                        event_detail["issues"].append("Missing conscience_passed")
                                    if "final_action" not in event:
                                        event_detail["issues"].append("Missing final_action")
                                    if "epistemic_data" not in event:
                                        event_detail["issues"].append("Missing epistemic_data")
                                    if "is_recursive" in event:
                                        events_with_recursive_flag += 1
                                        if event["is_recursive"]:
                                            recursive_conscience_count += 1

                                elif event_type == "action_result":
                                    if "action_executed" not in event:
                                        event_detail["issues"].append("Missing action_executed")
                                    if "execution_success" not in event:
                                        event_detail["issues"].append("Missing execution_success")

                                    # Validate audit trail
                                    if event.get("audit_entry_id"):
                                        events_with_audit_data += 1
                                        event_detail["has_audit_trail"] = True
                                        if not event.get("audit_sequence_number"):
                                            event_detail["issues"].append(
                                                "Has audit_entry_id but missing audit_sequence_number"
                                            )
                                        if not event.get("audit_entry_hash"):
                                            event_detail["issues"].append(
                                                "Has audit_entry_id but missing audit_entry_hash"
                                            )

                                event_details.append(event_detail)

                        except json.JSONDecodeError as e:
                            errors.append(f"JSON decode error: {e}")
                        except Exception as e:
                            errors.append(f"Error processing event: {e}")

            except Exception as e:
                errors.append(f"Stream monitoring error: {e}")
                stream_error.set()

        # Start monitoring thread
        monitor_thread = threading.Thread(target=monitor_stream, daemon=True)
        monitor_thread.start()

        # Wait for connection
        if not stream_connected.wait(timeout=3):
            return {
                "success": False,
                "error": "Failed to connect to SSE stream",
                "errors": errors,
            }

        # Wait a bit for events to stream
        time.sleep(1)

        # Trigger a task to generate events
        try:
            requests.post(
                f"{base_url}/v1/agent/interact",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={"message": "Test reasoning event streaming"},
                timeout=10,
            )
        except:
            pass  # Ignore errors, just trying to trigger events

        # Wait for events to stream (60s timeout allows wakeup to complete and actions to dispatch)
        elapsed = 0
        check_interval = 0.5
        while elapsed < timeout and len(received_events) < len(StreamingVerificationModule.EXPECTED_EVENTS):
            time.sleep(check_interval)
            elapsed += check_interval

        duration = time.time() - start_time

        # Check which events we received
        missing_events = StreamingVerificationModule.EXPECTED_EVENTS - received_events

        # Build result
        result = {
            "success": len(missing_events) == 0,  # Require all 5 events
            "received_events": sorted(list(received_events)),
            "missing_events": sorted(list(missing_events)),
            "duration": duration,
            "total_events": len(event_details),
            "events_with_audit_data": events_with_audit_data,
            "events_with_recursive_flag": events_with_recursive_flag,
            "recursive_aspdma_count": recursive_aspdma_count,
            "recursive_conscience_count": recursive_conscience_count,
            "event_details": event_details,
            "errors": errors,
        }

        # Build status message
        if result["success"]:
            message = f"✅ All 5 reasoning events received"
            if events_with_audit_data > 0:
                message += f"\n✅ Audit trail data present in {events_with_audit_data} ACTION_RESULT events"
            if recursive_aspdma_count > 0 or recursive_conscience_count > 0:
                message += (
                    f"\n✅ Recursive events: {recursive_aspdma_count} ASPDMA, {recursive_conscience_count} CONSCIENCE"
                )
            result["message"] = message
        else:
            result["message"] = f"❌ Missing events: {', '.join(missing_events)}"

        return result

    @staticmethod
    def run_custom_test(test: QATestCase, config: QAConfig, token: str) -> Dict[str, Any]:
        """Run streaming verification custom test."""
        if test.custom_handler == "verify_reasoning_stream":
            return StreamingVerificationModule.verify_streaming_events(config.base_url, token, timeout=60)
        else:
            return {
                "success": False,
                "message": f"Unknown custom handler: {test.custom_handler}",
            }

    @staticmethod
    def get_streaming_verification_tests() -> List[QATestCase]:
        """Get streaming verification test cases."""
        return [
            # SSE connectivity test
            QATestCase(
                module=QAModule.STREAMING,
                name="SSE Stream Connectivity",
                method="GET",
                endpoint="/v1/system/runtime/reasoning-stream",
                requires_auth=True,
                expected_status=200,
                timeout=3,
            ),
            # H3ERE Reasoning Event Streaming Verification
            QATestCase(
                module=QAModule.STREAMING,
                name="H3ERE Reasoning Event Stream Verification",
                method="CUSTOM",
                endpoint="",
                requires_auth=True,
                expected_status=200,
                timeout=70,  # 60s for event wait + 10s buffer
                custom_handler="verify_reasoning_stream",
            ),
        ]
