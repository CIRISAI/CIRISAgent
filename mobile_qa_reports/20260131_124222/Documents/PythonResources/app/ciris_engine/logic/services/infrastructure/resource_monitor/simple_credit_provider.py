"""Simple credit provider for single free credit per OAuth user."""

from __future__ import annotations

import asyncio
import logging
from typing import Dict

from ciris_engine.protocols.services.infrastructure.credit_gate import CreditGateProtocol
from ciris_engine.schemas.services.credit_gate import (
    CreditAccount,
    CreditCheckResult,
    CreditContext,
    CreditSpendRequest,
    CreditSpendResult,
)

logger = logging.getLogger(__name__)


class SimpleCreditProvider(CreditGateProtocol):
    """
    Simple credit provider that gives configurable free credits per OAuth user.

    Used when CIRIS_BILLING_ENABLED=false to provide basic functionality
    without requiring external billing backend.

    Default: 0 free uses (requires billing for all operations)
    Configurable via CIRIS_SIMPLE_FREE_USES environment variable.
    """

    def __init__(self, free_uses: int = 0) -> None:
        self._free_uses = max(0, free_uses)  # Ensure non-negative
        self._usage: Dict[str, int] = {}  # Maps account cache_key -> usage count
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Initialize provider (no-op for simple provider)."""
        logger.info(f"SimpleCreditProvider started - {self._free_uses} free uses per OAuth user")

    async def stop(self) -> None:
        """Cleanup provider (no-op for simple provider)."""
        logger.info("SimpleCreditProvider stopped")

    async def check_credit(
        self,
        account: CreditAccount,
        context: CreditContext | None = None,
    ) -> CreditCheckResult:
        """
        Check if user has free credits available.

        Each OAuth user gets configured number of free uses. After that, billing must be enabled.
        """
        if not account.provider or not account.account_id:
            raise ValueError("Credit account must include provider and account_id")

        cache_key = account.cache_key()

        async with self._lock:
            usage_count = self._usage.get(cache_key, 0)

        # Check if user has free uses remaining
        has_credit = usage_count < self._free_uses

        if has_credit:
            return CreditCheckResult(
                has_credit=True,
                credits_remaining=self._free_uses - usage_count,
                plan_name="free",
                reason=None,
            )
        else:
            if self._free_uses == 0:
                reason = "No free uses available. Contact administrator to enable billing."
            else:
                reason = "Free uses exhausted. Contact administrator to enable billing."
            return CreditCheckResult(
                has_credit=False,
                credits_remaining=0,
                plan_name="free",
                reason=reason,
            )

    async def spend_credit(
        self,
        account: CreditAccount,
        request: CreditSpendRequest,
        context: CreditContext | None = None,
    ) -> CreditSpendResult:
        """
        Spend the user's free credit.

        Increments usage counter. If already used all free uses, returns failure.
        """
        if request.amount_minor <= 0:
            raise ValueError("Spend amount must be positive")

        cache_key = account.cache_key()

        async with self._lock:
            usage_count = self._usage.get(cache_key, 0)

            if usage_count >= self._free_uses:
                # Already used all free credits
                if self._free_uses == 0:
                    reason = "No free uses available. Contact administrator to enable billing."
                else:
                    reason = "Free uses exhausted. Contact administrator to enable billing."
                return CreditSpendResult(
                    succeeded=False,
                    reason=reason,
                )

            # Increment usage
            self._usage[cache_key] = usage_count + 1

        remaining = self._free_uses - (usage_count + 1)
        logger.info(f"User {cache_key} used free credit ({usage_count + 1}/{self._free_uses}, {remaining} remaining)")

        return CreditSpendResult(
            succeeded=True,
            transaction_id=f"free-{cache_key}-{usage_count + 1}",
            balance_remaining=remaining,
            reason=f"Free use successful ({remaining} remaining)",
        )


__all__ = ["SimpleCreditProvider"]
