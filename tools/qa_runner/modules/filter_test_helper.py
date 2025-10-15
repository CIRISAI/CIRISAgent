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

    def __init__(self, base_url: str, token: str, verbose: bool = False):
        self.base_url = base_url
        self.token = token
        self.verbose = verbose
        self.completed_tasks: Set[str] = set()
        self.stream_thread: Optional[threading.Thread] = None
        self.should_stop = threading.Event()
        self.stream_error = threading.Event()
        self.stream_connected = threading.Event()
        self.current_response: Optional[Any] = None  # Track response for cleanup

    def start_monitoring(self) -> None:
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

    def stop_monitoring(self) -> None:
        """Stop monitoring SSE stream."""
        self.should_stop.set()

        # Close the response object to prevent connection leaks
        if self.current_response:
            try:
                self.current_response.close()
            except Exception:
                pass  # Ignore errors during cleanup
            self.current_response = None

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

    def _monitor_stream(self) -> None:
        """Monitor SSE stream in background thread with auto-reconnect."""
        retry_count = 0
        max_retries = 10

        while not self.should_stop.is_set() and retry_count < max_retries:
            try:
                headers = {"Authorization": f"Bearer {self.token}", "Accept": "text/event-stream"}

                response = requests.get(
                    f"{self.base_url}/v1/system/runtime/reasoning-stream",
                    headers=headers,
                    stream=True,
                    timeout=None,  # No timeout for streaming
                )

                if response.status_code != 200:
                    # Close failed response
                    try:
                        response.close()
                    except Exception:
                        pass
                    retry_count += 1
                    time.sleep(1)
                    continue

                # Store response for cleanup
                self.current_response = response

                self.stream_connected.set()
                retry_count = 0  # Reset on successful connection

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

                                # Look for action_result events (ANY action completes the thought)
                                if event_type == "action_result":
                                    action_executed = event.get("action_executed", "")
                                    execution_success = event.get("execution_success", False)
                                    task_id = event.get("task_id", "unknown")
                                    thought_id = event.get("thought_id", "unknown")

                                    if self.verbose:
                                        print(
                                            f"[SSE] ACTION_RESULT: task={task_id[:8]}, thought={thought_id[:8]}, "
                                            f"action={action_executed}, success={execution_success}"
                                        )

                                    # ANY action_result that succeeded indicates thought completion
                                    # (speak, memorize, recall, task_complete, etc. all complete the thought)
                                    if execution_success:
                                        if self.verbose:
                                            print(
                                                f"[SSE] ✅ Action completed: {action_executed} for thought {thought_id[:8]}"
                                            )
                                        # Use thought_id as the completion marker (not task_id which may be None)
                                        if thought_id and thought_id != "unknown":
                                            self.completed_tasks.add(thought_id)

                        except json.JSONDecodeError:
                            pass
                        except Exception:
                            pass

            except (requests.exceptions.RequestException, requests.exceptions.ChunkedEncodingError) as e:
                # Connection lost - close old response and retry
                if self.current_response:
                    try:
                        self.current_response.close()
                    except Exception:
                        pass
                    self.current_response = None

                if self.verbose:
                    print(f"[SSE] Connection lost, reconnecting... ({e})")
                self.stream_connected.clear()
                retry_count += 1
                time.sleep(1)
                continue
            except Exception as e:
                # Close response on any error
                if self.current_response:
                    try:
                        self.current_response.close()
                    except Exception:
                        pass
                    self.current_response = None

                if self.verbose:
                    print(f"[SSE] Error: {e}")
                self.stream_error.set()
                break

        # Cleanup when loop exits
        if self.current_response:
            try:
                self.current_response.close()
            except Exception:
                pass
            self.current_response = None


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
