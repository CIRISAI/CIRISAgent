"""Budget envelope schemas — the propose/approve/spend model for agent spend.

See ``FSD/BUDGET_ENVELOPE.md`` for the full design.

Three objects, deliberately kept structurally incompatible with each other:

- :class:`TicketProposal` — provenance for a ticket the agent opened via the
  ``create_ticket`` tool. Records which thought/task proposed it.
- :class:`RequestedBudget` — what the agent *asked for*. Agent-authored,
  carries no authority whatsoever. Requesting is not granting.
- :class:`GrantedBudget` — what a human/WA *authorized*. Issued only by the
  AUTHORITY-gated grant route, never by any tool.

``RequestedBudget`` and ``GrantedBudget`` use **disjoint field names** for the
amount and currency, and both set ``extra="forbid"``. That makes them
structurally unassignable to one another: ``GrantedBudget(**requested.model_dump())``
raises ``ValidationError`` on both counts (unknown ``requested_amount``, missing
``granted_amount``). A requested budget therefore cannot be laundered into a
granted one by any dict round-trip, which is the exact confusion this design
must never permit.

All three live under reserved keys in the ticket's ``metadata`` blob. Those keys
are refused by every agent-reachable write path — see
``RESERVED_TICKET_METADATA_KEYS``.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Reserved ticket-metadata keys
# ---------------------------------------------------------------------------

#: Provenance of an agent-proposed ticket (written by ``create_ticket``).
PROPOSAL_METADATA_KEY = "__proposal__"

#: What the agent asked for (written by ``create_ticket``, never re-writable).
REQUESTED_BUDGET_METADATA_KEY = "__requested_budget__"

#: What a human/WA authorized (written ONLY by the AUTHORITY grant route).
GRANTED_BUDGET_METADATA_KEY = "__granted_budget__"

#: Running total spent against the grant (written by the spend enforcement path).
BUDGET_SPENT_METADATA_KEY = "__budget_spent__"

#: Every metadata key that the reasoning loop must never be able to write.
#:
#: ``create_ticket`` populates ``__proposal__`` and ``__requested_budget__``
#: itself from validated tool arguments; it does not copy them out of
#: agent-supplied metadata. ``update_ticket`` refuses all four outright. This
#: frozenset is the single source of truth for that refusal.
RESERVED_TICKET_METADATA_KEYS = frozenset(
    {
        PROPOSAL_METADATA_KEY,
        REQUESTED_BUDGET_METADATA_KEY,
        GRANTED_BUDGET_METADATA_KEY,
        BUDGET_SPENT_METADATA_KEY,
    }
)

#: Ticket status for a proposal.
#:
#: The ticket status vocabulary is a **closed enum in the persist substrate**
#: (``pending``, ``assigned``, ``in_progress``, ``blocked``, ``deferred``,
#: ``completed``, ``cancelled``, ``failed``) — ``ticket_upsert`` rejects anything
#: else with ``unknown variant``. A dedicated ``proposed`` variant would require
#: a CIRISPersist change, so a proposal rides the existing ``blocked``, which is
#: exactly what it is: blocked on a human decision it cannot make itself.
#:
#: Crucially ``blocked`` is NOT one of the statuses WorkProcessor discovers
#: (``_process_pending_tickets`` lists ``pending``; ``_process_active_tickets``
#: lists ``assigned``/``in_progress``) and it is already in
#: ``_should_skip_ticket_by_status``. So a proposal never becomes an executing
#: task on its own.
#:
#: A proposal is distinguished from an ordinary blocked ticket by the presence
#: of :data:`PROPOSAL_METADATA_KEY`, which no agent-reachable path can write.
PROPOSAL_TICKET_STATUS = "blocked"

#: Backwards-compatible alias.
PROPOSED_TICKET_STATUS = PROPOSAL_TICKET_STATUS

#: The ticket statuses that WorkProcessor turns into Tasks. Kept here so the
#: "a proposal is not executing" invariant is assertable from one place.
EXECUTING_TICKET_STATUSES = frozenset({"pending", "assigned", "in_progress"})


def is_unapproved_proposal(ticket: object) -> bool:
    """True when a ticket is an agent proposal that no human has acted on yet.

    Requires both the agent-unwritable proposal marker and the blocked status.
    Once a human promotes the ticket the status changes and normal agent
    updates apply again.
    """
    if not isinstance(ticket, dict):
        return False
    if ticket.get("status") != PROPOSAL_TICKET_STATUS:
        return False
    metadata = ticket.get("metadata") or {}
    return isinstance(metadata, dict) and PROPOSAL_METADATA_KEY in metadata


# ---------------------------------------------------------------------------
# Proposal provenance
# ---------------------------------------------------------------------------


class TicketProposal(BaseModel):
    """Provenance for a ticket opened by the agent's reasoning loop.

    Written by the ``create_ticket`` tool from handler-supplied context, not
    from model-authored parameters.
    """

    origin_task_id: Optional[str] = Field(
        None, description="Task whose reasoning produced this proposal (handler-injected)"
    )
    origin_thought_id: Optional[str] = Field(None, description="Thought that produced this proposal, if known")
    proposed_at: datetime = Field(..., description="When the agent opened the proposal")
    proposed_by: str = Field("agent", description="Origin class of the proposal — always 'agent' for tool-created")
    goal_description: str = Field(..., description="What the agent says this work is for")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ---------------------------------------------------------------------------
# Requested (agent-authored — carries no authority)
# ---------------------------------------------------------------------------


class RequestedBudget(BaseModel):
    """A spend budget the agent has *asked* for. Never an authorization.

    Field names are deliberately disjoint from :class:`GrantedBudget` so the two
    cannot be interconverted by ``model_dump()`` round-trips.
    """

    requested_amount: Decimal = Field(..., gt=0, description="Amount the agent is asking to be allowed to spend")
    requested_currency: str = Field(..., min_length=2, max_length=8, description="Currency code, e.g. USDC")
    purpose: str = Field(..., min_length=1, description="What the agent intends to spend it on")
    justification: Optional[str] = Field(None, description="Why the agent believes this spend is warranted")

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ---------------------------------------------------------------------------
# Granted (human/WA-authored — the issuance event)
# ---------------------------------------------------------------------------


class GrantedBudget(BaseModel):
    """A spend budget a human/WA has *authorized* for one ticket.

    Issued only by the AUTHORITY-gated grant route. No tool writes this, and
    ``update_ticket`` refuses the metadata key it lives under.

    ``signature`` covers the canonical form of every other field (see
    ``budget_envelope.canonical_grant_payload``) and binds the grant to
    ``ticket_id``, so a grant cannot be replayed onto a different ticket.
    """

    ticket_id: str = Field(..., description="Ticket this grant is bound to — replay onto another ticket fails")
    granted_amount: Decimal = Field(..., gt=0, description="Maximum total spend authorized against this ticket")
    granted_currency: str = Field(..., min_length=2, max_length=8, description="Currency code, e.g. USDC")
    purpose: str = Field(..., min_length=1, description="What this grant authorizes spend for")
    expires_at: datetime = Field(..., description="Grant expiry — a spend after this is denied")
    granted_by_wa_id: str = Field(..., description="WA identity that issued the grant")
    granted_by_user_id: str = Field(..., description="API user (AUTHORITY role) that performed the issuance")
    granted_at: datetime = Field(..., description="Issuance timestamp")
    signature: Optional[str] = Field(
        None,
        description=(
            "Ed25519 signature over the canonical grant payload. Verified on every "
            "spend when a verifying key is resolvable."
        ),
    )

    model_config = ConfigDict(extra="forbid", defer_build=True)


# ---------------------------------------------------------------------------
# Spend accounting + decision
# ---------------------------------------------------------------------------


class BudgetSpendRecord(BaseModel):
    """One authorized spend charged against a grant."""

    amount: Decimal = Field(..., gt=0, description="Amount spent")
    currency: str = Field(..., description="Currency code")
    spent_at: datetime = Field(..., description="When the spend was authorized")
    task_id: Optional[str] = Field(None, description="Task that spent it")
    correlation_id: Optional[str] = Field(None, description="Tool-execution correlation id")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class BudgetSpentLedger(BaseModel):
    """Running total of spend charged against a ticket's grant."""

    total_spent: Decimal = Field(Decimal("0"), ge=0, description="Sum of all authorized spends")
    currency: Optional[str] = Field(None, description="Currency of the ledger (matches the grant)")
    records: List[BudgetSpendRecord] = Field(default_factory=list, description="Individual spends")

    model_config = ConfigDict(extra="forbid", defer_build=True)


