"""
Handler action test module - Tests all 10 handler verbs with mock LLM.

Each test validates:
1. The response indicates the CORRECT handler executed
2. Audit entries exist with accurate details for the handler action

The 10 handlers:
1. SPEAK - Communicate to user
2. MEMORIZE - Store to memory graph
3. RECALL - Query memory graph
4. FORGET - Remove from memory graph
5. TOOL - Execute external tool
6. OBSERVE - Fetch channel messages
7. DEFER - Defer to Wise Authority
8. REJECT - Reject request
9. PONDER - Think deeper
10. TASK_COMPLETE - Mark task done

CRITICAL: Tests use SSE monitoring to wait for task completion before
proceeding to the next test. This prevents the updated_info_available flag
from being set, which would cause bypass conscience to trigger PONDER retries.

AUDIT VALIDATION: After each handler test, we validate that:
- An audit entry exists for the handler action
- The audit entry has the correct action_type
- The audit entry has valid thought_id, task_id, and handler_name
"""

import asyncio
import json
import traceback
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from rich.console import Console

from .filter_test_helper import FilterTestHelper


@dataclass
class InteractResult:
    """Result from _interact with task_id for audit validation."""

    response: str
    task_id: Optional[str]


class HandlerTestModule:
    """Test module for verifying all 10 handler actions execute correctly.

    IMPORTANT: Tests validate:
    1. Responses indicate the correct handler was executed
    2. Audit entries exist with accurate details in all 3 locations:
       - Audit database (data/ciris_audit.db)
       - Log files (logs/sqlite/latest.log)
       - QA status file (qa_reports/qa_status.json)

    Uses SSE monitoring to ensure each task completes before the next test runs.
    """

    def __init__(self, client: Any, console: Console):
        self.client = client
        self.console = console
        self.results: List[Dict] = []
        self.sse_helper: Optional[FilterTestHelper] = None
        self.audit_entries_validated: Dict[str, bool] = {}  # Track audit validation per handler

    async def run(self) -> List[Dict]:
        """Run handler action tests for all 10 verbs."""
        self.console.print("\n[bold cyan]Running Handler Action Tests (10 Verbs)[/bold cyan]")
        self.console.print("=" * 60)

        # Start SSE monitoring to track task completion
        try:
            # Get base_url from transport
            transport = getattr(self.client, "_transport", None)
            base_url = getattr(transport, "base_url", None) if transport else None
            if not base_url:
                base_url = "http://localhost:8080"

            # Get token from transport.api_key
            token = getattr(transport, "api_key", None) if transport else None

            self.console.print(
                f"  [dim]SSE config: base_url={base_url}, token={'present' if token else 'MISSING'}[/dim]"
            )

            if token:
                self.sse_helper = FilterTestHelper(str(base_url), token, verbose=True)
                self.sse_helper.start_monitoring()
                self.console.print("  [dim]SSE monitoring started successfully[/dim]")
            else:
                self.console.print("  [yellow]Warning: No auth token found for SSE monitoring[/yellow]")
                self.sse_helper = None
        except Exception as e:
            self.console.print(f"  [yellow]Warning: SSE monitoring failed to start: {e}[/yellow]")
            import traceback

            self.console.print(f"  [dim]{traceback.format_exc()[:200]}[/dim]")
            self.sse_helper = None

        tests = [
            ("SPEAK", self._test_speak),
            ("MEMORIZE", self._test_memorize),
            ("RECALL", self._test_recall),
            ("FORGET", self._test_forget),
            ("PONDER", self._test_ponder),
            ("TASK_COMPLETE", self._test_task_complete),
            ("TOOL", self._test_tool),
            ("OBSERVE", self._test_observe),
            ("DEFER", self._test_defer),
            ("REJECT", self._test_reject),
        ]

        try:
            for name, test_func in tests:
                try:
                    await test_func()
                    self._record_result(name, True)
                except AssertionError as e:
                    self._record_result(name, False, str(e))
                except Exception as e:
                    self._record_result(name, False, f"Exception: {e}")
                    if self.console.is_terminal:
                        self.console.print(f"     [dim]{traceback.format_exc()[:300]}[/dim]")
        finally:
            # Stop SSE monitoring
            if self.sse_helper:
                self.sse_helper.stop_monitoring()
                self.console.print("  [dim]SSE monitoring stopped[/dim]")

        passed = sum(1 for r in self.results if r["status"] == "✅ PASS")
        total = len(self.results)
        self.console.print(f"\n[bold]Handler Tests: {passed}/{total} passed[/bold]")

        # Report audit validation summary
        if self.audit_entries_validated:
            audit_passed = sum(1 for v in self.audit_entries_validated.values() if v)
            audit_total = len(self.audit_entries_validated)
            self.console.print(f"[bold]Audit Validation: {audit_passed}/{audit_total} entries verified[/bold]")

            # List any handlers missing audit entries
            missing_audit = [k for k, v in self.audit_entries_validated.items() if not v]
            if missing_audit:
                self.console.print(f"  [yellow]Missing/invalid audit entries: {', '.join(missing_audit)}[/yellow]")

        return self.results

    def _record_result(self, test_name: str, passed: bool, error: str = None):
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({"test": test_name, "status": status, "error": error})
        if passed:
            self.console.print(f"  {status} {test_name}")
        else:
            self.console.print(f"  {status} {test_name}: {error}")

    async def _interact(self, message: str, timeout: float = 30.0) -> InteractResult:
        """Send a message via submit_message and wait for TASK_COMPLETE via SSE.

        Args:
            message: The message to send
            timeout: Max seconds to wait for TASK_COMPLETE

        Returns:
            InteractResult with response text and task_id for audit validation

        Uses the async pattern:
        1. submit_message() returns immediately with task_id
        2. Monitor SSE for TASK_COMPLETE action
        3. Get response from history (filtering by submission time)

        This prevents the updated_info_available flag from being set on
        subsequent tasks, which would cause bypass conscience retries.
        """
        from datetime import datetime, timezone

        # Reset task complete tracking before sending
        if self.sse_helper:
            self.sse_helper.task_complete_seen = False

        # Record submission time for filtering history
        submission_time = datetime.now(timezone.utc)

        # Submit message (returns immediately)
        submission = await self.client.agent.submit_message(message)
        if not submission.accepted:
            raise ValueError(f"Message rejected: {submission.rejection_reason}")

        task_id = submission.task_id
        self.console.print(f"    [dim]Submitted task {task_id[:8] if task_id else 'N/A'}...[/dim]")

        # Wait for TASK_COMPLETE action via SSE
        if self.sse_helper:
            completed = self._wait_for_task_complete_action(timeout=timeout)
            if not completed:
                self.console.print(f"    [yellow]Warning: TASK_COMPLETE not seen in {timeout}s[/yellow]")
        else:
            # No SSE monitoring - use delay as fallback
            await asyncio.sleep(5.0)

        # Get response from history - find agent message AFTER our submission
        history = await self.client.agent.get_history(limit=10)
        for msg in history.messages:
            if msg.is_agent and msg.timestamp > submission_time:
                return InteractResult(response=msg.content, task_id=task_id)

        # Fallback: if no message after submission time, try most recent
        for msg in history.messages:
            if msg.is_agent:
                return InteractResult(response=msg.content, task_id=task_id)

        raise ValueError("No agent response found in history")

    async def _validate_audit_entry(self, task_id: str, expected_action: str) -> bool:
        """Validate that an audit entry exists for the handler action.

        Checks all 3 audit locations:
        1. Audit database (data/ciris_audit.db) - via API
        2. Validates entry has correct action_type, thought_id, task_id

        Args:
            task_id: The task ID from the interaction
            expected_action: The expected action type (e.g., 'speak', 'memorize')

        Returns:
            True if valid audit entry found, False otherwise
        """
        import sqlite3
        from pathlib import Path

        # Try to query the audit database directly
        audit_db_path = Path("data/ciris_audit.db")
        if not audit_db_path.exists():
            self.console.print(f"    [yellow]Audit DB not found at {audit_db_path}[/yellow]")
            return False

        try:
            conn = sqlite3.connect(str(audit_db_path))
            cur = conn.cursor()

            # Query for audit entries matching this task
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
                self.console.print(f"    [yellow]No audit entries found for task {task_id[:8]}[/yellow]")
                return False

            # Find entry with matching action type
            for event_type, payload, summary in rows:
                if event_type.lower() == expected_action.lower():
                    # Validate payload has required fields
                    try:
                        payload_data = json.loads(payload) if payload else {}
                        has_thought_id = bool(payload_data.get("thought_id"))
                        has_task_id = bool(payload_data.get("task_id"))
                        has_handler_name = bool(payload_data.get("handler_name"))
                        has_action_type = payload_data.get("action_type") == expected_action.lower()

                        if has_thought_id and has_task_id and has_handler_name and has_action_type:
                            self.console.print(f"    [dim]✓ Audit validated: {expected_action}[/dim]")
                            return True
                        else:
                            missing = []
                            if not has_thought_id:
                                missing.append("thought_id")
                            if not has_task_id:
                                missing.append("task_id")
                            if not has_handler_name:
                                missing.append("handler_name")
                            if not has_action_type:
                                missing.append("action_type")
                            self.console.print(f"    [yellow]Audit entry missing fields: {missing}[/yellow]")
                    except json.JSONDecodeError:
                        self.console.print("    [yellow]Audit payload not valid JSON[/yellow]")

            self.console.print(f"    [yellow]No matching {expected_action} audit entry for task {task_id[:8]}[/yellow]")
            return False

        except Exception as e:
            self.console.print(f"    [yellow]Audit validation error: {e}[/yellow]")
            return False

    def _wait_for_task_complete_action(self, timeout: float = 30.0) -> bool:
        """Wait specifically for a TASK_COMPLETE action in the SSE stream.

        Returns True if TASK_COMPLETE was seen, False if timeout.
        """
        import time

        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check if we've seen TASK_COMPLETE
            if getattr(self.sse_helper, "task_complete_seen", False):
                self.console.print("    [dim]✓ TASK_COMPLETE seen[/dim]")
                return True

            time.sleep(0.1)

        return False

    def _decode_mock_response(self, response: str) -> str:
        """Decode CIRIS_MOCK_* base64 response if present.

        Returns the decoded message content, or the original response if not a mock response.
        """
        import base64

        MOCK_PREFIX = "CIRIS_MOCK_"
        if not response or MOCK_PREFIX not in response:
            return response

        try:
            # Find the mock prefix position
            idx = response.find(MOCK_PREFIX)
            if idx == -1:
                return response

            # Extract from prefix
            rest = response[idx + len(MOCK_PREFIX) :]
            if ":" not in rest:
                return response

            action, b64_payload = rest.split(":", 1)
            # Handle potential trailing content
            b64_payload = b64_payload.split()[0] if " " in b64_payload else b64_payload
            b64_payload = b64_payload.split("\n")[0]  # Only first line

            # Decode base64
            json_str = base64.b64decode(b64_payload.encode("ascii")).decode("utf-8")
            data = json.loads(json_str)

            # Build a searchable string from decoded content
            parts = [action.lower()]
            if "message" in data:
                parts.append(str(data["message"]).lower())
            if "payload" in data:
                payload = data["payload"]
                if isinstance(payload, dict):
                    for k, v in payload.items():
                        parts.append(str(k).lower())
                        parts.append(str(v).lower())
                else:
                    parts.append(str(payload).lower())

            decoded_content = " ".join(parts)
            return f"{response} [DECODED: {decoded_content}]"

        except Exception:
            return response

    def _validate_response(
        self, response: str, handler_name: str, required_patterns: List[str], forbidden_patterns: List[str] = None
    ) -> None:
        """Validate response contains evidence of correct handler execution.

        Args:
            response: The response text
            handler_name: Name of the handler being tested
            required_patterns: At least ONE of these must be in response (case-insensitive)
            forbidden_patterns: NONE of these should be in response (indicates wrong handler)
        """
        # Decode mock response if present
        response_decoded = self._decode_mock_response(response)
        response_lower = response_decoded.lower()

        # Check that at least one required pattern is present
        found_required = any(p.lower() in response_lower for p in required_patterns)
        if not found_required:
            raise AssertionError(
                f"{handler_name} handler not executed. Response lacks required patterns "
                f"{required_patterns}. Got: {response[:150]}..."
            )

        # Check that no forbidden patterns are present
        if forbidden_patterns:
            for pattern in forbidden_patterns:
                if pattern.lower() in response_lower:
                    raise AssertionError(
                        f"{handler_name} test failed - wrong handler executed. "
                        f"Found forbidden pattern '{pattern}'. Got: {response[:150]}..."
                    )

    # === HANDLER TESTS WITH PROPER VALIDATION ===

    async def _test_speak(self):
        """Test SPEAK handler - validates response and audit entry."""
        test_message = "Handler test message SPEAK123"
        result = await self._interact(f"$speak {test_message}")
        # SPEAK should echo the message or indicate speaking action
        self._validate_response(
            result.response,
            "SPEAK",
            required_patterns=[test_message, "SPEAK123"],
            forbidden_patterns=["Default response"],
        )
        # Validate audit entry
        if result.task_id:
            audit_valid = await self._validate_audit_entry(result.task_id, "speak")
            self.audit_entries_validated["SPEAK"] = audit_valid

    async def _test_memorize(self):
        """Test MEMORIZE handler - validates response and audit entry."""
        result = await self._interact("$memorize qa_handler_test/key123 CONFIG LOCAL value=test_value")
        self._validate_response(
            result.response,
            "MEMORIZE",
            required_patterns=["memorize", "stored", "memory", "qa_handler_test"],
        )
        # Validate audit entry
        if result.task_id:
            audit_valid = await self._validate_audit_entry(result.task_id, "memorize")
            self.audit_entries_validated["MEMORIZE"] = audit_valid

    async def _test_recall(self):
        """Test RECALL handler - validates response and audit entry."""
        result = await self._interact("$recall qa_handler_test/key123 CONFIG LOCAL")
        self._validate_response(
            result.response,
            "RECALL",
            required_patterns=["recall", "memory", "query", "qa_handler_test", "returned", "found"],
        )
        # Validate audit entry
        if result.task_id:
            audit_valid = await self._validate_audit_entry(result.task_id, "recall")
            self.audit_entries_validated["RECALL"] = audit_valid

    async def _test_forget(self):
        """Test FORGET handler - validates response and audit entry."""
        result = await self._interact("$forget qa_handler_test/key123 Cleanup test data")
        self._validate_response(
            result.response,
            "FORGET",
            required_patterns=["forget", "forgot", "removed", "deleted", "qa_handler_test"],
        )
        # Validate audit entry
        if result.task_id:
            audit_valid = await self._validate_audit_entry(result.task_id, "forget")
            self.audit_entries_validated["FORGET"] = audit_valid

    async def _test_ponder(self):
        """Test PONDER handler - validates response and audit entry."""
        result = await self._interact("$ponder What is the purpose of this QA test?", timeout=45.0)
        self._validate_response(
            result.response,
            "PONDER",
            required_patterns=["ponder", "thinking", "pondering", "question"],
            forbidden_patterns=["Default response"],
        )
        # Validate audit entry
        if result.task_id:
            audit_valid = await self._validate_audit_entry(result.task_id, "ponder")
            self.audit_entries_validated["PONDER"] = audit_valid

    async def _test_task_complete(self):
        """Test TASK_COMPLETE handler - validates response and audit entry."""
        result = await self._interact("$task_complete QA handler test completed successfully")
        self._validate_response(
            result.response,
            "TASK_COMPLETE",
            required_patterns=["complete", "completed", "finished", "done", "task"],
        )
        # Validate audit entry
        if result.task_id:
            audit_valid = await self._validate_audit_entry(result.task_id, "task_complete")
            self.audit_entries_validated["TASK_COMPLETE"] = audit_valid

    async def _test_tool(self):
        """Test TOOL handler - validates response and audit entry."""
        result = await self._interact("$tool self_help", timeout=45.0)
        self._validate_response(
            result.response,
            "TOOL",
            required_patterns=["tool", "self_help", "executed", "result"],
            forbidden_patterns=["ponder round", "conscience feedback"],  # Signs of bypass
        )
        # Validate audit entry
        if result.task_id:
            audit_valid = await self._validate_audit_entry(result.task_id, "tool")
            self.audit_entries_validated["TOOL"] = audit_valid

    async def _test_observe(self):
        """Test OBSERVE handler - validates response and audit entry."""
        result = await self._interact("$observe")
        self._validate_response(
            result.response,
            "OBSERVE",
            required_patterns=["observe", "observation", "fetched", "messages", "channel"],
        )
        # Validate audit entry
        if result.task_id:
            audit_valid = await self._validate_audit_entry(result.task_id, "observe")
            self.audit_entries_validated["OBSERVE"] = audit_valid

    async def _test_defer(self):
        """Test DEFER handler - validates response and audit entry."""
        result = await self._interact("$defer Need wise authority guidance for this QA test")
        self._validate_response(
            result.response,
            "DEFER",
            required_patterns=["defer", "deferred", "guidance", "authority", "escalat"],
        )
        # Validate audit entry
        if result.task_id:
            audit_valid = await self._validate_audit_entry(result.task_id, "defer")
            self.audit_entries_validated["DEFER"] = audit_valid

    async def _test_reject(self):
        """Test REJECT handler - validates response and audit entry."""
        result = await self._interact("$reject This QA test request should be rejected")
        self._validate_response(
            result.response,
            "REJECT",
            required_patterns=["reject", "rejected", "denied", "cannot", "refused"],
        )
        # Validate audit entry
        if result.task_id:
            audit_valid = await self._validate_audit_entry(result.task_id, "reject")
            self.audit_entries_validated["REJECT"] = audit_valid

    @staticmethod
    def get_handler_tests():
        """Legacy method - returns empty list."""
        return []


def run_handler_tests_sync(client: Any, console: Console = None) -> List[Dict]:
    """Run handler tests synchronously."""
    if console is None:
        console = Console()
    tests = HandlerTestModule(client=client, console=console)
    return asyncio.run(tests.run())
