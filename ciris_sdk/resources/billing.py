"""Billing resource for CIRIS SDK."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

from ..transport import Transport


class CreditStatus(BaseModel):
    """Credit status for a user."""

    has_credit: bool = Field(..., description="Whether user has available credit")
    credits_remaining: int = Field(..., description="Remaining paid credits")
    free_uses_remaining: int = Field(..., description="Remaining free uses")
    total_uses: int = Field(..., description="Total uses so far")
    plan_name: Optional[str] = Field(None, description="Current plan name")
    purchase_required: bool = Field(..., description="Whether purchase is required to continue")
    purchase_options: Optional[Dict[str, Any]] = Field(None, description="Purchase options if required")


class PurchaseInitiation(BaseModel):
    """Purchase initiation response."""

    payment_id: str = Field(..., description="Payment intent ID")
    client_secret: str = Field(..., description="Stripe client secret for frontend")
    amount_minor: int = Field(..., description="Amount in minor units (cents)")
    currency: str = Field(..., description="Currency code (USD)")
    uses_purchased: int = Field(..., description="Number of uses being purchased")
    publishable_key: Optional[str] = Field(None, description="Stripe publishable key")


class PurchaseStatus(BaseModel):
    """Purchase status response."""

    status: str = Field(..., description="Payment status (succeeded, pending, failed)")
    credits_added: Optional[int] = Field(None, description="Credits added (0 if not completed)")
    balance_after: Optional[int] = Field(None, description="Balance after credits added")


class BillingResource:
    """
    Billing client for v1 API.

    Manages credit purchases and billing operations.
    Works with both SimpleCreditProvider (free credits) and CIRISBillingProvider (paid credits).
    """

    def __init__(self, transport: Transport):
        self._transport = transport

    async def get_credits(self) -> CreditStatus:
        """
        Get current credit balance and status.

        Returns:
            CreditStatus with credit balance and purchase options

        Example:
            status = await client.billing.get_credits()
            print(f"Credits remaining: {status.credits_remaining}")
            if status.purchase_required:
                print("Purchase required to continue")
        """
        result = await self._transport.request("GET", "/v1/api/billing/credits")

        if isinstance(result, dict) and "data" in result:
            return CreditStatus(**result["data"])
        assert isinstance(result, dict), "Expected dict response from transport"
        return CreditStatus(**result)

    async def initiate_purchase(self, return_url: Optional[str] = None) -> PurchaseInitiation:
        """
        Initiate credit purchase flow (creates Stripe payment intent).

        Only works when billing is enabled (CIRISBillingProvider).
        Returns error when SimpleCreditProvider is active (billing disabled).

        Args:
            return_url: Optional URL to return to after payment

        Returns:
            PurchaseInitiation with Stripe payment details

        Example:
            purchase = await client.billing.initiate_purchase(
                return_url="https://myapp.com/payment-complete"
            )
            print(f"Payment ID: {purchase.payment_id}")
            print(f"Amount: ${purchase.amount_minor / 100}")
        """
        payload = {}
        if return_url:
            payload["return_url"] = return_url

        result = await self._transport.request("POST", "/v1/api/billing/purchase/initiate", json=payload)

        if isinstance(result, dict) and "data" in result:
            return PurchaseInitiation(**result["data"])
        assert isinstance(result, dict), "Expected dict response from transport"
        return PurchaseInitiation(**result)

    async def get_purchase_status(self, payment_id: str) -> PurchaseStatus:
        """
        Check payment status (for polling after payment).

        Frontend can poll this after initiating payment to confirm credits were added.
        Only works when billing is enabled (CIRISBillingProvider).

        Args:
            payment_id: Payment intent ID from initiate_purchase()

        Returns:
            PurchaseStatus with payment status and credits added

        Example:
            status = await client.billing.get_purchase_status("pi_abc123")
            if status.status == "succeeded":
                print(f"Purchase complete! {status.credits_added} credits added")
                print(f"New balance: {status.balance_after}")
        """
        result = await self._transport.request("GET", f"/v1/api/billing/purchase/status/{payment_id}")

        if isinstance(result, dict) and "data" in result:
            return PurchaseStatus(**result["data"])
        assert isinstance(result, dict), "Expected dict response from transport"
        return PurchaseStatus(**result)
