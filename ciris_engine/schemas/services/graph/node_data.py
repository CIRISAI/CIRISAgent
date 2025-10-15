"""
Typed node data schemas for graph nodes.

Replaces the generic JSONDict.data: Dict[str, Union[...]] with specific typed schemas.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from ciris_engine.schemas.types import JSONDict


class ValidationRule(BaseModel):
    """A single validation rule for configuration."""

    rule_type: str = Field(..., description="Type of validation: range, regex, enum, etc.")
    parameters: Dict[str, Union[str, int, float, bool]] = Field(..., description="Rule parameters")
    error_message: Optional[str] = Field(None, description="Custom error message")

    model_config = ConfigDict(extra="forbid")


class BaseNodeData(BaseModel):
    """Base class for all typed node data."""

    version: int = Field(1, description="Schema version for migration")
    created_at: datetime = Field(..., description="When this data was created")
    updated_at: datetime = Field(..., description="Last update time")

    model_config = ConfigDict(extra="forbid")  # No extra fields allowed

    @field_serializer("created_at", "updated_at")
    def serialize_datetime(self, dt: datetime) -> str:
        return dt.isoformat()


class ConfigNodeData(BaseNodeData):
    """Data for configuration nodes."""

    key: str = Field(..., description="Configuration key")
    value: Union[str, int, float, bool, List[str], Dict[str, str]] = Field(..., description="Configuration value")
    description: Optional[str] = Field(None, description="What this config controls")
    category: Optional[str] = Field(None, description="Config category: ethical, operational, etc.")
    is_sensitive: bool = Field(False, description="Whether this is a sensitive config")
    validation_rules: Optional[List[ValidationRule]] = Field(None, description="Validation rules for this config")


class TelemetryNodeData(BaseNodeData):
    """Data for telemetry/metrics nodes."""

    metric_name: str = Field(..., description="Name of the metric")
    metric_value: float = Field(..., description="Numeric value")
    metric_type: str = Field(..., description="Type: counter, gauge, histogram")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    labels: Dict[str, str] = Field(default_factory=dict, description="Metric labels")
    aggregation_type: Optional[str] = Field(None, description="How to aggregate: sum, avg, max, min")

    # For time-series data
    start_time: Optional[datetime] = Field(None, description="Start of measurement period")
    end_time: Optional[datetime] = Field(None, description="End of measurement period")
    sample_count: Optional[int] = Field(None, description="Number of samples in this period")


class AuditNodeData(BaseNodeData):
    """Data for audit event nodes."""

    event_type: str = Field(..., description="Type of audit event")
    event_category: str = Field(..., description="Category: security, compliance, operational")
    actor: str = Field(..., description="Who/what triggered this event")
    target: Optional[str] = Field(None, description="What was affected")
    action: str = Field(..., description="What action was taken")
    outcome: str = Field(..., description="Result: success, failure, partial")

    # Additional context
    ip_address: Optional[str] = Field(None, description="Source IP if applicable")
    user_agent: Optional[str] = Field(None, description="User agent if applicable")
    correlation_id: Optional[str] = Field(None, description="For tracing related events")
    risk_score: Optional[float] = Field(None, description="Risk assessment 0.0-1.0")

    # Evidence/details
    evidence: Dict[str, str] = Field(default_factory=dict, description="Supporting evidence")
    error_details: Optional[str] = Field(None, description="Error message if failed")


class MemoryNodeData(BaseNodeData):
    """Data for memory/knowledge nodes."""

    content: str = Field(..., description="The actual memory content")
    memory_type: str = Field(..., description="Type: fact, experience, learning, insight")
    source: str = Field(..., description="Where this memory came from")

    # Relationships
    related_memories: List[str] = Field(default_factory=list, description="Related memory node IDs")
    derived_from: Optional[str] = Field(None, description="Parent memory if derived")

    # Usage tracking
    access_count: int = Field(0, description="How often accessed")
    last_accessed: Optional[datetime] = Field(None, description="Last access time")
    importance_score: float = Field(0.5, description="Importance 0.0-1.0")


class TaskNodeData(BaseNodeData):
    """Data for task-related nodes."""

    task_id: str = Field(..., description="Associated task ID")
    task_type: str = Field(..., description="Type of task")
    status: str = Field(..., description="Current status")
    priority: int = Field(0, description="Task priority")

    # Task details
    description: str = Field(..., description="What this task is about")
    requester: Optional[str] = Field(None, description="Who requested this")
    deadline: Optional[datetime] = Field(None, description="When it's due")

    # Progress tracking
    progress_percentage: float = Field(0.0, description="Completion percentage")
    milestones: List[str] = Field(default_factory=list, description="Completed milestones")
    blockers: List[str] = Field(default_factory=list, description="Current blockers")

    @field_serializer("deadline")
    def serialize_optional_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None


class EnvironmentNodeData(BaseNodeData):
    """Data for environment/context nodes."""

    environment_type: str = Field(..., description="Type: channel, user, system")
    identifier: str = Field(..., description="Unique identifier")
    display_name: Optional[str] = Field(None, description="Human-readable name")

    # Context details
    properties: Dict[str, str] = Field(default_factory=dict, description="Environment properties")
    capabilities: List[str] = Field(default_factory=list, description="What this environment supports")
    restrictions: List[str] = Field(default_factory=list, description="What's not allowed")

    # State tracking
    is_active: bool = Field(True, description="Whether currently active")
    last_interaction: Optional[datetime] = Field(None, description="Last interaction time")
    interaction_count: int = Field(0, description="Total interactions")


# Type alias for all possible node data types
NodeData = Union[ConfigNodeData, TelemetryNodeData, AuditNodeData, MemoryNodeData, TaskNodeData, EnvironmentNodeData]


def create_node_data(
    node_type: str, data: Dict[str, Any]
) -> NodeData:  # NOQA: Modifies dict to add datetime objects for model construction
    """Factory function to create appropriate node data based on type."""
    type_map = {
        "config": ConfigNodeData,
        "telemetry": TelemetryNodeData,
        "audit": AuditNodeData,
        "memory": MemoryNodeData,
        "task": TaskNodeData,
        "environment": EnvironmentNodeData,
    }

    data_class = type_map.get(node_type)
    if not data_class:
        raise ValueError(f"Unknown node type: {node_type}")

    # Add timestamps if not present
    now = datetime.now(timezone.utc)
    if "created_at" not in data:
        data["created_at"] = now
    if "updated_at" not in data:
        data["updated_at"] = now

    # Create instance and cast to appropriate type
    return data_class(**data)  # type: ignore[no-any-return]
