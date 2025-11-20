"""
Runtime service schemas for runtime control operations.

Provides typed schemas for all runtime control service responses.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.adapters.tools import ToolInfo
from ciris_engine.schemas.services.runtime_control import PipelineState, StepResultData
from ciris_engine.schemas.types import ConfigDict, JSONDict


class AdapterStatus(str, Enum):
    """Adapter operational status."""

    ACTIVE = "active"
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    STARTING = "starting"
    STOPPING = "stopping"


class ProcessorStatus(str, Enum):
    """Processor operational status."""

    RUNNING = "running"
    PAUSED = "paused"
    STOPPED = "stopped"
    ERROR = "error"


class ConfigScope(str, Enum):
    """Configuration scope levels."""

    GLOBAL = "global"
    ADAPTER = "adapter"
    PROCESSOR = "processor"
    SERVICE = "service"


class ConfigValidationLevel(str, Enum):
    """Configuration validation levels."""

    SYNTAX = "syntax"
    SCHEMA = "schema"
    SEMANTIC = "semantic"
    FULL = "full"


class ProcessorQueueStatus(BaseModel):
    """Status of a processor queue."""

    processor_name: str = Field(..., description="Processor name")
    queue_size: int = Field(..., description="Current queue size")
    max_size: int = Field(..., description="Maximum queue size")
    processing_rate: float = Field(..., description="Messages per second")
    average_latency_ms: float = Field(..., description="Average processing latency")
    oldest_message_age_seconds: Optional[float] = Field(None, description="Age of oldest message")


class AdapterInfo(BaseModel):
    """Information about an adapter."""

    adapter_id: str = Field(..., description="Adapter identifier")
    adapter_type: str = Field(..., description="Type of adapter")
    status: AdapterStatus = Field(..., description="Current status")
    started_at: Optional[datetime] = Field(None, description="Start time")
    messages_processed: int = Field(0, description="Total messages processed")
    error_count: int = Field(0, description="Total errors")
    last_error: Optional[str] = Field(None, description="Last error message")
    tools: Optional[List[ToolInfo]] = Field(None, description="Tools provided by adapter")


class AdapterOperationResult(BaseModel):
    """Result of an adapter operation."""

    success: bool = Field(..., description="Whether operation succeeded")
    adapter_id: str = Field(..., description="Adapter identifier")
    adapter_type: str = Field(..., description="Type of adapter")
    operation: str = Field(..., description="Operation performed")
    error: Optional[str] = Field(None, description="Error message if failed")


class ConfigBackup(BaseModel):
    """Configuration backup information."""

    backup_id: str = Field(..., description="Backup identifier")
    created_at: datetime = Field(..., description="When backup was created")
    config_version: str = Field(..., description="Config version backed up")
    size_bytes: int = Field(..., description="Backup size")
    path: str = Field(..., description="Backup file path")
    description: Optional[str] = Field(None, description="Backup description")


class ServiceRegistryInfo(BaseModel):
    """Service registry information."""

    total_services: int = Field(..., description="Total registered services")
    services_by_type: Dict[str, int] = Field(..., description="Count by service type")
    handlers: Dict[str, List[str]] = Field(..., description="Handlers and their services")
    healthy_services: int = Field(..., description="Number of healthy services")
    circuit_breaker_states: Dict[str, str] = Field(..., description="Circuit breaker states")


class CircuitBreakerResetResult(BaseModel):
    """Result of circuit breaker reset operation."""

    success: bool = Field(..., description="Whether reset succeeded")
    reset_count: int = Field(..., description="Number of breakers reset")
    reset_services: List[str] = Field(..., description="Services that were reset")
    errors: List[str] = Field(default_factory=list, description="Any errors encountered")


class ServiceHealthStatus(BaseModel):
    """Health status of services."""

    overall_health: str = Field(..., description="Overall health: healthy, degraded, unhealthy")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    healthy_services: int = Field(..., description="Number of healthy services")
    unhealthy_services: int = Field(..., description="Number of unhealthy services")
    service_details: Dict[str, ConfigDict] = Field(..., description="Per-service health details")
    recommendations: List[str] = Field(default_factory=list, description="Health recommendations")


class ServiceSelectionExplanation(BaseModel):
    """Explanation of service selection logic."""

    overview: str = Field(..., description="Overview of selection logic")
    priority_groups: Dict[int, str] = Field(..., description="Priority group explanations")
    priorities: Optional[Dict[str, ConfigDict]] = Field(
        default_factory=lambda: {}, description="Priority level details"
    )
    selection_strategies: Dict[str, str] = Field(..., description="Strategy explanations")
    selection_flow: Optional[List[str]] = Field(default_factory=lambda: [], description="Selection flow steps")
    circuit_breaker_info: Optional[ConfigDict] = Field(
        default_factory=lambda: {}, description="Circuit breaker information"
    )
    examples: List[ConfigDict] = Field(..., description="Example scenarios")
    configuration_tips: List[str] = Field(..., description="Configuration recommendations")


class RuntimeEvent(BaseModel):
    """Runtime event notification."""

    event_type: str = Field(..., description="Type of event")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: str = Field(..., description="Event source")
    details: ConfigDict = Field(..., description="Event details")
    severity: str = Field("info", description="Event severity")


class ConfigReloadResult(BaseModel):
    """Result of configuration reload."""

    success: bool = Field(..., description="Whether reload succeeded")
    config_version: str = Field(..., description="New config version")
    changes_applied: int = Field(..., description="Number of changes applied")
    warnings: List[str] = Field(default_factory=list, description="Configuration warnings")
    error: Optional[str] = Field(None, description="Error if reload failed")


class ProcessorControlResponse(BaseModel):
    """Response from processor control operations."""

    success: bool = Field(..., description="Whether operation succeeded")
    processor_name: str = Field(..., description="Processor name")
    operation: str = Field(..., description="Operation performed")
    new_status: ProcessorStatus = Field(..., description="New processor status")
    error: Optional[str] = Field(None, description="Error message if failed")

    # H3ERE step data for single-step operations
    step_point: Optional[str] = Field(None, description="H3ERE step point executed")
    step_results: Optional[List[StepResultData]] = Field(None, description="Step results organized by round and task")
    thoughts_processed: Optional[int] = Field(None, description="Number of thoughts processed")
    processing_time_ms: Optional[float] = Field(None, description="Processing time in milliseconds")
    pipeline_state: Optional[PipelineState] = Field(None, description="Current pipeline state")
    current_round: Optional[int] = Field(None, description="Current processing round")
    pipeline_empty: Optional[bool] = Field(None, description="Whether pipeline is empty")


class AdapterOperationResponse(BaseModel):
    """Response from adapter operations."""

    success: bool = Field(..., description="Whether operation succeeded")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    adapter_id: str = Field(..., description="Adapter identifier")
    adapter_type: str = Field(..., description="Adapter type")
    status: AdapterStatus = Field(..., description="Current adapter status")
    error: Optional[str] = Field(None, description="Error message if failed")


class RuntimeStatusResponse(BaseModel):
    """Overall runtime status response."""

    is_running: bool = Field(..., description="Whether runtime is active")
    uptime_seconds: float = Field(..., description="Runtime uptime")
    processor_count: int = Field(..., description="Number of processors")
    adapter_count: int = Field(..., description="Number of adapters")
    total_messages_processed: int = Field(..., description="Total messages processed")
    current_load: float = Field(..., description="Current system load")
    processor_status: ProcessorStatus = Field(
        ProcessorStatus.RUNNING, description="Current processor operational status"
    )
    cognitive_state: Optional[str] = Field(None, description="Current cognitive state (AgentState)")
    queue_depth: int = Field(0, description="Number of items in processing queue")


class RuntimeStateSnapshot(BaseModel):
    """Complete runtime state snapshot."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    runtime_status: RuntimeStatusResponse = Field(..., description="Runtime status")
    processors: List[ProcessorQueueStatus] = Field(..., description="Processor statuses")
    adapters: List[AdapterInfo] = Field(..., description="Adapter information")
    config_version: str = Field(..., description="Current config version")
    health_summary: ServiceHealthStatus = Field(..., description="Service health summary")


