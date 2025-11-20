"""
Schemas for TSDB Consolidation data structures.

Provides type safety for all consolidation operations.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict, JSONValue


class RequestData(BaseModel):
    """Typed request data for service interactions."""

    channel_id: Optional[str] = Field(None, description="Channel ID")
    author_id: Optional[str] = Field(None, description="Author ID")
    author_name: Optional[str] = Field(None, description="Author name")
    content: Optional[str] = Field(None, description="Message content")
    parameters: Optional[JSONDict] = Field(default_factory=lambda: {}, description="Request parameters")
    headers: Optional[Dict[str, str]] = Field(default_factory=lambda: {}, description="Request headers")
    metadata: Optional[Dict[str, str]] = Field(default_factory=lambda: {}, description="Request metadata")


class ResponseData(BaseModel):
    """Typed response data for service interactions."""

    execution_time_ms: Optional[float] = Field(None, description="Execution time in milliseconds")
    success: Optional[bool] = Field(None, description="Whether the operation succeeded")
    error: Optional[str] = Field(None, description="Error message if failed")
    error_type: Optional[str] = Field(None, description="Type of error")
    result: Optional[JSONValue] = Field(None, description="Response result")
    resource_usage: Optional[Dict[str, float]] = Field(default_factory=lambda: {}, description="Resource usage metrics")
    metadata: Optional[Dict[str, str]] = Field(default_factory=lambda: {}, description="Response metadata")


class InteractionContext(BaseModel):
    """Typed context data for service interactions."""

    trace_id: Optional[str] = Field(None, description="Trace ID for correlation")
    span_id: Optional[str] = Field(None, description="Span ID for correlation")
    parent_span_id: Optional[str] = Field(None, description="Parent span ID")
    user_id: Optional[str] = Field(None, description="User ID")
    session_id: Optional[str] = Field(None, description="Session ID")
    environment: Optional[str] = Field(None, description="Environment (dev, prod, etc)")
    additional_data: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional context data"
    )


class ServiceInteractionData(BaseModel):
    """Data structure for service interaction consolidation."""

    correlation_id: str = Field(..., description="Unique correlation ID")
    action_type: str = Field(..., description="Type of action performed")
    service_type: str = Field(..., description="Type of service")
    timestamp: datetime = Field(..., description="When the interaction occurred")
    channel_id: str = Field(default="unknown", description="Channel where interaction occurred")

    # Request data fields
    request_data: Optional[RequestData] = Field(None, description="Typed request data")
    author_id: Optional[str] = Field(None, description="ID of the message author")
    author_name: Optional[str] = Field(None, description="Name of the message author")
    content: Optional[str] = Field(None, description="Message content")

    # Response data fields
    response_data: Optional[ResponseData] = Field(None, description="Typed response data")
    execution_time_ms: float = Field(default=0.0, description="Execution time in milliseconds")
    success: bool = Field(default=True, description="Whether the interaction succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")

    # Context data
    context: Optional[InteractionContext] = Field(None, description="Typed context data")


class MetricCorrelationData(BaseModel):
    """Data structure for metric correlation consolidation."""

    correlation_id: str = Field(..., description="Unique correlation ID")
    metric_name: str = Field(..., description="Name of the metric")
    value: float = Field(..., description="Metric value")
    timestamp: datetime = Field(..., description="When the metric was recorded")

    # Request/response data
    request_data: Optional[RequestData] = Field(None, description="Typed request data")
    response_data: Optional[ResponseData] = Field(None, description="Typed response data")

    # Tags and metadata
    tags: Dict[str, str] = Field(default_factory=dict, description="Metric tags")
    source: str = Field(default="correlation", description="Source of the metric (correlation or graph_node)")

    # Additional fields
    unit: Optional[str] = Field(None, description="Unit of measurement")
    aggregation_type: Optional[str] = Field(None, description="Type of aggregation (sum, avg, max, etc)")


class SpanTags(BaseModel):
    """Typed tags for trace spans."""

    task_id: Optional[str] = Field(None, description="Associated task ID")
    thought_id: Optional[str] = Field(None, description="Associated thought ID")
    component_type: Optional[str] = Field(None, description="Component type")
    handler_name: Optional[str] = Field(None, description="Handler name")
    user_id: Optional[str] = Field(None, description="User ID")
    channel_id: Optional[str] = Field(None, description="Channel ID")
    environment: Optional[str] = Field(None, description="Environment")
    version: Optional[str] = Field(None, description="Version")
    additional_tags: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Additional custom tags"
    )


class TraceSpanData(BaseModel):
    """Data structure for trace span consolidation."""

    trace_id: str = Field(..., description="Trace ID")
    span_id: str = Field(..., description="Span ID")
    parent_span_id: Optional[str] = Field(None, description="Parent span ID")
    timestamp: datetime = Field(..., description="When the span started")
    duration_ms: float = Field(default=0.0, description="Span duration in milliseconds")

    # Span metadata
    operation_name: str = Field(..., description="Name of the operation")
    service_name: str = Field(..., description="Service that created the span")
    status: str = Field(default="ok", description="Span status (ok, error, etc)")

    # Tags and context
    tags: Optional[SpanTags] = Field(None, description="Typed span tags")
    task_id: Optional[str] = Field(None, description="Associated task ID")
    thought_id: Optional[str] = Field(None, description="Associated thought ID")
    component_type: Optional[str] = Field(None, description="Component type that created the span")

    # Error information
    error: bool = Field(default=False, description="Whether the span had an error")
    error_message: Optional[str] = Field(None, description="Error message if any")
    error_type: Optional[str] = Field(None, description="Type of error")

    # Performance data
    latency_ms: Optional[float] = Field(None, description="Operation latency")
    resource_usage: Dict[str, float] = Field(default_factory=dict, description="Resource usage metrics")


class ThoughtSummary(BaseModel):
    """Summary of a thought for consolidation."""

    thought_id: str = Field(..., description="Thought ID")
    thought_type: str = Field(..., description="Type of thought")
    status: str = Field(..., description="Thought status")
    created_at: str = Field(..., description="ISO timestamp when created")
    content: Optional[str] = Field(None, description="Thought content summary")
    final_action: Optional[JSONDict] = Field(None, description="Final action taken")
    handler: Optional[str] = Field(None, description="Handler that processed this thought")
    round_number: int = Field(0, description="Processing round")
    depth: int = Field(0, description="Pondering depth")


class TaskMetadata(BaseModel):
    """Typed metadata for tasks."""

    priority: Optional[int] = Field(None, description="Task priority")
    tags: List[str] = Field(default_factory=list, description="Task tags")
    source: Optional[str] = Field(None, description="Task source")
    parent_task_id: Optional[str] = Field(None, description="Parent task ID")
    correlation_id: Optional[str] = Field(None, description="Correlation ID")
    custom_fields: Dict[str, Union[str, int, float, bool]] = Field(
        default_factory=dict, description="Custom metadata fields"
    )


class TaskCorrelationData(BaseModel):
    """Data structure for task correlation consolidation."""

    task_id: str = Field(..., description="Unique task ID")
    status: str = Field(..., description="Task status")
    created_at: datetime = Field(..., description="When task was created")
    updated_at: datetime = Field(..., description="When task was last updated")

    # Task metadata
    channel_id: Optional[str] = Field(None, description="Channel where task originated")
    user_id: Optional[str] = Field(None, description="User who created the task")
    task_type: Optional[str] = Field(None, description="Type of task")

    # Execution data
    retry_count: int = Field(default=0, description="Number of retries")
    duration_ms: float = Field(default=0.0, description="Total task duration")

    # Thoughts and handlers
    thoughts: List[ThoughtSummary] = Field(default_factory=list, description="Associated thought summaries")
    handlers_used: List[str] = Field(default_factory=list, description="Handlers that processed this task")
    final_handler: Optional[str] = Field(None, description="Final handler that completed the task")

    # Outcome data
    success: bool = Field(default=True, description="Whether task succeeded")
    error_message: Optional[str] = Field(None, description="Error message if failed")
    result_summary: Optional[str] = Field(None, description="Summary of task result")

    # Additional context
    metadata: Optional[TaskMetadata] = Field(None, description="Typed task metadata")


class ConversationEntry(BaseModel):
    """Single entry in a conversation."""

    timestamp: Optional[str] = Field(None, description="ISO formatted timestamp")
    correlation_id: str = Field(..., description="Correlation ID")
    action_type: str = Field(..., description="Type of action")
    content: str = Field(default="", description="Message content")
    author_id: Optional[str] = Field(None, description="Author ID")
    author_name: Optional[str] = Field(None, description="Author name")
    execution_time_ms: float = Field(default=0.0, description="Execution time")
    success: bool = Field(default=True, description="Whether action succeeded")


class ParticipantData(BaseModel):
    """Data about a conversation participant."""

    message_count: int = Field(default=0, description="Number of messages")
    channels: List[str] = Field(default_factory=list, description="Channels participated in")
    author_name: Optional[str] = Field(None, description="Participant name")


class MetricAggregation(BaseModel):
    """Aggregated metric data."""

    count: float = Field(..., description="Number of data points")
    sum: float = Field(..., description="Sum of values")
    min: float = Field(..., description="Minimum value")
    max: float = Field(..., description="Maximum value")
    avg: float = Field(..., description="Average value")


class ConversationSummary(BaseModel):
    """Summary of a conversation."""

    channel_id: str = Field(..., description="Channel ID")
    message_count: int = Field(..., description="Number of messages")
    participant_count: int = Field(..., description="Number of participants")
    start_time: str = Field(..., description="ISO timestamp of first message")
    end_time: str = Field(..., description="ISO timestamp of last message")
    participants: List[str] = Field(default_factory=list, description="List of participant IDs")


class TraceSummary(BaseModel):
    """Summary of trace data."""

    trace_count: int = Field(..., description="Number of traces")
    span_count: int = Field(..., description="Total number of spans")
    error_count: int = Field(..., description="Number of error spans")
    average_duration_ms: float = Field(..., description="Average span duration")
    services: List[str] = Field(default_factory=list, description="Services involved")
    operations: List[str] = Field(default_factory=list, description="Operations performed")


class AuditSummary(BaseModel):
    """Summary of audit data."""

    entry_count: int = Field(..., description="Number of audit entries")
    action_types: Dict[str, int] = Field(default_factory=dict, description="Count by action type")
    users: List[str] = Field(default_factory=list, description="Users who performed actions")
    services: List[str] = Field(default_factory=list, description="Services audited")


class TaskSummary(BaseModel):
    """Summary of task data."""

    total_tasks: int = Field(..., description="Total number of tasks")
    completed_tasks: int = Field(..., description="Number of completed tasks")
    failed_tasks: int = Field(..., description="Number of failed tasks")
    average_duration_ms: float = Field(..., description="Average task duration")
    handlers: Dict[str, int] = Field(default_factory=dict, description="Count by handler")
    task_types: Dict[str, int] = Field(default_factory=dict, description="Count by task type")


class MemorySummary(BaseModel):
    """Summary of memory data."""

    node_count: int = Field(..., description="Number of memory nodes")
    node_types: Dict[str, int] = Field(default_factory=dict, description="Count by node type")
    total_size_bytes: int = Field(default=0, description="Total size in bytes")
    scopes: Dict[str, int] = Field(default_factory=dict, description="Count by scope")


class TSDBPeriodSummary(BaseModel):
    """Summary data for a TSDB consolidation period."""

    # Metrics data
    metrics: Dict[str, MetricAggregation] = Field(default_factory=dict, description="Aggregated metrics for the period")

    # Resource usage totals
    total_tokens: int = Field(default=0, description="Total tokens used in period")
    total_cost_cents: int = Field(default=0, description="Total cost in cents for period")
    total_carbon_grams: float = Field(default=0.0, description="Total carbon emissions in grams")
    total_energy_kwh: float = Field(default=0.0, description="Total energy usage in kWh")

    # Action counts
    action_counts: Dict[str, int] = Field(default_factory=dict, description="Count of actions by type")
    source_node_count: int = Field(default=0, description="Number of source nodes consolidated")

    # Period information
    period_start: str = Field(..., description="ISO formatted period start time")
    period_end: str = Field(..., description="ISO formatted period end time")
    period_label: str = Field(..., description="Human-readable period label")

    # Consolidated data summaries
    conversations: List[ConversationSummary] = Field(
        default_factory=list, description="Consolidated conversation summaries"
    )
    traces: List[TraceSummary] = Field(default_factory=list, description="Consolidated trace summaries")
    audits: List[AuditSummary] = Field(default_factory=list, description="Consolidated audit summaries")
    tasks: List[TaskSummary] = Field(default_factory=list, description="Consolidated task summaries")
    memories: List[MemorySummary] = Field(default_factory=list, description="Consolidated memory summaries")


__all__ = [
    # Core data models
    "ServiceInteractionData",
    "MetricCorrelationData",
    "TraceSpanData",
    "TaskCorrelationData",
    "ConversationEntry",
    "ParticipantData",
    "TSDBPeriodSummary",
    # Supporting models
    "RequestData",
    "ResponseData",
    "InteractionContext",
    "SpanTags",
    "ThoughtSummary",
    "TaskMetadata",
    "MetricAggregation",
    "ConversationSummary",
    "TraceSummary",
    "AuditSummary",
    "TaskSummary",
    "MemorySummary",
]
