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


#: Deferral-context key carrying the base link the agent asks a Wise Authority to approve (rc21 section 3):
#: JSON text of :class:`ProposedBaseLink`.
PROPOSED_BASE_LINK_KEY = "proposed_base_link"

_HEX64 = "^[0-9a-f]{64}$"


class ProposedBaseLink(BaseModel):
    """The base link of the identity profile the agent asks a Wise Authority to approve (rc21 section 3).

    The base link names no ``prev``; its ``amendment_digest`` is ``manifest_digest``: the digest of the agent's
    shipped template as the root-WA-signed template manifest records it.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    template_name: str = Field(..., min_length=1, description="The shipped template the agent runs")
    template_version: Optional[str] = Field(None, description="The template manifest's version, when it states one")
    manifest_digest: str = Field(
        ..., pattern=_HEX64, description="sha256 (lowercase hex) of the template, as the template manifest records it"
    )


class ProfileAnchorStatus(str, Enum):
    """The identity profile's standing (rc21 section 3), as the deferral list reports it."""

    ANCHORED = "anchored"  # the held profile equals the signed chain's derived digest
    UNANCHORED = "unanchored"  # no base link: the shipped template runs, no amendment is authoritative
    MISMATCH = "mismatch"  # the held profile differs from the chain's digest
    CONTESTED = "contested"  # two links name one prev


class DeferralListProfile(BaseModel):
    """The identity profile beside the deferral list, so a WA sees whether a base link is awaited."""

    model_config = ConfigDict(defer_build=True)

    status: ProfileAnchorStatus = Field(..., description="anchored | unanchored | mismatch | contested")
    profile_digest: Optional[str] = Field(
        None, description="sha256 (hex) of CDE([CEG-profile/2, d0..dn]) over the held profile; null before the first check"
    )
    proposed_base_link: Optional[ProposedBaseLink] = Field(
        None, description="The base link a pending deferral asks approval of (resolve with base_link_digest), if any"
    )


class DeferralListCapabilities(BaseModel):
    """What this agent's deferral API supports, so a client can tell before it acts."""

    model_config = ConfigDict(defer_build=True)

    exact_amendment_text: bool = Field(
        True,
        description=(
            "Resolve accepts amendment_text with resolution='approve': the WA approves those exact bytes, and only "
            "they can become a verified identity amendment (CIRISAgent#1366 F1). A deferral that proposes one "
            "carries it as context.proposed_amendment."
        ),
    )
    exact_call_approval: bool = Field(
        True,
        description=(
            "Resolve accepts call_fingerprint with resolution='approve': the approval binds that one call "
            "(rc21 section 4). A deferral that asks approval of a call carries it as context.proposed_call."
        ),
    )
    base_link_approval: bool = Field(
        True,
        description=(
            "Resolve accepts base_link_digest with resolution='approve': the WA approves the profile's base link "
            "(rc21 section 3). A deferral that proposes one carries it as context.proposed_base_link."
        ),
    )


class DeferralListResponse(BaseModel):
    """Response containing list of pending deferrals."""

    model_config = ConfigDict(defer_build=True)

    deferrals: List[PendingDeferral] = Field(..., description="List of pending deferrals")
    total: int = Field(..., description="Total number of pending deferrals")
    capabilities: DeferralListCapabilities = Field(
        default_factory=DeferralListCapabilities, description="What this agent's deferral API supports"
    )
    profile: DeferralListProfile = Field(..., description="The identity profile's standing (rc21 section 3)")


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

    call_fingerprint: Optional[str] = Field(
        None,
        min_length=1,
        description=(
            "For a deferral that asks approval of one tool call: the tool_call_fingerprint (tool + exact arguments) "
            "the Wise Authority approves. Only with resolution='approve' (400, reason id "
            "wa.call_fingerprint_requires_approve), and never together with amendment_text (400, reason id "
            "wa.resolve_one_subject): a deferral is either a call approval or an identity change."
        ),
    )

    base_link_digest: Optional[str] = Field(
        None,
        pattern=_HEX64,
        description=(
            "For a deferral that proposes the profile's base link (context.proposed_base_link): its manifest_digest, "
            "which the Wise Authority approves. Only with resolution='approve' (400, reason id "
            "wa.base_link_digest_requires_approve); never with amendment_text or call_fingerprint (400, reason id "
            "wa.resolve_one_subject); must equal the proposed manifest_digest (400, reason id "
            "wa.base_link_digest_mismatch). The node signs it as the response row's amendment_digest."
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
