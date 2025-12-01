from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from .model_types import (
    AdapterConfig,
    AuditContext,
    BaseAttributes,
    ConfigAttributes,
    DeferralContext,
    MemoryAttributes,
    ProcessorResult,
    ProcessorStateInfo,
)
from .model_types import ServiceMetadata as ServiceMetadataTyped
from .model_types import (
    SystemConfiguration,
    TelemetryAttributes,
    ThoughtContent,
    VerificationResult,
)


class Message(BaseModel):
    id: str
    content: str
    author_id: str
    author_name: str
    channel_id: str
    timestamp: Optional[str] = None


# Memory Models
class GraphNode(BaseModel):
    """Base node for the graph - everything is a memory."""

    id: str = Field(..., description="Unique node identifier")
    type: str = Field(..., description="Type of node")
    scope: str = Field(..., description="Scope of the node")
    attributes: Union[BaseAttributes, MemoryAttributes, ConfigAttributes, TelemetryAttributes, Dict[str, Any]] = Field(
        ..., description="Node attributes"
    )
    version: int = Field(default=1, ge=1, description="Version number")
    updated_by: Optional[str] = Field(None, description="Who last updated")
    updated_at: Optional[datetime] = Field(None, description="When last updated")

    model_config = ConfigDict()

    @field_serializer("updated_at")
    def serialize_datetime(self, dt: Optional[datetime], _info: Any) -> Optional[str]:
        return dt.isoformat() if dt else None


class MemoryOpResult(BaseModel):
    """Result of memory operations."""

    success: bool = Field(..., description="Whether operation succeeded")
    node_id: Optional[str] = Field(None, description="ID of affected node")
    message: Optional[str] = Field(None, description="Operation message")
    error: Optional[str] = Field(None, description="Error message if failed")


class TimelineResponse(BaseModel):
    """Temporal view of memories."""

    memories: List[GraphNode] = Field(..., description="Memories in chronological order")
    buckets: Dict[str, int] = Field(..., description="Memory counts by time bucket")
    start_time: datetime = Field(..., description="Start of timeline range")
    end_time: datetime = Field(..., description="End of timeline range")
    total: int = Field(..., description="Total memories in range")


# Legacy models for backwards compatibility
class MemoryEntry(BaseModel):
    """Deprecated: Use GraphNode instead."""

    key: str
    value: Any


class MemoryScope(BaseModel):
    """Deprecated: Use GraphNode with scope field instead."""

    name: str
    entries: Optional[List[MemoryEntry]] = None


# Runtime Control Models
class ProcessorControlResponse(BaseModel):
    success: bool
    action: str
    timestamp: str
    result: Optional[ProcessorResult] = None
    error: Optional[str] = None


class AdapterInfo(BaseModel):
    adapter_id: str
    adapter_type: str
    is_running: bool
    health_status: str
    services_count: int
    loaded_at: str
    config_params: AdapterConfig


class AdapterLoadRequest(BaseModel):
    adapter_type: str
    adapter_id: Optional[str] = None
    config: Optional[AdapterConfig] = Field(
        default_factory=lambda: AdapterConfig(adapter_type="unknown", connection_params={}, feature_flags={}, limits={})
    )
    auto_start: bool = True


class AdapterOperationResponse(BaseModel):
    success: bool
    adapter_id: str
    adapter_type: str
    services_registered: Optional[int] = None
    services_unregistered: Optional[int] = None
    loaded_at: Optional[str] = None
    was_running: Optional[bool] = None
    error: Optional[str] = None


class RuntimeStatus(BaseModel):
    processor_status: str
    active_adapters: List[str]
    loaded_adapters: List[str]
    current_profile: str
    config_scope: str
    uptime_seconds: float
    last_config_change: Optional[str] = None
    health_status: str = "healthy"


class ConfigOperationResponse(BaseModel):
    success: bool
    operation: str
    timestamp: str
    path: Optional[str] = None
    old_value: Optional[Any] = None
    new_value: Optional[Any] = None
    scope: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    key: Optional[str] = None  # Added for config operations


class ConfigValue(BaseModel):
    """Represents a single configuration value."""

    key: str
    value: Any
    description: Optional[str] = None
    sensitive: bool = False
    last_modified: Optional[str] = None
    modified_by: Optional[str] = None


class ConfigItem(BaseModel):
    """Represents a configuration item in list responses."""

    key: str
    value: Any
    description: Optional[str] = None
    sensitive: bool = False
    redacted: bool = False  # True if value was redacted due to permissions
    last_modified: Optional[str] = None
    modified_by: Optional[str] = None


