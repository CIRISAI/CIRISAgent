"""Typed schemas for the live LLM provider conformance matrix.

Every value the matrix records is a Pydantic model — no ``Dict[str, Any]``
crosses a module boundary here. The report file written to disk is
``QuirksReport.model_dump_json()``, so the on-disk format and the in-process
format are the same thing by construction.

Reused from the product (NOT redefined here):
  - ``LLMValidationRequest`` / ``LLMValidationResponse`` — the wizard's own
    request/verdict pair, from ``routes/setup/models.py``.
  - ``LiveModelInfo`` / ``ListModelsResponse`` — the wizard's model listing.
  - ``ModelInfo`` / ``ModelCapabilitiesConfig`` — the on-device catalogue,
    from ``ciris_engine/config/model_capabilities.py``.

What is new here is only the matrix itself: a cell, what came back from the
wire, what the product's classifier made of it, and the gap between the two.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ─────────────────────────────────────────────────────────────────────────────
# Dimension enums — the matrix axes. These are the vocabulary; the actual
# combinations live in dimensions.py as data.
# ─────────────────────────────────────────────────────────────────────────────


class CredentialMode(str, Enum):
    """Failure injection on the credential axis."""

    VALID = "valid"  # the real key from ~/.<provider>_key
    INVALID = "invalid"  # well-formed but never-issued key
    ABSENT = "absent"  # empty string — user hit Next with a blank field
    MALFORMED = "malformed"  # real key with a trailing newline / stray whitespace


class ModelSelector(str, Enum):
    """Failure injection on the model axis."""

    CATALOGUE = "catalogue"  # a model from MODEL_CAPABILITIES.json for this provider
    CHEAP = "cheap"  # the designated cheap probe model (model-independent tests)
    OMITTED = "omitted"  # model=None — exercises the wizard's fabricated default
    NONEXISTENT = "nonexistent"  # a model id that cannot exist anywhere
    WRONG_CASE = "wrong_case"  # a real model id with its case mangled
    GATED = "gated"  # exists in the provider catalogue, account cannot use it
    POLICY_BLOCKED = "policy_blocked"  # exists, but no endpoint satisfies the account's data policy


class ProbeKind(str, Enum):
    """What call the cell makes."""

    CHAT_MINIMAL = "chat_minimal"  # exactly what the wizard's validator does
    CHAT_MAX_TOKENS_OVER_CAP = "chat_max_tokens_over_cap"  # max_tokens above a known provider cap
    CHAT_ALT_BASE_URL = "chat_alt_base_url"  # the base URL the wizard ADVERTISES, not the one it probes
    MODELS_LIST = "models_list"  # the live /models listing the wizard shows
    STATIC_AUDIT = "static_audit"  # no network — a consistency check on our own tables


class ExpectedCause(str, Enum):
    """The true cause of the cell's outcome, known a priori from the injection.

    This is the ground truth the product's user-facing message is graded
    against. A cell whose rendered cause disagrees with its expected cause is
    the defect class that sent Francesco to check his network cable.
    """

    SUCCESS = "success"
    AUTH = "auth"  # key missing, invalid, or malformed
    MODEL_NOT_FOUND = "model_not_found"  # model id does not exist at this provider
    MODEL_ACCESS_DENIED = "model_access_denied"  # model exists; this account may not use it
    POLICY_BLOCKED = "policy_blocked"  # blocked by a data-retention / privacy guardrail
    QUOTA = "quota"  # out of credit or rate limited
    ENDPOINT = "endpoint"  # the base URL genuinely is wrong
    REFUSED_NO_MODEL = "refused_no_model"  # product must refuse pre-network: no model was chosen
    UNKNOWN = "unknown"  # only used for exploratory cells


class RenderedCause(str, Enum):
    """The cause the product's own classifier tells the user about.

    Derived from ``LLMValidationResponse.message``, which is unique per branch
    of ``_classify_llm_connection_error``. Deriving it from the message rather
    than re-implementing the predicates means this cannot drift out of sync
    with the product's branch order.
    """

    SUCCESS = "success"
    AUTH = "auth"  # "Authentication failed"
    MODEL_NOT_FOUND = "model_not_found"  # "Model not found"
    ENDPOINT = "endpoint"  # "Endpoint not found"
    TIMEOUT = "timeout"  # "Connection timeout"
    REFUSED = "refused"  # "Connection refused"
    UNCLASSIFIED = "unclassified"  # "Connection failed" — the raw-error fallthrough
    SDK_MISSING = "sdk_missing"  # "SDK not installed"
    POLICY_BLOCKED = "policy_blocked"  # "Blocked by data policy"
    QUOTA = "quota"  # "Out of credit" / "Rate limited"
    REFUSED_NO_MODEL = "refused_no_model"  # "No model selected" — refused before any network


class FindingKind(str, Enum):
    """The quirk taxonomy. This enum IS the deliverable's vocabulary."""

    MISLEADING_ERROR = "misleading_error"  # rendered cause contradicts the true cause
    UNCLASSIFIED_ERROR = "unclassified_error"  # fell through to the raw-error branch
    STATUS_ANOMALY = "status_anomaly"  # provider used a surprising HTTP status for this injection
    CATALOGUE_STALE = "catalogue_stale"  # our catalogue names a model the provider no longer lists
    LISTED_BUT_UNUSABLE = "listed_but_unusable"  # provider lists it, then rejects a request for it
    FABRICATED_MODEL = "fabricated_model"  # product substituted a model the user never chose
    OPTION_REJECTED = "option_rejected"  # provider hard-errors on an option its peers accept
    OPTION_IGNORED = "option_ignored"  # provider silently ignored an option
    SILENT_FALLBACK = "silent_fallback"  # live query failed; user shown cached data as if current
    EMPTY_MODEL_LIST = "empty_model_list"  # user shown zero models and no explanation
    TABLE_DIVERGENCE = "table_divergence"  # two of our own tables disagree
    CREDENTIAL_ECHOED = "credential_echoed"  # provider echoed key material back in an error
    TRANSPORT_ERROR = "transport_error"  # could not reach the provider — not gradeable
    UNEXPECTED_SUCCESS = "unexpected_success"  # injection that should have failed did not


