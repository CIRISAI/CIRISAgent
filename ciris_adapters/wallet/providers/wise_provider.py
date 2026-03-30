"""
Wise Provider for Global Transfers.

Supports 56+ currencies for international money transfers
with mid-market exchange rates and transparent fees.

API Documentation: https://docs.wise.com/

Authentication:
- Personal API Token (Bearer) - for individual use
- OAuth 2.0 Client Credentials - for partners

Rate Limits: 500 requests/minute
"""

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional, cast

import httpx

from ..config import WiseProviderConfig
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


class WiseProvider(WalletProvider):
    """
    Wise provider for global money transfers.

    Flow:
    1. Create Quote → POST /v3/profiles/{profileId}/quotes
    2. Create Recipient → POST /v1/accounts
    3. Create Transfer → POST /v1/transfers
    4. Fund Transfer → POST /v3/profiles/{profileId}/transfers/{transferId}/payments

    Features:
    - 56+ currency balances
    - Mid-market exchange rates
    - Transparent fees (starting 0.33%)
    - Same-currency transfers: FREE

    Supported major currencies: USD, EUR, GBP, AUD, CAD, JPY, etc.
    """

    SANDBOX_URL = "https://api.wise-sandbox.com"
    PRODUCTION_URL = "https://api.wise.com"

    # Most commonly used currencies
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

    def __init__(self, config: WiseProviderConfig) -> None:
        self.config = config
        self._initialized = False
        self._balances: Dict[str, Balance] = {}
        self._transactions: List[Transaction] = []
        self._pending_requests: Dict[str, PaymentRequest] = {}
        self._recipients: Dict[str, Dict[str, Any]] = {}

        # Select environment
        self._base_url = self.PRODUCTION_URL if config.environment == "production" else self.SANDBOX_URL

        logger.info(f"WiseProvider created ({config.environment})")

    @property
    def provider_id(self) -> str:
        return "wise"

    @property
    def supported_currencies(self) -> List[str]:
        return self.SUPPORTED_CURRENCIES

    def _get_auth_header(self) -> Dict[str, str]:
        """Get authorization headers."""
        token = self.config.api_token.get_secret_value() if self.config.api_token else ""
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    async def initialize(self) -> bool:
        """Initialize the Wise provider."""
        logger.info("Initializing Wise provider")

        if not self.config.api_token:
            logger.error("Wise API token not configured")
            return False

        # Verify credentials and get profile
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/v1/profiles",
                    headers=self._get_auth_header(),
                )
                if response.status_code == 200:
                    profiles = response.json()
                    if profiles:
                        # Use first profile if not specified
                        if not self.config.profile_id:
                            self.config.profile_id = str(profiles[0]["id"])
                        self._initialized = True
                        logger.info(f"Wise provider initialized (profile: {self.config.profile_id})")
                        return True
                    else:
                        logger.error("No Wise profiles found")
                        return False
                else:
                    logger.error(f"Wise auth failed: {response.status_code}")
                    return False
        except Exception as e:
            logger.error(f"Wise init error: {e}")
            return False

    async def cleanup(self) -> None:
        """Cleanup provider resources."""
        self._initialized = False
        logger.info("Wise provider cleaned up")

    async def _create_quote(
        self,
        source_currency: str,
        target_currency: str,
        source_amount: Optional[Decimal] = None,
        target_amount: Optional[Decimal] = None,
    ) -> Dict[str, Any]:
        """Create a quote for currency conversion."""
        payload: Dict[str, Any] = {
            "sourceCurrency": source_currency,
            "targetCurrency": target_currency,
            "payOut": "BALANCE",
        }

        if source_amount:
            payload["sourceAmount"] = float(source_amount)
        elif target_amount:
            payload["targetAmount"] = float(target_amount)
        else:
            raise ValueError("Either source_amount or target_amount required")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/v3/profiles/{self.config.profile_id}/quotes",
                json=payload,
                headers=self._get_auth_header(),
            )
            response.raise_for_status()
            return cast(Dict[str, Any], response.json())

    async def _create_recipient(
        self,
        currency: str,
        account_holder_name: str,
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Create a recipient account."""
        payload = {
            "currency": currency,
            "type": details.get("type", "sort_code"),
            "profile": self.config.profile_id,
            "accountHolderName": account_holder_name,
            "details": details,
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._base_url}/v1/accounts",
                json=payload,
                headers=self._get_auth_header(),
            )
            response.raise_for_status()
            recipient_data: Dict[str, Any] = cast(Dict[str, Any], response.json())
            self._recipients[str(recipient_data["id"])] = recipient_data
            return recipient_data

    async def send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        memo: Optional[str] = None,
        **kwargs: object,
    ) -> TransactionResult:
        """
        Send money via Wise transfer.

        Args:
            recipient: Recipient account ID or email
            amount: Amount to send
            currency: Target currency
            memo: Transfer reference
            **kwargs: Additional params (source_currency, recipient_details)
        """
        source_currency = str(kwargs.get("source_currency", currency))
        target_currency = currency.upper()

        try:
            # Step 1: Create quote
            quote = await self._create_quote(
                source_currency=source_currency,
                target_currency=target_currency,
                target_amount=amount,
            )
            quote_id = quote["id"]

            # Step 2: Get or create recipient
            recipient_id = recipient
            if not recipient.isdigit():
                # Need to create recipient - requires account details
                recipient_details_raw = kwargs.get("recipient_details", {})
                recipient_details = cast(Dict[str, Any], recipient_details_raw) if recipient_details_raw else {}
                if not recipient_details:
                    return TransactionResult(
                        success=False,
                        provider=self.provider_id,
                        amount=amount,
                        currency=currency,
                        recipient=recipient,
                        error="recipient_details required for new recipient",
                    )
                recipient_account = await self._create_recipient(
                    currency=target_currency,
                    account_holder_name=str(recipient_details.get("name", recipient)),
                    details=recipient_details,
                )
                recipient_id = str(recipient_account["id"])

            # Step 3: Create transfer
            transfer_payload = {
                "targetAccount": int(recipient_id),
                "quoteUuid": quote_id,
                "customerTransactionId": str(uuid.uuid4()),
                "details": {
                    "reference": memo or "CIRIS Transfer",
                },
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self._base_url}/v1/transfers",
                    json=transfer_payload,
                    headers=self._get_auth_header(),
                )
                data = response.json()

                if response.status_code in (200, 201):
                    transfer_id = str(data["id"])

                    # Step 4: Fund from balance
                    fund_response = await client.post(
                        f"{self._base_url}/v3/profiles/{self.config.profile_id}/transfers/{transfer_id}/payments",
                        json={"type": "BALANCE"},
                        headers=self._get_auth_header(),
                    )

                    if fund_response.status_code in (200, 201):
                        logger.info(f"Wise transfer funded: {transfer_id}")

                        transaction = Transaction(
                            transaction_id=transfer_id,
                            provider=self.provider_id,
                            type=TransactionType.SEND,
                            status=TransactionStatus.PENDING,
                            amount=-amount,
                            currency=target_currency,
                            recipient=recipient,
                            memo=memo,
                            timestamp=datetime.now(timezone.utc),
                            fees={"wise_fee": Decimal(str(quote.get("fee", {}).get("total", 0)))},
                        )
                        self._transactions.insert(0, transaction)

                        return TransactionResult(
                            success=True,
                            transaction_id=transfer_id,
                            provider=self.provider_id,
                            amount=amount,
                            currency=target_currency,
                            recipient=recipient,
                            timestamp=datetime.now(timezone.utc),
                            fees={"wise_fee": Decimal(str(quote.get("fee", {}).get("total", 0)))},
                            confirmation={
                                "quote_id": quote_id,
                                "rate": quote.get("rate"),
                            },
                        )
                    else:
                        return TransactionResult(
                            success=False,
                            provider=self.provider_id,
                            amount=amount,
                            currency=currency,
                            recipient=recipient,
                            error=f"Failed to fund transfer: {fund_response.text}",
                        )
                else:
                    error = data.get("error") or data.get("message") or "Unknown error"
                    return TransactionResult(
                        success=False,
                        provider=self.provider_id,
                        amount=amount,
                        currency=currency,
                        recipient=recipient,
                        error=f"Wise transfer failed: {error}",
                    )

        except Exception as e:
            logger.error(f"Wise send error: {e}")
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
        Create a payment request (receive money).

        Wise uses balance account details for receiving.
        """
        # Get balance account details for the currency
        account_details = await self.get_account_details()

        request_id = str(uuid.uuid4())
        request = PaymentRequest(
            request_id=request_id,
            provider=self.provider_id,
            amount=amount,
            currency=currency.upper(),
            description=description,
            status=PaymentRequestStatus.PENDING,
            checkout_url=None,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            metadata={
                "profile_id": self.config.profile_id,
                "account_details": account_details.metadata,
                "instructions": f"Send {amount} {currency} to the Wise account details",
            },
        )
        self._pending_requests[request_id] = request
        return request

    async def get_balance(self, currency: Optional[str] = None) -> Balance:
        """Get Wise multi-currency balance."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/v1/borderless-accounts?profileId={self.config.profile_id}",
                    headers=self._get_auth_header(),
                )
                if response.status_code == 200:
                    data = response.json()
                    if data:
                        account = data[0]
                        for bal in account.get("balances", []):
                            curr = bal["currency"]
                            amount = Decimal(str(bal["amount"]["value"]))
                            self._balances[curr] = Balance(
                                currency=curr,
                                available=amount,
                                pending=Decimal("0"),
                                total=amount,
                            )

                        if currency and currency.upper() in self._balances:
                            return self._balances[currency.upper()]

                        # Return USD balance as default
                        return self._balances.get(
                            "USD",
                            Balance(
                                currency="USD",
                                available=Decimal("0"),
                                pending=Decimal("0"),
                                total=Decimal("0"),
                            ),
                        )

            return Balance(
                currency=currency or "USD",
                available=Decimal("0"),
                pending=Decimal("0"),
                total=Decimal("0"),
            )
        except Exception as e:
            logger.error(f"Wise balance error: {e}")
            return Balance(
                currency=currency or "USD",
                available=Decimal("0"),
                pending=Decimal("0"),
                total=Decimal("0"),
            )

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        currency: Optional[str] = None,
    ) -> List[Transaction]:
        """Get Wise transfer history."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/v1/transfers",
                    headers=self._get_auth_header(),
                    params={
                        "profile": self.config.profile_id,
                        "limit": limit,
                        "offset": offset,
                    },
                )
                if response.status_code == 200:
                    data = response.json()
                    transactions = []
                    for item in data:
                        status_map = {
                            "incoming_payment_waiting": TransactionStatus.PENDING,
                            "processing": TransactionStatus.PENDING,
                            "funds_converted": TransactionStatus.PENDING,
                            "outgoing_payment_sent": TransactionStatus.CONFIRMED,
                            "cancelled": TransactionStatus.CANCELLED,
                            "refunded": TransactionStatus.REFUNDED,
                        }
                        tx = Transaction(
                            transaction_id=str(item["id"]),
                            provider=self.provider_id,
                            type=TransactionType.SEND,
                            status=status_map.get(item["status"], TransactionStatus.PENDING),
                            amount=-Decimal(str(item["targetValue"])),
                            currency=item["targetCurrency"],
                            recipient=str(item.get("targetAccount")),
                            timestamp=datetime.fromisoformat(item["created"].replace("Z", "+00:00")),
                        )
                        transactions.append(tx)
                    return transactions
                return self._transactions[offset : offset + limit]
        except Exception as e:
            logger.error(f"Wise history error: {e}")
            return self._transactions[offset : offset + limit]

    async def get_account_details(self) -> AccountDetails:
        """Get Wise account details."""
        return AccountDetails(
            provider=self.provider_id,
            currency="USD",  # Multi-currency
            network="wise",
            metadata={
                "profile_id": self.config.profile_id,
                "environment": self.config.environment,
                "supported_currencies": self.SUPPORTED_CURRENCIES[:10],
            },
        )

    async def verify_payment(self, payment_ref: str) -> PaymentVerification:
        """Verify Wise transfer status."""
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(
                    f"{self._base_url}/v1/transfers/{payment_ref}",
                    headers=self._get_auth_header(),
                )

                if response.status_code == 200:
                    transfer = response.json()
                    status_map = {
                        "incoming_payment_waiting": TransactionStatus.PENDING,
                        "processing": TransactionStatus.PENDING,
                        "funds_converted": TransactionStatus.PENDING,
                        "outgoing_payment_sent": TransactionStatus.CONFIRMED,
                        "cancelled": TransactionStatus.CANCELLED,
                        "refunded": TransactionStatus.REFUNDED,
                        "bounced_back": TransactionStatus.FAILED,
                    }
                    return PaymentVerification(
                        verified=transfer["status"] == "outgoing_payment_sent",
                        status=status_map.get(transfer["status"], TransactionStatus.PENDING),
                        transaction_id=str(transfer["id"]),
                        amount=Decimal(str(transfer["targetValue"])),
                        currency=transfer["targetCurrency"],
                        timestamp=datetime.fromisoformat(transfer["created"].replace("Z", "+00:00")),
                    )

                return PaymentVerification(
                    verified=False,
                    status=TransactionStatus.FAILED,
                    error=f"Transfer not found: {payment_ref}",
                )

        except Exception as e:
            logger.error(f"Wise verify error: {e}")
            return PaymentVerification(
                verified=False,
                status=TransactionStatus.FAILED,
                error=str(e),
            )
