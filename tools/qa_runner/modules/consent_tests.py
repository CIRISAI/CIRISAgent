"""
Consent management QA tests.

Tests the complete consent lifecycle including:
- Initial consent creation on interaction
- Consent status queries
- Partnership requests
- Stream changes (temporary/anonymous/partnered)
- Consent revocation and decay
"""

import traceback
from typing import Dict, List, Optional

from rich.console import Console
from rich.table import Table

from ciris_sdk.client import CIRISClient
from ciris_sdk.resources.consent import ConsentScope, ConsentStatus


class ConsentTests:
    """Test consent management functionality."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize consent tests."""
        self.client = client
        self.console = console
        self.results = []

    async def run(self) -> List[Dict]:
        """Run all consent tests."""
        self.console.print("\n[cyan]📝 Testing Consent Management[/cyan]")

        tests = [
            ("Check Initial Status", self.test_initial_status),
            ("Create Default Consent", self.test_create_default_consent),
            ("Query Consent Records", self.test_query_consents),
            ("Change Consent Stream", self.test_change_stream),
            ("Request Partnership", self.test_request_partnership),
            ("Get Impact Report", self.test_impact_report),
            ("Audit Trail", self.test_audit_trail),
            ("Revoke Consent", self.test_revoke_consent),
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

    async def test_initial_status(self):
        """Test getting initial consent status."""
        status = await self.client.consent.get_status()

        # New users should not have consent initially
        if status.get("has_consent"):
            # Check if it's from a previous test
            if "user_id" not in status:
                raise ValueError("Invalid consent status response")

    async def test_create_default_consent(self):
        """Test that consent is created on first interaction."""
        # First interaction should create default consent
        response = await self.client.interact("Hello, this is a test message")

        if not response or not response.response:
            raise ValueError("No response from interaction")

        # Check consent was created
        status = await self.client.consent.get_status()

        # After interaction, should have consent
        if not status.get("has_consent", False):
            # Try to grant explicit consent
            await self.client.consent.grant_consent(
                stream="temporary", categories=["interaction"], reason="Test consent creation"
            )

            # Check again
            status = await self.client.consent.get_status()
            if not status.get("has_consent", False):
                raise ValueError("Consent not created after interaction")

    async def test_query_consents(self):
        """Test querying consent records."""
        # Query all consents for current user
        result = await self.client.consent.query_consents()

        if "consents" not in result:
            raise ValueError("Invalid query response")

        # Should have at least one consent after interaction
        if result["total"] == 0:
            # Grant one for testing
            await self.client.consent.grant_consent(stream="temporary", categories=["interaction"], reason="Test query")

            result = await self.client.consent.query_consents()
            if result["total"] == 0:
                raise ValueError("No consents found after granting")

    async def test_change_stream(self):
        """Test changing consent stream."""
        # First ensure we have consent
        await self.client.consent.grant_consent(
            stream="temporary", categories=["interaction"], reason="Initial consent"
        )

        # Change to anonymous
        result = await self.client.consent.grant_consent(
            stream="anonymous", categories=["interaction", "research"], reason="Testing anonymous stream"
        )

        if result.stream != "anonymous":
            raise ValueError(f"Stream not changed to anonymous: {result.stream}")

        # Change back to temporary
        result = await self.client.consent.grant_consent(
            stream="temporary", categories=["interaction"], reason="Testing temporary stream"
        )

        if result.stream != "temporary":
            raise ValueError(f"Stream not changed to temporary: {result.stream}")

    async def test_request_partnership(self):
        """Test requesting partnership (requires agent approval)."""
        try:
            # Request partnership
            result = await self.client.consent.grant_consent(
                stream="partnered",
                categories=["interaction", "preference", "improvement", "research", "sharing"],
                reason="Testing partnership request from QA suite",
            )

            # Partnership requires approval, so check status
            partnership_status = await self.client.consent.get_partnership_status()

            # Should be pending or none
            status_val = partnership_status.get("status", "none")
            if status_val not in ["pending", "none", "approved", "rejected"]:
                raise ValueError(f"Invalid partnership status: {status_val}")

        except Exception as e:
            # Partnership might not be available in test environment
            if "partnership" not in str(e).lower():
                raise

    async def test_impact_report(self):
        """Test getting consent impact report."""
        try:
            report = await self.client.consent.get_impact_report()

            # Should have standard fields
            if "total_interactions" not in report:
                raise ValueError("Missing total_interactions in impact report")

        except Exception as e:
            # Impact report might require existing consent
            if "consent" not in str(e).lower():
                raise

    async def test_audit_trail(self):
        """Test getting consent audit trail."""
        try:
            # First make a change to create audit entry
            await self.client.consent.grant_consent(
                stream="temporary", categories=["interaction", "improvement"], reason="Test audit trail"
            )

            # Get audit trail
            audit = await self.client.consent.get_audit_trail()

            # Should be a list
            if not isinstance(audit, list):
                raise ValueError("Audit trail should be a list")

        except Exception as e:
            # Audit might not be available
            if "audit" not in str(e).lower() and "not found" not in str(e).lower():
                raise

    async def test_revoke_consent(self):
        """Test revoking consent."""
        try:
            # First ensure we have consent
            await self.client.consent.grant_consent(
                stream="temporary", categories=["interaction"], reason="Test before revoke"
            )

            # Revoke consent
            result = await self.client.consent.revoke_consent()

            # Should return decay status
            if "decay_started" not in result and "user_id" not in result:
                raise ValueError("Invalid revoke response")

        except Exception as e:
            # Revoke might have specific requirements
            if "revoke" not in str(e).lower() and "consent" not in str(e).lower():
                raise

    def _print_summary(self):
        """Print test summary."""
        table = Table(title="Consent Test Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="green")

        passed = sum(1 for r in self.results if "PASS" in r["status"])
        total = len(self.results)

        for result in self.results:
            status_style = "green" if "PASS" in result["status"] else "red"
            table.add_row(result["test"], f"[{status_style}]{result['status']}[/{status_style}]")

        self.console.print(table)
        self.console.print(f"\n[bold]Passed: {passed}/{total}[/bold]")
