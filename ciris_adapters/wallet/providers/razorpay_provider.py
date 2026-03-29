"""
Razorpay Provider for UPI Payments (India).

Supports INR (Indian Rupee) payments via:
- UPI Intent (recommended - launches UPI app)
- UPI QR Code
- Cards and Net Banking

API Documentation: https://razorpay.com/docs/api/

Authentication: Basic HTTP Auth
- Base64(key_id:key_secret)

IMPORTANT: UPI Collect deprecated Feb 28, 2026 - use UPI Intent instead.
"""

import base64
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, cast

import httpx

from ..config import RazorpayProviderConfig
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


class RazorpayProvider(WalletProvider):
    """
    Razorpay provider for INR payments via UPI.

    Flow:
    1. Create Order → POST /v1/orders
    2. Create Payment (UPI Intent) → Returns app deep links
    3. Customer pays via UPI app
    4. Webhook confirms payment

    Fees:
    - UPI: ~2% platform fee (zero MDR from NPCI)
    - Cards: 2% + GST
    - International: 3% + GST

    Rate Limits:
    - 25 requests/second (default)
    """

    API_URL = "https://api.razorpay.com/v1"
    SUPPORTED_CURRENCIES = ["INR"]

    def __init__(self, config: RazorpayProviderConfig) -> None:
        self.config = config
        self._initialized = False
        self._balance = Balance(
            currency="INR",
            available=Decimal("0"),
            pending=Decimal("0"),
            total=Decimal("0"),
        )
        self._transactions: List[Transaction] = []
        self._pending_requests: Dict[str, PaymentRequest] = {}
        self._orders: Dict[str, Dict[str, Any]] = {}

        logger.info("RazorpayProvider created")

    @property
    def provider_id(self) -> str:
        return "razorpay"

    @property
    def supported_currencies(self) -> List[str]:
        return self.SUPPORTED_CURRENCIES

    def _get_auth_header(self) -> str:
        """Get Basic Auth header."""
        key_id = self.config.key_id.get_secret_value() if self.config.key_id else ""
        key_secret = self.config.key_secret.get_secret_value() if self.config.key_secret else ""
        credentials = base64.b64encode(f"{key_id}:{key_secret}".encode()).decode()
        return f"Basic {credentials}"

    async def initialize(self) -> bool:
        """Initialize the provider."""
        logger.info("Initializing Razorpay provider")

        if not self.config.key_id or not self.config.key_secret:
            logger.error("Razorpay key_id/key_secret not configured")
            return False

        # Verify credentials by fetching payment methods
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.API_URL}/payments",
                    headers={"Authorization": self._get_auth_header()},
                    params={"count": 1},
                )
                if response.status_code == 200:
                    self._initialized = True
                    logger.info("Razorpay provider initialized")
                    return True
                else:
                    logger.error(f"Razorpay auth failed: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Razorpay init error: {e}")
            return False

    async def cleanup(self) -> None:
        """Cleanup provider resources."""
        self._initialized = False
        logger.info("Razorpay provider cleaned up")

    async def _create_order(
        self,
        amount: Decimal,
        currency: str = "INR",
        receipt: Optional[str] = None,
        notes: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Create a Razorpay order (required before payment)."""
        # Amount in paise (1 INR = 100 paise)
        amount_paise = int(amount * 100)

        payload = {
            "amount": amount_paise,
            "currency": currency,
            "receipt": receipt or f"rcpt_{uuid.uuid4().hex[:8]}",
        }
        if notes:
            payload["notes"] = notes

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self.API_URL}/orders",
                json=payload,
                headers={
                    "Authorization": self._get_auth_header(),
                    "Content-Type": "application/json",
                },
            )
            response.raise_for_status()
            order: Dict[str, Any] = cast(Dict[str, Any], response.json())
            self._orders[order["id"]] = order
            return order

    async def send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        memo: Optional[str] = None,
        **kwargs: object,
    ) -> TransactionResult:
        """
        Send money via Razorpay (payout).

        Note: Payouts require Razorpay X (RazorpayX) account.
        This is a placeholder for future implementation.
        """
        return TransactionResult(
            success=False,
            provider=self.provider_id,
            amount=amount,
            currency=currency,
            recipient=recipient,
            error="Razorpay payouts require RazorpayX account. Use request() for payments.",
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
        Create a payment request via Razorpay.

        Returns order details for UPI Intent payment.
        """
        if currency.upper() != "INR":
            raise ValueError(f"Unsupported currency: {currency}. Razorpay supports INR.")

        try:
            # Create order first
            order = await self._create_order(
                amount=amount,
                currency="INR",
                notes={"description": description},
            )

            order_id = order["id"]

            request = PaymentRequest(
                request_id=order_id,
                provider=self.provider_id,
                amount=amount,
                currency="INR",
                description=description,
                status=PaymentRequestStatus.PENDING,
                checkout_url=None,  # UPI Intent uses app deep links
                created_at=datetime.now(timezone.utc),
                expires_at=expires_at,
                metadata={
                    "order_id": order_id,
                    "amount_paise": order["amount"],
                    "receipt": order["receipt"],
                    "key_id": self.config.key_id.get_secret_value()[:20] + "..." if self.config.key_id else None,
                },
            )
            self._pending_requests[order_id] = request
            logger.info(f"Razorpay order created: {order_id}")
            return request

        except Exception as e:
            logger.error(f"Razorpay order creation error: {e}")
            raise

    async def get_balance(self, currency: Optional[str] = None) -> Balance:
        """Get Razorpay account balance."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.API_URL}/balance",
                    headers={"Authorization": self._get_auth_header()},
                )
                if response.status_code == 200:
                    data = response.json()
                    # Balance in paise, convert to INR
                    balance_inr = Decimal(data.get("balance", 0)) / 100
                    self._balance = Balance(
                        currency="INR",
                        available=balance_inr,
                        pending=Decimal("0"),
                        total=balance_inr,
                    )
                return self._balance
        except Exception as e:
            logger.error(f"Razorpay balance error: {e}")
            return self._balance

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        currency: Optional[str] = None,
    ) -> List[Transaction]:
        """Get payment history from Razorpay."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.API_URL}/payments",
                    headers={"Authorization": self._get_auth_header()},
                    params={"count": limit, "skip": offset},
                )
                if response.status_code == 200:
                    data = response.json()
                    transactions = []
                    for item in data.get("items", []):
                        tx = Transaction(
                            transaction_id=item["id"],
                            provider=self.provider_id,
                            type=TransactionType.RECEIVE,
                            status=(
                                TransactionStatus.CONFIRMED
                                if item["status"] == "captured"
                                else TransactionStatus.PENDING
                            ),
                            amount=Decimal(item["amount"]) / 100,
                            currency=item["currency"],
                            sender=item.get("email"),
                            timestamp=datetime.fromtimestamp(
                                item["created_at"], tz=timezone.utc
                            ),
                            metadata={"method": item.get("method")},
                        )
                        transactions.append(tx)
                    return transactions
                return self._transactions[offset:offset + limit]
        except Exception as e:
            logger.error(f"Razorpay history error: {e}")
            return self._transactions[offset:offset + limit]

    async def get_account_details(self) -> AccountDetails:
        """Get Razorpay account details."""
        return AccountDetails(
            provider=self.provider_id,
            currency="INR",
            address=self.config.account_number,
            network="razorpay",
            metadata={
                "key_id": self.config.key_id.get_secret_value()[:12] + "..." if self.config.key_id else None,
            },
        )

    async def verify_payment(self, payment_ref: str) -> PaymentVerification:
        """Verify payment by order ID or payment ID."""
        try:
            # Try as payment ID first
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.API_URL}/payments/{payment_ref}",
                    headers={"Authorization": self._get_auth_header()},
                )

                if response.status_code == 200:
                    payment = response.json()
                    status_map = {
                        "captured": TransactionStatus.CONFIRMED,
                        "authorized": TransactionStatus.PENDING,
                        "failed": TransactionStatus.FAILED,
                        "refunded": TransactionStatus.REFUNDED,
                    }
                    return PaymentVerification(
                        verified=payment["status"] == "captured",
                        status=status_map.get(payment["status"], TransactionStatus.PENDING),
                        transaction_id=payment["id"],
                        amount=Decimal(payment["amount"]) / 100,
                        currency=payment["currency"],
                        timestamp=datetime.fromtimestamp(
                            payment["created_at"], tz=timezone.utc
                        ),
                    )

                # Try as order ID
                response = await client.get(
                    f"{self.API_URL}/orders/{payment_ref}/payments",
                    headers={"Authorization": self._get_auth_header()},
                )

                if response.status_code == 200:
                    data = response.json()
                    items = data.get("items", [])
                    if items:
                        payment = items[0]
                        return PaymentVerification(
                            verified=payment["status"] == "captured",
                            status=TransactionStatus.CONFIRMED if payment["status"] == "captured" else TransactionStatus.PENDING,
                            transaction_id=payment["id"],
                            amount=Decimal(payment["amount"]) / 100,
                            currency=payment["currency"],
                        )

                return PaymentVerification(
                    verified=False,
                    status=TransactionStatus.PENDING,
                    error="Payment not found or pending",
                )

        except Exception as e:
            logger.error(f"Razorpay verify error: {e}")
            return PaymentVerification(
                verified=False,
                status=TransactionStatus.FAILED,
                error=str(e),
            )
