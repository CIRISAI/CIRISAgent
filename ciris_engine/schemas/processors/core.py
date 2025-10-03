"""
Processing schemas for thought and DMA evaluation.

Provides type-safe structures for thought processing results.
"""

from typing import Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field

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
from ..dma.results import ActionSelectionDMAResult, CSDMAResult, DSDMAResult, EthicalDMAResult


class DMAResults(BaseModel):
    """Container for DMA evaluation results."""

    ethical_pdma: Optional[EthicalDMAResult] = Field(None, description="Ethical evaluation")
    csdma: Optional[CSDMAResult] = Field(None, description="Common sense evaluation")
    dsdma: Optional[DSDMAResult] = Field(None, description="Domain-specific evaluation")
    errors: List[str] = Field(default_factory=list, description="Errors during evaluation")

    model_config = ConfigDict(extra="forbid")


class ConscienceApplicationResult(BaseModel):
    """Result from conscience application."""

    original_action: ActionSelectionDMAResult = Field(..., description="Original action selected")
    final_action: ActionSelectionDMAResult = Field(..., description="Final action after consciences")
    overridden: bool = Field(False, description="Whether action was overridden")
    override_reason: Optional[str] = Field(None, description="Reason for override")
    epistemic_data: Dict[str, str] = Field(default_factory=dict, description="Epistemic faculty data")
    thought_depth_triggered: Optional[bool] = Field(
        None, description="Whether the thought depth guardrail forced an override"
    )
    updated_status_detected: Optional[bool] = Field(
        None, description="Whether the updated status conscience detected new information"
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
    "ConscienceApplicationResult",
    "ProcessedThoughtResult",
    "ThoughtProcessingMetrics",
    "ProcessingError",
]
