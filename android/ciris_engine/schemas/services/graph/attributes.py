"""
Typed node attribute schemas for graph services.

Provides strongly-typed schemas for graph node attributes.
These schemas ensure type safety across all graph node operations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Type, Union

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONValue


class NodeAttributesBase(BaseModel):
    """
    Base schema for all graph node attributes.

    This replaces the Dict[str, Any] pattern in graph services.
    All node-specific attributes should inherit from this base.
    """

    # Core temporal tracking
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When this node was created"
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When this node was last updated"
    )

    # Attribution
    created_by: str = Field(..., description="Service or user that created this node")
    updated_by: Optional[str] = Field(None, description="Service or user that last updated this node")

    # Metadata
    tags: List[str] = Field(default_factory=list, description="Tags for categorization and search")
    version: int = Field(1, ge=1, description="Schema version for migration support")

    # Security
    secret_refs: List[str] = Field(default_factory=list, description="Secret reference UUIDs for encrypted data")

    model_config = ConfigDict(
        extra="forbid",  # No extra fields allowed - ensures type safety
        validate_assignment=True,  # Validate on attribute assignment
        str_strip_whitespace=True,  # Clean up string inputs
    )


class MemoryNodeAttributes(NodeAttributesBase):
    """
    Specific attributes for memory nodes.

    Used by the memory service for storing knowledge, experiences, and insights.
    """

    # Memory content
    content: str = Field(..., description="The actual memory content")
    content_type: str = Field("text", description="Type of content: text, embedding, reference")

    # Memory classification
    memory_type: str = Field(..., description="Type: fact, experience, learning, insight, observation")
    importance: float = Field(0.5, ge=0.0, le=1.0, description="Importance score from 0.0 to 1.0")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence in this memory from 0.0 to 1.0")

    # Source tracking
    source: str = Field(..., description="Where this memory originated")
    source_type: str = Field("internal", description="Source type: internal, user, system, external")

    # Context
    channel_id: Optional[str] = Field(None, description="Channel context if applicable")
    user_id: Optional[str] = Field(None, description="User context if applicable")
    task_id: Optional[str] = Field(None, description="Task context if applicable")

    # Usage tracking
    access_count: int = Field(0, ge=0, description="Number of times accessed")
    last_accessed: Optional[datetime] = Field(None, description="Last access timestamp")

    # Relationships (stored as edge data, but tracked here for quick access)
    related_memories: List[str] = Field(default_factory=list, description="IDs of related memory nodes")
    derived_from: Optional[str] = Field(None, description="Parent memory ID if this is derived")

    # Embeddings support
    embedding_model: Optional[str] = Field(None, description="Model used for embedding")
    embedding_dimensions: Optional[int] = Field(None, description="Embedding vector dimensions")

    model_config = ConfigDict(extra="forbid")


class ConfigNodeAttributes(NodeAttributesBase):
    """
    Specific attributes for configuration nodes.

    Used by the config service for storing system and behavioral configuration.
    """

    # Configuration identity
    key: str = Field(..., description="Configuration key (unique within scope)")
    value: Union[str, int, float, bool, List[str], Dict[str, str]] = Field(..., description="Configuration value")

    # Metadata
    description: str = Field(..., description="What this configuration controls")
    category: str = Field(..., description="Category: system, behavioral, ethical, operational")

    # Validation
    value_type: str = Field(..., description="Expected type: string, integer, float, boolean, list, dict")
    validation_rules: List[Dict[str, JSONValue]] = Field(
        default_factory=list, description="Validation rules for this config"
    )

    # Security and sensitivity
    is_sensitive: bool = Field(False, description="Whether this contains sensitive data")
    requires_authority: bool = Field(False, description="Whether changes require WiseAuthority approval")

    # Change tracking
    previous_value: Optional[Union[str, int, float, bool, List[str], Dict[str, str]]] = Field(
        None, description="Previous value before last update"
    )
    change_reason: Optional[str] = Field(None, description="Reason for last change")
    approved_by: Optional[str] = Field(None, description="Who approved this config if required")

    # Scope and applicability
    scope: str = Field("system", description="Scope: system, channel, user")
    applies_to: List[str] = Field(default_factory=list, description="Specific entities this applies to")

    # Lifecycle
    is_active: bool = Field(True, description="Whether this config is currently active")
    expires_at: Optional[datetime] = Field(None, description="When this config expires")

    model_config = ConfigDict(extra="forbid")


class TelemetryNodeAttributes(NodeAttributesBase):
    """
    Specific attributes for telemetry nodes.

    Used by the telemetry service for storing metrics, performance data, and system observations.
    """

    # Metric identity
    metric_name: str = Field(..., description="Name of the metric")
    metric_type: str = Field(..., description="Type: counter, gauge, histogram, summary")

    # Metric value
    value: float = Field(..., description="Numeric value of the metric")
    unit: Optional[str] = Field(None, description="Unit of measurement")

    # Time window
    start_time: datetime = Field(..., description="Start of measurement period")
    end_time: datetime = Field(..., description="End of measurement period")
    duration_seconds: float = Field(..., ge=0, description="Duration of measurement period")

    # Aggregation
    aggregation_type: Optional[str] = Field(
        None, description="How this was aggregated: sum, avg, max, min, p50, p95, p99"
    )
    sample_count: int = Field(1, ge=1, description="Number of samples in this metric")

    # Statistical data (for histograms/summaries)
    min_value: Optional[float] = Field(None, description="Minimum observed value")
    max_value: Optional[float] = Field(None, description="Maximum observed value")
    mean_value: Optional[float] = Field(None, description="Mean/average value")
    std_deviation: Optional[float] = Field(None, description="Standard deviation")
    percentiles: Dict[str, float] = Field(default_factory=dict, description="Percentile values (e.g., p50, p95, p99)")

    # Labels and dimensions
    labels: Dict[str, str] = Field(default_factory=dict, description="Metric labels for filtering and grouping")

    # Source information
    service_name: str = Field(..., description="Service that generated this metric")
    host: Optional[str] = Field(None, description="Host/instance that generated this")

    # Alert thresholds
    warning_threshold: Optional[float] = Field(None, description="Warning threshold value")
    critical_threshold: Optional[float] = Field(None, description="Critical threshold value")
    threshold_direction: Optional[str] = Field(None, description="Threshold direction: above, below")

    # Resource usage (for resource metrics)
    resource_type: Optional[str] = Field(None, description="Resource type: cpu, memory, disk, network, tokens")
    resource_limit: Optional[float] = Field(None, description="Resource limit if applicable")

    model_config = ConfigDict(extra="forbid")


class LogNodeAttributes(NodeAttributesBase):
    """
    Specific attributes for log entry nodes.

    Used by the memory service for storing log entries as TSDB_DATA nodes.
    """

    # Log content
    log_message: str = Field(..., description="The log message content")
    log_level: str = Field(..., description="Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL")

    # Log metadata
    log_tags: Dict[str, str] = Field(default_factory=dict, description="Additional tags for the log entry")
    retention_policy: str = Field("raw", description="Retention policy for this log")

    model_config = ConfigDict(extra="forbid")


# Type unions for flexibility
AnyNodeAttributes = Union[
    NodeAttributesBase, MemoryNodeAttributes, ConfigNodeAttributes, TelemetryNodeAttributes, LogNodeAttributes
]


def create_node_attributes(node_type: str, data: Dict[str, JSONValue], created_by: str) -> AnyNodeAttributes:
    """
    Factory function to create appropriate node attributes based on type.

    Args:
        node_type: Type of node (memory, config, telemetry)
        data: Raw attribute data
        created_by: Who is creating this node

    Returns:
        Appropriate typed node attributes instance

    Raises:
        ValueError: If node_type is not recognized
    """
    # Ensure required fields
    if "created_by" not in data:
        data["created_by"] = created_by

    # Map node types to attribute classes
    type_map: Dict[str, Type[AnyNodeAttributes]] = {
        "memory": MemoryNodeAttributes,
        "config": ConfigNodeAttributes,
        "telemetry": TelemetryNodeAttributes,
        "log": LogNodeAttributes,
    }

    # Get the appropriate class
    attr_class = type_map.get(node_type)
    if not attr_class:
        # Fall back to base attributes for unknown types
        return NodeAttributesBase(**data)

    # Type is inferred correctly from the typed dictionary
    return attr_class(**data)


__all__ = [
    "NodeAttributesBase",
    "MemoryNodeAttributes",
    "ConfigNodeAttributes",
    "TelemetryNodeAttributes",
    "LogNodeAttributes",
    "AnyNodeAttributes",
    "create_node_attributes",
]
