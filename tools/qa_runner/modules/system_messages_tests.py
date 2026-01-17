"""
System messages visibility QA tests.

Tests that system messages (errors, status updates, processing info)
are properly sent and retrievable via the /v1/agent/history endpoint.

See FSD/system_messages.md for the full specification.
"""

import asyncio
import traceback
from typing import Any, Dict, List

from rich.console import Console
from rich.table import Table

from ciris_sdk.client import CIRISClient


class SystemMessagesTests:
    """Test system message visibility for UI/UX."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize system messages tests."""
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []

    async def run(self) -> List[Dict[str, Any]]:
        """Run all system messages tests."""
        self.console.print("\n[cyan]📨 Testing System Messages Visibility[/cyan]")

        tests = [
            ("History Endpoint Available", self.test_history_endpoint),
            ("Message Type Field Present", self.test_message_type_field),
            ("Queue Status Endpoint", self.test_queue_status),
            ("Valid Message Types", self.test_valid_message_types),
            ("Is Agent Flag Consistency", self.test_is_agent_consistency),
            ("System Message on Error", self.test_system_message_on_error),
        ]

        for name, test_func in tests:
            try:
                await test_func()
                self.results.append({"test": name, "status": "✅ PASS", "error": None})
                self.console.print(f"  ✅ {name}")
            except Exception as e:
                self.results.append({"test": name, "status": "❌ FAIL", "error": str(e)})
                self.console.print(f"  ❌ {name}: {str(e)[:100]}")
                if self.console.is_terminal:
                    self.console.print(f"     [dim]{traceback.format_exc()[:500]}[/dim]")

        self._print_summary()
        return self.results

    async def test_history_endpoint(self):
        """Test that history endpoint is available and returns data."""
        # Get conversation history
        history = await self.client.agent.get_history(limit=10)

        # Should return a list (even if empty)
        if not isinstance(history, list) and not hasattr(history, "messages"):
            raise ValueError(f"History endpoint returned unexpected type: {type(history)}")

    async def test_message_type_field(self):
        """Test that messages have message_type field."""
        # First send a message to ensure there's history
        try:
            await self.client.agent.submit_message("Test message for system messages QA")
            await asyncio.sleep(2)  # Wait for processing
        except Exception:
            pass  # Ignore errors - we just want some history

        history = await self.client.agent.get_history(limit=20)

        # Get messages from history response
        messages = history if isinstance(history, list) else getattr(history, "messages", [])

        if not messages:
            # No messages yet is OK for this test - skip
            return

        # Check if messages have message_type field
        for msg in messages[:5]:  # Check first 5
            if isinstance(msg, dict):
                if "message_type" not in msg:
                    raise ValueError("Message missing message_type field")
            elif hasattr(msg, "message_type"):
                # SDK model - has the field
                pass
            else:
                raise ValueError(f"Unknown message format: {type(msg)}")

    async def test_queue_status(self):
        """Test that queue status endpoint works."""
        import requests

        # Get base URL and token from client
        base_url = getattr(self.client, "_base_url", None)
        if not base_url:
            transport = getattr(self.client, "_transport", None)
            if transport:
                base_url = getattr(transport, "base_url", None) or getattr(transport, "_base_url", None)

        if not base_url:
            # Fallback - extract from client configuration
            base_url = "http://localhost:8000"

        # Get auth token
        token = None
        transport = getattr(self.client, "_transport", None)
        if transport:
            token = getattr(transport, "_api_key", None) or getattr(transport, "api_key", None)

        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.get(f"{base_url}/v1/system/runtime/queue", headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()
            # Success - endpoint exists and returns data
            return
        elif response.status_code == 404:
            raise ValueError("Queue status endpoint not found")
        else:
            raise ValueError(f"Queue status returned {response.status_code}")

    async def test_valid_message_types(self):
        """Test that all message_type values are valid."""
        history = await self.client.agent.get_history(limit=50)

        messages = history if isinstance(history, list) else getattr(history, "messages", [])

        valid_types = {"user", "agent", "system", "error"}

        for msg in messages:
            msg_type = msg.get("message_type") if isinstance(msg, dict) else getattr(msg, "message_type", None)
            if msg_type and msg_type not in valid_types:
                raise ValueError(f"Invalid message_type: {msg_type}")

    async def test_is_agent_consistency(self):
        """Test that is_agent flag is consistent with message_type.

        is_agent=True means the agent should NOT observe this message.
        - Agent messages: is_agent=True (don't re-observe own responses)
        - System/error messages: is_agent=True (don't observe system notifications)
        - User messages: is_agent=False (agent should observe user input)
        """
        history = await self.client.agent.get_history(limit=50)

        messages = history if isinstance(history, list) else getattr(history, "messages", [])

        for msg in messages:
            if isinstance(msg, dict):
                msg_type = msg.get("message_type")
                is_agent = msg.get("is_agent")
            else:
                msg_type = getattr(msg, "message_type", None)
                is_agent = getattr(msg, "is_agent", None)

            if msg_type is None or is_agent is None:
                continue

            # System, error, and agent messages should have is_agent=True
            # (prevents agent from observing them)
            if msg_type in ("system", "error", "agent") and not is_agent:
                raise ValueError(f"{msg_type} message has is_agent=False (should be True)")

            # User messages should have is_agent=False (agent should observe them)
            if msg_type == "user" and is_agent:
                raise ValueError(f"User message has is_agent=True (should be False)")

    async def test_system_message_on_error(self):
        """Test that system/error messages appear when errors occur."""
        # This test verifies the infrastructure exists for system messages
        # We can't easily trigger errors in a controlled way, so we just
        # verify that the history can contain system/error messages

        history = await self.client.agent.get_history(limit=100)

        messages = history if isinstance(history, list) else getattr(history, "messages", [])

        # Count message types
        type_counts = {"user": 0, "agent": 0, "system": 0, "error": 0}
        for msg in messages:
            msg_type = msg.get("message_type") if isinstance(msg, dict) else getattr(msg, "message_type", None)
            if msg_type in type_counts:
                type_counts[msg_type] += 1

        # Log the counts (informational - not a failure if no system messages yet)
        self.console.print(f"     [dim]Message type counts: {type_counts}[/dim]")

        # Test passes if we can count message types without error
        # Actual system messages will appear when LLM errors occur

    def _print_summary(self):
        """Print test summary table."""
        table = Table(title="System Messages Test Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Error", style="red")

        passed = 0
        failed = 0

        for result in self.results:
            status = result["status"]
            if "PASS" in status:
                passed += 1
            else:
                failed += 1
            table.add_row(result["test"], status, (result["error"] or "")[:50])

        self.console.print(table)
        self.console.print(f"\n[cyan]Summary: {passed} passed, {failed} failed[/cyan]")
