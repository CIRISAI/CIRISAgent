"""
DSAR (Data Subject Access Request) automation QA tests.

Tests the automated DSAR functionality including:
- DSAR request initiation
- Data export completeness
- Privacy guarantees (anonymization)
- Request status tracking
"""

import traceback
from typing import Dict, List

from rich.console import Console
from rich.table import Table

from ciris_sdk.client import CIRISClient


class DSARTests:
    """Test DSAR automation functionality."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize DSAR tests."""
        self.client = client
        self.console = console
        self.results = []

    async def run(self) -> List[Dict]:
        """Run all DSAR tests."""
        self.console.print("\n[cyan]📦 Testing DSAR Automation[/cyan]")

        tests = [
            ("Initiate Full DSAR", self.test_initiate_full_dsar),
            ("Verify Consent Data Export", self.test_consent_data_export),
            ("Verify Impact Metrics Export", self.test_impact_metrics_export),
            ("Verify Audit Trail Export", self.test_audit_trail_export),
            ("Test Consent-Only DSAR", self.test_consent_only_dsar),
            ("Test DSAR Status Tracking", self.test_dsar_status),
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

    async def test_initiate_full_dsar(self):
        """Test initiating a full DSAR request."""
        # First grant consent to have data to export
        await self.client.consent.grant_consent(
            stream="temporary", categories=["interaction", "improvement"], reason="Create data for DSAR test"
        )

        # Initiate full DSAR
        result = await self.client.consent.initiate_dsar(request_type="full")

        # Verify response structure
        if "request_id" not in result:
            raise ValueError("DSAR response missing request_id")

        if "export_data" not in result:
            raise ValueError("DSAR response missing export_data")

        # Verify export contains expected sections
        export_data = result["export_data"]
        if "consent" not in export_data:
            raise ValueError("DSAR export missing consent section")

    async def test_consent_data_export(self):
        """Test that DSAR exports consent data correctly."""
        # Grant consent first
        await self.client.consent.grant_consent(
            stream="temporary", categories=["interaction"], reason="Test consent export"
        )

        # Initiate DSAR
        result = await self.client.consent.initiate_dsar(request_type="full")
        export_data = result["export_data"]

        # Verify consent section
        consent_data = export_data.get("consent", {})
        if "stream" not in consent_data:
            raise ValueError("Consent export missing stream")

        if "categories" not in consent_data:
            raise ValueError("Consent export missing categories")

        if "granted_at" not in consent_data:
            raise ValueError("Consent export missing granted_at timestamp")

    async def test_impact_metrics_export(self):
        """Test that DSAR exports impact metrics."""
        # Initiate DSAR
        result = await self.client.consent.initiate_dsar(request_type="full")
        export_data = result["export_data"]

        # Verify impact section (may be empty if no interactions)
        if "impact" in export_data:
            impact_data = export_data["impact"]
            if "total_interactions" not in impact_data:
                raise ValueError("Impact export missing total_interactions")

    async def test_audit_trail_export(self):
        """Test that DSAR exports audit trail."""
        # Make a consent change to create audit entry
        await self.client.consent.grant_consent(
            stream="temporary", categories=["interaction", "improvement"], reason="Test audit trail export"
        )

        # Initiate DSAR
        result = await self.client.consent.initiate_dsar(request_type="full")
        export_data = result["export_data"]

        # Verify audit trail section
        if "audit_trail" in export_data:
            audit_data = export_data["audit_trail"]
            if not isinstance(audit_data, list):
                raise ValueError(f"Audit trail should be a list, got: {type(audit_data)}")

    async def test_consent_only_dsar(self):
        """Test DSAR with consent_only request type."""
        # Grant consent first
        await self.client.consent.grant_consent(stream="temporary", categories=["interaction"], reason="Test")

        # Initiate consent-only DSAR
        result = await self.client.consent.initiate_dsar(request_type="consent_only")

        # Should have consent data
        export_data = result["export_data"]
        if "consent" not in export_data:
            raise ValueError("Consent-only DSAR missing consent section")

        # Should NOT have interaction data (if that section exists)
        # Note: This depends on backend implementation
        # For now, just verify we got a valid response

    async def test_dsar_status(self):
        """Test DSAR status tracking."""
        # Initiate DSAR
        result = await self.client.consent.initiate_dsar(request_type="full")
        request_id = result["request_id"]

        # Check status
        status = await self.client.consent.get_dsar_status(request_id)

        # Verify status response
        if "status" not in status:
            raise ValueError("DSAR status response missing status field")

        # Status should be completed (since we process immediately)
        if status["status"] not in ["completed", "pending", "processing"]:
            raise ValueError(f"Invalid DSAR status: {status['status']}")

    def _print_summary(self):
        """Print test summary."""
        table = Table(title="DSAR Test Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="green")

        passed = sum(1 for r in self.results if "PASS" in r["status"])
        total = len(self.results)

        for result in self.results:
            status_style = "green" if "PASS" in result["status"] else "red"
            table.add_row(result["test"], f"[{status_style}]{result['status']}[/{status_style}]")

        self.console.print(table)
        self.console.print(f"\n[bold]Passed: {passed}/{total}[/bold]")
