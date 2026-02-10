"""
Handler action test module - Tests all 10 handler verbs with mock LLM.

Each test validates that the response indicates the CORRECT handler executed,
not just that some response was returned.

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
"""

import asyncio
import traceback
from typing import Any, Dict, List

from rich.console import Console


class HandlerTestModule:
    """Test module for verifying all 10 handler actions execute correctly.

    IMPORTANT: Tests must validate that responses indicate the correct handler
    was executed, not just that any response was returned.
    """

    def __init__(self, client: Any, console: Console):
        self.client = client
        self.console = console
        self.results: List[Dict] = []

    async def run(self) -> List[Dict]:
        """Run handler action tests for all 10 verbs."""
        self.console.print("\n[bold cyan]Running Handler Action Tests (10 Verbs)[/bold cyan]")
        self.console.print("=" * 60)

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

        passed = sum(1 for r in self.results if r["status"] == "✅ PASS")
        total = len(self.results)
        self.console.print(f"\n[bold]Handler Tests: {passed}/{total} passed[/bold]")

        return self.results

    def _record_result(self, test_name: str, passed: bool, error: str = None):
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({"test": test_name, "status": status, "error": error})
        if passed:
            self.console.print(f"  {status} {test_name}")
        else:
            self.console.print(f"  {status} {test_name}: {error}")

    async def _interact(self, message: str, delay_after: float = 5.0) -> str:
        """Send a message and get response.

        Args:
            message: The message to send
            delay_after: Seconds to wait after getting response (allows agent to settle)

        Note: Delay increased to 5s to ensure agent fully processes each command
        before the next one is sent. This prevents test bleeding.
        """
        response = await self.client.interact(message)
        if not response or not response.response:
            raise ValueError("No response from interaction")
        # Wait for agent to fully process before next test
        await asyncio.sleep(delay_after)
        return response.response

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
        response_lower = response.lower()

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
        """Test SPEAK handler - validates response contains the spoken message."""
        test_message = "Handler test message SPEAK123"
        response = await self._interact(f"$speak {test_message}")
        # SPEAK should echo the message or indicate speaking action
        self._validate_response(
            response,
            "SPEAK",
            required_patterns=[test_message, "SPEAK123"],
            forbidden_patterns=["Default response"],
        )

    async def _test_memorize(self):
        """Test MEMORIZE handler - validates memory storage confirmation."""
        response = await self._interact("$memorize qa_handler_test/key123 CONFIG LOCAL value=test_value")
        self._validate_response(
            response,
            "MEMORIZE",
            required_patterns=["memorize", "stored", "memory", "qa_handler_test"],
        )

    async def _test_recall(self):
        """Test RECALL handler - validates memory query response."""
        response = await self._interact("$recall qa_handler_test/key123 CONFIG LOCAL")
        self._validate_response(
            response,
            "RECALL",
            required_patterns=["recall", "memory", "query", "qa_handler_test", "returned", "found"],
        )

    async def _test_forget(self):
        """Test FORGET handler - validates memory removal confirmation."""
        response = await self._interact("$forget qa_handler_test/key123 Cleanup test data")
        self._validate_response(
            response,
            "FORGET",
            required_patterns=["forget", "forgot", "removed", "deleted", "qa_handler_test"],
        )

    async def _test_ponder(self):
        """Test PONDER handler - validates pondering response."""
        response = await self._interact("$ponder What is the purpose of this QA test?", delay_after=3.0)
        self._validate_response(
            response,
            "PONDER",
            required_patterns=["ponder", "thinking", "pondering", "question"],
            forbidden_patterns=["Default response"],
        )

    async def _test_task_complete(self):
        """Test TASK_COMPLETE handler - validates completion confirmation."""
        response = await self._interact("$task_complete QA handler test completed successfully")
        self._validate_response(
            response,
            "TASK_COMPLETE",
            required_patterns=["complete", "completed", "finished", "done", "task"],
        )

    async def _test_tool(self):
        """Test TOOL handler - validates tool execution response."""
        response = await self._interact("$tool self_help", delay_after=3.0)
        self._validate_response(
            response,
            "TOOL",
            required_patterns=["tool", "self_help", "executed", "result"],
            forbidden_patterns=["ponder round", "conscience feedback"],  # Signs of bypass
        )

    async def _test_observe(self):
        """Test OBSERVE handler - validates observation response."""
        response = await self._interact("$observe")
        self._validate_response(
            response,
            "OBSERVE",
            required_patterns=["observe", "observation", "fetched", "messages", "channel"],
        )

    async def _test_defer(self):
        """Test DEFER handler - validates deferral confirmation."""
        response = await self._interact("$defer Need wise authority guidance for this QA test")
        self._validate_response(
            response,
            "DEFER",
            required_patterns=["defer", "deferred", "guidance", "authority", "escalat"],
        )

    async def _test_reject(self):
        """Test REJECT handler - validates rejection confirmation."""
        response = await self._interact("$reject This QA test request should be rejected")
        self._validate_response(
            response,
            "REJECT",
            required_patterns=["reject", "rejected", "denied", "cannot", "refused"],
        )

    @staticmethod
    def get_handler_tests():
        """Legacy method - returns empty list."""
        return []

    @staticmethod
    def get_simple_handler_tests():
        """Legacy method - returns empty list."""
        return []


def run_handler_tests_sync(client: Any, console: Console = None) -> List[Dict]:
    """Run handler tests synchronously."""
    if console is None:
        console = Console()
    tests = HandlerTestModule(client=client, console=console)
    return asyncio.run(tests.run())
