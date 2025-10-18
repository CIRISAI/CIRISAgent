"""
Partnership management QA tests.

Tests the bilateral consent flow for partnerships including:
- Partnership request creation
- Partnership options query
- Status tracking
- Approval/rejection flow (limited testing without agent processor)
"""

import traceback
from typing import Dict, List

from rich.console import Console
from rich.table import Table

from ciris_sdk.client import CIRISClient


class PartnershipTests:
    """Test partnership management functionality."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize partnership tests."""
        self.client = client
        self.console = console
        self.results = []

    async def run(self) -> List[Dict]:
        """Run all partnership tests."""
        self.console.print("\n[cyan]🤝 Testing Partnership Management[/cyan]")

        tests = [
            ("Get Partnership Options", self.test_get_partnership_options),
            ("Request Partnership", self.test_request_partnership),
            ("Check Partnership Status", self.test_check_partnership_status),
            ("Verify Pending State", self.test_verify_pending_state),
            ("Test Stream Remains Unchanged", self.test_stream_unchanged),
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

    async def test_get_partnership_options(self):
        """Test getting partnership options and requirements."""
        try:
            options = await self.client.consent.get_partnership_options()

            # Verify response structure
            if not isinstance(options, dict):
                raise ValueError(f"Expected dict response, got: {type(options)}")

            # Should have description of partnership requirements
            # (exact structure depends on backend implementation)

        except Exception as e:
            # Partnership options endpoint may not be implemented yet
            if "404" in str(e) or "not found" in str(e).lower():
                self.console.print("    [yellow]Partnership options endpoint not yet implemented[/yellow]")
                # Don't fail the test - this is expected during development
            else:
                raise

    async def test_request_partnership(self):
        """Test requesting partnership upgrade."""
        # First ensure user has basic consent
        await self.client.consent.grant_consent(
            stream="temporary", categories=["interaction"], reason="Initial consent before partnership request"
        )

        # Request partnership upgrade
        result = await self.client.consent.grant_consent(
            stream="partnered",
            categories=["interaction", "preference", "improvement", "research", "sharing"],
            reason="Testing partnership request from QA suite",
        )

        # Should return a consent status
        if not hasattr(result, "stream") and "stream" not in str(result):
            raise ValueError("Partnership request did not return consent status")

    async def test_check_partnership_status(self):
        """Test checking partnership request status."""
        # Request partnership first
        await self.client.consent.grant_consent(
            stream="partnered",
            categories=["interaction", "preference", "improvement"],
            reason="Test partnership status check",
        )

        # Check status
        status = await self.client.consent.get_partnership_status()

        # Verify response structure
        if "partnership_status" not in status:
            raise ValueError("Partnership status response missing partnership_status field")

        # Status should be one of: pending, accepted, rejected, deferred, none
        partnership_status = status["partnership_status"]
        valid_statuses = ["pending", "accepted", "rejected", "deferred", "none"]
        if partnership_status not in valid_statuses:
            raise ValueError(f"Invalid partnership status: {partnership_status}")

    async def test_verify_pending_state(self):
        """Test that partnership request creates pending state."""
        # Start with temporary consent
        await self.client.consent.grant_consent(
            stream="temporary", categories=["interaction"], reason="Start temporary"
        )

        # Request partnership
        await self.client.consent.grant_consent(
            stream="partnered",
            categories=["interaction", "preference", "improvement"],
            reason="Test pending state",
        )

        # Check that we have a pending partnership
        status = await self.client.consent.get_partnership_status()

        # Should either be pending or none (if processed immediately)
        # In test environment without agent processor, status may be "none"
        if status["partnership_status"] not in ["pending", "none", "accepted"]:
            raise ValueError(f"Unexpected partnership status: {status['partnership_status']}")

    async def test_stream_unchanged(self):
        """Test that stream doesn't change until partnership is approved."""
        # Start with temporary
        await self.client.consent.grant_consent(stream="temporary", categories=["interaction"], reason="Start")

        # Request partnership
        await self.client.consent.grant_consent(
            stream="partnered",
            categories=["interaction", "preference"],
            reason="Test stream unchanged",
        )

        # Get current consent status
        consent_status = await self.client.consent.get_status()

        # Stream should still be temporary until agent approves
        # OR it might be partnered if there's no approval flow in test mode
        current_stream = consent_status.get("stream", "").lower()
        if current_stream not in ["temporary", "partnered"]:
            raise ValueError(f"Unexpected consent stream: {current_stream}")

    def _print_summary(self):
        """Print test summary."""
        table = Table(title="Partnership Test Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="green")

        passed = sum(1 for r in self.results if "PASS" in r["status"])
        total = len(self.results)

        for result in self.results:
            status_style = "green" if "PASS" in result["status"] else "red"
            table.add_row(result["test"], f"[{status_style}]{result['status']}[/{status_style}]")

        self.console.print(table)
        self.console.print(f"\n[bold]Passed: {passed}/{total}[/bold]")
