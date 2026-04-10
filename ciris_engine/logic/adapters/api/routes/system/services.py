"""
Services and resources endpoints.

Provides resource usage information, service status monitoring, and environment context.
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ciris_engine.logic.context.system_snapshot_helpers import get_enrichment_cache
from ciris_engine.logic.utils.location_utils import get_user_location
from ciris_engine.schemas.api.responses import SuccessResponse

from ...constants import ERROR_RESOURCE_MONITOR_NOT_AVAILABLE
from ...dependencies.auth import AuthContext, require_observer
from .helpers import create_service_status, get_runtime_control_service, update_service_summary
from .schemas import ResourceUsageResponse, ServicesStatusResponse

logger = logging.getLogger(__name__)

# Type alias for authenticated observer dependency (S8410 compliance)
AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]

router = APIRouter()


@router.get(
    "/resources",
    responses={
        500: {"description": "Error getting resource usage"},
        503: {"description": "Resource monitor not available"},
    },
)
async def get_resource_usage(
    request: Request,
    auth: AuthObserverDep,
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


@router.get("/services")
async def get_services_status(
    request: Request,
    auth: AuthObserverDep,
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


# ============================================================================
# Environment Information Endpoint
# ============================================================================


class LocationInfo(BaseModel):
    """User location information from setup."""

    location: Optional[str] = Field(None, description="Human-readable location string")
    latitude: Optional[float] = Field(None, description="Latitude in decimal degrees")
    longitude: Optional[float] = Field(None, description="Longitude in decimal degrees")
    timezone: Optional[str] = Field(None, description="IANA timezone")
    country: Optional[str] = Field(None, description="Country name")
    region: Optional[str] = Field(None, description="Region/state name")
    city: Optional[str] = Field(None, description="City name")
    iso6709: Optional[str] = Field(None, description="ISO 6709 coordinates string")
    has_coordinates: bool = Field(False, description="Whether lat/long are available")


class EnrichmentCacheStats(BaseModel):
    """Context enrichment cache statistics."""

    entries: int = Field(0, description="Number of cached entries")
    hits: int = Field(0, description="Cache hits since startup")
    misses: int = Field(0, description="Cache misses since startup")
    hit_rate_pct: float = Field(0.0, description="Cache hit rate percentage")
    startup_populated: bool = Field(False, description="Whether cache was populated at startup")


class EnvironmentInfoResponse(BaseModel):
    """Environment information response including location and context enrichment."""

    location: LocationInfo = Field(description="User location from setup")
    context_enrichment: Dict[str, Any] = Field(
        default_factory=dict,
        description="Context enrichment results from adapters, keyed by 'adapter_type:tool_name'",
    )
    cache_stats: EnrichmentCacheStats = Field(description="Context enrichment cache statistics")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@router.get("/environment")
async def get_environment_info(
    request: Request,
    auth: AuthObserverDep,
) -> SuccessResponse[EnvironmentInfoResponse]:
    """
    Environment context information.

    Returns user location from setup and context enrichment data from all adapters.
    This includes data from Home Assistant, weather services, navigation, and other
    adapters that provide context_enrichment=True tools.

    Useful for debugging why certain context data may not be available.
    """
    try:
        # Get user location from environment variables
        user_location = get_user_location()
        location_dict = user_location.to_dict()

        location_info = LocationInfo(
            location=location_dict.get("location"),
            latitude=location_dict.get("latitude"),
            longitude=location_dict.get("longitude"),
            timezone=location_dict.get("timezone"),
            country=location_dict.get("country"),
            region=location_dict.get("region"),
            city=location_dict.get("city"),
            iso6709=location_dict.get("iso6709"),
            has_coordinates=user_location.has_coordinates(),
        )

        # Get context enrichment cache data
        cache = get_enrichment_cache()
        enrichment_data = cache.get_all_entries()
        cache_stats_raw = cache.stats

        cache_stats = EnrichmentCacheStats(
            entries=cache_stats_raw.get("entries", 0),
            hits=cache_stats_raw.get("hits", 0),
            misses=cache_stats_raw.get("misses", 0),
            hit_rate_pct=cache_stats_raw.get("hit_rate_pct", 0.0),
            startup_populated=cache_stats_raw.get("startup_populated", False),
        )

        return SuccessResponse(
            data=EnvironmentInfoResponse(
                location=location_info,
                context_enrichment=enrichment_data,
                cache_stats=cache_stats,
            )
        )

    except Exception as e:
        logger.error(f"Error getting environment info: {e}")
        raise HTTPException(status_code=500, detail=str(e))
