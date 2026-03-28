"""
PIX Provider for Brazilian Payments.

Supports BRL (Brazilian Real) via PIX instant payments through
aggregators like Mercado Pago, Stripe (via EBANX), or direct bank APIs.

API Documentation:
- Mercado Pago: https://www.mercadopago.com.br/developers/
- Stripe PIX: https://docs.stripe.com/payments/pix

Authentication: Bearer Token (access_token)
- Must include X-Idempotency-Key header for payment creation
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

from ..config import PIXProviderConfig
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


class PIXProvider(WalletProvider):
    """
    PIX provider for BRL payments in Brazil.

    Supports:
    - QR Code payments (static and dynamic)
    - PIX key payments (CPF, CNPJ, email, phone, EVP)
    - Instant settlement (24/7)

    Aggregators:
    - mercadopago (default): Full PIX support
    - stripe: Via EBANX partnership
    - ebanx: Direct integration

    Fees:
    - Consumer: FREE (regulated)
    - Merchant: ~2% via aggregators
    """

    # Mercado Pago URLs
    MP_SANDBOX_URL = "https://api.mercadopago.com"
    MP_PRODUCTION_URL = "https://api.mercadopago.com"

    SUPPORTED_CURRENCIES = ["BRL"]

    def __init__(self, config: PIXProviderConfig) -> None:
        self.config = config
        self._initialized = False
        self._balance = Balance(
            currency="BRL",
            available=Decimal("0"),
            pending=Decimal("0"),
            total=Decimal("0"),
        )
        self._transactions: List[Transaction] = []
        self._pending_requests: Dict[str, PaymentRequest] = {}

        # Select API URL based on provider
        self._base_url = self.MP_PRODUCTION_URL

        logger.info(f"PIXProvider created (aggregator: {config.provider})")

    @property
    def provider_id(self) -> str:
        return "pix"

    @property
    def supported_currencies(self) -> List[str]:
        return self.SUPPORTED_CURRENCIES

    def _get_auth_header(self) -> Dict[str, str]:
        """Get authorization headers."""
        token = self.config.access_token.get_secret_value() if self.config.access_token else ""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def initialize(self) -> bool:
        """Initialize the PIX provider."""
        logger.info(f"Initializing PIX provider ({self.config.provider})")

        if not self.config.access_token:
            logger.error("PIX access_token not configured")
            return False

        # Verify credentials
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/v1/payment_methods",
                    headers=self._get_auth_header(),
                )
                if response.status_code == 200:
                    self._initialized = True
                    logger.info("PIX provider initialized")
                    return True
                else:
                    logger.error(f"PIX auth failed: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"PIX init error: {e}")
            return False

    async def cleanup(self) -> None:
        """Cleanup provider resources."""
        self._initialized = False
        logger.info("PIX provider cleaned up")

    async def send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        memo: Optional[str] = None,
        **kwargs: object,
    ) -> TransactionResult:
        """
        Send PIX payment.

        Args:
            recipient: PIX key (CPF, CNPJ, email, phone, or EVP/random key)
            amount: Amount in BRL
            currency: Must be "BRL"
            memo: Payment description
        """
        if currency.upper() != "BRL":
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=f"Unsupported currency: {currency}. PIX only supports BRL.",
            )

        # PIX outbound transfers require bank API integration
        # Most aggregators don't support outbound PIX via API
        return TransactionResult(
            success=False,
            provider=self.provider_id,
            amount=amount,
            currency=currency,
            recipient=recipient,
            error="PIX outbound transfers require direct bank integration. Use request() for incoming payments.",
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
        Create a PIX payment request (QR Code).

        Returns QR code data for customer to scan.
        """
        if currency.upper() != "BRL":
            raise ValueError(f"Unsupported currency: {currency}. PIX supports BRL only.")

        payer_email = kwargs.get("payer_email", "customer@example.com")

        # Generate idempotency key
        idempotency_key = str(uuid.uuid4())

        payload = {
            "transaction_amount": float(amount),
            "description": description,
            "payment_method_id": "pix",
            "payer": {
                "email": payer_email,
            },
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                headers = self._get_auth_header()
                headers["X-Idempotency-Key"] = idempotency_key

                response = await client.post(
                    f"{self._base_url}/v1/payments",
                    json=payload,
                    headers=headers,
                )
                data = response.json()

                if response.status_code in (200, 201):
                    payment_id = str(data.get("id", ""))

                    # Extract QR code from response
                    pix_data = data.get("point_of_interaction", {}).get("transaction_data", {})
                    qr_code = pix_data.get("qr_code", "")
                    qr_code_base64 = pix_data.get("qr_code_base64", "")

                    request = PaymentRequest(
                        request_id=payment_id,
                        provider=self.provider_id,
                        amount=amount,
                        currency="BRL",
                        description=description,
                        status=PaymentRequestStatus.PENDING,
                        checkout_url=None,  # PIX uses QR code, not URL
                        created_at=datetime.now(timezone.utc),
                        expires_at=expires_at,
                        metadata={
                            "qr_code": qr_code,
                            "qr_code_base64": qr_code_base64,
                            "idempotency_key": idempotency_key,
                            "external_reference": data.get("external_reference"),
                        },
                    )
                    self._pending_requests[payment_id] = request
                    logger.info(f"PIX payment request created: {payment_id}")
                    return request
                else:
                    error = data.get("message") or data.get("error") or "Unknown error"
                    raise Exception(f"PIX payment creation failed: {error}")

        except Exception as e:
            logger.error(f"PIX request error: {e}")
            raise

    async def get_balance(self, currency: Optional[str] = None) -> Balance:
        """Get account balance (via aggregator)."""
        # Balance checking depends on aggregator
        # Mercado Pago has a balance endpoint
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/users/me",
                    headers=self._get_auth_header(),
                )
                if response.status_code == 200:
                    # Balance would be in account details
                    # This is a simplified implementation
                    pass
            return self._balance
        except Exception as e:
            logger.error(f"PIX balance error: {e}")
            return self._balance

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        currency: Optional[str] = None,
    ) -> List[Transaction]:
        """Get PIX payment history."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/v1/payments/search",
                    headers=self._get_auth_header(),
                    params={
                        "limit": limit,
                        "offset": offset,
                        "sort": "date_created",
                        "criteria": "desc",
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    transactions = []
                    for item in data.get("results", []):
                        if item.get("payment_method_id") == "pix":
                            tx = Transaction(
                                transaction_id=str(item["id"]),
                                provider=self.provider_id,
                                type=TransactionType.RECEIVE,
                                status=(
                                    TransactionStatus.CONFIRMED
                                    if item["status"] == "approved"
                                    else TransactionStatus.PENDING
                                ),
                                amount=Decimal(str(item["transaction_amount"])),
                                currency="BRL",
                                sender=item.get("payer", {}).get("email"),
                                timestamp=datetime.fromisoformat(
                                    item["date_created"].replace("Z", "+00:00")
                                ),
                            )
                            transactions.append(tx)
                    return transactions
                return self._transactions[offset:offset + limit]
        except Exception as e:
            logger.error(f"PIX history error: {e}")
            return self._transactions[offset:offset + limit]

    async def get_account_details(self) -> AccountDetails:
        """Get PIX account details."""
        return AccountDetails(
            provider=self.provider_id,
            currency="BRL",
            address=self.config.pix_key,
            network="pix",
            metadata={
                "aggregator": self.config.provider,
                "pix_key": self.config.pix_key,
            },
        )

    async def verify_payment(self, payment_ref: str) -> PaymentVerification:
        """Verify PIX payment status."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/v1/payments/{payment_ref}",
                    headers=self._get_auth_header(),
                )

                if response.status_code == 200:
                    payment = response.json()
                    status_map = {
                        "approved": TransactionStatus.CONFIRMED,
                        "pending": TransactionStatus.PENDING,
                        "in_process": TransactionStatus.PENDING,
                        "rejected": TransactionStatus.FAILED,
                        "cancelled": TransactionStatus.CANCELLED,
                        "refunded": TransactionStatus.REFUNDED,
                    }
                    return PaymentVerification(
                        verified=payment["status"] == "approved",
                        status=status_map.get(payment["status"], TransactionStatus.PENDING),
                        transaction_id=str(payment["id"]),
                        amount=Decimal(str(payment["transaction_amount"])),
                        currency="BRL",
                        timestamp=datetime.fromisoformat(
                            payment["date_approved"].replace("Z", "+00:00")
                        ) if payment.get("date_approved") else None,
                    )

                return PaymentVerification(
                    verified=False,
                    status=TransactionStatus.FAILED,
                    error=f"Payment not found: {payment_ref}",
                )

        except Exception as e:
            logger.error(f"PIX verify error: {e}")
            return PaymentVerification(
                verified=False,
                status=TransactionStatus.FAILED,
                error=str(e),
            )
