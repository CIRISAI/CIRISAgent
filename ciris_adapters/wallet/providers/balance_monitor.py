"""
Balance Monitor for Wallet Providers.

Polls blockchain/provider APIs for balance changes and incoming transfers.
Provides cached balance data for context enrichment without blocking agent processing.
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional

from ..schemas import Balance, Transaction, TransactionStatus, TransactionType

logger = logging.getLogger(__name__)

# Type for balance change callback
BalanceChangeCallback = Callable[[str, Balance, Optional[Transaction]], None]


class BalanceMonitor:
    """
    Monitors wallet balances and detects incoming transfers.

    Features:
    - Periodic polling with configurable interval
    - Cached balance for instant access (context enrichment)
    - Change detection with callback notifications
    - Graceful degradation on network errors
    """

    DEFAULT_POLL_INTERVAL = 30.0  # seconds
    MIN_POLL_INTERVAL = 5.0
    MAX_POLL_INTERVAL = 300.0

    def __init__(
        self,
        provider_id: str,
        get_balance_fn: Callable[[], Any],
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        on_balance_change: Optional[BalanceChangeCallback] = None,
    ) -> None:
        """
        Initialize the balance monitor.

        Args:
            provider_id: Identifier for the provider being monitored
            get_balance_fn: Async function to fetch current balance
            poll_interval: Seconds between balance checks
            on_balance_change: Callback when balance changes (provider_id, new_balance, transaction)
        """
        self.provider_id = provider_id
        self._get_balance_fn = get_balance_fn
        self._poll_interval = max(
            self.MIN_POLL_INTERVAL,
            min(poll_interval, self.MAX_POLL_INTERVAL)
        )
        self._on_balance_change = on_balance_change

        # Cached state
        self._cached_balance: Optional[Balance] = None
        self._last_poll: Optional[datetime] = None
        self._poll_count = 0
        self._error_count = 0
        self._consecutive_errors = 0

        # Control
        self._running = False
        self._poll_task: Optional[asyncio.Task[None]] = None

        logger.info(
            f"BalanceMonitor created for {provider_id} "
            f"(poll_interval={self._poll_interval}s)"
        )

    @property
    def cached_balance(self) -> Optional[Balance]:
        """Get the most recently cached balance (non-blocking)."""
        return self._cached_balance

    @property
    def last_poll_time(self) -> Optional[datetime]:
        """Get the timestamp of the last successful poll."""
        return self._last_poll

    @property
    def is_running(self) -> bool:
        """Check if the monitor is actively polling."""
        return self._running

    def get_cache_age_seconds(self) -> Optional[float]:
        """Get the age of the cached balance in seconds."""
        if not self._last_poll:
            return None
        return (datetime.now(timezone.utc) - self._last_poll).total_seconds()

    async def start(self) -> None:
        """Start the balance polling loop."""
        if self._running:
            logger.warning(f"BalanceMonitor {self.provider_id} already running")
            return

        logger.info(f"Starting BalanceMonitor for {self.provider_id}")
        self._running = True

        # Do initial poll immediately
        await self._poll_once()

        # Start background polling
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop(self) -> None:
        """Stop the balance polling loop."""
        if not self._running:
            return

        logger.info(f"Stopping BalanceMonitor for {self.provider_id}")
        self._running = False

        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        logger.info(
            f"BalanceMonitor {self.provider_id} stopped "
            f"(polls={self._poll_count}, errors={self._error_count})"
        )

    async def force_refresh(self) -> Optional[Balance]:
        """Force an immediate balance refresh (bypasses poll interval)."""
        return await self._poll_once()

    async def _poll_loop(self) -> None:
        """Background polling loop."""
        while self._running:
            try:
                await asyncio.sleep(self._poll_interval)
                if self._running:  # Check again after sleep
                    await self._poll_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"BalanceMonitor {self.provider_id} poll loop error: {e}")
                self._consecutive_errors += 1
                # Back off on repeated errors
                if self._consecutive_errors > 3:
                    backoff = min(self._poll_interval * 2, self.MAX_POLL_INTERVAL)
                    logger.warning(f"Backing off to {backoff}s due to repeated errors")
                    await asyncio.sleep(backoff)

    async def _poll_once(self) -> Optional[Balance]:
        """Perform a single balance poll."""
        try:
            # Get current balance from provider
            result = await self._get_balance_fn()
            new_balance: Balance = result  # Type hint for mypy
            self._poll_count += 1
            self._consecutive_errors = 0

            # Detect changes
            old_balance = self._cached_balance
            balance_changed = self._detect_change(old_balance, new_balance)

            # Update cache
            self._cached_balance = new_balance
            self._last_poll = datetime.now(timezone.utc)

            if balance_changed:
                logger.info(
                    f"[{self.provider_id}] Balance changed: "
                    f"{old_balance.total if old_balance else 'N/A'} → {new_balance.total}"
                )

                # Detect if this was an incoming transfer
                incoming_tx = None
                if old_balance and new_balance.total > old_balance.total:
                    diff = new_balance.total - old_balance.total
                    incoming_tx = Transaction(
                        transaction_id=f"detected_{datetime.now(timezone.utc).timestamp()}",
                        provider=self.provider_id,
                        type=TransactionType.RECEIVE,
                        status=TransactionStatus.CONFIRMED,
                        amount=diff,
                        currency=new_balance.currency,
                        timestamp=datetime.now(timezone.utc),
                        metadata={"detected_by": "balance_monitor"},
                    )
                    logger.info(f"[{self.provider_id}] Detected incoming transfer: +{diff}")

                # Notify callback
                if self._on_balance_change:
                    try:
                        self._on_balance_change(self.provider_id, new_balance, incoming_tx)
                    except Exception as e:
                        logger.error(f"Balance change callback error: {e}")

            return new_balance

        except Exception as e:
            self._error_count += 1
            self._consecutive_errors += 1
            logger.warning(
                f"[{self.provider_id}] Balance poll failed: {e} "
                f"(consecutive_errors={self._consecutive_errors})"
            )
            return None

    def _detect_change(
        self,
        old: Optional[Balance],
        new: Balance
    ) -> bool:
        """Detect if balance has changed."""
        if old is None:
            return True  # First poll is always a "change"
        return (
            old.available != new.available or
            old.pending != new.pending or
            old.total != new.total
        )

    def get_stats(self) -> Dict[str, Any]:
        """Get monitoring statistics."""
        return {
            "provider_id": self.provider_id,
            "is_running": self._running,
            "poll_count": self._poll_count,
            "error_count": self._error_count,
            "consecutive_errors": self._consecutive_errors,
            "poll_interval": self._poll_interval,
            "last_poll": self._last_poll.isoformat() if self._last_poll else None,
            "cache_age_seconds": self.get_cache_age_seconds(),
            "cached_balance": {
                "available": str(self._cached_balance.available),
                "pending": str(self._cached_balance.pending),
                "total": str(self._cached_balance.total),
                "currency": self._cached_balance.currency,
            } if self._cached_balance else None,
        }
