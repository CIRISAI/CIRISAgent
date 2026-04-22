"""
Consent management API endpoints - FAIL FAST, NO FAKE DATA.

Implements Consensual Evolution Protocol v0.2.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ciris_engine.logic.services.governance.consent import ConsentNotFoundError, ConsentService, ConsentValidationError
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import (
    CategoryMetadata,
    ConsentAuditEntry,
    ConsentCategoriesResponse,
    ConsentCategory,
    ConsentCleanupResponse,
    ConsentDecayStatus,
    ConsentImpactReport,
    ConsentQueryResponse,
    ConsentRecordResponse,
    ConsentRequest,
    ConsentStatus,
    ConsentStatusResponse,
    ConsentStream,
    ConsentStreamsResponse,
    DSARInitiateResponse,
    DSARStatusResponse,
    PartnershipStatusResponse,
    StreamMetadata,
)

from ..dependencies.auth import AuthContext, get_auth_context, require_observer

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/consent",
    tags=["consent"],
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Insufficient permissions"},
        404: {"description": "Consent not found"},
    },
)

# Stream metadata definitions - eliminate duplication
STREAM_METADATA: Dict[ConsentStream, Dict[str, Any]] = {
    ConsentStream.TEMPORARY: {
        "name": "Temporary",
        "description": "We forget about you in 14 days unless you say otherwise",
        "duration_days": 14,
        "auto_forget": True,
        "learning_enabled": False,
    },
    ConsentStream.PARTNERED: {
        "name": "Partnered",
        "description": "Explicit consent for mutual growth and learning",
        "duration_days": None,
        "auto_forget": False,
        "learning_enabled": True,
        "requires_categories": True,
    },
    ConsentStream.ANONYMOUS: {
        "name": "Anonymous",
        "description": "Statistics only, no identity retained",
        "duration_days": None,
        "auto_forget": False,
        "learning_enabled": True,
        "identity_removed": True,
    },
}

# Category metadata definitions - eliminate duplication
CATEGORY_METADATA: Dict[ConsentCategory, Dict[str, str]] = {
    ConsentCategory.INTERACTION: {
        "name": "Interaction",
        "description": "Learn from our conversations",
    },
    ConsentCategory.PREFERENCE: {
        "name": "Preference",
        "description": "Learn preferences and patterns",
    },
    ConsentCategory.IMPROVEMENT: {
        "name": "Improvement",
        "description": "Use for self-improvement",
    },
    ConsentCategory.RESEARCH: {
        "name": "Research",
        "description": "Use for research purposes",
    },
    ConsentCategory.SHARING: {
        "name": "Sharing",
        "description": "Share learnings with others",
    },
}

# Partnership status messages - eliminate duplication
PARTNERSHIP_MESSAGES = {
    "accepted": "Partnership approved! You now have PARTNERED consent.",
    "rejected": "Partnership request was declined by the agent.",
    "deferred": "Agent needs more information about the partnership.",
    "pending": "Partnership request is being considered by the agent.",
    "none": "No pending partnership request.",
}


def get_consent_manager(request: Request) -> ConsentService:
    """Get the consent manager instance from app state."""
    if not hasattr(request.app.state, "consent_manager") or not request.app.state.consent_manager:
        # Create a default instance if not initialized
        from ciris_engine.logic.services.lifecycle.time import TimeService

        time_service = TimeService()
        request.app.state.consent_manager = ConsentService(time_service=time_service)

    # Return the consent manager with explicit type
    manager: ConsentService = request.app.state.consent_manager
    return manager


def _build_consent_record(
    consent_status: ConsentStatus, user_id: str, status_filter: Optional[str] = None
) -> ConsentRecordResponse:
    """
    Build consent record response - eliminates duplication.

    Args:
        consent_status: The consent status object
        user_id: User ID
        status_filter: Optional status filter (ACTIVE/REVOKED/etc)

    Returns:
        Consent record response
    """
    # TEMPORARY and PARTNERED are the active streams
    is_active = consent_status.stream in [ConsentStream.TEMPORARY, ConsentStream.PARTNERED]

    # Determine status
    if status_filter == "ACTIVE":
        status = "ACTIVE"
    else:
        status = "ACTIVE" if is_active else "REVOKED"

    return ConsentRecordResponse(
        id=f"consent_{user_id}",
        user_id=user_id,
        status=status,
        scope="general",
        purpose="Agent interaction and data processing",
        granted_at=consent_status.timestamp.isoformat() if hasattr(consent_status, "timestamp") else None,
        expires_at=consent_status.expiry.isoformat() if hasattr(consent_status, "expiry") else None,
        metadata={},
    )


@router.get("/status", response_model=ConsentStatusResponse)
async def get_consent_status(
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> ConsentStatusResponse:
    """
    Get current consent status for authenticated user.

    Returns None if no consent exists (user has not interacted yet).
    """
    user_id = auth.user_id  # Use user_id from auth context
    try:
        consent = await manager.get_consent(user_id)
        return ConsentStatusResponse(
            has_consent=True,
            user_id=user_id,
            stream=consent.stream.value if hasattr(consent.stream, "value") else str(consent.stream),
            granted_at=consent.granted_at.isoformat() if hasattr(consent, "granted_at") else None,
            expires_at=(
                consent.expires_at.isoformat() if hasattr(consent, "expires_at") and consent.expires_at else None
            ),
        )
    except ConsentNotFoundError:
        # No consent exists yet - user hasn't interacted
        return ConsentStatusResponse(
            has_consent=False,
            user_id=user_id,
            message="No consent record found. Consent will be created on first interaction.",
        )


@router.get("/query", response_model=ConsentQueryResponse)
async def query_consents(
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> ConsentQueryResponse:
    """
    Query consent records with optional filters.

    Args:
        status: Filter by status (ACTIVE, REVOKED, EXPIRED)
        user_id: Filter by user ID (admin only)

    Returns:
        Dictionary with consents list and total count
    """
    # For non-admin users, only show their own consents
    if auth.role != "ADMIN" and user_id and user_id != auth.user_id:
        raise HTTPException(status_code=403, detail="Cannot query other users' consents")

    # If no user_id specified, use authenticated user's ID
    if not user_id:
        user_id = auth.user_id

    # Get user's consent status
    try:
        consent_status = await manager.get_consent(user_id)
        # TEMPORARY and PARTNERED are the active streams
        is_active = consent_status.stream in [ConsentStream.TEMPORARY, ConsentStream.PARTNERED]

        # Filter by status if requested
        if status == "ACTIVE" and not is_active:
            consents = []
        else:
            consent_record = _build_consent_record(consent_status, user_id, status)
            consents = [consent_record]
    except Exception:
        # No consent found
        consents = []

    return ConsentQueryResponse(consents=consents, total=len(consents))


@router.post("/grant", response_model=ConsentStatus)
async def grant_consent(
    request: ConsentRequest,
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> ConsentStatus:
    """
    Grant or update consent.

    Streams:
    - TEMPORARY: 14-day auto-forget (default)
    - PARTNERED: Explicit consent for mutual growth
    - ANONYMOUS: Statistics only, no identity
    """
    # Ensure user can only update their own consent
    request.user_id = auth.user_id

    # Generate channel_id for API requests (needed for partnership tasks)
    channel_id = f"api_{auth.user_id}"

    try:
        result = await manager.grant_consent(request, channel_id=channel_id)

        # Check if this created a pending partnership request
        if request.stream == ConsentStream.PARTNERED:
            # Check if there's a pending partnership
            partnership_status = await manager.check_pending_partnership(auth.user_id)
            if partnership_status == "pending":
                # Return a special response indicating partnership is pending
                return ConsentStatus(
                    user_id=result.user_id,
                    stream=result.stream,  # Still shows current stream
                    categories=result.categories,
                    granted_at=result.granted_at,
                    expires_at=result.expires_at,
                    last_modified=result.last_modified,
                    impact_score=result.impact_score,
                    attribution_count=result.attribution_count,
                    # Add a note about pending partnership
                )

        return result
    except ConsentValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )


@router.post("/revoke", response_model=ConsentDecayStatus)
async def revoke_consent(
    reason: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> ConsentDecayStatus:
    """
    Revoke consent and start decay protocol.

    - Immediate identity severance
    - 90-day pattern decay
    - Safety patterns may be retained (anonymized)
    """
    user_id = auth.user_id
    try:
        return await manager.revoke_consent(user_id, reason)
    except ConsentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No consent found to revoke",
        )


@router.get("/impact", response_model=ConsentImpactReport)
async def get_impact_report(
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> ConsentImpactReport:
    """
    Get impact report showing contribution to collective learning.

    Shows:
    - Patterns contributed
    - Users helped
    - Impact score
    - Example contributions (anonymized)
    """
    user_id = auth.user_id
    try:
        return await manager.get_impact_report(user_id)
    except ConsentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No consent data found",
        )
    except ValueError as e:
        # Handle memory bus requirement error
        if "memory bus" in str(e).lower():
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail=str(e),  # Pass through the actual error message
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Error generating impact report for {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate impact report: {str(e)}",
        )


@router.get("/audit", response_model=list[ConsentAuditEntry])
async def get_audit_trail(
    limit: int = 100,
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> list[ConsentAuditEntry]:
    """
    Get consent change history - IMMUTABLE AUDIT TRAIL.
    """
    user_id = auth.user_id
    try:
        audit_entries = await manager.get_audit_trail(user_id, limit)

        # Log if audit trail is empty (might indicate missing memory bus)
        if not audit_entries:
            logger.warning(f"Audit trail empty for {user_id} - may indicate missing memory bus or no consent history")

        return audit_entries
    except Exception as e:
        logger.error(f"Error retrieving audit trail for {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to retrieve audit trail: {str(e)}",
        )


@router.get("/streams", response_model=ConsentStreamsResponse)
async def get_consent_streams() -> ConsentStreamsResponse:
    """
    Get available consent streams and their descriptions.
    """
    # Convert metadata to typed models
    streams_dict = {
        str(k.value): StreamMetadata(
            name=v["name"],
            description=v["description"],
            duration_days=v.get("duration_days"),
            auto_forget=v.get("auto_forget", False),
            learning_enabled=v.get("learning_enabled", False),
            identity_removed=v.get("identity_removed", False),
            requires_categories=v.get("requires_categories", False),
        )
        for k, v in STREAM_METADATA.items()
    }
    return ConsentStreamsResponse(
        streams=streams_dict,
        default=ConsentStream.TEMPORARY.value,
    )


@router.get("/categories", response_model=ConsentCategoriesResponse)
async def get_consent_categories() -> ConsentCategoriesResponse:
    """
    Get available consent categories for PARTNERED stream.
    """
    # Convert metadata to typed models
    categories_dict = {
        str(k.value): CategoryMetadata(
            name=v["name"],
            description=v["description"],
        )
        for k, v in CATEGORY_METADATA.items()
    }
    return ConsentCategoriesResponse(categories=categories_dict)


@router.get("/partnership/status", response_model=PartnershipStatusResponse)
async def check_partnership_status(
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> PartnershipStatusResponse:
    """
    Check status of pending partnership request.

    Returns current status and any pending partnership request outcome.
    """
    user_id = auth.user_id

    # Check for pending partnership
    status = await manager.check_pending_partnership(user_id)

    # Get current consent status
    try:
        current_consent = await manager.get_consent(user_id)
        current_stream = current_consent.stream
    except ConsentNotFoundError:
        current_stream = ConsentStream.TEMPORARY

    # Convert enum to string
    stream_value = current_stream.value if hasattr(current_stream, "value") else str(current_stream)

    # Use the message lookup to eliminate duplicate if/elif chains
    message_key = status if status in PARTNERSHIP_MESSAGES else "none"
    message = PARTNERSHIP_MESSAGES[message_key]

    return PartnershipStatusResponse(
        current_stream=stream_value,
        partnership_status=status or "none",
        message=message,
    )


@router.post("/cleanup", response_model=ConsentCleanupResponse)
async def cleanup_expired(
    _auth: AuthContext = Depends(require_observer),
    manager: ConsentService = Depends(get_consent_manager),
) -> ConsentCleanupResponse:
    """
    Clean up expired TEMPORARY consents (admin only).

    HARD DELETE after 14 days - NO GRACE PERIOD.
    """
    count = await manager.cleanup_expired()
    return ConsentCleanupResponse(
        cleaned=count,
        message=f"Cleaned up {count} expired consent records",
    )


# DSAR helper functions to reduce cognitive complexity
async def _get_consent_export_data(manager: ConsentService, user_id: str) -> Optional[dict[str, object]]:
    """Extract consent data for DSAR export.

    Args:
        manager: Consent service manager
        user_id: User ID

    Returns:
        Consent data dictionary or None if not found
    """
    try:
        consent = await manager.get_consent(user_id)
        return {
            "user_id": user_id,
            "stream": consent.stream.value if hasattr(consent.stream, "value") else str(consent.stream),
            "categories": [c.value if hasattr(c, "value") else str(c) for c in consent.categories],
            "granted_at": consent.granted_at.isoformat() if hasattr(consent, "granted_at") else None,
            "expires_at": (
                consent.expires_at.isoformat() if hasattr(consent, "expires_at") and consent.expires_at else None
            ),
            "last_modified": (consent.last_modified.isoformat() if hasattr(consent, "last_modified") else None),
        }
    except ConsentNotFoundError:
        return None


async def _get_impact_export_data(manager: ConsentService, user_id: str) -> Optional[dict[str, object]]:
    """Extract impact data for DSAR export.

    Args:
        manager: Consent service manager
        user_id: User ID

    Returns:
        Impact data dictionary or None if not found
    """
    try:
        impact = await manager.get_impact_report(user_id)
        return {
            "total_interactions": impact.total_interactions,
            "patterns_contributed": impact.patterns_contributed,
            "users_helped": impact.users_helped,
            "categories_active": [c.value if hasattr(c, "value") else str(c) for c in impact.categories_active],
            "impact_score": impact.impact_score,
            "example_contributions": impact.example_contributions,
        }
    except ConsentNotFoundError:
        return None


async def _get_audit_export_data(manager: ConsentService, user_id: str) -> list[dict[str, object]]:
    """Extract audit trail data for DSAR export.

    Args:
        manager: Consent service manager
        user_id: User ID

    Returns:
        List of audit entry dictionaries (empty list if error)
    """
    try:
        audit_entries = await manager.get_audit_trail(user_id, limit=1000)
        return [
            {
                "entry_id": entry.entry_id,
                "user_id": entry.user_id,
                "timestamp": entry.timestamp.isoformat(),
                "previous_stream": (
                    entry.previous_stream.value
                    if hasattr(entry.previous_stream, "value")
                    else str(entry.previous_stream)
                ),
                "new_stream": (entry.new_stream.value if hasattr(entry.new_stream, "value") else str(entry.new_stream)),
                "previous_categories": [c.value if hasattr(c, "value") else str(c) for c in entry.previous_categories],
                "new_categories": [c.value if hasattr(c, "value") else str(c) for c in entry.new_categories],
                "initiated_by": entry.initiated_by,
                "reason": entry.reason,
            }
            for entry in audit_entries
        ]
    except Exception:
        return []


# DSAR (Data Subject Access Request) endpoints
@router.post("/dsar/initiate", response_model=DSARInitiateResponse)
async def initiate_dsar(
    request_type: str = "full",
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> DSARInitiateResponse:
    """
    Initiate automated DSAR (Data Subject Access Request).

    Args:
        request_type: Type of DSAR - "full", "consent_only", "impact_only", or "audit_only"

    Returns:
        Export data matching the request type
    """
    user_id = auth.user_id

    try:
        # Build the export data based on request type using helper functions
        export_data: dict[str, object] = {}

        if request_type in ["full", "consent_only"]:
            export_data["consent"] = await _get_consent_export_data(manager, user_id)

        if request_type in ["full", "impact_only"]:
            export_data["impact"] = await _get_impact_export_data(manager, user_id)

        if request_type in ["full", "audit_only"]:
            export_data["audit_trail"] = await _get_audit_export_data(manager, user_id)

        # Generate a request ID for tracking (using timezone-aware datetime)
        from datetime import datetime, timezone

        request_id = f"dsar_{user_id}_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"

        return DSARInitiateResponse(
            request_id=request_id,
            user_id=user_id,
            request_type=request_type,
            status="completed",
            export_data=export_data,
        )

    except Exception as e:
        logger.error(f"Error generating DSAR for {user_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate DSAR: {str(e)}",
        )


@router.get("/dsar/status/{request_id}", response_model=DSARStatusResponse)
async def get_dsar_status(
    request_id: str,
    auth: AuthContext = Depends(get_auth_context),
) -> DSARStatusResponse:
    """
    Get status of a DSAR request.

    Since DSAR requests are processed immediately, this always returns "completed".
    In a production system with async processing, this would track actual status.
    """
    # Extract user_id from request_id (format: dsar_{user_id}_{timestamp})
    parts = request_id.split("_")
    if len(parts) < 3 or parts[0] != "dsar":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid request_id format",
        )

    request_user_id = "_".join(parts[1:-1])  # Reconstruct user_id (may contain underscores)

    # Verify the request belongs to the authenticated user
    if request_user_id != auth.user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot access another user's DSAR request",
        )

    return DSARStatusResponse(
        request_id=request_id,
        user_id=auth.user_id,
        status="completed",
        message="DSAR request completed - data is immediately available",
    )
