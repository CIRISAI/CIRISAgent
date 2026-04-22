"""
System management endpoints for CIRIS API v3.0 (Simplified).

Consolidates health, time, resources, runtime control, services, and shutdown
into a unified system operations interface.
"""

import asyncio
import html
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, ValidationError, field_serializer
from starlette.responses import JSONResponse

from ciris_engine.constants import CIRIS_VERSION
from ciris_engine.logic.utils.path_resolution import get_package_root
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolParameterSchema
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.api.telemetry import ServiceMetrics, TimeSyncStatus
from ciris_engine.schemas.runtime.adapter_management import (
    AdapterConfig,
    AdapterListResponse,
    AdapterMetrics,
    AdapterOperationResult,
    ModuleConfigParameter,
    ModuleTypeInfo,
    ModuleTypesResponse,
)
from ciris_engine.schemas.runtime.adapter_management import RuntimeAdapterStatus as AdapterStatusSchema
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.manifest import ConfigurationStep
from ciris_engine.schemas.services.core.runtime import ProcessorStatus
from ciris_engine.schemas.services.resources_core import ResourceBudget, ResourceSnapshot
from ciris_engine.schemas.types import JSONDict
from ciris_engine.utils.serialization import serialize_timestamp

from ..constants import (
    DESC_CURRENT_COGNITIVE_STATE,
    DESC_HUMAN_READABLE_STATUS,
    ERROR_RESOURCE_MONITOR_NOT_AVAILABLE,
    ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE,
    ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE,
    ERROR_TIME_SERVICE_NOT_AVAILABLE,
)
from ..dependencies.auth import AuthContext, require_admin, require_observer

router = APIRouter(prefix="/system", tags=["system"])

# Capability constants (avoid duplication)
CAP_COMM_SEND_MESSAGE = "communication:send_message"
CAP_COMM_FETCH_MESSAGES = "communication:fetch_messages"
MANIFEST_FILENAME = "manifest.json"
ERROR_ADAPTER_CONFIG_SERVICE_NOT_AVAILABLE = "Adapter configuration service not available"

# Common communication capabilities for adapters
COMM_CAPABILITIES = [CAP_COMM_SEND_MESSAGE, CAP_COMM_FETCH_MESSAGES]
logger = logging.getLogger(__name__)


# Request/Response Models


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


class ResourceUsageResponse(BaseModel):
    """System resource usage and limits."""

    current_usage: ResourceSnapshot = Field(..., description="Current resource usage")
    limits: ResourceBudget = Field(..., description="Configured resource limits")
    health_status: str = Field(..., description="Resource health (healthy/warning/critical)")
    warnings: List[str] = Field(default_factory=list, description="Resource warnings")
    critical: List[str] = Field(default_factory=list, description="Critical resource issues")


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


class AdapterActionRequest(BaseModel):
    """Request for adapter operations."""

    config: Optional[AdapterConfig] = Field(None, description="Adapter configuration")
    auto_start: bool = Field(True, description="Whether to auto-start the adapter")
    force: bool = Field(False, description="Force the operation")


class ToolInfoResponse(BaseModel):
    """Tool information response with provider details."""

    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    provider: str = Field(..., description="Provider service name")
    parameters: Optional[ToolParameterSchema] = Field(None, description="Tool parameter schema")
    category: str = Field("general", description="Tool category")
    cost: float = Field(0.0, description="Cost to execute the tool")
    when_to_use: Optional[str] = Field(None, description="Guidance on when to use the tool")


# Adapter Configuration Response Models


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


# Endpoints


@router.get("/health", response_model=SuccessResponse[SystemHealthResponse])
async def get_system_health(request: Request) -> SuccessResponse[SystemHealthResponse]:
    """
    Overall system health.

    Returns comprehensive system health including service status,
    initialization state, and current cognitive state.
    """
    # Get basic system info
    uptime_seconds = _get_system_uptime(request)
    current_time = _get_current_time(request)
    cognitive_state = _get_cognitive_state_safe(request)
    init_complete = _check_initialization_status(request)

    # Collect service health data
    services = await _collect_service_health(request)
    processor_healthy = await _check_processor_health(request)

    # Determine overall system status
    status = _determine_overall_status(init_complete, processor_healthy, services)

    response = SystemHealthResponse(
        status=status,
        version=CIRIS_VERSION,
        uptime_seconds=uptime_seconds,
        services=services,
        initialization_complete=init_complete,
        cognitive_state=cognitive_state,
        timestamp=current_time,
    )

    return SuccessResponse(data=response)


