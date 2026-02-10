"""
Handler action test module - Tests all 10 handler verbs with mock LLM.

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
    """Test module for verifying all 10 handler actions execute correctly."""

    def __init__(self, client: Any, console: Console):
        self.client = client
        self.console = console
        self.results: List[Dict] = []

    async def run(self) -> List[Dict]:
        """Run handler action tests for all 10 verbs."""
        self.console.print("\n[bold cyan]Running Handler Action Tests (10 Verbs)[/bold cyan]")
        self.console.print("=" * 60)

        tests = [
            # Directly testable via $command
            ("SPEAK", self._test_speak),
            ("MEMORIZE", self._test_memorize),
            ("RECALL", self._test_recall),
            ("FORGET", self._test_forget),
            ("PONDER", self._test_ponder),
            ("TASK_COMPLETE", self._test_task_complete),
            # Require special conditions
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

    async def _interact(self, message: str) -> str:
        """Send a message and get response."""
        response = await self.client.interact(message)
        if not response or not response.response:
            raise ValueError("No response from interaction")
        return response.response

    # === DIRECTLY TESTABLE HANDLERS ===

    async def _test_speak(self):
        """Test SPEAK handler - direct output to user."""
        response = await self._interact("$speak Handler test message")
        assert response is not None and len(response) > 0, "No SPEAK response"

    async def _test_memorize(self):
        """Test MEMORIZE handler - store to memory graph."""
        response = await self._interact("$memorize handler_test/mem_key CONFIG LOCAL value=mem_value")
        assert response is not None and len(response) > 0, "No MEMORIZE response"

    async def _test_recall(self):
        """Test RECALL handler - query memory graph."""
        response = await self._interact("$recall handler_test/mem_key CONFIG LOCAL")
        assert response is not None and len(response) > 0, "No RECALL response"

    async def _test_forget(self):
        """Test FORGET handler - remove from memory graph."""
        response = await self._interact("$forget handler_test/mem_key CONFIG LOCAL")
        assert response is not None and len(response) > 0, "No FORGET response"

    async def _test_ponder(self):
        """Test PONDER handler - deeper thinking."""
        response = await self._interact("$ponder What is the meaning of this test?")
        assert response is not None and len(response) > 0, "No PONDER response"

    async def _test_task_complete(self):
        """Test TASK_COMPLETE handler - mark task done."""
        response = await self._interact("$task_complete Test completed successfully")
        assert response is not None and len(response) > 0, "No TASK_COMPLETE response"

    # === HANDLERS REQUIRING SPECIAL CONDITIONS ===

    async def _test_tool(self):
        """Test TOOL handler - execute external tool."""
        # Use self_help tool - it's always available and requires no params
        response = await self._interact("$tool self_help")
        assert response is not None, "No TOOL response"

    async def _test_observe(self):
        """Test OBSERVE handler - fetch channel messages."""
        response = await self._interact("$observe")
        assert response is not None, "No OBSERVE response"

    async def _test_defer(self):
        """Test DEFER handler - defer to Wise Authority."""
        response = await self._interact("$defer Need guidance on this")
        assert response is not None, "No DEFER response"

    async def _test_reject(self):
        """Test REJECT handler - reject request."""
        response = await self._interact("$reject This request is not allowed")
        assert response is not None, "No REJECT response"

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
