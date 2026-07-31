"""Tests for the budget envelope nesting model (#938).

The invariants under test:
- absence of a granted budget is a DENIAL, never "unbounded"
- a spend is bounded by min(task grant remaining, trust envelope remaining)
- the denial names which bound bit
- a grant can never widen the trust-driven envelope
- spending decrements both envelopes
- the approval step cannot be reached from inside the reasoning loop
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.persistence.models.tickets import create_ticket, get_ticket
from ciris_engine.logic.services.governance.budget_envelope import (
    NestingViolation,
    authorize_spend,
    canonical_grant_payload,
    issue_grant,
    load_grant,
    load_spent_ledger,
    record_spend,
)
from ciris_engine.schemas.services.budget_envelope import (
    BUDGET_SPENT_METADATA_KEY,
    GRANTED_BUDGET_METADATA_KEY,
    REQUESTED_BUDGET_METADATA_KEY,
    BudgetDenialReason,
    GrantedBudget,
    TrustEnvelope,
)

TICKET_ID = "PROP-BUDGET-TEST"
TASK_ID = "TICKET-PROP-BUDGET-TEST-20260730120000"


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
def ticket_with_task(temp_db_path):
    """A ticket plus a task whose stored context points at it."""
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
                "description": f"Process ticket {TICKET_ID}",
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


def _trust(max_tx="100", daily="1000"):
    return TrustEnvelope(
        max_transaction=Decimal(max_tx), daily_remaining=Decimal(daily), currency="USDC"
    )


async def _grant(amount="50", hours=24, currency="USDC", ticket_id=TICKET_ID):
    return await issue_grant(
        ticket_id=ticket_id,
        granted_amount=Decimal(amount),
        granted_currency=currency,
        purpose="test spend",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=hours),
        granted_by_wa_id="wa-authority-1",
        granted_by_user_id="alice",
        auth_service=None,
    )


class TestFailClosed:
    """Absence of a grant is a denial. Never 'unbounded'."""

    @pytest.mark.asyncio
    async def test_no_task_id_denies(self, ticket_with_task):
        d = await authorize_spend(task_id=None, amount=Decimal("1"), currency="USDC", trust_envelope=_trust())
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.NO_TASK_CONTEXT

    @pytest.mark.asyncio
    async def test_task_with_no_ticket_denies(self, ticket_with_task):
        d = await authorize_spend(
            task_id="SOME-RANDOM-TASK", amount=Decimal("1"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.NO_TICKET_FOR_TASK

    @pytest.mark.asyncio
    async def test_ticket_with_no_grant_denies(self, ticket_with_task):
        """The headline case: a ticket exists, no human granted anything."""
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("0.01"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.NO_GRANTED_BUDGET
        assert "no human-approved budget" in d.message

    @pytest.mark.asyncio
    async def test_malformed_grant_denies(self, ticket_with_task):
        """Garbage in the reserved key must not read as permissive."""
        from ciris_engine.logic.persistence.models.tickets import update_ticket_metadata

        update_ticket_metadata(TICKET_ID, {GRANTED_BUDGET_METADATA_KEY: "not-a-grant"})
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("1"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.GRANT_MALFORMED

    @pytest.mark.asyncio
    async def test_expired_grant_denies(self, ticket_with_task):
        await _grant(amount="50", hours=-1)
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("1"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.GRANT_EXPIRED

    @pytest.mark.asyncio
    async def test_currency_mismatch_denies(self, ticket_with_task):
        await _grant(amount="50", currency="USDC")
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("1"), currency="KES", trust_envelope=_trust()
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.CURRENCY_MISMATCH

    @pytest.mark.asyncio
    async def test_grant_bound_to_another_ticket_denies(self, ticket_with_task):
        """A grant lifted onto a different ticket is rejected."""
        from ciris_engine.logic.persistence.models.tickets import update_ticket_metadata

        foreign = GrantedBudget(
            ticket_id="SOME-OTHER-TICKET",
            granted_amount=Decimal("1000"),
            granted_currency="USDC",
            purpose="replayed",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            granted_by_wa_id="wa-1",
            granted_by_user_id="mallory",
            granted_at=datetime.now(timezone.utc),
        )
        update_ticket_metadata(TICKET_ID, {GRANTED_BUDGET_METADATA_KEY: foreign.model_dump(mode="json")})
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("1"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.GRANT_TICKET_MISMATCH


class TestNestingInvariant:
    """min(task grant, trust envelope) — and a grant can never widen the outer bound."""

    @pytest.mark.asyncio
    async def test_spend_within_both_allowed(self, ticket_with_task):
        await _grant(amount="50")
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("10"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is True
        assert d.effective_limit == Decimal("50")

    @pytest.mark.asyncio
    async def test_task_grant_is_the_tighter_bound(self, ticket_with_task):
        await _grant(amount="20")
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("30"), currency="USDC", trust_envelope=_trust("100", "1000")
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.TASK_BUDGET_EXHAUSTED
        assert d.binding_constraint == "task_grant"
        assert "Bound by: task grant" in d.message

    @pytest.mark.asyncio
    async def test_trust_envelope_is_the_tighter_bound(self, ticket_with_task):
        """A large grant cannot widen a small trust envelope."""
        await _grant(amount="500")
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("200"), currency="USDC", trust_envelope=_trust("100", "1000")
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.TRUST_ENVELOPE_EXCEEDED
        assert d.binding_constraint == "trust_envelope"
        assert "Bound by: trust envelope" in d.message

    @pytest.mark.asyncio
    async def test_grant_larger_than_trust_never_permits_more_than_trust(self, ticket_with_task):
        """The decisive nesting test: outer bound wins regardless of the grant."""
        await _grant(amount="10000")
        trust = _trust("100", "1000")
        ok = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("100"), currency="USDC", trust_envelope=trust
        )
        assert ok.allowed is True
        assert ok.effective_limit == trust.remaining == Decimal("100")

        over = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("100.01"), currency="USDC", trust_envelope=trust
        )
        assert over.allowed is False
        assert over.reason is BudgetDenialReason.TRUST_ENVELOPE_EXCEEDED

    @pytest.mark.asyncio
    async def test_daily_remaining_tightens_the_envelope(self, ticket_with_task):
        await _grant(amount="500")
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("30"), currency="USDC", trust_envelope=_trust("100", "25")
        )
        assert d.allowed is False
        assert d.trust_remaining == Decimal("25")

    @pytest.mark.asyncio
    async def test_issuance_rejects_grant_exceeding_trust_ceiling(self, ticket_with_task):
        """Approving cannot widen the outer bound, at issuance time too."""
        with pytest.raises(NestingViolation):
            await issue_grant(
                ticket_id=TICKET_ID,
                granted_amount=Decimal("5000"),
                granted_currency="USDC",
                purpose="too much",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                granted_by_wa_id="wa-1",
                granted_by_user_id="alice",
                trust_ceiling=Decimal("1000"),
            )
        # and nothing was written
        assert GRANTED_BUDGET_METADATA_KEY not in (get_ticket(TICKET_ID)["metadata"] or {})


class TestSpendDecrementsBoth:
    @pytest.mark.asyncio
    async def test_spend_decrements_the_task_grant(self, ticket_with_task):
        await _grant(amount="50")

        assert record_spend(ticket_id=TICKET_ID, amount=Decimal("30"), currency="USDC", task_id=TASK_ID)

        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("25"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is False
        assert d.granted_remaining == Decimal("20")
        assert d.reason is BudgetDenialReason.TASK_BUDGET_EXHAUSTED

        ok = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("20"), currency="USDC", trust_envelope=_trust()
        )
        assert ok.allowed is True

    @pytest.mark.asyncio
    async def test_ledger_persists_records(self, ticket_with_task):
        await _grant(amount="50")
        record_spend(ticket_id=TICKET_ID, amount=Decimal("5"), currency="USDC", task_id=TASK_ID)
        record_spend(ticket_id=TICKET_ID, amount=Decimal("7"), currency="USDC", task_id=TASK_ID)

        ledger = load_spent_ledger(get_ticket(TICKET_ID))
        assert ledger.total_spent == Decimal("12")
        assert len(ledger.records) == 2

    @pytest.mark.asyncio
    async def test_grant_survives_spend_recording(self, ticket_with_task):
        """Recording a spend must not clobber the grant."""
        await _grant(amount="50")
        record_spend(ticket_id=TICKET_ID, amount=Decimal("5"), currency="USDC")
        grant, reason = load_grant(get_ticket(TICKET_ID))
        assert grant is not None and reason is None
        assert grant.granted_amount == Decimal("50")

    @pytest.mark.asyncio
    async def test_corrupt_ledger_reads_as_exhausted(self, ticket_with_task):
        """Resetting the ledger by corrupting it must not refill the budget."""
        from ciris_engine.logic.persistence.models.tickets import update_ticket_metadata

        await _grant(amount="50")
        metadata = get_ticket(TICKET_ID)["metadata"]
        metadata[BUDGET_SPENT_METADATA_KEY] = "wiped"
        update_ticket_metadata(TICKET_ID, metadata)

        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("1"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is False
        assert d.granted_remaining == Decimal("0")


class TestOverRequestGrants:
    """An AUTHORITY user may grant ABOVE the agent's request.

    User ruling: "yes an AUTHORITY can approve above what the agent requested,
    of course, the agent may have requested too little."

    So `granted <= requested` is NOT a bound anywhere. It is only *recorded*, so
    an over-request grant is distinguishable in audit from an ordinary one.
    """

    @staticmethod
    def _set_requested(amount: str) -> None:
        from ciris_engine.logic.persistence.models.tickets import update_ticket_metadata

        from ciris_engine.schemas.services.budget_envelope import REQUESTED_BUDGET_METADATA_KEY, RequestedBudget

        requested = RequestedBudget(
            requested_amount=Decimal(amount), requested_currency="USDC", purpose="fee"
        )
        metadata = get_ticket(TICKET_ID)["metadata"] or {}
        metadata[REQUESTED_BUDGET_METADATA_KEY] = requested.model_dump(mode="json")
        update_ticket_metadata(TICKET_ID, metadata)

    @pytest.mark.asyncio
    async def test_granting_above_the_request_is_allowed(self, ticket_with_task):
        self._set_requested("25")
        grant = await _grant(amount="250")
        assert grant.granted_amount == Decimal("250")

        # ...and it actually spends, up to the granted amount.
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("200"), currency="USDC", trust_envelope=_trust("1000", "1000")
        )
        assert d.allowed is True

    @pytest.mark.asyncio
    async def test_over_request_grant_is_marked(self, ticket_with_task):
        self._set_requested("25")
        grant = await _grant(amount="250")
        assert grant.exceeds_request is True
        assert grant.requested_amount_at_grant == Decimal("25")

    @pytest.mark.asyncio
    async def test_at_or_below_request_is_not_marked(self, ticket_with_task):
        self._set_requested("25")
        at = await _grant(amount="25")
        assert at.exceeds_request is False
        assert at.requested_amount_at_grant == Decimal("25")

        below = await _grant(amount="10")
        assert below.exceeds_request is False

    @pytest.mark.asyncio
    async def test_ticket_with_no_requested_budget_is_grantable(self, ticket_with_task):
        """A human-opened ticket requests nothing. It must still be grantable."""
        assert REQUESTED_BUDGET_METADATA_KEY not in (get_ticket(TICKET_ID)["metadata"] or {})

        grant = await _grant(amount="500")
        assert grant.granted_amount == Decimal("500")
        assert grant.requested_amount_at_grant is None
        # No request to exceed => not an over-request grant.
        assert grant.exceeds_request is False

        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("10"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is True

    @pytest.mark.asyncio
    async def test_marking_is_covered_by_the_signature(self, ticket_with_task):
        """The over-request marker cannot be stripped without breaking the signature."""
        self._set_requested("25")
        grant = await _grant(amount="250")
        laundered = grant.model_copy(update={"exceeds_request": False, "requested_amount_at_grant": None})
        assert canonical_grant_payload(grant) != canonical_grant_payload(laundered)

    @pytest.mark.asyncio
    async def test_over_request_grant_is_still_bounded_by_trust_headroom(self, ticket_with_task):
        """The ruling relaxed nothing about the real bound."""
        self._set_requested("25")
        await _grant(amount="10000")

        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("200"), currency="USDC", trust_envelope=_trust("100", "1000")
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.TRUST_ENVELOPE_EXCEEDED
        assert d.binding_constraint == "trust_envelope"

    @pytest.mark.asyncio
    async def test_issuance_still_refuses_to_exceed_the_trust_ceiling(self, ticket_with_task):
        """Over-request is fine; over-*ceiling* is not, request or no request."""
        self._set_requested("25")
        with pytest.raises(NestingViolation):
            await issue_grant(
                ticket_id=TICKET_ID,
                granted_amount=Decimal("5000"),
                granted_currency="USDC",
                purpose="too much",
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
                granted_by_wa_id="wa-1",
                granted_by_user_id="alice",
                trust_ceiling=Decimal("1000"),
            )

    def test_request_body_cannot_assert_the_marking(self):
        """A caller cannot supply the audit marking at all — the body is rejected.

        Stronger than ignoring it: `extra="forbid"` means an attempt to assert
        `exceeds_request` fails loudly instead of appearing to have been honoured.
        """
        from pydantic import ValidationError

        from ciris_engine.logic.adapters.api.routes.tickets import GrantBudgetRequest

        with pytest.raises(ValidationError):
            GrantBudgetRequest(
                amount=Decimal("250"), currency="USDC", purpose="fee", exceeds_request=False
            )
        with pytest.raises(ValidationError):
            GrantBudgetRequest(
                amount=Decimal("250"),
                currency="USDC",
                purpose="fee",
                requested_amount_at_grant=Decimal("9999"),
            )

    def test_unknown_request_field_is_rejected_not_defaulted(self):
        """A typo'd field must 422, not silently take a default.

        `expires_in_hourz` quietly taking the 24h default is the money-endpoint
        version of the silent-default bug this codebase keeps finding.
        """
        from pydantic import ValidationError

        from ciris_engine.logic.adapters.api.routes.tickets import GrantBudgetRequest

        with pytest.raises(ValidationError):
            GrantBudgetRequest(amount=Decimal("1"), currency="USDC", purpose="p", expires_in_hourz=1)

    @pytest.mark.asyncio
    async def test_marking_is_derived_from_the_ticket_not_the_caller(self, ticket_with_task):
        """The issuance path takes no marking parameters; it reads the ticket."""
        self._set_requested("25")
        grant = await issue_grant(
            ticket_id=TICKET_ID,
            granted_amount=Decimal("250"),
            granted_currency="USDC",
            purpose="fee",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            granted_by_wa_id="wa-1",
            granted_by_user_id="mallory",
        )
        assert grant.exceeds_request is True
        assert grant.requested_amount_at_grant == Decimal("25")

        import inspect

        params = set(inspect.signature(issue_grant).parameters)
        assert "exceeds_request" not in params
        assert "requested_amount_at_grant" not in params


class TestRegrantSemantics:
    """Re-granting raises the CEILING; it does not top up spent money.

    This is security-relevant, not cosmetic: if a second grant reset the ledger,
    a human "raising the budget" would silently refund everything already spent,
    and repeated re-grants would be an unbounded spend channel.
    """

    @pytest.mark.asyncio
    async def test_regrant_preserves_the_spend_ledger(self, ticket_with_task):
        await _grant(amount="25")
        record_spend(ticket_id=TICKET_ID, amount=Decimal("25"), currency="USDC")

        exhausted = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("1"), currency="USDC", trust_envelope=_trust()
        )
        assert exhausted.allowed is False

        # Human raises the ceiling 25 -> 40.
        await _grant(amount="40")

        ledger = load_spent_ledger(get_ticket(TICKET_ID))
        assert ledger.total_spent == Decimal("25"), "re-grant reset the ledger — spent money was refunded"

        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("15"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is True
        assert d.granted_remaining == Decimal("15")  # 40 granted - 25 spent

        over = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("16"), currency="USDC", trust_envelope=_trust()
        )
        assert over.allowed is False

    @pytest.mark.asyncio
    async def test_regrant_below_spent_revokes_rather_than_going_negative(self, ticket_with_task):
        """Lowering a grant below what is already spent is an effective revocation."""
        await _grant(amount="50")
        record_spend(ticket_id=TICKET_ID, amount=Decimal("40"), currency="USDC")

        await _grant(amount="10")

        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("1"), currency="USDC", trust_envelope=_trust()
        )
        assert d.granted_remaining == Decimal("0")
        assert d.allowed is False


class TestSignature:
    @pytest.mark.asyncio
    async def test_signature_binds_the_ticket_id(self, ticket_with_task):
        """The canonical payload includes ticket_id, so a grant cannot be replayed."""
        g1 = GrantedBudget(
            ticket_id="T-A",
            granted_amount=Decimal("10"),
            granted_currency="USDC",
            purpose="p",
            expires_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            granted_by_wa_id="wa",
            granted_by_user_id="u",
            granted_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
        g2 = g1.model_copy(update={"ticket_id": "T-B"})
        assert canonical_grant_payload(g1) != canonical_grant_payload(g2)

    @pytest.mark.asyncio
    async def test_invalid_signature_denies(self, ticket_with_task):
        """A grant carrying a signature that does not verify is rejected."""
        from ciris_engine.logic.persistence.models.tickets import update_ticket_metadata

        grant = GrantedBudget(
            ticket_id=TICKET_ID,
            granted_amount=Decimal("500"),
            granted_currency="USDC",
            purpose="forged",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            granted_by_wa_id="wa-1",
            granted_by_user_id="mallory",
            granted_at=datetime.now(timezone.utc),
            signature="bm90LWEtcmVhbC1zaWduYXR1cmU=",
        )
        update_ticket_metadata(TICKET_ID, {GRANTED_BUDGET_METADATA_KEY: grant.model_dump(mode="json")})

        auth = Mock()
        auth.get_wa = AsyncMock(return_value=Mock(pubkey="AAAA"))
        auth._verify_signature = Mock(return_value=False)

        d = await authorize_spend(
            task_id=TASK_ID,
            amount=Decimal("1"),
            currency="USDC",
            trust_envelope=_trust(),
            auth_service=auth,
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.GRANT_SIGNATURE_INVALID

    @pytest.mark.asyncio
    async def test_signed_grant_with_no_verifier_denies(self, ticket_with_task):
        """A signature we cannot check fails closed."""
        from ciris_engine.logic.persistence.models.tickets import update_ticket_metadata

        grant = GrantedBudget(
            ticket_id=TICKET_ID,
            granted_amount=Decimal("500"),
            granted_currency="USDC",
            purpose="p",
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            granted_by_wa_id="wa-1",
            granted_by_user_id="u",
            granted_at=datetime.now(timezone.utc),
            signature="c29tZXRoaW5n",
        )
        update_ticket_metadata(TICKET_ID, {GRANTED_BUDGET_METADATA_KEY: grant.model_dump(mode="json")})
        d = await authorize_spend(
            task_id=TASK_ID,
            amount=Decimal("1"),
            currency="USDC",
            trust_envelope=_trust(),
            auth_service=None,
        )
        assert d.allowed is False
        assert d.reason is BudgetDenialReason.GRANT_SIGNATURE_INVALID


class TestSelfApprovalImpossible:
    """The agent cannot satisfy the approval step from inside the reasoning loop."""

    @pytest.mark.asyncio
    async def test_no_tool_can_write_a_grant(self, ticket_with_task, temp_db_path):
        """Every agent-reachable ticket write path refuses the grant key."""
        from unittest.mock import AsyncMock as _AsyncMock

        from ciris_engine.logic.secrets.service import SecretsService
        from ciris_engine.logic.services.tools.core_tool_service.service import CoreToolService

        secrets = Mock(spec=SecretsService)
        secrets.retrieve_secret = _AsyncMock()
        time_service = Mock()
        time_service.now.return_value = datetime.now(timezone.utc)
        service = CoreToolService(secrets_service=secrets, time_service=time_service, db_path=temp_db_path)
        await service.start()

        forged = {
            "ticket_id": TICKET_ID,
            "granted_amount": "1000000",
            "granted_currency": "USDC",
            "purpose": "self-approved",
            "expires_at": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            "granted_by_wa_id": "wa-1",
            "granted_by_user_id": "the-agent",
            "granted_at": datetime.now(timezone.utc).isoformat(),
        }

        # Every tool this service exposes, given a grant-shaped payload.
        for tool_name in await service.get_available_tools():
            await service.execute_tool(
                tool_name,
                {
                    "ticket_id": TICKET_ID,
                    "goal_description": "self approve",
                    "metadata": {GRANTED_BUDGET_METADATA_KEY: forged},
                    "reason": "x",
                    "await_human": True,
                    "secret_uuid": "x",
                    "purpose": "x",
                    "operation": "list_patterns",
                },
            )

        # No tool produced a usable grant on the ticket.
        grant, reason = load_grant(get_ticket(TICKET_ID))
        assert grant is None, "a tool wrote a budget grant — self-approval is possible"
        assert reason is BudgetDenialReason.NO_GRANTED_BUDGET

        # And spend is still denied.
        d = await authorize_spend(
            task_id=TASK_ID, amount=Decimal("1"), currency="USDC", trust_envelope=_trust()
        )
        assert d.allowed is False

    def test_issuance_route_requires_authority(self):
        """The only grant-issuing route is gated on AUTHORITY, not ADMIN."""
        import inspect

        from ciris_engine.logic.adapters.api.routes import tickets as tickets_routes

        source = inspect.getsource(tickets_routes.grant_ticket_budget)
        assert "require_authority" in source

        from ciris_engine.schemas.api.auth import UserRole

        assert UserRole.ADMIN.has_permission(UserRole.AUTHORITY) is False
        assert UserRole.AUTHORITY.has_permission(UserRole.AUTHORITY) is True
        assert UserRole.SYSTEM_ADMIN.has_permission(UserRole.AUTHORITY) is True

    def test_ticket_not_found_detail_is_disambiguable(self):
        """A missing ticket must be distinguishable from a missing endpoint.

        The HITL client cannot otherwise tell "no such ticket" from "this server
        predates the budget feature", which need different UI.
        """
        from ciris_engine.logic.adapters.api.routes.tickets import (
            TICKET_NOT_FOUND_ERROR_CODE,
            _ticket_not_found_detail,
        )

        detail = _ticket_not_found_detail("PROP-MISSING")
        # Structured code is the robust discriminator.
        assert detail["error_code"] == TICKET_NOT_FOUND_ERROR_CODE == "TICKET_NOT_FOUND"
        # ...and the prose contains lowercase "ticket" for substring matchers.
        assert "ticket" in detail["message"]
        assert "PROP-MISSING" in detail["message"]

    def test_issue_grant_is_not_reachable_from_any_tool(self):
        """No tool service imports the issuance function."""
        import pathlib

        repo = pathlib.Path(__file__).resolve().parents[6]
        offenders = []
        for path in list((repo / "ciris_engine" / "logic" / "services" / "tools").rglob("*.py")) + list(
            (repo / "ciris_adapters").rglob("*.py")
        ):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "issue_grant" in text:
                offenders.append(str(path))
        assert offenders == [], f"issue_grant reachable from tool/adapter code: {offenders}"
