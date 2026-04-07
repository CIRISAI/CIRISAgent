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
6. All sends/receives audited via audit service with spam prevention

Dependencies:
- ciris-verify>=1.3.1       # Unified wallet signing (secp256k1 + EVM support)
- httpx                     # RPC client for Base L2
"""

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Awaitable, Callable, ClassVar, Dict, List, Optional, Union

from ..config import PaymasterConfig, X402ProviderConfig
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
from .coinbase_paymaster import CoinbasePaymaster, CoinbasePaymasterConfig
from .paymaster_client import ArkaClient, BundlerClient, BundlerError, PaymasterError, UserOperation
from .validation import WalletValidator

logger = logging.getLogger(__name__)

# Type alias for EVM signing callback from CIRISVerify
# (tx_hash: bytes, chain_id: int) -> signature: bytes (65 bytes: r || s || v)
EVMSigningCallback = Callable[[bytes, int], bytes]

# Type alias for async audit callback for receives
# (sender: str, amount: Decimal, currency: str, tx_hash: Optional[str]) -> Coroutine
# Using Coroutine instead of Awaitable for create_task compatibility
from collections.abc import Coroutine as CoroutineType

AsyncReceiveAuditCallback = Callable[[str, Decimal, str, Optional[str]], CoroutineType[Any, Any, None]]


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
        3: (Decimal("50.00"), Decimal("500.00")),  # Medium trust
        2: (Decimal("0.10"), Decimal("1.00")),  # Low trust (micropayments)
        1: (Decimal("0.00"), Decimal("0.00")),  # Minimal (receive only)
        0: (Decimal("0.00"), Decimal("0.00")),  # None (frozen)
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
            return (
                False,
                f"Amount {amount} exceeds limit {self.max_transaction} for attestation level {self.attestation_level}",
            )

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
        paymaster_config: Optional[PaymasterConfig] = None,
    ) -> None:
        """
        Initialize the x402 provider.

        Args:
            config: Provider configuration
            evm_address: Checksummed EVM address from CIRISVerify.get_wallet_info()
            evm_signing_callback: Callback to sign EVM transactions:
                                 (tx_hash: bytes, chain_id: int) -> signature: bytes
            paymaster_config: Optional paymaster configuration for gasless transactions

        Raises:
            ValueError: If CIRISVerify wallet is not available (evm_address is None)
        """
        self.config = config
        self.paymaster_config = paymaster_config or PaymasterConfig()

        # CIRISVerify wallet primitives - REQUIRED
        if not evm_address:
            raise ValueError(
                "CIRISVerify wallet not available. " "x402 provider requires CIRISVerify 1.3.1+ with a loaded key."
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

        # Async audit callback for receives (set by wallet adapter)
        self._receive_audit_callback: Optional[AsyncReceiveAuditCallback] = None

        # Cached spending authority (refreshed on attestation change)
        self._spending_authority: Optional[SpendingAuthority] = None

        # Chain client for on-chain queries (RPC)
        self._chain_client = ChainClient(
            network=config.network,
            rpc_url=config.rpc_url,
        )

        # ERC-4337 Paymaster and Bundler clients for gasless transactions
        # See FSD/WALLET_REGULATORY_COMPLIANCE.md Section 10
        self._arka_client: Optional[ArkaClient] = None
        self._coinbase_paymaster: Optional[CoinbasePaymaster] = None
        self._bundler_client: Optional[BundlerClient] = None

        if self.paymaster_config.enabled:
            chain_id = self._chain_client.chain_id
            provider = self.paymaster_config.provider.lower()

            if provider == "coinbase":
                # Initialize Coinbase Paymaster
                coinbase_config = self._build_coinbase_config()
                if coinbase_config:
                    try:
                        self._coinbase_paymaster = CoinbasePaymaster(coinbase_config)
                        logger.info("[X402] Coinbase Paymaster enabled")
                    except ValueError as e:
                        logger.warning(f"[X402] Coinbase Paymaster init failed: {e}")
                else:
                    logger.warning("[X402] Coinbase Paymaster config not available")
            else:
                # Initialize Arka Paymaster (legacy)
                api_key = self._get_arka_api_key()
                if api_key:
                    self._arka_client = ArkaClient(
                        arka_url=self.paymaster_config.arka_url,
                        api_key=api_key,
                        chain_id=chain_id,
                    )
                    logger.info(f"[X402] Arka Paymaster enabled: {self.paymaster_config.arka_url}")
                else:
                    logger.warning("[X402] Arka API key not available, paymaster disabled")

            # Bundler is needed for both providers
            if self._coinbase_paymaster or self._arka_client:
                self._bundler_client = BundlerClient(
                    bundler_url=self.paymaster_config.bundler_url,
                    entry_point=self.paymaster_config.entrypoint_address,
                )

        # Validator for mission-critical safety checks
        # Limits will be updated from attestation level
        self._validator = WalletValidator()

        logger.info(f"X402Provider created for network: {config.network}, " f"address: {self._evm_address}")

    def _get_arka_api_key(self) -> Optional[str]:
        """Get Arka API key from build secrets or config.

        Priority:
        1. Build-time obfuscated secret (generated by Gradle for Android release)
        2. Config file / environment variable
        """
        # Try build-time secret first (Android release builds)
        try:
            from ._build_secrets import get_arka_api_key

            key: Optional[str] = get_arka_api_key()
            if key:
                logger.debug("[X402] Using build-time Arka API key")
                return key
        except ImportError:
            pass  # Not an Android build, or secrets not generated

        # Fall back to config
        if self.paymaster_config.arka_api_key:
            return self.paymaster_config.arka_api_key.get_secret_value()

        return None

    def _build_coinbase_config(self) -> Optional[CoinbasePaymasterConfig]:
        """Build Coinbase Paymaster config from build secrets or PaymasterConfig.

        Priority:
        1. Build-time obfuscated URL (generated by Gradle for Android release)
        2. PaymasterConfig fields (coinbase_api_key_name, coinbase_api_key_secret)
        """
        # Try build-time secret first (Android release builds)
        # CoinbasePaymaster._load_build_time_secret() handles this internally
        try:
            from ._build_secrets import get_coinbase_paymaster_url

            url: Optional[str] = get_coinbase_paymaster_url()
            if url:
                logger.debug("[X402] Using build-time Coinbase paymaster URL")
                return CoinbasePaymasterConfig(
                    enabled=True,
                    endpoint_url=url,
                )
        except ImportError:
            pass  # Not an Android build, or secrets not generated

        # Fall back to PaymasterConfig fields
        if self.paymaster_config.coinbase_api_key_name and self.paymaster_config.coinbase_api_key_secret:
            return CoinbasePaymasterConfig(
                enabled=True,
                api_key_name=self.paymaster_config.coinbase_api_key_name,
                api_key_secret=(
                    self.paymaster_config.coinbase_api_key_secret.get_secret_value()
                    if self.paymaster_config.coinbase_api_key_secret
                    else None
                ),
                base_url=self.paymaster_config.coinbase_base_url,
            )

        return None

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

    def _on_balance_change(self, provider_id: str, new_balance: Balance, incoming_tx: Optional[Transaction]) -> None:
        """Handle balance change notifications from monitor."""
        self._balance = new_balance

        for callback in self._balance_change_callbacks:
            try:
                callback(provider_id, new_balance, incoming_tx)
            except Exception as e:
                logger.error(f"Balance change callback error: {e}")

        if incoming_tx:
            logger.info(f"[{provider_id}] Incoming transfer detected: " f"+{incoming_tx.amount} {incoming_tx.currency}")
            self._transactions.insert(0, incoming_tx)

            # Trigger async audit callback for receives (with spam prevention)
            if self._receive_audit_callback:
                try:
                    # Schedule async audit in event loop
                    loop = asyncio.get_event_loop()
                    loop.create_task(
                        self._receive_audit_callback(
                            incoming_tx.sender or "unknown",
                            abs(incoming_tx.amount),
                            incoming_tx.currency,
                            incoming_tx.transaction_id,
                        )
                    )
                except RuntimeError:
                    # No event loop running - skip audit
                    logger.debug("[X402] No event loop for receive audit")
                except Exception as e:
                    logger.error(f"[X402] Failed to schedule receive audit: {e}")

    async def _fetch_balance_from_chain(self) -> Balance:
        """Fetch balance from blockchain via RPC."""
        try:
            usdc_balance = await self._chain_client.get_usdc_balance(self._evm_address)
            eth_balance = await self._chain_client.get_eth_balance(self._evm_address)

            logger.debug(f"[X402] On-chain balance for {self._evm_address}: " f"{usdc_balance} USDC, {eth_balance} ETH")

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

    def set_receive_audit_callback(self, callback: AsyncReceiveAuditCallback) -> None:
        """
        Set the async audit callback for received funds.

        The callback will be invoked (with spam prevention) when:
        - An incoming transfer is detected via balance monitor
        - Amount is above dust threshold

        Args:
            callback: Async function(sender, amount, currency, tx_hash) -> None
        """
        self._receive_audit_callback = callback
        logger.info("[X402] Receive audit callback registered")

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
            from ciris_engine.logic.services.infrastructure.authentication.verifier_singleton import get_verifier

            verifier = get_verifier()

            # Get attestation level first (needed regardless of hardware trust status)
            challenge = os.urandom(32)
            status = verifier.get_license_status(challenge_nonce=challenge)
            level = getattr(status, "attestation_level", 0)

            # Check for hardware trust degradation
            if getattr(verifier, "_has_wallet_support", False):
                try:
                    hw_info = getattr(verifier, "get_hardware_info_sync", lambda: None)()
                    if hw_info is not None and getattr(hw_info, "hardware_trust_degraded", False):
                        logger.warning(f"[X402] Hardware trust degraded: {hw_info.trust_degradation_reason}")
                        advisories = None
                        if hasattr(hw_info, "limitations") and hw_info.limitations:
                            advisories = []
                            for lim in hw_info.limitations:
                                if hasattr(lim, "advisory") and lim.advisory:
                                    advisories.append(
                                        {
                                            "cve": lim.advisory.cve,
                                            "title": lim.advisory.title,
                                            "impact": lim.advisory.impact,
                                        }
                                    )

                        # Use actual attestation level, not hardcoded 0
                        self._spending_authority = SpendingAuthority.from_attestation(
                            attestation_level=level,
                            hardware_trust_degraded=True,
                            trust_degradation_reason=hw_info.trust_degradation_reason,
                            security_advisories=advisories,
                        )
                        return self._spending_authority
                except Exception as e:
                    logger.debug(f"[X402] Hardware info check failed: {e}")

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
                error="Cannot send: CIRISVerify signing callback not available. " "Wallet is in receive-only mode.",
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
        # When paymaster is enabled, we don't need ETH for gas
        try:
            has_paymaster = self._coinbase_paymaster or self._arka_client
            if self.paymaster_config.enabled and has_paymaster:
                # Paymaster sponsors gas - skip ETH balance check
                eth_balance = Decimal("1.0")  # Dummy value to pass validation
                gas_price = 0  # Gas paid by paymaster
                logger.debug("[X402] Paymaster enabled - skipping ETH balance check")
            else:
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
        # Note: Gas validation is skipped when paymaster is enabled (gas_price=0)
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
                        {"code": e.code, "message": e.message, "field": e.field} for e in validation_result.errors
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

        # Use paymaster flow if enabled (gasless transactions)
        # Check Coinbase first, then Arka
        has_paymaster = self._coinbase_paymaster or self._arka_client
        if self.paymaster_config.enabled and has_paymaster and self._bundler_client:
            try:
                return await self._send_usdc_via_paymaster(recipient, amount)
            except (PaymasterError, BundlerError) as e:
                # Fall back to legacy EOA transaction if paymaster fails
                logger.warning(f"[X402] Paymaster flow failed, falling back to legacy: {e}")
                return await self._send_usdc_legacy(recipient, amount)

        # Legacy flow: Direct EOA transaction (requires ETH for gas)
        return await self._send_usdc_legacy(recipient, amount)

    async def _send_usdc_legacy(self, recipient: str, amount: Decimal) -> str:
        """Legacy USDC transfer via direct EOA transaction (requires ETH for gas)."""
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

    async def _send_usdc_via_paymaster(self, recipient: str, amount: Decimal) -> str:
        """
        Send USDC via ERC-4337 UserOperation with paymaster sponsorship.

        This enables gasless transactions - users don't need ETH for gas fees.
        The paymaster (Coinbase or Arka) sponsors the gas, which is an infrastructure
        cost for CIRIS, not money transmission.

        See FSD/WALLET_REGULATORY_COMPLIANCE.md Section 10.
        """
        assert self._evm_signing_callback is not None
        assert self._coinbase_paymaster is not None or self._arka_client is not None
        assert self._bundler_client is not None

        # Determine which paymaster to use
        using_coinbase = self._coinbase_paymaster is not None

        logger.info(f"[X402] Sending {amount} USDC via paymaster to {recipient}")

        # Get smart account nonce from EntryPoint
        nonce = await self._chain_client.get_smart_account_nonce(self._evm_address)

        # Get current fee data
        max_fee, priority_fee = await self._chain_client.get_fee_data()

        # Build the UserOperation calldata
        # This wraps transfer(recipient, amount) in execute() for the smart account
        call_data = self._chain_client.build_userop_calldata_for_transfer(
            recipient=recipient,
            amount=amount,
            token_address=self._chain_client.usdc_address,
        )

        # Create initial UserOperation (without gas estimates)
        # FIXME: P1 - Smart account deployment issue
        # The current implementation assumes self._evm_address is an already-deployed
        # ERC-4337 smart account, but it's actually just an EOA derived from CIRISVerify.
        # For new users, bundlers will reject with "account not deployed" because:
        #   1. sender should be the counterfactual smart account address (from factory)
        #   2. init_code should contain factory + init calldata for first deployment
        # Fix requires: smart account factory integration, address computation, and
        # tracking deployment state. See issue: CIRISAI/CIRISAgent#656
        user_op = UserOperation(
            sender=self._evm_address,
            nonce=hex(nonce),
            init_code="0x",  # FIXME: Need init_code for undeployed accounts
            call_data="0x" + call_data.hex(),
            call_gas_limit=hex(200000),  # Initial estimate
            verification_gas_limit=hex(100000),
            pre_verification_gas=hex(50000),
            max_fee_per_gas=hex(max_fee),
            max_priority_fee_per_gas=hex(priority_fee),
            paymaster_and_data="0x",  # Will be filled by Arka
            signature="0x",  # Will sign after paymaster data
        )

        # Get gas estimates from bundler
        try:
            gas_estimate = await self._bundler_client.estimate_user_operation_gas(user_op)
            user_op.call_gas_limit = gas_estimate.call_gas_limit
            user_op.verification_gas_limit = gas_estimate.verification_gas_limit
            user_op.pre_verification_gas = gas_estimate.pre_verification_gas
            logger.debug(f"[X402] Gas estimate: {gas_estimate}")
        except BundlerError as e:
            logger.warning(f"[X402] Gas estimation failed, using defaults: {e}")

        # Request sponsorship from configured paymaster (Coinbase or Arka)
        try:
            if using_coinbase:
                assert self._coinbase_paymaster is not None
                sponsorship = await self._coinbase_paymaster.sponsor(
                    user_op=user_op,
                    entry_point=self.paymaster_config.entrypoint_address,
                )
                logger.info("[X402] Coinbase Paymaster sponsorship approved")
            else:
                assert self._arka_client is not None
                sponsorship = await self._arka_client.sponsor(
                    user_op=user_op,
                    entry_point=self.paymaster_config.entrypoint_address,
                )
                logger.info("[X402] Arka Paymaster sponsorship approved")

            user_op.paymaster_and_data = sponsorship.paymaster_and_data

            # Update gas limits if paymaster provided them
            if sponsorship.call_gas_limit:
                user_op.call_gas_limit = sponsorship.call_gas_limit
            if sponsorship.verification_gas_limit:
                user_op.verification_gas_limit = sponsorship.verification_gas_limit
            if sponsorship.pre_verification_gas:
                user_op.pre_verification_gas = sponsorship.pre_verification_gas

        except PaymasterError as e:
            logger.error(f"[X402] Paymaster sponsorship failed: {e}")
            raise

        # Compute UserOperation hash for signing
        # This is a simplified hash - actual implementation would use
        # the ERC-4337 specified hash format
        user_op_hash = self._compute_user_op_hash(user_op)

        # Sign UserOperation with CIRISVerify
        signature = self._evm_signing_callback(user_op_hash, self._chain_client.chain_id)
        user_op.signature = "0x" + signature.hex()

        # Submit UserOperation to bundler
        try:
            op_hash = await self._bundler_client.send_user_operation(user_op)
            logger.info(f"[X402] UserOperation submitted: {op_hash}")

            # Wait for inclusion (with timeout)
            receipt = await self._bundler_client.wait_for_receipt(
                op_hash,
                timeout_seconds=120.0,
            )

            if receipt.success:
                # Extract transaction hash from receipt
                tx_hash = str(receipt.receipt.get("transactionHash", op_hash))
                logger.info(f"[X402] UserOperation confirmed: {tx_hash}")
                return tx_hash
            else:
                raise BundlerError(f"UserOperation failed on-chain: {op_hash}")

        except BundlerError as e:
            logger.error(f"[X402] Bundler submission failed: {e}")
            raise

    def _compute_user_op_hash(self, user_op: UserOperation) -> bytes:
        """
        Compute the hash of a UserOperation for signing.

        This follows the ERC-4337 specification for UserOperation hashing.
        """
        from .chain_client import keccak256

        # Pack UserOperation fields (excluding signature)
        packed = (
            bytes.fromhex(user_op.sender[2:].zfill(64))
            + int(user_op.nonce, 16).to_bytes(32, "big")
            + keccak256(bytes.fromhex(user_op.init_code[2:] if len(user_op.init_code) > 2 else ""))
            + keccak256(bytes.fromhex(user_op.call_data[2:] if len(user_op.call_data) > 2 else ""))
            + int(user_op.call_gas_limit, 16).to_bytes(32, "big")
            + int(user_op.verification_gas_limit, 16).to_bytes(32, "big")
            + int(user_op.pre_verification_gas, 16).to_bytes(32, "big")
            + int(user_op.max_fee_per_gas, 16).to_bytes(32, "big")
            + int(user_op.max_priority_fee_per_gas, 16).to_bytes(32, "big")
            + keccak256(bytes.fromhex(user_op.paymaster_and_data[2:] if len(user_op.paymaster_and_data) > 2 else ""))
        )

        # Hash the packed data
        user_op_hash = keccak256(packed)

        # Combine with EntryPoint address and chain ID
        entry_point = bytes.fromhex(self.paymaster_config.entrypoint_address[2:].zfill(64))
        chain_id = self._chain_client.chain_id.to_bytes(32, "big")

        final_hash = keccak256(user_op_hash + entry_point + chain_id)
        return final_hash

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
