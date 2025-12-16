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

    model_config = ConfigDict(extra="forbid")


class CoherenceCheckResult(BaseModel):
    """Result of coherence safety check"""

    passed: bool = Field(description="Whether the check passed")
    coherence_score: float = Field(ge=0.0, le=1.0, description="Coherence score (0=low, 1=high)")
    threshold: float = Field(ge=0.0, le=1.0, description="Threshold used for check")
    message: str = Field(description="Human-readable result message")

    model_config = ConfigDict(extra="forbid")


class OptimizationVetoResult(BaseModel):
    """Result of optimization veto check"""

    decision: str = Field(description="Decision: proceed, abort, or defer")
    justification: str = Field(description="Justification for the decision")
    entropy_reduction_ratio: float = Field(ge=0.0, description="Estimated entropy reduction ratio")
    affected_values: List[str] = Field(default_factory=list, description="Values that would be affected")

    model_config = ConfigDict(extra="forbid")


class EpistemicHumilityResult(BaseModel):
    """Result of epistemic humility check"""

    epistemic_certainty: float = Field(ge=0.0, le=1.0, description="Level of epistemic certainty")
    identified_uncertainties: List[str] = Field(default_factory=list, description="Identified uncertainties")
    reflective_justification: str = Field(description="Reflective justification")
    recommended_action: str = Field(description="Recommended action: proceed, ponder, or defer")

    model_config = ConfigDict(extra="forbid")


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

    model_config = ConfigDict(extra="forbid")


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

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "ConscienceStatus",
    "EntropyCheckResult",
    "CoherenceCheckResult",
    "OptimizationVetoResult",
    "EpistemicHumilityResult",
    "EpistemicData",
    "ConscienceCheckResult",
]
