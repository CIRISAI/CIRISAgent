"""
Base test module with SSE monitoring for task completion.

All test modules should inherit from BaseTestModule to get:
- SSE-based task completion monitoring
- Proper submit_message → wait for TASK_COMPLETE → get history flow
- Audit validation helpers
- Transparent decoding of Mock LLM packaged responses

This prevents the updated_info_available flag from being set between tests,
which would trigger bypass conscience PONDER retries.
"""

import asyncio
import base64
import json
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from rich.console import Console

from .filter_test_helper import FilterTestHelper

# Mock LLM response prefix for packaged responses
MOCK_RESPONSE_PREFIX = "CIRIS_MOCK_"


@dataclass
class MockLLMResponse:
    """Decoded response from Mock LLM packaged format."""

    action: str  # e.g., "MEMORIZE", "RECALL", "SPEAK"
    status: str  # e.g., "success", "error", "not_found"
    payload: Dict[str, Any]
    message: str
    raw: str  # Original encoded string


@dataclass
class InteractResult:
    """Result from _interact with task_id for audit validation."""

    response: str
    task_id: Optional[str]
    decoded: Optional[MockLLMResponse] = None  # Decoded Mock LLM response if applicable


class BaseTestModule:
    """Base class for test modules with SSE monitoring.

    Provides:
    - SSE monitoring for TASK_COMPLETE detection
    - _interact() that waits for task completion before returning
    - Audit validation helpers
    """

    def __init__(
        self,
        client: Any,
        console: Console,
        fail_fast: bool = True,
        test_timeout: float = 30.0,
    ):
        """Initialize base test module.

        Args:
            client: CIRISClient instance
            console: Rich console for output
            fail_fast: Exit on first test failure (default True)
            test_timeout: Timeout for individual test interactions (default 30s)
        """
        self.client = client
        self.console = console
        self.results: List[Dict] = []
        self.sse_helper: Optional[FilterTestHelper] = None
        self.audit_entries_validated: Dict[str, bool] = {}
        self.fail_fast = fail_fast
        self.test_timeout = test_timeout

    def _start_sse_monitoring(self) -> None:
        """Start SSE monitoring for task completion tracking."""
        try:
            transport = getattr(self.client, "_transport", None)
            base_url = getattr(transport, "base_url", None) if transport else None
            if not base_url:
                base_url = "http://localhost:8080"

            token = getattr(transport, "api_key", None) if transport else None

            self.console.print(
                f"  [dim]SSE config: base_url={base_url}, token={'present' if token else 'MISSING'}[/dim]"
            )

            if token:
                self.sse_helper = FilterTestHelper(str(base_url), token, verbose=False)
                self.sse_helper.start_monitoring()
                self.console.print("  [dim]SSE monitoring started[/dim]")
            else:
                self.console.print("  [yellow]Warning: No auth token for SSE monitoring[/yellow]")
                self.sse_helper = None
        except Exception as e:
            self.console.print(f"  [yellow]Warning: SSE monitoring failed: {e}[/yellow]")
            self.console.print(f"  [dim]{traceback.format_exc()[:200]}[/dim]")
            self.sse_helper = None

    def _stop_sse_monitoring(self) -> None:
        """Stop SSE monitoring."""
        if self.sse_helper:
            self.sse_helper.stop_monitoring()
            self.console.print("  [dim]SSE monitoring stopped[/dim]")

    def _decode_mock_response(self, content: str) -> Optional[MockLLMResponse]:
        """Decode a Mock LLM packaged response.

        Format: CIRIS_MOCK_<ACTION>:<base64_json_payload>

        Args:
            content: The response content to decode

        Returns:
            MockLLMResponse if valid packaged response, None otherwise
        """
        if not content or not content.startswith(MOCK_RESPONSE_PREFIX):
            return None

        try:
            # Extract action and payload
            rest = content[len(MOCK_RESPONSE_PREFIX) :]
            if ":" not in rest:
                return None

            action, b64_payload = rest.split(":", 1)

            # Decode base64
            json_str = base64.b64decode(b64_payload.encode("ascii")).decode("utf-8")
            data = json.loads(json_str)

            return MockLLMResponse(
                action=action.upper(),
                status=data.get("status", "unknown"),
                payload=data.get("payload", {}),
                message=data.get("message", ""),
                raw=content,
            )

        except Exception:
            return None

    def _find_packaged_response(self, content: str) -> Optional[MockLLMResponse]:
        """Find and decode a packaged response anywhere in the content.

        The packaged response may be embedded in larger content.

        Args:
            content: The full response content

        Returns:
            MockLLMResponse if found and decoded, None otherwise
        """
        if not content:
            return None

        # Find the CIRIS_MOCK_ prefix
        idx = content.find(MOCK_RESPONSE_PREFIX)
        if idx == -1:
            return None

        # Extract from prefix to end of line or end of content
        start = idx
        end = content.find("\n", start)
        if end == -1:
            end = len(content)

        packaged_content = content[start:end].strip()
        return self._decode_mock_response(packaged_content)

    async def _interact(self, message: str, timeout: Optional[float] = None) -> InteractResult:
        """Send a message and wait for TASK_COMPLETE via SSE.

        Args:
            message: The message to send
            timeout: Max seconds to wait for TASK_COMPLETE (defaults to self.test_timeout)

        Returns:
            InteractResult with response text and task_id
        """
        # Use configured test_timeout if not specified
        if timeout is None:
            timeout = self.test_timeout
        # Capture the most recent agent message BEFORE submitting
        last_agent_msg_content = None
        try:
            pre_history = await self.client.agent.get_history(limit=5)
            for msg in pre_history.messages:
                if msg.is_agent:
                    last_agent_msg_content = msg.content
                    break
        except Exception:
            pass  # If history fails, continue anyway

        # Reset task complete tracking
        if self.sse_helper:
            self.sse_helper.task_complete_seen = False
            self.sse_helper.completed_tasks.clear()

        # Submit message (returns immediately)
        submission = await self.client.agent.submit_message(message)
        if not submission.accepted:
            raise ValueError(f"Message rejected: {submission.rejection_reason}")

        task_id = submission.task_id

        # Wait for any action to complete via SSE
        if self.sse_helper:
            completed = self._wait_for_task_action(timeout=timeout)
            if not completed:
                self.console.print(f"    [yellow]TASK_COMPLETE not seen in {timeout}s[/yellow]")
        else:
            await asyncio.sleep(3.0)

        # Poll history for a NEW agent message (different from pre-submission)
        response = await self._poll_for_new_response(last_agent_msg_content, timeout=5.0)
        if response:
            # Try to decode packaged Mock LLM response
            decoded = self._find_packaged_response(response)
            return InteractResult(response=response, task_id=task_id, decoded=decoded)

        raise ValueError("No new agent response found in history")

    async def _poll_for_new_response(self, last_content: Optional[str], timeout: float = 5.0) -> Optional[str]:
        """Poll history until we see a NEW agent response.

        Args:
            last_content: The content of the last agent message before our submission
            timeout: Max seconds to poll

        Returns:
            New response content, or None if timeout
        """
        start_time = time.time()
        poll_interval = 0.5

        while time.time() - start_time < timeout:
            try:
                history = await self.client.agent.get_history(limit=5)
                for msg in history.messages:
                    if msg.is_agent:
                        # If no previous message, any agent message is new
                        if last_content is None:
                            return msg.content
                        # If content is different, this is our new response
                        if msg.content != last_content:
                            return msg.content
                        break  # Most recent agent message is still the old one
            except Exception:
                pass

            await asyncio.sleep(poll_interval)

        # Timeout - return the most recent message anyway (fallback)
        try:
            history = await self.client.agent.get_history(limit=5)
            for msg in history.messages:
                if msg.is_agent:
                    return msg.content
        except Exception:
            pass

        return None

    def _wait_for_task_action(self, timeout: float = 30.0) -> bool:
        """Wait for any action to complete via SSE.

        Returns:
            True if TASK_COMPLETE seen or any action completed, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check for TASK_COMPLETE action
            if getattr(self.sse_helper, "task_complete_seen", False):
                return True

            # Check if any action completed (by thought_id)
            completed_tasks = getattr(self.sse_helper, "completed_tasks", set())
            if len(completed_tasks) > 0:
                return True

            time.sleep(0.1)

        return False

    async def _interact_simple(self, message: str, timeout: float = 30.0) -> str:
        """Simplified interact that just returns the response string.

        For packaged responses, returns the human-readable message from the payload.
        For non-packaged responses, returns the raw response.

        Args:
            message: The message to send
            timeout: Max seconds to wait

        Returns:
            Response string (decoded if packaged)
        """
        result = await self._interact(message, timeout)

        # If we have a decoded packaged response, return useful info
        if result.decoded:
            # Return a formatted string with action, status, and payload info
            decoded = result.decoded
            payload = decoded.payload

            # Format based on action type for test assertions
            if decoded.action == "MEMORIZE":
                node_id = payload.get("node_id", "unknown")
                scope = payload.get("scope", "LOCAL")
                return f"[MEMORIZE] status={decoded.status} node_id={node_id} scope={scope}"
            elif decoded.action == "RECALL":
                query = payload.get("query", "")
                value = payload.get("value", "")
                if decoded.status == "not_found":
                    return f"[RECALL] status=not_found query={query}"
                return f"[RECALL] status={decoded.status} query={query} value={value}"
            elif decoded.action == "FORGET":
                node_id = payload.get("node_id", "unknown")
                return f"[FORGET] status={decoded.status} node_id={node_id}"
            elif decoded.action == "TOOL":
                tool_name = payload.get("tool_name", "unknown")
                return f"[TOOL] status={decoded.status} tool={tool_name}"
            elif decoded.action == "OBSERVE":
                channel = payload.get("channel", "unknown")
                return f"[OBSERVE] status={decoded.status} channel={channel}"
            elif decoded.action == "PONDER":
                return f"[PONDER] status={decoded.status} insights={payload.get('insights', '')}"
            elif decoded.action == "DEFER":
                return f"[DEFER] status={decoded.status} reason={payload.get('reason', '')}"
            elif decoded.action == "REJECT":
                return f"[REJECT] status={decoded.status} reason={payload.get('reason', '')}"
            elif decoded.action == "SPEAK":
                return f"[SPEAK] status={decoded.status} content={payload.get('content', '')}"
            elif decoded.action == "TASK_COMPLETE":
                return f"[TASK_COMPLETE] status={decoded.status}"
            else:
                return f"[{decoded.action}] status={decoded.status} message={decoded.message}"

        return result.response

    def get_decoded_payload(self, result: InteractResult) -> Optional[Dict[str, Any]]:
        """Get the payload from a decoded Mock LLM response.

        Args:
            result: The InteractResult from _interact()

        Returns:
            Payload dict if decoded, None otherwise
        """
        if result.decoded:
            return result.decoded.payload
        return None

    def _wait_for_task_complete(self, timeout: float = 30.0) -> bool:
        """Wait for TASK_COMPLETE action in SSE stream.

        Returns:
            True if TASK_COMPLETE seen, False if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if getattr(self.sse_helper, "task_complete_seen", False):
                return True
            time.sleep(0.1)

        return False

    async def _validate_audit_entry(self, task_id: str, expected_action: str) -> bool:
        """Validate audit entry exists for handler action.

        Args:
            task_id: The task ID from the interaction
            expected_action: Expected action type (e.g., 'speak', 'memorize')

        Returns:
            True if valid audit entry found
        """
        audit_db_path = Path("data/ciris_audit.db")
        if not audit_db_path.exists():
            self.console.print(f"    [yellow]Audit DB not found[/yellow]")
            return False

        try:
            import sqlite3

            conn = sqlite3.connect(str(audit_db_path))
            cur = conn.cursor()

            cur.execute(
                """
                SELECT event_type, event_payload, event_summary
                FROM audit_log
                WHERE event_payload LIKE ?
                ORDER BY entry_id DESC
                LIMIT 10
                """,
                (f"%{task_id}%",),
            )

            rows = cur.fetchall()
            conn.close()

            if not rows:
                return False

            for event_type, payload, summary in rows:
                if event_type.lower() == expected_action.lower():
                    try:
                        payload_data = json.loads(payload) if payload else {}
                        has_thought_id = bool(payload_data.get("thought_id"))
                        has_task_id = bool(payload_data.get("task_id"))
                        has_handler_name = bool(payload_data.get("handler_name"))
                        has_action_type = payload_data.get("action_type") == expected_action.lower()

                        if has_thought_id and has_task_id and has_handler_name and has_action_type:
                            return True
                    except json.JSONDecodeError:
                        pass

            return False

        except Exception as e:
            self.console.print(f"    [yellow]Audit validation error: {e}[/yellow]")
            return False

    def _record_result(self, test_name: str, passed: bool, error: str = None) -> None:
        """Record a test result.

        Args:
            test_name: Name of the test
            passed: Whether the test passed
            error: Error message if failed
        """
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({"test": test_name, "status": status, "error": error})
        if passed:
            self.console.print(f"  {status} {test_name}")
        else:
            self.console.print(f"  {status} {test_name}: {error}")