class KeyLiveness(str, Enum):
    """Whether a provider credential works — established BEFORE the sweep.

    A stale credential is an operations problem, not a product defect. Grading
    a provider's column against a dead key manufactures findings that look like
    provider quirks and are nothing of the sort, so liveness is established
    first and a column that cannot be trusted is skipped rather than failed.

    ``NO_CREDIT`` is deliberately separate from ``EXPIRED_OR_REVOKED``: the key
    is valid and re-issuing it changes nothing. Putting a no-credit provider on
    a re-provisioning list wastes the owner's time on the wrong remedy.
    """

    LIVE = "live"  # credential accepted, a completion came back
    NO_CREDIT = "no_credit"  # credential valid, account out of funds — top up, do NOT re-issue
    EXPIRED_OR_REVOKED = "expired_or_revoked"  # re-provision this one
    RATE_LIMITED = "rate_limited"  # transient; re-run later
    OTHER = "other"  # reached the provider, failed for a reason unrelated to the credential
    MISSING = "missing"  # no key file on disk
    NOT_PROBED = "not_probed"  # --dry-run: nothing was contacted


class KeyStatus(BaseModel):
    """One provider's credential verdict. Never contains the credential."""

    provider: str = Field(..., description="Provider id")
    key_file: str = Field(..., description="Path the key was read from — path only, never the value")
    liveness: KeyLiveness = Field(..., description="Verdict")
    http_status: Optional[int] = Field(None, description="Status the preflight call returned")
    provider_message: Optional[str] = Field(None, description="Provider's own error text, redacted")
    remedy: str = Field(..., description="What a human should actually do about it")

    model_config = ConfigDict(extra="forbid")

    @property
    def needs_reprovisioning(self) -> bool:
        """True only where issuing a NEW key is the fix."""
        return self.liveness in (KeyLiveness.EXPIRED_OR_REVOKED, KeyLiveness.MISSING)

    @property
    def blocks_real_key_cells(self) -> bool:
        """True when cells that use the real credential cannot produce signal.

        Injections that use a synthetic key (INVALID) or none at all (ABSENT)
        are unaffected by our credential being stale, so they keep running —
        they are testing the provider and the product, not our account.
        """
        return self.liveness not in (KeyLiveness.LIVE, KeyLiveness.NO_CREDIT, KeyLiveness.NOT_PROBED)

    @property
    def blocks_token_spend(self) -> bool:
        """True when a token-generating call would only re-observe the same failure."""
        return self.blocks_real_key_cells or self.liveness is KeyLiveness.NO_CREDIT


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