class BudgetDenialReason(str, Enum):
    """Why a spend was denied. Named so the failure says which bound bit."""

    NO_TASK_CONTEXT = "no_task_context"
    NO_TICKET_FOR_TASK = "no_ticket_for_task"
    NO_GRANTED_BUDGET = "no_granted_budget"
    GRANT_MALFORMED = "grant_malformed"
    GRANT_SIGNATURE_INVALID = "grant_signature_invalid"
    GRANT_TICKET_MISMATCH = "grant_ticket_mismatch"
    GRANT_EXPIRED = "grant_expired"
    CURRENCY_MISMATCH = "currency_mismatch"
    TASK_BUDGET_EXHAUSTED = "task_budget_exhausted"
    TRUST_ENVELOPE_EXCEEDED = "trust_envelope_exceeded"


class BudgetSpendDecision(BaseModel):
    """The result of authorizing a spend against the nested envelopes.

    ``allowed=False`` is the default outcome for every path that cannot
    positively resolve a valid grant. Absence of a grant is a denial, never
    "unbounded".
    """

    allowed: bool = Field(..., description="Whether the spend is authorized")
    reason: Optional[BudgetDenialReason] = Field(None, description="Denial reason code (None when allowed)")
    message: str = Field(..., description="Human-readable explanation naming the binding constraint")
    ticket_id: Optional[str] = Field(None, description="Ticket whose grant was consulted")
    granted_remaining: Optional[Decimal] = Field(None, description="Remaining on the task's granted budget")
    trust_remaining: Optional[Decimal] = Field(None, description="Remaining on the deployment trust envelope")
    effective_limit: Optional[Decimal] = Field(
        None, description="min(granted_remaining, trust_remaining) — the bound actually applied"
    )
    binding_constraint: Optional[str] = Field(
        None, description="Which envelope bound the spend: 'task_grant' or 'trust_envelope'"
    )

    model_config = ConfigDict(extra="forbid", defer_build=True)


class TrustEnvelope(BaseModel):
    """The deployment-scoped (trust-driven) outer bound a grant nests inside.

    Resolved from wallet configuration and, when reachable, the live provider
    spending tracker. A granted budget may never exceed this.
    """

    max_transaction: Decimal = Field(..., gt=0, description="Per-transaction ceiling")
    daily_remaining: Decimal = Field(..., ge=0, description="Remaining daily allowance")
    currency: Optional[str] = Field(None, description="Currency the bound applies to, if currency-specific")

    @property
    def remaining(self) -> Decimal:
        """The tighter of the per-transaction and daily bounds."""
        return min(self.max_transaction, self.daily_remaining)

    model_config = ConfigDict(extra="forbid", defer_build=True)
