"""
Wallet Audit Helper - Audit wallet events with spam prevention.

Provides rate-limited, dust-filtered audit logging for wallet events:
- Sends/transfers
- Receives
- Swaps
- Security events

Spam prevention:
- Dust filter: Ignore amounts below thresholds ($0.01 USDC, 0.0001 ETH)
- Error rate limiting: Max 1 error audit per fingerprint per minute
- Deduplication: Skip duplicate events within 30-second window
"""

import hashlib
import logging
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Dict, Optional

_ADDR_LOG_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")


def _addr_for_log(addr: str) -> str:
    """Render an address safely for log output.

    User-supplied addresses flow into audit logs. Anything that isn't a
    well-formed `0x`-prefixed 40-hex-char string could smuggle in CR/LF
    or ANSI control chars and forge fake log lines. Rather than sanitize
    char-by-char and keep a partial-looking address, reject the whole
    value and emit a fixed placeholder the SOC can grep for.
    """
    if isinstance(addr, str) and _ADDR_LOG_RE.match(addr):
        return addr[:10] + "..."
    return "<invalid-address>"

if TYPE_CHECKING:
    from ciris_engine.logic.services.graph.audit_service.service import GraphAuditService
    from ciris_engine.schemas.audit.core import EventPayload

logger = logging.getLogger(__name__)


# Dust thresholds - amounts below these are not audited to prevent spam
DUST_THRESHOLDS: Dict[str, Decimal] = {
    "USDC": Decimal("0.01"),  # $0.01 minimum
    "USDT": Decimal("0.01"),  # $0.01 minimum
    "ETH": Decimal("0.0001"),  # ~$0.20 minimum
    "BTC": Decimal("0.000001"),  # ~$0.10 minimum
}

# Rate limiting constants
ERROR_COOLDOWN_SECONDS = 60.0  # Max 1 error per fingerprint per minute
EVENT_DEDUP_SECONDS = 30.0  # Skip duplicate events within 30 seconds


