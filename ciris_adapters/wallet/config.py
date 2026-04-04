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
        default="base-mainnet",
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
# ERC-4337 Paymaster Configuration (Gas Sponsorship)
# =============================================================================


class PaymasterConfig(BaseModel):
    """
    Configuration for ERC-4337 paymaster gas sponsorship.

    Supports two providers:
    - Coinbase Paymaster (recommended for compliance)
    - Etherspot Arka (MIT licensed, self-hostable)

    Regulatory Note: Gas sponsorship is infrastructure expense, not money transmission.
    See FSD/WALLET_REGULATORY_COMPLIANCE.md Section 10.
    """

    enabled: bool = Field(
        default=True,
        description="Enable paymaster for gasless transactions",
    )

    # Provider selection: "coinbase" or "arka"
    provider: str = Field(
        default="coinbase",
        description="Paymaster provider: 'coinbase' (recommended) or 'arka'",
    )

    # Coinbase Paymaster settings
    coinbase_api_key_name: Optional[str] = Field(
        None,
        description="Coinbase CDP API key name",
    )
    coinbase_api_key_secret: Optional[SecretStr] = Field(
        None,
        description="Coinbase CDP API key secret",
    )
    coinbase_base_url: str = Field(
        default="https://api.developer.coinbase.com/rpc/v1/base",
        description="Coinbase RPC endpoint for Base",
    )

    # Arka Paymaster settings (fallback)
    arka_url: str = Field(
        default="https://arka.etherspot.io",
        description="Arka paymaster service URL (or self-hosted instance)",
    )
    arka_api_key: Optional[SecretStr] = Field(
        None,
        description="Arka API key for sponsorship (optional for self-hosted)",
    )

    # Common settings
    bundler_url: str = Field(
        default="https://bundler.etherspot.io/8453",
        description="ERC-4337 bundler URL for Base (chain ID 8453)",
    )
    entrypoint_address: str = Field(
        default="0x5FF137D4b0FDCD49DcA30c7CF57E578a026d2789",
        description="ERC-4337 EntryPoint v0.6 contract address",
    )
    max_gas_limit: int = Field(
        default=500000,
        description="Maximum gas limit for sponsored operations",
    )
    max_priority_fee_gwei: int = Field(
        default=2,
        description="Maximum priority fee in gwei",
    )


# =============================================================================
# Commons Credits Gas Sponsorship Policy
# =============================================================================


class GasSponsorshipPolicyConfig(BaseModel):
    """
    Configuration for Commons Credits gas sponsorship policy.

    No-KYC approach using economic controls:
    1. USDC transfers only (contract + function allowlist)
    2. Minimum $1.00 value (sybil resistance)
    3. Global monthly budget cap

    See FSD/COMMONS_CREDITS.md for full specification.
    """

    enabled: bool = Field(
        default=True,
        description="Enable Commons Credits gas sponsorship",
    )

    # Contract allowlist - only these tokens get sponsored
    allowed_contracts: list[str] = Field(
        default=["0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"],  # USDC on Base
        description="Token contracts eligible for sponsored transfers",
    )

    # Function allowlist - only these ERC-20 functions get sponsored
    # transfer(address,uint256) = 0xa9059cbb
    allowed_functions: list[str] = Field(
        default=["0xa9059cbb"],  # transfer(address,uint256)
        description="Function selectors eligible for sponsorship (4-byte hex)",
    )

    # Minimum transfer value ($1 prevents dust/spam attacks)
    min_transfer_usd: Decimal = Field(
        default=Decimal("1.00"),
        description="Minimum transfer value for sponsorship eligibility",
    )

    # Global monthly budget (caps total exposure, no KYC needed)
    monthly_budget_usd: Decimal = Field(
        default=Decimal("500.00"),
        description="Global monthly gas sponsorship budget in USD",
    )


class BundlerConfig(BaseModel):
    """Configuration for ERC-4337 bundler service."""

    url: str = Field(
        default="https://bundler.etherspot.io/8453",
        description="Bundler JSON-RPC URL",
    )
    timeout_seconds: int = Field(
        default=60,
        description="Timeout for bundler requests",
    )
    retry_attempts: int = Field(
        default=3,
        description="Number of retry attempts for failed submissions",
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
            "EUR": "wise",  # Default for EUR transfers
            "GBP": "wise",  # Default for GBP transfers
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
