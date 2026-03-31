"""
Chapa Wallet Provider.

Ethiopian Birr (ETB) payments via Chapa payment gateway.
Supports Telebirr, CBE Birr, and bank transfers.

Dependencies:
- chapa  # Chapa Python SDK (pip install chapa)
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..config import ChapaProviderConfig
from ..schemas import (
    AccountDetails,
    Balance,
    PaymentRequest,
    PaymentRequestStatus,
    PaymentVerification,
    Transaction,
    TransactionResult,
    TransactionStatus,
    TransactionType,
)
from .base import WalletProvider

logger = logging.getLogger(__name__)


class ChapaProvider(WalletProvider):
    """
    Chapa provider for Ethiopian Birr (ETB) payments.

    Key features:
    - Telebirr integration (mobile money)
    - CBE Birr integration
    - Bank transfer support
    - 24-hour settlement to Ethiopian bank account

    Chapa handles all local payment methods through a unified API.
    Users pay via their preferred method (Telebirr, bank, etc.)
    and CIRIS receives ETB in the merchant account.
    """

    SUPPORTED_CURRENCIES = ["ETB"]

    def __init__(self, config: ChapaProviderConfig) -> None:
        """
        Initialize the Chapa provider.

        Args:
            config: Provider configuration with API key and callback URL
        """
        self.config = config
        self._initialized = False
        self._chapa_client: Optional[Any] = None

        # Track pending requests and transactions (in-memory)
        self._pending_requests: Dict[str, PaymentRequest] = {}
        self._transactions: List[Transaction] = []
        self._balance = Balance(
            currency="ETB",
            available=Decimal("0"),
            pending=Decimal("0"),
            total=Decimal("0"),
        )

        logger.info("ChapaProvider created")

    @property
    def provider_id(self) -> str:
        return "chapa"

    @property
    def supported_currencies(self) -> List[str]:
        return self.SUPPORTED_CURRENCIES

    async def initialize(self) -> bool:
        """Initialize the provider with Chapa SDK."""
        logger.info("Initializing ChapaProvider")

        if not self.config.secret_key:
            logger.warning("Chapa secret key not configured")
            self._initialized = True  # Allow to run without key for testing
            return True

        try:
            # Try to import and initialize Chapa SDK
            # from chapa import AsyncChapa
            # self._chapa_client = AsyncChapa(self.config.secret_key.get_secret_value())
            logger.info("Chapa SDK would be initialized here")
            self._initialized = True
            return True
        except ImportError:
            logger.warning("Chapa SDK not installed - running in simulation mode")
            self._initialized = True
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Chapa: {e}")
            return False

    async def cleanup(self) -> None:
        """Cleanup provider resources."""
        logger.info("Cleaning up ChapaProvider")
        self._chapa_client = None
        self._initialized = False

    async def send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        memo: Optional[str] = None,
        **kwargs: object,
    ) -> TransactionResult:
        """
        Send ETB to a recipient.

        For Chapa, sends are typically bank transfers or mobile money transfers.
        Recipient should be a phone number or bank account.

        Args:
            recipient: Phone number (+251...) or bank account
            amount: Amount in ETB
            currency: Must be ETB
            memo: Optional transfer description

        Returns:
            TransactionResult with transfer details.
        """
        currency = currency.upper()
        if currency != "ETB":
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=f"Chapa only supports ETB, got: {currency}",
            )

        # Validate recipient format (Ethiopian phone or simplistic check)
        is_phone = recipient.startswith("+251") or recipient.startswith("0")
        if not is_phone and not recipient.isdigit():
            logger.warning(f"Unusual recipient format: {recipient}")

        # TODO: Implement actual Chapa transfer
        # Chapa supports:
        # - chapa.transfer(account_name, account_number, amount, reference, bank_code)
        # - For mobile money, different flow

        logger.info(f"[CHAPA] Sending {amount} ETB to {recipient} (memo: {memo})")

        # Generate transaction reference
        tx_ref = f"CIRIS-{uuid.uuid4().hex[:8].upper()}"
        timestamp = datetime.now(timezone.utc)

        # Record transaction
        transaction = Transaction(
            transaction_id=tx_ref,
            provider=self.provider_id,
            type=TransactionType.SEND,
            status=TransactionStatus.PENDING,  # Chapa transfers are async
            amount=-amount,
            currency=currency,
            recipient=recipient,
            sender="CIRIS",
            memo=memo,
            timestamp=timestamp,
            fees={"provider_fee": amount * Decimal("0.015")},  # 1.5% Chapa fee
            metadata={"tx_ref": tx_ref},
        )
        self._transactions.insert(0, transaction)

        # Update balance
        fee = amount * Decimal("0.015")
        self._balance.available -= amount + fee
        self._balance.total = self._balance.available + self._balance.pending

        return TransactionResult(
            success=True,
            transaction_id=tx_ref,
            provider=self.provider_id,
            amount=amount,
            currency=currency,
            recipient=recipient,
            timestamp=timestamp,
            fees={"provider_fee": fee},
            confirmation={
                "tx_ref": tx_ref,
                "status": "pending",
                "settlement": "24_hours",
            },
        )

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
        Create a payment request via Chapa checkout.

        Returns a checkout URL where the payer can complete payment
        via Telebirr, CBE Birr, or bank transfer.

        Args:
            amount: Amount in ETB
            currency: Must be ETB
            description: What the payment is for
            expires_at: Optional expiration
            callback_url: Webhook URL for payment notification

        Returns:
            PaymentRequest with Chapa checkout URL.
        """
        currency = currency.upper()
        tx_ref = f"CIRIS-{uuid.uuid4().hex[:8].upper()}"

        # Determine callback URL
        final_callback = callback_url or self.config.callback_base_url
        if final_callback and not final_callback.endswith("/"):
            final_callback = f"{final_callback}/wallet/chapa/callback"

        # TODO: Create actual Chapa checkout
        # response = await self._chapa_client.initialize(
        #     amount=float(amount),
        #     currency="ETB",
        #     tx_ref=tx_ref,
        #     callback_url=final_callback,
        #     return_url=final_callback,
        #     customization={
        #         "title": self.config.merchant_name,
        #         "description": description,
        #     }
        # )
        # checkout_url = response["data"]["checkout_url"]

        # Simulated checkout URL for testing
        checkout_url = f"https://checkout.chapa.co/checkout/payment/{tx_ref}"

        request = PaymentRequest(
            request_id=tx_ref,
            provider=self.provider_id,
            amount=amount,
            currency=currency,
            description=description,
            status=PaymentRequestStatus.PENDING,
            checkout_url=checkout_url,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            metadata={
                "tx_ref": tx_ref,
                "callback_url": final_callback,
                "merchant": self.config.merchant_name,
            },
        )

        self._pending_requests[tx_ref] = request
        logger.info(f"[CHAPA] Created payment request: {tx_ref} for {amount} ETB")
        logger.info(f"[CHAPA] Checkout URL: {checkout_url}")

        return request

    async def get_balance(self, currency: Optional[str] = None) -> Balance:
        """
        Get account balance.

        Note: Chapa doesn't provide real-time balance API.
        Balance is tracked from settlements.
        """
        # TODO: Could query Chapa dashboard API if available
        return self._balance

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        currency: Optional[str] = None,
    ) -> List[Transaction]:
        """Get transaction history."""
        # Filter by currency if specified (though Chapa only does ETB)
        transactions = self._transactions
        if currency:
            currency = currency.upper()
            transactions = [t for t in transactions if t.currency == currency]

        return transactions[offset : offset + limit]

    async def get_account_details(self) -> AccountDetails:
        """Get account details."""
        return AccountDetails(
            provider=self.provider_id,
            currency="ETB",
            account_id=self.config.merchant_name,
            metadata={
                "merchant_name": self.config.merchant_name,
                "supported_methods": ["telebirr", "cbe_birr", "bank_transfer"],
                "settlement_time": "24_hours",
            },
        )

    async def verify_payment(self, payment_ref: str) -> PaymentVerification:
        """
        Verify a payment by reference ID.

        Chapa provides verification via:
        - Callback webhook (preferred)
        - Polling verify endpoint
        """
        # Check pending requests first
        if payment_ref in self._pending_requests:
            request = self._pending_requests[payment_ref]

            # TODO: Query Chapa verification endpoint
            # result = await self._chapa_client.verify(payment_ref)
            # if result["status"] == "success":
            #     request.status = PaymentRequestStatus.PAID
            #     request.paid_at = datetime.now(timezone.utc)

            return PaymentVerification(
                verified=request.status == PaymentRequestStatus.PAID,
                status=(
                    TransactionStatus.CONFIRMED
                    if request.status == PaymentRequestStatus.PAID
                    else TransactionStatus.PENDING
                ),
                transaction_id=request.transaction_id,
                amount=request.amount,
                currency=request.currency,
                timestamp=request.paid_at,
            )

        # Check transaction history
        for tx in self._transactions:
            if tx.transaction_id == payment_ref:
                return PaymentVerification(
                    verified=tx.status == TransactionStatus.CONFIRMED,
                    status=tx.status,
                    transaction_id=tx.transaction_id,
                    amount=abs(tx.amount),
                    currency=tx.currency,
                    timestamp=tx.timestamp,
                )

        return PaymentVerification(
            verified=False,
            status=TransactionStatus.FAILED,
            error=f"Payment reference not found: {payment_ref}",
        )

    async def handle_callback(self, payload: Dict[str, Any]) -> bool:
        """
        Handle Chapa webhook callback.

        Called when Chapa notifies us of a payment completion.

        Args:
            payload: Webhook payload from Chapa

        Returns:
            True if callback processed successfully.
        """
        tx_ref = payload.get("tx_ref") or payload.get("reference")
        status = payload.get("status", "").lower()

        logger.info(f"[CHAPA] Callback received: tx_ref={tx_ref}, status={status}")

        if not tx_ref:
            logger.error("[CHAPA] Callback missing tx_ref")
            return False

        if tx_ref not in self._pending_requests:
            logger.warning(f"[CHAPA] Unknown tx_ref in callback: {tx_ref}")
            return False

        request = self._pending_requests[tx_ref]

        if status == "success":
            request.status = PaymentRequestStatus.PAID
            request.paid_at = datetime.now(timezone.utc)
            request.transaction_id = payload.get("transaction_id", tx_ref)

            # Record as incoming transaction
            transaction = Transaction(
                transaction_id=request.transaction_id or tx_ref,
                provider=self.provider_id,
                type=TransactionType.RECEIVE,
                status=TransactionStatus.CONFIRMED,
                amount=request.amount,
                currency=request.currency,
                memo=request.description,
                timestamp=request.paid_at,
                metadata=payload,
            )
            self._transactions.insert(0, transaction)

            # Update balance
            self._balance.pending += request.amount
            self._balance.total = self._balance.available + self._balance.pending

            logger.info(f"[CHAPA] Payment confirmed: {tx_ref} - {request.amount} ETB")
            return True

        elif status in ("failed", "cancelled"):
            request.status = PaymentRequestStatus.CANCELLED
            logger.info(f"[CHAPA] Payment {status}: {tx_ref}")
            return True

        return False

    def set_balance(self, available: Decimal, pending: Decimal = Decimal("0")) -> None:
        """Set balance (for testing or after settlement)."""
        self._balance = Balance(
            currency="ETB",
            available=available,
            pending=pending,
            total=available + pending,
        )
        logger.info(f"[CHAPA] Balance set: {available} ETB available, {pending} pending")
