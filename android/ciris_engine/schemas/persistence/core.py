"""
Persistence-specific schemas for type-safe database operations.

These schemas ensure all data flowing through the persistence layer is properly typed.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.telemetry.core import ServiceCorrelationStatus


class DeferralPackage(BaseModel):
    """Type-safe container for deferral report package data."""

    defer_until: Optional[datetime] = Field(None, description="Timestamp for deferred execution")
    reason: Optional[str] = Field(None, description="Reason for deferral")
    context: Dict[str, str] = Field(default_factory=dict, description="Additional context as strings")

    model_config = ConfigDict(extra="forbid")


class DeferralReportContext(BaseModel):
    """Type-safe response for deferral report queries."""

    task_id: str = Field(..., description="Associated task ID")
    thought_id: str = Field(..., description="Associated thought ID")
    package: Optional[DeferralPackage] = Field(None, description="Deferral package data")

    model_config = ConfigDict(extra="forbid")


class CorrelationUpdateRequest(BaseModel):
    """Type-safe request for updating correlations."""

    correlation_id: str = Field(..., description="Correlation to update")
    response_data: Optional[Dict[str, str]] = Field(None, description="Response data as strings")
    status: Optional[ServiceCorrelationStatus] = Field(None, description="New status")
    metric_value: Optional[float] = Field(None, description="Metric value if applicable")
    tags: Optional[Dict[str, str]] = Field(None, description="Tags to update")

    model_config = ConfigDict(extra="forbid")


class MetricsQuery(BaseModel):
    """Type-safe query parameters for metrics timeseries."""

    metric_name: str = Field(..., description="Name of the metric to query")
    start_time: Optional[datetime] = Field(None, description="Start of time range")
    end_time: Optional[datetime] = Field(None, description="End of time range")
    tags: Dict[str, str] = Field(default_factory=dict, description="Filter tags")
    aggregation: str = Field("avg", description="Aggregation method: avg, sum, max, min")
    interval: str = Field("1h", description="Time bucket interval")

    model_config = ConfigDict(extra="forbid")


class IdentityContext(BaseModel):
    """Type-safe identity context for processing."""

    agent_name: str = Field(..., description="Agent identifier")
    agent_role: str = Field(..., description="Agent role description")
    description: str = Field(..., description="Agent description")
    domain_specific_knowledge: Dict[str, str] = Field(
        default_factory=dict, description="Domain knowledge as key-value pairs"
    )
    permitted_actions: List[HandlerActionType] = Field(..., description="Allowed actions as enums")
    restricted_capabilities: List[str] = Field(default_factory=list)
    dsdma_prompt_template: Optional[str] = Field(None)
    csdma_overrides: Dict[str, str] = Field(default_factory=dict, description="CSDMA overrides")
    action_selection_pdma_overrides: Dict[str, str] = Field(
        default_factory=dict, description="Action selection overrides"
    )

    model_config = ConfigDict(extra="forbid")


class ThoughtSummary(BaseModel):
    """Type-safe thought summary for recent thoughts queries."""

    thought_id: str = Field(..., description="Unique thought ID")
    thought_type: str = Field(..., description="Type of thought")
    status: str = Field(..., description="Current status")
    created_at: datetime = Field(..., description="Creation timestamp")
    content: str = Field(..., description="Thought content")
    source_task_id: str = Field(..., description="Source task ID")

    model_config = ConfigDict(extra="forbid")


class TaskSummaryInfo(BaseModel):
    """Type-safe task summary for queries returning task info."""

    task_id: str = Field(..., description="Unique task ID")
    description: str = Field(..., description="Task description")
    status: str = Field(..., description="Current status")
    created_at: datetime = Field(..., description="Creation timestamp")
    priority: Optional[int] = Field(None, description="Task priority")
    channel_id: Optional[str] = Field(None, description="Associated channel")

    model_config = ConfigDict(extra="forbid")


class QueryTimeRange(BaseModel):
    """Time range for queries."""

    start_time: datetime = Field(..., description="Start of range")
    end_time: datetime = Field(..., description="End of range")

    model_config = ConfigDict(extra="forbid")


class PersistenceHealth(BaseModel):
    """Health status of persistence layer."""

    healthy: bool = Field(..., description="Overall health status")
    database_accessible: bool = Field(..., description="Can access database")
    table_count: int = Field(..., description="Number of tables")
    connection_pool_size: int = Field(..., description="Connection pool size")
    active_connections: int = Field(..., description="Active connections")
    last_query_time: Optional[datetime] = Field(None, description="Last successful query")
    error_message: Optional[str] = Field(None, description="Error if unhealthy")

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "DeferralPackage",
    "DeferralReportContext",
    "CorrelationUpdateRequest",
    "MetricsQuery",
    "IdentityContext",
    "ThoughtSummary",
    "TaskSummaryInfo",
    "QueryTimeRange",
    "PersistenceHealth",
]