@dataclass
class WalletAuditHelper:
    """
    Helper for auditing wallet events with spam prevention.

    Usage:
        helper = WalletAuditHelper(audit_service)
        await helper.audit_send(recipient="0x...", amount=Decimal("10.00"), currency="USDC", tx_hash="0x...")
        await helper.audit_receive(sender="0x...", amount=Decimal("5.00"), currency="USDC")
        await helper.audit_send_failed(recipient="0x...", amount=Decimal("10.00"), error="Insufficient gas")
    """

    audit_service: Optional["GraphAuditService"]

    # Rate limiting state
    _error_timestamps: Dict[str, float] = field(default_factory=dict)
    _event_timestamps: Dict[str, float] = field(default_factory=dict)

    def _is_dust(self, amount: Decimal, currency: str) -> bool:
        """Check if amount is below dust threshold."""
        threshold = DUST_THRESHOLDS.get(currency.upper(), Decimal("0.01"))
        return amount < threshold

    def _compute_event_fingerprint(
        self,
        event_type: str,
        address: str,
        amount: Decimal,
        currency: str,
    ) -> str:
        """Compute a fingerprint for event deduplication."""
        data = f"{event_type}:{address.lower()}:{amount}:{currency.upper()}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _compute_error_fingerprint(
        self,
        event_type: str,
        error: str,
    ) -> str:
        """Compute a fingerprint for error rate limiting."""
        # Normalize error message by taking first 100 chars
        error_normalized = error[:100] if error else "unknown"
        data = f"{event_type}:{error_normalized}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def _is_duplicate_event(self, fingerprint: str) -> bool:
        """Check if event is a duplicate within dedup window."""
        now = time.time()
        last_time = self._event_timestamps.get(fingerprint, 0)
        if now - last_time < EVENT_DEDUP_SECONDS:
            return True
        self._event_timestamps[fingerprint] = now
        return False

    def _is_error_rate_limited(self, fingerprint: str) -> bool:
        """Check if error is rate limited."""
        now = time.time()
        last_time = self._error_timestamps.get(fingerprint, 0)
        if now - last_time < ERROR_COOLDOWN_SECONDS:
            return True
        self._error_timestamps[fingerprint] = now
        return False

    def _cleanup_old_timestamps(self) -> None:
        """Remove old timestamps to prevent memory leak."""
        now = time.time()
        cutoff_event = now - EVENT_DEDUP_SECONDS * 2
        cutoff_error = now - ERROR_COOLDOWN_SECONDS * 2

        self._event_timestamps = {k: v for k, v in self._event_timestamps.items() if v > cutoff_event}
        self._error_timestamps = {k: v for k, v in self._error_timestamps.items() if v > cutoff_error}

    async def audit_send(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        tx_hash: Optional[str] = None,
        tx_id: Optional[str] = None,
        network: str = "base-mainnet",
    ) -> bool:
        """
        Audit a successful send/transfer.

        Args:
            recipient: Recipient address
            amount: Amount sent
            currency: Currency code (USDC, ETH, etc.)
            tx_hash: Transaction hash on-chain
            tx_id: Internal transaction ID
            network: Network name

        Returns:
            True if audited, False if skipped (dust, duplicate, or no service)
        """
        if not self.audit_service:
            logger.debug("[WALLET_AUDIT] No audit service - skipping send audit")
            return False

        # Dust filter
        if self._is_dust(amount, currency):
            logger.debug(f"[WALLET_AUDIT] Skipping dust send: {amount} {currency}")
            return False

        # Dedup filter
        fingerprint = self._compute_event_fingerprint("send", recipient, amount, currency)
        if self._is_duplicate_event(fingerprint):
            logger.debug(f"[WALLET_AUDIT] Skipping duplicate send: {fingerprint}")
            return False

        # Periodic cleanup
        self._cleanup_old_timestamps()

        try:
            from ciris_engine.schemas.audit.core import EventPayload

            payload = EventPayload(
                action="wallet_send",
                result="success",
                service_name="wallet",
                user_id=recipient[:10] + "...",  # Truncate for privacy
            )

            await self.audit_service.log_event(
                event_type="wallet_funds_sent",
                event_data=payload,
                amount=str(amount),
                currency=currency,
                recipient=recipient,
                tx_hash=tx_hash,
                tx_id=tx_id,
                network=network,
            )

            logger.info(f"[WALLET_AUDIT] Audited send: {amount} {currency} to {_addr_for_log(recipient)}")
            return True

        except Exception as e:
            logger.error(f"[WALLET_AUDIT] Failed to audit send: {e}")
            return False

    async def audit_send_failed(
        self,
        recipient: str,
        amount: Decimal,
        currency: str,
        error: str,
        network: str = "base-mainnet",
    ) -> bool:
        """
        Audit a failed send/transfer.

        Rate limited to prevent audit spam from error loops.

        Args:
            recipient: Intended recipient
            amount: Intended amount
            currency: Currency code
            error: Error message
            network: Network name

        Returns:
            True if audited, False if skipped (rate limited, dust, or no service)
        """
        if not self.audit_service:
            return False

        # Dust filter (still don't audit dust failures)
        if self._is_dust(amount, currency):
            logger.debug(f"[WALLET_AUDIT] Skipping dust send failure: {amount} {currency}")
            return False

        # Error rate limiting
        error_fingerprint = self._compute_error_fingerprint("send_failed", error)
        if self._is_error_rate_limited(error_fingerprint):
            logger.debug(f"[WALLET_AUDIT] Rate limited send failure: {error_fingerprint}")
            return False

        # Periodic cleanup
        self._cleanup_old_timestamps()

        try:
            from ciris_engine.schemas.audit.core import EventPayload

            payload = EventPayload(
                action="wallet_send",
                result="failure",
                error=error[:200],  # Truncate error message
                service_name="wallet",
                user_id=recipient[:10] + "...",
            )

            await self.audit_service.log_event(
                event_type="wallet_transfer_failed",
                event_data=payload,
                amount=str(amount),
                currency=currency,
                recipient=recipient,
                network=network,
            )

            logger.info(f"[WALLET_AUDIT] Audited send failure: {amount} {currency}")
            return True

        except Exception as e:
            logger.error(f"[WALLET_AUDIT] Failed to audit send failure: {e}")
            return False

    async def audit_receive(
        self,
        sender: str,
        amount: Decimal,
        currency: str,
        tx_hash: Optional[str] = None,
        network: str = "base-mainnet",
    ) -> bool:
        """
        Audit a received payment.

        Args:
            sender: Sender address
            amount: Amount received
            currency: Currency code
            tx_hash: Transaction hash on-chain
            network: Network name

        Returns:
            True if audited, False if skipped (dust, duplicate, or no service)
        """
        if not self.audit_service:
            return False

        # Dust filter
        if self._is_dust(amount, currency):
            logger.debug(f"[WALLET_AUDIT] Skipping dust receive: {amount} {currency}")
            return False

        # Dedup filter
        fingerprint = self._compute_event_fingerprint("receive", sender, amount, currency)
        if self._is_duplicate_event(fingerprint):
            logger.debug(f"[WALLET_AUDIT] Skipping duplicate receive: {fingerprint}")
            return False

        # Periodic cleanup
        self._cleanup_old_timestamps()

        try:
            from ciris_engine.schemas.audit.core import EventPayload

            payload = EventPayload(
                action="wallet_receive",
                result="success",
                service_name="wallet",
                user_id=sender[:10] + "...",
            )

            await self.audit_service.log_event(
                event_type="wallet_funds_received",
                event_data=payload,
                amount=str(amount),
                currency=currency,
                sender=sender,
                tx_hash=tx_hash,
                network=network,
            )

            logger.info(f"[WALLET_AUDIT] Audited receive: {amount} {currency} from {_addr_for_log(sender)}")
            return True

        except Exception as e:
            logger.error(f"[WALLET_AUDIT] Failed to audit receive: {e}")
            return False

    async def audit_swap(
        self,
        usdc_spent: Decimal,
        eth_received: Decimal,
        tx_hash: Optional[str] = None,
        network: str = "base-mainnet",
    ) -> bool:
        """
        Audit a successful USDC→ETH swap.

        Args:
            usdc_spent: USDC amount spent
            eth_received: ETH amount received
            tx_hash: Transaction hash
            network: Network name

        Returns:
            True if audited, False if skipped
        """
        if not self.audit_service:
            return False

        # Dust filter on input
        if self._is_dust(usdc_spent, "USDC"):
            logger.debug(f"[WALLET_AUDIT] Skipping dust swap: {usdc_spent} USDC")
            return False

        # Dedup filter
        fingerprint = self._compute_event_fingerprint("swap", "swap", usdc_spent, "USDC")
        if self._is_duplicate_event(fingerprint):
            logger.debug(f"[WALLET_AUDIT] Skipping duplicate swap: {fingerprint}")
            return False

        try:
            from ciris_engine.schemas.audit.core import EventPayload

            payload = EventPayload(
                action="wallet_swap",
                result="success",
                service_name="wallet",
            )

            await self.audit_service.log_event(
                event_type="wallet_swap_completed",
                event_data=payload,
                usdc_spent=str(usdc_spent),
                eth_received=str(eth_received),
                tx_hash=tx_hash,
                network=network,
            )

            logger.info(f"[WALLET_AUDIT] Audited swap: {usdc_spent} USDC → {eth_received} ETH")
            return True

        except Exception as e:
            logger.error(f"[WALLET_AUDIT] Failed to audit swap: {e}")
            return False

    async def audit_swap_failed(
        self,
        usdc_amount: Decimal,
        error: str,
        network: str = "base-mainnet",
    ) -> bool:
        """
        Audit a failed USDC→ETH swap.

        Rate limited to prevent spam.

        Args:
            usdc_amount: Intended USDC amount
            error: Error message
            network: Network name

        Returns:
            True if audited, False if skipped (rate limited)
        """
        if not self.audit_service:
            return False

        # Error rate limiting
        error_fingerprint = self._compute_error_fingerprint("swap_failed", error)
        if self._is_error_rate_limited(error_fingerprint):
            logger.debug(f"[WALLET_AUDIT] Rate limited swap failure: {error_fingerprint}")
            return False

        try:
            from ciris_engine.schemas.audit.core import EventPayload

            payload = EventPayload(
                action="wallet_swap",
                result="failure",
                error=error[:200],
                service_name="wallet",
            )

            await self.audit_service.log_event(
                event_type="wallet_swap_failed",
                event_data=payload,
                usdc_amount=str(usdc_amount),
                network=network,
            )

            logger.info(f"[WALLET_AUDIT] Audited swap failure: {usdc_amount} USDC")
            return True

        except Exception as e:
            logger.error(f"[WALLET_AUDIT] Failed to audit swap failure: {e}")
            return False

    async def audit_security_event(
        self,
        event_type: str,
        severity: str,
        description: str,
        attestation_level: Optional[int] = None,
        hardware_degraded: Optional[bool] = None,
    ) -> bool:
        """
        Audit a wallet security event.

        Args:
            event_type: Type of security event (e.g., "trust_degraded", "attestation_change")
            severity: Severity level (low, medium, high, critical)
            description: Human-readable description
            attestation_level: Current attestation level if relevant
            hardware_degraded: Whether hardware trust is degraded

        Returns:
            True if audited, False if skipped
        """
        if not self.audit_service:
            return False

        # Dedup filter - use event_type + description as fingerprint
        fingerprint = self._compute_error_fingerprint(event_type, description)
        if self._is_duplicate_event(fingerprint):
            logger.debug(f"[WALLET_AUDIT] Skipping duplicate security event: {fingerprint}")
            return False

        try:
            from ciris_engine.schemas.audit.core import EventPayload

            payload = EventPayload(
                action=event_type,
                result=severity,
                error=description if severity in ("high", "critical") else None,
                service_name="wallet",
            )

            await self.audit_service.log_event(
                event_type="wallet_security_event",
                event_data=payload,
                security_event_type=event_type,
                severity=severity,
                description=description,
                attestation_level=attestation_level,
                hardware_degraded=hardware_degraded,
            )

            logger.info(f"[WALLET_AUDIT] Audited security event: {event_type} ({severity})")
            return True

        except Exception as e:
            logger.error(f"[WALLET_AUDIT] Failed to audit security event: {e}")
            return False


# Global instance for use in wallet routes
_wallet_audit_helper: Optional[WalletAuditHelper] = None


def get_wallet_audit_helper(audit_service: Optional["GraphAuditService"] = None) -> WalletAuditHelper:
    """
    Get or create the wallet audit helper.

    Args:
        audit_service: Audit service instance. If provided, updates the helper's service.

    Returns:
        WalletAuditHelper instance
    """
    global _wallet_audit_helper

    if _wallet_audit_helper is None:
        _wallet_audit_helper = WalletAuditHelper(audit_service=audit_service)
    elif audit_service is not None:
        _wallet_audit_helper.audit_service = audit_service

    return _wallet_audit_helper
