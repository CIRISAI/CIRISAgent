"""Protocol definition for Unlimit billing services."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .schemas import (
    BillingChargeRequest,
    BillingChargeResult,
    BillingCheckResult,
    BillingContext,
    BillingIdentity,
)


@runtime_checkable
class UnlimitBillingProtocol(Protocol):
    """Contract for billing providers that gate interactions based on credits."""

    async def start(self) -> None:
        """Initialise provider resources (e.g., network clients)."""
        ...

    async def stop(self) -> None:
        """Release provider resources."""
        ...

    async def check_credits(
        self,
        identity: BillingIdentity,
        context: BillingContext | None = None,
    ) -> BillingCheckResult:
        """Return the billing decision for the supplied identity."""
        ...

    async def spend_credits(
        self,
        identity: BillingIdentity,
        charge: BillingChargeRequest,
        context: BillingContext | None = None,
    ) -> BillingChargeResult:
        """Execute a spend against the billing account."""
        ...


__all__ = ["UnlimitBillingProtocol"]
