"""
System health and time endpoints.

Provides health status and time synchronization information.
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ciris_engine.constants import CIRIS_VERSION
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.api.telemetry import TimeSyncStatus

from ...constants import ERROR_TIME_SERVICE_NOT_AVAILABLE
from ...dependencies.auth import AuthContext, require_observer
from .helpers import (
    check_initialization_status,
    check_processor_health,
    collect_service_health,
    determine_overall_status,
    get_cognitive_state_safe,
    get_current_time,
    get_system_uptime,
)
from .schemas import StartupStatusResponse, SystemHealthResponse, SystemTimeResponse, SystemWarning

logger = logging.getLogger(__name__)

# Type alias for authenticated observer dependency (S8410 compliance)
AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]

router = APIRouter()


async def check_llm_availability() -> tuple[bool, list[SystemWarning]]:
    """Check LLM provider availability and return (has_working_llm, warnings)."""
    warnings: list[SystemWarning] = []
    has_working_llm = False

    from ciris_engine.logic.registries.base import get_global_registry
    from ciris_engine.schemas.runtime.enums import ServiceType

    registry = get_global_registry()
    llm_providers = registry._services.get(ServiceType.LLM, [])

    if not llm_providers:
        # No LLM providers registered at all
        logger.debug("check_llm_availability: No LLM providers registered - degraded_mode=True")
        warnings.append(SystemWarning(
            code="no_llm_provider",
            message="No LLM provider configured. Add a provider in LLM Settings to enable AI features.",
            severity="error",
            action_url="/settings/llm",
        ))
    else:
        # Check if any provider is actually healthy
        # Note: registry._services returns List[ServiceProvider], we need .instance for actual service
        for service_provider in llm_providers:
            provider_name = getattr(service_provider, 'name', str(service_provider))
            # Get the actual service instance from the ServiceProvider wrapper
            service = getattr(service_provider, 'instance', service_provider)
            try:
                if hasattr(service, 'is_healthy'):
                    is_healthy = await service.is_healthy()
                    if is_healthy:
                        has_working_llm = True
                        break
                elif hasattr(service, 'healthy') and service.healthy:
                    has_working_llm = True
                    break
            except Exception as e:
                logger.debug(f"check_llm_availability: Provider '{provider_name}' check failed: {e}")

        if not has_working_llm:
            logger.debug(
                f"check_llm_availability: All {len(llm_providers)} providers unhealthy - degraded_mode=True"
            )
            warnings.append(SystemWarning(
                code="llm_providers_unhealthy",
                message="All LLM providers are currently unavailable. Check your provider settings or network connection.",
                severity="warning",
                action_url="/settings/llm",
            ))

    return has_working_llm, warnings


async def collect_system_warnings(request: Request) -> tuple[bool, list[SystemWarning]]:
    """Collect system-level warnings and check degraded mode.

    Returns (degraded_mode, warnings) tuple.
    """
    # Check LLM availability first
    has_working_llm, llm_warnings = await check_llm_availability()
    warnings = llm_warnings.copy()

    # Check for adapters needing re-authentication
    adapter_manager = getattr(request.app.state, "adapter_manager", None)
    if adapter_manager:
        try:
            adapter_statuses = await adapter_manager.get_all_adapter_status()
            for status in adapter_statuses:
                if status.needs_reauth:
                    warnings.append(SystemWarning(
                        code="adapter_needs_reauth",
                        message=f"Adapter '{status.adapter_id}' needs re-authentication: {status.reauth_reason or 'Token expired'}",
                        severity="warning",
                        action_url=f"/settings/adapters/{status.adapter_id}",
                    ))
        except Exception as e:
            logger.debug(f"Could not check adapter reauth status: {e}")

    # degraded_mode is True when NO working LLM is available
    degraded_mode = not has_working_llm
    return degraded_mode, warnings


@router.get("/health")
async def get_system_health(request: Request) -> SuccessResponse[SystemHealthResponse]:
    """
    Overall system health.

    Returns comprehensive system health including service status,
    initialization state, current cognitive state, and system warnings.
    """
    # Get basic system info
    uptime_seconds = get_system_uptime(request)
    current_time = get_current_time(request)
    cognitive_state = get_cognitive_state_safe(request)
    init_complete = check_initialization_status(request)

    # Collect service health data
    services = await collect_service_health(request)
    processor_healthy = await check_processor_health(request)

    # Collect system warnings and check degraded mode
    degraded_mode, warnings = await collect_system_warnings(request)

    # Determine overall system status
    status = determine_overall_status(init_complete, processor_healthy, services)

    response = SystemHealthResponse(
        status=status,
        version=CIRIS_VERSION,
        uptime_seconds=uptime_seconds,
        services=services,
        initialization_complete=init_complete,
        cognitive_state=cognitive_state,
        timestamp=current_time,
        warnings=warnings,
        degraded_mode=degraded_mode,
    )

    return SuccessResponse(data=response)


@router.get("/startup-status")
async def get_startup_status() -> SuccessResponse[StartupStatusResponse]:
    """
    Startup progress for desktop client polling.

    Returns service initialization count and phase.
    Unauthenticated - available during boot before auth is ready.
    """
    from ciris_engine.logic.runtime.startup_logging import (
        SERVICE_NAMES,
        TOTAL_CORE_SERVICES,
        get_api_status,
        get_api_status_history,
        get_current_phase,
        get_services_started,
    )

    services_started = get_services_started()
    started_names = [SERVICE_NAMES[i - 1] for i in sorted(services_started) if 1 <= i <= len(SERVICE_NAMES)]

    return SuccessResponse(
        data=StartupStatusResponse(
            phase=get_current_phase(),
            services_online=len(services_started),
            services_total=TOTAL_CORE_SERVICES,
            service_names=started_names,
            api_status=get_api_status(),
            api_status_history=get_api_status_history(),
        )
    )


@router.get(
    "/time",
    responses={
        500: {"description": "Failed to get time information"},
        503: {"description": "Time service not available"},
    },
)
async def get_system_time(
    request: Request,
    auth: AuthObserverDep,
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
