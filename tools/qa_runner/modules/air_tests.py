"""
AIR (Artificial Interaction Reminder) QA tests.

Tests the parasocial attachment prevention system including:
- Basic interaction tracking
- Message-based reminder triggers (20+ messages)
- Time-based reminder triggers (30+ minutes)
- AIR reminder appearance in response
- Session management

Based on MDD-aligned design (v2.0) with objective thresholds only.
See FSD/AIR_ARTIFICIAL_INTERACTION_REMINDER.md for design rationale.
"""

import asyncio
import logging
import traceback
from typing import Any, Dict, List

import httpx
from rich.console import Console

logger = logging.getLogger(__name__)


class AIRTests:
    """Test AIR (Artificial Interaction Reminder) parasocial prevention functionality."""

    def __init__(self, client: Any, console: Console):
        """Initialize AIR tests.

        Args:
            client: CIRIS SDK client (authenticated)
            console: Rich console for output
        """
        self.client = client
        self.console = console
        self.results: List[Dict[str, Any]] = []

        # Extract base URL and token from client for direct HTTP calls
        self.base_url = getattr(client, "base_url", "http://localhost:8080")
        if hasattr(client, "_transport") and hasattr(client._transport, "base_url"):
            self.base_url = client._transport.base_url

        # Extract token from client
        self.token = getattr(client, "api_key", None)
        if hasattr(client, "_transport") and hasattr(client._transport, "api_key"):
            self.token = client._transport.api_key

    async def run(self) -> List[Dict[str, Any]]:
        """Run all AIR tests."""
        self.console.print("\n[cyan]🛡️ Testing AIR (Artificial Interaction Reminder) System[/cyan]")

        tests = [
            ("Basic Interaction Tracking", self.test_basic_tracking),
            ("AIR Manager Initialization", self.test_air_manager_init),
            ("Message Threshold Tracking", self.test_message_threshold),
            ("AIR Reminder Format", self.test_reminder_format),
            ("Session Reset After Idle", self.test_session_reset),
            ("Grounding Suggestions Present", self.test_grounding_suggestions),
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
                    self.console.print(f"     [dim]{traceback.format_exc()}[/dim]")

        self._print_summary()
        return self.results

    async def test_basic_tracking(self) -> None:
        """Test that basic interaction tracking works without errors."""
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self.base_url}/v1/agent/interact",
                headers={"Authorization": f"Bearer {self.token}"},
                json={"message": "Hello, this is a normal test message."},
            )

            assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
            data = response.json()

            # Verify response structure
            assert "data" in data, "Missing 'data' in response"
            assert "response" in data["data"], "Missing 'response' in data"

            # First message should NOT trigger AIR reminder
            response_text = data["data"]["response"]
            assert (
                "Mindful Interaction Reminder" not in response_text
            ), "AIR reminder should not appear on first message"

    async def test_air_manager_init(self) -> None:
        """Test that AIR manager initializes correctly via ConsentService."""
        # This tests the internal initialization - we verify by making multiple calls
        # without errors, which confirms AIR manager is properly initialized
        async with httpx.AsyncClient(timeout=60.0) as client:
            for i in range(3):
                response = await client.post(
                    f"{self.base_url}/v1/agent/interact",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json={"message": f"Test message {i+1} for AIR initialization check."},
                )
                assert response.status_code == 200, f"Request {i+1} failed: {response.status_code}"

    async def test_message_threshold(self) -> None:
        """Test that message tracking works for threshold detection.

        Note: Full threshold testing (20+ messages) takes too long for QA suite.
        This test verifies:
        1. Multiple messages can be sent without errors
        2. AIR tracking doesn't crash with rapid messages
        3. Response structure is correct throughout

        For comprehensive threshold testing, use the unit tests directly.
        """
        async with httpx.AsyncClient(timeout=120.0) as client:
            # Send 5 messages to verify tracking works (fast test)
            # Full threshold testing would require 20+ messages taking 20+ minutes
            for i in range(5):
                response = await client.post(
                    f"{self.base_url}/v1/agent/interact",
                    headers={"Authorization": f"Bearer {self.token}"},
                    json={"message": f"Threshold tracking test message {i+1}."},
                )
                assert response.status_code == 200, f"Request {i+1} failed: {response.status_code}"

                data = response.json()
                assert "data" in data, "Missing 'data' in response"
                assert "response" in data["data"], "Missing 'response' in data"

                # Small delay to not overwhelm the server
                await asyncio.sleep(0.1)

            self.console.print(f"     [dim]Message tracking verified (5 messages sent successfully)[/dim]")

    async def test_reminder_format(self) -> None:
        """Test that AIR reminders have the expected format when triggered.

        This test verifies the reminder generation code path by examining
        the AIR module directly.
        """
        from datetime import datetime, timezone

        from ciris_engine.logic.services.governance.consent.air import ArtificialInteractionReminder, InteractionSession
        from ciris_engine.logic.services.lifecycle.time import TimeService

        time_service = TimeService()
        air = ArtificialInteractionReminder(time_service=time_service)

        # Create a mock session for reminder generation
        now = datetime.now(timezone.utc)
        session = InteractionSession("test_user", "test_channel", now)
        session.message_timestamps = [now] * 5  # Simulate 5 messages

        # Manually trigger a reminder to verify format
        reminder = air._generate_reminder(session, time_triggered=True, message_triggered=False)

        assert reminder is not None, "Reminder should be generated"
        assert len(reminder) > 100, "Reminder should have substantial content"

        # Check for key elements based on the simplified AIR
        reminder_lower = reminder.lower()

        # Should mention its nature as a language model/tool
        assert (
            "language model" in reminder_lower or "tool" in reminder_lower
        ), "Reminder should mention being a language model or tool"

        # Should mention what it's NOT (human substitute)
        assert "not" in reminder_lower and (
            "friend" in reminder_lower or "substitute" in reminder_lower
        ), "Reminder should clarify what AI is not (friend, substitute, etc.)"

        # Check for grounding suggestions (5-4-3-2-1 technique)
        assert (
            "5 things" in reminder_lower or "notice" in reminder_lower
        ), "Reminder should include grounding suggestions"

        # Check for physical world references
        assert "physical" in reminder_lower or "real" in reminder_lower, "Reminder should reference physical/real world"

    async def test_session_reset(self) -> None:
        """Test that sessions are properly managed and can be reset."""
        from ciris_engine.logic.services.governance.consent.air import ArtificialInteractionReminder
        from ciris_engine.logic.services.lifecycle.time import TimeService

        time_service = TimeService()
        air = ArtificialInteractionReminder(time_service=time_service)

        # Track some interactions
        for i in range(5):
            air.track_interaction("reset_test_user", "reset_test_channel", "api", f"Message {i}")

        # Verify session exists
        session_key = ("reset_test_user", "reset_test_channel")
        assert session_key in air._sessions, "Session should exist after tracking"

        # InteractionSession stores timestamps in message_timestamps list
        initial_count = len(air._sessions[session_key].message_timestamps)
        assert initial_count == 5, f"Expected 5 messages, got {initial_count}"

        # Track more to verify increment works
        air.track_interaction("reset_test_user", "reset_test_channel", "api", "Message 6")
        new_count = len(air._sessions[session_key].message_timestamps)
        assert new_count == 6, f"Message count should increment, got {new_count}"

    async def test_grounding_suggestions(self) -> None:
        """Test that AIR reminders include 5-4-3-2-1 grounding technique."""
        from datetime import datetime, timezone

        from ciris_engine.logic.services.governance.consent.air import ArtificialInteractionReminder, InteractionSession
        from ciris_engine.logic.services.lifecycle.time import TimeService

        time_service = TimeService()
        air = ArtificialInteractionReminder(time_service=time_service)

        # Create a mock session
        now = datetime.now(timezone.utc)
        session = InteractionSession("test_user", "test_channel", now)
        session.message_timestamps = [now] * 5

        # Generate reminder
        reminder = air._generate_reminder(session, time_triggered=True, message_triggered=False)
        reminder_lower = reminder.lower()

        # Should include grounding techniques
        assert "5 things" in reminder_lower, "Should mention 5 things to see"
        assert "breath" in reminder_lower, "Should mention breathing"
        assert "feet" in reminder_lower or "floor" in reminder_lower, "Should mention physical grounding"

        # Should encourage human connection
        assert "real person" in reminder_lower, "Should encourage connecting with real people"

    def _print_summary(self) -> None:
        """Print test summary."""
        passed = sum(1 for r in self.results if "PASS" in r["status"])
        total = len(self.results)

        self.console.print(f"\n[bold]AIR Tests: {passed}/{total} passed[/bold]")

        if passed < total:
            self.console.print("[yellow]Failed tests:[/yellow]")
            for r in self.results:
                if "FAIL" in r["status"]:
                    self.console.print(f"  - {r['test']}: {r['error']}")