# System Telemetry Models
class SystemHealth(BaseModel):
    overall_health: str
    adapters_healthy: int
    services_healthy: int
    processor_status: str
    memory_usage_mb: float
    uptime_seconds: float


class TelemetrySnapshot(BaseModel):
    timestamp: str
    schema_version: str
    runtime_uptime_seconds: float
    memory_usage_mb: float
    cpu_usage_percent: float
    overall_health: str
    adapters: List[AdapterInfo]
    processor_state: ProcessorStateInfo
    configuration: SystemConfiguration


class ServiceInfo(BaseModel):
    name: str
    service_type: str
    handler: Optional[str] = None
    priority: str
    capabilities: List[str]
    status: str
    circuit_breaker_state: str
    metadata: ServiceMetadataTyped


class ProcessorState(BaseModel):
    is_running: bool
    current_round: int
    thoughts_pending: int
    thoughts_processing: int
    thoughts_completed_24h: int
    last_activity: Optional[str] = None
    processor_mode: str
    idle_rounds: int


class MetricRecord(BaseModel):
    metric_name: str
    value: float
    tags: Dict[str, str] = {}
    timestamp: str


class DeferralInfo(BaseModel):
    deferral_id: str
    thought_id: str
    reason: str
    context: DeferralContext
    status: str
    created_at: str
    resolved_at: Optional[str] = None


# Audit Models
class AuditEntryResponse(BaseModel):
    """Audit entry response with formatted fields."""

    id: str
    action: str
    actor: str
    timestamp: datetime
    context: AuditContext
    signature: Optional[str] = None
    hash_chain: Optional[str] = None


class AuditEntryDetailResponse(BaseModel):
    """Detailed audit entry with verification info."""

    entry: AuditEntryResponse
    verification: Optional[VerificationResult] = None
    chain_position: Optional[int] = None
    next_entry_id: Optional[str] = None
    previous_entry_id: Optional[str] = None


class AuditEntriesResponse(BaseModel):
    """List of audit entries with cursor pagination."""

    entries: List[AuditEntryResponse]
    cursor: Optional[str] = None
    has_more: bool = False
    total_matches: Optional[int] = None  # Only if requested


class AuditExportResponse(BaseModel):
    """Audit export response."""

    format: str
    total_entries: int
    export_url: Optional[str] = None
    export_data: Optional[str] = None


# Telemetry Models
class TelemetryMetricData(BaseModel):
    """Single metric data point."""

    timestamp: datetime
    value: float
    tags: Dict[str, str] = {}


class TelemetryDetailedMetric(BaseModel):
    """Detailed metric information."""

    name: str
    current_value: float
    unit: Optional[str] = None
    trend: str = "stable"  # up|down|stable
    hourly_average: float = 0.0
    daily_average: float = 0.0
    by_service: Dict[str, float] = {}
    recent_data: List[TelemetryMetricData] = []


class TelemetrySystemOverview(BaseModel):
    """System overview combining all observability data."""

    # Core metrics
    uptime_seconds: float
    cognitive_state: str
    messages_processed_24h: int = 0
    thoughts_processed_24h: int = 0
    tasks_completed_24h: int = 0
    errors_24h: int = 0

    # Resource usage
    tokens_per_hour: float = 0.0
    cost_per_hour_cents: float = 0.0
    carbon_per_hour_grams: float = 0.0
    memory_mb: float = 0.0
    cpu_percent: float = 0.0

    # Service health
    healthy_services: int = 0
    degraded_services: int = 0
    error_rate_percent: float = 0.0

    # Agent activity
    current_task: Optional[str] = None
    reasoning_depth: int = 0
    active_deferrals: int = 0
    recent_incidents: int = 0


class TelemetryReasoningTrace(BaseModel):
    """Reasoning trace information."""

    trace_id: str
    task_id: Optional[str] = None
    task_description: Optional[str] = None
    start_time: datetime
    duration_ms: float
    thought_count: int = 0
    decision_count: int = 0
    reasoning_depth: int = 0
    thoughts: List[ThoughtContent] = []
    outcome: Optional[str] = None


class TelemetryLogEntry(BaseModel):
    """System log entry."""

    timestamp: datetime
    level: str  # DEBUG|INFO|WARNING|ERROR|CRITICAL
    service: str
    message: str
    context: Dict[str, str] = {}
    trace_id: Optional[str] = None
