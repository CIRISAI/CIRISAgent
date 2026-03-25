"""
x402 Wallet Provider.

USDC payments on Base L2 via the x402 HTTP payment protocol.
Uses deterministic wallet derivation from CIRISVerify Ed25519 signing key.

Dependencies:
- x402[fastapi,httpx,evm]  # Core x402 protocol
- cdp-sdk                   # Coinbase Developer Platform
- eth-keys                  # Ethereum key handling
"""

import hashlib
import hmac
import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from ..config import X402ProviderConfig
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


class X402Provider(WalletProvider):
    """
    x402 provider for USDC payments on Base L2.

    Key features:
    - Wallet address derived from CIRISVerify Ed25519 key
    - Attestation-gated spending authority
    - Gas-free transactions via Coinbase paymaster
    - ~400ms finality on Base L2

    The signing key never leaves the secure element. This provider
    receives signing requests and returns signed transactions.
    """

    DOMAIN_SEPARATOR = b"CIRIS-x402-wallet-v1"
    SUPPORTED_CURRENCIES = ["USDC", "ETH"]

    def __init__(
        self,
        config: X402ProviderConfig,
        ed25519_seed: Optional[bytes] = None,
    ) -> None:
        """
        Initialize the x402 provider.

        Args:
            config: Provider configuration
            ed25519_seed: Optional Ed25519 seed for wallet derivation.
                         In production, this comes from secure element.
        """
        self.config = config
        self._ed25519_seed = ed25519_seed
        self._evm_address: Optional[str] = None
        self._initialized = False

        # Track pending transactions and balances (in-memory for now)
        self._pending_requests: Dict[str, PaymentRequest] = {}
        self._transactions: List[Transaction] = []
        self._balance = Balance(
            currency="USDC",
            available=Decimal("0"),
            pending=Decimal("0"),
            total=Decimal("0"),
        )

        logger.info(
            f"X402Provider created for network: {config.network}"
        )

    @property
    def provider_id(self) -> str:
        return "x402"

    @property
    def supported_currencies(self) -> List[str]:
        return self.SUPPORTED_CURRENCIES

    def _derive_evm_address(self, seed: bytes) -> str:
        """
        Derive EVM wallet address from Ed25519 seed.

        Uses HKDF-SHA256 with domain separation to derive a secp256k1 key,
        then computes the corresponding Ethereum address.

        This is deterministic: same seed always produces same address.
        """
        try:
            # Import eth_keys only when needed
            from eth_keys import keys as eth_keys

            # HKDF-extract
            prk = hmac.new(self.DOMAIN_SEPARATOR, seed, hashlib.sha256).digest()

            # HKDF-expand to 32 bytes (secp256k1 private key)
            info = b"evm-secp256k1-signing-key"
            okm = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()

            # Derive EVM address
            private_key = eth_keys.PrivateKey(okm)
            address: str = private_key.public_key.to_checksum_address()
            return address

        except ImportError:
            logger.warning("eth_keys not installed, using placeholder address")
            # Generate deterministic placeholder from seed
            hash_bytes = hashlib.sha256(self.DOMAIN_SEPARATOR + seed).digest()
            return "0x" + hash_bytes[:20].hex()

    async def initialize(self) -> bool:
        """Initialize the provider."""
        logger.info(f"Initializing X402Provider on {self.config.network}")

        if self._ed25519_seed:
            self._evm_address = self._derive_evm_address(self._ed25519_seed)
            logger.info(f"Derived wallet address: {self._evm_address}")
        else:
            logger.warning("No Ed25519 seed provided - wallet operations will fail")

        # TODO: Initialize x402 client and CDP SDK
        # from x402 import x402Client
        # from x402.mechanisms.evm.exact import ExactEvmScheme
        # self._client = x402Client()
        # self._client.register("eip155:*", ExactEvmScheme(signer=self._signer))

        self._initialized = True
        return True

    async def cleanup(self) -> None:
        """Cleanup provider resources."""
        logger.info("Cleaning up X402Provider")
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
        Send USDC to a recipient.

        Args:
            recipient: EVM address (0x...)
            amount: Amount in USDC (or ETH)
            currency: USDC or ETH
            memo: Optional transaction memo

        Returns:
            TransactionResult with transaction ID and confirmation.
        """
        currency = currency.upper()
        if currency not in self.SUPPORTED_CURRENCIES:
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=f"Unsupported currency: {currency}. Supported: {self.SUPPORTED_CURRENCIES}",
            )

        if not self._evm_address:
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error="Wallet not initialized (no Ed25519 seed)",
            )

        # Validate recipient address format
        if not recipient.startswith("0x") or len(recipient) != 42:
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=f"Invalid EVM address format: {recipient}",
            )

        # TODO: Implement actual x402 transaction
        # For now, return a simulated success for testing
        logger.info(
            f"[X402] Sending {amount} {currency} to {recipient}"
            f" (memo: {memo})"
        )

        # Generate transaction ID
        tx_id = f"0x{uuid.uuid4().hex}"
        timestamp = datetime.now(timezone.utc)

        # Record transaction
        transaction = Transaction(
            transaction_id=tx_id,
            provider=self.provider_id,
            type=TransactionType.SEND,
            status=TransactionStatus.PENDING,  # Would be CONFIRMED after blockchain confirmation
            amount=-amount,  # Negative for sends
            currency=currency,
            recipient=recipient,
            sender=self._evm_address,
            memo=memo,
            timestamp=timestamp,
            fees={"network_fee": Decimal("0.001")},
            confirmation={
                "network": self.config.network,
                "tx_hash": tx_id,
            },
        )
        self._transactions.insert(0, transaction)

        # Update balance
        self._balance.available -= amount
        self._balance.total = self._balance.available + self._balance.pending

        return TransactionResult(
            success=True,
            transaction_id=tx_id,
            provider=self.provider_id,
            amount=amount,
            currency=currency,
            recipient=recipient,
            timestamp=timestamp,
            fees={"network_fee": Decimal("0.001")},
            confirmation={
                "network": self.config.network,
                "tx_hash": tx_id,
                "block_number": None,  # Would be set after confirmation
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
        Create a payment request.

        For x402, this generates the payment details that would be
        returned in a 402 response body.
        """
        currency = currency.upper()
        request_id = f"req_{uuid.uuid4().hex[:12]}"

        # x402 payment requests don't have checkout URLs
        # Payment is made via X-PAYMENT header
        request = PaymentRequest(
            request_id=request_id,
            provider=self.provider_id,
            amount=amount,
            currency=currency,
            description=description,
            status=PaymentRequestStatus.PENDING,
            checkout_url=None,  # x402 uses in-band payment
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at,
            metadata={
                "network": self.config.network,
                "pay_to": self.config.treasury_address or self._evm_address,
                "scheme": "exact",
            },
        )

        self._pending_requests[request_id] = request
        logger.info(f"[X402] Created payment request: {request_id} for {amount} {currency}")

        return request

    async def get_balance(self, currency: Optional[str] = None) -> Balance:
        """Get account balance."""
        # TODO: Query actual balance from Base network
        # For now return tracked balance
        return self._balance

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        currency: Optional[str] = None,
    ) -> List[Transaction]:
        """Get transaction history."""
        # Filter by currency if specified
        transactions = self._transactions
        if currency:
            currency = currency.upper()
            transactions = [t for t in transactions if t.currency == currency]

        # Apply pagination
        return transactions[offset : offset + limit]

    async def get_account_details(self) -> AccountDetails:
        """Get account details."""
        return AccountDetails(
            provider=self.provider_id,
            currency="USDC",
            address=self._evm_address,
            network=self.config.network,
            attestation_level=5,  # TODO: Get from CIRISVerify
            metadata={
                "chain_id": 8453 if "mainnet" in self.config.network else 84532,
                "treasury": self.config.treasury_address,
            },
        )

    async def verify_payment(self, payment_ref: str) -> PaymentVerification:
        """Verify a payment by reference ID."""
        # Check pending requests
        if payment_ref in self._pending_requests:
            request = self._pending_requests[payment_ref]
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

    def set_balance(self, available: Decimal, pending: Decimal = Decimal("0")) -> None:
        """Set balance (for testing or funding)."""
        self._balance = Balance(
            currency="USDC",
            available=available,
            pending=pending,
            total=available + pending,
        )
        logger.info(f"[X402] Balance set: {available} USDC available, {pending} pending")
