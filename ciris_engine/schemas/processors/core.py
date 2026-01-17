"""
Processing schemas for thought and DMA evaluation.

Provides type-safe structures for thought processing results.
"""

from typing import Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.conscience.core import (
    CoherenceCheckResult,
    EntropyCheckResult,
    EpistemicData,
    EpistemicHumilityResult,
    OptimizationVetoResult,
)
from ciris_engine.schemas.runtime.enums import HandlerActionType

from ..actions.parameters import (
    DeferParams,
    ForgetParams,
    MemorizeParams,
    ObserveParams,
    PonderParams,
    RecallParams,
    RejectParams,
    SpeakParams,
    TaskCompleteParams,
    ToolParams,
)
from ..dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult, IDMAResult


class DMAResults(BaseModel):
    """Container for DMA evaluation results."""

    ethical_pdma: Optional[EthicalDMAResult] = Field(None, description="Ethical evaluation")
    csdma: Optional[CSDMAResult] = Field(None, description="Common sense evaluation")
    dsdma: Optional[DSDMAResult] = Field(None, description="Domain-specific evaluation")
    idma: Optional[IDMAResult] = Field(None, description="Intuition/CCA epistemic diversity evaluation")
    errors: List[str] = Field(default_factory=list, description="Errors during evaluation")

    model_config = ConfigDict(extra="forbid")


class SingleConscienceCheckResult(BaseModel):
    """Result from checking a single conscience."""

    skip: bool = Field(False, description="Whether this conscience check should be skipped")
    passed: bool = Field(True, description="Whether the conscience check passed")
    reason: Optional[str] = Field(None, description="Reason for failure if not passed")
    epistemic_data: Optional[EpistemicData] = Field(None, description="Epistemic data from this conscience")
    replacement_action: Optional[ActionSelectionDMAResult] = Field(
        None, description="Replacement action if conscience overrides"
    )
    thought_depth_triggered: Optional[bool] = Field(None, description="Whether thought depth guardrail was triggered")
    updated_status_detected: Optional[bool] = Field(None, description="Whether updated status was detected")

    model_config = ConfigDict(extra="forbid")


class ConscienceCheckInternalResult(BaseModel):
    """Internal result from _run_conscience_checks before creating ConscienceApplicationResult."""

    final_action: ActionSelectionDMAResult = Field(..., description="Final action after all conscience checks")
    overridden: bool = Field(False, description="Whether action was overridden by a conscience")
    override_reason: Optional[str] = Field(None, description="Reason for conscience override")
    epistemic_data: Optional[EpistemicData] = Field(
        None, description="Aggregated epistemic data from conscience checks"
    )
    thought_depth_triggered: Optional[bool] = Field(None, description="Whether the thought depth guardrail triggered")
    updated_status_detected: Optional[bool] = Field(
        None, description="Whether the updated status conscience detected changes"
    )

    model_config = ConfigDict(extra="forbid")


class ConscienceApplicationResult(BaseModel):
    """Result from conscience application with all 6 conscience check details.

    Captures results from:
    - Bypass Guardrails (ALL actions): UpdatedStatus, ThoughtDepth
    - Ethical Faculties (non-exempt): Entropy, Coherence, OptimizationVeto, EpistemicHumility
    """

    original_action: ActionSelectionDMAResult = Field(..., description="Original action selected")
    final_action: ActionSelectionDMAResult = Field(..., description="Final action after consciences")
    overridden: bool = Field(False, description="Whether action was overridden")
    override_reason: Optional[str] = Field(None, description="Reason for override")
    epistemic_data: EpistemicData = Field(..., description="Epistemic faculty data from conscience checks (REQUIRED)")

    # === BYPASS GUARDRAILS ===
    # 1. Updated Status Conscience
    updated_status_detected: Optional[bool] = Field(
        None, description="Whether UpdatedStatusConscience detected new information"
    )
    updated_status_content: Optional[str] = Field(None, description="Content of new observation if detected")

    # 2. Thought Depth Conscience
    thought_depth_triggered: Optional[bool] = Field(
        None, description="Whether ThoughtDepthGuardrail forced DEFER due to max depth"
    )
    thought_depth_current: Optional[int] = Field(None, description="Current thought depth")
    thought_depth_max: Optional[int] = Field(None, description="Maximum allowed depth")

    # === ETHICAL FACULTIES ===
    # Flag for exempt actions (skip ethical faculties)
    ethical_faculties_skipped: Optional[bool] = Field(
        None, description="Whether ethical faculties were skipped due to exempt action"
    )

    # 3. Entropy Conscience
    entropy_check: Optional[EntropyCheckResult] = Field(None, description="Entropy conscience check result")

    # 4. Coherence Conscience
    coherence_check: Optional[CoherenceCheckResult] = Field(None, description="Coherence conscience check result")

    # 5. Optimization Veto Conscience
    optimization_veto_check: Optional[OptimizationVetoResult] = Field(
        None, description="Optimization veto conscience check result"
    )

    # 6. Epistemic Humility Conscience
    epistemic_humility_check: Optional[EpistemicHumilityResult] = Field(
        None, description="Epistemic humility conscience check result"
    )

    model_config = ConfigDict(extra="forbid")


class ProcessedThoughtResult(BaseModel):
    """Result from thought processor containing both action and conscience data."""

    action_result: ActionSelectionDMAResult = Field(..., description="Action selection result")
    conscience_result: Optional[ConscienceApplicationResult] = Field(None, description="conscience application result")

    @property
    def selected_action(self) -> HandlerActionType:
        """Convenience property for compatibility."""
        return self.action_result.selected_action

    @property
    def action_parameters(self) -> Union[
        ObserveParams,
        SpeakParams,
        ToolParams,
        PonderParams,
        RejectParams,
        DeferParams,
        MemorizeParams,
        RecallParams,
        ForgetParams,
        TaskCompleteParams,
    ]:
        """Convenience property for compatibility."""
        return self.action_result.action_parameters

    model_config = ConfigDict(extra="forbid")


class ThoughtProcessingMetrics(BaseModel):
    """Metrics for thought processing."""

    processing_time_ms: float = Field(..., description="Total processing time")
    dma_time_ms: float = Field(..., description="DMA evaluation time")
    conscience_time_ms: float = Field(..., description="conscience application time")
    llm_calls: int = Field(..., description="Number of LLM calls")
    tokens_used: int = Field(..., description="Total tokens consumed")

    model_config = ConfigDict(extra="forbid")


class ProcessingError(BaseModel):
    """Error during thought processing."""

    error_type: str = Field(..., description="Type of error")
    error_message: str = Field(..., description="Error message")
    component: str = Field(..., description="Component that failed")
    recoverable: bool = Field(..., description="Whether error is recoverable")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "DMAResults",
    "SingleConscienceCheckResult",
    "ConscienceCheckInternalResult",
    "ConscienceApplicationResult",
    "ProcessedThoughtResult",
    "ThoughtProcessingMetrics",
    "ProcessingError",
]
