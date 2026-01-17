"""
System route helpers - Common functions used across system endpoints.

This module consolidates helper functions to avoid code duplication
and improve testability.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException, Request

from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.api.telemetry import ServiceMetrics
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core.runtime import ProcessorStatus
from ciris_engine.schemas.types import JSONDict

from ...constants import (
    ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE,
    ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE,
)
from .schemas import RuntimeControlResponse, ServiceStatus

logger = logging.getLogger(__name__)


# ============================================================================
# Time and Uptime Helpers
# ============================================================================


def get_system_uptime(request: Request) -> float:
    """Get system uptime in seconds."""
    time_service: Optional[TimeServiceProtocol] = getattr(request.app.state, "time_service", None)
    start_time = getattr(time_service, "_start_time", None) if time_service else None
    current_time = time_service.now() if time_service else datetime.now(timezone.utc)
    return (current_time - start_time).total_seconds() if start_time else 0.0


def get_current_time(request: Request) -> datetime:
    """Get current system time."""
    time_service: Optional[TimeServiceProtocol] = getattr(request.app.state, "time_service", None)
    return time_service.now() if time_service else datetime.now(timezone.utc)


# ============================================================================
# Cognitive State Helpers
# ============================================================================


def get_cognitive_state_safe(request: Request) -> Optional[str]:
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


def get_cognitive_state(request: Request) -> Optional[str]:
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


# ============================================================================
# Initialization Helpers
# ============================================================================


def check_initialization_status(request: Request) -> bool:
    """Check if system initialization is complete."""
    init_service = getattr(request.app.state, "initialization_service", None)
    if init_service and hasattr(init_service, "is_initialized"):
        result: bool = init_service.is_initialized()
        return result
    return True


# ============================================================================
# Service Health Helpers
# ============================================================================


async def check_provider_health(provider: Any) -> bool:
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


async def collect_service_health(request: Request) -> Dict[str, Dict[str, int]]:
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
                    if await check_provider_health(provider):
                        healthy_count += 1
                    else:
                        logger.debug(f"Service health check returned unhealthy for {service_type.value}")
                services[service_type.value] = {"available": len(providers), "healthy": healthy_count}
    except Exception as e:
        logger.error(f"Error checking service health: {e}")

    return services


def check_processor_via_runtime(runtime: Any) -> Optional[bool]:
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


def get_runtime_control_from_app(request: Request) -> Any:
    """Get RuntimeControlService from app state, trying multiple locations."""
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    return runtime_control


async def check_health_via_runtime_control(runtime_control: Any) -> Optional[bool]:
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


async def check_processor_health(request: Request) -> bool:
    """Check if processor thread is healthy."""
    runtime = getattr(request.app.state, "runtime", None)

    # First try: Check the runtime's agent_processor directly
    runtime_result = check_processor_via_runtime(runtime)
    if runtime_result is True:
        return True

    # Second try: Use RuntimeControlService if available (for full API)
    runtime_control = get_runtime_control_from_app(request)
    control_result = await check_health_via_runtime_control(runtime_control)
    if control_result is not None:
        return control_result

    # If we have a runtime with agent_processor, consider healthy
    if runtime and getattr(runtime, "agent_processor", None) is not None:
        return True

    return False


def determine_overall_status(init_complete: bool, processor_healthy: bool, services: Dict[str, Dict[str, int]]) -> str:
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


# ============================================================================
# Runtime Control Helpers
# ============================================================================


def get_runtime_control_service(request: Request) -> Any:
    """Get runtime control service from request, trying main service first."""
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)
    return runtime_control


def validate_runtime_action(action: str) -> None:
    """Validate the runtime control action."""
    valid_actions = ["pause", "resume", "state"]
    if action not in valid_actions:
        raise HTTPException(status_code=400, detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}")


async def execute_pause_action(runtime_control: Any, reason: Optional[str]) -> bool:
    """Execute pause action and return success status."""
    import inspect

    sig = inspect.signature(runtime_control.pause_processing)
    if len(sig.parameters) > 0:  # API runtime control service
        success: bool = await runtime_control.pause_processing(reason or "API request")
    else:  # Main runtime control service
        control_response = await runtime_control.pause_processing()
        success = control_response.success
    return success


def extract_pipeline_state_info(
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


def create_pause_response(
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


async def execute_resume_action(runtime_control: Any) -> RuntimeControlResponse:
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


async def execute_state_action(runtime_control: Any) -> RuntimeControlResponse:
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


def create_final_response(
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


# ============================================================================
# Service Status Helpers
# ============================================================================


def parse_direct_service_key(service_key: str) -> tuple[str, str]:
    """Parse direct service key and return service_type and display_name."""
    parts = service_key.split(".")
    if len(parts) >= 3:
        service_type = parts[1]  # 'graph', 'infrastructure', etc.
        service_name = parts[2]  # 'memory_service', 'time_service', etc.

        # Convert snake_case to PascalCase for display
        display_name = "".join(word.capitalize() for word in service_name.split("_"))
        return service_type, display_name
    return "unknown", service_key


def get_service_category(service_type_enum: str) -> str:
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


def create_display_name(service_type_enum: str, service_name: str, adapter_prefix: str) -> str:
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


def map_service_type_enum(service_type_enum: str, service_name: str, adapter_prefix: str) -> tuple[str, str]:
    """Map ServiceType enum to category and create display name."""
    service_type = get_service_category(service_type_enum)
    display_name = create_display_name(service_type_enum, service_name, adapter_prefix)

    return service_type, display_name


def parse_registry_service_key(service_key: str) -> tuple[str, str]:
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
    service_type, display_name = map_service_type_enum(service_type_enum, service_name, adapter_prefix)

    return service_type, display_name


def parse_service_key(service_key: str) -> tuple[str, str]:
    """Parse any service key and return service_type and display_name."""
    parts = service_key.split(".")

    # Handle direct services (format: direct.service_type.service_name)
    if service_key.startswith("direct.") and len(parts) >= 3:
        return parse_direct_service_key(service_key)

    # Handle registry services (format: registry.ServiceType.ENUM.ServiceName_id)
    elif service_key.startswith("registry.") and len(parts) >= 3:
        return parse_registry_service_key(service_key)

    else:
        return "unknown", service_key


def create_service_status(service_key: str, details: JSONDict) -> ServiceStatus:
    """Create ServiceStatus from service key and details."""
    service_type, display_name = parse_service_key(service_key)

    return ServiceStatus(
        name=display_name,
        type=service_type,
        healthy=details.get("healthy", False),
        available=details.get("healthy", False),  # Use healthy as available
        uptime_seconds=None,  # Not available in simplified view
        metrics=ServiceMetrics(),
    )


def update_service_summary(service_summary: Dict[str, Dict[str, int]], service_type: str, is_healthy: bool) -> None:
    """Update service summary with service type and health status."""
    if service_type not in service_summary:
        service_summary[service_type] = {"total": 0, "healthy": 0}
    service_summary[service_type]["total"] += 1
    if is_healthy:
        service_summary[service_type]["healthy"] += 1


# ============================================================================
# Shutdown Helpers
# ============================================================================


def validate_shutdown_request(request_body: Any) -> None:
    """Validate shutdown request confirmation."""
    if not request_body.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required (confirm=true)")


def get_shutdown_service(request: Request) -> tuple[Any, Any]:
    """Get shutdown service from runtime, raising HTTPException if not available."""
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime:
        raise HTTPException(status_code=503, detail="Runtime not available")

    shutdown_service = getattr(runtime, "shutdown_service", None)
    if not shutdown_service:
        raise HTTPException(status_code=503, detail=ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE)

    return shutdown_service, runtime


def check_shutdown_already_requested(shutdown_service: Any) -> None:
    """Check if shutdown is already in progress."""
    if shutdown_service.is_shutdown_requested():
        existing_reason = shutdown_service.get_shutdown_reason()
        raise HTTPException(status_code=409, detail=f"Shutdown already requested: {existing_reason}")


def build_shutdown_reason(reason: str, force: bool, user_id: str) -> str:
    """Build and sanitize shutdown reason."""
    full_reason = f"{reason} (API shutdown by {user_id})"
    if force:
        full_reason += " [FORCED]"

    # Sanitize reason for logging to prevent log injection
    # Replace newlines and control characters with spaces
    safe_reason = "".join(c if c.isprintable() and c not in "\n\r\t" else " " for c in full_reason)

    return safe_reason


def create_audit_metadata(force: bool, role_value: str, request: Request) -> Dict[str, Any]:
    """Create metadata dict for shutdown audit event."""
    is_service_account = role_value == "SERVICE_ACCOUNT"
    return {
        "force": force,
        "is_service_account": is_service_account,
        "auth_role": role_value,
        "ip_address": request.client.host if request.client else "unknown",
        "user_agent": request.headers.get("user-agent", "unknown"),
        "request_path": str(request.url.path),
    }


async def audit_shutdown_request(
    request: Request, force: bool, user_id: str, role_value: str, severity: str, safe_reason: str
) -> None:  # NOSONAR - async required for create_task
    """Audit the shutdown request for security tracking."""
    audit_service = getattr(request.app.state, "audit_service", None)
    if not audit_service:
        return

    from ciris_engine.schemas.services.graph.audit import AuditEventData

    audit_event = AuditEventData(
        entity_id="system",
        actor=user_id,
        outcome="initiated",
        severity=severity,
        action="system_shutdown",
        resource="system",
        reason=safe_reason,
        metadata=create_audit_metadata(force, role_value, request),
    )

    # Store task reference to prevent garbage collection
    # Using _ prefix to indicate we're intentionally not awaiting
    _audit_task = asyncio.create_task(audit_service.log_event("system_shutdown_request", audit_event))


async def execute_shutdown(shutdown_service: Any, runtime: Any, force: bool, reason: str) -> None:
    """Execute the shutdown with appropriate method based on force flag."""
    if force:
        # Forced shutdown: bypass thought processing, immediate termination
        await shutdown_service.emergency_shutdown(reason, timeout_seconds=5)
    else:
        # Normal shutdown: allow thoughtful consideration via runtime
        # The runtime's request_shutdown will call the shutdown service AND set global flags
        runtime.request_shutdown(reason)


def is_localhost_request(request: Request) -> bool:
    """Check if request originates from localhost (safe for unauthenticated shutdown)."""
    client_host = request.client.host if request.client else None
    # Accept localhost variants: 127.0.0.1, ::1, localhost
    return client_host in ("127.0.0.1", "::1", "localhost", None)


# Constants for local shutdown
RESUME_TIMEOUT_SECONDS = 30.0


def get_server_state(runtime: Any) -> Dict[str, Any]:
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

    state = determine_server_state(runtime, shutdown_in_progress, resume_in_progress)

    return {
        "server_state": state,
        "uptime_seconds": round(uptime, 2),
        "resume_in_progress": resume_in_progress,
        "resume_elapsed_seconds": round(resume_elapsed, 2) if resume_elapsed else None,
    }


def determine_server_state(runtime: Any, shutdown_in_progress: bool, resume_in_progress: bool) -> str:
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


def initiate_force_shutdown(runtime: Any, reason: str) -> None:
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


# ============================================================================
# Adapter Config Service Helper
# ============================================================================


def get_adapter_config_service(request: Request) -> Any:
    """Get AdapterConfigurationService from app state."""
    service = getattr(request.app.state, "adapter_configuration_service", None)
    if not service:
        raise HTTPException(status_code=503, detail="Adapter configuration service not available")
    return service
