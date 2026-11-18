"""Prompt context provenance: segments, AAA carriers, the policy table and the per-call manifest.

FSD/PROMPT_CONTEXT_PROVENANCE.md (CIRISAgent#1366 Phase 2). Every piece of text the agent sends to a model is
a typed :class:`PromptSegment`, described on five independent axes (FSD §4): its kind (what it is), and its
provenance, source, trust and lifecycle (where it came from and what it is worth). ``PromptAssembler``
(``ciris_engine.logic.prompt_assembly``) checks segments against ``context_policy.yaml`` and records what each
call contained in a :class:`PromptManifest`.

The enum values are the closed vocabulary of ``formal/h3ere_ctxflow/gen_contract_policy.py``; a test fails if
the two drift (tests/ciris_engine/logic/prompt_assembly/test_context_policy_drift.py).
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SegmentKind(str, Enum):
    """What the text is (FSD §4.1)."""

    STAGE_INSTRUCTION = "stage_instruction"
    SCHEMA_INSTRUCTION = "schema_instruction"
    ACCORD = "accord"
    IDENTITY_BASE = "identity_base"
    AMENDMENT = "amendment"
    RULE = "rule"
    WA_GUIDANCE = "wa_guidance"
    REQUEST = "request"
    HISTORY = "history"
    SENDER_IDENTITY = "sender_identity"
    DISPLAY_NAME = "display_name"
    ACTION_RECORD = "action_record"
    DRAFT = "draft"
    DMA_OUTPUT = "dma_output"
    CONSCIENCE_FEEDBACK = "conscience_feedback"
    TOOL_OUTPUT = "tool_output"
    PIPELINE_POSITION = "pipeline_position"


class RuleProvenance(str, Enum):
    """Where a rule came from (FSD §4.2). Only signed provenances are authoritative (FSD §15.1)."""

    USER_CHAT = "user_chat"
    WA_CHAT = "wa_chat"
    SIGNED_GUIDANCE = "signed_guidance"
    AMENDMENT = "amendment"


class SegmentSource(str, Enum):
    """Which component produced the bytes (FSD §4.3)."""

    USER_INPUT = "user_input"
    ADAPTER_METADATA = "adapter_metadata"
    AUTH_CONTEXT = "auth_context"
    SIGNED_ROW = "signed_row"
    AGENT_PROFILE = "agent_profile"
    ENGINE = "engine"
    LLM_OUTPUT = "llm_output"
    TOOL_OUTPUT = "tool_output"
    PROVIDER_LIB = "provider_lib"


class TrustLevel(str, Enum):
    """How far a segment can be trusted (FSD §4.4). Ordered untrusted < verified < system."""

    UNTRUSTED = "untrusted"
    VERIFIED = "verified"
    SYSTEM = "system"


TRUST_ORDER: Dict[TrustLevel, int] = {TrustLevel.UNTRUSTED: 0, TrustLevel.VERIFIED: 1, TrustLevel.SYSTEM: 2}


def min_trust(*levels: TrustLevel) -> TrustLevel:
    """The lowest of ``levels`` (the taint rule's ``min``)."""
    return min(levels, key=lambda level: TRUST_ORDER[level])


class Lifecycle(str, Enum):
    """How long a segment lives (FSD §4.6)."""

    STANDING = "standing"
    PER_TASK = "per-task"
    PER_MESSAGE = "per-message"
    PER_THOUGHT = "per-thought"
    RETRY_ONLY = "retry-only"
    PER_CALL = "per-call"


class PolicyPredicate(str, Enum):
    """The closed predicate set of context_policy.yaml (gen_contract_policy.PREDICATES)."""

    ALWAYS = "always"
    NEVER = "never"
    TRUSTED_RULE_IN_FORCE = "trusted_rule_in_force"
    ID_SCOPED = "id_scoped"
    SIGNED_GUIDANCE_IN_FORCE = "signed_guidance_in_force"
    AMENDMENT_IN_FORCE = "amendment_in_force"
    ADVISORY_RULE = "advisory_rule"
    RETRY = "retry"


class PromptStage(str, Enum):
    """One LLM call site in a thought (FSD §3). Names are the policy file's stage keys."""

    ASPDMA = "aspdma"
    TSASPDMA = "tsaspdma"
    DSASPDMA = "dsaspdma"
    FSASPDMA = "fsaspdma"
    MSASPDMA = "msaspdma"
    RSASPDMA = "rsaspdma"
    CSDMA = "csdma"
    DSDMA = "dsdma"
    PDMA = "pdma"
    IDMA = "idma"
    COHERENCE = "coherence"
    ENTROPY = "entropy"
    EPISTEMIC = "epistemic"
    OPTVETO = "optveto"


class StageRole(str, Enum):
    """The part a stage plays (FSD §3, §8)."""

    DRAFTER = "drafter"
    SECOND_PASS = "second_pass"
    EVALUATOR = "evaluator"
    JUDGE = "judge"


class ManifestThoughtKind(str, Enum):
    """The thought a call belongs to, as the manifest records it (FSD §8)."""

    SEED = "seed"
    FOLLOWUP = "followup"
    GUIDANCE = "guidance"


# --------------------------------------------------------------------------------------------------------------
# AAA carriers (FSD §4.5)
# --------------------------------------------------------------------------------------------------------------


class AuthnCarrier(BaseModel):
    """Authentication: the verified subject and what verified it. Required on ``sender_identity``."""

    subject_id: str = Field(..., min_length=1, description="The verified user id")
    role: str = Field(..., min_length=1, description="The verified role (e.g. OBSERVER, ADMIN, AUTHORITY)")
    verifier: str = Field(..., min_length=1, description="What established it: auth context, gateway token, signature")

    model_config = ConfigDict(extra="forbid", frozen=True)


class GrantKind(str, Enum):
    """The kind of grant an authz carrier names."""

    AMENDMENT = "amendment"
    DEFERRAL = "deferral"
    RESPONSE_ATTESTATION = "response_attestation"


class AuthzCarrier(BaseModel):
    """Authorization: the grant that makes a segment binding. Required on amendments, signed rules, WA guidance."""

    grant_kind: GrantKind = Field(..., description="What the grant id names")
    grant_id: str = Field(..., min_length=1, description="Amendment node id, deferral id or attestation id")
    authorizer_id: Optional[str] = Field(None, description="The Wise Authority that granted it")
    signature_verified: bool = Field(..., description="Whether the grant's signature verified")
    attestation_ids: List[str] = Field(default_factory=list, description="Request/response attestation ids")
    granted_at: Optional[str] = Field(None, description="ISO-8601 time of the grant")

    model_config = ConfigDict(extra="forbid", frozen=True)


class AcctCarrier(BaseModel):
    """Accounting: the record tying a segment to the audit trail (and veto ids for conscience feedback)."""

    audit_entry_id: Optional[str] = Field(None, description="Audit entry id")
    row_hash: Optional[str] = Field(None, description="Hash of the signed row the bytes came from")
    trace_id: Optional[str] = Field(None, description="Trace id")
    veto_id: Optional[str] = Field(None, description="Veto id, for conscience_feedback (FSD §9)")
    discharge_ids: List[str] = Field(default_factory=list, description="Discharge records (FSD §9)")

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------------------------------------------
# The segment
# --------------------------------------------------------------------------------------------------------------


class PromptSegment(BaseModel):
    """One contiguous piece of text a caller hands the assembler (FSD §3, §4).

    Trust and lifecycle are declared by the policy for the kind (and, for a rule, the provenance). A caller may
    state a LOWER trust (e.g. an action record it knows embeds user text); it can never raise one. ``lifecycle``,
    when stated, must match the policy's. ``sender_identity`` carries no text: it is rendered from ``authn``
    alone, so its bytes are system-built (FSD §6).
    """

    segment_id: str = Field(..., min_length=1, description="Unique within one call")
    kind: SegmentKind
    provenance: Optional[RuleProvenance] = Field(None, description="Required on rule, forbidden elsewhere")
    source: SegmentSource
    text: str = Field("", description="The segment's bytes (before the assembler's labelling)")
    trust: Optional[TrustLevel] = Field(None, description="Caller's own trust; can only lower the policy's")
    lifecycle: Optional[Lifecycle] = Field(None, description="If stated, must equal the policy's lifecycle")
    authn: Optional[AuthnCarrier] = None
    authz: Optional[AuthzCarrier] = None
    acct: Optional[AcctCarrier] = None
    derived_from: List[str] = Field(default_factory=list, description="Ids of segments whose bytes this contains")
    order_key: str = Field("", description="Orders segments of one kind (e.g. an amendment's granted_at)")
    truncated: bool = Field(False, description="The producer cut the text")
    origin_task_id: Optional[str] = Field(None, description="Task a per-task segment belongs to")
    origin_thought_id: Optional[str] = Field(None, description="Thought a per-thought segment belongs to")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @model_validator(mode="after")
    def _shape(self) -> "PromptSegment":
        if (self.kind == SegmentKind.RULE) != (self.provenance is not None):
            raise ValueError("provenance is required on a rule segment and only on a rule segment")
        if self.kind == SegmentKind.SENDER_IDENTITY and self.text:
            raise ValueError("sender_identity carries no text: it is rendered from authn")
        if self.segment_id in self.derived_from:
            raise ValueError("a segment cannot derive from itself")
        return self

    @property
    def policy_key(self) -> str:
        """The policy row key: ``kind`` or ``rule.<provenance>``."""
        if self.provenance is not None:
            return f"{self.kind.value}.{self.provenance.value}"
        return self.kind.value


# --------------------------------------------------------------------------------------------------------------
# The policy table (loaded from context_policy.yaml)
# --------------------------------------------------------------------------------------------------------------


class KindSpec(BaseModel):
    """Static properties of one kind (context_policy.yaml ``kinds``)."""

    trust: Optional[TrustLevel] = Field(None, description="None for rule: its trust comes from provenance")
    lifecycle: Lifecycle
    authn_required: bool = False
    authz_required: bool = False
    acct_required: bool = False
    render_labelled: bool = False
    residual: bool = Field(False, description="Accepted residual (FSD §10)")
    source: Optional[SegmentSource] = Field(None, description="The only source this kind may have, if fixed")

    model_config = ConfigDict(extra="forbid", frozen=True)


class PolicyRow(BaseModel):
    """stage × kind (× provenance) → predicate. Row order is the stage's rendering order."""

    kind: SegmentKind
    provenance: Optional[RuleProvenance] = None
    predicate: PolicyPredicate

    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def key(self) -> str:
        return f"{self.kind.value}.{self.provenance.value}" if self.provenance is not None else self.kind.value


class ContextPolicy(BaseModel):
    """The typed context policy (FSD §5)."""

    version: int
    ablated_stages: List[PromptStage]
    kinds: Dict[SegmentKind, KindSpec]
    rule_provenance: Dict[RuleProvenance, TrustLevel]
    stages: Dict[PromptStage, List[PolicyRow]]
    source_sha256: str = Field(..., description="sha256 of the policy file bytes")

    model_config = ConfigDict(extra="forbid", frozen=True)


class PolicyFacts(BaseModel):
    """The system state the predicates are evaluated against, established by the system, never by segments.

    Required segments are checked against these facts, so they must come from trusted state (signed rows,
    auth context), never from the segments being checked: otherwise a missing rule would hide itself.
    """

    signed_guidance_in_force: bool = Field(False, description="Signed WA guidance from a resolved deferral applies")
    amendment_in_force: bool = Field(False, description="A landed identity amendment carries a rule that applies")
    id_scoped: bool = Field(False, description="The rule in force is scoped to a verified identity")
    advisory_rule: bool = Field(False, description="A rule was stated in chat (user or WA), not signed")

    model_config = ConfigDict(extra="forbid", frozen=True)

    @property
    def trusted_rule_in_force(self) -> bool:
        return self.signed_guidance_in_force or self.amendment_in_force


# --------------------------------------------------------------------------------------------------------------
# Guard and manifest
# --------------------------------------------------------------------------------------------------------------


class AssemblyMode(str, Enum):
    """What the guard does on a violation (FSD §6)."""

    FAIL_CLOSED = "fail_closed"  # tests / QA: raise
    STRIP_AND_INCIDENT = "strip_and_incident"  # production: strip, record an incident, proceed


class GuardViolationKind(str, Enum):
    FORBIDDEN = "forbidden"  # the policy does not allow this kind at this stage, in this state
    MISSING_REQUIRED = "missing_required"
    TAINTED = "tainted"  # trust after taint is below the policy's trust for the kind (laundering)
    MISSING_CARRIER = "missing_carrier"  # a required authn / authz / acct is absent
    WRONG_SOURCE = "wrong_source"
    LIFECYCLE_MISMATCH = "lifecycle_mismatch"
    CROSS_SCOPE = "cross_scope"  # a per-task / per-thought segment from another task / thought
    DUPLICATE_SEGMENT_ID = "duplicate_segment_id"


class GuardAction(str, Enum):
    RAISED = "raised"
    STRIPPED = "stripped"
    RECORDED = "recorded"  # a missing required segment: nothing to strip


class GuardViolation(BaseModel):
    kind: GuardViolationKind
    stage: PromptStage
    policy_key: str = Field(..., description="kind or rule.<provenance> the violation concerns")
    segment_id: Optional[str] = Field(None, description="None for a missing required segment")
    detail: str = Field(..., description="Why. Never the segment's text.")
    action: GuardAction

    model_config = ConfigDict(extra="forbid", frozen=True)


class SegmentRecord(BaseModel):
    """One segment of one call, as sent (FSD §8)."""

    segment_id: str
    kind: SegmentKind
    provenance: Optional[RuleProvenance] = None
    source: SegmentSource
    trust: TrustLevel = Field(..., description="Trust after taint")
    lifecycle: Lifecycle
    authn: Optional[AuthnCarrier] = None
    authz: Optional[AuthzCarrier] = None
    acct: Optional[AcctCarrier] = None
    message_index: int = Field(..., ge=0)
    span_start: int = Field(..., ge=0, description="[start, end) in characters of the message content")
    span_end: int = Field(..., ge=0)
    sha256: str = Field(..., description="sha256 of the rendered bytes at the span")
    truncated: bool = False
    derived_from: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid", frozen=True)


class ProviderCapture(str, Enum):
    """How the provider library's own additions to the call were captured (FSD §10, #1363)."""

    NOT_FINALIZED = "not_finalized"  # the manifest has not reached the LLM bus
    CAPTURED = "captured"  # the library's message changes were reproduced and recorded as segments
    NO_MESSAGE_CHANGE = "no_message_change"  # the library added kwargs only (tools, response_format)
    UNSUPPORTED_MODE = "unsupported_mode"  # a provider mode whose changes are not reproduced
    UNRECOGNIZED_CHANGE = "unrecognized_change"  # the library rewrote messages in a way not recorded
    UNAVAILABLE = "unavailable"  # no instructor client / mode on the selected service


class PromptManifest(BaseModel):
    """The per-call record of the segments one LLM call contained (FSD §8). Never placed in the prompt."""

    call_id: str
    task_id: Optional[str] = None
    thought_id: Optional[str] = None
    thought_kind: ManifestThoughtKind
    retry_index: int = Field(0, ge=0)
    stage: PromptStage
    stage_role: StageRole
    response_model: str
    max_tokens_sent: Optional[int] = Field(None, ge=0, description="Filled by the LLM bus from what it sent")
    policy_version: int
    policy_sha256: str
    assembler_version: str
    guard_mode: AssemblyMode
    guard_violations: List[GuardViolation] = Field(default_factory=list)
    segments: List[SegmentRecord] = Field(default_factory=list)
    messages_sha256: str = Field(..., description="sha256 of the assembled messages, as the LLM bus hashes them")
    # Filled when the manifest reaches the LLM bus (logic/prompt_assembly/manifest_scope.py)
    sent_messages_match: Optional[bool] = Field(
        None, description="The bus sent exactly the assembled messages (the differential check, FSD §8)"
    )
    provider_capture: ProviderCapture = ProviderCapture.NOT_FINALIZED
    provider_mode: Optional[str] = Field(None, description="The provider library mode (e.g. instructor 'json_mode')")
    provider_kwargs_added: List[str] = Field(default_factory=list, description="Request kwargs the library added")

    model_config = ConfigDict(extra="forbid", frozen=True)


__all__ = [
    "AcctCarrier",
    "AssemblyMode",
    "AuthnCarrier",
    "AuthzCarrier",
    "ContextPolicy",
    "GrantKind",
    "GuardAction",
    "GuardViolation",
    "GuardViolationKind",
    "KindSpec",
    "Lifecycle",
    "ManifestThoughtKind",
    "PolicyFacts",
    "PolicyPredicate",
    "PolicyRow",
    "PromptManifest",
    "PromptSegment",
    "PromptStage",
    "ProviderCapture",
    "RuleProvenance",
    "SegmentKind",
    "SegmentRecord",
    "SegmentSource",
    "StageRole",
    "TRUST_ORDER",
    "TrustLevel",
    "min_trust",
]
