"""
Wallet Providers.

Provider implementations for different payment rails:
- x402: USDC on Base L2 via x402 protocol
- chapa: Ethiopian Birr via Chapa gateway
- (future) mpesa: Kenyan Shilling via M-Pesa
- (future) flutterwave: Nigerian Naira via Flutterwave
"""

from .base import WalletProvider

__all__ = ["WalletProvider"]
