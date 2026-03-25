"""
CIRIS Wallet Adapter.

Generic money tools that work across crypto (x402/USDC) and fiat (Chapa/ETB) providers.

Tools:
- send_money: Send money to any recipient
- request_money: Create payment requests/invoices
- get_statement: Check balance, history, and account details

The implementation details (crypto vs fiat) are abstracted behind currency
and provider_params, enabling a unified interface for all payment operations.
"""

from .adapter import Adapter, WalletAdapter
from .config import ChapaProviderConfig, WalletAdapterConfig, X402ProviderConfig
from .schemas import (
    AccountDetails,
    AccountStatement,
    Balance,
    PaymentRequest,
    PaymentRequestStatus,
    PaymentVerification,
    Transaction,
    TransactionResult,
    TransactionStatus,
    TransactionType,
)
from .tool_service import WalletToolService

__all__ = [
    # Adapter
    "Adapter",
    "WalletAdapter",
    "WalletToolService",
    # Config
    "WalletAdapterConfig",
    "X402ProviderConfig",
    "ChapaProviderConfig",
    # Schemas
    "Transaction",
    "TransactionResult",
    "TransactionType",
    "TransactionStatus",
    "PaymentRequest",
    "PaymentRequestStatus",
    "PaymentVerification",
    "Balance",
    "AccountDetails",
    "AccountStatement",
]
