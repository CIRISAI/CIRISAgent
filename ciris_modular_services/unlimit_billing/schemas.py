"""Schema definitions for the Unlimit billing module."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .ap2 import (
    AP2CheckoutPayload,
    AP2Mandate,
    AP2MandateChain,
    AP2MandateType,
    AP2PaymentMethod,
    AP2PaymentMethodType,
    AP2Proof,
)


class PaymentMethod(str, Enum):
    """Supported non-crypto payment method families."""

    CARD = "BANKCARD"
    BANK = "BANK_TRANSFER"
    WALLET = "WALLET"
    CASH = "CASH"
    PAYPAL = "PAYPAL"


class PaymentCustomer(BaseModel):
    """Minimal customer details for pay-ins."""

    email: Optional[str] = Field(None, description="Customer email address")
    phone: Optional[str] = Field(None, description="Customer phone number")
    full_name: Optional[str] = Field(None, description="Customer full name")
    country: Optional[str] = Field(None, description="ISO-3166 alpha-2 country code")

class BillingIdentity(BaseModel):
    """Identity information that Unlimit uses to look up balances."""

    oauth_provider: str = Field(..., description="OAuth provider identifier (e.g., 'google')")
    external_id: str = Field(..., description="Provider-scoped user identifier")
    wa_id: Optional[str] = Field(None, description="Wise Authority identifier when available")
    tenant_id: Optional[str] = Field(None, description="Optional tenant/group identifier")

    def cache_key(self) -> str:
        """Return a deterministic cache key for this identity."""
        tenant_part = self.tenant_id or "global"
        return f"{self.oauth_provider}:{self.external_id}:{tenant_part}"


class BillingContext(BaseModel):
    """Additional context captured during billing checks."""

    agent_id: Optional[str] = Field(None, description="Agent performing the interaction")
    channel_id: Optional[str] = Field(None, description="Interaction channel identifier")
    request_id: Optional[str] = Field(None, description="Request correlation ID")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Arbitrary key-value metadata")


class BillingCheckResult(BaseModel):
    """Result payload returned after contacting Unlimit."""

    has_balance: bool = Field(..., description="Whether the user has sufficient credits")
    credits_remaining: Optional[int] = Field(None, description="Remaining credits if reported by Unlimit")
    expires_at: Optional[datetime] = Field(None, description="Credit expiration timestamp")
    plan_name: Optional[str] = Field(None, description="Plan or product name")
    reason: Optional[str] = Field(None, description="Reason for denial or failure")
    provider_metadata: Dict[str, str] = Field(
        default_factory=dict,
        description="Additional fields supplied by Unlimit",
    )


class BillingChargeRequest(BaseModel):
    """Parameters describing a charge/spend attempt."""

    amount_minor: int = Field(..., ge=1, description="Charge amount in minor currency units (e.g., cents)")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO-4217 currency code")
    description: Optional[str] = Field(None, description="Human readable description of the charge")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Provider metadata for reconciliation")


class BillingChargeResult(BaseModel):
    """Outcome of a charge/spend attempt."""

    succeeded: bool = Field(..., description="Whether the charge succeeded")
    transaction_id: Optional[str] = Field(None, description="Provider transaction identifier")
    balance_remaining: Optional[int] = Field(None, description="Balance remaining in minor units if provided")
    reason: Optional[str] = Field(None, description="Failure or contextual reason")
    provider_metadata: Dict[str, str] = Field(
        default_factory=dict,
        description="Additional provider fields for auditing",
    )


class AP2CheckoutRequest(BaseModel):
    """Incoming request payload for AP2 checkout tool."""

    identity: BillingIdentity = Field(..., description="Identity being charged")
    charge: BillingChargeRequest = Field(..., description="Charge parameters")
    ap2: AP2CheckoutPayload = Field(..., description="AP2-specific payload including mandates")
    context: Optional[BillingContext] = Field(None, description="Optional interaction context")


class AP2InvoiceDetails(BaseModel):
    """Additional invoice information for AP2 invoice tool."""

    request_id: str = Field(..., description="Idempotent invoice request identifier")
    description: str = Field(..., description="Invoice description")
    items: List[InvoiceItem] = Field(default_factory=list, description="Optional invoice items")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional merchant metadata")


class AP2InvoiceRequest(AP2CheckoutRequest):
    """AP2 request payload for invoice creation."""

    invoice: AP2InvoiceDetails = Field(..., description="Invoice-specific details")
    customer: PaymentCustomer = Field(default_factory=PaymentCustomer, description="Customer paying the invoice")


class PaymentRequest(BaseModel):
    """Request to create a payment via Unlimit pay-in API."""

    request_id: str = Field(..., description="Idempotent request identifier")
    description: str = Field(..., description="Order description")
    amount: float = Field(..., ge=0.01, description="Payment amount in major units")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO currency code")
    payment_method: PaymentMethod = Field(..., description="Payment method type")
    customer: PaymentCustomer = Field(default_factory=PaymentCustomer, description="Customer information")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Merchant metadata")


class PaymentResult(BaseModel):
    """Outcome of a payment creation request."""

    succeeded: bool = Field(..., description="Whether the payment was accepted")
    payment_id: Optional[str] = Field(None, description="Unlimit payment identifier")
    status: Optional[str] = Field(None, description="Payment status as reported by Unlimit")
    redirect_url: Optional[str] = Field(None, description="Hosted payment page URL, if provided")
    reason: Optional[str] = Field(None, description="Failure reason when not successful")
    provider_metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw provider data")


class InvoiceItem(BaseModel):
    """Line item for an invoice."""

    name: str = Field(..., description="Item name")
    quantity: int = Field(..., ge=1, description="Number of units")
    unit_price: float = Field(..., ge=0.0, description="Unit price in major units")


class InvoiceRequest(BaseModel):
    """Request to create an invoice/hosted payment link."""

    request_id: str = Field(..., description="Idempotent request identifier")
    description: str = Field(..., description="Invoice description")
    amount: float = Field(..., ge=0.01, description="Total amount in major units")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO currency code")
    customer: PaymentCustomer = Field(default_factory=PaymentCustomer, description="Customer information")
    items: List[InvoiceItem] = Field(default_factory=list, description="Optional line items")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Merchant metadata")


class InvoiceResult(BaseModel):
    """Outcome of invoice creation."""

    succeeded: bool = Field(..., description="Whether the invoice was created")
    invoice_id: Optional[str] = Field(None, description="Invoice identifier")
    status: Optional[str] = Field(None, description="Invoice status")
    payment_url: Optional[str] = Field(None, description="Hosted payment link")
    reason: Optional[str] = Field(None, description="Failure reason")
    provider_metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw provider data")


class RefundRequest(BaseModel):
    """Refund request details."""

    payment_id: str = Field(..., description="Original payment identifier")
    request_id: str = Field(..., description="Idempotent request identifier")
    amount: Optional[float] = Field(None, ge=0.01, description="Refund amount in major units")
    currency: Optional[str] = Field(None, min_length=3, max_length=3, description="Currency for refund")
    reason: Optional[str] = Field(None, description="Reason for refund")


class RefundResult(BaseModel):
    """Outcome of a refund request."""

    succeeded: bool = Field(..., description="Whether the refund was accepted")
    refund_id: Optional[str] = Field(None, description="Refund identifier")
    status: Optional[str] = Field(None, description="Refund status")
    reason: Optional[str] = Field(None, description="Failure reason")
    provider_metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw provider data")


class PayoutBeneficiary(BaseModel):
    """Beneficiary information for payouts."""

    name: str = Field(..., description="Beneficiary full name")
    account_number: str = Field(..., description="Bank or wallet account number")
    bank_code: Optional[str] = Field(None, description="Bank identifier/BIC")
    country: str = Field(..., description="ISO-3166 alpha-2 country")


class PayoutRequest(BaseModel):
    """Request to send funds from Unlimit account."""

    request_id: str = Field(..., description="Idempotent request identifier")
    amount: float = Field(..., ge=0.01, description="Amount in major units")
    currency: str = Field(..., min_length=3, max_length=3, description="Currency")
    description: str = Field(..., description="Payout description")
    beneficiary: PayoutBeneficiary = Field(..., description="Payout beneficiary")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Merchant metadata")


class PayoutResult(BaseModel):
    """Outcome of a payout request."""

    succeeded: bool = Field(..., description="Whether the payout was accepted")
    payout_id: Optional[str] = Field(None, description="Payout identifier")
    status: Optional[str] = Field(None, description="Payout status")
    reason: Optional[str] = Field(None, description="Failure reason")
    provider_metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw provider data")


class ReportEntry(BaseModel):
    """Individual report item."""

    reference_id: str = Field(..., description="Payment or payout reference")
    kind: str = Field(..., description="Type of operation")
    amount: float = Field(..., description="Amount in major units")
    currency: str = Field(..., description="Currency code")
    created_at: datetime = Field(..., description="Timestamp of the event")
    status: str = Field(..., description="Operation status")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Provider metadata")


class ReportQuery(BaseModel):
    """Query parameters for reports."""

    date_from: datetime = Field(..., description="Start of reporting period")
    date_to: datetime = Field(..., description="End of reporting period")
    kind: Optional[str] = Field(None, description="Filter by operation type")
    limit: int = Field(100, ge=1, le=1000, description="Max results")


__all__ = [
    "BillingIdentity",
    "BillingContext",
    "BillingCheckResult",
    "BillingChargeRequest",
    "BillingChargeResult",
    "AP2CheckoutRequest",
    "AP2InvoiceDetails",
    "AP2InvoiceRequest",
    "AP2CheckoutPayload",
    "AP2Mandate",
    "AP2MandateChain",
    "AP2MandateType",
    "AP2PaymentMethod",
    "AP2PaymentMethodType",
    "AP2Proof",
    "PaymentMethod",
    "PaymentCustomer",
    "PaymentRequest",
    "PaymentResult",
    "InvoiceItem",
    "InvoiceRequest",
    "InvoiceResult",
    "RefundRequest",
    "RefundResult",
    "PayoutBeneficiary",
    "PayoutRequest",
    "PayoutResult",
    "ReportEntry",
    "ReportQuery",
]
