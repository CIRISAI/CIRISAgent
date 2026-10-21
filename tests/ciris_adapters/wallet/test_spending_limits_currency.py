"""Spending ceilings are denominated, and a mismatch denies (#946).

`SpendingLimits` declared three bare `Decimal`s with no currency, while
`SpendingTracker` accumulates spend keyed BY currency. So `max_transaction=100`
passed 100 USDC and 100 KES alike — values roughly three orders of magnitude
apart. The ceiling was not a bound on value; it was "N of whatever is being
sent", and every comparison silently assumed the operator meant the currency of
the transaction in front of it.

This became load-bearing rather than merely imprecise when #939 made
`spending_limits` the outer trust envelope that a human-approved task budget
nests inside.

Two properties under test: a declared currency is enforced, and an undeclared
one is not silently invented — an existing config must not acquire a
denomination its operator never wrote.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ciris_adapters.wallet.config import SpendingLimits


class TestAppliesTo:
    def test_declared_and_matching_returns_true(self) -> None:
        assert SpendingLimits(currency="USDC").applies_to("USDC") is True

    def test_declared_and_mismatched_returns_false(self) -> None:
        """False means deny. Comparing a USDC ceiling against a KES amount is
        not a weaker check, it is a meaningless one."""
        assert SpendingLimits(currency="USDC").applies_to("KES") is False

    def test_undeclared_returns_none_not_true(self) -> None:
        """None is the legacy state and must stay distinguishable from a match.

        Returning True here would be the original bug with extra steps: the
        config would silently acquire whichever currency showed up first.
        """
        assert SpendingLimits().applies_to("USDC") is None
        assert SpendingLimits().currency is None

    @pytest.mark.parametrize("declared,requested", [("usdc", "USDC"), ("USDC", "usdc"), (" USDC ", "USDC")])
    def test_comparison_is_case_and_whitespace_insensitive(self, declared: str, requested: str) -> None:
        """Operators write config by hand; 'usdc' must not read as a mismatch
        and silently deny every spend."""
        assert SpendingLimits(currency=declared).applies_to(requested) is True

    def test_a_near_miss_is_still_a_mismatch(self) -> None:
        """USD and USDC are different currencies."""
        assert SpendingLimits(currency="USD").applies_to("USDC") is False


class TestMigrationSafety:
    def test_existing_config_does_not_acquire_a_currency(self) -> None:
        """#946 item 4. A config written before this field existed parses
        unchanged and stays undeclared — no default of 'USD', no inference."""
        legacy = SpendingLimits(
            max_transaction=Decimal("100.00"),
            daily_limit=Decimal("1000.00"),
            session_limit=Decimal("500.00"),
        )
        assert legacy.currency is None
        assert legacy.max_transaction == Decimal("100.00")

    def test_declaring_a_currency_does_not_move_the_ceilings(self) -> None:
        declared = SpendingLimits(currency="KES", max_transaction=Decimal("100.00"))
        assert declared.max_transaction == Decimal("100.00")
        assert declared.currency == "KES"

    def test_the_defect_in_one_assertion(self) -> None:
        """Before #946 these two configs were indistinguishable in behaviour.

        Both bound a 100-unit transaction identically, in currencies about
        three orders of magnitude apart. Now only the matching one applies.
        """
        usdc_limits = SpendingLimits(currency="USDC", max_transaction=Decimal("100.00"))
        assert usdc_limits.applies_to("USDC") is True
        assert usdc_limits.applies_to("KES") is False
