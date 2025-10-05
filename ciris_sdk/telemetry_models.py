"""
Telemetry-specific models for CIRIS SDK.

These models provide type-safe alternatives to Dict[str, Any] usage
in telemetry operations.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_serializer


# Resource Models
class ResourceUsage(BaseModel):
    """Current resource usage metrics."""

    cpu_percent: float = Field(..., description="CPU usage percentage")
    memory_mb: float = Field(..., description="Memory usage in MB")
    memory_percent: float = Field(..., description="Memory usage percentage")
    disk_gb: Optional[float] = Field(None, description="Disk usage in GB")
    disk_percent: Optional[float] = Field(None, description="Disk usage percentage")
    network_connections: Optional[int] = Field(None, description="Active network connections")
    open_files: Optional[int] = Field(None, description="Open file descriptors")
    threads: Optional[int] = Field(None, description="Active threads")

    model_config = ConfigDict(extra="allow")


class ResourceLimits(BaseModel):
    """Resource limits configuration."""

    max_memory_mb: Optional[float] = Field(None, description="Maximum memory in MB")
    max_cpu_percent: Optional[float] = Field(None, description="Maximum CPU percentage")
    max_disk_gb: Optional[float] = Field(None, description="Maximum disk in GB")
    max_connections: Optional[int] = Field(None, description="Maximum network connections")
    max_open_files: Optional[int] = Field(None, description="Maximum open files")

    model_config = ConfigDict(extra="allow")


class ResourceHealth(BaseModel):
    """Resource health status."""

    status: str = Field(..., description="Overall health status: healthy|degraded|critical")
    warnings: List[str] = Field(default_factory=list, description="Health warnings")

    # Optional fields for backward compatibility
    cpu_health: Optional[str] = Field(None, description="CPU health status")
    memory_health: Optional[str] = Field(None, description="Memory health status")
    disk_health: Optional[str] = Field(None, description="Disk health status")

    model_config = ConfigDict(extra="allow")


class ResourceHistoryPoint(BaseModel):
    """Single point in resource history."""

    timestamp: datetime = Field(..., description="Measurement timestamp")
    value: float = Field(..., description="Measured value")
    unit: Optional[str] = Field(None, description="Unit of measurement")

    @field_serializer("timestamp")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


# Metric Models
class MetricData(BaseModel):
    """Individual metric data."""

    name: str = Field(..., description="Metric name")
    value: float = Field(..., description="Current value")
    unit: Optional[str] = Field(None, description="Unit of measurement")
    timestamp: datetime = Field(..., description="Measurement time")
    tags: Dict[str, str] = Field(default_factory=dict, description="Metric tags")
    service: Optional[str] = Field(None, description="Service that produced metric")

    @field_serializer("timestamp")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class MetricAggregate(BaseModel):
    """Aggregated metric statistics."""

    min: float = Field(..., description="Minimum value")
    max: float = Field(..., description="Maximum value")
    avg: float = Field(..., description="Average value")
    sum: float = Field(..., description="Sum of values")
    count: int = Field(..., description="Number of data points")
    p50: Optional[float] = Field(None, description="50th percentile")
    p95: Optional[float] = Field(None, description="95th percentile")
    p99: Optional[float] = Field(None, description="99th percentile")


class MetricTrend(BaseModel):
    """Metric trend information."""

    direction: str = Field(..., description="Trend direction: up|down|stable")
    change_percent: float = Field(..., description="Percentage change")
    change_absolute: float = Field(..., description="Absolute change")
    period: str = Field(..., description="Period of comparison")


# Query Models
class QueryFilter(BaseModel):
    """Filter for telemetry queries."""

    field: str = Field(..., description="Field to filter on")
    operator: str = Field(..., description="Comparison operator: eq|ne|gt|lt|gte|lte|contains|in")
    value: Union[str, int, float, bool, List[Union[str, int, float]]] = Field(..., description="Filter value")

    model_config = ConfigDict(extra="forbid")


class QueryFilters(BaseModel):
    """Collection of query filters."""

    filters: List[QueryFilter] = Field(default_factory=list, description="List of filters")
    logic: str = Field(default="AND", description="Filter logic: AND|OR")

    model_config = ConfigDict(extra="forbid")


# Thought Models for Traces
class ThoughtData(BaseModel):
    """Thought information in traces."""

    thought_id: str = Field(..., description="Unique thought ID")
    content: str = Field(..., description="Thought content")
    handler: str = Field(..., description="Handler that processed thought")
    created_at: datetime = Field(..., description="Creation time")
    completed_at: Optional[datetime] = Field(None, description="Completion time")
    status: str = Field(..., description="Status: PENDING|PROCESSING|COMPLETED|FAILED")
    result: Optional[str] = Field(None, description="Processing result")

    @field_serializer("created_at", "completed_at")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


# Lineage Models
class LineageInfo(BaseModel):
    """Agent lineage information."""

    version: str = Field(..., description="Agent version")
    commit: Optional[str] = Field(None, description="Git commit hash")
    build_date: Optional[datetime] = Field(None, description="Build date")
    parent_version: Optional[str] = Field(None, description="Parent version")
    environment: Optional[str] = Field(None, description="Deployment environment")

    model_config = ConfigDict(extra="allow")

    @field_serializer("build_date")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


# Processor State Models
class ProcessorStateData(BaseModel):
    """Processor state information."""

    is_running: bool = Field(..., description="Whether processor is running")
    current_state: str = Field(..., description="Current cognitive state")
    current_round: int = Field(..., description="Current processing round")
    thoughts_pending: int = Field(..., description="Pending thoughts")
    thoughts_processing: int = Field(..., description="Currently processing thoughts")
    last_activity: Optional[datetime] = Field(None, description="Last activity time")
    idle_rounds: int = Field(..., description="Consecutive idle rounds")

    model_config = ConfigDict(extra="allow")

    @field_serializer("last_activity")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


# Configuration Models
class ConfigurationData(BaseModel):
    """System configuration snapshot."""

    profile: str = Field(..., description="Active configuration profile")
    environment: str = Field(..., description="Deployment environment")
    debug_mode: bool = Field(..., description="Debug mode enabled")
    log_level: str = Field(..., description="Logging level")
    features: Dict[str, bool] = Field(default_factory=dict, description="Feature flags")

    model_config = ConfigDict(extra="allow")


# Service Metadata Models
class ServiceMetadata(BaseModel):
    """Service metadata information."""

    version: Optional[str] = Field(None, description="Service version")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime")
    last_restart: Optional[datetime] = Field(None, description="Last restart time")
    restart_count: Optional[int] = Field(None, description="Number of restarts")
    error_count: Optional[int] = Field(None, description="Error count")

    model_config = ConfigDict(extra="allow")

    @field_serializer("last_restart")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


# Context Models
class InteractionContext(BaseModel):
    """Context for agent interactions."""

    channel_id: Optional[str] = Field(None, description="Channel identifier")
    user_id: Optional[str] = Field(None, description="User identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(extra="allow")


class AuditContext(BaseModel):
    """Context for audit entries."""

    ip_address: Optional[str] = Field(None, description="Client IP address")
    user_agent: Optional[str] = Field(None, description="User agent string")
    request_id: Optional[str] = Field(None, description="Request identifier")
    session_id: Optional[str] = Field(None, description="Session identifier")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(extra="allow")


class DeferralContext(BaseModel):
    """Context for deferrals."""

    original_thought_id: str = Field(..., description="Original thought ID")
    authority_id: str = Field(..., description="Authority that created deferral")
    priority: str = Field(..., description="Deferral priority")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")

    model_config = ConfigDict(extra="allow")


# Verification Models
class VerificationResult(BaseModel):
    """Result of verification operations."""

    is_valid: bool = Field(..., description="Whether verification passed")
    verified_at: datetime = Field(..., description="Verification timestamp")
    method: str = Field(..., description="Verification method used")
    details: Dict[str, str] = Field(default_factory=dict, description="Verification details")

    @field_serializer("verified_at")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None
