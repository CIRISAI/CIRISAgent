"""
Wallet Adapter Schemas.

Pydantic models for wallet transactions, balances, and account details.
These are provider-agnostic - both crypto and fiat providers use the same models.
"""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class TransactionType(str, Enum):
    """Type of wallet transaction."""

    SEND = "send"
    RECEIVE = "receive"
    REQUEST = "request"
    REFUND = "refund"
    FEE = "fee"


class TransactionStatus(str, Enum):
    """Status of a wallet transaction."""

    PENDING = "pending"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"
    REFUNDED = "refunded"


class PaymentRequestStatus(str, Enum):
    """Status of a payment request."""

    PENDING = "pending"
    PAID = "paid"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class Transaction(BaseModel):
    """A wallet transaction (send or receive)."""

    transaction_id: str = Field(..., description="Unique transaction identifier")
    provider: str = Field(..., description="Provider that processed the transaction")
    type: TransactionType = Field(..., description="Transaction type")
    status: TransactionStatus = Field(..., description="Transaction status")
    amount: Decimal = Field(..., description="Transaction amount (negative for sends)")
    currency: str = Field(..., description="Currency code (USDC, ETB, KES, etc.)")
    recipient: Optional[str] = Field(None, description="Recipient address/phone/username")
    sender: Optional[str] = Field(None, description="Sender address/phone/username")
    memo: Optional[str] = Field(None, description="Transaction memo/description")
    timestamp: datetime = Field(..., description="Transaction timestamp")
    fees: Optional[Dict[str, Decimal]] = Field(None, description="Fee breakdown")
    confirmation: Optional[Dict[str, Any]] = Field(None, description="Provider-specific confirmation data")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional provider-specific metadata")


class TransactionResult(BaseModel):
    """Result of a send_money operation."""

    success: bool = Field(..., description="Whether the transaction succeeded")
    transaction_id: Optional[str] = Field(None, description="Transaction ID if successful")
    provider: str = Field(..., description="Provider used")
    amount: Decimal = Field(..., description="Amount sent")
    currency: str = Field(..., description="Currency code")
    recipient: str = Field(..., description="Recipient address/phone")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    fees: Optional[Dict[str, Decimal]] = Field(None, description="Fee breakdown")
    confirmation: Optional[Dict[str, Any]] = Field(None, description="Confirmation data")
    error: Optional[str] = Field(None, description="Error message if failed")


class PaymentRequest(BaseModel):
    """A payment request/invoice."""

    request_id: str = Field(..., description="Unique request identifier")
    provider: str = Field(..., description="Provider handling the request")
    amount: Decimal = Field(..., description="Requested amount")
    currency: str = Field(..., description="Currency code")
    description: str = Field(..., description="What the payment is for")
    status: PaymentRequestStatus = Field(default=PaymentRequestStatus.PENDING, description="Request status")
    checkout_url: Optional[str] = Field(None, description="URL for payer to complete payment")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = Field(None, description="When request expires")
    paid_at: Optional[datetime] = Field(None, description="When payment was received")
    transaction_id: Optional[str] = Field(None, description="Transaction ID once paid")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class Balance(BaseModel):
    """Account balance information."""

    currency: str = Field(..., description="Currency code")
    available: Decimal = Field(..., description="Available balance")
    pending: Decimal = Field(default=Decimal("0"), description="Pending balance")
    total: Decimal = Field(..., description="Total balance (available + pending)")
    metadata: Optional[Dict[str, Any]] = Field(
        None, description="Additional balance metadata (e.g., eth_balance for gas)"
    )


class AccountDetails(BaseModel):
    """Account details for a provider."""

    provider: str = Field(..., description="Provider identifier")
    currency: str = Field(..., description="Primary currency")
    address: Optional[str] = Field(None, description="Wallet address (crypto)")
    phone: Optional[str] = Field(None, description="Phone number (mobile money)")
    account_id: Optional[str] = Field(None, description="Account identifier")
    network: Optional[str] = Field(None, description="Network (e.g., base-mainnet)")
    attestation_level: Optional[int] = Field(None, description="CIRISVerify attestation level (0-5)")
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional details")


class AccountStatement(BaseModel):
    """Full account statement with balance, history, and details."""

    provider: str = Field(..., description="Provider identifier")
    currency: str = Field(..., description="Primary currency")
    balance: Optional[Balance] = Field(None, description="Current balance")
    details: Optional[AccountDetails] = Field(None, description="Account details")
    history: Optional[List[Transaction]] = Field(None, description="Transaction history")


class PaymentVerification(BaseModel):
    """Result of verifying a payment."""

    verified: bool = Field(..., description="Whether payment is verified")
    status: TransactionStatus = Field(..., description="Payment status")
    transaction_id: Optional[str] = Field(None, description="Transaction ID if found")
    amount: Optional[Decimal] = Field(None, description="Payment amount")
    currency: Optional[str] = Field(None, description="Currency")
    timestamp: Optional[datetime] = Field(None, description="Payment timestamp")
    error: Optional[str] = Field(None, description="Error if verification failed")


# =============================================================================
# Gas Sponsorship Schemas (Commons Credits)
# =============================================================================


class SponsorshipEligibility(BaseModel):
    """
    Result of gas sponsorship eligibility check.

    Part of the Commons Credits system - see FSD/COMMONS_CREDITS.md
    """

    eligible: bool = Field(..., description="Whether transaction qualifies for gas sponsorship")
    reason: str = Field(..., description="Human-readable explanation")
    budget_remaining_usd: Optional[Decimal] = Field(None, description="Remaining monthly sponsorship budget in USD")
    estimated_gas_usd: Optional[Decimal] = Field(None, description="Estimated gas cost for this transaction")


class SponsorshipPolicy(BaseModel):
    """
    Gas sponsorship policy configuration.

    Rules (No KYC):
    1. USDC transfers only (contract allowlist)
    2. Minimum $1.00 value (economic sybil resistance)
    3. Global monthly budget cap

    See FSD/COMMONS_CREDITS.md for rationale.
    """

    # USDC on Base mainnet
    USDC_BASE_ADDRESS: str = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    USDC_DECIMALS: int = 6

    min_transfer_usd: Decimal = Field(
        default=Decimal("1.00"),
        description="Minimum transfer value for sponsorship ($1 default)",
    )
    monthly_budget_usd: Decimal = Field(
        default=Decimal("500.00"),
        description="Global monthly gas sponsorship budget",
    )
    allowed_contracts: List[str] = Field(
        default_factory=lambda: ["0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"],
        description="Token contracts eligible for sponsored transfers",
    )

    @property
    def min_transfer_raw(self) -> int:
        """Minimum transfer in raw USDC units (6 decimals)."""
        return int(self.min_transfer_usd * Decimal(10**self.USDC_DECIMALS))


class SponsorshipBudgetStatus(BaseModel):
    """Current status of the gas sponsorship budget."""

    month: str = Field(..., description="Current month (YYYY-MM)")
    budget_usd: Decimal = Field(..., description="Total monthly budget")
    spent_usd: Decimal = Field(..., description="Amount spent this month")
    remaining_usd: Decimal = Field(..., description="Remaining budget")
    utilization_percent: Decimal = Field(..., description="Budget utilization percentage")
    transactions_sponsored: int = Field(..., description="Number of sponsored transactions")
    is_exhausted: bool = Field(..., description="Whether budget is exhausted")
