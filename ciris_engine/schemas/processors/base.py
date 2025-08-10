"""
Schemas for base processor operations.

These replace all Dict[str, Any] usage in base_processor.py.
"""

from datetime import datetime
from typing import Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class ProcessorSpecificMetrics(BaseModel):
    """Processor-specific metrics that extend base metrics."""

    thoughts_generated: int = Field(0, description="Number of thoughts generated")
    actions_dispatched: int = Field(0, description="Number of actions dispatched")
    memories_created: int = Field(0, description="Number of memories created")
    state_transitions: int = Field(0, description="Number of state transitions")
    average_response_time_ms: Optional[float] = Field(None, description="Average response time")
    llm_tokens_used: int = Field(0, description="Total LLM tokens consumed")
    cache_hits: int = Field(0, description="Number of cache hits")
    cache_misses: int = Field(0, description="Number of cache misses")
    custom_counters: Dict[str, int] = Field(default_factory=dict, description="Custom counter metrics")
    custom_gauges: Dict[str, float] = Field(default_factory=dict, description="Custom gauge metrics")

    model_config = ConfigDict(extra="forbid")  # Strict validation for metrics


class ProcessorMetrics(BaseModel):
    """Metrics tracked by processors."""

    start_time: Optional[datetime] = Field(None, description="When processing started")
    end_time: Optional[datetime] = Field(None, description="When processing ended")
    items_processed: int = Field(0, description="Number of items processed")
    errors: int = Field(0, description="Number of errors encountered")
    rounds_completed: int = Field(0, description="Number of processing rounds completed")

    # Additional metrics can be added by specific processors
    additional_metrics: ProcessorSpecificMetrics = Field(
        default_factory=ProcessorSpecificMetrics, description="Processor-specific metrics"
    )


class ProcessorServices(BaseModel):
    """Services available to processors."""

    discord_service: Optional[object] = Field(None, description="Discord service if available")
    memory_service: Optional[object] = Field(None, description="Memory service")
    audit_service: Optional[object] = Field(None, description="Audit service")
    telemetry_service: Optional[object] = Field(None, description="Telemetry service")

    model_config = ConfigDict(arbitrary_types_allowed=True)


class AdapterChannelContext(BaseModel):
    """Context information for a specific channel from an adapter's perspective.

    This is the lightweight schema used by adapters to pass channel information
    to the system. For the comprehensive system-internal channel context, see
    ciris_engine.schemas.runtime.system_context.ChannelContext.
    """

    channel_id: str = Field(..., description="Channel identifier")
    channel_type: str = Field(..., description="Type of channel (discord, api, cli)")
    adapter_name: str = Field(..., description="Name of the adapter")
    user_id: Optional[str] = Field(None, description="User ID if applicable")
    guild_id: Optional[str] = Field(None, description="Guild/server ID if applicable")
    thread_id: Optional[str] = Field(None, description="Thread ID if in a thread")
    permissions: Dict[str, bool] = Field(default_factory=dict, description="Channel permissions")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional channel metadata")

    model_config = ConfigDict(extra="allow")  # Allow adapter-specific fields


class ProcessorContext(BaseModel):
    """Context for processor operations."""

    processor_name: str = Field(..., description="Name of the processor")
    current_state: str = Field(..., description="Current agent state")
    round_number: int = Field(..., description="Current round number")
    channel_context: Optional[AdapterChannelContext] = Field(None, description="Channel context if available")
    task_context: Optional[str] = Field(None, description="Current task being processed")
    memory_context: Optional[str] = Field(None, description="Relevant memory context")


class MetricsUpdate(BaseModel):
    """Update to processor metrics."""

    items_processed: Optional[int] = Field(None, description="Items processed increment")
    errors: Optional[int] = Field(None, description="Errors increment")
    rounds_completed: Optional[int] = Field(None, description="Rounds completed increment")

    # Specific metric updates
    thoughts_generated: Optional[int] = Field(None, description="Thoughts generated increment")
    actions_dispatched: Optional[int] = Field(None, description="Actions dispatched increment")
    memories_created: Optional[int] = Field(None, description="Memories created increment")
    state_transitions: Optional[int] = Field(None, description="State transitions increment")
    llm_tokens_used: Optional[int] = Field(None, description="LLM tokens used increment")
    cache_hits: Optional[int] = Field(None, description="Cache hits increment")
    cache_misses: Optional[int] = Field(None, description="Cache misses increment")

    # Custom metric updates
    custom_counters: Dict[str, int] = Field(default_factory=dict, description="Custom counter increments")
    custom_gauges: Dict[str, float] = Field(default_factory=dict, description="Custom gauge updates")
