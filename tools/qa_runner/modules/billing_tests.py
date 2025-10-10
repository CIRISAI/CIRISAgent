"""
Billing QA tests.

Tests the billing system including:
- Credit balance checking
- Credit purchase initiation
- Payment status polling
- SimpleCreditProvider vs CIRISBillingProvider behavior
"""

import traceback
from typing import Dict, List, Optional

from rich.console import Console
from rich.table import Table

from ciris_sdk.client import CIRISClient


class BillingTests:
    """Test billing functionality."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize billing tests."""
        self.client = client
        self.console = console
        self.results = []
        self.payment_id: Optional[str] = None

    async def run(self) -> List[Dict]:
        """Run all billing tests."""
        self.console.print("\n[cyan]💳 Testing Billing System[/cyan]")

        tests = [
            ("Get Credit Status", self.test_get_credit_status),
            ("Check Credit Balance Display", self.test_credit_balance_display),
            ("Check Purchase Options", self.test_purchase_options),
            ("Initiate Purchase (if enabled)", self.test_initiate_purchase),
            ("Check Purchase Status (if initiated)", self.test_purchase_status),
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

    async def test_get_credit_status(self):
        """Test getting credit status."""
        status = await self.client.billing.get_credits()

        # Should have all required fields
        if not hasattr(status, "has_credit"):
            raise ValueError("Missing has_credit field")
        if not hasattr(status, "credits_remaining"):
            raise ValueError("Missing credits_remaining field")
        if not hasattr(status, "free_uses_remaining"):
            raise ValueError("Missing free_uses_remaining field")
        if not hasattr(status, "total_uses"):
            raise ValueError("Missing total_uses field")
        if not hasattr(status, "purchase_required"):
            raise ValueError("Missing purchase_required field")

        # Store for debugging
        self.console.print(f"     [dim]Credit status: {status.model_dump()}[/dim]")

    async def test_credit_balance_display(self):
        """Test credit balance display logic."""
        status = await self.client.billing.get_credits()

        # Check if user has credit
        if status.has_credit:
            # User has available credit (free or paid)
            total_available = status.credits_remaining + status.free_uses_remaining
            if total_available <= 0:
                raise ValueError("has_credit=True but no credits available")
        else:
            # User has no credit
            if status.credits_remaining > 0 or status.free_uses_remaining > 0:
                raise ValueError("has_credit=False but credits show as available")

        # Verify plan name is set
        if status.plan_name is None:
            raise ValueError("plan_name should not be None")

    async def test_purchase_options(self):
        """Test purchase options in credit status."""
        status = await self.client.billing.get_credits()

        # If purchase required, should have options
        if status.purchase_required:
            if status.purchase_options is None:
                raise ValueError("purchase_required=True but no purchase_options")

            # Check purchase options structure
            options = status.purchase_options
            if "price_minor" not in options:
                raise ValueError("Missing price_minor in purchase_options")
            if "uses" not in options:
                raise ValueError("Missing uses in purchase_options")
            if "currency" not in options:
                raise ValueError("Missing currency in purchase_options")

            self.console.print(f"     [dim]Purchase: ${options['price_minor'] / 100} for {options['uses']} uses[/dim]")

    async def test_initiate_purchase(self):
        """Test initiating credit purchase (if billing enabled)."""
        try:
            purchase = await self.client.billing.initiate_purchase(return_url="https://test.example.com/return")

            # Verify purchase response structure
            if not hasattr(purchase, "payment_id"):
                raise ValueError("Missing payment_id in purchase response")
            if not hasattr(purchase, "client_secret"):
                raise ValueError("Missing client_secret in purchase response")
            if not hasattr(purchase, "amount_minor"):
                raise ValueError("Missing amount_minor in purchase response")

            # Store payment_id for status check
            self.payment_id = purchase.payment_id
            self.console.print(f"     [dim]Payment initiated: {purchase.payment_id}[/dim]")
            self.console.print(
                f"     [dim]Amount: ${purchase.amount_minor / 100:.2f} for {purchase.uses_purchased} uses[/dim]"
            )

        except Exception as e:
            # Billing might be disabled or Stripe not configured - this is acceptable
            error_msg = str(e).lower()
            if any(
                err in error_msg
                for err in ["billing not enabled", "not configured", "payment provider", "stripe", "403", "forbidden"]
            ):
                self.console.print(f"     [dim]Purchase unavailable: {str(e)[:80]}[/dim]")
            else:
                raise

    async def test_purchase_status(self):
        """Test checking purchase status (if purchase initiated)."""
        if self.payment_id is None:
            # No purchase to check - skip test
            self.console.print("     [dim]Skipping: No payment to check[/dim]")
            return

        # Check purchase status
        try:
            status = await self.client.billing.get_purchase_status(self.payment_id)

            # Verify status response structure
            if not hasattr(status, "status"):
                raise ValueError("Missing status field in purchase status")
            if not hasattr(status, "credits_added"):
                raise ValueError("Missing credits_added field in purchase status")

            # Status should be one of the valid Stripe payment statuses
            valid_statuses = [
                "succeeded",
                "pending",
                "failed",
                "unknown",
                "requires_payment_method",
                "requires_confirmation",
                "requires_action",
                "processing",
                "canceled",
            ]
            if status.status not in valid_statuses:
                raise ValueError(f"Invalid purchase status: {status.status}")

            self.console.print(f"     [dim]Purchase status: {status.status}[/dim]")

        except Exception as e:
            # 404 is acceptable for test payments
            error_msg = str(e).lower()
            if "404" in error_msg or "not found" in error_msg:
                self.console.print("     [dim]Test payment not found (expected for test)[/dim]")
            else:
                raise

    def _print_summary(self):
        """Print test summary."""
        table = Table(title="Billing Test Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="green")

        passed = sum(1 for r in self.results if "PASS" in r["status"])
        total = len(self.results)

        for result in self.results:
            status_style = "green" if "PASS" in result["status"] else "red"
            table.add_row(result["test"], f"[{status_style}]{result['status']}[/{status_style}]")

        self.console.print(table)
        self.console.print(f"\n[bold]Passed: {passed}/{total}[/bold]")
