"""
Wallet Provider Protocol.

Base protocol that all wallet providers must implement.
This enables provider-agnostic money operations across crypto and fiat rails.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from ..schemas import AccountDetails, Balance, PaymentRequest, PaymentVerification, Transaction, TransactionResult


class WalletProvider(ABC):
    """
    Abstract base class for wallet providers.

    All wallet providers (x402, Chapa, M-Pesa, etc.) must implement this interface.
    This enables the WalletToolService to work with any provider through the same
    generic tools (send_money, request_money, get_statement).

    Providers handle the specifics of their payment rail:
    - x402: USDC transactions on Base L2 via x402 protocol
    - Chapa: ETB transactions via Telebirr, CBE Birr, bank transfer
    - M-Pesa: KES transactions via Safaricom (future)
    - etc.
    """

    @property
    @abstractmethod
    def provider_id(self) -> str:
        """
        Unique provider identifier.

        Examples: 'x402', 'chapa', 'mpesa', 'flutterwave'
        """
        ...

    @property
    @abstractmethod
    def supported_currencies(self) -> List[str]:
        """
        List of supported currency codes.

        Examples:
        - x402: ['USDC', 'ETH']
        - Chapa: ['ETB']
        - M-Pesa: ['KES']
        """
        ...

    @abstractmethod
    async def initialize(self) -> bool:
        """
        Initialize the provider.

        Called during adapter startup. Should establish connections,
        verify credentials, etc.

        Returns:
            True if initialization successful, False otherwise.
        """
        ...

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Cleanup provider resources.

        Called during adapter shutdown. Should close connections,
        flush pending operations, etc.
        """
        ...

    @abstractmethod
    async def send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        memo: Optional[str] = None,
        **kwargs: object,
    ) -> TransactionResult:
        """
        Send money to a recipient.

        Args:
            recipient: Recipient address/phone/username (format depends on provider)
            amount: Amount to send
            currency: Currency code (must be in supported_currencies)
            memo: Optional transaction memo/description
            **kwargs: Provider-specific parameters

        Returns:
            TransactionResult with success status, transaction ID, etc.

        Raises:
            ValueError: If currency not supported or parameters invalid
        """
        ...

    @abstractmethod
    async def request(
        self,
        amount: Decimal,
        currency: str,
        description: str,
        expires_at: Optional[datetime] = None,
        callback_url: Optional[str] = None,
        **kwargs: object,
    ) -> PaymentRequest:
        """
        Create a payment request/invoice.

        Args:
            amount: Requested amount
            currency: Currency code
            description: What the payment is for
            expires_at: Optional expiration timestamp
            callback_url: Optional webhook URL for payment notification
            **kwargs: Provider-specific parameters

        Returns:
            PaymentRequest with request ID, checkout URL, etc.
        """
        ...

    @abstractmethod
    async def get_balance(self, currency: Optional[str] = None) -> Balance:
        """
        Get account balance.

        Args:
            currency: Specific currency to query (None for primary currency)

        Returns:
            Balance with available, pending, and total amounts.
        """
        ...

    @abstractmethod
    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        currency: Optional[str] = None,
    ) -> List[Transaction]:
        """
        Get transaction history.

        Args:
            limit: Maximum transactions to return
            offset: Skip this many transactions (pagination)
            currency: Filter by currency (None for all)

        Returns:
            List of Transaction objects, most recent first.
        """
        ...

    @abstractmethod
    async def get_account_details(self) -> AccountDetails:
        """
        Get account details.

        Returns:
            AccountDetails with address/phone, network, attestation level, etc.
        """
        ...

    @abstractmethod
    async def verify_payment(self, payment_ref: str) -> PaymentVerification:
        """
        Verify a payment by reference ID.

        Used to check if a payment request has been fulfilled.

        Args:
            payment_ref: Payment reference (request_id or transaction_id)

        Returns:
            PaymentVerification with verified status and transaction details.
        """
        ...

    def supports_currency(self, currency: str) -> bool:
        """Check if this provider supports a currency."""
        return currency.upper() in [c.upper() for c in self.supported_currencies]
