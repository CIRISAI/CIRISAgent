"""
Conscience Schemas v1 - Safety check schemas for CIRIS Agent

Provides schemas for conscience validation results and epistemic safety checks.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict


class ConscienceStatus(str, Enum):
    """Status of a conscience check"""

    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


class EntropyCheckResult(BaseModel):
    """Result of entropy safety check"""

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


class OptimizationVetoResult(BaseModel):
    """Result of optimization veto check"""

    decision: str = Field(description="Decision: proceed, abort, or defer")
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
    where fail-safe lives, not the schema.

    Only `identified_uncertainties` carries a harmless default (empty list)
    — a missing uncertainty list doesn't bypass any gate.
    """

    epistemic_certainty: float = Field(..., ge=0.0, le=1.0, description="Level of epistemic certainty")
    identified_uncertainties: List[str] = Field(default_factory=list, description="Identified uncertainties")
    reflective_justification: str = Field(..., description="Reflective justification")
    recommended_action: str = Field(..., description="Recommended action: proceed, ponder, or defer")

    model_config = ConfigDict(defer_build=True, extra="forbid")


class EpistemicData(BaseModel):
    """Epistemic safety metadata - core epistemic metrics only"""

    entropy_level: float = Field(ge=0.0, le=1.0, description="Current entropy level")
    coherence_level: float = Field(ge=0.0, le=1.0, description="Current coherence level")
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