@router.get("/time", response_model=SuccessResponse[SystemTimeResponse])
async def get_system_time(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[SystemTimeResponse]:
    """
    System time information.

    Returns both system time (host OS) and agent time (TimeService),
    along with synchronization status.
    """
    # Get time service
    time_service: Optional[TimeServiceProtocol] = getattr(request.app.state, "time_service", None)
    if not time_service:
        raise HTTPException(status_code=503, detail=ERROR_TIME_SERVICE_NOT_AVAILABLE)

    try:
        # Get system time (actual OS time)
        system_time = datetime.now(timezone.utc)

        # Get agent time (from TimeService)
        agent_time = time_service.now()

        # Calculate uptime
        start_time = getattr(time_service, "_start_time", None)
        if not start_time:
            start_time = agent_time
            uptime_seconds = 0.0
        else:
            uptime_seconds = (agent_time - start_time).total_seconds()

        # Calculate time sync status
        is_mocked = getattr(time_service, "_mock_time", None) is not None
        time_diff_ms = (agent_time - system_time).total_seconds() * 1000

        time_sync = TimeSyncStatus(
            synchronized=not is_mocked and abs(time_diff_ms) < 1000,  # Within 1 second
            drift_ms=time_diff_ms,
            last_sync=getattr(time_service, "_last_sync", agent_time),
            sync_source="mock" if is_mocked else "system",
        )

        response = SystemTimeResponse(
            system_time=system_time, agent_time=agent_time, uptime_seconds=uptime_seconds, time_sync=time_sync
        )

        return SuccessResponse(data=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get time information: {str(e)}")


@router.get("/resources", response_model=SuccessResponse[ResourceUsageResponse])
async def get_resource_usage(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ResourceUsageResponse]:
    """
    Resource usage and limits.

    Returns current resource consumption, configured limits,
    and health status.
    """
    resource_monitor = getattr(request.app.state, "resource_monitor", None)
    if not resource_monitor:
        raise HTTPException(status_code=503, detail=ERROR_RESOURCE_MONITOR_NOT_AVAILABLE)

    try:
        # Get current snapshot and budget
        snapshot = resource_monitor.snapshot
        budget = resource_monitor.budget

        # Determine health status
        if snapshot.critical:
            health_status = "critical"
        elif snapshot.warnings:
            health_status = "warning"
        else:
            health_status = "healthy"

        response = ResourceUsageResponse(
            current_usage=snapshot,
            limits=budget,
            health_status=health_status,
            warnings=snapshot.warnings,
            critical=snapshot.critical,
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"Error getting resource usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_runtime_control_service(request: Request) -> Any:
    """Get runtime control service from request, trying main service first."""
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)
    return runtime_control


def _validate_runtime_action(action: str) -> None:
    """Validate the runtime control action."""
    valid_actions = ["pause", "resume", "state"]
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}")


async def _execute_pause_action(runtime_control: Any, body: RuntimeAction) -> bool:
    """Execute pause action and return success status."""
    # Check if the service expects a reason parameter (API runtime control) or not (main runtime control)
    import inspect

    sig = inspect.signature(runtime_control.pause_processing)
    if len(sig.parameters) > 0:  # API runtime control service
        success: bool = await runtime_control.pause_processing(body.reason or "API request")
    else:  # Main runtime control service
        control_response = await runtime_control.pause_processing()
        success = control_response.success
    return success


def _extract_pipeline_state_info(
    request: Request,
) -> tuple[Optional[str], Optional[JSONDict], Optional[JSONDict]]:
    """
    Extract pipeline state information for UI display.

    Returns:
        Tuple of (current_step, current_step_schema, pipeline_state)
    """
    current_step: Optional[str] = None
    current_step_schema: Optional[JSONDict] = None
    pipeline_state: Optional[JSONDict] = None

    try:
        # Try to get current pipeline state from the runtime
        runtime = getattr(request.app.state, "runtime", None)
        if runtime and hasattr(runtime, "agent_processor") and runtime.agent_processor:
            if (
                hasattr(runtime.agent_processor, "_pipeline_controller")
                and runtime.agent_processor._pipeline_controller
            ):
                pipeline_controller = runtime.agent_processor._pipeline_controller

                # Get current pipeline state
                try:
                    pipeline_state_obj = pipeline_controller.get_current_state()
                    if pipeline_state_obj and hasattr(pipeline_state_obj, "current_step"):
                        current_step = pipeline_state_obj.current_step
                    if pipeline_state_obj and hasattr(pipeline_state_obj, "pipeline_state"):
                        pipeline_state = pipeline_state_obj.pipeline_state
                except Exception as e:
                    logger.debug(f"Could not get current step from pipeline: {e}")

                # Get the full step schema/metadata
                if current_step:
                    try:
                        # Get step schema - this would include all step metadata
                        current_step_schema = {
                            "step_point": current_step,
                            "description": f"System paused at step: {current_step}",
                            "timestamp": datetime.now().isoformat(),
                            "can_single_step": True,
                            "next_actions": ["single_step", "resume"],
                        }
                    except Exception as e:
                        logger.debug(f"Could not get step schema: {e}")
    except Exception as e:
        logger.debug(f"Could not get pipeline information: {e}")

    return current_step, current_step_schema, pipeline_state


def _create_pause_response(
    success: bool,
    current_step: Optional[str],
    current_step_schema: Optional[JSONDict],
    pipeline_state: Optional[JSONDict],
) -> RuntimeControlResponse:
    """Create pause action response."""
    # Create clear message based on success state
    if success:
        step_suffix = f" at step: {current_step}" if current_step else ""
        message = f"Processing paused{step_suffix}"
    else:
        message = "Already paused"

    result = RuntimeControlResponse(
        success=success,
        message=message,
        processor_state="paused" if success else "unknown",
        cognitive_state="UNKNOWN",
    )

    # Add current step information to response for UI
    if current_step:
        result.current_step = current_step
        result.current_step_schema = current_step_schema
        result.pipeline_state = pipeline_state

    return result


async def _execute_resume_action(runtime_control: Any) -> RuntimeControlResponse:
    """Execute resume action."""
    # Check if the service returns a control response or just boolean
    resume_result = await runtime_control.resume_processing()
    if hasattr(resume_result, "success"):  # Main runtime control service
        success = resume_result.success
    else:  # API runtime control service
        success = resume_result

    return RuntimeControlResponse(
        success=success,
        message="Processing resumed" if success else "Not paused",
        processor_state="active" if success else "unknown",
        cognitive_state="UNKNOWN",
        queue_depth=0,
    )


async def _execute_state_action(runtime_control: Any) -> RuntimeControlResponse:
    """Execute state query action."""
    # Get current state without changing it
    status = await runtime_control.get_runtime_status()
    # Get queue depth from the same source as queue endpoint
    queue_status = await runtime_control.get_processor_queue_status()
    actual_queue_depth = queue_status.queue_size if queue_status else 0

    return RuntimeControlResponse(
        success=True,
        message="Current runtime state retrieved",
        processor_state="paused" if status.processor_status == ProcessorStatus.PAUSED else "active",
        cognitive_state=status.cognitive_state or "UNKNOWN",
        queue_depth=actual_queue_depth,
    )


def _get_system_uptime(request: Request) -> float:
    """Get system uptime in seconds."""
    time_service: Optional[TimeServiceProtocol] = getattr(request.app.state, "time_service", None)
    start_time = getattr(time_service, "_start_time", None) if time_service else None
    current_time = time_service.now() if time_service else datetime.now(timezone.utc)
    return (current_time - start_time).total_seconds() if start_time else 0.0


def _get_current_time(request: Request) -> datetime:
    """Get current system time."""
    time_service: Optional[TimeServiceProtocol] = getattr(request.app.state, "time_service", None)
    return time_service.now() if time_service else datetime.now(timezone.utc)


def _get_cognitive_state_safe(request: Request) -> Optional[str]:
    """Safely get cognitive state from agent processor."""
    runtime = getattr(request.app.state, "runtime", None)
    if not (runtime and hasattr(runtime, "agent_processor") and runtime.agent_processor is not None):
        return None

    try:
        state: str = runtime.agent_processor.get_current_state()
        return state
    except Exception as e:
        logger.warning(
            f"Failed to retrieve cognitive state: {type(e).__name__}: {str(e)} - Agent processor may not be initialized"
        )
        return None


def _check_initialization_status(request: Request) -> bool:
    """Check if system initialization is complete."""
    init_service = getattr(request.app.state, "initialization_service", None)
    if init_service and hasattr(init_service, "is_initialized"):
        result: bool = init_service.is_initialized()
        return result
    return True


async def _check_provider_health(provider: Any) -> bool:
    """Check if a single provider is healthy."""
    try:
        if hasattr(provider, "is_healthy"):
            if asyncio.iscoroutinefunction(provider.is_healthy):
                result: bool = await provider.is_healthy()
                return result
            else:
                result_sync: bool = provider.is_healthy()
                return result_sync
        else:
            return True  # Assume healthy if no method
    except Exception:
        return False


async def _collect_service_health(request: Request) -> Dict[str, Dict[str, int]]:
    """Collect service health data from service registry."""
    services: Dict[str, Dict[str, int]] = {}
    if not (hasattr(request.app.state, "service_registry") and request.app.state.service_registry is not None):
        return services

    service_registry = request.app.state.service_registry
    try:
        for service_type in list(ServiceType):
            providers = service_registry.get_services_by_type(service_type)
            if providers:
                healthy_count = 0
                for provider in providers:
                    if await _check_provider_health(provider):
                        healthy_count += 1
                    else:
                        logger.debug(f"Service health check returned unhealthy for {service_type.value}")
                services[service_type.value] = {"available": len(providers), "healthy": healthy_count}
    except Exception as e:
        logger.error(f"Error checking service health: {e}")

    return services


def _check_processor_via_runtime(runtime: Any) -> Optional[bool]:
    """Check processor health via runtime's agent_processor directly.

    Returns True if healthy, False if unhealthy, None if cannot determine.
    """
    if not runtime:
        return None
    agent_processor = getattr(runtime, "agent_processor", None)
    if not agent_processor:
        return None
    # Agent processor exists - check if it's running
    is_running = getattr(agent_processor, "_running", False)
    if is_running:
        return True
    # Also check via _agent_task if available
    agent_task = getattr(runtime, "_agent_task", None)
    if agent_task and not agent_task.done():
        return True
    return None


def _get_runtime_control_from_app(request: Request) -> Any:
    """Get RuntimeControlService from app state, trying multiple locations."""
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    return runtime_control


async def _check_health_via_runtime_control(runtime_control: Any) -> Optional[bool]:
    """Check processor health via RuntimeControlService.

    Returns True if healthy, False if unhealthy, None if cannot determine.
    """
    if not runtime_control:
        return None
    try:
        # Try get_processor_queue_status if available
        if hasattr(runtime_control, "get_processor_queue_status"):
            queue_status = await runtime_control.get_processor_queue_status()
            processor_healthy = queue_status.processor_name != "unknown"
            runtime_status = await runtime_control.get_runtime_status()
            return bool(processor_healthy and runtime_status.is_running)
        # Fallback: Check runtime status dict (APIRuntimeControlService)
        elif hasattr(runtime_control, "get_runtime_status"):
            status = runtime_control.get_runtime_status()
            if isinstance(status, dict):
                # APIRuntimeControlService returns dict, not paused = healthy
                return not status.get("paused", False)
    except Exception as e:
        logger.warning(f"Failed to check processor health via runtime_control: {e}")
    return None


async def _check_processor_health(request: Request) -> bool:
    """Check if processor thread is healthy."""
    runtime = getattr(request.app.state, "runtime", None)

    # First try: Check the runtime's agent_processor directly
    runtime_result = _check_processor_via_runtime(runtime)
    if runtime_result is True:
        return True

    # Second try: Use RuntimeControlService if available (for full API)
    runtime_control = _get_runtime_control_from_app(request)
    control_result = await _check_health_via_runtime_control(runtime_control)
    if control_result is not None:
        return control_result

    # If we have a runtime with agent_processor, consider healthy
    if runtime and getattr(runtime, "agent_processor", None) is not None:
        return True

    return False


def _determine_overall_status(init_complete: bool, processor_healthy: bool, services: Dict[str, Dict[str, int]]) -> str:
    """Determine overall system status based on components."""
    total_services = sum(s.get("available", 0) for s in services.values())
    healthy_services = sum(s.get("healthy", 0) for s in services.values())

    if not init_complete:
        return "initializing"
    elif not processor_healthy:
        return "critical"  # Processor thread dead = critical
    elif healthy_services == total_services:
        return "healthy"
    elif healthy_services >= total_services * 0.8:
        return "degraded"
    else:
        return "critical"


def _get_cognitive_state(request: Request) -> Optional[str]:
    """Get cognitive state from agent processor if available."""
    cognitive_state: Optional[str] = None
    runtime = getattr(request.app.state, "runtime", None)
    if runtime and hasattr(runtime, "agent_processor") and runtime.agent_processor is not None:
        try:
            cognitive_state = runtime.agent_processor.get_current_state()
        except Exception as e:
            logger.warning(
                f"Failed to retrieve cognitive state: {type(e).__name__}: {str(e)} - Agent processor may not be initialized"
            )
    return cognitive_state


def _create_final_response(
    base_result: RuntimeControlResponse, cognitive_state: Optional[str]
) -> RuntimeControlResponse:
    """Create final response with cognitive state and any enhanced fields."""
    response = RuntimeControlResponse(
        success=base_result.success,
        message=base_result.message,
        processor_state=base_result.processor_state,
        cognitive_state=cognitive_state or base_result.cognitive_state or "UNKNOWN",
        queue_depth=base_result.queue_depth,
    )

    # Copy enhanced fields if they exist
    if hasattr(base_result, "current_step"):
        response.current_step = base_result.current_step
    if hasattr(base_result, "current_step_schema"):
        response.current_step_schema = base_result.current_step_schema
    if hasattr(base_result, "pipeline_state"):
        response.pipeline_state = base_result.pipeline_state

    return response


@router.post("/runtime/{action}", response_model=SuccessResponse[RuntimeControlResponse])
async def control_runtime(
    action: str, request: Request, body: RuntimeAction = Body(...), auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[RuntimeControlResponse]:
    """
    Runtime control actions.

    Control agent runtime behavior. Valid actions:
    - pause: Pause message processing
    - resume: Resume message processing
    - state: Get current runtime state

    Requires ADMIN role.
    """
    try:
        runtime_control = _get_runtime_control_service(request)
        _validate_runtime_action(action)

        # Execute action
        if action == "pause":
            success = await _execute_pause_action(runtime_control, body)
            current_step, current_step_schema, pipeline_state = _extract_pipeline_state_info(request)
            result = _create_pause_response(success, current_step, current_step_schema, pipeline_state)
        elif action == "resume":
            result = await _execute_resume_action(runtime_control)
        elif action == "state":
            result = await _execute_state_action(runtime_control)
            return SuccessResponse(data=result)

        # Get cognitive state and create final response
        cognitive_state = _get_cognitive_state(request)
        response = _create_final_response(result, cognitive_state)

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Valid cognitive states for transition
VALID_COGNITIVE_STATES = {"WORK", "DREAM", "PLAY", "SOLITUDE"}


@router.post("/state/transition", response_model=SuccessResponse[StateTransitionResponse])
async def transition_cognitive_state(
    request: Request,
    body: StateTransitionRequest = Body(...),
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[StateTransitionResponse]:
    """
    Request a cognitive state transition.

    Transitions the agent to a different cognitive state (WORK, DREAM, PLAY, SOLITUDE).
    Valid transitions depend on the current state:
    - From WORK: Can transition to DREAM, PLAY, or SOLITUDE
    - From PLAY: Can transition to WORK or SOLITUDE
    - From SOLITUDE: Can transition to WORK
    - From DREAM: Typically transitions back to WORK when complete

    Requires ADMIN role.
    """
    try:
        target_state = body.target_state.upper()
        logger.info(f"[STATE_TRANSITION] Request received: target_state={target_state}, reason={body.reason}")

        # Validate target state
        if target_state not in VALID_COGNITIVE_STATES:
            logger.error(f"[STATE_TRANSITION] FAIL: Invalid target state '{target_state}'")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid target state '{target_state}'. Must be one of: {', '.join(sorted(VALID_COGNITIVE_STATES))}",
            )

        # Get current state
        previous_state = _get_cognitive_state(request)
        logger.info(f"[STATE_TRANSITION] Current state: {previous_state}")

        # Get runtime control service - FAIL FAST with detailed logging
        runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
        if not runtime_control:
            runtime_control = getattr(request.app.state, "runtime_control_service", None)

        if not runtime_control:
            logger.error("[STATE_TRANSITION] FAIL: No runtime control service available in app.state")
            logger.error(f"[STATE_TRANSITION] Available app.state attrs: {dir(request.app.state)}")
            raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

        # Log service type for debugging
        service_type = type(runtime_control).__name__
        service_module = type(runtime_control).__module__
        logger.info(f"[STATE_TRANSITION] Runtime control service: {service_type} from {service_module}")

        # Check if request_state_transition is available - FAIL LOUD
        has_method = hasattr(runtime_control, "request_state_transition")
        logger.info(f"[STATE_TRANSITION] Has request_state_transition method: {has_method}")

        if not has_method:
            available_methods = [m for m in dir(runtime_control) if not m.startswith("_")]
            logger.error(f"[STATE_TRANSITION] FAIL: Service {service_type} missing request_state_transition")
            logger.error(f"[STATE_TRANSITION] Available methods: {available_methods}")
            raise HTTPException(
                status_code=503,
                detail=f"State transition not supported by {service_type}. Missing request_state_transition method.",
            )

        # Request the transition
        reason = body.reason or f"Requested via API from {previous_state or 'UNKNOWN'}"
        logger.info(f"[STATE_TRANSITION] Calling request_state_transition({target_state}, {reason})")
        success = await runtime_control.request_state_transition(target_state, reason)
        logger.info(f"[STATE_TRANSITION] Transition result: success={success}")

        # Get current state after transition attempt
        current_state = _get_cognitive_state(request) or target_state
        logger.info(f"[STATE_TRANSITION] Post-transition state: {current_state}")

        if success:
            message = f"Transition to {target_state} initiated successfully"
        else:
            message = f"Transition to {target_state} could not be initiated"

        return SuccessResponse(
            data=StateTransitionResponse(
                success=success,
                message=message,
                previous_state=previous_state,
                current_state=current_state,
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[STATE_TRANSITION] FAIL: Unexpected error: {type(e).__name__}: {e}")
        import traceback

        logger.error(f"[STATE_TRANSITION] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


def _parse_direct_service_key(service_key: str) -> tuple[str, str]:
    """Parse direct service key and return service_type and display_name."""
    parts = service_key.split(".")
    if len(parts) >= 3:
        service_type = parts[1]  # 'graph', 'infrastructure', etc.
        service_name = parts[2]  # 'memory_service', 'time_service', etc.

        # Convert snake_case to PascalCase for display
        display_name = "".join(word.capitalize() for word in service_name.split("_"))
        return service_type, display_name
    return "unknown", service_key


def _parse_registry_service_key(service_key: str) -> tuple[str, str]:
    """Parse registry service key and return service_type and display_name."""
    parts = service_key.split(".")
    logger.debug(f"Parsing registry key: {service_key}, parts: {parts}")

    # Handle both 3-part and 4-part keys
    if len(parts) >= 4 and parts[1] == "ServiceType":
        # Format: registry.ServiceType.ENUM.ServiceName_id
        service_type_enum = f"{parts[1]}.{parts[2]}"  # 'ServiceType.TOOL'
        service_name = parts[3]  # 'APIToolService_127803015745648'
        logger.debug(f"4-part key: {service_key}, service_name: {service_name}")
    else:
        # Fallback: registry.ENUM.ServiceName
        service_type_enum = parts[1]  # 'ServiceType.COMMUNICATION', etc.
        service_name = parts[2] if len(parts) > 2 else parts[1]  # Service name or enum value
        logger.debug(f"3-part key: {service_key}, service_name: {service_name}")

    # Clean up service name (remove instance ID)
    if "_" in service_name:
        service_name = service_name.split("_")[0]

    # Extract adapter type from service name
    adapter_prefix = ""
    if "Discord" in service_name:
        adapter_prefix = "DISCORD"
    elif "API" in service_name:
        adapter_prefix = "API"
    elif "CLI" in service_name:
        adapter_prefix = "CLI"

    # Map ServiceType enum to category and set display name
    service_type, display_name = _map_service_type_enum(service_type_enum, service_name, adapter_prefix)

    return service_type, display_name


def _map_service_type_enum(service_type_enum: str, service_name: str, adapter_prefix: str) -> tuple[str, str]:
    """Map ServiceType enum to category and create display name."""
    service_type = _get_service_category(service_type_enum)
    display_name = _create_display_name(service_type_enum, service_name, adapter_prefix)

    return service_type, display_name


def _get_service_category(service_type_enum: str) -> str:
    """Get the service category based on the service type enum."""
    # Tool Services (need to check first due to SECRETS_TOOL containing SECRETS)
    if "TOOL" in service_type_enum:
        return "tool"

    # Adapter Services (Communication is adapter-specific)
    elif "COMMUNICATION" in service_type_enum:
        return "adapter"

    # Runtime Services (need to check RUNTIME_CONTROL before SECRETS in infrastructure)
    elif any(service in service_type_enum for service in ["LLM", "RUNTIME_CONTROL", "TASK_SCHEDULER"]):
        return "runtime"

    # Graph Services (6)
    elif any(
        service in service_type_enum
        for service in ["MEMORY", "CONFIG", "TELEMETRY", "AUDIT", "INCIDENT_MANAGEMENT", "TSDB_CONSOLIDATION"]
    ):
        return "graph"

    # Infrastructure Services (7)
    elif any(
        service in service_type_enum
        for service in [
            "TIME",
            "SECRETS",
            "AUTHENTICATION",
            "RESOURCE_MONITOR",
            "DATABASE_MAINTENANCE",
            "INITIALIZATION",
            "SHUTDOWN",
        ]
    ):
        return "infrastructure"

    # Governance Services (4)
    elif any(
        service in service_type_enum
        for service in ["WISE_AUTHORITY", "ADAPTIVE_FILTER", "VISIBILITY", "SELF_OBSERVATION"]
    ):
        return "governance"

    else:
        return "unknown"


def _create_display_name(service_type_enum: str, service_name: str, adapter_prefix: str) -> str:
    """Create appropriate display name based on service type and adapter prefix."""
    if not adapter_prefix:
        return service_name

    if "COMMUNICATION" in service_type_enum:
        return f"{adapter_prefix}-COMM"
    elif "RUNTIME_CONTROL" in service_type_enum:
        return f"{adapter_prefix}-RUNTIME"
    elif "TOOL" in service_type_enum:
        return f"{adapter_prefix}-TOOL"
    elif "WISE_AUTHORITY" in service_type_enum:
        return f"{adapter_prefix}-WISE"
    else:
        return service_name


def _parse_service_key(service_key: str) -> tuple[str, str]:
    """Parse any service key and return service_type and display_name."""
    parts = service_key.split(".")

    # Handle direct services (format: direct.service_type.service_name)
    if service_key.startswith("direct.") and len(parts) >= 3:
        return _parse_direct_service_key(service_key)

    # Handle registry services (format: registry.ServiceType.ENUM.ServiceName_id)
    elif service_key.startswith("registry.") and len(parts) >= 3:
        return _parse_registry_service_key(service_key)

    else:
        return "unknown", service_key


def _create_service_status(service_key: str, details: JSONDict) -> ServiceStatus:
    """Create ServiceStatus from service key and details."""
    service_type, display_name = _parse_service_key(service_key)

    return ServiceStatus(
        name=display_name,
        type=service_type,
        healthy=details.get("healthy", False),
        available=details.get("healthy", False),  # Use healthy as available
        uptime_seconds=None,  # Not available in simplified view
        metrics=ServiceMetrics(),
    )


def _update_service_summary(service_summary: Dict[str, Dict[str, int]], service_type: str, is_healthy: bool) -> None:
    """Update service summary with service type and health status."""
    if service_type not in service_summary:
        service_summary[service_type] = {"total": 0, "healthy": 0}
    service_summary[service_type]["total"] += 1
    if is_healthy:
        service_summary[service_type]["healthy"] += 1


@router.get("/services", response_model=SuccessResponse[ServicesStatusResponse])
async def get_services_status(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ServicesStatusResponse]:
    """
    Service status.

    Returns status of all system services including health,
    availability, and basic metrics.
    """
    # Use the runtime control service to get all services
    try:
        runtime_control = _get_runtime_control_service(request)
    except HTTPException:
        # Handle case where no runtime control service is available
        return SuccessResponse(
            data=ServicesStatusResponse(
                services=[], total_services=0, healthy_services=0, timestamp=datetime.now(timezone.utc)
            )
        )

    # Get service health status from runtime control
    try:
        health_status = await runtime_control.get_service_health_status()

        # Convert service details to ServiceStatus list using helper functions
        services = []
        service_summary: Dict[str, Dict[str, int]] = {}

        # Include ALL services (both direct and registry)
        for service_key, details in health_status.service_details.items():
            status = _create_service_status(service_key, details)
            services.append(status)
            _update_service_summary(service_summary, status.type, status.healthy)

        return SuccessResponse(
            data=ServicesStatusResponse(
                services=services,
                total_services=len(services),
                healthy_services=sum(1 for s in services if s.healthy),
                timestamp=datetime.now(timezone.utc),
            )
        )
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        return SuccessResponse(
            data=ServicesStatusResponse(
                services=[], total_services=0, healthy_services=0, timestamp=datetime.now(timezone.utc)
            )
        )


def _validate_shutdown_request(body: ShutdownRequest) -> None:
    """Validate shutdown request confirmation."""
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required (confirm=true)")


def _get_shutdown_service(request: Request) -> Any:
    """Get shutdown service from runtime, raising HTTPException if not available."""
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime:
        raise HTTPException(status_code=503, detail="Runtime not available")

    shutdown_service = getattr(runtime, "shutdown_service", None)
    if not shutdown_service:
        raise HTTPException(status_code=503, detail=ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE)

    return shutdown_service, runtime


def _check_shutdown_already_requested(shutdown_service: Any) -> None:
    """Check if shutdown is already in progress."""
    if shutdown_service.is_shutdown_requested():
        existing_reason = shutdown_service.get_shutdown_reason()
        raise HTTPException(status_code=409, detail=f"Shutdown already requested: {existing_reason}")


def _build_shutdown_reason(body: ShutdownRequest, auth: AuthContext) -> str:
    """Build and sanitize shutdown reason."""
    reason = f"{body.reason} (API shutdown by {auth.user_id})"
    if body.force:
        reason += " [FORCED]"

    # Sanitize reason for logging to prevent log injection
    # Replace newlines and control characters with spaces
    safe_reason = "".join(c if c.isprintable() and c not in "\n\r\t" else " " for c in reason)

    return safe_reason


def _create_audit_metadata(body: ShutdownRequest, auth: AuthContext, request: Request) -> Dict[str, Any]:
    """Create metadata dict for shutdown audit event."""
    is_service_account = auth.role.value == "SERVICE_ACCOUNT"
    return {
        "force": body.force,
        "is_service_account": is_service_account,
        "auth_role": auth.role.value,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "request_path": str(request.url.path),
    }


async def _audit_shutdown_request(
    request: Request, body: ShutdownRequest, auth: AuthContext, safe_reason: str
) -> None:  # NOSONAR - async required for create_task
    """Audit the shutdown request for security tracking."""
    audit_service = getattr(request.app.state, "audit_service", None)
    if not audit_service:
        return

    from ciris_engine.schemas.services.graph.audit import AuditEventData

    audit_event = AuditEventData(
        entity_id="system",
        actor=auth.user_id,
        outcome="initiated",
        severity="high" if body.force else "warning",
        action="system_shutdown",
        resource="system",
        reason=safe_reason,
        metadata=_create_audit_metadata(body, auth, request),
    )

    import asyncio

    # Store task reference to prevent garbage collection
    # Using _ prefix to indicate we're intentionally not awaiting
    _audit_task = asyncio.create_task(audit_service.log_event("system_shutdown_request", audit_event))


async def _execute_shutdown(shutdown_service: Any, runtime: Any, body: ShutdownRequest, reason: str) -> None:
    """Execute the shutdown with appropriate method based on force flag."""
    if body.force:
        # Forced shutdown: bypass thought processing, immediate termination
        await shutdown_service.emergency_shutdown(reason, timeout_seconds=5)
    else:
        # Normal shutdown: allow thoughtful consideration via runtime
        # The runtime's request_shutdown will call the shutdown service AND set global flags
        runtime.request_shutdown(reason)


@router.post("/shutdown", response_model=SuccessResponse[ShutdownResponse])
async def shutdown_system(
    body: ShutdownRequest, request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[ShutdownResponse]:
    """
    Graceful shutdown.

    Initiates graceful system shutdown. Requires confirmation
    flag to prevent accidental shutdowns.

    Requires ADMIN role.
    """
    try:
        # Validate and get required services
        _validate_shutdown_request(body)
        shutdown_service, runtime = _get_shutdown_service(request)

        # Check if already shutting down
        _check_shutdown_already_requested(shutdown_service)

        # Build and sanitize shutdown reason
        safe_reason = _build_shutdown_reason(body, auth)

        # Log shutdown request
        logger.warning(f"SHUTDOWN requested: {safe_reason}")

        # Audit shutdown request
        await _audit_shutdown_request(request, body, auth, safe_reason)

        # Execute shutdown
        await _execute_shutdown(shutdown_service, runtime, body, safe_reason)

        # Create response
        response = ShutdownResponse(
            status="initiated",
            message=f"System shutdown initiated: {safe_reason}",
            shutdown_initiated=True,
            timestamp=datetime.now(timezone.utc),
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating shutdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _is_localhost_request(request: Request) -> bool:
    """Check if request originates from localhost (safe for unauthenticated shutdown)."""
    client_host = request.client.host if request.client else None
    # Accept localhost variants: 127.0.0.1, ::1, localhost
    return client_host in ("127.0.0.1", "::1", "localhost", None)


# Constants for local shutdown
_RESUME_TIMEOUT_SECONDS = 30.0


def _get_server_state(runtime: Any) -> Dict[str, Any]:
    """Get server state info for logging and responses.

    Args:
        runtime: The runtime instance (may be None)

    Returns:
        Dict with server_state, uptime_seconds, resume_in_progress, resume_elapsed_seconds
    """
    if not runtime:
        return {
            "server_state": "STARTING",
            "uptime_seconds": 0,
            "resume_in_progress": False,
            "resume_elapsed_seconds": None,
        }

    uptime = time.time() - getattr(runtime, "_startup_time", time.time())
    resume_in_progress = getattr(runtime, "_resume_in_progress", False)
    resume_started = getattr(runtime, "_resume_started_at", None)
    resume_elapsed = (time.time() - resume_started) if resume_started else None
    shutdown_in_progress = getattr(runtime, "_shutdown_in_progress", False)

    state = _determine_server_state(runtime, shutdown_in_progress, resume_in_progress)

    return {
        "server_state": state,
        "uptime_seconds": round(uptime, 2),
        "resume_in_progress": resume_in_progress,
        "resume_elapsed_seconds": round(resume_elapsed, 2) if resume_elapsed else None,
    }


def _determine_server_state(runtime: Any, shutdown_in_progress: bool, resume_in_progress: bool) -> str:
    """Determine the current server state string.

    Args:
        runtime: The runtime instance
        shutdown_in_progress: Whether shutdown is in progress
        resume_in_progress: Whether resume is in progress

    Returns:
        State string: SHUTTING_DOWN, RESUMING, READY, or INITIALIZING
    """
    if shutdown_in_progress:
        return "SHUTTING_DOWN"
    if resume_in_progress:
        return "RESUMING"
    if runtime and getattr(runtime, "_initialized", False):
        return "READY"
    return "INITIALIZING"


def _check_resume_blocking(runtime: Any, state_info: Dict[str, Any]) -> Optional[Response]:
    """Check if resume is in progress and should block shutdown.

    Args:
        runtime: The runtime instance
        state_info: Current server state info dict

    Returns:
        JSONResponse if shutdown should be blocked, None if OK to proceed
    """
    resume_in_progress = getattr(runtime, "_resume_in_progress", False)
    if not resume_in_progress:
        return None

    resume_started_at = getattr(runtime, "_resume_started_at", None)
    resume_elapsed = (time.time() - resume_started_at) if resume_started_at else 0

    if resume_elapsed >= _RESUME_TIMEOUT_SECONDS:
        # Resume stuck - allow shutdown
        logger.warning(
            f"[LOCAL_SHUTDOWN] Resume exceeded timeout ({resume_elapsed:.1f}s > "
            f"{_RESUME_TIMEOUT_SECONDS}s) - treating as stuck, allowing shutdown"
        )
        return None

    # Resume actively happening - ask caller to retry
    remaining = _RESUME_TIMEOUT_SECONDS - resume_elapsed
    retry_after_ms = min(2000, int(remaining * 1000))

    logger.warning(
        f"[LOCAL_SHUTDOWN] Rejected (409) - resume in progress for {resume_elapsed:.1f}s, "
        f"retry in {retry_after_ms}ms (timeout at {_RESUME_TIMEOUT_SECONDS}s)"
    )
    return JSONResponse(
        status_code=409,
        content={
            "status": "busy",
            "reason": f"Resume from first-run in progress ({resume_elapsed:.1f}s elapsed)",
            "retry_after_ms": retry_after_ms,
            "resume_timeout_seconds": _RESUME_TIMEOUT_SECONDS,
            **state_info,
        },
    )


def _check_shutdown_already_in_progress(runtime: Any, state_info: Dict[str, Any]) -> Optional[Response]:
    """Check if shutdown is already in progress.

    Args:
        runtime: The runtime instance
        state_info: Current server state info dict

    Returns:
        JSONResponse if shutdown already in progress, None otherwise
    """
    shutdown_service = getattr(runtime, "shutdown_service", None)
    shutdown_in_progress = getattr(runtime, "_shutdown_in_progress", False)

    is_shutting_down = shutdown_in_progress or (shutdown_service and shutdown_service.is_shutdown_requested())

    if not is_shutting_down:
        return None

    existing_reason = shutdown_service.get_shutdown_reason() if shutdown_service else "unknown"
    logger.info(f"[LOCAL_SHUTDOWN] Shutdown already in progress: {existing_reason}")
    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "reason": f"Shutdown already in progress: {existing_reason}",
            **state_info,
        },
    )


def _initiate_force_shutdown(runtime: Any, reason: str) -> None:
    """Initiate forced shutdown with background exit thread.

    Args:
        runtime: The runtime instance
        reason: Shutdown reason string
    """
    import os
    import threading

    runtime._shutdown_in_progress = True

    def _force_exit() -> None:
        """Force process exit after brief delay to allow response to be sent."""
        time.sleep(0.5)
        logger.warning("[LOCAL_SHUTDOWN] Force exiting process NOW")
        os._exit(0)

    exit_thread = threading.Thread(target=_force_exit, daemon=True)
    exit_thread.start()

    # Also request normal shutdown in case force exit fails
    runtime.request_shutdown(reason)


@router.post("/local-shutdown", response_model=SuccessResponse[ShutdownResponse])
async def local_shutdown(request: Request) -> Response:
    """
    Localhost-only shutdown endpoint (no authentication required).

    This endpoint is designed for Android/mobile apps where:
    - App data may be cleared (losing auth tokens)
    - Previous Python process may still be running
    - Need to gracefully shut down before starting new instance

    Security: Only accepts requests from localhost (127.0.0.1, ::1).
    This is safe because only processes on the same device can call it.

    Response codes for SmartStartup negotiation:
    - 200: Shutdown initiated successfully
    - 202: Shutdown already in progress
    - 403: Not localhost (security rejection)
    - 409: Resume in progress, retry later (with retry_after_ms)
    - 503: Server not ready
    """
    # Verify request is from localhost
    client_host = request.client.host if request.client else "unknown"
    if not _is_localhost_request(request):
        logger.warning(f"[LOCAL_SHUTDOWN] Rejected from non-local client: {client_host}")
        raise HTTPException(status_code=403, detail="This endpoint only accepts requests from localhost")

    logger.info(f"[LOCAL_SHUTDOWN] Request received from {client_host}")

    # Get runtime
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime:
        logger.warning("[LOCAL_SHUTDOWN] Runtime not available (503)")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "reason": "Runtime not available",
                "retry_after_ms": 1000,
                "server_state": "STARTING",
            },
        )

    state_info = _get_server_state(runtime)
    logger.info(f"[LOCAL_SHUTDOWN] Server state: {state_info}")

    # Check if resume is blocking shutdown
    resume_response = _check_resume_blocking(runtime, state_info)
    if resume_response:
        return resume_response

    # Check if already shutting down
    shutdown_response = _check_shutdown_already_in_progress(runtime, state_info)
    if shutdown_response:
        return shutdown_response

    # Verify shutdown service is available
    shutdown_service = getattr(runtime, "shutdown_service", None)
    if not shutdown_service:
        logger.warning("[LOCAL_SHUTDOWN] Shutdown service not available (503)")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "reason": "Shutdown service not available",
                "retry_after_ms": 1000,
                **state_info,
            },
        )

    # Initiate shutdown
    reason = "Local shutdown requested (Android SmartStartup)"
    logger.warning(f"[LOCAL_SHUTDOWN] Initiating IMMEDIATE shutdown: {reason}")
    _initiate_force_shutdown(runtime, reason)

    logger.info("[LOCAL_SHUTDOWN] Shutdown initiated successfully (200)")
    return JSONResponse(
        status_code=200,
        content={
            "status": "accepted",
            "reason": reason,
            **state_info,
        },
    )


# Adapter Management Endpoints


@router.get("/adapters", response_model=SuccessResponse[AdapterListResponse])
async def list_adapters(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[AdapterListResponse]:
    """
    List all loaded adapters.

    Returns information about all currently loaded adapter instances
    including their type, status, and basic metrics.
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Get adapter list from runtime control service
        adapters = await runtime_control.list_adapters()

        # Convert to response format
        adapter_statuses = []
        for adapter in adapters:
            # Convert AdapterInfo to AdapterStatusSchema
            # Check status using the enum value (which is lowercase)
            from ciris_engine.schemas.services.core.runtime import AdapterStatus

            is_running = adapter.status == AdapterStatus.RUNNING or str(adapter.status).lower() == "running"

            config = AdapterConfig(adapter_type=adapter.adapter_type, enabled=is_running, settings={})

            metrics = None
            if adapter.messages_processed > 0 or adapter.error_count > 0:
                metrics = AdapterMetrics(
                    messages_processed=adapter.messages_processed,
                    errors_count=adapter.error_count,
                    uptime_seconds=(
                        (datetime.now(timezone.utc) - adapter.started_at).total_seconds() if adapter.started_at else 0
                    ),
                    last_error=adapter.last_error,
                    last_error_time=None,
                )

            adapter_statuses.append(
                AdapterStatusSchema(
                    adapter_id=adapter.adapter_id,
                    adapter_type=adapter.adapter_type,
                    is_running=is_running,
                    loaded_at=adapter.started_at or datetime.now(timezone.utc),
                    services_registered=[],  # Not available from AdapterInfo
                    config_params=config,
                    metrics=metrics,  # Pass the AdapterMetrics object directly
                    last_activity=None,
                    tools=adapter.tools,  # Include tools information
                )
            )

        running_count = sum(1 for a in adapter_statuses if a.is_running)

        response = AdapterListResponse(
            adapters=adapter_statuses, total_count=len(adapter_statuses), running_count=running_count
        )

        return SuccessResponse(data=response)

    except ValidationError as e:
        logger.error(f"Validation error listing adapters: {e}")
        logger.error(f"Validation errors detail: {e.errors()}")
        # Return empty list on validation error to avoid breaking GUI
        return SuccessResponse(data=AdapterListResponse(adapters=[], total_count=0, running_count=0))
    except Exception as e:
        logger.error(f"Error listing adapters: {e}")
        logger.error(f"Error type: {type(e).__name__}")
        import traceback

        logger.error(f"Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


# Module types helper functions


def _get_core_adapter_info(adapter_type: str) -> ModuleTypeInfo:
    """Generate ModuleTypeInfo for a core adapter."""
    core_adapters: Dict[str, Dict[str, Any]] = {
        "api": {
            "name": "API Adapter",
            "description": "REST API adapter providing HTTP endpoints for CIRIS interaction",
            "service_types": ["COMMUNICATION", "TOOL", "RUNTIME_CONTROL"],
            "capabilities": [*COMM_CAPABILITIES, "tool:api", "runtime_control"],
            "configuration": [
                ModuleConfigParameter(
                    name="host",
                    param_type="string",
                    default="127.0.0.1",
                    description="Host address to bind to",
                    env_var="CIRIS_API_HOST",
                    required=False,
                ),
                ModuleConfigParameter(
                    name="port",
                    param_type="integer",
                    default=8000,
                    description="Port to listen on",
                    env_var="CIRIS_API_PORT",
                    required=False,
                ),
                ModuleConfigParameter(
                    name="debug",
                    param_type="boolean",
                    default=False,
                    description="Enable debug mode",
                    env_var="CIRIS_API_DEBUG",
                    required=False,
                ),
            ],
        },
        "cli": {
            "name": "CLI Adapter",
            "description": "Command-line interface adapter for interactive terminal sessions",
            "service_types": ["COMMUNICATION"],
            "capabilities": COMM_CAPABILITIES,
            "configuration": [
                ModuleConfigParameter(
                    name="prompt",
                    param_type="string",
                    default="CIRIS> ",
                    description="CLI prompt string",
                    required=False,
                ),
            ],
        },
        "discord": {
            "name": "Discord Adapter",
            "description": "Discord bot adapter for community interaction",
            "service_types": ["COMMUNICATION", "TOOL"],
            "capabilities": [*COMM_CAPABILITIES, "tool:discord"],
            "configuration": [
                ModuleConfigParameter(
                    name="discord_token",
                    param_type="string",
                    description="Discord bot token",
                    env_var="CIRIS_DISCORD_TOKEN",
                    required=True,
                    sensitivity="HIGH",
                ),
                ModuleConfigParameter(
                    name="guild_id",
                    param_type="string",
                    description="Discord guild ID to operate in",
                    env_var="CIRIS_DISCORD_GUILD_ID",
                    required=False,
                ),
                ModuleConfigParameter(
                    name="channel_id",
                    param_type="string",
                    description="Default channel ID for messages",
                    env_var="CIRIS_DISCORD_CHANNEL_ID",
                    required=False,
                ),
            ],
        },
    }

    adapter_info = core_adapters.get(adapter_type, {})
    return ModuleTypeInfo(
        module_id=adapter_type,
        name=adapter_info.get("name", adapter_type.title()),
        version="1.0.0",
        description=adapter_info.get("description", f"Core {adapter_type} adapter"),
        author="CIRIS Team",
        module_source="core",
        service_types=adapter_info.get("service_types", []),
        capabilities=adapter_info.get("capabilities", []),
        configuration_schema=adapter_info.get("configuration", []),
        requires_external_deps=adapter_type == "discord",
        external_dependencies={"discord.py": ">=2.0.0"} if adapter_type == "discord" else {},
        is_mock=False,
        safe_domain=None,
        prohibited=[],
        metadata=None,
    )


def _check_platform_requirements_satisfied(platform_requirements: List[str]) -> bool:
    """Check if current platform satisfies the given requirements.

    Args:
        platform_requirements: List of requirement strings

    Returns:
        True if platform satisfies all requirements, False otherwise
    """
    if not platform_requirements:
        return True

    from ciris_engine.logic.utils.platform_detection import detect_platform_capabilities
    from ciris_engine.schemas.platform import PlatformRequirement

    try:
        caps = detect_platform_capabilities()
        req_enums = []
        for req_str in platform_requirements:
            try:
                req_enums.append(PlatformRequirement(req_str))
            except ValueError:
                pass  # Unknown requirement, skip
        return caps.satisfies(req_enums)
    except Exception:
        return False


def _should_filter_adapter(manifest_data: Dict[str, Any], filter_by_platform: bool = True) -> bool:
    """Check if an adapter should be filtered from public listings.

    Filters out:
    - Mock adapters (module.MOCK: true)
    - Library modules (metadata.type: "library")
    - Modules with no services (empty services array)
    - Common/utility modules (name ends with _common)
    - Adapters that don't meet platform requirements (if filter_by_platform=True)

    Args:
        manifest_data: The manifest JSON data
        filter_by_platform: If True, also filter adapters that don't meet platform requirements

    Returns:
        True if the adapter should be filtered (hidden), False otherwise
    """
    module_info = manifest_data.get("module", {})
    metadata = manifest_data.get("metadata", {})
    services = manifest_data.get("services", [])

    # Filter mock adapters
    if module_info.get("MOCK", False):
        return True

    # Filter library modules
    if isinstance(metadata, dict) and metadata.get("type") == "library":
        return True

    # Filter modules with no services (utility/common modules)
    if not services:
        return True

    # Filter common modules by name pattern
    module_name = module_info.get("name", "")
    if module_name.endswith("_common") or module_name.endswith("common"):
        return True

    # Filter adapters that don't meet platform requirements
    if filter_by_platform:
        platform_requirements = manifest_data.get("platform_requirements", [])
        if not _check_platform_requirements_satisfied(platform_requirements):
            return True

    return False


def _extract_service_types(manifest_data: Dict[str, Any]) -> List[str]:
    """Extract unique service types from manifest services list."""
    service_types = []
    for svc in manifest_data.get("services", []):
        svc_type = svc.get("type", "")
        if svc_type and svc_type not in service_types:
            service_types.append(svc_type)
    return service_types


def _parse_config_parameters(manifest_data: Dict[str, Any]) -> List[ModuleConfigParameter]:
    """Parse configuration parameters from manifest."""
    config_params: List[ModuleConfigParameter] = []
    for param_name, param_data in manifest_data.get("configuration", {}).items():
        if isinstance(param_data, dict):
            config_params.append(
                ModuleConfigParameter(
                    name=param_name,
                    param_type=param_data.get("type", "string"),
                    default=param_data.get("default"),
                    description=param_data.get("description", ""),
                    env_var=param_data.get("env"),
                    required=param_data.get("required", True),
                    sensitivity=param_data.get("sensitivity"),
                )
            )
    return config_params


def _parse_manifest_to_module_info(manifest_data: Dict[str, Any], module_id: str) -> ModuleTypeInfo:
    """Parse a module manifest into a ModuleTypeInfo."""
    module_info = manifest_data.get("module", {})

    # Extract service types and config params using helpers
    service_types = _extract_service_types(manifest_data)
    config_params = _parse_config_parameters(manifest_data)

    # Extract external dependencies
    deps = manifest_data.get("dependencies", {})
    external_deps = deps.get("external", {}) if isinstance(deps, dict) else {}
    external_deps = external_deps or {}

    # Extract metadata
    metadata = manifest_data.get("metadata", {})
    safe_domain = metadata.get("safe_domain") if isinstance(metadata, dict) else None
    prohibited = metadata.get("prohibited", []) if isinstance(metadata, dict) else []

    # Extract platform requirements
    platform_requirements = manifest_data.get("platform_requirements", [])
    platform_requirements_rationale = manifest_data.get("platform_requirements_rationale")

    # Check platform availability using shared helper
    platform_available = _check_platform_requirements_satisfied(platform_requirements)

    return ModuleTypeInfo(
        module_id=module_id,
        name=module_info.get("name", module_id),
        version=module_info.get("version", "1.0.0"),
        description=module_info.get("description", ""),
        author=module_info.get("author", "Unknown"),
        module_source="modular",
        service_types=service_types,
        capabilities=manifest_data.get("capabilities", []),
        configuration_schema=config_params,
        requires_external_deps=bool(external_deps),
        external_dependencies=external_deps,
        is_mock=module_info.get("MOCK", False) or module_info.get("is_mock", False),
        safe_domain=safe_domain if isinstance(safe_domain, str) else None,
        prohibited=prohibited if isinstance(prohibited, list) else [],
        metadata=metadata if isinstance(metadata, dict) else None,
        platform_requirements=platform_requirements,
        platform_requirements_rationale=platform_requirements_rationale,
        platform_available=platform_available,
    )


# Entry point group for adapter discovery (defined in setup.py)
ADAPTER_ENTRY_POINT_GROUP = "ciris.adapters"


async def _read_manifest_async(manifest_path: Path) -> Optional[Dict[str, Any]]:
    """Read and parse a manifest file asynchronously."""
    import aiofiles

    try:
        async with aiofiles.open(manifest_path, mode="r") as f:
            content = await f.read()
        result: Dict[str, Any] = json.loads(content)
        return result
    except Exception:
        return None


def _try_load_service_manifest(service_name: str, apply_filter: bool = True) -> Optional[ModuleTypeInfo]:
    """Try to load a modular service manifest by name.

    Args:
        service_name: Name of the service to load
        apply_filter: If True, filter out mock/common/library modules

    Returns:
        ModuleTypeInfo if found and not filtered, None otherwise
    """
    import importlib

    try:
        submodule = importlib.import_module(f"ciris_adapters.{service_name}")
        if not hasattr(submodule, "__path__"):
            return None
        manifest_file = Path(submodule.__path__[0]) / MANIFEST_FILENAME
        if not manifest_file.exists():
            return None
        with open(manifest_file) as f:
            manifest_data = json.load(f)

        # Filter out mock/common/library modules from public listings
        if apply_filter and _should_filter_adapter(manifest_data):
            logger.debug("Filtering adapter %s from listings (mock/common/library)", service_name)
            return None

        return _parse_manifest_to_module_info(manifest_data, service_name)
    except Exception as e:
        logger.debug("Service %s not available: %s", service_name, e)
        return None


async def _discover_services_from_directory(services_base: Path) -> List[ModuleTypeInfo]:
    """Discover modular services by iterating the services directory.

    Filters out mock, common, and library modules from the listing.
    """
    adapters: List[ModuleTypeInfo] = []

    for item in services_base.iterdir():
        if not item.is_dir() or item.name.startswith("_"):
            continue

        # Try importlib-based loading first (Android compatibility)
        # Filter is applied inside _try_load_service_manifest
        module_info = _try_load_service_manifest(item.name)
        if module_info:
            adapters.append(module_info)
            logger.debug("Discovered modular service: %s", item.name)
            continue

        # Fallback to direct file access
        manifest_path = item / MANIFEST_FILENAME
        manifest_data = await _read_manifest_async(manifest_path)
        if manifest_data:
            # Apply filter for direct file access path
            if _should_filter_adapter(manifest_data):
                logger.debug("Filtering adapter %s from listings (mock/common/library)", item.name)
                continue

            module_info = _parse_manifest_to_module_info(manifest_data, item.name)
            adapters.append(module_info)
            logger.debug("Discovered modular service (direct): %s", item.name)

    return adapters


async def _discover_services_via_entry_points() -> List[ModuleTypeInfo]:
    """Discover modular services via importlib.metadata entry points.

    This is the preferred discovery method as it works across all platforms
    including Android where filesystem iteration may fail. Entry points are
    defined in setup.py under the 'ciris.adapters' group.

    Note: This function is async for API consistency even though the underlying
    operations are synchronous. This allows uniform await usage in callers.
    """
    from importlib.metadata import entry_points
    from typing import Iterable

    adapters: List[ModuleTypeInfo] = []

    try:
        # Get entry points - API varies by Python version
        eps = entry_points()

        # Try the modern API first (Python 3.10+)
        adapter_eps: Iterable[Any]
        if hasattr(eps, "select"):
            # Python 3.10+ with SelectableGroups
            adapter_eps = eps.select(group=ADAPTER_ENTRY_POINT_GROUP)
        elif isinstance(eps, dict):
            # Python 3.9 style dict-like access
            adapter_eps = eps.get(ADAPTER_ENTRY_POINT_GROUP, [])
        else:
            # Fallback - try to iterate or access as needed
            adapter_eps = getattr(eps, ADAPTER_ENTRY_POINT_GROUP, [])

        for ep in adapter_eps:
            module_info = _try_load_service_manifest(ep.name)
            if module_info:
                adapters.append(module_info)
                logger.debug("Discovered adapter via entry point: %s", ep.name)

    except Exception as e:
        logger.warning("Entry point discovery failed: %s", e)

    return adapters


async def _discover_adapters() -> List[ModuleTypeInfo]:
    """Discover all available modular services.

    Uses a fallback chain:
    1. Try filesystem iteration (fastest, works in dev)
    2. Fall back to entry points (works on Android and installed packages)
    """
    try:
        import ciris_adapters

        if not hasattr(ciris_adapters, "__path__"):
            return await _discover_services_via_entry_points()

        services_base = Path(ciris_adapters.__path__[0])
        logger.debug("Modular services base path: %s", services_base)

        try:
            return await _discover_services_from_directory(services_base)
        except OSError as e:
            logger.debug("iterdir failed (%s), falling back to entry points", e)
            return await _discover_services_via_entry_points()

    except ImportError as e:
        logger.debug("ciris_adapters not available: %s", e)
        return await _discover_services_via_entry_points()


@router.get("/adapters/types", response_model=SuccessResponse[ModuleTypesResponse])
async def list_module_types(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ModuleTypesResponse]:
    """
    List all available module/adapter types.

    Returns both core adapters (api, cli, discord) and modular services
    (mcp_client, mcp_server, reddit, etc.) with their typed configuration schemas.

    This endpoint is useful for:
    - Dynamic adapter loading UI
    - Configuration validation
    - Capability discovery

    Requires OBSERVER role.
    """
    try:
        # Get core adapters
        core_adapter_types = ["api", "cli", "discord"]
        core_modules = [_get_core_adapter_info(t) for t in core_adapter_types]

        # Discover modular services
        adapters = await _discover_adapters()

        response = ModuleTypesResponse(
            core_modules=core_modules,
            adapters=adapters,
            total_core=len(core_modules),
            total_adapters=len(adapters),
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error("Error listing module types: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


# NOTE: Static routes like /adapters/persisted and /adapters/configurable must come BEFORE
# the parametrized route /adapters/{adapter_id} to avoid being captured by the path parameter.


class PersistedConfigsResponse(BaseModel):
    """Response for persisted adapter configurations."""

    persisted_configs: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict,
        description="Map of adapter_type to configuration data",
    )
    count: int = Field(..., description="Number of persisted configurations")


@router.get(
    "/adapters/persisted",
    response_model=SuccessResponse[PersistedConfigsResponse],
)
async def list_persisted_configurations(
    request: Request,
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[PersistedConfigsResponse]:
    """
    List all persisted adapter configurations.

    Returns configurations that are set to load on startup.

    Requires ADMIN role.
    """
    try:
        adapter_config_service = getattr(request.app.state, "adapter_configuration_service", None)
        config_service = getattr(request.app.state, "config_service", None)

        if not adapter_config_service:
            raise HTTPException(status_code=503, detail=ERROR_ADAPTER_CONFIG_SERVICE_NOT_AVAILABLE)

        persisted_configs: Dict[str, Dict[str, Any]] = {}
        if config_service:
            persisted_configs = await adapter_config_service.load_persisted_configs(config_service)

        response = PersistedConfigsResponse(
            persisted_configs=persisted_configs,
            count=len(persisted_configs),
        )
        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing persisted configurations: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RemovePersistedResponse(BaseModel):
    """Response for removing a persisted configuration."""

    success: bool = Field(..., description="Whether the removal succeeded")
    adapter_type: str = Field(..., description="Adapter type that was removed")
    message: str = Field(..., description="Status message")


@router.delete(
    "/adapters/{adapter_type}/persisted",
    response_model=SuccessResponse[RemovePersistedResponse],
)
async def remove_persisted_configuration(
    adapter_type: str,
    request: Request,
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[RemovePersistedResponse]:
    """
    Remove a persisted adapter configuration.

    This prevents the adapter from being automatically loaded on startup.

    Requires ADMIN role.
    """
    try:
        adapter_config_service = getattr(request.app.state, "adapter_configuration_service", None)
        config_service = getattr(request.app.state, "config_service", None)

        if not adapter_config_service:
            raise HTTPException(status_code=503, detail=ERROR_ADAPTER_CONFIG_SERVICE_NOT_AVAILABLE)

        if not config_service:
            raise HTTPException(status_code=503, detail="Config service not available")

        success = await adapter_config_service.remove_persisted_config(
            adapter_type=adapter_type,
            config_service=config_service,
        )

        if success:
            message = f"Removed persisted configuration for {adapter_type}"
        else:
            message = f"No persisted configuration found for {adapter_type}"

        response = RemovePersistedResponse(
            success=success,
            adapter_type=adapter_type,
            message=message,
        )
        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error removing persisted configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _get_adapter_config_service(request: Request) -> Any:
    """Get AdapterConfigurationService from app state."""
    service = getattr(request.app.state, "adapter_configuration_service", None)
    if not service:
        raise HTTPException(status_code=503, detail=ERROR_ADAPTER_CONFIG_SERVICE_NOT_AVAILABLE)
    return service


@router.get("/adapters/configurable", response_model=SuccessResponse[ConfigurableAdaptersResponse])
async def list_configurable_adapters(
    request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[ConfigurableAdaptersResponse]:
    """
    List adapters that support interactive configuration.

    Returns information about all adapters that have defined interactive
    configuration workflows, including their workflow types and step counts.

    Requires ADMIN role.
    """
    try:
        config_service = _get_adapter_config_service(request)
        adapter_types = config_service.get_configurable_adapters()

        # Build detailed info for each adapter
        adapters = []
        for adapter_type in adapter_types:
            manifest = config_service._adapter_manifests.get(adapter_type)
            if not manifest:
                continue

            # Check if any step is OAuth
            requires_oauth = any(step.step_type == "oauth" for step in manifest.steps)

            adapters.append(
                ConfigurableAdapterInfo(
                    adapter_type=adapter_type,
                    name=adapter_type.replace("_", " ").title(),
                    description=f"Interactive configuration for {adapter_type}",
                    workflow_type=manifest.workflow_type,
                    step_count=len(manifest.steps),
                    requires_oauth=requires_oauth,
                    steps=[
                        ConfigStepInfo(
                            step_id=step.step_id,
                            step_type=step.step_type,
                            title=step.title,
                            description=step.description,
                            optional=getattr(step, "optional", False),
                        )
                        for step in manifest.steps
                    ],
                )
            )

        response = ConfigurableAdaptersResponse(adapters=adapters, total_count=len(adapters))
        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing configurable adapters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/{adapter_id}", response_model=SuccessResponse[AdapterStatusSchema])
async def get_adapter_status(
    adapter_id: str, request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[AdapterStatusSchema]:
    """
    Get detailed status of a specific adapter.

    Returns comprehensive information about an adapter instance
    including configuration, metrics, and service registrations.
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Get adapter info from runtime control service
        adapter_info = await runtime_control.get_adapter_info(adapter_id)

        if not adapter_info:
            raise HTTPException(status_code=404, detail=f"Adapter '{adapter_id}' not found")

        # Debug logging
        logger.info(f"Adapter info type: {type(adapter_info)}, value: {adapter_info}")

        # Convert to response format
        metrics_dict = None
        if adapter_info.messages_processed > 0 or adapter_info.error_count > 0:
            metrics = AdapterMetrics(
                messages_processed=adapter_info.messages_processed,
                errors_count=adapter_info.error_count,
                uptime_seconds=(
                    (datetime.now(timezone.utc) - adapter_info.started_at).total_seconds()
                    if adapter_info.started_at
                    else 0
                ),
                last_error=adapter_info.last_error,
                last_error_time=None,
            )
            metrics_dict = metrics.__dict__

        status = AdapterStatusSchema(
            adapter_id=adapter_info.adapter_id,
            adapter_type=adapter_info.adapter_type,
            is_running=adapter_info.status == "RUNNING",
            loaded_at=adapter_info.started_at,
            services_registered=[],  # Not exposed via AdapterInfo
            config_params=AdapterConfig(adapter_type=adapter_info.adapter_type, enabled=True, settings={}),
            metrics=metrics_dict,
            last_activity=None,
            tools=adapter_info.tools,  # Include tools information
        )

        return SuccessResponse(data=status)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting adapter status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/adapters/{adapter_type}", response_model=SuccessResponse[AdapterOperationResult])
async def load_adapter(
    adapter_type: str,
    body: AdapterActionRequest,
    request: Request,
    adapter_id: Optional[str] = None,
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[AdapterOperationResult]:
    """
    Load a new adapter instance.

    Dynamically loads and starts a new adapter of the specified type.
    Requires ADMIN role.

    Adapter types: cli, api, discord, mcp, mcp_server

    Args:
        adapter_type: Type of adapter to load
        adapter_id: Optional unique ID for the adapter (auto-generated if not provided)
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Generate adapter ID if not provided
        import uuid

        if not adapter_id:
            adapter_id = f"{adapter_type}_{uuid.uuid4().hex[:8]}"

        logger.info(f"[LOAD_ADAPTER] Loading adapter: type={adapter_type}, id={adapter_id}")
        logger.debug(f"[LOAD_ADAPTER] Config: {body.config}, auto_start={body.auto_start}")

        result = await runtime_control.load_adapter(
            adapter_type=adapter_type, adapter_id=adapter_id, config=body.config, auto_start=body.auto_start
        )

        logger.info(
            f"[LOAD_ADAPTER] Result: success={result.success}, adapter_id={result.adapter_id}, error={result.error}"
        )

        # Convert response
        response = AdapterOperationResult(
            success=result.success,
            adapter_id=result.adapter_id,
            adapter_type=adapter_type,
            message=result.error if not result.success else f"Adapter {result.adapter_id} loaded successfully",
            error=result.error,
            details={"timestamp": result.timestamp.isoformat()},
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"[LOAD_ADAPTER] Error loading adapter type={adapter_type}, id={adapter_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/adapters/{adapter_id}", response_model=SuccessResponse[AdapterOperationResult])
async def unload_adapter(
    adapter_id: str, request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[AdapterOperationResult]:
    """
    Unload an adapter instance.

    Stops and removes an adapter from the runtime.
    Will fail if it's the last communication-capable adapter.
    Requires ADMIN role.
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Unload adapter through runtime control service
        result = await runtime_control.unload_adapter(
            adapter_id=adapter_id, force=False  # Never force, respect safety checks
        )

        # Log failures explicitly
        if not result.success:
            logger.error(f"Adapter unload failed: {result.error}")

        # Convert response
        response = AdapterOperationResult(
            success=result.success,
            adapter_id=result.adapter_id,
            adapter_type=result.adapter_type,
            message=result.error if not result.success else f"Adapter {result.adapter_id} unloaded successfully",
            error=result.error,
            details={"timestamp": result.timestamp.isoformat()},
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"Error unloading adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/adapters/{adapter_id}/reload", response_model=SuccessResponse[AdapterOperationResult])
async def reload_adapter(
    adapter_id: str, body: AdapterActionRequest, request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[AdapterOperationResult]:
    """
    Reload an adapter with new configuration.

    Stops the adapter and restarts it with new configuration.
    Useful for applying configuration changes without full restart.
    Requires ADMIN role.
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Get current adapter info to preserve type
        adapter_info = await runtime_control.get_adapter_info(adapter_id)
        if not adapter_info:
            raise HTTPException(status_code=404, detail=f"Adapter '{adapter_id}' not found")

        # First unload the adapter
        unload_result = await runtime_control.unload_adapter(adapter_id, force=False)
        if not unload_result.success:
            raise HTTPException(status_code=400, detail=f"Failed to unload adapter: {unload_result.error}")

        # Then reload with new config
        load_result = await runtime_control.load_adapter(
            adapter_type=adapter_info.adapter_type,
            adapter_id=adapter_id,
            config=body.config,
            auto_start=body.auto_start,
        )

        # Convert response
        response = AdapterOperationResult(
            success=load_result.success,
            adapter_id=load_result.adapter_id,
            adapter_type=adapter_info.adapter_type,
            message=(
                f"Adapter {adapter_id} reloaded successfully"
                if load_result.success
                else f"Reload failed: {load_result.error}"
            ),
            error=load_result.error,
            details={"timestamp": load_result.timestamp.isoformat()},
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reloading adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Adapter Configuration Workflow Endpoints


@router.post("/adapters/{adapter_type}/configure/start", response_model=SuccessResponse[ConfigurationSessionResponse])
async def start_adapter_configuration(
    adapter_type: str,
    request: Request,
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[ConfigurationSessionResponse]:
    """
    Start interactive configuration session for an adapter.

    Creates a new configuration session and returns the session ID along with
    information about the first step in the workflow.

    Requires ADMIN role.
    """
    try:
        config_service = _get_adapter_config_service(request)

        # Start the session
        session = await config_service.start_session(adapter_type=adapter_type, user_id=auth.user_id)

        # Get manifest to access steps
        manifest = config_service._adapter_manifests.get(adapter_type)
        if not manifest:
            raise HTTPException(status_code=404, detail=f"Adapter '{adapter_type}' not found")

        # Get current step
        current_step = manifest.steps[0] if manifest.steps else None

        response = ConfigurationSessionResponse(
            session_id=session.session_id,
            adapter_type=session.adapter_type,
            status=session.status.value,
            current_step_index=session.current_step_index,
            current_step=current_step,
            total_steps=len(manifest.steps),
            created_at=session.created_at,
        )

        return SuccessResponse(data=response)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting configuration session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/configure/{session_id}", response_model=SuccessResponse[ConfigurationStatusResponse])
async def get_configuration_status(
    session_id: str,
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[ConfigurationStatusResponse]:
    """
    Get current status of a configuration session.

    Returns complete session state including current step, collected configuration,
    and session status.

    Requires OBSERVER role.
    """
    try:
        config_service = _get_adapter_config_service(request)
        session = config_service.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

        # Get manifest to access steps
        manifest = config_service._adapter_manifests.get(session.adapter_type)
        if not manifest:
            raise HTTPException(status_code=500, detail=f"Manifest for '{session.adapter_type}' not found")

        # Get current step
        current_step = None
        if session.current_step_index < len(manifest.steps):
            current_step = manifest.steps[session.current_step_index]

        response = ConfigurationStatusResponse(
            session_id=session.session_id,
            adapter_type=session.adapter_type,
            status=session.status.value,
            current_step_index=session.current_step_index,
            current_step=current_step,
            total_steps=len(manifest.steps),
            collected_config=session.collected_config,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting configuration status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/adapters/configure/{session_id}/step", response_model=SuccessResponse[StepExecutionResponse])
async def execute_configuration_step(
    session_id: str,
    request: Request,
    body: StepExecutionRequest = Body(...),
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[StepExecutionResponse]:
    """
    Execute the current configuration step.

    The body contains step-specific data such as user selections, input values,
    or OAuth callback data. The step type determines what data is expected.

    Requires ADMIN role.
    """
    try:
        config_service = _get_adapter_config_service(request)

        # Execute the step
        result = await config_service.execute_step(session_id, body.step_data)

        response = StepExecutionResponse(
            step_id=result.step_id,
            success=result.success,
            data=result.data,
            next_step_index=result.next_step_index,
            error=result.error,
            awaiting_callback=result.awaiting_callback,
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing configuration step: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/configure/{session_id}/status")
async def get_session_status(
    session_id: str,
    request: Request,
) -> SuccessResponse[ConfigurationSessionResponse]:
    """
    Get the current status of a configuration session.

    Useful for polling after OAuth callback to check if authentication completed.
    """
    try:
        config_service = _get_adapter_config_service(request)
        session = config_service.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get adapter steps from the adapter manifest (InteractiveConfiguration)
        current_step = None
        total_steps = 0
        manifest = config_service._adapter_manifests.get(session.adapter_type)
        if manifest and manifest.steps:
            steps = manifest.steps
            total_steps = len(steps)
            if session.current_step_index < len(steps):
                # Use the ConfigurationStep directly from the manifest
                current_step = steps[session.current_step_index]

        response = ConfigurationSessionResponse(
            session_id=session.session_id,
            adapter_type=session.adapter_type,
            status=session.status.value,
            current_step_index=session.current_step_index,
            current_step=current_step,
            total_steps=total_steps,
            created_at=session.created_at,
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/configure/{session_id}/oauth/callback")
async def oauth_callback(
    session_id: str,
    code: str,
    state: str,
    request: Request,
) -> Response:
    """
    Handle OAuth callback from external service.

    This endpoint is called by OAuth providers after user authorization.
    It processes the authorization code and advances the configuration workflow.
    Returns HTML that redirects back to the app or shows success message.

    No authentication required (OAuth state validation provides security).
    """
    logger.info("=" * 60)
    logger.info("[OAUTH CALLBACK] *** CALLBACK RECEIVED ***")
    logger.info(f"[OAUTH CALLBACK] Full URL: {request.url}")
    logger.info(f"[OAUTH CALLBACK] Path: {request.url.path}")
    logger.info(f"[OAUTH CALLBACK] session_id: {session_id}")
    logger.info(f"[OAUTH CALLBACK] state: {state}")
    logger.info(f"[OAUTH CALLBACK] code length: {len(code)}")
    logger.info(
        f"[OAUTH CALLBACK] code preview: {code[:20]}..." if len(code) > 20 else f"[OAUTH CALLBACK] code: {code}"
    )
    logger.info(f"[OAUTH CALLBACK] Headers: {dict(request.headers)}")
    logger.info("=" * 60)
    try:
        config_service = _get_adapter_config_service(request)

        # Verify session exists and state matches
        session = config_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if state != session_id:
            raise HTTPException(status_code=400, detail="Invalid OAuth state")

        # Execute the OAuth callback step
        result = await config_service.execute_step(session_id, {"code": code, "state": state})

        if not result.success:
            error_html = f"""<!DOCTYPE html>
<html>
<head><title>OAuth Failed</title></head>
<body style="font-family: sans-serif; text-align: center; padding: 50px;">
    <h1 style="color: #d32f2f;">Authentication Failed</h1>
    <p>{html.escape(result.error or "OAuth callback failed")}</p>
    <p>Please close this window and try again in the app.</p>
</body>
</html>"""
            return Response(content=error_html, media_type="text/html")

        # Return HTML that tells user to go back to app
        # Try to use deep link to return to app automatically
        success_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>OAuth Success</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family: sans-serif; text-align: center; padding: 50px; background: #f5f5f5;">
    <div style="background: white; padding: 40px; border-radius: 10px; max-width: 400px; margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        <h1 style="color: #4caf50; margin-bottom: 20px;">✓ Connected!</h1>
        <p style="color: #666; font-size: 18px;">Authentication successful.</p>
        <p style="color: #888; margin-top: 20px;">You can close this window and return to the CIRIS app.</p>
        <p style="color: #aaa; font-size: 12px; margin-top: 30px;">Session: {html.escape(session_id[:8])}...</p>
    </div>
</body>
</html>"""
        return Response(content=success_html, media_type="text/html")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling OAuth callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/oauth/callback")
async def oauth_deeplink_callback(
    code: str,
    state: str,
    request: Request,
    provider: Optional[str] = None,
    source: Optional[str] = None,
) -> SuccessResponse[Dict[str, Any]]:
    """
    Handle OAuth callback forwarded from Android deep link (ciris://oauth/callback).

    This endpoint receives OAuth callbacks that were forwarded from OAuthCallbackActivity
    on Android. The Android app uses a deep link (ciris://oauth/callback) to receive
    the OAuth redirect from the system browser, then forwards to this endpoint.

    This is a generic endpoint that works for any OAuth2 provider (Home Assistant,
    Discord, Google, Microsoft, Reddit, etc.) - the state parameter contains the
    session_id which identifies the configuration session.

    Args:
        code: Authorization code from OAuth provider
        state: State parameter (contains session_id for session lookup)
        provider: Optional provider hint (home_assistant, discord, etc.)
        source: Source of callback (deeplink indicates forwarded from Android)

    Returns:
        Success response with callback processing result
    """
    logger.info("=" * 60)
    logger.info("[OAUTH DEEPLINK CALLBACK] *** FORWARDED CALLBACK RECEIVED ***")
    logger.info(f"[OAUTH DEEPLINK CALLBACK] Full URL: {request.url}")
    logger.info(f"[OAUTH DEEPLINK CALLBACK] state (session_id): {state}")
    logger.info(f"[OAUTH DEEPLINK CALLBACK] provider: {provider}")
    logger.info(f"[OAUTH DEEPLINK CALLBACK] source: {source}")
    logger.info(f"[OAUTH DEEPLINK CALLBACK] code length: {len(code)}")
    logger.info("=" * 60)

    try:
        config_service = _get_adapter_config_service(request)

        # The state parameter IS the session_id
        session_id = state

        # Handle provider-prefixed state (e.g., "ha:actual_session_id")
        if ":" in state:
            parts = state.split(":", 1)
            if len(parts) == 2 and len(parts[0]) < 20:
                # Looks like "provider:session_id"
                provider = provider or parts[0]
                session_id = parts[1]
                logger.info(f"[OAUTH DEEPLINK CALLBACK] Extracted provider={provider}, session_id={session_id}")

        # Verify session exists
        session = config_service.get_session(session_id)
        if not session:
            logger.error(f"[OAUTH DEEPLINK CALLBACK] Session not found: {session_id}")
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        # Execute the OAuth callback step
        result = await config_service.execute_step(session_id, {"code": code, "state": state})

        if not result.success:
            logger.error(f"[OAUTH DEEPLINK CALLBACK] OAuth step failed: {result.error}")
            raise HTTPException(status_code=400, detail=result.error or "OAuth callback failed")

        logger.info(f"[OAUTH DEEPLINK CALLBACK] Successfully processed OAuth callback for session {session_id}")

        return SuccessResponse(
            data={
                "session_id": session_id,
                "success": True,
                "message": "OAuth callback processed successfully",
                "next_step": result.next_step_index,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OAUTH DEEPLINK CALLBACK] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _get_runtime_control_service_for_adapter_load(request: Request) -> Any:
    """Get RuntimeControlService for adapter loading (returns None if unavailable)."""
    from ciris_engine.schemas.runtime.enums import ServiceType

    runtime_control_service = getattr(request.app.state, "main_runtime_control_service", None)
    if runtime_control_service:
        return runtime_control_service

    runtime_control_service = getattr(request.app.state, "runtime_control_service", None)
    if runtime_control_service:
        return runtime_control_service

    service_registry = getattr(request.app.state, "service_registry", None)
    if service_registry:
        return await service_registry.get_service(handler="api", service_type=ServiceType.RUNTIME_CONTROL)

    return None


async def _load_adapter_after_config(request: Request, session: Any) -> str:
    """Load adapter after configuration and return status message."""
    import uuid

    runtime_control_service = await _get_runtime_control_service_for_adapter_load(request)
    if not runtime_control_service:
        logger.warning("[COMPLETE_CONFIG] RuntimeControlService not available, adapter not loaded")
        return " - runtime control service unavailable"

    logger.info("[COMPLETE_CONFIG] Loading adapter via RuntimeControlService.load_adapter")
    adapter_config = dict(session.collected_config)
    adapter_id = f"{session.adapter_type}_{uuid.uuid4().hex[:8]}"

    load_result = await runtime_control_service.load_adapter(
        adapter_type=session.adapter_type,
        adapter_id=adapter_id,
        config=adapter_config,
    )

    if load_result.success:
        logger.info(f"[COMPLETE_CONFIG] Adapter loaded successfully: {adapter_id}")
        return f" - adapter '{adapter_id}' loaded and started"
    else:
        logger.error(f"[COMPLETE_CONFIG] Adapter load failed: {load_result.error}")
        return f" - adapter load failed: {load_result.error}"


async def _persist_config_if_requested(
    body: ConfigurationCompleteRequest, session: Any, adapter_config_service: Any, request: Request
) -> tuple[bool, str]:
    """Persist configuration if requested. Returns (persisted, message_suffix)."""
    if not body.persist:
        return False, ""

    graph_config_service = getattr(request.app.state, "config_service", None)
    persisted = await adapter_config_service.persist_adapter_config(
        adapter_type=session.adapter_type,
        config=session.collected_config,
        config_service=graph_config_service,
    )
    return persisted, " and persisted for startup" if persisted else " (persistence failed)"


@router.post("/adapters/configure/{session_id}/complete", response_model=SuccessResponse[ConfigurationCompleteResponse])
async def complete_configuration(
    session_id: str,
    request: Request,
    body: ConfigurationCompleteRequest = Body(default=ConfigurationCompleteRequest()),
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[ConfigurationCompleteResponse]:
    """
    Finalize and apply the configuration.

    Validates the collected configuration and applies it to the adapter.
    Once completed, the adapter should be ready to use with the new configuration.

    If `persist` is True, the configuration will be saved for automatic loading
    on startup, allowing the adapter to be automatically configured when the
    system restarts.

    Requires ADMIN role.
    """
    try:
        adapter_config_service = _get_adapter_config_service(request)

        session = adapter_config_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

        success = await adapter_config_service.complete_session(session_id)
        persisted = False
        message = ""

        if success:
            message = f"Configuration applied successfully for {session.adapter_type}"
            logger.info(f"[COMPLETE_CONFIG] Config applied, attempting to start adapter for {session.adapter_type}")

            try:
                message += await _load_adapter_after_config(request, session)
            except Exception as e:
                logger.error(f"Error loading adapter after config: {e}", exc_info=True)
                message += f" - adapter load error: {e}"

            persisted, persist_msg = await _persist_config_if_requested(body, session, adapter_config_service, request)
            message += persist_msg
        else:
            message = f"Configuration validation or application failed for {session.adapter_type}"

        response = ConfigurationCompleteResponse(
            success=success,
            adapter_type=session.adapter_type,
            message=message,
            applied_config=session.collected_config if success else {},
            persisted=persisted,
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Tool endpoints
@router.get("/tools")
async def get_available_tools(request: Request, auth: AuthContext = Depends(require_observer)) -> JSONDict:
    """
    Get list of all available tools from all tool providers.

    Returns tools from:
    - Core tool services (secrets, self_help)
    - Adapter tool services (API, Discord, etc.)

    Requires OBSERVER role.
    """

    try:
        all_tools = []
        tool_providers = set()  # Use set to avoid counting duplicates

        # Get all tool providers from the service registry
        service_registry = getattr(request.app.state, "service_registry", None)
        if service_registry:
            # Get provider info for TOOL services
            provider_info = service_registry.get_provider_info(service_type=ServiceType.TOOL.value)
            provider_info.get("services", {}).get(ServiceType.TOOL.value, [])

            # Get the actual provider instances from the registry
            if hasattr(service_registry, "_services") and ServiceType.TOOL in service_registry._services:
                for provider_data in service_registry._services[ServiceType.TOOL]:
                    try:
                        provider = provider_data.instance
                        provider_name = provider.__class__.__name__
                        tool_providers.add(provider_name)  # Use add to avoid duplicates

                        if hasattr(provider, "get_all_tool_info"):
                            # Modern interface with ToolInfo objects
                            tool_infos = await provider.get_all_tool_info()
                            for info in tool_infos:
                                all_tools.append(
                                    ToolInfoResponse(
                                        name=info.name,
                                        description=info.description,
                                        provider=provider_name,
                                        parameters=info.parameters if hasattr(info, "parameters") else None,
                                        category=getattr(info, "category", "general"),
                                        cost=getattr(info, "cost", 0.0),
                                        when_to_use=getattr(info, "when_to_use", None),
                                    )
                                )
                        elif hasattr(provider, "list_tools"):
                            # Legacy interface
                            tool_names = await provider.list_tools()
                            for name in tool_names:
                                all_tools.append(
                                    ToolInfoResponse(
                                        name=name,
                                        description=f"{name} tool",
                                        provider=provider_name,
                                        parameters=None,
                                        category="general",
                                        cost=0.0,
                                        when_to_use=None,
                                    )
                                )
                    except Exception as e:
                        logger.warning(f"Failed to get tools from provider {provider_name}: {e}", exc_info=True)

        # Deduplicate tools by name (in case multiple providers offer the same tool)
        seen_tools = {}
        unique_tools = []
        for tool in all_tools:
            if tool.name not in seen_tools:
                seen_tools[tool.name] = tool
                unique_tools.append(tool)
            else:
                # If we see the same tool from multiple providers, add provider info
                existing = seen_tools[tool.name]
                if existing.provider != tool.provider:
                    existing.provider = f"{existing.provider}, {tool.provider}"

        # Log provider information for debugging
        logger.info(f"Tool providers found: {len(tool_providers)} unique providers: {tool_providers}")
        logger.info(f"Total tools collected: {len(all_tools)}, Unique tools: {len(unique_tools)}")
        logger.info(f"Tool provider summary: {list(tool_providers)}")

        # Create response with additional metadata for tool providers
        # Since ResponseMetadata is immutable, we need to create a dict response
        return {
            "data": [tool.model_dump() for tool in unique_tools],
            "metadata": {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "request_id": None,
                "duration_ms": None,
                "providers": list(tool_providers),
                "provider_count": len(tool_providers),
                "total_tools": len(unique_tools),
            },
        }

    except Exception as e:
        logger.error(f"Error getting available tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))
