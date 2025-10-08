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
    Simple credit provider that gives 1 free credit per OAuth user.

    Used when CIRIS_BILLING_ENABLED=false to provide basic functionality
    without requiring external billing backend.
    """

    def __init__(self) -> None:
        self._usage: Dict[str, int] = {}  # Maps account cache_key -> usage count
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Initialize provider (no-op for simple provider)."""
        logger.info("SimpleCreditProvider started - 1 free credit per OAuth user")

    async def stop(self) -> None:
        """Cleanup provider (no-op for simple provider)."""
        logger.info("SimpleCreditProvider stopped")

    async def check_credit(
        self,
        account: CreditAccount,
        context: CreditContext | None = None,
    ) -> CreditCheckResult:
        """
        Check if user has their 1 free credit available.

        Each OAuth user gets exactly 1 free use. After that, billing must be enabled.
        """
        if not account.provider or not account.account_id:
            raise ValueError("Credit account must include provider and account_id")

        cache_key = account.cache_key()

        async with self._lock:
            usage_count = self._usage.get(cache_key, 0)

        # Each user gets 1 free use
        has_credit = usage_count < 1

        if has_credit:
            return CreditCheckResult(
                has_credit=True,
                credits_remaining=0,  # No paid credits
                plan_name="free",
                reason=None,
            )
        else:
            return CreditCheckResult(
                has_credit=False,
                credits_remaining=0,
                plan_name="free",
                reason="Free credit exhausted. Contact administrator to enable billing.",
            )

    async def spend_credit(
        self,
        account: CreditAccount,
        request: CreditSpendRequest,
        context: CreditContext | None = None,
    ) -> CreditSpendResult:
        """
        Spend the user's 1 free credit.

        Increments usage counter. If already used, returns failure.
        """
        if request.amount_minor <= 0:
            raise ValueError("Spend amount must be positive")

        cache_key = account.cache_key()

        async with self._lock:
            usage_count = self._usage.get(cache_key, 0)

            if usage_count >= 1:
                # Already used free credit
                return CreditSpendResult(
                    succeeded=False,
                    reason="Free credit exhausted. Contact administrator to enable billing.",
                )

            # Increment usage
            self._usage[cache_key] = usage_count + 1

        logger.info(f"User {cache_key} used their free credit")

        return CreditSpendResult(
            succeeded=True,
            transaction_id=f"free-{cache_key}-{usage_count + 1}",
            balance_remaining=0,  # No paid credits remain
            reason="Free credit used successfully",
        )


__all__ = ["SimpleCreditProvider"]
