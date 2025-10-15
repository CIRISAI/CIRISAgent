"""
Schemas for main processor operations.

Provides typed schemas for logic/processors/core/main_processor.py.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.types import JSONDict


class ProcessorServices(BaseModel):
    """Services available to processors."""

    service_registry: Optional[object] = Field(None, description="Service registry")
    identity_manager: Optional[object] = Field(None, description="Identity manager")
    memory_service: Optional[object] = Field(None, description="Memory service")
    audit_service: Optional[object] = Field(None, description="Audit service")
    telemetry_service: Optional[object] = Field(None, description="Telemetry service")
    time_service: Optional[object] = Field(None, description="Time service")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ProcessingRoundResult(BaseModel):
    """Result from a single processing round."""

    round_number: int = Field(..., description="Round number")
    state: AgentState = Field(..., description="Current agent state")
    processor_name: str = Field(..., description="Processor that handled this round")
    success: bool = Field(..., description="Whether round succeeded")
    items_processed: int = Field(0, description="Items processed")
    errors: int = Field(0, description="Errors encountered")
    state_changed: bool = Field(False, description="Whether state changed")
    new_state: Optional[AgentState] = Field(None, description="New state if changed")
    processing_time_ms: float = Field(..., description="Processing time in milliseconds")
    details: JSONDict = Field(default_factory=dict, description="Additional round details")


class ProcessingStatus(BaseModel):
    """Overall processing status."""

    is_running: bool = Field(..., description="Whether processing is active")
    current_state: AgentState = Field(..., description="Current agent state")
    current_round: int = Field(0, description="Current round number")
    total_rounds_completed: int = Field(0, description="Total rounds completed")
    start_time: Optional[datetime] = Field(None, description="When processing started")
    last_round_time: Optional[datetime] = Field(None, description="When last round completed")
    errors_last_hour: int = Field(0, description="Errors in last hour")
    state_transitions: int = Field(0, description="Number of state transitions")


class PreloadTask(BaseModel):
    """A task to preload after WORK state transition."""

    description: str = Field(..., description="Task description")
    priority: int = Field(5, description="Task priority")
    channel_id: Optional[str] = Field(None, description="Channel to use")
    metadata: JSONDict = Field(default_factory=dict, description="Additional task metadata")


class StateTransitionResult(BaseModel):
    """Result of a state transition."""

    from_state: AgentState = Field(..., description="Previous state")
    to_state: AgentState = Field(..., description="New state")
    success: bool = Field(..., description="Whether transition succeeded")
    reason: str = Field(..., description="Reason for transition")
    timestamp: datetime = Field(..., description="When transition occurred")
    validation_errors: List[str] = Field(default_factory=list, description="Validation errors if failed")


class MainProcessorMetrics(BaseModel):
    """Metrics for a specific processor."""

    processor_name: str = Field(..., description="Name of processor")
    rounds_handled: int = Field(0, description="Rounds handled by this processor")
    items_processed: int = Field(0, description="Total items processed")
    errors: int = Field(0, description="Total errors")
    average_round_time_ms: float = Field(0.0, description="Average round processing time")
    last_active: Optional[datetime] = Field(None, description="Last activity time")


class GlobalProcessingMetrics(BaseModel):
    """Global metrics across all processors."""

    total_rounds: int = Field(0, description="Total rounds across all processors")
    total_items_processed: int = Field(0, description="Total items processed")
    total_errors: int = Field(0, description="Total errors")
    uptime_seconds: float = Field(0.0, description="Processing uptime")
    processor_metrics: Dict[str, MainProcessorMetrics] = Field(
        default_factory=dict, description="Per-processor metrics"
    )
    state_distribution: Dict[AgentState, int] = Field(default_factory=dict, description="Time spent in each state")


class ShutdownRequest(BaseModel):
    """Request to shutdown processing."""

    reason: str = Field(..., description="Reason for shutdown")
    graceful: bool = Field(True, description="Whether to shutdown gracefully")
    timeout_seconds: float = Field(30.0, description="Timeout for graceful shutdown")
    force_after_timeout: bool = Field(True, description="Force shutdown after timeout")
    requested_by: str = Field("system", description="Who requested shutdown")
    timestamp: datetime = Field(..., description="When shutdown was requested")
