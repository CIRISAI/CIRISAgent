"""Reviewed-action admission and the dispatch gate's vocabulary (CIRISAgent#1366 items 10 + 19, rc21 §4).

One module holds every name the constitution's rc21 wire fixes or will fix:
the call/review schemes, the faculty set a draft must pass, the review
record's members, the dispatch tokens, and the enumeration of the callers the
system runs WITHOUT a review. Call sites import the names; a wire revision
touches this file only.

rc21 §4 (action scope):

* **Fingerprint** ``[-16, digest]``: ``SHA-256(CDE(["CEG-call/2", verb, tool,
  arguments, channel]))`` — ``reviewed_action.ceg_call_fingerprint``. Text form
  here: ``"-16:<hex>"`` (:data:`FINGERPRINT_PREFIX`).
* **Review record** (node-local, carried in the trace): ``fingerprint``,
  ``thought``, ``outcome`` (passed | objected), ``faculties``, ``discharges``
  (passed only), plus ``considered`` (passed only: the thought's earlier
  objection digests, constitution answer 2026-11-18). Record digest:
  ``SHA-256(CDE(["CEG-review/2", record]))``.
* **Dispatch tokens**: ``action_not_reviewed``, ``action_review_incomplete``,
  ``action_objection_undischarged``, ``action_approval_mismatch``,
  ``effect_untrusted_unacknowledged``.

Dependency-light on purpose (no ``task_envelope`` import): the subject schema
imports :class:`ReviewedCall` from here.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, FrozenSet, List, Mapping, Optional, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.veto_record import ObjectionType

#: rc21 §4 schemes.
CEG_CALL_SCHEME = "CEG-call/2"
CEG_REVIEW_SCHEME = "CEG-review/2"
#: The hash algorithm id in ``[-16, digest]`` (SHA-256).
SHA256_ALG_ID = -16
#: Text rendering of ``[-16, digest]`` used inside the agent: ``"-16:<hex>"``.
FINGERPRINT_PREFIX = f"{SHA256_ALG_ID}:"

#: The four faculties a draft must pass, all four, on that exact fingerprint.
#: A faculty that did not run (circuit open, transport failure, benchmark mode
#: with none registered) is NOT a pass: fail closed.
REQUIRED_REVIEW_FACULTIES: FrozenSet[str] = frozenset(
    {"coherence", "entropy", "epistemic_humility", "optimization_veto"}
)
#: Back-compat name.
REQUIRED_REVIEW_CONSCIENCES = REQUIRED_REVIEW_FACULTIES

#: One legal tool argument value (``ToolParams.parameters``).
ToolArgumentValue = Union[str, int, float, bool, List[str], Dict[str, str]]


class ReviewOutcome(str, Enum):
    PASSED = "passed"
    OBJECTED = "objected"


class ReviewDischarge(BaseModel):
    """``[objection, evidence]``: an objection record's digest and the trusted row that discharges it."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    objection: str = Field(..., description="Digest of the objected review record (-16:<hex>)")
    evidence: str = Field(..., description="Row id of the trusted row (a person seated over the agent)")


class ReviewRecord(BaseModel):
    """The rc21 §4 review record. Exactly the wire members; its digest is over these only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fingerprint: str = Field(..., description="The call reviewed, -16:<hex>")
    thought: str = Field(..., description="The thought the call belongs to")
    outcome: ReviewOutcome
    faculties: Tuple[str, ...] = Field(..., description="passed: all four; objected: those that objected")
    discharges: Tuple[ReviewDischarge, ...] = Field(default=(), description="passed only")
    considered: Tuple[str, ...] = Field(default=(), description="passed only: earlier objection digests of the thought")

    @property
    def missing_faculties(self) -> FrozenSet[str]:
        return REQUIRED_REVIEW_FACULTIES - frozenset(self.faculties)


class ReviewEntry(BaseModel):
    """A review record as this node holds it: the wire record plus node-local facts.

    ``digest`` is computed by ``reviewed_action.review_record_digest``. The rest
    is NOT in the wire record: the task the thought belongs to (dispatch binds
    it), the objection kinds an objected record carries (the discharge rule
    needs them), and ``derived_from`` — the action record's declaration of the
    untrusted input its arguments derive from (constitution answer 2026-11-18:
    a passed record whose action declares its derivation IS the citing record).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    record: ReviewRecord
    digest: str = Field(..., description="SHA-256(CDE([CEG-review/2, record])), -16:<hex>")
    task_id: str = Field(..., description="The task the thought belongs to")
    objection_types: Tuple[ObjectionType, ...] = Field(default=(), description="objected only")
    derived_from: Tuple[str, ...] = Field(
        default=(), description="passed only: digests/ids of the untrusted segments the arguments derive from"
    )


#: Back-compat alias for the record the admission seam takes.
ReviewedActionRecord = ReviewEntry


