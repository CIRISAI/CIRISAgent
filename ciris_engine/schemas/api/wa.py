"""
WA (Wise Authority) API schemas for CIRIS API v3 (Simplified).

Provides type-safe structures for WA API endpoints.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from ciris_engine.schemas.services.authority.wise_authority import PendingDeferral
from ciris_engine.schemas.services.authority_core import WAPermission
from ciris_engine.schemas.types import JSONDict


class DeferralListResponse(BaseModel):
    """Response containing list of pending deferrals."""

    model_config = ConfigDict(defer_build=True)

    deferrals: List[PendingDeferral] = Field(..., description="List of pending deferrals")
    total: int = Field(..., description="Total number of pending deferrals")


#: The longest identity amendment a Wise Authority can approve in one resolution.
MAX_AMENDMENT_TEXT_CHARS = 4000


class ResolveDeferralRequest(BaseModel):
    """Request to resolve a deferral with integrated guidance."""

    model_config = ConfigDict(defer_build=True)

    resolution: str = Field(..., pattern="^(approve|reject|modify)$", description="Resolution type")
    guidance: str = Field(..., description="WA wisdom guidance integrated with the decision")
    amendment_text: Optional[str] = Field(
        None,
        min_length=1,
        max_length=MAX_AMENDMENT_TEXT_CHARS,
        description=(
            "The EXACT identity amendment text the Wise Authority approves (CIRISAgent#1366 F1). Only with "
            "resolution='approve'. The API computes its sha256; the node signs that digest into the WA's response "
            "row, and the guidance task writes these bytes as the amendment. Without it an approval lands no "
            "identity amendment."
        ),
    )

    @field_validator("amendment_text")
    @classmethod
    def _exact_text_has_no_outer_whitespace(cls, value: Optional[str]) -> Optional[str]:
        """The exact bytes, so no outer whitespace: the stored amendment is read back stripped,
        and a digest over bytes that cannot round-trip could never verify."""
        if value is not None and (not value.strip() or value != value.strip()):
            raise ValueError("amendment_text must be non-empty and carry no leading or trailing whitespace")
        return value


class ResolveDeferralResponse(BaseModel):
    """Response after resolving a deferral."""

    model_config = ConfigDict(defer_build=True)

    success: bool = Field(..., description="Whether resolution succeeded")
    deferral_id: str = Field(..., description="ID of resolved deferral")
    resolved_at: datetime = Field(..., description="When deferral was resolved")
    request_attestation_id: Optional[str] = Field(
        None, description="The deferral:request:v1 row this answer references, if the node signed one (#1316)"
    )
    response_attestation_id: Optional[str] = Field(
        None, description="The Wise Authority's signed deferral:response row, if the node authors rows (#1316)"
    )


class PermissionsListResponse(BaseModel):
    """Response containing list of permissions."""

    model_config = ConfigDict(defer_build=True)

    permissions: List[WAPermission] = Field(..., description="List of permissions")
    wa_id: str = Field(..., description="WA ID these permissions belong to")


class WAStatusResponse(BaseModel):
    """WA service status response."""

    model_config = ConfigDict(defer_build=True)

    service_healthy: bool = Field(..., description="Whether WA service is healthy")
    active_was: int = Field(..., description="Number of active WAs")
    pending_deferrals: int = Field(..., description="Number of pending deferrals")
    deferrals_24h: int = Field(..., description="Deferrals created in last 24 hours")
    average_resolution_time_minutes: float = Field(..., description="Average deferral resolution time")
    timestamp: datetime = Field(..., description="Status timestamp")
    subscribers: List[str] = Field(default_factory=list, description="List of WA bus subscriber names")

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

    model_config = ConfigDict(defer_build=True)

    topic: str = Field(..., description="Topic requiring guidance")
    context: Optional[str] = Field(None, description="Additional context for the guidance request")
    urgency: Optional[UrgencyLevel] = Field(None, description="Urgency level")


class WAGuidanceResponse(BaseModel):
    """WA guidance response."""

    model_config = ConfigDict(defer_build=True)

    guidance: str = Field(..., description="Wisdom guidance provided")
    wa_id: str = Field(..., description="ID of WA who provided guidance")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence level (0-1)")
    additional_context: JSONDict = Field(default_factory=dict, description="Additional context")
    timestamp: datetime = Field(..., description="When guidance was provided")

    @field_serializer("timestamp")
    def serialize_timestamp(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return timestamp.isoformat() if timestamp else None