_SEVERITY_ORDER = {
    Severity.CRITICAL: 0,
    Severity.HIGH: 1,
    Severity.MEDIUM: 2,
    Severity.LOW: 3,
    Severity.INFO: 4,
}


def severity_rank(severity: Severity) -> int:
    """Sort key: critical first."""
    return _SEVERITY_ORDER[severity]


# ─────────────────────────────────────────────────────────────────────────────
# Cell definition and results
# ─────────────────────────────────────────────────────────────────────────────


class MatrixCell(BaseModel):
    """One (provider × model × credential × probe) coordinate.

    Cells are generated from ``dimensions.py`` data. ``cell_id`` is stable
    across runs so two reports can be diffed.
    """

    cell_id: str = Field(..., description="Stable identifier: provider/probe/credential/model-selector")
    provider: str = Field(..., description="Provider id as the wizard names it")
    probe: ProbeKind = Field(..., description="What call this cell makes")
    credential: CredentialMode = Field(..., description="Credential injection")
    model_selector: ModelSelector = Field(..., description="Model injection")
    requested_model: Optional[str] = Field(None, description="Model the user would have chosen (None = omitted)")
    base_url: Optional[str] = Field(None, description="Base URL this cell probes (None = SDK default)")
    client_base_url: Optional[str] = Field(
        None,
        description="base_url the CLIENT puts in LLMValidationRequest — normally None for dropdown providers, "
        "and the value the product hands to its classifier. Distinct from base_url, which is where the "
        "request actually goes after the product resolves it.",
    )
    expected_cause: ExpectedCause = Field(..., description="Ground truth for grading the rendered message")
    rationale: str = Field(..., description="Why this cell exists — the quirk it hunts")
    costs_tokens: bool = Field(default=True, description="False for listings and static audits")

    model_config = ConfigDict(extra="forbid")


class LLMProbeOutcome(BaseModel):
    """What actually came back from the provider.

    Every string field is passed through the key redactor before it lands here.
    """

    succeeded: bool = Field(..., description="Whether the call returned 2xx")
    http_status: Optional[int] = Field(None, description="HTTP status, or None for transport-level failures")
    exception_type: Optional[str] = Field(None, description="Fully-qualified provider SDK exception class")
    exception_str: Optional[str] = Field(None, description="str(exception) — exactly what the classifier reads")
    provider_error_code: Optional[str] = Field(None, description="error.code / error.type from the response body")
    provider_error_message: Optional[str] = Field(None, description="error.message from the response body")
    raw_body_excerpt: Optional[str] = Field(None, description="Redacted head of the raw response body")
    effective_model: Optional[str] = Field(None, description="Model actually sent — may differ from requested")
    completion_tokens: Optional[int] = Field(None, description="usage.completion_tokens when the call succeeded")
    listed_model_ids: List[str] = Field(default_factory=list, description="Model ids returned by a MODELS_LIST probe")
    listed_model_ids_truncated: bool = Field(
        default=False,
        description="True when the id list was cut down for storage. Catalogue reconciliation is skipped for a "
        "truncated list — a partial listing cannot prove a model is absent, and reporting it as absent would "
        "manufacture a stale-catalogue finding out of a storage decision.",
    )
    latency_ms: float = Field(default=0.0, ge=0, description="Wall-clock duration of the call")
    from_fixture: bool = Field(default=False, description="True when replayed from a recorded fixture (--dry-run)")

    model_config = ConfigDict(extra="forbid")


class ClassifierVerdict(BaseModel):
    """What the product's own classifier turns the outcome into.

    Produced by feeding the captured exception to the real
    ``_classify_llm_connection_error``. The three ``LLMValidationResponse``
    fields are copied verbatim; ``rendered_cause`` is the branch they imply.
    """

    valid: bool = Field(..., description="LLMValidationResponse.valid")
    message: str = Field(..., description="LLMValidationResponse.message — the branch fingerprint")
    error: Optional[str] = Field(None, description="LLMValidationResponse.error — what the user actually reads")
    rendered_cause: RenderedCause = Field(..., description="Cause implied by the message")

    model_config = ConfigDict(extra="forbid")


