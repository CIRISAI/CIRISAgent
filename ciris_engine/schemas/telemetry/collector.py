"""
Schemas for comprehensive telemetry collector operations.

These replace all Dict[str, Any] usage in logic/telemetry/comprehensive_collector.py.
"""

from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field


class HealthDetails(BaseModel):
    """Health details for system components."""

    adapters: str = Field("unknown", description="Adapter health status")
    services: str = Field("unknown", description="Service health status")
    processor: str = Field("unknown", description="Processor health status")
    error: Optional[str] = Field(None, description="Error message if any")


class HealthStatus(BaseModel):
    """Overall system health status."""

    overall: str = Field("unknown", description="Overall health: healthy, degraded, critical, error, unknown")
    details: HealthDetails = Field(
        default_factory=lambda: HealthDetails(adapters="unknown", services="unknown", processor="unknown", error=None),
        description="Health details",
    )


class MetricEntry(BaseModel):
    """A single metric history entry."""

    timestamp: str = Field(..., description="ISO timestamp")
    value: float = Field(..., description="Metric value")
    tags: Dict[str, str] = Field(default_factory=dict, description="Metric tags")


class ProcessorStateSnapshot(BaseModel):
    """Snapshot of processor state."""

    thoughts_pending: int = Field(0, description="Thoughts pending")
    thoughts_processing: int = Field(0, description="Thoughts processing")
    current_round: int = Field(0, description="Current round number")


class SingleStepResult(BaseModel):
    """Result from executing a single processing step."""

    status: str = Field(..., description="Status: completed, error")
    error: Optional[str] = Field(None, description="Error message if failed")
    round_number: Optional[int] = Field(None, description="Round number executed")
    execution_time_ms: Optional[int] = Field(None, description="Execution time in milliseconds")
    before_state: Optional[ProcessorStateSnapshot] = Field(None, description="State before execution")
    after_state: Optional[ProcessorStateSnapshot] = Field(None, description="State after execution")
    processing_result: Any = Field(None, description="Processing result")
    timestamp: str = Field(..., description="Execution timestamp")
    summary: Optional[Dict[str, Union[str, int, float, bool]]] = Field(None, description="Execution summary")


class ProcessingQueueStatus(BaseModel):
    """Status of the processing queue."""

    status: Optional[str] = Field(None, description="Status: available, unavailable")
    size: Optional[int] = Field(None, description="Queue size")
    capacity: Optional[Any] = Field(None, description="Queue capacity")
    oldest_item_age: Optional[str] = Field(None, description="Age of oldest item")
