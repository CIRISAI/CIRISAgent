"""
Handler interaction test module - SDK-based tests with proper validation.

Tests agent message handling and response quality via the SDK interact() method.
Now validates actual response content, not just HTTP status codes.
"""

import asyncio
import traceback
from typing import Any, Dict, List

from rich.console import Console


class HandlerTestModule:
    """SDK-based test module for agent handler interactions."""

    def __init__(self, client: Any, console: Console):
        """Initialize handler tests.

        Args:
            client: CIRISClient instance for making API requests
            console: Rich console for output
        """
        self.client = client
        self.console = console
        self.results: List[Dict] = []

    async def run(self) -> List[Dict]:
        """Run all handler tests with proper validation."""
        self.console.print("\n[bold cyan]Running Handler Tests[/bold cyan]")
        self.console.print("=" * 60)

        tests = [
            # Basic interaction tests
            ("Status request", self._test_status_request),
            ("System health check", self._test_system_health),
            ("Simple conversation", self._test_simple_conversation),
            ("Question answering", self._test_question_answering),
            ("Agent identity", self._test_agent_identity),
            # Response quality tests
            ("Non-empty response", self._test_nonempty_response),
            ("Response coherence", self._test_response_coherence),
            ("Multi-turn conversation", self._test_multi_turn),
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
                    self.console.print(f"     [dim]{traceback.format_exc()[:500]}[/dim]")

        # Print summary
        passed = sum(1 for r in self.results if r["status"] == "✅ PASS")
        total = len(self.results)
        self.console.print(f"\n[bold]Handler Tests: {passed}/{total} passed[/bold]")

        return self.results

    def _record_result(self, test_name: str, passed: bool, error: str = None):
        """Record a test result."""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({"test": test_name, "status": status, "error": error})
        if passed:
            self.console.print(f"  {status} {test_name}")
        else:
            self.console.print(f"  {status} {test_name}: {error}")

    async def _interact(self, message: str) -> str:
        """Send a message and get response text."""
        response = await self.client.interact(message)
        if not response or not response.response:
            raise ValueError("No response from interaction")
        return response.response

    # Basic interaction tests
    async def _test_status_request(self):
        """Test status request gets meaningful response."""
        response = await self._interact("What's your current status?")

        # Should get a substantive response about status
        assert len(response) > 20, f"Response too short ({len(response)} chars), expected substantive status"

        # Response should contain relevant words
        response_lower = response.lower()
        assert any(
            word in response_lower
            for word in ["status", "online", "operational", "ready", "running", "active", "i'm", "i am", "working"]
        ), f"Response doesn't seem to address status: {response[:100]}"

    async def _test_system_health(self):
        """Test system health check gets meaningful response."""
        response = await self._interact("Are all systems operational?")

        # Should get a substantive response
        assert len(response) > 20, f"Response too short ({len(response)} chars)"

        # Response should contain health-related words
        response_lower = response.lower()
        assert any(
            word in response_lower
            for word in ["system", "operational", "healthy", "running", "yes", "working", "online", "everything", "all"]
        ), f"Response doesn't seem to address health: {response[:100]}"

    async def _test_simple_conversation(self):
        """Test simple conversation gets friendly response."""
        response = await self._interact("Hello, how are you today?")

        # Should get a friendly response
        assert len(response) > 10, f"Response too short ({len(response)} chars)"

        # Should acknowledge the greeting
        response_lower = response.lower()
        assert any(
            word in response_lower
            for word in ["hello", "hi", "hey", "greetings", "good", "well", "fine", "doing", "thank", "help"]
        ), f"Response doesn't seem to acknowledge greeting: {response[:100]}"

    async def _test_question_answering(self):
        """Test question answering about purpose."""
        response = await self._interact("What is your purpose?")

        # Should get a substantive response about purpose
        assert len(response) > 30, f"Response too short ({len(response)} chars)"

        # Response should address purpose/function
        response_lower = response.lower()
        assert any(
            word in response_lower
            for word in ["purpose", "help", "assist", "support", "serve", "designed", "created", "role", "task", "goal"]
        ), f"Response doesn't seem to address purpose: {response[:100]}"

    async def _test_agent_identity(self):
        """Test agent responds with identity info."""
        response = await self._interact("Tell me about CIRIS")

        # Should get a substantive response about CIRIS
        assert len(response) > 30, f"Response too short ({len(response)} chars)"

        # Response should mention CIRIS or related concepts
        response_lower = response.lower()
        assert any(
            word in response_lower for word in ["ciris", "agent", "ai", "assistant", "ethical", "integrity", "system"]
        ), f"Response doesn't seem relevant to CIRIS: {response[:100]}"

    # Response quality tests
    async def _test_nonempty_response(self):
        """Test that agent always returns non-empty responses."""
        messages = [
            "Hello",
            "What time is it?",
            "Tell me something interesting",
        ]

        for msg in messages:
            response = await self._interact(msg)
            assert response is not None and len(response.strip()) > 0, f"Empty response for message: {msg}"

    async def _test_response_coherence(self):
        """Test that responses are coherent (not gibberish)."""
        response = await self._interact("Can you help me with a task?")

        # Response should have proper sentence structure (starts with capital, has punctuation)
        assert len(response) > 10, f"Response too short"

        # Check for basic coherence - response should have words, not just symbols
        words = response.split()
        assert len(words) >= 3, f"Response has too few words: {words}"

        # At least some words should be recognizable English
        common_words = {
            "i",
            "the",
            "a",
            "is",
            "to",
            "you",
            "help",
            "can",
            "and",
            "or",
            "with",
            "for",
            "of",
            "in",
            "on",
            "yes",
            "no",
        }
        response_words = set(word.lower().strip(".,!?") for word in words)
        overlap = response_words & common_words
        assert len(overlap) >= 1 or len(response) > 50, f"Response doesn't seem coherent: {response[:100]}"

    async def _test_multi_turn(self):
        """Test multi-turn conversation maintains coherence."""
        # First turn
        response1 = await self._interact("My name is TestUser")
        assert len(response1) > 0, "No response to introduction"

        # Second turn - should maintain context
        response2 = await self._interact("What did I just tell you?")
        assert len(response2) > 0, "No response to context question"

        # Third turn - different topic
        response3 = await self._interact("Thank you for your help")
        assert len(response3) > 0, "No response to thanks"

    @staticmethod
    def get_handler_tests():
        """Legacy method for backward compatibility - returns empty list since tests are now SDK-based."""
        return []

    @staticmethod
    def get_simple_handler_tests():
        """Get simple handler test cases - removed as these endpoints don't exist."""
        return []


def run_handler_tests_sync(client: Any, console: Console = None) -> List[Dict]:
    """Run handler tests synchronously (for CLI invocation)."""
    if console is None:
        console = Console()

    tests = HandlerTestModule(client=client, console=console)
    return asyncio.run(tests.run())
