"""AP2 (Agent Payments Protocol) schema definitions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, HttpUrl


class AP2MandateType(str, Enum):
    """Mandate types recognised by AP2."""

    INTENT = "intent"
    CART = "cart"


class AP2Mandate(BaseModel):
    """Mandate describing authorised instructions in AP2."""

    mandate_id: str = Field(..., description="Unique identifier for the mandate")
    mandate_type: AP2MandateType = Field(..., description="Type of the mandate")
    version: str = Field("1.0", description="Mandate schema version")
    issued_at: datetime = Field(..., description="When the mandate was issued")
    expires_at: Optional[datetime] = Field(None, description="When the mandate expires, if ever")
    amount_minor: Optional[int] = Field(
        None, ge=0, description="Authorised amount in minor currency units (e.g., cents)"
    )
    currency: Optional[str] = Field(None, min_length=3, max_length=3, description="ISO-4217 currency code")
    instructions: Dict[str, str] = Field(default_factory=dict, description="Human-readable mandate instructions")
    constraints: Dict[str, str] = Field(default_factory=dict, description="Constraint metadata")
    credential_reference: Optional[str] = Field(
        None, description="Identifier of the credential that signed this mandate"
    )
    signature: str = Field(..., description="Detached signature over the mandate contents")


class AP2Credential(BaseModel):
    """Verifiable credential associated with a mandate."""

    credential_id: str = Field(..., description="Unique credential identifier")
    issuer: str = Field(..., description="Entity issuing the credential")
    subject: str = Field(..., description="Credential subject (agent or user)")
    issued_at: datetime = Field(..., description="When the credential was issued")
    expires_at: Optional[datetime] = Field(None, description="When the credential expires")
    proof_type: str = Field(..., description="Type of proof used for the credential")
    proof_value: str = Field(..., description="Encoded proof value")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional credential metadata")


class AP2PaymentMethodType(str, Enum):
    """Supported payment method families."""

    CARD = "card"
    BANK = "bank_transfer"
    STABLECOIN = "stablecoin"
    CRYPTO = "crypto"
    WALLET = "wallet"


class AP2PaymentMethod(BaseModel):
    """Payment method details linked to the mandate."""

    method_type: AP2PaymentMethodType = Field(..., description="Payment method family")
    provider: Optional[str] = Field(None, description="Provider or network identifier")
    network: Optional[str] = Field(None, description="Card or blockchain network")
    payment_token: str = Field(..., description="Opaque token referencing the payment method")
    display_name: Optional[str] = Field(None, description="Masked representation for auditing")
    linked_mandate_id: Optional[str] = Field(None, description="Mandate this payment method is authorised for")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional payment metadata")


class AP2MandateChain(BaseModel):
    """Mandate chain required for AP2 transactions."""

    intent: AP2Mandate = Field(..., description="Intent mandate describing user request")
    cart: AP2Mandate = Field(..., description="Cart mandate describing final purchase")
    credentials: List[AP2Credential] = Field(
        default_factory=list, description="Credentials that sign or support the mandates"
    )


class AP2Proof(BaseModel):
    """Proof artefact binding the payment method to the mandate."""

    proof_type: str = Field(..., description="Proof type (e.g., jw3c, zkp)")
    proof_value: str = Field(..., description="Encoded proof payload")
    verification_service: Optional[HttpUrl] = Field(
        None, description="Optional service that can verify the proof"
    )
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional proof metadata")


class AP2CheckoutPayload(BaseModel):
    """Complete AP2 payload required to execute a payment."""

    mandates: AP2MandateChain = Field(..., description="Mandate chain for the purchase")
    payment_method: AP2PaymentMethod = Field(..., description="Payment method details")
    proof: Optional[AP2Proof] = Field(None, description="Proof linking mandates to payment method")
    metadata: Dict[str, str] = Field(default_factory=dict, description="AP2 metadata for auditing")


__all__ = [
    "AP2MandateType",
    "AP2Mandate",
    "AP2Credential",
    "AP2PaymentMethodType",
    "AP2PaymentMethod",
    "AP2MandateChain",
    "AP2Proof",
    "AP2CheckoutPayload",
]