class ReviewedCall(BaseModel):
    """The call as the consciences reviewed it, carried to the gate by ``ToolHandler``.

    Arguments are the REVIEWED ones: secret references, never decapsulated
    values. The gate recomputes the fingerprint from these and the tool name
    the bus is actually dispatching.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    fingerprint: str = Field(..., description="The stamp the thought processor set (reviewed_action_hash)")
    tool_name: str = Field(..., description="Resolved tool name as reviewed")
    arguments: Dict[str, ToolArgumentValue] = Field(default_factory=dict, description="Arguments as reviewed")
    channel_id: Optional[str] = Field(None, description="Target channel as reviewed")


class GateRefusalReason(str, Enum):
    """Why the dispatch gate refused.

    The ``action_*`` / ``effect_*`` values are rc21 §4's dispatch tokens. The
    ``ciris.tool_gate.*`` ids are the envelope gate's (TaskEnvelope Phase 2),
    which the wire does not name.
    """

    # rc21 §4 dispatch tokens
    NOT_REVIEWED = "action_not_reviewed"  # also: a changed call
    REVIEW_INCOMPLETE = "action_review_incomplete"
    OBJECTION_UNDISCHARGED = "action_objection_undischarged"
    APPROVAL_MISMATCH = "action_approval_mismatch"
    EFFECT_UNTRUSTED_UNACKNOWLEDGED = "effect_untrusted_unacknowledged"
    # envelope gate
    NO_SUBJECT = "ciris.tool_gate.no_subject"
    NO_ENVELOPE = "ciris.tool_gate.no_envelope"
    TOOL_NOT_GRANTED = "ciris.tool_gate.tool_not_granted"
    SYSTEM_CALLER_UNDECLARED = "ciris.tool_gate.system_caller_undeclared"
    NOT_ENRICHMENT_TOOL = "ciris.tool_gate.not_enrichment_tool"
    ADAPTER_PATH_WRITE = "ciris.tool_gate.adapter_path_write"
    UNGATED_PROVIDER_CALL = "ciris.tool_gate.ungated_provider_call"


class GateRefusal(BaseModel):
    """A typed refusal from the dispatch gate."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    reason: GateRefusalReason = Field(..., description="Refusal reason id / dispatch token")
    tool_name: str = Field(..., description="The tool that was refused")
    detail: str = Field("", description="Log-safe explanation")
    subject: str = Field("none", description="ToolInvocationSubject.describe(), or 'none'")

    def message(self) -> str:
        """The error string a refused ToolExecutionResult carries."""
        return f"{self.reason.value}: {self.detail}" if self.detail else self.reason.value


class ToolPrincipalRestriction(BaseModel):
    """A deterministic authorization fact: only these principals may cause this tool.

    An action on such a tool claims to act for one of them; without the trusted
    row (the requester's VERIFIED id among the authorized ones) the effect is
    ``effect_untrusted_unacknowledged``. Keyed on
    ``TaskEnvelope.requester.user_id`` (the adapter's verified sender), never on
    a display name.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    tool_name: str = Field(..., description="The restricted tool")
    authorized_user_ids: FrozenSet[str] = Field(..., description="Principals that may cause it")
    source_id: str = Field(..., description="The trusted row this fact comes from (amendment node / attestation id)")


class SystemCaller(BaseModel):
    """A code-declared caller that runs tools WITHOUT a conscience review, by design."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    origin: str = Field(..., description="ToolCallOrigin value this caller must arrive with")
    tools: Optional[FrozenSet[str]] = Field(
        ...,
        description=(
            "Literal tools it may call. None ONLY for the enrichment cache, whose tools are "
            "every provider tool declaring context_enrichment=True (verified at dispatch)."
        ),
    )
    why: str = Field(..., description="Why this call has no review")


#: Component names (``ToolInvocationSubject.component``).
DSAR_COMPONENT = "DSARModificationOrchestrator"
CONNECTOR_SETUP_COMPONENT = "api.routes.connectors"
ENRICHMENT_CACHE_COMPONENT = "context_enrichment_cache"

#: Every caller the system runs without a conscience review. Anything not here
#: arriving without a task is refused (SYSTEM_CALLER_UNDECLARED). Task-bound
#: context enrichment is the one task-scoped unreviewed call; it is a rule in
#: the gate (origin CONTEXT_ENRICHMENT + provider declares context_enrichment).
SYSTEM_CALLERS: Mapping[str, SystemCaller] = {
    DSAR_COMPONENT: SystemCaller(
        origin="governance_service",
        tools=frozenset({"sql_anonymize_user", "sql_export_user", "sql_delete_user", "sql_verify_deletion"}),
        why="statutory DSAR obligation, driven by an authenticated request, never by the model",
    ),
    CONNECTOR_SETUP_COMPONENT: SystemCaller(
        origin="adapter_lifecycle",
        tools=frozenset({"initialize_sql_connector", "sql_query"}),
        why="operator connector setup/test through the authenticated API",
    ),
    ENRICHMENT_CACHE_COMPONENT: SystemCaller(
        origin="system_enrichment",
        tools=None,
        why="read-only context enrichment run outside any task (startup, adapter load, operator refresh)",
    ),
}

#: Deferral-context key carrying the call a Wise Authority is asked to approve:
#: JSON text ``{tool, arguments, channel, call_fingerprint}`` (agreed with the client).
PROPOSED_CALL_KEY = "proposed_call"


__all__ = [
    "CEG_CALL_SCHEME",
    "CEG_REVIEW_SCHEME",
    "CONNECTOR_SETUP_COMPONENT",
    "DSAR_COMPONENT",
    "ENRICHMENT_CACHE_COMPONENT",
    "FINGERPRINT_PREFIX",
    "GateRefusal",
    "GateRefusalReason",
    "PROPOSED_CALL_KEY",
    "REQUIRED_REVIEW_CONSCIENCES",
    "REQUIRED_REVIEW_FACULTIES",
    "ReviewDischarge",
    "ReviewEntry",
    "ReviewOutcome",
    "ReviewRecord",
    "ReviewedActionRecord",
    "ReviewedCall",
    "SHA256_ALG_ID",
    "SYSTEM_CALLERS",
    "SystemCaller",
    "ToolArgumentValue",
    "ToolPrincipalRestriction",
]
