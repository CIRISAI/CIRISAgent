"""
x402 Wallet Provider.

USDC payments on Base L2 via the x402 HTTP payment protocol.
Uses deterministic wallet derivation from CIRISVerify Ed25519 signing key.

Key security features:
1. Private key NEVER leaves CIRISVerify's secure element
2. Attestation-gated spending (Level 0-5 → $0-$100/tx)
3. Hardware trust check (CIRISVerify 1.2.x) - degraded trust → receive-only

Dependencies:
- x402[fastapi,httpx,evm]  # Core x402 protocol (future)
- eth-keys                  # Ethereum key handling
- ciris-verify>=1.2.1       # Hardware trust detection
"""

import hashlib
import hmac
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

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

logger = logging.getLogger(__name__)

# Type alias for signing callback
SigningCallback = Callable[[bytes], bytes]


@dataclass
class SpendingAuthority:
    """Spending authority based on attestation level and hardware trust.

    CIRISVerify 1.2.x Integration:
    - hardware_trust_degraded == True → max_transaction = 0 (receive-only)
    - Otherwise, attestation_level determines spending limits
    """

    max_transaction: Decimal
    max_daily: Decimal
    attestation_level: int
    hardware_trust_degraded: bool
    trust_degradation_reason: Optional[str] = None
    security_advisories: Optional[List[Dict[str, Any]]] = None

    # Attestation Level → Spending Limits (per integration guide)
    SPENDING_LIMITS: Dict[int, tuple[Decimal, Decimal]] = {
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
        """Create SpendingAuthority from attestation data.

        Args:
            attestation_level: Level 0-5 from CIRISVerify
            hardware_trust_degraded: True if hardware compromised (1.2.x)
            trust_degradation_reason: Human-readable reason
            security_advisories: CVE details for UI
        """
        # If hardware trust is degraded, force receive-only regardless of level
        if hardware_trust_degraded:
            return cls(
                max_transaction=Decimal("0.00"),
                max_daily=Decimal("0.00"),
                attestation_level=attestation_level,
                hardware_trust_degraded=True,
                trust_degradation_reason=trust_degradation_reason,
                security_advisories=security_advisories,
            )

        # Get limits from attestation level
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
        """Check if spending is allowed.

        Returns:
            (allowed, error_message) tuple
        """
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

    Key features:
    - Wallet address derived from CIRISVerify Ed25519 PUBLIC key
    - Private key NEVER leaves secure element
    - Signing delegated to CIRISVerify via callback
    - Attestation-gated spending authority
    - ~400ms finality on Base L2

    For receiving: Only needs public key (address derivation)
    For sending: Needs signing callback to CIRISVerify
    """

    DOMAIN_SEPARATOR = b"CIRIS-x402-wallet-v1"
    SUPPORTED_CURRENCIES = ["USDC", "ETH"]

    def __init__(
        self,
        config: X402ProviderConfig,
        ed25519_public_key: Optional[bytes] = None,
        ed25519_seed: Optional[bytes] = None,
        signing_callback: Optional[SigningCallback] = None,
    ) -> None:
        """
        Initialize the x402 provider.

        Args:
            config: Provider configuration
            ed25519_public_key: Ed25519 public key (32 bytes) for address derivation.
                               This is the preferred method - key stays in secure element.
            ed25519_seed: Optional Ed25519 seed (32 bytes) for testing only.
                         In production, use public_key + signing_callback instead.
            signing_callback: Callback to CIRISVerify for signing operations.
                            Required for send operations if using public_key mode.
        """
        self.config = config
        self._ed25519_public_key = ed25519_public_key
        self._ed25519_seed = ed25519_seed  # Only for testing
        self._signing_callback = signing_callback
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

        # Balance monitor for detecting incoming transfers
        # Initialized after wallet address is derived
        self._balance_monitor: Optional[BalanceMonitor] = None
        self._balance_change_callbacks: List[Any] = []

        # Cached spending authority (refreshed on attestation change)
        self._spending_authority: Optional[SpendingAuthority] = None

        # Chain client for on-chain queries (RPC)
        self._chain_client = ChainClient(
            network=config.network,
            rpc_url=config.rpc_url,
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

    def _derive_evm_address_from_pubkey(self, public_key: bytes) -> str:
        """
        Derive EVM wallet address from Ed25519 PUBLIC key.

        This is the secure method - private key never leaves CIRISVerify.
        Uses HKDF-SHA256 with domain separation to create a deterministic
        mapping from Ed25519 public key to EVM address.

        Args:
            public_key: Ed25519 public key (32 bytes)

        Returns:
            EVM address (0x...)
        """
        # HKDF with public key as input keying material
        # This creates a deterministic, one-way mapping
        prk = hmac.new(self.DOMAIN_SEPARATOR, public_key, hashlib.sha256).digest()
        info = b"evm-address-from-ed25519-pubkey"
        address_bytes = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:20]

        # Convert to checksum address
        address_hex = address_bytes.hex()
        return self._to_checksum_address(address_hex)

    def _to_checksum_address(self, address_hex: str) -> str:
        """Convert raw hex to EIP-55 checksum address."""
        address_hex = address_hex.lower().replace("0x", "")
        hash_bytes = hashlib.sha3_256(address_hex.encode()).digest()

        checksum_address = "0x"
        for i, char in enumerate(address_hex):
            if char in "0123456789":
                checksum_address += char
            elif hash_bytes[i // 2] >> (4 * (1 - i % 2)) & 0xF >= 8:
                checksum_address += char.upper()
            else:
                checksum_address += char
        return checksum_address

    def _derive_evm_address_from_seed(self, seed: bytes) -> str:
        """
        Derive EVM wallet address from Ed25519 seed (TESTING ONLY).

        In production, use _derive_evm_address_from_pubkey instead.
        This method is only for testing when we have direct access to the seed.
        """
        try:
            from eth_keys import keys as eth_keys

            # HKDF-extract
            prk = hmac.new(self.DOMAIN_SEPARATOR, seed, hashlib.sha256).digest()

            # HKDF-expand to 32 bytes (secp256k1 private key)
            info = b"evm-secp256k1-signing-key"
            okm = hmac.new(prk, info + b"\x01", hashlib.sha256).digest()

            # Derive EVM address from secp256k1 private key
            private_key = eth_keys.PrivateKey(okm)
            address: str = private_key.public_key.to_checksum_address()
            return address

        except ImportError:
            logger.warning("eth_keys not installed, using HKDF-based address")
            # Fall back to HKDF-based address derivation
            return self._derive_evm_address_from_pubkey(seed)

    async def initialize(self) -> bool:
        """Initialize the provider and derive wallet address."""
        logger.info(f"Initializing X402Provider on {self.config.network}")

        # Priority: public_key (secure) > seed (testing only)
        if self._ed25519_public_key:
            self._evm_address = self._derive_evm_address_from_pubkey(self._ed25519_public_key)
            logger.info(f"Derived wallet address from public key: {self._evm_address}")
            if not self._signing_callback:
                logger.warning("No signing callback - send operations will fail (receive-only mode)")
        elif self._ed25519_seed:
            logger.warning("Using Ed25519 seed directly - this should only be used for testing!")
            self._evm_address = self._derive_evm_address_from_seed(self._ed25519_seed)
            logger.info(f"Derived wallet address from seed: {self._evm_address}")
        else:
            logger.warning("No Ed25519 key provided - wallet will use placeholder address")
            # Generate a deterministic placeholder for testing
            placeholder = hashlib.sha256(b"CIRIS-no-key-placeholder").digest()[:20]
            self._evm_address = self._to_checksum_address(placeholder.hex())
            logger.info(f"Using placeholder address: {self._evm_address}")

        self._initialized = True

        # Start balance monitor for incoming transfer detection
        self._balance_monitor = BalanceMonitor(
            provider_id=self.provider_id,
            get_balance_fn=self._fetch_balance_from_chain,
            poll_interval=30.0,  # Poll every 30 seconds
            on_balance_change=self._on_balance_change,
        )
        await self._balance_monitor.start()
        logger.info(f"Balance monitor started for {self._evm_address}")

        return True

    def _on_balance_change(
        self, provider_id: str, new_balance: Balance, incoming_tx: Optional[Transaction]
    ) -> None:
        """Handle balance change notifications from monitor."""
        # Update internal balance
        self._balance = new_balance

        # Notify registered callbacks
        for callback in self._balance_change_callbacks:
            try:
                callback(provider_id, new_balance, incoming_tx)
            except Exception as e:
                logger.error(f"Balance change callback error: {e}")

        # Log incoming transfers
        if incoming_tx:
            logger.info(
                f"[{provider_id}] Incoming transfer detected: "
                f"+{incoming_tx.amount} {incoming_tx.currency}"
            )
            self._transactions.insert(0, incoming_tx)

    async def _fetch_balance_from_chain(self) -> Balance:
        """Fetch balance from blockchain via RPC.

        Queries:
        1. USDC balance via ERC-20 balanceOf()
        2. ETH balance via eth_getBalance (for gas estimation)

        Returns:
            Balance with on-chain USDC amount
        """
        if not self._evm_address:
            logger.warning("[X402] No wallet address, returning zero balance")
            return Balance(
                currency="USDC",
                available=Decimal("0"),
                pending=Decimal("0"),
                total=Decimal("0"),
            )

        try:
            # Query USDC balance from chain
            usdc_balance = await self._chain_client.get_usdc_balance(self._evm_address)

            # Also query ETH for gas estimation (stored in metadata)
            eth_balance = await self._chain_client.get_eth_balance(self._evm_address)

            logger.debug(
                f"[X402] On-chain balance for {self._evm_address}: "
                f"{usdc_balance} USDC, {eth_balance} ETH"
            )

            # Update internal balance
            self._balance = Balance(
                currency="USDC",
                available=usdc_balance,
                pending=Decimal("0"),  # Pending would require mempool scanning
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
            # Return cached balance on error
            return self._balance

    def register_balance_callback(self, callback: Any) -> None:
        """Register a callback for balance changes."""
        self._balance_change_callbacks.append(callback)

    async def cleanup(self) -> None:
        """Cleanup provider resources."""
        logger.info("Cleaning up X402Provider")

        # Stop balance monitor
        if self._balance_monitor:
            await self._balance_monitor.stop()
            self._balance_monitor = None

        self._initialized = False

    def _get_spending_authority(self) -> SpendingAuthority:
        """Get spending authority from CIRISVerify attestation.

        CIRISVerify 1.2.x Integration:
        1. Check hardware_trust_degraded (vulnerable SoC, emulator, rooted)
        2. If degraded → receive-only mode
        3. Otherwise use attestation_level for spending limits

        Returns:
            SpendingAuthority with limits and trust status
        """
        # Try to get CIRISVerify instance
        try:
            from ciris_verify import CIRISVerify
            verifier = CIRISVerify()

            # Get hardware info (1.2.x feature)
            # On Android, this needs Build.* properties passed via JNI
            # For now, try the sync method which works on desktop
            # Check for 1.2.x features with hasattr for backwards compatibility
            if hasattr(verifier, "has_hardware_info_support") and verifier.has_hardware_info_support():
                hw_info = getattr(verifier, "get_hardware_info_sync", lambda: None)()

                if hw_info is not None and hw_info.hardware_trust_degraded:
                    logger.warning(
                        f"[X402] Hardware trust degraded: {hw_info.trust_degradation_reason}"
                    )
                    # Convert limitations to serializable format
                    advisories = None
                    if hw_info.limitations:
                        advisories = []
                        for lim in hw_info.limitations:
                            if lim.advisory:
                                advisories.append({
                                    "cve": lim.advisory.cve,
                                    "title": lim.advisory.title,
                                    "impact": lim.advisory.impact,
                                    "software_patchable": lim.advisory.software_patchable,
                                    "min_patch_level": lim.advisory.min_patch_level,
                                })

                    self._spending_authority = SpendingAuthority.from_attestation(
                        attestation_level=0,  # Degraded = level 0 equivalent
                        hardware_trust_degraded=True,
                        trust_degradation_reason=hw_info.trust_degradation_reason,
                        security_advisories=advisories,
                    )
                    return self._spending_authority

            # Get attestation level via license status
            challenge = os.urandom(32)
            status = verifier.get_license_status(challenge_nonce=challenge)
            level = getattr(status, "attestation_level", 0)

            self._spending_authority = SpendingAuthority.from_attestation(
                attestation_level=level,
                hardware_trust_degraded=False,
            )
            logger.info(f"[X402] Spending authority: level={level}, max_tx={self._spending_authority.max_transaction}")
            return self._spending_authority

        except ImportError:
            logger.warning("[X402] CIRISVerify not available, using minimal spending authority")
            self._spending_authority = SpendingAuthority.from_attestation(
                attestation_level=1,  # Receive-only without CIRISVerify
                hardware_trust_degraded=False,
            )
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
                error="Wallet not initialized (no Ed25519 key)",
            )

        # Check signing capability (need either callback or seed)
        if not self._signing_callback and not self._ed25519_seed:
            return TransactionResult(
                success=False,
                provider=self.provider_id,
                amount=amount,
                currency=currency,
                recipient=recipient,
                error="Cannot send: no signing capability (receive-only mode). "
                      "Ensure CIRISVerify is initialized with a key.",
            )

        # =====================================================================
        # CIRISVerify 1.2.x: Check hardware trust and spending authority
        # =====================================================================
        spending_authority = self._get_spending_authority()

        # Check if hardware trust is degraded (vulnerable SoC, emulator, rooted)
        if spending_authority.hardware_trust_degraded:
            logger.warning(f"[X402] Send blocked - hardware trust degraded")
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

        # Check if amount is within spending limits for attestation level
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

        # TODO: Implement actual x402 transaction using signing callback
        # When implemented:
        # 1. Build EIP-712 typed data for the transfer
        # 2. Sign via self._signing_callback(typed_data_hash) if available
        # 3. Submit to x402 facilitator
        #
        # For now, simulate transaction for testing
        signing_mode = "CIRISVerify callback" if self._signing_callback else "local seed (testing)"
        logger.info(
            f"[X402] Sending {amount} {currency} to {recipient}"
            f" (memo: {memo}, signing: {signing_mode})"
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
        """Get account balance.

        Uses cached balance from monitor when available (non-blocking).
        Falls back to internal tracked balance if monitor not running.
        """
        # Prefer cached balance from monitor (non-blocking)
        if self._balance_monitor and self._balance_monitor.cached_balance:
            return self._balance_monitor.cached_balance

        # Fall back to tracked balance
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
        """Get account details including attestation level from CIRISVerify."""
        # Get spending authority which includes attestation level
        spending_authority = self._get_spending_authority()

        return AccountDetails(
            provider=self.provider_id,
            currency="USDC",
            address=self._evm_address,
            network=self.config.network,
            attestation_level=spending_authority.attestation_level,
            metadata={
                "chain_id": 8453 if "mainnet" in self.config.network else 84532,
                "treasury": self.config.treasury_address,
                "hardware_trust_degraded": spending_authority.hardware_trust_degraded,
                "trust_degradation_reason": spending_authority.trust_degradation_reason,
                "max_transaction": str(spending_authority.max_transaction),
                "max_daily": str(spending_authority.max_daily),
                "security_advisories": spending_authority.security_advisories,
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
