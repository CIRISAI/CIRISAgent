"""
x402 Wallet Provider.

USDC payments on Base L2 via the x402 HTTP payment protocol.
All wallet primitives (address derivation, signing) come from CIRISVerify.

Key Architecture (FSD-WALLET-001):
1. Ed25519 root identity stored in CIRISVerify (hardware-backed when available)
2. secp256k1 wallet key derived via HKDF from Ed25519 seed
3. EVM address derived from secp256k1 public key (keccak256)
4. Address derivation and signing BOTH happen in CIRISVerify → guaranteed match

CRITICAL: CIRISVerify is the ONLY source for wallet operations.
- No fallback address derivation
- No local key handling
- If CIRISVerify is unavailable, wallet operations fail

Key security features:
1. Private keys NEVER leave CIRISVerify's secure boundary
2. Hardware-backed signing on Android (StrongBox/TEE) and iOS (Keychain)
3. Software fallback with secure storage on desktop/server
4. Attestation-gated spending (Level 0-5 → $0-$100/tx)
5. Hardware trust check - degraded trust → receive-only mode

Dependencies:
- ciris-verify>=1.3.1       # Unified wallet signing (secp256k1 + EVM support)
- httpx                     # RPC client for Base L2
"""

import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, ClassVar, Dict, List, Optional

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
from .balance_monitor import BalanceMonitor
from .base import WalletProvider
from .chain_client import ChainClient
from .validation import WalletValidator

logger = logging.getLogger(__name__)

# Type alias for EVM signing callback from CIRISVerify
# (tx_hash: bytes, chain_id: int) -> signature: bytes (65 bytes: r || s || v)
EVMSigningCallback = Callable[[bytes, int], bytes]


@dataclass
class SpendingAuthority:
    """Spending authority based on attestation level and hardware trust.

    CIRISVerify Integration:
    - hardware_trust_degraded == True → max_transaction = 0 (receive-only)
    - Otherwise, attestation_level determines spending limits
    """

    max_transaction: Decimal
    max_daily: Decimal
    attestation_level: int
    hardware_trust_degraded: bool
    trust_degradation_reason: Optional[str] = None
    security_advisories: Optional[List[Dict[str, Any]]] = None

    # Attestation Level → Spending Limits (per FSD-WALLET-001)
    SPENDING_LIMITS: ClassVar[Dict[int, tuple[Decimal, Decimal]]] = {
        5: (Decimal("100.00"), Decimal("1000.00")),  # Full trust
        4: (Decimal("100.00"), Decimal("1000.00")),  # High trust (advisory logged)
        3: (Decimal("50.00"), Decimal("500.00")),    # Medium trust
        2: (Decimal("0.10"), Decimal("1.00")),       # Low trust (micropayments)
        1: (Decimal("0.00"), Decimal("0.00")),       # Minimal (receive only)
        0: (Decimal("0.00"), Decimal("0.00")),       # None (frozen)
    }

    @classmethod
    def from_attestation(
        cls,
        attestation_level: int,
        hardware_trust_degraded: bool = False,
        trust_degradation_reason: Optional[str] = None,
        security_advisories: Optional[List[Dict[str, Any]]] = None,
    ) -> "SpendingAuthority":
        """Create SpendingAuthority from attestation data."""
        if hardware_trust_degraded:
            return cls(
                max_transaction=Decimal("0.00"),
                max_daily=Decimal("0.00"),
                attestation_level=attestation_level,
                hardware_trust_degraded=True,
                trust_degradation_reason=trust_degradation_reason,
                security_advisories=security_advisories,
            )

        limits = cls.SPENDING_LIMITS.get(attestation_level, (Decimal("0.00"), Decimal("0.00")))
        return cls(
            max_transaction=limits[0],
            max_daily=limits[1],
            attestation_level=attestation_level,
            hardware_trust_degraded=False,
            trust_degradation_reason=None,
            security_advisories=security_advisories,
        )

    def can_spend(self, amount: Decimal) -> tuple[bool, Optional[str]]:
        """Check if spending is allowed."""
        if self.hardware_trust_degraded:
            return (False, f"Hardware trust degraded: {self.trust_degradation_reason}. Receive-only mode active.")

        if self.attestation_level <= 1:
            return (False, f"Attestation level {self.attestation_level} is receive-only.")

        if amount > self.max_transaction:
            return (False, f"Amount {amount} exceeds limit {self.max_transaction} for attestation level {self.attestation_level}")

        return (True, None)


