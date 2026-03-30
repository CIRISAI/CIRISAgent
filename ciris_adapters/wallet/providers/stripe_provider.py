"""
Stripe Provider for Global Card Payments.

Supports card payments in 135+ currencies via Stripe Connect.

API Documentation: https://docs.stripe.com/api

Authentication: Basic HTTP Auth
- Base64(secret_key:) - note the trailing colon
- For Connect: Add Stripe-Account header

Rate Limits: 25 requests/second (default)
"""

import base64
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

from ..config import StripeProviderConfig
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


class StripeProvider(WalletProvider):
    """
    Stripe provider for global card payments.

    Flow:
    1. Create PaymentIntent → POST /v1/payment_intents
    2. Confirm payment client-side (Stripe.js/Elements)
    3. Webhook confirms payment

    Features:
    - 135+ presentment currencies
    - 46+ supported countries
    - Cards, wallets, bank transfers
    - Stripe Connect for marketplaces

    Fees:
    - Card-not-present: 3.4% + $0.30
    - Card-present: 2.70% + $0.05
    - International: +1%
    - Currency conversion: +1%
    """

    API_URL = "https://api.stripe.com/v1"
    API_VERSION = "2026-02-25"

    # Major supported currencies
    SUPPORTED_CURRENCIES = [
        "USD",
        "EUR",
        "GBP",
        "AUD",
        "CAD",
        "JPY",
        "CHF",
        "SGD",
        "HKD",
        "NZD",
        "SEK",
        "NOK",
        "DKK",
        "PLN",
        "MXN",
        "BRL",
        "INR",
        "ZAR",
        "THB",
        "MYR",
        "PHP",
        "IDR",
        "KRW",
        "TWD",
    ]

    def __init__(self, config: StripeProviderConfig) -> None:
        self.config = config
        self._initialized = False
        self._balance = Balance(
            currency="USD",
            available=Decimal("0"),
            pending=Decimal("0"),
            total=Decimal("0"),
        )
        self._transactions: List[Transaction] = []
        self._pending_requests: Dict[str, PaymentRequest] = {}
        self._payment_intents: Dict[str, Dict[str, Any]] = {}

        logger.info("StripeProvider created")

    @property
    def provider_id(self) -> str:
        return "stripe"

    @property
    def supported_currencies(self) -> List[str]:
        return self.SUPPORTED_CURRENCIES

    def _get_auth_header(self) -> Dict[str, str]:
        """Get authorization headers."""
        secret = self.config.secret_key.get_secret_value() if self.config.secret_key else ""
        # Stripe uses secret_key: (with trailing colon, no password)
        credentials = base64.b64encode(f"{secret}:".encode()).decode()
        headers = {
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Stripe-Version": self.API_VERSION,
        }
        # Add Connect header if using connected account
        if self.config.connect_account_id:
            headers["Stripe-Account"] = self.config.connect_account_id
        return headers

    async def initialize(self) -> bool:
        """Initialize the Stripe provider."""
        logger.info("Initializing Stripe provider")

        if not self.config.secret_key:
            logger.error("Stripe secret_key not configured")
            return False

        # Verify credentials
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.API_URL}/balance",
                    headers=self._get_auth_header(),
                )
                if response.status_code == 200:
                    self._initialized = True
                    logger.info("Stripe provider initialized")
                    return True
                else:
                    logger.error(f"Stripe auth failed: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Stripe init error: {e}")
            return False

    async def cleanup(self) -> None:
        """Cleanup provider resources."""
        self._initialized = False
        logger.info("Stripe provider cleaned up")

    def _encode_params(self, params: Dict[str, Any], prefix: str = "") -> str:
        """Encode nested params for x-www-form-urlencoded."""
        items = []
        for key, value in params.items():
            full_key = f"{prefix}[{key}]" if prefix else key
            if isinstance(value, dict):
                items.append(self._encode_params(value, full_key))
            elif isinstance(value, bool):
                items.append(f"{full_key}={'true' if value else 'false'}")
            elif value is not None:
                items.append(f"{full_key}={value}")
        return "&".join(filter(None, items))

    async def send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        memo: Optional[str] = None,
        **kwargs: object,
    ) -> TransactionResult:
        """
        Send money via Stripe (payout to connected account or bank).

        Args:
            recipient: Connected account ID (acct_*) or bank account token
            amount: Amount to send
            currency: Currency code
            memo: Payout description
        """
        currency = currency.upper()

        try:
            # Convert to smallest unit (cents for USD)
            amount_cents = int(amount * 100)

            params = {
                "amount": amount_cents,
                "currency": currency.lower(),
                "description": memo or "CIRIS Payout",
            }

            # If recipient is a connected account, use transfers
            if recipient.startswith("acct_"):
                params["destination"] = recipient
                endpoint = f"{self.API_URL}/transfers"
            else:
                # Standard payout to default bank
                endpoint = f"{self.API_URL}/payouts"

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    endpoint,
                    content=self._encode_params(params),
                    headers=self._get_auth_header(),
                )
                data = response.json()

                if response.status_code in (200, 201):
                    tx_id = data["id"]
                    logger.info(f"Stripe payout created: {tx_id}")

                    transaction = Transaction(
                        transaction_id=tx_id,
                        provider=self.provider_id,
                        type=TransactionType.SEND,
                        status=TransactionStatus.PENDING,
                        amount=-amount,
                        currency=currency,
                        recipient=recipient,
                        memo=memo,
                        timestamp=datetime.now(timezone.utc),
                    )
                    self._transactions.insert(0, transaction)

                    return TransactionResult(
                        success=True,
                        transaction_id=tx_id,
                        provider=self.provider_id,
                        amount=amount,
                        currency=currency,
                        recipient=recipient,
                        timestamp=datetime.now(timezone.utc),
                    )
                else:
                    error = data.get("error", {}).get("message", "Unknown error")
                    return TransactionResult(
                        success=False,
                        provider=self.provider_id,
                        amount=amount,
                        currency=currency,
                        recipient=recipient,
                        error=f"Stripe payout failed: {error}",
                    )

        except Exception as e:
            logger.error(f"Stripe send error: {e}")
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=str(e),
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
        Create a payment request (PaymentIntent).

        Returns client_secret for Stripe.js/Elements integration.
        """
        currency = currency.upper()
        amount_cents = int(amount * 100)

        params: Dict[str, Any] = {
            "amount": amount_cents,
            "currency": currency.lower(),
            "description": description,
            "automatic_payment_methods": {"enabled": True},
        }

        # Add metadata
        metadata = kwargs.get("metadata", {})
        if metadata:
            params["metadata"] = metadata

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.API_URL}/payment_intents",
                    content=self._encode_params(params),
                    headers=self._get_auth_header(),
                )
                data = response.json()

                if response.status_code in (200, 201):
                    intent_id = data["id"]
                    client_secret = data["client_secret"]

                    self._payment_intents[intent_id] = data

                    request = PaymentRequest(
                        request_id=intent_id,
                        provider=self.provider_id,
                        amount=amount,
                        currency=currency,
                        description=description,
                        status=PaymentRequestStatus.PENDING,
                        checkout_url=None,  # Client-side handles payment
                        created_at=datetime.now(timezone.utc),
                        expires_at=expires_at,
                        metadata={
                            "client_secret": client_secret,
                            "publishable_key": self.config.publishable_key,
                            "payment_intent_id": intent_id,
                        },
                    )
                    self._pending_requests[intent_id] = request
                    logger.info(f"Stripe PaymentIntent created: {intent_id}")
                    return request
                else:
                    error = data.get("error", {}).get("message", "Unknown error")
                    raise Exception(f"PaymentIntent creation failed: {error}")

        except Exception as e:
            logger.error(f"Stripe request error: {e}")
            raise

    async def get_balance(self, currency: Optional[str] = None) -> Balance:
        """Get Stripe account balance."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.API_URL}/balance",
                    headers=self._get_auth_header(),
                )
                if response.status_code == 200:
                    data = response.json()

                    # Sum up available balances
                    available = Decimal("0")
                    pending = Decimal("0")

                    for bal in data.get("available", []):
                        if currency and bal["currency"].upper() != currency.upper():
                            continue
                        available += Decimal(bal["amount"]) / 100

                    for bal in data.get("pending", []):
                        if currency and bal["currency"].upper() != currency.upper():
                            continue
                        pending += Decimal(bal["amount"]) / 100

                    self._balance = Balance(
                        currency=currency or "USD",
                        available=available,
                        pending=pending,
                        total=available + pending,
                    )

                return self._balance
        except Exception as e:
            logger.error(f"Stripe balance error: {e}")
            return self._balance

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        currency: Optional[str] = None,
    ) -> List[Transaction]:
        """Get Stripe payment history."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                params = {"limit": limit}
                if offset > 0:
                    # Stripe uses cursor-based pagination
                    # This is simplified; real impl would track cursors
                    pass

                response = await client.get(
                    f"{self.API_URL}/charges",
                    headers=self._get_auth_header(),
                    params=params,
                )
                if response.status_code == 200:
                    data = response.json()
                    transactions = []
                    for item in data.get("data", []):
                        if currency and item["currency"].upper() != currency.upper():
                            continue

                        status_map = {
                            "succeeded": TransactionStatus.CONFIRMED,
                            "pending": TransactionStatus.PENDING,
                            "failed": TransactionStatus.FAILED,
                        }
                        tx = Transaction(
                            transaction_id=item["id"],
                            provider=self.provider_id,
                            type=TransactionType.RECEIVE,
                            status=status_map.get(item["status"], TransactionStatus.PENDING),
                            amount=Decimal(item["amount"]) / 100,
                            currency=item["currency"].upper(),
                            sender=item.get("billing_details", {}).get("email"),
                            timestamp=datetime.fromtimestamp(item["created"], tz=timezone.utc),
                            metadata={"payment_method": item.get("payment_method_details", {}).get("type")},
                        )
                        transactions.append(tx)
                    return transactions
                return self._transactions[offset : offset + limit]
        except Exception as e:
            logger.error(f"Stripe history error: {e}")
            return self._transactions[offset : offset + limit]

    async def get_account_details(self) -> AccountDetails:
        """Get Stripe account details."""
        return AccountDetails(
            provider=self.provider_id,
            currency="USD",
            network="stripe",
            metadata={
                "publishable_key": self.config.publishable_key,
                "connect_account": self.config.connect_account_id,
            },
        )

    async def verify_payment(self, payment_ref: str) -> PaymentVerification:
        """Verify Stripe payment status."""
        try:
            # Try as PaymentIntent first
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self.API_URL}/payment_intents/{payment_ref}",
                    headers=self._get_auth_header(),
                )

                if response.status_code == 200:
                    intent = response.json()
                    status_map = {
                        "succeeded": TransactionStatus.CONFIRMED,
                        "processing": TransactionStatus.PENDING,
                        "requires_payment_method": TransactionStatus.PENDING,
                        "requires_confirmation": TransactionStatus.PENDING,
                        "requires_action": TransactionStatus.PENDING,
                        "canceled": TransactionStatus.CANCELLED,
                    }
                    return PaymentVerification(
                        verified=intent["status"] == "succeeded",
                        status=status_map.get(intent["status"], TransactionStatus.PENDING),
                        transaction_id=intent["id"],
                        amount=Decimal(intent["amount"]) / 100,
                        currency=intent["currency"].upper(),
                        timestamp=datetime.fromtimestamp(intent["created"], tz=timezone.utc),
                    )

                # Try as Charge
                response = await client.get(
                    f"{self.API_URL}/charges/{payment_ref}",
                    headers=self._get_auth_header(),
                )

                if response.status_code == 200:
                    charge = response.json()
                    return PaymentVerification(
                        verified=charge["status"] == "succeeded",
                        status=(
                            TransactionStatus.CONFIRMED
                            if charge["status"] == "succeeded"
                            else TransactionStatus.PENDING
                        ),
                        transaction_id=charge["id"],
                        amount=Decimal(charge["amount"]) / 100,
                        currency=charge["currency"].upper(),
                    )

                return PaymentVerification(
                    verified=False,
                    status=TransactionStatus.FAILED,
                    error=f"Payment not found: {payment_ref}",
                )

        except Exception as e:
            logger.error(f"Stripe verify error: {e}")
            return PaymentVerification(
                verified=False,
                status=TransactionStatus.FAILED,
                error=str(e),
            )
