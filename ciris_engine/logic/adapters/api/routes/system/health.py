"""
System health and time endpoints.

Provides health status and time synchronization information.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

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
from .schemas import SystemHealthResponse, SystemTimeResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health", response_model=SuccessResponse[SystemHealthResponse])
async def get_system_health(request: Request) -> SuccessResponse[SystemHealthResponse]:
    """
    Overall system health.

    Returns comprehensive system health including service status,
    initialization state, and current cognitive state.
    """
    # Get basic system info
    uptime_seconds = get_system_uptime(request)
    current_time = get_current_time(request)
    cognitive_state = get_cognitive_state_safe(request)
    init_complete = check_initialization_status(request)

    # Collect service health data
    services = await collect_service_health(request)
    processor_healthy = await check_processor_health(request)

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
