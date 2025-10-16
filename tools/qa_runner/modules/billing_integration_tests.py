"""
Billing Integration QA tests with OAuth user.

Tests the complete billing workflow with credit deduction:
- Initial credit balance (3 free uses from billing backend)
- Credit deduction after message interaction
- Credit exhaustion after 3 messages
- Purchase workflow when credits exhausted
"""

import asyncio
import traceback
from typing import Dict, List

from rich.console import Console
from rich.table import Table

from ciris_sdk.client import CIRISClient


class BillingIntegrationTests:
    """Test complete billing workflow with credit deduction."""

    def __init__(self, client: CIRISClient, console: Console):
        """Initialize billing integration tests."""
        self.client = client
        self.console = console
        self.results = []
        self.initial_credits = None
        self.after_first_message = None
        self.after_exhaustion = None
        self.payment_id = None

    async def run(self) -> List[Dict]:
        """Run full billing integration tests."""
        self.console.print("\n[cyan]💳 Testing Billing Integration (Credit Deduction)[/cyan]")
        self.console.print(
            "[dim]Testing with OAuth user account - billing backend will auto-replenish to 3 credits[/dim]"
        )

        tests = [
            ("Initial Credit Check (expect 3 free uses)", self.test_initial_credits),
            ("Send Message (should consume 1 credit)", self.test_message_deduction),
            ("Verify Credit Deduction (expect 2 remaining)", self.test_credit_after_message),
            ("Send 2 More Messages (consume remaining)", self.test_exhaust_credits),
            ("Verify No Credits Remaining", self.test_credits_exhausted),
            ("Test Purchase Required Flag", self.test_purchase_required),
            ("Test Purchase Initiation", self.test_purchase_initiate),
            ("Test Purchase Status Query", self.test_purchase_status),
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
                    # Show detailed error for debugging
                    error_lines = traceback.format_exc().split("\n")
                    for line in error_lines[-10:]:  # Last 10 lines
                        if line.strip():
                            self.console.print(f"     [dim]{line}[/dim]")
                # Don't stop on first failure - continue testing

        self._print_summary()
        return self.results

    async def test_initial_credits(self):
        """Verify user starts with 3 free uses (or has been auto-replenished)."""
        status = await self.client.billing.get_credits()
        self.initial_credits = status.free_uses_remaining

        if not status.has_credit:
            raise ValueError(
                f"OAuth user should have credit. Status: has_credit={status.has_credit}, "
                f"free_uses={status.free_uses_remaining}, credits={status.credits_remaining}"
            )

        # Billing backend should auto-replenish to 3 (or user might have more)
        if status.free_uses_remaining < 1:
            raise ValueError(
                f"Expected at least 1 free use for testing, got {status.free_uses_remaining}. "
                "Billing backend may need to replenish the account."
            )

        self.console.print(
            f"     [dim]Initial credits: {status.free_uses_remaining} free uses, "
            f"{status.credits_remaining} paid credits[/dim]"
        )

    async def test_message_deduction(self):
        """Send a message (should deduct 1 credit)."""
        try:
            # Send a simple message that should succeed quickly with mock LLM
            response = await self.client.agent.interact("Test billing: hello")
            self.console.print(f"     [dim]Message sent successfully[/dim]")
        except Exception as e:
            # Message might fail for other reasons, but credit should still be charged
            error_msg = str(e)
            if "credit" in error_msg.lower() or "insufficient" in error_msg.lower():
                # If error is about credits, re-raise it
                raise
            else:
                # Other errors are acceptable - credit should still be charged
                self.console.print(f"     [dim]Message response: {error_msg[:80]}[/dim]")

    async def test_credit_after_message(self):
        """Verify credits decreased after message."""
        # Brief wait for credit deduction to be processed
        await asyncio.sleep(1)

        status = await self.client.billing.get_credits()
        self.after_first_message = status.free_uses_remaining

        expected = self.initial_credits - 1
        if status.free_uses_remaining != expected:
            raise ValueError(
                f"Expected {expected} free uses after message, got {status.free_uses_remaining}. "
                f"Started with {self.initial_credits}. This indicates credit deduction may not be working."
            )

        self.console.print(
            f"     [dim]Credits after message: {status.free_uses_remaining} free uses " f"(consumed 1 credit)[/dim]"
        )

    async def test_exhaust_credits(self):
        """Send messages to exhaust remaining credits."""
        remaining_credits = self.after_first_message

        # If credit deduction isn't working, remaining_credits may still be 3
        # Limit iterations to prevent hanging
        max_attempts = min(remaining_credits, 5)  # Cap at 5 messages

        for i in range(max_attempts):
            try:
                # Add timeout to prevent hanging
                await asyncio.wait_for(
                    self.client.agent.interact(f"Test billing: message {i+2}"), timeout=15.0  # 15s timeout per message
                )
                self.console.print(f"     [dim]Message {i+2} sent[/dim]")
            except asyncio.TimeoutError:
                self.console.print(f"     [dim]Message {i+2} timeout[/dim]")
                break
            except Exception as e:
                # Credit should still be charged even if message fails
                error_msg = str(e)
                if "credit" in error_msg.lower() or "insufficient" in error_msg.lower():
                    # This might be expected if we ran out of credits
                    self.console.print(f"     [dim]Credit check failed (expected): {error_msg[:80]}[/dim]")
                    break
                else:
                    self.console.print(f"     [dim]Message {i+2} error: {error_msg[:80]}[/dim]")

            # Brief wait between messages
            await asyncio.sleep(0.5)

    async def test_credits_exhausted(self):
        """Verify no credits remaining."""
        await asyncio.sleep(1)

        status = await self.client.billing.get_credits()
        self.after_exhaustion = status.free_uses_remaining

        if status.free_uses_remaining != 0:
            raise ValueError(
                f"Expected 0 free uses after exhaustion, got {status.free_uses_remaining}. "
                f"Started with {self.initial_credits}, consumed {self.initial_credits} messages."
            )

        if status.has_credit:
            # If they have paid credits remaining, that's OK
            if status.credits_remaining > 0:
                self.console.print(
                    f"     [dim]All free uses consumed, {status.credits_remaining} paid credits remain[/dim]"
                )
                return
            else:
                raise ValueError(
                    "User should not have credit after using all free uses and no paid credits. "
                    f"has_credit={status.has_credit}, free_uses={status.free_uses_remaining}, "
                    f"credits={status.credits_remaining}"
                )

        self.console.print(f"     [dim]All credits consumed (free and paid)[/dim]")

    async def test_purchase_required(self):
        """Verify purchase required flag is set when credits exhausted."""
        status = await self.client.billing.get_credits()

        # Only check purchase_required if user has no credits at all
        if status.credits_remaining > 0:
            self.console.print(f"     [dim]Skipping: User has {status.credits_remaining} paid credits remaining[/dim]")
            return

        if not status.purchase_required:
            raise ValueError(
                "purchase_required should be True when credits exhausted. "
                f"has_credit={status.has_credit}, free_uses={status.free_uses_remaining}, "
                f"credits={status.credits_remaining}, purchase_required={status.purchase_required}"
            )

        if not status.purchase_options:
            raise ValueError("purchase_options should be present when purchase required")

        options = status.purchase_options
        price_display = f"${options['price_minor']/100:.2f}" if "price_minor" in options else "unknown"
        uses_display = options.get("uses", "unknown")

        self.console.print(f"     [dim]Purchase required: {price_display} for {uses_display} uses[/dim]")

    async def test_purchase_initiate(self):
        """Test initiating a purchase (creates Stripe payment intent)."""
        try:
            # Initiate purchase with test mode Stripe
            purchase = await self.client.billing.initiate_purchase(return_url="https://test.ciris.ai/payment-complete")

            # Verify response structure
            if not purchase.payment_id:
                raise ValueError("Missing payment_id in purchase response")

            if not purchase.client_secret:
                raise ValueError("Missing client_secret in purchase response")

            if purchase.amount_minor <= 0:
                raise ValueError(f"Invalid amount_minor: {purchase.amount_minor}")

            if purchase.uses_purchased <= 0:
                raise ValueError(f"Invalid uses_purchased: {purchase.uses_purchased}")

            if purchase.currency != "USD":
                raise ValueError(f"Expected currency USD, got {purchase.currency}")

            # Store payment_id for status test
            self.payment_id = purchase.payment_id

            price_display = f"${purchase.amount_minor / 100:.2f}"
            self.console.print(
                f"     [dim]Payment initiated: {price_display} for {purchase.uses_purchased} uses "
                f"(payment_id: {purchase.payment_id[:16]}...)[/dim]"
            )

        except Exception as e:
            error_msg = str(e)
            # Check if this is a "billing not enabled" error (SimpleCreditProvider)
            if "billing not enabled" in error_msg.lower() or "contact administrator" in error_msg.lower():
                self.console.print(
                    "     [dim]Skipping: Billing backend not enabled (SimpleCreditProvider active)[/dim]"
                )
                return
            # Re-raise other errors
            raise

    async def test_purchase_status(self):
        """Test querying purchase status."""
        if not self.payment_id:
            self.console.print("     [dim]Skipping: No payment_id from initiate test[/dim]")
            return

        try:
            # Query payment status
            status = await self.client.billing.get_purchase_status(self.payment_id)

            # Verify response structure
            if not status.status:
                raise ValueError("Missing status in purchase status response")

            # Status should be one of: succeeded, pending, failed, processing
            valid_statuses = ["succeeded", "pending", "failed", "processing", "requires_payment_method"]
            if status.status not in valid_statuses:
                raise ValueError(f"Invalid status: {status.status}, expected one of {valid_statuses}")

            # For test mode without completing payment, status should be "pending"
            # credits_added should be 0 or None for pending payments
            if status.status == "succeeded" and status.credits_added == 0:
                raise ValueError("Status is 'succeeded' but credits_added is 0")

            self.console.print(
                f"     [dim]Payment status: {status.status}, " f"credits_added: {status.credits_added or 0}[/dim]"
            )

        except Exception as e:
            error_msg = str(e)
            # Check if this is a "billing not enabled" error
            if "billing not enabled" in error_msg.lower() or "payment not found" in error_msg.lower():
                self.console.print("     [dim]Skipping: Billing backend not enabled[/dim]")
                return
            # Re-raise other errors
            raise

    def _print_summary(self):
        """Print test summary."""
        table = Table(title="Billing Integration Test Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status", style="green")

        passed = sum(1 for r in self.results if "PASS" in r["status"])
        total = len(self.results)

        for result in self.results:
            status_style = "green" if "PASS" in result["status"] else "red"
            table.add_row(result["test"], f"[{status_style}]{result['status']}[/{status_style}]")

        self.console.print(table)
        self.console.print(f"\n[bold]Passed: {passed}/{total}[/bold]")

        # Show credit progression summary
        if self.initial_credits is not None:
            self.console.print("\n[cyan]Credit Progression:[/cyan]")
            self.console.print(f"  Initial: {self.initial_credits} free uses")
            if self.after_first_message is not None:
                self.console.print(f"  After 1st message: {self.after_first_message} free uses")
            if self.after_exhaustion is not None:
                self.console.print(f"  After exhaustion: {self.after_exhaustion} free uses")
