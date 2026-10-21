"""
Wallet Providers - Lazy Loaded.

Provider implementations for different payment rails:
- x402: USDC on Base L2 via x402 protocol
- chapa: Ethiopian Birr (ETB) via Chapa gateway
- mpesa: Kenyan Shilling (KES) via M-Pesa Daraja API
- razorpay: Indian Rupee (INR) via Razorpay/UPI
- pix: Brazilian Real (BRL) via PIX/Mercado Pago
- wise: Global transfers via Wise API
- stripe: Global card payments via Stripe Connect

Gas sponsorship (Commons Credits):
- sponsorship_policy: No-KYC eligibility rules
- coinbase_paymaster: Coinbase CDP paymaster client
- paymaster_client: Etherspot Arka paymaster client

Providers are lazy-loaded via the registry to minimize memory usage.
Only import the registry and base class here - providers load on demand.
"""

from .base import WalletProvider
from .registry import (
    ProviderLoadError,
    create_provider,
    get_available_providers,
    get_loaded_providers,
    get_provider_class,
    is_provider_available,
)

# Gas sponsorship exports (Commons Credits)
from .sponsorship_policy import (
    SponsorshipPolicy,
    SponsorshipPolicyConfig,
    get_sponsorship_policy,
    reset_sponsorship_policy,
)

__all__ = [
    # Provider infrastructure
    "WalletProvider",
    "ProviderLoadError",
    "create_provider",
    "get_available_providers",
    "get_loaded_providers",
    "get_provider_class",
    "is_provider_available",
    # Gas sponsorship (Commons Credits)
    "SponsorshipPolicy",
    "SponsorshipPolicyConfig",
    "get_sponsorship_policy",
    "reset_sponsorship_policy",
]