class X402Provider(WalletProvider):
    """
    x402 provider for USDC payments on Base L2.

    CRITICAL: All wallet primitives come from CIRISVerify.
    - EVM address from CIRISVerify.get_wallet_info()
    - Transaction signing from CIRISVerify.sign_evm_transaction()
    - No local key handling or fallback derivation

    Key features:
    - Hardware-backed signing on Android (StrongBox/TEE) and iOS (Keychain)
    - Software fallback with secure storage on desktop/server
    - Attestation-gated spending authority (Level 0-5 → $0-$100/tx)
    - ~400ms finality on Base L2
    """

    SUPPORTED_CURRENCIES = ["USDC", "ETH"]

    def __init__(
        self,
        config: X402ProviderConfig,
        evm_address: Optional[str] = None,
        evm_signing_callback: Optional[EVMSigningCallback] = None,
    ) -> None:
        """
        Initialize the x402 provider.

        Args:
            config: Provider configuration
            evm_address: Checksummed EVM address from CIRISVerify.get_wallet_info()
            evm_signing_callback: Callback to sign EVM transactions:
                                 (tx_hash: bytes, chain_id: int) -> signature: bytes

        Raises:
            ValueError: If CIRISVerify wallet is not available (evm_address is None)
        """
        self.config = config

        # CIRISVerify wallet primitives - REQUIRED
        if not evm_address:
            raise ValueError(
                "CIRISVerify wallet not available. "
                "x402 provider requires CIRISVerify 1.3.1+ with a loaded key."
            )

        self._evm_address = evm_address
        self._evm_signing_callback = evm_signing_callback
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

        # Balance monitor for detecting incoming transfers
        self._balance_monitor: Optional[BalanceMonitor] = None
        self._balance_change_callbacks: List[Any] = []

        # Cached spending authority (refreshed on attestation change)
        self._spending_authority: Optional[SpendingAuthority] = None

        # Chain client for on-chain queries (RPC)
        self._chain_client = ChainClient(
            network=config.network,
            rpc_url=config.rpc_url,
        )

        # Validator for mission-critical safety checks
        # Limits will be updated from attestation level
        self._validator = WalletValidator()

        logger.info(
            f"X402Provider created for network: {config.network}, "
            f"address: {self._evm_address}"
        )

    @property
    def provider_id(self) -> str:
        return "x402"

    @property
    def supported_currencies(self) -> List[str]:
        return self.SUPPORTED_CURRENCIES

    @property
    def evm_address(self) -> str:
        """Get the EVM wallet address (from CIRISVerify)."""
        return self._evm_address

    @property
    def can_sign(self) -> bool:
        """Check if signing is available."""
        return self._evm_signing_callback is not None

    async def initialize(self) -> bool:
        """Initialize async components (balance monitor, etc.)."""
        logger.info(f"Initializing X402Provider on {self.config.network}")

        if not self._evm_signing_callback:
            logger.warning("No signing callback - send operations will fail (receive-only mode)")

        self._initialized = True

        # Start balance monitor for incoming transfer detection
        self._balance_monitor = BalanceMonitor(
            provider_id=self.provider_id,
            get_balance_fn=self._fetch_balance_from_chain,
            poll_interval=30.0,
            on_balance_change=self._on_balance_change,
        )
        await self._balance_monitor.start()
        logger.info(f"Balance monitor started for {self._evm_address}")

        return True

    def _on_balance_change(
        self, provider_id: str, new_balance: Balance, incoming_tx: Optional[Transaction]
    ) -> None:
        """Handle balance change notifications from monitor."""
        self._balance = new_balance

        for callback in self._balance_change_callbacks:
            try:
                callback(provider_id, new_balance, incoming_tx)
            except Exception as e:
                logger.error(f"Balance change callback error: {e}")

        if incoming_tx:
            logger.info(
                f"[{provider_id}] Incoming transfer detected: "
                f"+{incoming_tx.amount} {incoming_tx.currency}"
            )
            self._transactions.insert(0, incoming_tx)

    async def _fetch_balance_from_chain(self) -> Balance:
        """Fetch balance from blockchain via RPC."""
        try:
            usdc_balance = await self._chain_client.get_usdc_balance(self._evm_address)
            eth_balance = await self._chain_client.get_eth_balance(self._evm_address)

            logger.debug(
                f"[X402] On-chain balance for {self._evm_address}: "
                f"{usdc_balance} USDC, {eth_balance} ETH"
            )

            self._balance = Balance(
                currency="USDC",
                available=usdc_balance,
                pending=Decimal("0"),
                total=usdc_balance,
                metadata={
                    "eth_balance": str(eth_balance),
                    "address": self._evm_address,
                    "network": self.config.network,
                },
            )
            return self._balance

        except Exception as e:
            logger.error(f"[X402] Failed to fetch on-chain balance: {e}")
            return self._balance

    def register_balance_callback(self, callback: Any) -> None:
        """Register a callback for balance changes."""
        self._balance_change_callbacks.append(callback)

    async def cleanup(self) -> None:
        """Cleanup provider resources."""
        logger.info("Cleaning up X402Provider")

        if self._balance_monitor:
            await self._balance_monitor.stop()
            self._balance_monitor = None

        self._initialized = False

    def _get_spending_authority(self) -> SpendingAuthority:
        """Get spending authority from CIRISVerify attestation."""
        try:
            from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import (
                get_verifier,
            )

            verifier = get_verifier()

            # Check for hardware trust degradation
            if getattr(verifier, '_has_wallet_support', False):
                try:
                    hw_info = getattr(verifier, "get_hardware_info_sync", lambda: None)()
                    if hw_info is not None and getattr(hw_info, 'hardware_trust_degraded', False):
                        logger.warning(
                            f"[X402] Hardware trust degraded: {hw_info.trust_degradation_reason}"
                        )
                        advisories = None
                        if hasattr(hw_info, 'limitations') and hw_info.limitations:
                            advisories = []
                            for lim in hw_info.limitations:
                                if hasattr(lim, 'advisory') and lim.advisory:
                                    advisories.append({
                                        "cve": lim.advisory.cve,
                                        "title": lim.advisory.title,
                                        "impact": lim.advisory.impact,
                                    })

                        self._spending_authority = SpendingAuthority.from_attestation(
                            attestation_level=0,
                            hardware_trust_degraded=True,
                            trust_degradation_reason=hw_info.trust_degradation_reason,
                            security_advisories=advisories,
                        )
                        return self._spending_authority
                except Exception as e:
                    logger.debug(f"[X402] Hardware info check failed: {e}")

            # Get attestation level
            challenge = os.urandom(32)
            status = verifier.get_license_status(challenge_nonce=challenge)
            level = getattr(status, "attestation_level", 0)

            self._spending_authority = SpendingAuthority.from_attestation(
                attestation_level=level,
                hardware_trust_degraded=False,
            )
            logger.info(f"[X402] Spending authority: level={level}, max_tx={self._spending_authority.max_transaction}")
            return self._spending_authority

        except Exception as e:
            logger.error(f"[X402] Error getting spending authority: {e}")
            # Default to receive-only on error
            self._spending_authority = SpendingAuthority.from_attestation(
                attestation_level=1,
                hardware_trust_degraded=False,
            )
            return self._spending_authority

    async def send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        memo: Optional[str] = None,
        **kwargs: object,
    ) -> TransactionResult:
        """
        Send USDC or ETH to a recipient.

        Args:
            recipient: EVM address (0x...)
            amount: Amount in USDC (6 decimals) or ETH (18 decimals)
            currency: USDC or ETH
            memo: Optional transaction memo (not stored on-chain)

        Returns:
            TransactionResult with transaction hash and confirmation.
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

        # Check signing capability
        if not self._evm_signing_callback:
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error="Cannot send: CIRISVerify signing callback not available. "
                      "Wallet is in receive-only mode.",
            )

        # Check hardware trust and spending authority
        spending_authority = self._get_spending_authority()

        if spending_authority.hardware_trust_degraded:
            logger.warning("[X402] Send blocked - hardware trust degraded")
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=f"Send blocked: {spending_authority.trust_degradation_reason}. "
                      f"Wallet is in receive-only mode due to compromised hardware security.",
                metadata={
                    "hardware_trust_degraded": True,
                    "security_advisories": spending_authority.security_advisories,
                },
            )

        can_spend, spend_error = spending_authority.can_spend(amount)
        if not can_spend:
            logger.warning(f"[X402] Send blocked - {spend_error}")
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=spend_error,
                metadata={
                    "attestation_level": spending_authority.attestation_level,
                    "max_transaction": str(spending_authority.max_transaction),
                },
            )

        # Update validator limits from attestation level
        self._validator.update_limits_from_attestation(
            max_transaction=spending_authority.max_transaction,
            daily_limit=spending_authority.max_daily,
        )

        # Get ETH balance and gas price for validation
        try:
            eth_balance = await self._chain_client.get_eth_balance(self._evm_address)
            gas_price = await self._chain_client.get_gas_price()
        except Exception as e:
            logger.error(f"[X402] Failed to get chain state: {e}")
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=f"Failed to query chain state: {e}",
            )

        # Run all safety validations (MDD: Mission-critical checks)
        validation_result = self._validator.validate_send(
            recipient=recipient,
            amount=amount,
            currency=currency,
            eth_balance=eth_balance,
            gas_price=gas_price,
        )

        if not validation_result.valid:
            error_msg = validation_result.error_message()
            logger.warning(f"[X402] Validation failed: {error_msg}")
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=error_msg,
                metadata={
                    "validation_errors": [
                        {"code": e.code, "message": e.message, "field": e.field}
                        for e in validation_result.errors
                    ],
                    "warnings": validation_result.warnings,
                },
            )

        # Log any warnings
        for warning in validation_result.warnings:
            logger.warning(f"[X402] Validation warning: {warning}")

        # Build and sign transaction
        try:
            if currency == "USDC":
                tx_hash = await self._send_usdc(recipient, amount)
            else:  # ETH
                tx_hash = await self._send_eth(recipient, amount)

            timestamp = datetime.now(timezone.utc)

            # Record transaction
            transaction = Transaction(
                transaction_id=tx_hash,
                provider=self.provider_id,
                type=TransactionType.SEND,
                status=TransactionStatus.PENDING,
                amount=-amount,
                currency=currency,
                recipient=recipient,
                sender=self._evm_address,
                memo=memo,
                timestamp=timestamp,
                fees={"network_fee": Decimal("0.001")},  # Estimated
                confirmation={
                    "network": self.config.network,
                    "tx_hash": tx_hash,
                    "explorer_url": self._chain_client.get_explorer_url(tx_hash),
                },
            )
            self._transactions.insert(0, transaction)

            # Record for duplicate protection
            self._validator.record_successful_send(recipient, amount, currency)

            logger.info(f"[X402] Sent {amount} {currency} to {recipient}: {tx_hash}")

            return TransactionResult(
                success=True,
                transaction_id=tx_hash,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                timestamp=timestamp,
                fees={"network_fee": Decimal("0.001")},
                confirmation={
                    "network": self.config.network,
                    "tx_hash": tx_hash,
                    "explorer_url": self._chain_client.get_explorer_url(tx_hash),
                },
            )

        except Exception as e:
            logger.error(f"[X402] Transaction failed: {e}")
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error=f"Transaction failed: {e}",
            )

    async def _send_usdc(self, recipient: str, amount: Decimal) -> str:
        """Build and send ERC-20 USDC transfer transaction."""
        # Signing callback must be available (checked in send())
        assert self._evm_signing_callback is not None

        # Get nonce and gas parameters
        nonce = await self._chain_client.get_nonce(self._evm_address)
        gas_price = await self._chain_client.get_gas_price()

        # Build ERC-20 transfer transaction
        tx_data = self._chain_client.build_erc20_transfer(
            to=recipient,
            amount=amount,
            decimals=6,  # USDC has 6 decimals
        )

        # Build unsigned transaction
        unsigned_tx = {
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 65000,  # Standard ERC-20 transfer
            "to": self._chain_client.usdc_address,
            "value": 0,
            "data": tx_data,
            "chainId": self._chain_client.chain_id,
        }

        # Encode and hash the transaction
        tx_hash = self._chain_client.hash_transaction(unsigned_tx)

        # Sign with CIRISVerify
        signature = self._evm_signing_callback(tx_hash, self._chain_client.chain_id)

        # Encode signed transaction
        signed_tx = self._chain_client.encode_signed_transaction(unsigned_tx, signature)

        # Broadcast
        tx_id = await self._chain_client.send_raw_transaction(signed_tx)
        return tx_id

    async def _send_eth(self, recipient: str, amount: Decimal) -> str:
        """Build and send ETH transfer transaction."""
        # Signing callback must be available (checked in send())
        assert self._evm_signing_callback is not None

        # Get nonce and gas parameters
        nonce = await self._chain_client.get_nonce(self._evm_address)
        gas_price = await self._chain_client.get_gas_price()

        # Build unsigned transaction
        unsigned_tx = {
            "nonce": nonce,
            "gasPrice": gas_price,
            "gas": 21000,  # Standard ETH transfer
            "to": recipient,
            "value": int(amount * Decimal(10**18)),  # Convert to wei
            "data": b"",
            "chainId": self._chain_client.chain_id,
        }

        # Encode and hash the transaction
        tx_hash = self._chain_client.hash_transaction(unsigned_tx)

        # Sign with CIRISVerify
        signature = self._evm_signing_callback(tx_hash, self._chain_client.chain_id)

        # Encode signed transaction
        signed_tx = self._chain_client.encode_signed_transaction(unsigned_tx, signature)

        # Broadcast
        tx_id = await self._chain_client.send_raw_transaction(signed_tx)
        return tx_id

    async def request(
        self,
        amount: Decimal,
        currency: str,
        description: str,
        expires_at: Optional[datetime] = None,
        callback_url: Optional[str] = None,
        **kwargs: object,
    ) -> PaymentRequest:
        """Create a payment request."""
        currency = currency.upper()
        request_id = f"req_{uuid.uuid4().hex[:12]}"

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
        if self._balance_monitor and self._balance_monitor.cached_balance:
            return self._balance_monitor.cached_balance
        return self._balance

    async def get_history(
        self,
        limit: int = 50,
        offset: int = 0,
        currency: Optional[str] = None,
    ) -> List[Transaction]:
        """Get transaction history."""
        transactions = self._transactions
        if currency:
            currency = currency.upper()
            transactions = [t for t in transactions if t.currency == currency]
        return transactions[offset : offset + limit]

    async def get_account_details(self) -> AccountDetails:
        """Get account details including attestation level from CIRISVerify."""
        spending_authority = self._get_spending_authority()

        return AccountDetails(
            provider=self.provider_id,
            currency="USDC",
            address=self._evm_address,
            network=self.config.network,
            attestation_level=spending_authority.attestation_level,
            metadata={
                "chain_id": self._chain_client.chain_id,
                "treasury": self.config.treasury_address,
                "hardware_trust_degraded": spending_authority.hardware_trust_degraded,
                "trust_degradation_reason": spending_authority.trust_degradation_reason,
                "max_transaction": str(spending_authority.max_transaction),
                "max_daily": str(spending_authority.max_daily),
                "security_advisories": spending_authority.security_advisories,
                "can_sign": self.can_sign,
            },
        )

    async def verify_payment(self, payment_ref: str) -> PaymentVerification:
        """Verify a payment by reference ID."""
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
