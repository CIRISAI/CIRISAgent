"""
M-Pesa Provider via Safaricom Daraja API.

Supports KES (Kenyan Shilling) payments via:
- STK Push (Lipa Na M-Pesa Online)
- B2C (Business to Customer)
- C2B (Customer to Business)
- Account Balance queries

API Documentation: https://developer.safaricom.co.ke/

Authentication: OAuth 2.0 (Client Credentials)
- Base64(consumer_key:consumer_secret) for token
- Bearer token for API calls
- Token valid for 3600 seconds (1 hour)
"""

import base64
import hashlib
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

import httpx

from ..config import MPesaProviderConfig
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


class MPesaProvider(WalletProvider):
    """
    M-Pesa provider for KES payments via Safaricom Daraja API.

    Supports:
    - STK Push: Initiate payment prompt on customer's phone
    - B2C: Send money from business to customer
    - C2B: Receive payments from customers
    - Balance queries

    Rate Limits:
    - Token refresh every 3600 seconds
    - Implement proper throttling for API calls

    Fees:
    - API access is FREE
    - Transaction fees vary by operation type and amount
    """

    SANDBOX_URL = "https://sandbox.safaricom.co.ke"
    PRODUCTION_URL = "https://api.safaricom.co.ke"
    SUPPORTED_CURRENCIES = ["KES"]

    def __init__(self, config: MPesaProviderConfig) -> None:
        self.config = config
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None
        self._initialized = False
        self._balance = Balance(
            currency="KES",
            available=Decimal("0"),
            pending=Decimal("0"),
            total=Decimal("0"),
        )
        self._transactions: List[Transaction] = []
        self._pending_requests: Dict[str, PaymentRequest] = {}

        # Select environment
        self._base_url = (
            self.PRODUCTION_URL
            if config.environment == "production"
            else self.SANDBOX_URL
        )

        logger.info(f"MPesaProvider created ({config.environment})")

    @property
    def provider_id(self) -> str:
        return "mpesa"

    @property
    def supported_currencies(self) -> List[str]:
        return self.SUPPORTED_CURRENCIES

    async def initialize(self) -> bool:
        """Initialize the provider and obtain access token."""
        logger.info("Initializing M-Pesa provider")

        if not self.config.consumer_key or not self.config.consumer_secret:
            logger.error("M-Pesa consumer key/secret not configured")
            return False

        # Get initial access token
        success = await self._refresh_token()
        self._initialized = success
        return success

    async def cleanup(self) -> None:
        """Cleanup provider resources."""
        self._access_token = None
        self._initialized = False
        logger.info("M-Pesa provider cleaned up")

    async def _refresh_token(self) -> bool:
        """Refresh OAuth access token."""
        try:
            # Base64 encode credentials
            key = self.config.consumer_key.get_secret_value() if self.config.consumer_key else ""
            secret = self.config.consumer_secret.get_secret_value() if self.config.consumer_secret else ""
            credentials = base64.b64encode(f"{key}:{secret}".encode()).decode()

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/oauth/v1/generate?grant_type=client_credentials",
                    headers={"Authorization": f"Basic {credentials}"},
                )
                response.raise_for_status()
                data = response.json()

                self._access_token = data["access_token"]
                # Token valid for 3600 seconds
                self._token_expires_at = datetime.now(timezone.utc)
                logger.info("M-Pesa access token refreshed")
                return True

        except Exception as e:
            logger.error(f"Failed to refresh M-Pesa token: {e}")
            return False

    async def _ensure_token(self) -> bool:
        """Ensure we have a valid access token."""
        if not self._access_token:
            return await self._refresh_token()

        # Refresh if expired (with 5 minute buffer)
        if self._token_expires_at:
            from datetime import timedelta
            buffer = timedelta(minutes=5)
            if datetime.now(timezone.utc) >= self._token_expires_at - buffer:
                return await self._refresh_token()

        return True

    def _generate_password(self, timestamp: str) -> str:
        """Generate Lipa Na M-Pesa password."""
        shortcode = self.config.shortcode or ""
        passkey = self.config.passkey.get_secret_value() if self.config.passkey else ""
        data_to_encode = f"{shortcode}{passkey}{timestamp}"
        return base64.b64encode(data_to_encode.encode()).decode()

    async def send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        memo: Optional[str] = None,
        **kwargs: object,
    ) -> TransactionResult:
        """
        Send money to M-Pesa recipient (B2C).

        Args:
            recipient: Phone number (254XXXXXXXXX format)
            amount: Amount in KES
            currency: Must be "KES"
            memo: Transaction description
        """
        if currency.upper() != "KES":
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=f"Unsupported currency: {currency}. M-Pesa only supports KES.",
            )

        if not await self._ensure_token():
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error="Failed to authenticate with M-Pesa",
            )

        try:
            # B2C Payment Request
            payload = {
                "InitiatorName": self.config.initiator_name,
                "SecurityCredential": self._get_security_credential(),
                "CommandID": "BusinessPayment",
                "Amount": int(amount),
                "PartyA": self.config.shortcode,
                "PartyB": recipient,
                "Remarks": memo or "CIRIS Payment",
                "QueueTimeOutURL": f"{self.config.callback_base_url}/mpesa/timeout",
                "ResultURL": f"{self.config.callback_base_url}/mpesa/result",
                "Occasion": "",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/mpesa/b2c/v1/paymentrequest",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "Content-Type": "application/json",
                    },
                )
                data = response.json()

                if response.status_code == 200 and data.get("ResponseCode") == "0":
                    tx_id = data.get("ConversationID", "")
                    logger.info(f"M-Pesa B2C initiated: {tx_id}")

                    # Record transaction
                    transaction = Transaction(
                        transaction_id=tx_id,
                        provider=self.provider_id,
                        type=TransactionType.SEND,
                        status=TransactionStatus.PENDING,
                        amount=-amount,
                        currency="KES",
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
                        currency="KES",
                        recipient=recipient,
                        timestamp=datetime.now(timezone.utc),
                        confirmation={"originator_conversation_id": data.get("OriginatorConversationID")},
                    )
                else:
                    error = data.get("errorMessage") or data.get("ResponseDescription") or "Unknown error"
                    return TransactionResult(
                        success=False,
                        provider=self.provider_id,
                        amount=amount,
                        currency="KES",
                        recipient=recipient,
                        error=f"M-Pesa B2C failed: {error}",
                    )

        except Exception as e:
            logger.error(f"M-Pesa B2C error: {e}")
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency="KES",
                recipient=recipient,
                error=f"M-Pesa B2C error: {str(e)}",
            )

    def _get_security_credential(self) -> str:
        """Get encrypted security credential for B2C.

        In production, this should encrypt the initiator password
        using Safaricom's RSA public key certificate.
        """
        # For sandbox, use a placeholder
        # Production requires RSA encryption with Safaricom cert
        return "placeholder_security_credential"

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
        Create a payment request (STK Push).

        Initiates Lipa Na M-Pesa prompt on customer's phone.
        """
        phone_number = kwargs.get("phone_number", "")
        if not phone_number:
            raise ValueError("phone_number required for M-Pesa STK Push")

        if not await self._ensure_token():
            raise Exception("Failed to authenticate with M-Pesa")

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = self._generate_password(timestamp)

        payload = {
            "BusinessShortCode": self.config.shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone_number,
            "PartyB": self.config.shortcode,
            "PhoneNumber": phone_number,
            "CallBackURL": callback_url or f"{self.config.callback_base_url}/mpesa/stkpush/callback",
            "AccountReference": description[:12],  # Max 12 chars
            "TransactionDesc": description[:13],   # Max 13 chars
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/mpesa/stkpush/v1/processrequest",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "Content-Type": "application/json",
                    },
                )
                data = response.json()

                if data.get("ResponseCode") == "0":
                    request_id = data.get("CheckoutRequestID", "")
                    request = PaymentRequest(
                        request_id=request_id,
                        provider=self.provider_id,
                        amount=amount,
                        currency="KES",
                        description=description,
                        status=PaymentRequestStatus.PENDING,
                        checkout_url=None,  # STK Push has no URL
                        created_at=datetime.now(timezone.utc),
                        expires_at=expires_at,
                        metadata={
                            "merchant_request_id": data.get("MerchantRequestID"),
                            "phone_number": phone_number,
                        },
                    )
                    self._pending_requests[request_id] = request
                    logger.info(f"M-Pesa STK Push initiated: {request_id}")
                    return request
                else:
                    raise Exception(f"STK Push failed: {data.get('errorMessage', 'Unknown')}")

        except Exception as e:
            logger.error(f"M-Pesa STK Push error: {e}")
            raise

    async def get_balance(self, currency: Optional[str] = None) -> Balance:
        """Query M-Pesa account balance."""
        if not await self._ensure_token():
            return self._balance

        try:
            payload = {
                "Initiator": self.config.initiator_name,
                "SecurityCredential": self._get_security_credential(),
                "CommandID": "AccountBalance",
                "PartyA": self.config.shortcode,
                "IdentifierType": "4",  # Organization shortcode
                "Remarks": "Balance query",
                "QueueTimeOutURL": f"{self.config.callback_base_url}/mpesa/timeout",
                "ResultURL": f"{self.config.callback_base_url}/mpesa/balance/result",
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/mpesa/accountbalance/v1/query",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "Content-Type": "application/json",
                    },
                )
                data = response.json()

                if data.get("ResponseCode") == "0":
                    logger.info("M-Pesa balance query initiated (async)")
                    # Balance comes via callback, return cached for now
                    return self._balance
                else:
                    logger.error(f"Balance query failed: {data}")
                    return self._balance

        except Exception as e:
            logger.error(f"M-Pesa balance query error: {e}")
            return self._balance

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        currency: Optional[str] = None,
    ) -> List[Transaction]:
        """Get transaction history."""
        return self._transactions[offset:offset + limit]

    async def get_account_details(self) -> AccountDetails:
        """Get M-Pesa account details."""
        return AccountDetails(
            provider=self.provider_id,
            currency="KES",
            address=self.config.shortcode,
            network="safaricom",
            metadata={
                "environment": self.config.environment,
                "shortcode": self.config.shortcode,
                "initiator": self.config.initiator_name,
            },
        )

    async def verify_payment(self, payment_ref: str) -> PaymentVerification:
        """Verify payment status via STK Query."""
        if not await self._ensure_token():
            return PaymentVerification(
                verified=False,
                status=TransactionStatus.FAILED,
                error="Failed to authenticate",
            )

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        password = self._generate_password(timestamp)

        try:
            payload = {
                "BusinessShortCode": self.config.shortcode,
                "Password": password,
                "Timestamp": timestamp,
                "CheckoutRequestID": payment_ref,
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/mpesa/stkpushquery/v1/query",
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {self._access_token}",
                        "Content-Type": "application/json",
                    },
                )
                data = response.json()

                result_code = data.get("ResultCode")
                if result_code == "0":
                    return PaymentVerification(
                        verified=True,
                        status=TransactionStatus.CONFIRMED,
                        transaction_id=payment_ref,
                        amount=self._pending_requests.get(payment_ref, PaymentRequest(
                            request_id="",
                            provider=self.provider_id,
                            amount=Decimal("0"),
                            currency="KES",
                            description="",
                            status=PaymentRequestStatus.PENDING,
                            created_at=datetime.now(timezone.utc),
                        )).amount,
                        currency="KES",
                        timestamp=datetime.now(timezone.utc),
                    )
                elif result_code == "1032":
                    return PaymentVerification(
                        verified=False,
                        status=TransactionStatus.CANCELLED,
                        error="Transaction cancelled by user",
                    )
                else:
                    return PaymentVerification(
                        verified=False,
                        status=TransactionStatus.PENDING,
                        error=data.get("ResultDesc", "Transaction pending"),
                    )

        except Exception as e:
            logger.error(f"M-Pesa STK query error: {e}")
            return PaymentVerification(
                verified=False,
                status=TransactionStatus.FAILED,
                error=str(e),
            )
