"""
System management endpoints for CIRIS API v3.0 (Simplified).

Consolidates health, time, resources, runtime control, services, and shutdown
into a unified system operations interface.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field, ValidationError, field_serializer

from ciris_engine.constants import CIRIS_VERSION
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolParameterSchema
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.api.telemetry import ServiceMetrics, TimeSyncStatus
from ciris_engine.schemas.runtime.adapter_management import (
    AdapterConfig,
    AdapterListResponse,
    AdapterMetrics,
    AdapterOperationResult,
)
from ciris_engine.schemas.runtime.adapter_management import RuntimeAdapterStatus as AdapterStatusSchema
from ciris_engine.schemas.runtime.enums import ServiceType
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
                        logger.warning(
                            f"Service health check failed for {service_type.value}: Service may not implement is_healthy()"
                        )
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
    # Validate confirmation
    if not body.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required (confirm=true)")

    # Get shutdown service from runtime
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime:
        raise HTTPException(status_code=503, detail="Runtime not available")

    shutdown_service = getattr(runtime, "shutdown_service", None)
    if not shutdown_service:
        raise HTTPException(status_code=503, detail=ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE)

    try:
        # Check if already shutting down
        if shutdown_service.is_shutdown_requested():
            existing_reason = shutdown_service.get_shutdown_reason()
            raise HTTPException(status_code=409, detail=f"Shutdown already requested: {existing_reason}")

        # Build shutdown reason
        reason = f"{body.reason} (API shutdown by {auth.user_id})"
        if body.force:
            reason += " [FORCED]"

        # Sanitize reason for logging to prevent log injection
        # Replace newlines and control characters with spaces
        safe_reason = "".join(c if c.isprintable() and c not in "\n\r\t" else " " for c in reason)

        # Log shutdown request with sanitized reason
        logger.warning(f"SHUTDOWN requested: {safe_reason}")

        # Audit shutdown request - especially important for service tokens
        audit_service = getattr(request.app.state, "audit_service", None)
        if audit_service:
            from ciris_engine.schemas.services.graph.audit import AuditEventData

            # Check if this is a service account
            is_service_account = auth.role.value == "SERVICE_ACCOUNT"
            audit_event = AuditEventData(
                entity_id="system",
                actor=auth.user_id,
                outcome="initiated",
                severity="high" if body.force else "warning",
                action="system_shutdown",
                resource="system",
                reason=safe_reason,
                metadata={
                    "force": body.force,
                    "is_service_account": is_service_account,
                    "auth_role": auth.role.value,
                    "ip_address": request.client.host if request.client else "unknown",
                    "user_agent": request.headers.get("user-agent", "unknown"),
                    "request_path": str(request.url.path),
                },
            )
            import asyncio

            # Store task reference to prevent garbage collection
            # Using _ prefix to indicate we're intentionally not awaiting
            _audit_task = asyncio.create_task(audit_service.log_event("system_shutdown_request", audit_event))

        # Execute shutdown - use emergency_shutdown for force=true to skip thought processing
        if body.force:
            # Forced shutdown: bypass thought processing, immediate termination
            await shutdown_service.emergency_shutdown(reason, timeout_seconds=5)
        else:
            # Normal shutdown: allow thoughtful consideration via runtime
            # The runtime's request_shutdown will call the shutdown service AND set global flags
            runtime.request_shutdown(reason)

        response = ShutdownResponse(
            status="initiated",
            message=f"System shutdown initiated: {reason}",
            shutdown_initiated=True,
            timestamp=datetime.now(timezone.utc),
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating shutdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    adapter_type: str, body: AdapterActionRequest, request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[AdapterOperationResult]:
    """
    Load a new adapter instance.

    Dynamically loads and starts a new adapter of the specified type.
    Requires ADMIN role.

    Adapter types: cli, api, discord
    """
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Generate adapter ID if not provided
        import uuid

        adapter_id = f"{adapter_type}_{uuid.uuid4().hex[:8]}"

        # Load adapter through runtime control service
        logger.info(
            f"Loading adapter through runtime_control: {runtime_control.__class__.__name__} (id: {id(runtime_control)})"
        )
        if hasattr(runtime_control, "adapter_manager"):
            logger.info(f"Runtime control adapter_manager id: {id(runtime_control.adapter_manager)}")

        result = await runtime_control.load_adapter(
            adapter_type=adapter_type, adapter_id=adapter_id, config=body.config, auto_start=body.auto_start
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
        logger.error(f"Error loading adapter: {e}")
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
                f"Adapter reloaded: {load_result.message}"
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