class QuirkFinding(BaseModel):
    """One defect or provider quirk, attributable to one cell."""

    kind: FindingKind = Field(..., description="Taxonomy entry")
    severity: Severity = Field(..., description="How much this hurts a real user")
    cell_id: str = Field(..., description="Cell that produced it")
    provider: str = Field(..., description="Provider involved")
    summary: str = Field(..., description="One line, safe to put in a table")
    detail: str = Field(..., description="Full explanation including both sides of the gap")
    truth: Optional[str] = Field(None, description="What the provider actually said")
    rendered: Optional[str] = Field(None, description="What CIRIS told the user")

    model_config = ConfigDict(extra="forbid")


class CellResult(BaseModel):
    """A cell plus everything observed for it."""

    cell: MatrixCell
    outcome: LLMProbeOutcome
    classifier: Optional[ClassifierVerdict] = Field(
        None, description="None for MODELS_LIST / STATIC_AUDIT cells, which have no exception to classify"
    )
    listing: Optional[str] = Field(None, description="MODELS_LIST cells: 'live' or 'static' — the source the user sees")
    findings: List[QuirkFinding] = Field(default_factory=list)
    skipped_reason: Optional[str] = Field(None, description="Set when the cell could not run (e.g. no key on disk)")

    model_config = ConfigDict(extra="forbid")


# ─────────────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────────────


class ProviderSummary(BaseModel):
    """Per-provider roll-up."""

    provider: str
    cells_run: int = 0
    cells_skipped: int = 0
    live_calls: int = 0
    findings_by_severity: dict[str, int] = Field(default_factory=dict)
    catalogue_model_count: int = Field(default=0, description="Models in MODEL_CAPABILITIES.json")
    live_model_count: Optional[int] = Field(None, description="Models the provider's /models returned")
    key_available: bool = Field(default=False, description="Whether ~/.<provider>_key existed (value never read out)")
    key_liveness: KeyLiveness = Field(
        default=KeyLiveness.NOT_PROBED, description="Credential verdict from the preflight"
    )

    model_config = ConfigDict(extra="forbid")


class QuirksReport(BaseModel):
    """The machine-readable deliverable.

    Written to ``<report-dir>/llm_matrix_<timestamp>/quirks_report.json``.
    Contains no credential material: every recorded string is redacted at
    capture time, before it reaches an ``LLMProbeOutcome``.
    """

    schema_version: str = Field(default="1.0.0", description="Bump on breaking report-shape changes")
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    mode: str = Field(..., description="'live' or 'dry-run'")
    providers_selected: List[str] = Field(default_factory=list)
    total_cells: int = 0
    total_live_calls: int = 0
    findings: List[QuirkFinding] = Field(default_factory=list)
    key_statuses: List[KeyStatus] = Field(
        default_factory=list, description="Credential verdict per provider, established before the sweep"
    )
    provider_summaries: List[ProviderSummary] = Field(default_factory=list)
    results: List[CellResult] = Field(default_factory=list)
    classifier_gap_rate: float = Field(
        default=0.0,
        ge=0,
        le=1,
        description="Fraction of gradeable failure cells whose rendered cause contradicted the true cause",
    )

    model_config = ConfigDict(extra="forbid")

    def keys_needing_reprovisioning(self) -> List[KeyStatus]:
        """The list that goes to whoever owns the credentials."""
        return [k for k in self.key_statuses if k.needs_reprovisioning]

    def count_by_severity(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.severity.value] = counts.get(finding.severity.value, 0) + 1
        return counts


__all__ = [
    "CellResult",
    "KeyLiveness",
    "KeyStatus",
    "ClassifierVerdict",
    "CredentialMode",
    "ExpectedCause",
    "FindingKind",
    "LLMProbeOutcome",
    "MatrixCell",
    "ModelSelector",
    "ProbeKind",
    "ProviderSummary",
    "QuirkFinding",
    "QuirksReport",
    "RenderedCause",
    "Severity",
    "severity_rank",
]
