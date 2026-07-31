"""Budget envelope resolution and enforcement.

The nesting model, in one line::

    a spend is authorized iff  amount <= min(granted_remaining, trust_remaining)

where ``granted_remaining`` comes from a human-issued, WA-signed grant bound to
one ticket, and ``trust_remaining`` is the deployment-scoped wallet envelope
that already existed. Absence of a grant is a **denial** — never "unbounded".

Layering note (CEG §0.0): this module surfaces and enforces; it does not mint
authority. The issuance event lives in the AUTHORITY-gated API route, outside
the reasoning loop. No function here is reachable from a tool except
:func:`authorize_spend` and :func:`record_spend`, neither of which can widen a
grant.

See ``FSD/BUDGET_ENVELOPE.md``.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, Optional, Tuple

from ciris_engine.schemas.services.budget_envelope import (
    BUDGET_SPENT_METADATA_KEY,
    GRANTED_BUDGET_METADATA_KEY,
    BudgetDenialReason,
    BudgetSpendDecision,
    BudgetSpendRecord,
    BudgetSpentLedger,
    GrantedBudget,
    TrustEnvelope,
)

logger = logging.getLogger(__name__)

__all__ = [
    "canonical_grant_payload",
    "sign_grant",
    "verify_grant_signature",
    "resolve_ticket_id_for_task",
    "load_grant",
    "load_spent_ledger",
    "authorize_spend",
    "record_spend",
    "issue_grant",
    "NestingViolation",
]


class NestingViolation(ValueError):
    """Raised when an issuance would widen the outer (trust-driven) envelope."""


# ---------------------------------------------------------------------------
# Canonicalization + signing
# ---------------------------------------------------------------------------


def canonical_grant_payload(grant: GrantedBudget) -> bytes:
    """Canonical bytes a grant signature covers.

    Every field except ``signature`` is included, so the signature binds the
    amount, the currency, the expiry, the issuing identities **and the
    ``ticket_id``** — a grant lifted onto another ticket fails verification.

    Uses RFC 8785 (JCS) via the substrate canonicalizer when available, falling
    back to sorted-key compact JSON. The fallback is deterministic and
    ``ensure_ascii=False`` so it round-trips non-ASCII purposes identically.
    """
    payload: Dict[str, Any] = grant.model_dump(mode="json", exclude={"signature"})
    try:
        from ciris_verify import jcs_canonicalize  # substrate-provided canonicalizer

        canonical: bytes = jcs_canonicalize(json.dumps(payload, ensure_ascii=False))
        return canonical
    except Exception:  # pragma: no cover - exercised only without the substrate wheel
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


async def sign_grant(grant: GrantedBudget, auth_service: Any) -> Optional[str]:
    """Sign a grant with the issuing WA's key. Returns None if no key is available.

    A deployment with no signing key still gets a usable grant — the structural
    defense (no tool can write the reserved metadata key) does not depend on the
    signature. What the signature adds is detection of a grant written through
    some *other* path. See the FSD's "what this does NOT do".
    """
    if auth_service is None:
        return None
    try:
        # sign_as_wa is the existing arbitrary-data WA signing entry point
        # (authentication/service.py:1474) — CIRISVerify named key when
        # available, file-based System WA key otherwise.
        signature = await auth_service.sign_as_wa(grant.granted_by_wa_id, canonical_grant_payload(grant))
        return str(signature) if signature else None
    except Exception as e:
        logger.warning("Budget grant signing unavailable for WA %s: %s", grant.granted_by_wa_id, e)
        return None


async def verify_grant_signature(grant: GrantedBudget, auth_service: Any) -> bool:
    """Verify a grant's signature.

    Returns True when the signature is valid. Returns True when there is no
    signature **and** no verifying key is resolvable (an unsigned deployment),
    because in that configuration the structural defense is the whole defense
    and refusing every grant would simply disable the feature. Returns False
    whenever a signature is present and does not verify — a forged or tampered
    grant is always rejected.
    """
    if not grant.signature:
        return True
    if auth_service is None:
        # A signature exists but we cannot check it. Fail closed: something
        # wrote a signature, so a verifier is expected to be present.
        logger.warning("Grant for ticket %s carries a signature but no auth service to verify it", grant.ticket_id)
        return False
    try:
        wa = await auth_service.get_wa(grant.granted_by_wa_id)
        if not wa or not getattr(wa, "pubkey", None):
            logger.warning("Grant for ticket %s: issuing WA %s not resolvable", grant.ticket_id, grant.granted_by_wa_id)
            return False
        return bool(auth_service._verify_signature(canonical_grant_payload(grant), grant.signature, wa.pubkey))
    except Exception as e:
        logger.warning("Grant signature verification errored for ticket %s: %s", grant.ticket_id, e)
        return False


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def resolve_ticket_id_for_task(task_id: str) -> Optional[str]:
    """Resolve the ticket a task is processing, or None.

    Reads the raw persist row rather than a materialized :class:`Task`, because
    ``TaskContext`` is ``extra="forbid"`` and drops ``ticket_id`` during
    materialization (``persistence/models/tasks.py:128``). The ticket id lives
    in the stored context JSON that ``WorkProcessor._create_seed_task_for_ticket``
    wrote.
    """
    if not task_id:
        return None
    try:
        from ciris_engine.logic.persistence.models.graph import get_persist_engine

        engine = get_persist_engine()
        if engine is None:
            return None
        raw = engine.task_get(task_id)
        if raw is None:
            return None
        row = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(row, dict):
            return None
        ctx = row.get("context")
        if isinstance(ctx, str):
            try:
                ctx = json.loads(ctx)
            except json.JSONDecodeError:
                return None
        if not isinstance(ctx, dict):
            return None
        ticket_id = ctx.get("ticket_id")
        return str(ticket_id) if ticket_id else None
    except Exception as e:
        logger.warning("Failed to resolve ticket for task %s: %s", task_id, e)
        return None


def _coerce_decimal(value: Any) -> Optional[Decimal]:
    """Best-effort Decimal coercion for values that round-tripped through JSON."""
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def load_grant(ticket: Dict[str, Any]) -> Tuple[Optional[GrantedBudget], Optional[BudgetDenialReason]]:
    """Load and structurally validate the grant on a ticket.

    Returns ``(grant, None)`` on success or ``(None, reason)`` describing why no
    usable grant exists. A malformed grant is a denial, not an absence — an
    attacker who can write garbage into the reserved key must not be able to
    turn that into a permissive outcome.
    """
    metadata = ticket.get("metadata") or {}
    if not isinstance(metadata, dict):
        return None, BudgetDenialReason.NO_GRANTED_BUDGET
    raw = metadata.get(GRANTED_BUDGET_METADATA_KEY)
    if raw is None:
        return None, BudgetDenialReason.NO_GRANTED_BUDGET
    if not isinstance(raw, dict):
        return None, BudgetDenialReason.GRANT_MALFORMED
    try:
        return GrantedBudget.model_validate(raw), None
    except Exception as e:
        logger.warning("Malformed granted budget on ticket %s: %s", ticket.get("ticket_id"), e)
        return None, BudgetDenialReason.GRANT_MALFORMED


def load_spent_ledger(ticket: Dict[str, Any]) -> BudgetSpentLedger:
    """Load the spend ledger for a ticket. A malformed ledger reads as fully spent.

    Failing to a zero ledger would let an attacker reset the running total by
    corrupting it, so an unparseable ledger is treated as maximally consumed by
    the caller (which compares against the grant).
    """
    metadata = ticket.get("metadata") or {}
    if not isinstance(metadata, dict):
        return BudgetSpentLedger()
    raw = metadata.get(BUDGET_SPENT_METADATA_KEY)
    if raw is None:
        return BudgetSpentLedger()
    if not isinstance(raw, dict):
        logger.warning("Malformed spend ledger on ticket %s; treating as exhausted", ticket.get("ticket_id"))
        return BudgetSpentLedger(total_spent=Decimal("999999999"))
    try:
        return BudgetSpentLedger.model_validate(raw)
    except Exception as e:
        logger.warning("Unparseable spend ledger on ticket %s (%s); treating as exhausted", ticket.get("ticket_id"), e)
        return BudgetSpentLedger(total_spent=Decimal("999999999"))


# ---------------------------------------------------------------------------
# Authorization
# ---------------------------------------------------------------------------


def _deny(reason: BudgetDenialReason, message: str, ticket_id: Optional[str] = None) -> BudgetSpendDecision:
    return BudgetSpendDecision(allowed=False, reason=reason, message=message, ticket_id=ticket_id)


async def authorize_spend(
    *,
    task_id: Optional[str],
    amount: Decimal,
    currency: str,
    trust_envelope: TrustEnvelope,
    auth_service: Any = None,
    now: Optional[datetime] = None,
) -> BudgetSpendDecision:
    """Authorize a spend against the nested envelopes. Fails closed at every step.

    The nesting invariant is enforced *here*, at spend time: whatever amount a
    grant names, the spend can never exceed ``trust_envelope.remaining``. An
    over-large grant therefore cannot widen the outer bound even if one were
    somehow issued.
    """
    now = now or datetime.now(timezone.utc)

    if not task_id:
        return _deny(
            BudgetDenialReason.NO_TASK_CONTEXT,
            "Spend denied: no originating task. Spend requires a task carrying an approved budget envelope.",
        )

    ticket_id = resolve_ticket_id_for_task(task_id)
    if not ticket_id:
        return _deny(
            BudgetDenialReason.NO_TICKET_FOR_TASK,
            f"Spend denied: task {task_id} is not processing a ticket, so it carries no approved budget envelope.",
        )

    from ciris_engine.logic.persistence.models.tickets import get_ticket

    ticket = get_ticket(ticket_id)
    if not ticket:
        return _deny(
            BudgetDenialReason.NO_TICKET_FOR_TASK,
            f"Spend denied: ticket {ticket_id} not found.",
            ticket_id,
        )

    grant, reason = load_grant(ticket)
    if grant is None:
        assert reason is not None
        if reason is BudgetDenialReason.NO_GRANTED_BUDGET:
            message = (
                f"Spend denied: ticket {ticket_id} has no human-approved budget. "
                "A budget must be granted by a Wise Authority before any spend."
            )
        else:
            message = f"Spend denied: ticket {ticket_id} has a malformed budget grant."
        return _deny(reason, message, ticket_id)

    if grant.ticket_id != ticket_id:
        return _deny(
            BudgetDenialReason.GRANT_TICKET_MISMATCH,
            f"Spend denied: grant is bound to ticket {grant.ticket_id}, not {ticket_id}.",
            ticket_id,
        )

    if not await verify_grant_signature(grant, auth_service):
        return _deny(
            BudgetDenialReason.GRANT_SIGNATURE_INVALID,
            f"Spend denied: budget grant on ticket {ticket_id} failed signature verification.",
            ticket_id,
        )

    expires_at = grant.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at <= now:
        return _deny(
            BudgetDenialReason.GRANT_EXPIRED,
            f"Spend denied: budget grant on ticket {ticket_id} expired at {expires_at.isoformat()}.",
            ticket_id,
        )

    if grant.granted_currency.upper() != currency.upper():
        return _deny(
            BudgetDenialReason.CURRENCY_MISMATCH,
            (
                f"Spend denied: grant authorizes {grant.granted_currency} but the spend is in "
                f"{currency}. A grant does not carry across currencies."
            ),
            ticket_id,
        )

    ledger = load_spent_ledger(ticket)
    granted_remaining = grant.granted_amount - ledger.total_spent
    if granted_remaining < 0:
        granted_remaining = Decimal("0")

    trust_remaining = trust_envelope.remaining
    effective_limit = min(granted_remaining, trust_remaining)
    binding = "task_grant" if granted_remaining <= trust_remaining else "trust_envelope"

    if amount > effective_limit:
        if binding == "task_grant":
            reason_code = BudgetDenialReason.TASK_BUDGET_EXHAUSTED
            message = (
                f"Spend denied: {amount} {currency} exceeds the approved task budget remaining "
                f"({granted_remaining} {currency} of {grant.granted_amount} granted on ticket {ticket_id}). "
                f"Bound by: task grant."
            )
        else:
            reason_code = BudgetDenialReason.TRUST_ENVELOPE_EXCEEDED
            message = (
                f"Spend denied: {amount} {currency} exceeds the deployment trust envelope remaining "
                f"({trust_remaining} {currency}; per-transaction {trust_envelope.max_transaction}, "
                f"daily remaining {trust_envelope.daily_remaining}). Bound by: trust envelope."
            )
        return BudgetSpendDecision(
            allowed=False,
            reason=reason_code,
            message=message,
            ticket_id=ticket_id,
            granted_remaining=granted_remaining,
            trust_remaining=trust_remaining,
            effective_limit=effective_limit,
            binding_constraint=binding,
        )

    return BudgetSpendDecision(
        allowed=True,
        reason=None,
        message=(
            f"Spend of {amount} {currency} authorized against ticket {ticket_id} "
            f"(task grant remaining {granted_remaining}, trust envelope remaining {trust_remaining})."
        ),
        ticket_id=ticket_id,
        granted_remaining=granted_remaining,
        trust_remaining=trust_remaining,
        effective_limit=effective_limit,
        binding_constraint=binding,
    )


def record_spend(
    *,
    ticket_id: str,
    amount: Decimal,
    currency: str,
    task_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """Charge an authorized spend against the ticket's grant ledger.

    Decrements the *inner* envelope. The outer (trust-driven) envelope is
    decremented independently by the wallet's own ``SpendingTracker`` inside
    ``validate_send``; both are debited for every spend.
    """
    now = now or datetime.now(timezone.utc)
    from ciris_engine.logic.persistence.models.tickets import get_ticket, update_ticket_metadata

    ticket = get_ticket(ticket_id)
    if not ticket:
        logger.error("Cannot record spend: ticket %s not found", ticket_id)
        return False

    metadata = ticket.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    ledger = load_spent_ledger(ticket)
    ledger.total_spent = ledger.total_spent + amount
    ledger.currency = ledger.currency or currency.upper()
    ledger.records.append(
        BudgetSpendRecord(
            amount=amount,
            currency=currency.upper(),
            spent_at=now,
            task_id=task_id,
            correlation_id=correlation_id,
        )
    )

    metadata[BUDGET_SPENT_METADATA_KEY] = ledger.model_dump(mode="json")
    ok = update_ticket_metadata(ticket_id, metadata)
    if ok:
        logger.info(
            "[BUDGET] Recorded spend %s %s against ticket %s (total %s)",
            amount,
            currency,
            ticket_id,
            ledger.total_spent,
        )
    else:
        logger.error("[BUDGET] Failed to record spend %s %s against ticket %s", amount, currency, ticket_id)
    return ok


# ---------------------------------------------------------------------------
# Issuance (AUTHORITY-gated route only — never reachable from a tool)
# ---------------------------------------------------------------------------


async def issue_grant(
    *,
    ticket_id: str,
    granted_amount: Decimal,
    granted_currency: str,
    purpose: str,
    expires_at: datetime,
    granted_by_wa_id: str,
    granted_by_user_id: str,
    trust_ceiling: Optional[Decimal] = None,
    auth_service: Any = None,
    now: Optional[datetime] = None,
) -> GrantedBudget:
    """Issue a granted budget onto a ticket. The issuance event.

    Called only from the AUTHORITY-gated API route. Enforces the nesting
    invariant at issuance when a ``trust_ceiling`` is resolvable; the
    authoritative enforcement is still the ``min()`` in :func:`authorize_spend`,
    which binds regardless of what was issued.

    Raises:
        NestingViolation: if the grant would exceed the trust-driven envelope.
        ValueError: if the ticket does not exist.
    """
    now = now or datetime.now(timezone.utc)

    if trust_ceiling is not None and granted_amount > trust_ceiling:
        raise NestingViolation(
            f"Granted budget {granted_amount} {granted_currency} exceeds the trust-driven envelope "
            f"ceiling {trust_ceiling}. A grant nests inside the trust envelope; it cannot widen it."
        )

    from ciris_engine.logic.persistence.models.tickets import get_ticket, update_ticket_metadata

    ticket = get_ticket(ticket_id)
    if not ticket:
        raise ValueError(f"Ticket {ticket_id} not found")

    grant = GrantedBudget(
        ticket_id=ticket_id,
        granted_amount=granted_amount,
        granted_currency=granted_currency.upper(),
        purpose=purpose,
        expires_at=expires_at,
        granted_by_wa_id=granted_by_wa_id,
        granted_by_user_id=granted_by_user_id,
        granted_at=now,
        signature=None,
    )
    signature = await sign_grant(grant, auth_service)
    if signature:
        grant = grant.model_copy(update={"signature": signature})

    metadata = ticket.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}
    metadata[GRANTED_BUDGET_METADATA_KEY] = grant.model_dump(mode="json")

    if not update_ticket_metadata(ticket_id, metadata):
        raise ValueError(f"Failed to write budget grant to ticket {ticket_id}")

    logger.info(
        "[BUDGET] Grant issued on ticket %s: %s %s by WA %s (user %s), expires %s",
        ticket_id,
        granted_amount,
        granted_currency,
        granted_by_wa_id,
        granted_by_user_id,
        expires_at.isoformat(),
    )
    return grant
