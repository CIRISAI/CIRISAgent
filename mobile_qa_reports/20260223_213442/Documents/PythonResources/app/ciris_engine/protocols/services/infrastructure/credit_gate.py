"""Protocols for credit gating providers used by the resource monitor."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from ciris_engine.schemas.services.credit_gate import (
    CreditAccount,
    CreditCheckResult,
    CreditContext,
    CreditSpendRequest,
    CreditSpendResult,
)


@runtime_checkable
class CreditGateProtocol(Protocol):
    """Contract for asynchronous credit gating providers."""

    async def start(self) -> None:
        """Initialise provider resources (e.g., network clients)."""
        ...

    async def stop(self) -> None:
        """Release provider resources."""
        ...

    async def check_credit(
        self,
        account: CreditAccount,
        context: CreditContext | None = None,
    ) -> CreditCheckResult:
        """Check whether the account currently holds sufficient credit."""
        ...

    async def spend_credit(
        self,
        account: CreditAccount,
        request: CreditSpendRequest,
        context: CreditContext | None = None,
    ) -> CreditSpendResult:
        """Attempt to spend credit for the supplied account."""
        ...


__all__ = ["CreditGateProtocol"]
