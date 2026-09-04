"""
Conscience Schemas v1 - Safety check schemas for CIRIS Agent

Provides schemas for conscience validation results and epistemic safety checks.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ciris_engine.schemas.types import JSONDict


class ConscienceStatus(str, Enum):
    """Status of a conscience check"""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    #: The check COULD NOT RUN — the model was unreachable (timeout, connection,
    #: rate limit, auth, missing model). Distinct from FAILED, which means the
    #: check ran and objected. Conflating them is CIRISAgent#1049: a provider
    #: timeout was reported as "Epistemic humility concern: abort", which reads
    #: as the agent declining, and a scorer counted it as exactly that.
    #: Still fails closed (passed=False) — it just says so honestly.
    ERROR = "error"


class EntropyResult(BaseModel):
    """Raw LLM output schema for the IRIS-E semantic-entropy shard.

    IRIS-E performs in-prompt self-resampling rather than judging surface
    disorder. The LLM is asked to enumerate three semantically-different
    directions a thoughtful CIRIS-aligned agent could have gone on the same
    task, THEN compare the actual response against that alternative space.

      - entropy 0.0 → the three alternatives converge to the same meaning
                      as the actual response (anchored, low confabulation
                      risk).
      - entropy 1.0 → the alternatives diverge widely from each other AND
                      from the actual response (unanchored, high
                      confabulation risk) OR the actual response is an
                      outlier to a tight cluster (sycophantic drift,
                      attractor capture).

    FLAT SCHEMA — three primitive string fields rather than a List[str].
    Complex schemas (lists, nested types) trigger "forced function calling
    (mode = ANY) is not supported" on several OpenRouter backends and
    degrade structured-output reliability on Llama-family models. Three
    explicit fields keep the schema flat and composable with the same
    flat-fields convention ASPDMALLMResult uses. Consumers that want the
    list-shape use the `alternative_meanings` property.
    """

    alternative_1: str = Field(
        default="",
        description=(
            "First alternative direction the agent could have taken. SHORT "
            "PHRASE (3-10 words). NOT a paraphrase of the actual response — "
            "a genuinely different angle, conclusion, or framing."
        ),
    )
    alternative_2: str = Field(
        default="",
        description=(
            "Second alternative direction. SHORT PHRASE (3-10 words). Must "
            "be genuinely different from alternative_1 and from the actual "
            "response — not a paraphrase, a different framing-direction."
        ),
    )
    alternative_3: str = Field(
        default="",
        description=(
            "Third alternative direction. SHORT PHRASE (3-10 words). Must "
            "be genuinely different from alternative_1, alternative_2, and "
            "the actual response — not a paraphrase, a different framing-"
            "direction. The three together form the cluster the actual "
            "response is compared against."
        ),
    )
    actual_is_representative: bool = Field(
        default=True,
        description=(
            "Whether the actual response sits inside the meaning cluster "
            "formed by the three alternatives. False indicates outlier / "
            "attractor-capture / sycophantic-drift risk."
        ),
    )
    entropy: float = Field(
        ge=0.0,
        le=1.0,
        description=(
            "Semantic entropy 0.00-1.00. High when the three alternatives "
            "diverge from each other or when the actual response is an "
            "outlier to the cluster."
        ),
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")

    @property
    def alternative_meanings(self) -> List[str]:
        """List-of-non-empty-alternatives view, for consumers (traces,
        retry-guidance builders) that read the cluster as a list. Drops
        empty strings so callers don't need to filter."""
        return [a for a in (self.alternative_1, self.alternative_2, self.alternative_3) if a]


class CoherenceResult(BaseModel):
    """Raw LLM output schema for the IRIS-C coherence shard. Single
    primitive float field — the simplest flat schema possible."""

    coherence: float = Field(ge=0.0, le=1.0)

    model_config = ConfigDict(defer_build=True, extra="forbid")


