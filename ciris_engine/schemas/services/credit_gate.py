"""Schemas for external credit gating services."""

from __future__ import annotations

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, Field


class CreditAccount(BaseModel):
    """Account reference used when querying external credit providers."""

    provider: str = Field(..., description="Provider namespace (e.g., 'oauth:google', 'app:internal')")
    account_id: str = Field(..., description="Identifier scoped to the provider")
    authority_id: Optional[str] = Field(None, description="Optional governance or Wise Authority identifier")
    tenant_id: Optional[str] = Field(None, description="Tenant/group identifier when deploying multi-tenant")

    def cache_key(self) -> str:
        """Return deterministic cache key for memoized decisions."""
        tenant_part = self.tenant_id or "global"
        authority_part = self.authority_id or "anon"
        return f"{self.provider}:{self.account_id}:{authority_part}:{tenant_part}"


class CreditContext(BaseModel):
    """Lightweight context captured alongside a credit decision."""

    agent_id: Optional[str] = Field(None, description="Agent performing the interaction")
    channel_id: Optional[str] = Field(None, description="Interaction channel identifier")
    request_id: Optional[str] = Field(None, description="Request correlation ID")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Auxiliary metadata for audits")


class CreditCheckResult(BaseModel):
    """Outcome returned from the credit provider after a balance check."""

    has_credit: bool = Field(..., description="Whether the account has sufficient credit to proceed")
    credits_remaining: Optional[int] = Field(None, description="Remaining credits in provider-specific units")
    expires_at: Optional[datetime] = Field(None, description="Optional expiration timestamp for the credit window")
    plan_name: Optional[str] = Field(None, description="Plan or product name reported by the provider")
    reason: Optional[str] = Field(None, description="Provider-supplied reason for denial or failure")
    provider_metadata: Dict[str, str] = Field(
        default_factory=dict,
        description="Additional provider fields for downstream auditing",
    )


class CreditSpendRequest(BaseModel):
    """Parameters describing a credit spend attempt."""

    amount_minor: int = Field(..., ge=1, description="Amount in provider minor units (e.g., cents)")
    currency: str = Field(..., min_length=3, max_length=3, description="ISO-4217 currency code")
    description: Optional[str] = Field(None, description="Human-readable description of the spend")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Provider metadata for reconciliation")


class CreditSpendResult(BaseModel):
    """Outcome of a credit spend attempt."""

    succeeded: bool = Field(..., description="Whether the spend was accepted by the provider")
    transaction_id: Optional[str] = Field(None, description="Provider transaction identifier")
    balance_remaining: Optional[int] = Field(None, description="Remaining balance in minor units if available")
    reason: Optional[str] = Field(None, description="Failure or contextual information returned by provider")
    provider_metadata: Dict[str, str] = Field(
        default_factory=dict,
        description="Additional provider fields for auditing",
    )


__all__ = [
    "CreditAccount",
    "CreditContext",
    "CreditCheckResult",
    "CreditSpendRequest",
    "CreditSpendResult",
]
