"""Schema definitions for the Unlimit billing module."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

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


__all__ = [
    "BillingIdentity",
    "BillingContext",
    "BillingCheckResult",
    "BillingChargeRequest",
    "BillingChargeResult",
    "AP2CheckoutRequest",
    "AP2CheckoutPayload",
    "AP2Mandate",
    "AP2MandateChain",
    "AP2MandateType",
    "AP2PaymentMethod",
    "AP2PaymentMethodType",
    "AP2Proof",
]
