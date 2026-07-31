"""Budget-envelope enforcement on the wallet spend path (#938 / #939).

The point of this file is the ALL-PROVIDERS test. The pre-existing spending
limits (`WalletValidator`/`SpendingTracker`) are imported by exactly one
provider — `x402_provider.py:57`. Six fiat rails (stripe, wise, mpesa, razorpay,
pix, chapa) had no agent-side spend limit at all. A deny-path test that only
exercises x402 would pass while the gate was absent on every other rail, which
is worse than no enforcement because it produces a passing suite and a false
claim.

So: every rail in `PROVIDER_MODULES` is exercised, and the assertion is that the
provider's `send` is NEVER reached without an approved budget.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_adapters.wallet.config import WalletAdapterConfig, SpendingLimits
from ciris_adapters.wallet.providers.registry import PROVIDER_MODULES
from ciris_adapters.wallet.tool_service import WalletToolService
from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.persistence.models.tickets import create_ticket, get_ticket
from ciris_engine.logic.services.governance.budget_envelope import issue_grant
from ciris_engine.schemas.services.budget_envelope import BUDGET_SPENT_METADATA_KEY, BudgetDenialReason

TICKET_ID = "PROP-WALLET-TEST"
TASK_ID = "TICKET-PROP-WALLET-TEST-20260730120000"
RECIPIENT = "0x" + "a" * 40


@pytest.fixture
def temp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    from ciris_engine.logic.persistence.models import graph as _graph_mod

    prior_engine = _graph_mod._engine
    prior_dsn = _graph_mod._engine_dsn
    initialize_database(db_path)

    yield db_path

    _graph_mod._engine = prior_engine
    _graph_mod._engine_dsn = prior_dsn
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def ticket_and_task(temp_db_path):
    import json

    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    create_ticket(
        ticket_id=TICKET_ID,
        sop="AGENT_PROPOSAL",
        ticket_type="proposal",
        status="in_progress",
        email="agent-proposal@local",
    )
    now = datetime.now(timezone.utc).isoformat()
    get_persist_engine().task_upsert(
        json.dumps(
            {
                "task_id": TASK_ID,
                "channel_id": "ticket_processing",
                "agent_occurrence_id": "default",
                "description": "spend task",
                "status": "active",
                "priority": 5,
                "created_at": now,
                "updated_at": now,
                "parent_task_id": None,
                "context": {
                    "ticket_id": TICKET_ID,
                    "correlation_id": "corr-1",
                    "channel_id": "ticket_processing",
                    "agent_occurrence_id": "default",
                },
            }
        )
    )
    return TICKET_ID, TASK_ID


def _fake_provider(provider_id: str) -> Mock:
    """A provider stand-in that records whether money would have moved."""
    provider = Mock()
    provider.provider_id = provider_id
    provider.supports_currency = Mock(return_value=True)
    result = Mock()
    result.success = True
    result.transaction_id = f"tx-{provider_id}"
    result.provider = provider_id
    result.amount = Decimal("10")
    result.currency = "USDC"
    result.recipient = RECIPIENT
    result.timestamp = datetime.now(timezone.utc)
    result.fees = {}
    result.confirmation = None
    result.error = None
    provider.send = AsyncMock(return_value=result)
    # No _validator attribute: models the six fiat rails, which have none.
    del provider._validator
    return provider


def _service(provider: Mock, max_transaction="100", daily_limit="1000") -> WalletToolService:
    config = WalletAdapterConfig(
        spending_limits=SpendingLimits(
            max_transaction=Decimal(max_transaction),
            daily_limit=Decimal(daily_limit),
            session_limit=Decimal("500"),
        )
    )
    return WalletToolService(config=config, providers={provider.provider_id: provider})


async def _grant(amount="50"):
    return await issue_grant(
        ticket_id=TICKET_ID,
        granted_amount=Decimal(amount),
        granted_currency="USDC",
        purpose="test",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        granted_by_wa_id="wa-1",
        granted_by_user_id="alice",
    )


class TestEveryRailIsGated:
    """The gate must fire for EVERY provider, not just the one with limits."""

    @pytest.mark.parametrize("provider_id", sorted(PROVIDER_MODULES.keys()))
    @pytest.mark.asyncio
    async def test_no_grant_denies_on_every_rail(self, provider_id, ticket_and_task):
        provider = _fake_provider(provider_id)
        service = _service(provider)

        result = await service.execute_tool(
            "send_money",
            {"recipient": RECIPIENT, "amount": 10, "currency": "USDC", "task_id": TASK_ID},
        )

        assert result.success is False, f"{provider_id}: spend allowed with no approved budget"
        assert result.data["denied_by"] == "budget_envelope"
        assert result.data["reason"] == BudgetDenialReason.NO_GRANTED_BUDGET.value
        provider.send.assert_not_awaited()

    @pytest.mark.parametrize("provider_id", sorted(PROVIDER_MODULES.keys()))
    @pytest.mark.asyncio
    async def test_no_task_context_denies_on_every_rail(self, provider_id, ticket_and_task):
        """A spend with no originating task reaches no rail."""
        provider = _fake_provider(provider_id)
        service = _service(provider)

        result = await service.execute_tool(
            "send_money", {"recipient": RECIPIENT, "amount": 10, "currency": "USDC"}
        )

        assert result.success is False, f"{provider_id}: spend allowed with no task context"
        assert result.data["reason"] == BudgetDenialReason.NO_TASK_CONTEXT.value
        provider.send.assert_not_awaited()

    @pytest.mark.parametrize("provider_id", sorted(PROVIDER_MODULES.keys()))
    @pytest.mark.asyncio
    async def test_over_grant_denies_on_every_rail(self, provider_id, ticket_and_task):
        provider = _fake_provider(provider_id)
        service = _service(provider)
        await _grant(amount="5")

        result = await service.execute_tool(
            "send_money",
            {"recipient": RECIPIENT, "amount": 10, "currency": "USDC", "task_id": TASK_ID},
        )

        assert result.success is False, f"{provider_id}: spend exceeded the approved budget"
        assert result.data["reason"] == BudgetDenialReason.TASK_BUDGET_EXHAUSTED.value
        provider.send.assert_not_awaited()

    @pytest.mark.parametrize("provider_id", sorted(PROVIDER_MODULES.keys()))
    @pytest.mark.asyncio
    async def test_approved_spend_reaches_every_rail(self, provider_id, ticket_and_task):
        """The gate must not break legitimate, approved spend."""
        provider = _fake_provider(provider_id)
        service = _service(provider)
        await _grant(amount="50")

        result = await service.execute_tool(
            "send_money",
            {"recipient": RECIPIENT, "amount": 10, "currency": "USDC", "task_id": TASK_ID},
        )

        assert result.success is True, f"{provider_id}: approved spend was blocked ({result.error})"
        provider.send.assert_awaited_once()


class TestTrustEnvelopeIsLoadBearing:
    """`WalletAdapterConfig.spending_limits` had zero readers before this (#939)."""

    @pytest.mark.asyncio
    async def test_config_max_transaction_bounds_the_spend(self, ticket_and_task):
        provider = _fake_provider("stripe")
        service = _service(provider, max_transaction="20", daily_limit="1000")
        await _grant(amount="500")

        result = await service.execute_tool(
            "send_money",
            {"recipient": RECIPIENT, "amount": 25, "currency": "USDC", "task_id": TASK_ID},
        )
        assert result.success is False
        assert result.data["reason"] == BudgetDenialReason.TRUST_ENVELOPE_EXCEEDED.value
        assert result.data["binding_constraint"] == "trust_envelope"
        provider.send.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_config_daily_limit_bounds_the_spend(self, ticket_and_task):
        provider = _fake_provider("wise")
        service = _service(provider, max_transaction="100", daily_limit="15")
        await _grant(amount="500")

        result = await service.execute_tool(
            "send_money",
            {"recipient": RECIPIENT, "amount": 20, "currency": "USDC", "task_id": TASK_ID},
        )
        assert result.success is False
        assert result.data["reason"] == BudgetDenialReason.TRUST_ENVELOPE_EXCEEDED.value

    @pytest.mark.asyncio
    async def test_denial_names_which_bound_bit(self, ticket_and_task):
        provider = _fake_provider("stripe")
        service = _service(provider, max_transaction="100", daily_limit="1000")
        await _grant(amount="5")

        result = await service.execute_tool(
            "send_money",
            {"recipient": RECIPIENT, "amount": 50, "currency": "USDC", "task_id": TASK_ID},
        )
        assert "Bound by: task grant" in result.error
        assert result.data["binding_constraint"] == "task_grant"


class TestSpendDecrementsTheGrant:
    @pytest.mark.asyncio
    async def test_successful_spend_is_charged_to_the_ticket(self, ticket_and_task):
        provider = _fake_provider("x402")
        service = _service(provider)
        await _grant(amount="50")

        first = await service.execute_tool(
            "send_money",
            {"recipient": RECIPIENT, "amount": 30, "currency": "USDC", "task_id": TASK_ID},
        )
        assert first.success is True

        ledger = get_ticket(TICKET_ID)["metadata"][BUDGET_SPENT_METADATA_KEY]
        assert Decimal(ledger["total_spent"]) == Decimal("30")

        # The remaining 20 is now the binding constraint.
        second = await service.execute_tool(
            "send_money",
            {"recipient": RECIPIENT, "amount": 25, "currency": "USDC", "task_id": TASK_ID},
        )
        assert second.success is False
        assert second.data["reason"] == BudgetDenialReason.TASK_BUDGET_EXHAUSTED.value
        assert second.data["granted_remaining"] == "20"

    @pytest.mark.asyncio
    async def test_grant_is_exhausted_after_full_spend(self, ticket_and_task):
        provider = _fake_provider("mpesa")
        service = _service(provider)
        await _grant(amount="20")

        ok = await service.execute_tool(
            "send_money",
            {"recipient": RECIPIENT, "amount": 20, "currency": "USDC", "task_id": TASK_ID},
        )
        assert ok.success is True

        after = await service.execute_tool(
            "send_money",
            {"recipient": RECIPIENT, "amount": Decimal("0.01"), "currency": "USDC", "task_id": TASK_ID},
        )
        assert after.success is False
        assert after.data["granted_remaining"] == "0"
