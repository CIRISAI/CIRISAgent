"""
WA (Wise Authority) API schemas for CIRIS API v3 (Simplified).

Provides type-safe structures for WA API endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_serializer

from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.authority_core import WAPermission
from ciris_engine.schemas.types import JSONDict


class DeferralListResponse(BaseModel):
    """Response containing list of pending deferrals."""

    deferrals: List[PendingDeferral] = Field(..., description="List of pending deferrals")
    total: int = Field(..., description="Total number of pending deferrals")


class ResolveDeferralRequest(BaseModel):
    """Request to resolve a deferral with integrated guidance."""

    resolution: str = Field(..., pattern="^(approve|reject|modify)$", description="Resolution type")
    guidance: str = Field(..., description="WA wisdom guidance integrated with the decision")


class ResolveDeferralResponse(BaseModel):
    """Response after resolving a deferral."""

    success: bool = Field(..., description="Whether resolution succeeded")
    deferral_id: str = Field(..., description="ID of resolved deferral")
    resolved_at: datetime = Field(..., description="When deferral was resolved")


class PermissionsListResponse(BaseModel):
    """Response containing list of permissions."""

    permissions: List[WAPermission] = Field(..., description="List of permissions")
    wa_id: str = Field(..., description="WA ID these permissions belong to")


class WAStatusResponse(BaseModel):
    """WA service status response."""

    service_healthy: bool = Field(..., description="Whether WA service is healthy")
    active_was: int = Field(..., description="Number of active WAs")
    pending_deferrals: int = Field(..., description="Number of pending deferrals")
    deferrals_24h: int = Field(..., description="Deferrals created in last 24 hours")
    average_resolution_time_minutes: float = Field(..., description="Average deferral resolution time")
    timestamp: datetime = Field(..., description="Status timestamp")

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return timestamp.isoformat() if timestamp else None


class UrgencyLevel(str, Enum):
    """Urgency level for guidance requests."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class WAGuidanceRequest(BaseModel):
    """Request for WA guidance on a topic."""

    topic: str = Field(..., description="Topic requiring guidance")
    context: Optional[str] = Field(None, description="Additional context for the guidance request")
    urgency: Optional[UrgencyLevel] = Field(None, description="Urgency level")


class WAGuidanceResponse(BaseModel):
    """WA guidance response."""

    guidance: str = Field(..., description="Wisdom guidance provided")
    wa_id: str = Field(..., description="ID of WA who provided guidance")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level (0-1)")
    additional_context: JSONDict = Field(default_factory=dict, description="Additional context")
    timestamp: datetime = Field(..., description="When guidance was provided")

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return timestamp.isoformat() if timestamp else None