class ConfigSnapshot(BaseModel):
    """Configuration snapshot for runtime control."""

    configs: ConfigDict = Field(..., description="Configuration key-value pairs")
    version: str = Field(..., description="Configuration version")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sensitive_keys: List[str] = Field(default_factory=list, description="Keys containing sensitive data")
    metadata: JSONDict = Field(default_factory=dict, description="Additional metadata")


class ConfigOperationResponse(BaseModel):
    """Response from configuration operations."""

    success: bool = Field(..., description="Whether operation succeeded")
    operation: str = Field(..., description="Operation performed")
    config_path: Optional[str] = Field(None, description="Configuration path")
    details: ConfigDict = Field(default_factory=dict, description="Operation details")
    error: Optional[str] = Field(None, description="Error message if failed")


class ConfigValidationResponse(BaseModel):
    """Configuration validation response."""

    valid: bool = Field(..., description="Whether config is valid")
    validation_level: ConfigValidationLevel = Field(..., description="Level of validation")
    errors: List[str] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    suggestions: List[str] = Field(default_factory=list, description="Improvement suggestions")


class ConfigBackupResponse(BaseModel):
    """Configuration backup response."""

    success: bool = Field(..., description="Whether backup succeeded")
    backup_id: str = Field(..., description="Backup identifier")
    backup_path: str = Field(..., description="Where backup was saved")
    size_bytes: int = Field(..., description="Backup size")
    error: Optional[str] = Field(None, description="Error message if failed")
