"""
Services and resources endpoints.

Provides resource usage information and service status monitoring.
"""

import logging
from datetime import datetime, timezone
from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Request

from ciris_engine.schemas.api.responses import SuccessResponse

from ...constants import ERROR_RESOURCE_MONITOR_NOT_AVAILABLE
from ...dependencies.auth import AuthContext, require_observer
from .helpers import (
    create_service_status,
    get_runtime_control_service,
    update_service_summary,
)
from .schemas import ResourceUsageResponse, ServicesStatusResponse

logger = logging.getLogger(__name__)

router = APIRouter()


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
        runtime_control = get_runtime_control_service(request)
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
            status = create_service_status(service_key, details)
            services.append(status)
            update_service_summary(service_summary, status.type, status.healthy)

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