class EntropyCheckResult(BaseModel):
    """Post-evaluation entropy result — wraps the raw `EntropyResult` LLM
    output with the threshold-decision the conscience evaluator applied.

    Distinct from `EntropyResult` because this carries the
    pass/fail/threshold tuple the rest of the pipeline reads after the
    conscience has decided. Downstream consumers (streaming events, retry
    guidance, audit traces) read THIS, not the raw LLM output."""

    passed: bool = Field(description="Whether the check passed")
    entropy_score: float = Field(ge=0.0, le=1.0, description="Entropy score (0=low, 1=high)")
    threshold: float = Field(ge=0.0, le=1.0, description="Threshold used for check")
    message: str = Field(description="Human-readable result message")
    # The 3 semantically-different alternatives IRIS-E enumerated alongside the
    # actual response. Preserved so downstream retry guidance can use them as
    # concrete pivot targets instead of free-text scolding.
    alternative_meanings: List[str] = Field(
        default_factory=list, description="Alternatives IRIS-E enumerated (typically 3)"
    )
    actual_is_representative: Optional[bool] = Field(
        default=None, description="Whether the actual response sits in the alternative-meaning cluster"
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


class CoherenceCheckResult(BaseModel):
    """Result of coherence safety check"""

    passed: bool = Field(description="Whether the check passed")
    coherence_score: float = Field(ge=0.0, le=1.0, description="Coherence score (0=low, 1=high)")
    threshold: float = Field(ge=0.0, le=1.0, description="Threshold used for check")
    message: str = Field(description="Human-readable result message")

    model_config = ConfigDict(defer_build=True, extra="forbid")


# --- GATE VERBS -------------------------------------------------------------
# The two LLM-backed gate shards (optimization veto, epistemic humility) each
# ask the model for a single decision verb. On 2026-09-04 llama-4-scout
# answered the humility check with recommended_action="speak" -- the name of
# the action it had been asked to evaluate, meaning "go ahead" -- and the bare
# `str` field accepted it, so `passed = (verb == "proceed")` failed a reply the
# model had just called ethically unremarkable. The action was forced to PONDER
# twice on one thought and the user never got an answer.
#
# Normalise the VERB, and nothing else: case and whitespace, common synonyms,
# and the evaluated action's own name (an echo is approval). Anything still
# unrecognised raises, which pydantic turns into a ValidationError and
# instructor feeds back to the model as a reask naming the allowed verbs --
# that is the retry the gate should have had. The fields stay strictly
# required; this widens what counts as a verb, never what counts as a result.
_ACTION_ECHO_IS_APPROVAL = frozenset({"speak", "tool", "observe", "memorize", "recall", "forget", "task_complete"})
_VERB_SYNONYMS = {
    "proceed": frozenset({"proceed", "continue", "approve", "approved", "accept", "accepted", "allow", "allowed", "ok", "okay", "pass", "go", "yes"}),
    "ponder": frozenset({"ponder", "reconsider", "rethink", "reflect", "pause", "revise", "modify", "amend"}),
    "defer": frozenset({"defer", "escalate", "wise_authority", "wa", "human"}),
    "abort": frozenset({"abort", "reject", "stop", "halt", "block", "veto", "deny"}),
}


def normalize_gate_verb(value: object, *, allowed: tuple, offered: tuple, fallback: Optional[Dict[str, str]] = None) -> str:
    """Return the canonical verb for a model's decision string, or raise.

    `allowed` is what the field accepts (may include the code's own fail-closed
    fallback, e.g. "abort"); `offered` is what the model is told it may say, so
    the reask message never advertises a verb we do not want it to choose.
    `fallback` maps a recognised-but-not-allowed canonical verb to an allowed
    one -- the optimization veto has no reconsider verb, and has always passed
    anything that was not abort/defer, so "modify" reads as proceed there.
    """
    if not isinstance(value, str):
        raise ValueError(f"decision verb must be a string, one of {', '.join(offered)}; got {type(value).__name__}")
    raw = value.strip().lower().strip("\"'.")
    # "HandlerActionType.SPEAK" -> "speak"
    raw = raw.rsplit(".", 1)[-1]
    if raw in _ACTION_ECHO_IS_APPROVAL and "proceed" in allowed:
        return "proceed"
    for canonical, words in _VERB_SYNONYMS.items():
        if raw in words:
            if canonical in allowed:
                return canonical
            if fallback and canonical in fallback and fallback[canonical] in allowed:
                return fallback[canonical]
    raise ValueError(f"decision verb must be one of {', '.join(offered)}; got {value!r}")


class OptimizationVetoResult(BaseModel):
    """Result of optimization veto check"""

    decision: str = Field(description="Decision: proceed, abort, or defer")

    @field_validator("decision", mode="before")
    @classmethod
    def _normalize_decision(cls, v: object) -> str:
        return normalize_gate_verb(
            v, allowed=("proceed", "abort", "defer"), offered=("proceed", "abort", "defer"), fallback={"ponder": "proceed"}
        )
    justification: str = Field(default="", description="Justification for the decision")
    entropy_reduction_ratio: float = Field(
        ge=0.0,
        description="Estimated entropy reduction ratio",
        validation_alias="entropy_reduction",  # Accept common LLM variation
    )
    affected_values: List[str] = Field(default_factory=list, description="Values that would be affected")

    model_config = ConfigDict(defer_build=True, extra="forbid", populate_by_name=True)


class EpistemicHumilityResult(BaseModel):
    """Result of epistemic humility check.

    This is a SAFETY GATE. When the LLM cannot produce a valid check result,
    the conscience-execution layer already safe-fails the thought to PONDER
    with an "abort" override (see EpistemicHumilityConscience.check on LLM
    exception). Schema-level defaults on the gate fields would route an
    empty/malformed LLM output to `recommended_action="proceed"` with
    `epistemic_certainty=0.5` and thus silently pass through the gate —
    that's a fail-open for an alignment conscience, the exact opposite of
    what this shard is for.

    Keep `recommended_action`, `epistemic_certainty`, and
    `reflective_justification` strictly required. The conscience code is
    where fail-safe lives, not the schema. The only leniency is the VERB
    normaliser (see normalize_gate_verb): a synonym or an echo of the evaluated
    action is read as the verb it means; an unrecognised verb is a validation
    error, which instructor reasks -- it is never defaulted.

    Only `identified_uncertainties` carries a harmless default (empty list)
    — a missing uncertainty list doesn't bypass any gate.
    """

    epistemic_certainty: float = Field(..., ge=0.0, le=1.0, description="Level of epistemic certainty")
    identified_uncertainties: List[str] = Field(default_factory=list, description="Identified uncertainties")
    reflective_justification: str = Field(..., description="Reflective justification")
    recommended_action: str = Field(..., description="Recommended action: proceed, ponder, or defer")

    @field_validator("recommended_action", mode="before")
    @classmethod
    def _normalize_recommended_action(cls, v: object) -> str:
        # "abort" is accepted because the conscience's fail-closed fallback
        # constructs it; it is deliberately NOT in `offered`, so a reask never
        # invites the model to veto by naming the option.
        return normalize_gate_verb(v, allowed=("proceed", "ponder", "defer", "abort"), offered=("proceed", "ponder", "defer"))

    model_config = ConfigDict(defer_build=True, extra="forbid")


class EpistemicData(BaseModel):
    """Epistemic safety metadata - core epistemic metrics only"""

    # NULLABLE ON PURPOSE: None means NOT MEASURED, and there must be a way to
    # say that. These were non-nullable, so a code path with no measurement had
    # no honest value to write and substituted entropy=0.1 / coherence=0.9 —
    # numbers that are indistinguishable downstream from a faculty that actually
    # ran and returned them. A trace then carried a confident scalar for a check
    # that never happened.
    #
    # Anything consuming these must handle None as "unmeasured" rather than
    # coercing it to a number; a default here is a fabricated measurement.
    entropy_level: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Current entropy level; None if not measured"
    )
    coherence_level: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Current coherence level; None if not measured"
    )
    uncertainty_acknowledged: bool = Field(description="Whether uncertainty was acknowledged")
    reasoning_transparency: float = Field(ge=0.0, le=1.0, description="Transparency of reasoning")
    # NEW: Stores the actual content of a new observation that arrived during processing
    # This is used by UpdatedStatusConscience to pass the new message to retry context
    CIRIS_OBSERVATION_UPDATED_STATUS: Optional[str] = Field(
        default=None, description="Content of new observation that arrived during processing"
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")

    @classmethod
    def create_neutral(cls) -> "EpistemicData":
        """Create neutral/default EpistemicData for fallback cases."""
        return cls(
            entropy_level=0.5,
            coherence_level=0.5,
            uncertainty_acknowledged=True,
            reasoning_transparency=0.5,
        )


class ConscienceCheckResult(BaseModel):
    """Unified result from conscience safety checks"""

    status: ConscienceStatus = Field(description="Overall check status")
    passed: bool = Field(description="Whether all checks passed")
    reason: Optional[str] = Field(default=None, description="Reason for failure/warning")
    check_ran: bool = Field(
        default=True,
        description=(
            "False when the shard could not reach its model, so no judgement was formed. "
            "Callers MUST NOT retry on this: the retry makes the same call and spends "
            "another full timeout (CIRISAgent#1049)."
        ),
    )
    epistemic_data: Optional[EpistemicData] = Field(
        default=None, description="Epistemic safety metadata (provided by epistemic consciences)"
    )

    # Detailed check results (each conscience provides its own check)
    entropy_check: Optional[EntropyCheckResult] = Field(default=None, description="Entropy check result")
    coherence_check: Optional[CoherenceCheckResult] = Field(default=None, description="Coherence check result")
    optimization_veto_check: Optional[OptimizationVetoResult] = Field(
        default=None, description="Optimization veto result"
    )
    epistemic_humility_check: Optional[EpistemicHumilityResult] = Field(
        default=None, description="Humility check result"
    )

    # Metrics
    entropy_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Overall entropy score")
    coherence_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Overall coherence score")

    # Preserved IRIS-E alternatives (pivot targets for recursive ASPDMA retry)
    entropy_alternatives: Optional[List[str]] = Field(
        default=None, description="IRIS-E's enumerated alternative meanings for retry guidance"
    )
    entropy_actual_is_representative: Optional[bool] = Field(
        default=None, description="IRIS-E's actual_is_representative flag"
    )

    # Prompts used (for streaming/debugging when include_prompts flag is set)
    entropy_prompt: Optional[str] = Field(default=None, description="User prompt used for entropy evaluation")
    coherence_prompt: Optional[str] = Field(default=None, description="User prompt used for coherence evaluation")
    optimization_veto_prompt: Optional[str] = Field(default=None, description="User prompt used for optimization veto")
    epistemic_humility_prompt: Optional[str] = Field(
        default=None, description="User prompt used for epistemic humility evaluation"
    )

    # Processing metadata
    check_timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When check was performed"
    )
    processing_time_ms: Optional[float] = Field(default=None, ge=0.0, description="Processing time in milliseconds")

    # Optional replacement action for conscience checks that override the selected action
    # Used by ThoughtDepthGuardrail and UpdatedStatusConscience
    replacement_action: Optional[JSONDict] = Field(
        default=None, description="Replacement action when conscience overrides"
    )

    # Optional observation content for UpdatedStatusConscience
    CIRIS_OBSERVATION_UPDATED_STATUS: Optional[str] = Field(
        default=None, description="New observation that arrived during processing"
    )
    original_action: Optional[JSONDict] = Field(
        default=None, description="Original action payload evaluated by conscience"
    )
    thought_depth_triggered: Optional[bool] = Field(
        default=None, description="Whether the thought depth guardrail triggered"
    )
    updated_status_detected: Optional[bool] = Field(
        default=None, description="Whether the updated status conscience detected changes"
    )
    action_sequence_triggered: Optional[bool] = Field(
        default=None, description="Whether the action sequence conscience blocked a repeated SPEAK"
    )

    model_config = ConfigDict(defer_build=True, extra="forbid")


__all__ = [
    "ConscienceStatus",
    "EntropyCheckResult",
    "CoherenceCheckResult",
    "OptimizationVetoResult",
    "EpistemicHumilityResult",
    "EpistemicData",
    "ConscienceCheckResult",
]
