"""
System route schemas - Request/Response models for system endpoints.

This module consolidates all Pydantic models used by system routes.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_serializer

from ciris_engine.schemas.api.telemetry import ServiceMetrics, TimeSyncStatus
from ciris_engine.schemas.runtime.manifest import ConfigurationStep
from ciris_engine.schemas.services.resources_core import ResourceBudget, ResourceSnapshot
from ciris_engine.schemas.types import JSONDict
from ciris_engine.utils.serialization import serialize_timestamp

from ...constants import DESC_CURRENT_COGNITIVE_STATE, DESC_HUMAN_READABLE_STATUS


# Health & Time Response Models


class SystemHealthResponse(BaseModel):
    """Overall system health status."""

    status: str = Field(..., description="Overall health status (healthy/degraded/critical)")
    version: str = Field(..., description="System version")
    uptime_seconds: float = Field(..., description="System uptime in seconds")
    services: Dict[str, Dict[str, int]] = Field(..., description="Service health summary")
    initialization_complete: bool = Field(..., description="Whether system initialization is complete")
    cognitive_state: Optional[str] = Field(None, description="Current cognitive state if available")
    timestamp: datetime = Field(..., description="Current server time")

    @field_serializer("timestamp")
    def serialize_ts(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return serialize_timestamp(timestamp, _info)


class SystemTimeResponse(BaseModel):
    """System and agent time information."""

    system_time: datetime = Field(..., description="Host system time (OS time)")
    agent_time: datetime = Field(..., description="Agent's TimeService time")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    time_sync: TimeSyncStatus = Field(..., description="Time synchronization status")

    @field_serializer("system_time", "agent_time")
    def serialize_times(self, dt: datetime, _info: Any) -> Optional[str]:
        return serialize_timestamp(dt, _info)


# Resource Response Models


class ResourceUsageResponse(BaseModel):
    """System resource usage and limits."""

    current_usage: ResourceSnapshot = Field(..., description="Current resource usage")
    limits: ResourceBudget = Field(..., description="Configured resource limits")
    health_status: str = Field(..., description="Resource health (healthy/warning/critical)")
    warnings: List[str] = Field(default_factory=list, description="Resource warnings")
    critical: List[str] = Field(default_factory=list, description="Critical resource issues")


# Runtime Control Models


class RuntimeAction(BaseModel):
    """Runtime control action request."""

    reason: Optional[str] = Field(None, description="Reason for the action")


class StateTransitionRequest(BaseModel):
    """Request to transition cognitive state."""

    target_state: str = Field(..., description="Target cognitive state (WORK, DREAM, PLAY, SOLITUDE)")
    reason: Optional[str] = Field(None, description="Reason for the transition")


class StateTransitionResponse(BaseModel):
    """Response to cognitive state transition request."""

    success: bool = Field(..., description="Whether transition was initiated")
    message: str = Field(..., description="Human-readable status message")
    previous_state: Optional[str] = Field(None, description="State before transition")
    current_state: str = Field(..., description="Current cognitive state after transition attempt")


class RuntimeControlResponse(BaseModel):
    """Response to runtime control actions."""

    success: bool = Field(..., description="Whether action succeeded")
    message: str = Field(..., description=DESC_HUMAN_READABLE_STATUS)
    processor_state: str = Field(..., description="Current processor state")
    cognitive_state: Optional[str] = Field(None, description=DESC_CURRENT_COGNITIVE_STATE)
    queue_depth: int = Field(0, description="Number of items in processing queue")

    # Enhanced pause response fields for UI display
    current_step: Optional[str] = Field(None, description="Current pipeline step when paused")
    current_step_schema: Optional[JSONDict] = Field(None, description="Full schema object for current step")
    pipeline_state: Optional[JSONDict] = Field(None, description="Complete pipeline state when paused")


# Services Response Models


class ServiceStatus(BaseModel):
    """Individual service status."""

    name: str = Field(..., description="Service name")
    type: str = Field(..., description="Service type")
    healthy: bool = Field(..., description="Whether service is healthy")
    available: bool = Field(..., description="Whether service is available")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime if tracked")
    metrics: ServiceMetrics = Field(
        default_factory=lambda: ServiceMetrics(
            uptime_seconds=None,
            requests_handled=None,
            error_count=None,
            avg_response_time_ms=None,
            memory_mb=None,
            custom_metrics=None,
        ),
        description="Service-specific metrics",
    )


class ServicesStatusResponse(BaseModel):
    """Status of all system services."""

    services: List[ServiceStatus] = Field(..., description="List of service statuses")
    total_services: int = Field(..., description="Total number of services")
    healthy_services: int = Field(..., description="Number of healthy services")
    timestamp: datetime = Field(..., description="When status was collected")

    @field_serializer("timestamp")
    def serialize_ts(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return serialize_timestamp(timestamp, _info)


# Shutdown Models


class ShutdownRequest(BaseModel):
    """Graceful shutdown request."""

    reason: str = Field(..., description="Reason for shutdown")
    force: bool = Field(False, description="Force immediate shutdown")
    confirm: bool = Field(..., description="Confirmation flag (must be true)")


class ShutdownResponse(BaseModel):
    """Response to shutdown request."""

    status: str = Field(..., description="Shutdown status")
    message: str = Field(..., description=DESC_HUMAN_READABLE_STATUS)
    shutdown_initiated: bool = Field(..., description="Whether shutdown was initiated")
    timestamp: datetime = Field(..., description="When shutdown was initiated")

    @field_serializer("timestamp")
    def serialize_ts(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return serialize_timestamp(timestamp, _info)


# Adapter Management Models


class AdapterActionRequest(BaseModel):
    """Request for adapter operations."""

    config: Optional[Any] = Field(None, description="Adapter configuration")
    auto_start: bool = Field(True, description="Whether to auto-start the adapter")
    force: bool = Field(False, description="Force the operation")


# Adapter Configuration Workflow Models


class ConfigStepInfo(BaseModel):
    """Information about a configuration step."""

    step_id: str = Field(..., description="Unique step identifier")
    step_type: str = Field(..., description="Type of step (discovery, oauth, select, confirm)")
    title: str = Field(..., description="Step title")
    description: str = Field(..., description="Step description")
    optional: bool = Field(False, description="Whether this step is optional")


class ConfigurableAdapterInfo(BaseModel):
    """Information about an adapter that supports interactive configuration."""

    adapter_type: str = Field(..., description="Type identifier for the adapter")
    name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="Description of the adapter")
    workflow_type: str = Field(..., description="Type of configuration workflow")
    step_count: int = Field(..., description="Number of steps in the configuration workflow")
    requires_oauth: bool = Field(False, description="Whether this adapter requires OAuth authentication")
    steps: List[ConfigStepInfo] = Field(default_factory=list, description="Configuration steps")


class ConfigurableAdaptersResponse(BaseModel):
    """Response containing list of configurable adapters."""

    adapters: List[ConfigurableAdapterInfo] = Field(..., description="List of configurable adapters")
    total_count: int = Field(..., description="Total number of configurable adapters")


class ConfigurationSessionResponse(BaseModel):
    """Response for starting a configuration session."""

    session_id: str = Field(..., description="Unique session identifier")
    adapter_type: str = Field(..., description="Adapter being configured")
    status: str = Field(..., description="Current session status")
    current_step_index: int = Field(..., description="Index of current step")
    current_step: Optional[ConfigurationStep] = Field(None, description="Current step information")
    total_steps: int = Field(..., description="Total number of steps in workflow")
    created_at: datetime = Field(..., description="When session was created")

    @field_serializer("created_at")
    def serialize_ts(self, created_at: datetime, _info: Any) -> Optional[str]:
        return serialize_timestamp(created_at, _info)


class ConfigurationStatusResponse(BaseModel):
    """Response for configuration session status."""

    session_id: str = Field(..., description="Session identifier")
    adapter_type: str = Field(..., description="Adapter being configured")
    status: str = Field(..., description="Current session status")
    current_step_index: int = Field(..., description="Index of current step")
    current_step: Optional[ConfigurationStep] = Field(None, description="Current step information")
    total_steps: int = Field(..., description="Total number of steps in workflow")
    collected_config: Dict[str, Any] = Field(..., description="Configuration collected so far")
    created_at: datetime = Field(..., description="When session was created")
    updated_at: datetime = Field(..., description="When session was last updated")

    @field_serializer("created_at", "updated_at")
    def serialize_times(self, dt: datetime, _info: Any) -> Optional[str]:
        return serialize_timestamp(dt, _info)


class StepExecutionRequest(BaseModel):
    """Request to execute a configuration step."""

    step_data: Dict[str, Any] = Field(default_factory=dict, description="Data for step execution")


class StepExecutionResponse(BaseModel):
    """Response from executing a configuration step."""

    step_id: str = Field(..., description="ID of the executed step")
    success: bool = Field(..., description="Whether step execution succeeded")
    data: Dict[str, Any] = Field(default_factory=dict, description="Data returned by the step")
    next_step_index: Optional[int] = Field(None, description="Index of next step to execute")
    error: Optional[str] = Field(None, description="Error message if execution failed")
    awaiting_callback: bool = Field(False, description="Whether step is waiting for external callback")


class ConfigurationCompleteRequest(BaseModel):
    """Request body for completing a configuration session."""

    persist: bool = Field(default=False, description="If True, persist configuration for automatic loading on startup")


class ConfigurationCompleteResponse(BaseModel):
    """Response from completing a configuration session."""

    success: bool = Field(..., description="Whether configuration was applied successfully")
    adapter_type: str = Field(..., description="Adapter that was configured")
    message: str = Field(..., description="Human-readable result message")
    applied_config: Dict[str, Any] = Field(default_factory=dict, description="Configuration that was applied")
    persisted: bool = Field(default=False, description="Whether configuration was persisted for startup")


# Persisted Configurations Models


class PersistedConfigsResponse(BaseModel):
    """Response for persisted adapter configurations."""

    persisted_configs: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Map of adapter_type to configuration data",
    )
    count: int = Field(..., description="Number of persisted configurations")


class RemovePersistedResponse(BaseModel):
    """Response for removing a persisted configuration."""

    success: bool = Field(..., description="Whether the removal succeeded")
    adapter_type: str = Field(..., description="Adapter type that was removed")
    message: str = Field(..., description="Status message")


# Tool Models


class ToolInfoResponse(BaseModel):
    """Tool information response with provider details."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    provider: str = Field(..., description="Provider service name")
    parameters: Optional[Any] = Field(None, description="Tool parameter schema")
    category: str = Field("general", description="Tool category")
    cost: float = Field(0.0, description="Cost to execute the tool")
    when_to_use: Optional[str] = Field(None, description="Guidance on when to use the tool")
