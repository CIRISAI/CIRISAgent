"""
Wallet Adapter Configuration.

Configuration models for the wallet adapter and its providers.
"""

from decimal import Decimal
from typing import Dict, Optional

from pydantic import BaseModel, Field, SecretStr


class SpendingLimits(BaseModel):
    """Spending limits for wallet operations."""

    max_transaction: Decimal = Field(
        default=Decimal("100.00"),
        description="Maximum amount per transaction",
    )
    daily_limit: Decimal = Field(
        default=Decimal("1000.00"),
        description="Maximum daily spending",
    )
    session_limit: Decimal = Field(
        default=Decimal("500.00"),
        description="Maximum spending per session",
    )


class X402ProviderConfig(BaseModel):
    """Configuration for the x402/USDC provider."""

    enabled: bool = Field(default=True, description="Whether x402 provider is enabled")
    network: str = Field(
        default="base-sepolia",
        description="EVM network (base-mainnet or base-sepolia)",
    )
    treasury_address: Optional[str] = Field(
        None,
        description="Treasury wallet address for receiving payments",
    )
    facilitator_url: str = Field(
        default="https://x402.org/facilitator",
        description="x402 facilitator URL",
    )
    # Key derivation uses CIRISVerify Ed25519 key, not stored here


class ChapaProviderConfig(BaseModel):
    """Configuration for the Chapa/ETB provider."""

    enabled: bool = Field(default=True, description="Whether Chapa provider is enabled")
    secret_key: Optional[SecretStr] = Field(
        None,
        description="Chapa API secret key",
    )
    callback_base_url: Optional[str] = Field(
        None,
        description="Base URL for payment callbacks",
    )
    merchant_name: str = Field(
        default="CIRIS",
        description="Merchant name shown to payers",
    )


class WalletAdapterConfig(BaseModel):
    """Configuration for the WalletAdapter."""

    # Provider configurations
    x402: X402ProviderConfig = Field(
        default_factory=X402ProviderConfig,
        description="x402/USDC provider configuration",
    )
    chapa: ChapaProviderConfig = Field(
        default_factory=ChapaProviderConfig,
        description="Chapa/ETB provider configuration",
    )

    # Currency to provider mapping
    currency_providers: Dict[str, str] = Field(
        default={
            "USDC": "x402",
            "ETH": "x402",
            "ETB": "chapa",
            "KES": "mpesa",  # Future
            "NGN": "flutterwave",  # Future
        },
        description="Default provider for each currency",
    )

    # Spending limits
    spending_limits: SpendingLimits = Field(
        default_factory=SpendingLimits,
        description="Spending limits for outbound payments",
    )

    # Attestation requirements (for x402 crypto operations)
    min_attestation_level: int = Field(
        default=3,
        ge=0,
        le=5,
        description="Minimum CIRISVerify attestation level for transactions",
    )

    # Default provider when currency doesn't specify
    default_provider: str = Field(
        default="x402",
        description="Default provider when currency not in mapping",
    )
