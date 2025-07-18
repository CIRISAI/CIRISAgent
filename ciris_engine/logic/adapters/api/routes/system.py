"""
System management endpoints for CIRIS API v3.0 (Simplified).

Consolidates health, time, resources, runtime control, services, and shutdown
into a unified system operations interface.
"""
from typing import List, Optional, Dict, Any, Union
from datetime import datetime, timezone
from fastapi import APIRouter, Request, HTTPException, Depends, Body
from pydantic import BaseModel, Field, field_serializer
import logging
import asyncio
from ciris_engine.utils.serialization import serialize_timestamp

from ciris_engine.schemas.api.responses import SuccessResponse
from ..dependencies.auth import require_observer, require_admin, AuthContext
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.resources_core import ResourceSnapshot, ResourceBudget
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.api.telemetry import TimeSyncStatus, ServiceMetrics
from ciris_engine.schemas.runtime.adapter_management import (
    AdapterOperationResult, AdapterListResponse,
    AdapterStatus as AdapterStatusSchema, AdapterConfig, AdapterMetrics
)
from ..constants import ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE, ERROR_TIME_SERVICE_NOT_AVAILABLE, ERROR_RESOURCE_MONITOR_NOT_AVAILABLE, ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE, DESC_HUMAN_READABLE_STATUS, DESC_CURRENT_COGNITIVE_STATE

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

    @field_serializer('timestamp')
    def serialize_ts(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return serialize_timestamp(timestamp, _info)


class SystemTimeResponse(BaseModel):
    """System and agent time information."""
    system_time: datetime = Field(..., description="Host system time (OS time)")
    agent_time: datetime = Field(..., description="Agent's TimeService time")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    time_sync: TimeSyncStatus = Field(..., description="Time synchronization status")

    @field_serializer('system_time', 'agent_time')
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


class ServiceStatus(BaseModel):
    """Individual service status."""
    name: str = Field(..., description="Service name")
    type: str = Field(..., description="Service type")
    healthy: bool = Field(..., description="Whether service is healthy")
    available: bool = Field(..., description="Whether service is available")
    uptime_seconds: Optional[float] = Field(None, description="Service uptime if tracked")
    metrics: ServiceMetrics = Field(default_factory=lambda: ServiceMetrics(
        uptime_seconds=None,
        requests_handled=None,
        error_count=None,
        avg_response_time_ms=None,
        memory_mb=None,
        custom_metrics=None
    ), description="Service-specific metrics")


class ServicesStatusResponse(BaseModel):
    """Status of all system services."""
    services: List[ServiceStatus] = Field(..., description="List of service statuses")
    total_services: int = Field(..., description="Total number of services")
    healthy_services: int = Field(..., description="Number of healthy services")
    timestamp: datetime = Field(..., description="When status was collected")

    @field_serializer('timestamp')
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

    @field_serializer('timestamp')
    def serialize_ts(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return serialize_timestamp(timestamp, _info)


class AdapterActionRequest(BaseModel):
    """Request for adapter operations."""
    config: Optional[Dict[str, Any]] = Field(None, description="Adapter configuration")
    auto_start: bool = Field(True, description="Whether to auto-start the adapter")
    force: bool = Field(False, description="Force the operation")


class ToolInfo(BaseModel):
    """Information about an available tool."""
    name: str = Field(..., description="Tool name")
    description: str = Field(..., description="Tool description")
    provider: str = Field(..., description="Provider service name")
    schema: Dict[str, Any] = Field(default_factory=dict, description="Tool parameter schema")
    category: str = Field("general", description="Tool category")


# Endpoints

@router.get("/health", response_model=SuccessResponse[SystemHealthResponse])
async def get_system_health(request: Request) -> SuccessResponse[SystemHealthResponse]:
    """
    Overall system health.

    Returns comprehensive system health including service status,
    initialization state, and current cognitive state.
    """
    # Get time service for uptime calculation
    time_service: Optional[TimeServiceProtocol] = getattr(request.app.state, 'time_service', None)
    start_time = getattr(time_service, '_start_time', None) if time_service else None
    current_time = time_service.now() if time_service else datetime.now(timezone.utc)
    uptime_seconds = (current_time - start_time).total_seconds() if start_time else 0.0

    # Check cognitive state if runtime is available
    cognitive_state = None
    runtime = getattr(request.app.state, 'runtime', None)
    if runtime and hasattr(runtime, 'agent_processor'):
        try:
            cognitive_state = runtime.agent_processor.get_current_state()
        except Exception as e:
            logger.warning(f"Failed to retrieve cognitive state: {type(e).__name__}: {str(e)} - Agent processor may not be initialized")
            pass

    # Check initialization status
    init_complete = True
    init_service = getattr(request.app.state, 'initialization_service', None)
    if init_service and hasattr(init_service, 'is_initialized'):
        init_complete = init_service.is_initialized()

    # Collect service health
    services = {}
    if hasattr(request.app.state, 'service_registry') and request.app.state.service_registry is not None:
        service_registry = request.app.state.service_registry
        try:
            for service_type in ServiceType:
                providers = service_registry.get_services_by_type(service_type)
                if providers:
                    healthy_count = 0
                    for provider in providers:
                        try:
                            if hasattr(provider, "is_healthy"):
                                if asyncio.iscoroutinefunction(provider.is_healthy):
                                    is_healthy = await provider.is_healthy()
                                else:
                                    is_healthy = provider.is_healthy()
                                if is_healthy:
                                    healthy_count += 1
                            else:
                                healthy_count += 1  # Assume healthy if no method
                        except Exception as e:
                            logger.warning(f"Service health check failed for {service_type.value}: {type(e).__name__}: {str(e)} - Service may not implement is_healthy()")
                            # Continue with service counted as unhealthy

                    services[service_type.value] = {
                        "available": len(providers),
                        "healthy": healthy_count
                    }
        except Exception as e:
            logger.error(f"Error checking service health: {e}")

    # Determine overall status
    total_services = sum(s.get("available", 0) for s in services.values())
    healthy_services = sum(s.get("healthy", 0) for s in services.values())

    if not init_complete:
        status = "initializing"
    elif healthy_services == total_services:
        status = "healthy"
    elif healthy_services >= total_services * 0.8:
        status = "degraded"
    else:
        status = "critical"

    response = SystemHealthResponse(
        status=status,
        version="1.0.2",
        uptime_seconds=uptime_seconds,
        services=services,
        initialization_complete=init_complete,
        cognitive_state=cognitive_state,
        timestamp=current_time
    )

    return SuccessResponse(data=response)


@router.get("/time", response_model=SuccessResponse[SystemTimeResponse])
async def get_system_time(
    request: Request,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[SystemTimeResponse]:
    """
    System time information.

    Returns both system time (host OS) and agent time (TimeService),
    along with synchronization status.
    """
    # Get time service
    time_service: Optional[TimeServiceProtocol] = getattr(request.app.state, 'time_service', None)
    if not time_service:
        raise HTTPException(status_code=503, detail=ERROR_TIME_SERVICE_NOT_AVAILABLE)

    try:
        # Get system time (actual OS time)
        system_time = datetime.now(timezone.utc)

        # Get agent time (from TimeService)
        agent_time = time_service.now()

        # Calculate uptime
        start_time = getattr(time_service, '_start_time', None)
        if not start_time:
            start_time = agent_time
            uptime_seconds = 0.0
        else:
            uptime_seconds = (agent_time - start_time).total_seconds()

        # Calculate time sync status
        is_mocked = getattr(time_service, '_mock_time', None) is not None
        time_diff_ms = (agent_time - system_time).total_seconds() * 1000

        time_sync = TimeSyncStatus(
            synchronized=not is_mocked and abs(time_diff_ms) < 1000,  # Within 1 second
            drift_ms=time_diff_ms,
            last_sync=getattr(time_service, '_last_sync', agent_time),
            sync_source="mock" if is_mocked else "system"
        )

        response = SystemTimeResponse(
            system_time=system_time,
            agent_time=agent_time,
            uptime_seconds=uptime_seconds,
            time_sync=time_sync
        )

        return SuccessResponse(data=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get time information: {str(e)}")


@router.get("/resources", response_model=SuccessResponse[ResourceUsageResponse])
async def get_resource_usage(
    request: Request,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ResourceUsageResponse]:
    """
    Resource usage and limits.

    Returns current resource consumption, configured limits,
    and health status.
    """
    resource_monitor = getattr(request.app.state, 'resource_monitor', None)
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
            critical=snapshot.critical
        )

        return SuccessResponse(data=response)

    except Exception as e:
        logger.error(f"Error getting resource usage: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/runtime/{action}", response_model=SuccessResponse[RuntimeControlResponse])
async def control_runtime(
    action: str,
    request: Request,
    body: RuntimeAction = Body(...),
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[RuntimeControlResponse]:
    """
    Runtime control actions.

    Control agent runtime behavior. Valid actions:
    - pause: Pause message processing
    - resume: Resume message processing
    - state: Get current runtime state

    Requires ADMIN role.
    """
    runtime_control = getattr(request.app.state, 'runtime_control_service', None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        # Validate action
        valid_actions = ["pause", "resume", "state"]
        if action not in valid_actions:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid action. Must be one of: {', '.join(valid_actions)}"
            )

        # Execute action
        if action == "pause":
            success = await runtime_control.pause_processing(body.reason or "API request")
            result = RuntimeControlResponse(
                success=success,
                message="Processing paused" if success else "Already paused",
                processor_state="paused" if success else "unknown",
                cognitive_state="UNKNOWN",
                queue_depth=0
            )
        elif action == "resume":
            success = await runtime_control.resume_processing()
            result = RuntimeControlResponse(
                success=success,
                message="Processing resumed" if success else "Not paused",
                processor_state="active" if success else "unknown",
                cognitive_state="UNKNOWN",
                queue_depth=0
            )
        elif action == "state":
            # Get current state without changing it
            status = await runtime_control.get_runtime_status()
            result = RuntimeControlResponse(
                success=True,
                message="Current runtime state retrieved",
                processor_state="paused" if status.get("paused", False) else "active",
                cognitive_state=status.get("cognitive_state", "UNKNOWN"),
                queue_depth=0  # Not tracked in simplified version
            )
            return SuccessResponse(data=result)

        # Get cognitive state if available
        cognitive_state = None
        runtime = getattr(request.app.state, 'runtime', None)
        if runtime and hasattr(runtime, 'agent_processor'):
            try:
                cognitive_state = runtime.agent_processor.get_current_state()
            except Exception as e:
                logger.warning(f"Failed to retrieve cognitive state: {type(e).__name__}: {str(e)} - Agent processor may not be initialized")
                pass

        # Convert result to our response format
        response = RuntimeControlResponse(
            success=result.success,
            message=result.message,
            processor_state=result.processor_state,
            cognitive_state=cognitive_state,
            queue_depth=result.queue_depth
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services", response_model=SuccessResponse[ServicesStatusResponse])
async def get_services_status(
    request: Request,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ServicesStatusResponse]:
    """
    Service status.

    Returns status of all system services including health,
    availability, and basic metrics.
    """
    # Use the runtime control service to get all services
    runtime_control = getattr(request.app.state, 'main_runtime_control_service', None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, 'runtime_control_service', None)
    
    if not runtime_control:
        return SuccessResponse(
            data=ServicesStatusResponse(
                services=[],
                total_services=0,
                healthy_services=0,
                timestamp=datetime.now(timezone.utc)
            )
        )
    
    # Get service health status from runtime control
    try:
        health_status = await runtime_control.get_service_health_status()
        
        # Convert service details to ServiceStatus list
        services = []
        service_summary = {}
        
        # Include ALL services (both direct and registry)
        for service_key, details in health_status.service_details.items():
            # Parse service key to get type and name
            parts = service_key.split('.')
            
            # Handle direct services (format: direct.service_type.service_name)
            if service_key.startswith('direct.') and len(parts) >= 3:
                source = parts[0]  # 'direct'
                service_type = parts[1]  # 'graph', 'infrastructure', etc.
                service_name = parts[2]  # 'memory_service', 'time_service', etc.
                
                # Convert snake_case to PascalCase for display
                service_name = ''.join(word.capitalize() for word in service_name.split('_'))
                
            # Handle registry services (format: registry.ServiceType.ENUM.ServiceName_id)
            elif service_key.startswith('registry.') and len(parts) >= 3:
                source = parts[0]  # 'registry'
                
                # Handle both 3-part and 4-part keys
                if len(parts) >= 4 and parts[1] == 'ServiceType':
                    # Format: registry.ServiceType.ENUM.ServiceName_id
                    service_type_enum = f"{parts[1]}.{parts[2]}"  # 'ServiceType.TOOL'
                    service_name = parts[3]  # 'APIToolService_127803015745648'
                    logger.debug(f"4-part key: {service_key}, service_name: {service_name}")
                else:
                    # Fallback: registry.ENUM.ServiceName
                    service_type_enum = parts[1]  # 'ServiceType.COMMUNICATION', etc.
                    service_name = parts[2]  # Service name or enum value
                    logger.debug(f"3-part key: {service_key}, service_name: {service_name}")
                
                # Clean up service name (remove instance ID)
                original_service_name = service_name
                if '_' in service_name:
                    service_name = service_name.split('_')[0]
                
                # Extract adapter type from service name and create display name
                adapter_prefix = ''
                display_name = service_name
                
                if 'Discord' in service_name:
                    adapter_prefix = 'DISCORD'
                elif 'API' in service_name:
                    adapter_prefix = 'API'
                elif 'CLI' in service_name:
                    adapter_prefix = 'CLI'
                
                # Map ServiceType enum to category and set display name
                service_type = 'unknown'
                if 'COMMUNICATION' in service_type_enum:
                    service_type = 'adapter'
                    if adapter_prefix:
                        display_name = f"{adapter_prefix}-COMM"
                elif 'MEMORY' in service_type_enum:
                    service_type = 'graph'
                elif 'LLM' in service_type_enum:
                    service_type = 'runtime'
                elif 'TIME' in service_type_enum:
                    service_type = 'infrastructure'
                elif 'TOOL' in service_type_enum:
                    service_type = 'tool'
                    if adapter_prefix:
                        display_name = f"{adapter_prefix}-TOOL"
                elif 'WISE_AUTHORITY' in service_type_enum:
                    service_type = 'governance'
                    if adapter_prefix:
                        display_name = f"{adapter_prefix}-WISE"
                elif 'RUNTIME_CONTROL' in service_type_enum:
                    service_type = 'runtime'
                    if adapter_prefix:
                        display_name = f"{adapter_prefix}-RUNTIME"
                
                # Use display name for adapter services
                if adapter_prefix and display_name != service_name:
                    service_name = display_name
            else:
                source = 'unknown'
                service_type = 'unknown'
                service_name = service_key
            
            # Create ServiceStatus
            status = ServiceStatus(
                name=service_name,
                type=service_type,
                healthy=details.get('healthy', False),
                available=details.get('healthy', False),  # Use healthy as available
                uptime_seconds=None,  # Not available in simplified view
                metrics=ServiceMetrics()
            )
            services.append(status)
            
            # Update service summary
            if service_type not in service_summary:
                service_summary[service_type] = {'total': 0, 'healthy': 0}
            service_summary[service_type]['total'] += 1
            if details.get('healthy', False):
                service_summary[service_type]['healthy'] += 1
        
        return SuccessResponse(
            data=ServicesStatusResponse(
                services=services,
                total_services=len(services),
                healthy_services=sum(1 for s in services if s.healthy),
                timestamp=datetime.now(timezone.utc)
            )
        )
    except Exception as e:
        logger.error(f"Error getting service status: {e}")
        return SuccessResponse(
            data=ServicesStatusResponse(
                services=[],
                total_services=0,
                healthy_services=0,
                timestamp=datetime.now(timezone.utc)
            )
        )


@router.post("/shutdown", response_model=SuccessResponse[ShutdownResponse])
async def shutdown_system(
    body: ShutdownRequest,
    request: Request,
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[ShutdownResponse]:
    """
    Graceful shutdown.

    Initiates graceful system shutdown. Requires confirmation
    flag to prevent accidental shutdowns.

    Requires ADMIN role.
    """
    # Validate confirmation
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Confirmation required (confirm=true)"
        )

    # Get shutdown service from runtime
    runtime = getattr(request.app.state, 'runtime', None)
    if not runtime:
        raise HTTPException(status_code=503, detail="Runtime not available")

    shutdown_service = getattr(runtime, 'shutdown_service', None)
    if not shutdown_service:
        raise HTTPException(status_code=503, detail=ERROR_SHUTDOWN_SERVICE_NOT_AVAILABLE)

    try:
        # Check if already shutting down
        if shutdown_service.is_shutdown_requested():
            existing_reason = shutdown_service.get_shutdown_reason()
            raise HTTPException(
                status_code=409,
                detail=f"Shutdown already requested: {existing_reason}"
            )

        # Build shutdown reason
        reason = f"{body.reason} (API shutdown by {auth.user_id})"
        if body.force:
            reason += " [FORCED]"

        # Sanitize reason for logging to prevent log injection
        # Replace newlines and control characters with spaces
        safe_reason = ''.join(c if c.isprintable() and c not in '\n\r\t' else ' ' for c in reason)
        
        # Log shutdown request with sanitized reason
        logger.warning(f"SHUTDOWN requested: {safe_reason}")

        # Execute shutdown through runtime to ensure proper state transition
        # The runtime's request_shutdown will call the shutdown service AND set global flags
        runtime.request_shutdown(reason)

        response = ShutdownResponse(
            status="initiated",
            message=f"System shutdown initiated: {reason}",
            shutdown_initiated=True,
            timestamp=datetime.now(timezone.utc)
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
    request: Request,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[AdapterListResponse]:
    """
    List all loaded adapters.
    
    Returns information about all currently loaded adapter instances
    including their type, status, and basic metrics.
    """
    runtime_control = getattr(request.app.state, 'main_runtime_control_service', None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)
    
    try:
        # Get adapter list from runtime control service
        adapters = await runtime_control.list_adapters()
        
        # Convert to response format
        adapter_statuses = []
        for adapter in adapters:
            # Convert AdapterInfo to AdapterStatusSchema
            config = AdapterConfig(
                adapter_type=adapter.adapter_type,
                enabled=adapter.status == "RUNNING",
                settings={}
            )
            
            metrics = None
            if adapter.messages_processed > 0 or adapter.error_count > 0:
                metrics = AdapterMetrics(
                    messages_processed=adapter.messages_processed,
                    errors_count=adapter.error_count,
                    uptime_seconds=(datetime.now(timezone.utc) - adapter.started_at).total_seconds() if adapter.started_at else 0,
                    last_error=adapter.last_error,
                    last_error_time=None
                )
            
            adapter_statuses.append(AdapterStatusSchema(
                adapter_id=adapter.adapter_id,
                adapter_type=adapter.adapter_type,
                is_running=adapter.status == "RUNNING",
                loaded_at=adapter.started_at or datetime.now(timezone.utc),
                services_registered=[],  # Not available from AdapterInfo
                config_params=config,
                metrics=metrics.__dict__ if metrics else None,
                last_activity=None,
                tools=adapter.tools  # Include tools information
            ))
        
        running_count = sum(1 for a in adapter_statuses if a.is_running)
        
        response = AdapterListResponse(
            adapters=adapter_statuses,
            total_count=len(adapter_statuses),
            running_count=running_count
        )
        
        return SuccessResponse(data=response)
        
    except Exception as e:
        logger.error(f"Error listing adapters: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/{adapter_id}", response_model=SuccessResponse[AdapterStatusSchema])
async def get_adapter_status(
    adapter_id: str,
    request: Request,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[AdapterStatusSchema]:
    """
    Get detailed status of a specific adapter.
    
    Returns comprehensive information about an adapter instance
    including configuration, metrics, and service registrations.
    """
    runtime_control = getattr(request.app.state, 'main_runtime_control_service', None)
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
                uptime_seconds=(datetime.now(timezone.utc) - adapter_info.started_at).total_seconds() if adapter_info.started_at else 0,
                last_error=adapter_info.last_error,
                last_error_time=None
            )
            metrics_dict = metrics.__dict__
        
        status = AdapterStatusSchema(
            adapter_id=adapter_info.adapter_id,
            adapter_type=adapter_info.adapter_type,
            is_running=adapter_info.status == "RUNNING",
            loaded_at=adapter_info.started_at,
            services_registered=[],  # Not exposed via AdapterInfo
            config_params=AdapterConfig(
                adapter_type=adapter_info.adapter_type,
                enabled=True,
                settings={}
            ),
            metrics=metrics_dict,
            last_activity=None,
            tools=adapter_info.tools  # Include tools information
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
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[AdapterOperationResult]:
    """
    Load a new adapter instance.
    
    Dynamically loads and starts a new adapter of the specified type.
    Requires ADMIN role.
    
    Adapter types: cli, api, discord
    """
    runtime_control = getattr(request.app.state, 'main_runtime_control_service', None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)
    
    try:
        # Generate adapter ID if not provided
        import uuid
        adapter_id = f"{adapter_type}_{uuid.uuid4().hex[:8]}"
        
        # Load adapter through runtime control service
        logger.info(f"Loading adapter through runtime_control: {runtime_control.__class__.__name__} (id: {id(runtime_control)})")
        if hasattr(runtime_control, 'adapter_manager'):
            logger.info(f"Runtime control adapter_manager id: {id(runtime_control.adapter_manager)}")
        
        result = await runtime_control.load_adapter(
            adapter_type=adapter_type,
            adapter_id=adapter_id,
            config=body.config,
            auto_start=body.auto_start
        )
        
        # Convert response
        response = AdapterOperationResult(
            success=result.success,
            adapter_id=result.adapter_id,
            adapter_type=adapter_type,
            message=result.error if not result.success else f"Adapter {result.adapter_id} loaded successfully",
            error=result.error,
            details={"timestamp": result.timestamp.isoformat()}
        )
        
        return SuccessResponse(data=response)
        
    except Exception as e:
        logger.error(f"Error loading adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/adapters/{adapter_id}", response_model=SuccessResponse[AdapterOperationResult])
async def unload_adapter(
    adapter_id: str,
    request: Request,
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[AdapterOperationResult]:
    """
    Unload an adapter instance.
    
    Stops and removes an adapter from the runtime.
    Will fail if it's the last communication-capable adapter.
    Requires ADMIN role.
    """
    runtime_control = getattr(request.app.state, 'main_runtime_control_service', None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)
    
    try:
        # Unload adapter through runtime control service
        result = await runtime_control.unload_adapter(
            adapter_id=adapter_id,
            force=False  # Never force, respect safety checks
        )
        
        # Convert response
        response = AdapterOperationResult(
            success=result.success,
            adapter_id=result.adapter_id,
            adapter_type=result.adapter_type,
            message=result.error if not result.success else f"Adapter {result.adapter_id} unloaded successfully",
            error=result.error,
            details={"timestamp": result.timestamp.isoformat()}
        )
        
        return SuccessResponse(data=response)
        
    except Exception as e:
        logger.error(f"Error unloading adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/adapters/{adapter_id}/reload", response_model=SuccessResponse[AdapterOperationResult])
async def reload_adapter(
    adapter_id: str,
    body: AdapterActionRequest,
    request: Request,
    auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[AdapterOperationResult]:
    """
    Reload an adapter with new configuration.
    
    Stops the adapter and restarts it with new configuration.
    Useful for applying configuration changes without full restart.
    Requires ADMIN role.
    """
    runtime_control = getattr(request.app.state, 'main_runtime_control_service', None)
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
            auto_start=body.auto_start
        )
        
        # Convert response
        response = AdapterOperationResult(
            success=load_result.success,
            adapter_id=load_result.adapter_id,
            adapter_type=adapter_info.adapter_type,
            message=f"Adapter reloaded: {load_result.message}" if load_result.success else f"Reload failed: {load_result.error}",
            error=load_result.error,
            details={"timestamp": load_result.timestamp.isoformat()}
        )
        
        return SuccessResponse(data=response)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reloading adapter: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Tool endpoints
@router.get("/tools", response_model=SuccessResponse[List[ToolInfo]])
async def get_available_tools(
    request: Request,
    auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[List[ToolInfo]]:
    """
    Get list of all available tools from all tool providers.
    
    Returns tools from:
    - Core tool services (secrets, self_help)
    - Adapter tool services (API, Discord, etc.)
    
    Requires OBSERVER role.
    """
    
    try:
        all_tools = []
        tool_providers = []
        
        # Get all tool providers from the service registry
        service_registry = getattr(request.app.state, 'service_registry', None)
        if service_registry:
            # Get provider info for TOOL services
            provider_info = service_registry.get_provider_info(service_type=ServiceType.TOOL.value)
            provider_info.get('services', {}).get(ServiceType.TOOL.value, [])
            
            # Get the actual provider instances from the registry
            if hasattr(service_registry, '_services') and ServiceType.TOOL in service_registry._services:
                for provider_data in service_registry._services[ServiceType.TOOL]:
                    try:
                        provider = provider_data.instance
                        provider_name = provider.__class__.__name__
                        tool_providers.append(provider_name)
                        
                        if hasattr(provider, 'get_all_tool_info'):
                            # Modern interface with ToolInfo objects
                            tool_infos = await provider.get_all_tool_info()
                            for info in tool_infos:
                                all_tools.append(ToolInfo(
                                    name=info.name,
                                    description=info.description,
                                    provider=provider_name,
                                    schema=info.parameters.model_dump() if info.parameters else {},
                                    category=getattr(info, 'category', 'general')
                                ))
                        elif hasattr(provider, 'list_tools'):
                            # Legacy interface
                            tool_names = await provider.list_tools()
                            for name in tool_names:
                                all_tools.append(ToolInfo(
                                    name=name,
                                    description=f"{name} tool",
                                    provider=provider_name,
                                    schema={},
                                    category="general"
                                ))
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
        
        return SuccessResponse[List[ToolInfo]](
            data=unique_tools
        )
        
    except Exception as e:
        logger.error(f"Error getting available tools: {e}")
        raise HTTPException(status_code=500, detail=str(e))
