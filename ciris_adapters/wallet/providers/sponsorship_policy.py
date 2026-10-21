"""
Gas Sponsorship Policy for Commons Credits.

Implements the no-KYC gas sponsorship rules:
1. USDC transfers only (contract allowlist)
2. Minimum $1.00 value (economic sybil resistance)
3. Global monthly budget cap

See FSD/COMMONS_CREDITS.md for full specification.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from ..schemas import SponsorshipBudgetStatus, SponsorshipEligibility

logger = logging.getLogger(__name__)


class SponsorshipPolicyConfig(BaseModel):
    """Configuration for gas sponsorship policy."""

    enabled: bool = Field(
        default=True,
        description="Enable gas sponsorship for eligible transactions",
    )

    # Contract allowlist - USDC on Base by default
    allowed_contracts: list[str] = Field(
        default=["0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"],
        description="Token contracts eligible for sponsored transfers (lowercase)",
    )

    # Function allowlist - ERC-20 transfer by default
    # transfer(address,uint256) = 0xa9059cbb
    allowed_functions: list[str] = Field(
        default=["0xa9059cbb"],
        description="Function selectors eligible for sponsorship (4-byte hex, lowercase)",
    )

    # Minimum transfer value
    min_transfer_usd: Decimal = Field(
        default=Decimal("1.00"),
        description="Minimum transfer value for sponsorship eligibility",
    )

    # Global budget
    monthly_budget_usd: Decimal = Field(
        default=Decimal("500.00"),
        description="Global monthly gas sponsorship budget in USD",
    )


class SponsorshipPolicy:
    """
    Gas sponsorship eligibility checker for Commons Credits economy.

    No KYC approach:
    - Only USDC transfers sponsored (allowlist)
    - Minimum $1 value prevents dust attacks
    - Global monthly budget caps exposure

    Attack economics: To drain $500 budget, attacker burns $500,000+ USDC.
    """

    # USDC constants
    USDC_BASE_ADDRESS = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    USDC_DECIMALS = 6

    def __init__(self, config: Optional[SponsorshipPolicyConfig] = None):
        """
        Initialize sponsorship policy.

        Args:
            config: Policy configuration (uses defaults if not provided)
        """
        self.config = config or SponsorshipPolicyConfig()

        # Normalize contract addresses to lowercase
        self._allowed_contracts = {addr.lower() for addr in self.config.allowed_contracts}

        # Normalize function selectors to lowercase
        self._allowed_functions = {fn.lower() for fn in self.config.allowed_functions}

        # Budget tracking (in-memory, resets on restart)
        # Production should persist to database
        self._month_key: Optional[str] = None
        self._month_spent_usd: Decimal = Decimal("0")
        self._month_tx_count: int = 0

    @property
    def min_transfer_raw(self) -> int:
        """Minimum transfer in raw USDC units."""
        return int(self.config.min_transfer_usd * Decimal(10**self.USDC_DECIMALS))

    def check_eligibility(
        self,
        token_address: str,
        amount_raw: int,
        function_selector: Optional[str] = None,
        estimated_gas_usd: Optional[Decimal] = None,
    ) -> SponsorshipEligibility:
        """
        Check if a transaction is eligible for gas sponsorship.

        Args:
            token_address: ERC-20 token contract address
            amount_raw: Transfer amount in raw token units
            function_selector: 4-byte function selector (e.g., "0xa9059cbb" for transfer)
            estimated_gas_usd: Estimated gas cost in USD (for budget check)

        Returns:
            SponsorshipEligibility with eligible flag, reason, and budget info
        """
        if not self.config.enabled:
            return SponsorshipEligibility(
                eligible=False,
                reason="Gas sponsorship is disabled",
            )

        # Rule 1a: Contract allowlist
        if token_address.lower() not in self._allowed_contracts:
            return SponsorshipEligibility(
                eligible=False,
                reason="Only USDC transfers are eligible for gas sponsorship",
            )

        # Rule 1b: Function allowlist (if provided)
        if function_selector and function_selector.lower() not in self._allowed_functions:
            return SponsorshipEligibility(
                eligible=False,
                reason="Only transfer() calls are eligible for gas sponsorship",
            )

        # Rule 2: Minimum transfer value
        if amount_raw < self.min_transfer_raw:
            min_usd = self.config.min_transfer_usd
            return SponsorshipEligibility(
                eligible=False,
                reason=f"Minimum transfer amount is ${min_usd} USDC",
            )

        # Rule 3: Global budget check
        self._reset_if_new_month()
        remaining = self.config.monthly_budget_usd - self._month_spent_usd

        if remaining <= Decimal("0"):
            return SponsorshipEligibility(
                eligible=False,
                reason="Monthly gas sponsorship budget exhausted",
                budget_remaining_usd=Decimal("0"),
            )

        # If we have gas estimate, check if it fits in budget
        if estimated_gas_usd is not None and estimated_gas_usd > remaining:
            return SponsorshipEligibility(
                eligible=False,
                reason="Insufficient sponsorship budget for this transaction",
                budget_remaining_usd=remaining,
                estimated_gas_usd=estimated_gas_usd,
            )

        # All checks passed
        logger.debug(
            f"[Sponsorship] Eligible: token={token_address[:10]}..., "
            f"amount={amount_raw}, budget_remaining=${remaining}"
        )

        return SponsorshipEligibility(
            eligible=True,
            reason="Transaction eligible for gas sponsorship",
            budget_remaining_usd=remaining,
            estimated_gas_usd=estimated_gas_usd,
        )

    def record_sponsorship(self, gas_cost_usd: Decimal) -> None:
        """
        Record a sponsored transaction's gas cost.

        Args:
            gas_cost_usd: Actual gas cost in USD
        """
        self._reset_if_new_month()
        self._month_spent_usd += gas_cost_usd
        self._month_tx_count += 1

        logger.info(
            f"[Sponsorship] Recorded ${gas_cost_usd} gas cost. "
            f"Month total: ${self._month_spent_usd}/{self.config.monthly_budget_usd}"
        )

    def get_budget_status(self) -> SponsorshipBudgetStatus:
        """Get current budget status."""
        self._reset_if_new_month()

        remaining = self.config.monthly_budget_usd - self._month_spent_usd
        utilization = (
            (self._month_spent_usd / self.config.monthly_budget_usd * 100)
            if self.config.monthly_budget_usd > 0
            else Decimal("0")
        )

        return SponsorshipBudgetStatus(
            month=self._month_key or self._get_month_key(),
            budget_usd=self.config.monthly_budget_usd,
            spent_usd=self._month_spent_usd,
            remaining_usd=max(remaining, Decimal("0")),
            utilization_percent=utilization,
            transactions_sponsored=self._month_tx_count,
            is_exhausted=remaining <= Decimal("0"),
        )

    def _reset_if_new_month(self) -> None:
        """Reset budget counter on month boundary."""
        current_month = self._get_month_key()

        if self._month_key != current_month:
            if self._month_key is not None:
                logger.info(
                    f"[Sponsorship] Month rollover: {self._month_key} -> {current_month}. "
                    f"Previous month: ${self._month_spent_usd} spent, "
                    f"{self._month_tx_count} transactions."
                )
            self._month_key = current_month
            self._month_spent_usd = Decimal("0")
            self._month_tx_count = 0

    @staticmethod
    def _get_month_key() -> str:
        """Get current month key (YYYY-MM)."""
        return datetime.now(timezone.utc).strftime("%Y-%m")


# Global singleton for policy (can be overridden in tests)
_policy_instance: Optional[SponsorshipPolicy] = None


def get_sponsorship_policy(config: Optional[SponsorshipPolicyConfig] = None) -> SponsorshipPolicy:
    """
    Get the global sponsorship policy instance.

    Args:
        config: Optional config to use (only applies on first call)

    Returns:
        SponsorshipPolicy singleton
    """
    global _policy_instance
    if _policy_instance is None:
        _policy_instance = SponsorshipPolicy(config)
    return _policy_instance


def reset_sponsorship_policy() -> None:
    """Reset the global policy instance (for testing)."""
    global _policy_instance
    _policy_instance = None
