"""Schemas for DMA orchestration operations."""

from typing import Dict, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.dma.results import CSDMAResult, DSDMAResult, EthicalDMAResult
from ciris_engine.schemas.types import ConfigDict


class DMAMetadata(BaseModel):
    """Metadata for DSDMA operations."""

    channel_id: Optional[str] = Field(None, description="Channel ID if available")
    user_id: Optional[str] = Field(None, description="User ID if available")
    platform: Optional[str] = Field(None, description="Platform name")
    session_data: ConfigDict = Field(default_factory=dict, description="Session-specific data")
    metadata: ConfigDict = Field(default_factory=dict, description="Additional context metadata")


class InitialDMAResults(BaseModel):
    """Results from initial DMA runs - all 3 DMA results are required."""

    ethical_pdma: EthicalDMAResult = Field(..., description="Ethical PDMA result (required)")
    csdma: CSDMAResult = Field(..., description="CSDMA result (required)")
    dsdma: DSDMAResult = Field(..., description="DSDMA result (required)")

    # User prompts passed to each DMA (for debugging/transparency)
    ethical_pdma_prompt: Optional[str] = Field(None, description="User prompt passed to Ethical PDMA")
    csdma_prompt: Optional[str] = Field(None, description="User prompt passed to CSDMA")
    dsdma_prompt: Optional[str] = Field(None, description="User prompt passed to DSDMA")


class DMAError(BaseModel):
    """Error from a DMA execution."""

    dma_name: str = Field(..., description="Name of the DMA that failed")
    error_message: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Type of error")
    traceback: Optional[str] = Field(None, description="Full traceback if available")


class DMAErrors(BaseModel):
    """Collection of DMA errors."""

    ethical_pdma: Optional[DMAError] = Field(None, description="Ethical PDMA error")
    csdma: Optional[DMAError] = Field(None, description="CSDMA error")
    dsdma: Optional[DMAError] = Field(None, description="DSDMA error")

    def has_errors(self) -> bool:
        """Check if any errors occurred."""
        return any([self.ethical_pdma, self.csdma, self.dsdma])

    def get_error_summary(self) -> str:
        """Get summary of all errors."""
        errors = []
        if self.ethical_pdma:
            errors.append(f"ethical_pdma: {self.ethical_pdma.error_message}")
        if self.csdma:
            errors.append(f"csdma: {self.csdma.error_message}")
        if self.dsdma:
            errors.append(f"dsdma: {self.dsdma.error_message}")
        return "; ".join(errors) if errors else "No errors"


class ActionSelectionContext(BaseModel):
    """Context for action selection."""

    thought_id: str = Field(..., description="Thought ID being processed")
    task_id: str = Field(..., description="Task ID")
    channel_id: Optional[str] = Field(None, description="Channel ID if available")
    ethical_pdma_result: EthicalDMAResult = Field(..., description="Ethical evaluation")
    csdma_result: CSDMAResult = Field(..., description="Common sense evaluation")
    dsdma_result: Optional[DSDMAResult] = Field(None, description="Domain specific evaluation")
    metadata: ConfigDict = Field(default_factory=dict, description="Additional context")


class CircuitBreakerStatus(BaseModel):
    """Status of a circuit breaker."""

    name: str = Field(..., description="Circuit breaker name")
    is_open: bool = Field(..., description="Whether circuit is open (failing)")
    failure_count: int = Field(0, description="Number of consecutive failures")
    last_failure: Optional[str] = Field(None, description="Last failure timestamp")
    next_attempt: Optional[str] = Field(None, description="When circuit will close")


class DMAOrchestratorStatus(BaseModel):
    """Status of the DMA orchestrator."""

    circuit_breakers: Dict[str, CircuitBreakerStatus] = Field(..., description="Circuit breaker states")
    retry_limit: int = Field(..., description="Retry limit for DMAs")
    timeout_seconds: float = Field(..., description="Timeout for DMA execution")
    dsdma_available: bool = Field(..., description="Whether DSDMA is configured")


__all__ = [
    "DMAMetadata",
    "InitialDMAResults",
    "DMAError",
    "DMAErrors",
    "ActionSelectionContext",
    "CircuitBreakerStatus",
    "DMAOrchestratorStatus",
]
