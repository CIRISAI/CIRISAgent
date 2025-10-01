"""
Filter test helper - monitors SSE for TASK_COMPLETE events.

Ensures filter tests wait for task completion before proceeding to next test.
"""

import json
import threading
import time
from typing import Any, Dict, Optional, Set

import requests


class FilterTestHelper:
    """Helper to monitor task completion via SSE for filter tests."""

    def __init__(self, base_url: str, token: str):
        self.base_url = base_url
        self.token = token
        self.completed_tasks: Set[str] = set()
        self.stream_thread: Optional[threading.Thread] = None
        self.should_stop = threading.Event()
        self.stream_error = threading.Event()
        self.stream_connected = threading.Event()

    def start_monitoring(self):
        """Start monitoring SSE stream for task completions."""
        if self.stream_thread and self.stream_thread.is_alive():
            return  # Already monitoring

        self.should_stop.clear()
        self.stream_error.clear()
        self.stream_connected.clear()
        self.stream_thread = threading.Thread(target=self._monitor_stream, daemon=True)
        self.stream_thread.start()

        # Wait for connection
        if not self.stream_connected.wait(timeout=5):
            raise RuntimeError("Failed to connect to SSE stream")

    def stop_monitoring(self):
        """Stop monitoring SSE stream."""
        self.should_stop.set()
        if self.stream_thread:
            self.stream_thread.join(timeout=2)

    def wait_for_task_complete(self, task_id: Optional[str] = None, timeout: float = 30.0) -> bool:
        """
        Wait for a specific task to complete, or any task if task_id is None.

        Args:
            task_id: Specific task ID to wait for, or None to wait for any completion
            timeout: Maximum time to wait in seconds

        Returns:
            True if task completed, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if self.stream_error.is_set():
                return False

            # Check if our specific task completed
            if task_id:
                if task_id in self.completed_tasks:
                    return True
            else:
                # Wait for any task to complete (for tests that don't track task_id)
                if len(self.completed_tasks) > 0:
                    # Clear the set for next test
                    self.completed_tasks.clear()
                    return True

            time.sleep(0.1)

        return False

    def _monitor_stream(self):
        """Monitor SSE stream in background thread."""
        try:
            headers = {"Authorization": f"Bearer {self.token}", "Accept": "text/event-stream"}

            response = requests.get(
                f"{self.base_url}/v1/system/runtime/reasoning-stream",
                headers=headers,
                stream=True,
                timeout=5,
            )

            if response.status_code != 200:
                self.stream_error.set()
                return

            self.stream_connected.set()

            # Parse SSE stream
            for line in response.iter_lines():
                if self.should_stop.is_set():
                    break

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

                            # Look for action_result events with TASK_COMPLETE action
                            if event_type == "action_result":
                                action_executed = event.get("action_executed", "")
                                execution_success = event.get("execution_success", False)

                                # Check if this is a TASK_COMPLETE action that succeeded
                                if "TASK_COMPLETE" in action_executed and execution_success:
                                    task_id = event.get("task_id")
                                    if task_id:
                                        self.completed_tasks.add(task_id)

                    except json.JSONDecodeError:
                        pass
                    except Exception:
                        pass

        except Exception:
            self.stream_error.set()


def wait_for_filter_test_completion(
    base_url: str, token: str, test_name: str, task_id: Optional[str] = None, timeout: float = 30.0
) -> bool:
    """
    Helper function to wait for a filter test to complete.

    Args:
        base_url: API base URL
        token: Authentication token
        test_name: Name of the test (for logging)
        task_id: Optional specific task ID to wait for
        timeout: Maximum time to wait in seconds

    Returns:
        True if task completed, False if timeout
    """
    helper = FilterTestHelper(base_url, token)

    try:
        helper.start_monitoring()

        # Give the test a moment to create the task
        time.sleep(0.5)

        # Wait for completion
        completed = helper.wait_for_task_complete(task_id, timeout)

        return completed

    finally:
        helper.stop_monitoring()
