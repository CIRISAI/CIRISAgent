"""
Wallet Adapter Configuration.

Configuration models for the wallet adapter and its providers.
Providers are lazy-loaded, so only import configs when needed.
"""

from decimal import Decimal
from typing import Any, Dict, Optional

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


# =============================================================================
# Provider Configurations - Each provider has its own config class
# =============================================================================


class X402ProviderConfig(BaseModel):
    """Configuration for the x402/USDC provider (Base L2)."""

    enabled: bool = Field(default=False, description="Whether x402 provider is enabled")
    network: str = Field(
        default="base-sepolia",
        description="EVM network (base-mainnet or base-sepolia)",
    )
    rpc_url: Optional[str] = Field(
        None,
        description="Custom RPC URL (uses public Base RPC if not specified)",
    )
    treasury_address: Optional[str] = Field(
        None,
        description="Treasury wallet address for receiving payments",
    )
    facilitator_url: str = Field(
        default="https://x402.org/facilitator",
        description="x402 facilitator URL",
    )


class ChapaProviderConfig(BaseModel):
    """Configuration for the Chapa/ETB provider (Ethiopia)."""

    enabled: bool = Field(default=False, description="Whether Chapa provider is enabled")
    secret_key: Optional[SecretStr] = Field(
        None,
        description="Chapa API secret key (CHASECK_*)",
    )
    callback_base_url: Optional[str] = Field(
        None,
        description="Base URL for payment callbacks",
    )
    merchant_name: str = Field(
        default="CIRIS",
        description="Merchant name shown to payers",
    )


class MPesaProviderConfig(BaseModel):
    """Configuration for M-Pesa/Daraja provider (Kenya/Africa)."""

    enabled: bool = Field(default=False, description="Whether M-Pesa provider is enabled")
    consumer_key: Optional[SecretStr] = Field(
        None,
        description="Daraja API consumer key",
    )
    consumer_secret: Optional[SecretStr] = Field(
        None,
        description="Daraja API consumer secret",
    )
    shortcode: Optional[str] = Field(
        None,
        description="Business shortcode (Paybill/Till number)",
    )
    passkey: Optional[SecretStr] = Field(
        None,
        description="Lipa Na M-Pesa passkey",
    )
    initiator_name: str = Field(
        default="testapi",
        description="Initiator name for B2C operations",
    )
    environment: str = Field(
        default="sandbox",
        description="Environment: sandbox or production",
    )
    callback_base_url: Optional[str] = Field(
        None,
        description="Base URL for M-Pesa callbacks",
    )


class RazorpayProviderConfig(BaseModel):
    """Configuration for Razorpay/UPI provider (India)."""

    enabled: bool = Field(default=False, description="Whether Razorpay provider is enabled")
    key_id: Optional[SecretStr] = Field(
        None,
        description="Razorpay Key ID",
    )
    key_secret: Optional[SecretStr] = Field(
        None,
        description="Razorpay Key Secret",
    )
    webhook_secret: Optional[SecretStr] = Field(
        None,
        description="Webhook signature secret",
    )
    account_number: Optional[str] = Field(
        None,
        description="Virtual account number for UPI collect",
    )


class PIXProviderConfig(BaseModel):
    """Configuration for PIX provider (Brazil)."""

    enabled: bool = Field(default=False, description="Whether PIX provider is enabled")
    provider: str = Field(
        default="mercadopago",
        description="PIX aggregator: mercadopago, stripe, or ebanx",
    )
    access_token: Optional[SecretStr] = Field(
        None,
        description="Provider access token",
    )
    client_id: Optional[str] = Field(
        None,
        description="OAuth client ID (if using OAuth flow)",
    )
    client_secret: Optional[SecretStr] = Field(
        None,
        description="OAuth client secret",
    )
    callback_base_url: Optional[str] = Field(
        None,
        description="Base URL for payment callbacks",
    )
    pix_key: Optional[str] = Field(
        None,
        description="PIX key for receiving (CPF, CNPJ, email, phone, or EVP)",
    )


class WiseProviderConfig(BaseModel):
    """Configuration for Wise provider (Global transfers)."""

    enabled: bool = Field(default=False, description="Whether Wise provider is enabled")
    api_token: Optional[SecretStr] = Field(
        None,
        description="Wise API token (Personal or OAuth)",
    )
    profile_id: Optional[str] = Field(
        None,
        description="Wise profile ID (personal or business)",
    )
    environment: str = Field(
        default="sandbox",
        description="Environment: sandbox or production",
    )
    webhook_secret: Optional[SecretStr] = Field(
        None,
        description="Webhook signature secret",
    )


class StripeProviderConfig(BaseModel):
    """Configuration for Stripe provider (Global cards)."""

    enabled: bool = Field(default=False, description="Whether Stripe provider is enabled")
    secret_key: Optional[SecretStr] = Field(
        None,
        description="Stripe secret key (sk_live_* or sk_test_*)",
    )
    publishable_key: Optional[str] = Field(
        None,
        description="Stripe publishable key (pk_*)",
    )
    webhook_secret: Optional[SecretStr] = Field(
        None,
        description="Webhook signing secret (whsec_*)",
    )
    connect_account_id: Optional[str] = Field(
        None,
        description="Connected account ID for Stripe Connect (acct_*)",
    )


# =============================================================================
# Main Wallet Configuration
# =============================================================================


class WalletAdapterConfig(BaseModel):
    """Configuration for the WalletAdapter with lazy-loaded providers."""

    # Provider configurations - keyed by provider name
    # Only enabled providers are loaded into memory
    provider_configs: Dict[str, Any] = Field(
        default_factory=dict,
        description="Provider configurations keyed by name (x402, chapa, mpesa, etc.)",
    )

    # Currency to provider mapping
    currency_providers: Dict[str, str] = Field(
        default={
            "USDC": "x402",
            "ETH": "x402",
            "ETB": "chapa",
            "KES": "mpesa",
            "INR": "razorpay",
            "BRL": "pix",
            "USD": "stripe",  # Default for USD card payments
            "EUR": "wise",    # Default for EUR transfers
            "GBP": "wise",    # Default for GBP transfers
        },
        description="Default provider for each currency",
    )

    # Spending limits
    spending_limits: SpendingLimits = Field(
        default_factory=SpendingLimits,
        description="Spending limits for outbound payments",
    )

    # Attestation requirements (for crypto operations)
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
