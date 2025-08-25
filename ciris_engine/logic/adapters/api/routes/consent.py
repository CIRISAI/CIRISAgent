"""
Consent management API endpoints - FAIL FAST, NO FAKE DATA.

Implements Consensual Evolution Protocol v0.2.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ciris_engine.logic.services.governance.consent import ConsentNotFoundError, ConsentService, ConsentValidationError
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import (
    ConsentAuditEntry,
    ConsentCategory,
    ConsentDecayStatus,
    ConsentImpactReport,
    ConsentRequest,
    ConsentStatus,
    ConsentStream,
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
STREAM_METADATA = {
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
CATEGORY_METADATA = {
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

    return request.app.state.consent_manager


def _build_consent_dict(consent_status, user_id: str, status_filter: Optional[str] = None) -> dict:
    """
    Build consent dictionary - eliminates duplication.

    Args:
        consent_status: The consent status object
        user_id: User ID
        status_filter: Optional status filter (ACTIVE/REVOKED/etc)

    Returns:
        Consent dictionary
    """
    is_active = consent_status.stream in [ConsentStream.TEMPORARY, ConsentStream.PERSISTENT]

    # Determine status
    if status_filter == "ACTIVE":
        status = "ACTIVE"
    else:
        status = "ACTIVE" if is_active else "REVOKED"

    return {
        "id": f"consent_{user_id}",
        "user_id": user_id,
        "status": status,
        "scope": "general",
        "purpose": "Agent interaction and data processing",
        "granted_at": (consent_status.timestamp.isoformat() if hasattr(consent_status, "timestamp") else None),
        "expires_at": consent_status.expiry.isoformat() if hasattr(consent_status, "expiry") else None,
        "metadata": {},
    }


@router.get("/status")
async def get_consent_status(
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> dict:
    """
    Get current consent status for authenticated user.

    Returns None if no consent exists (user has not interacted yet).
    """
    user_id = auth.user_id  # Use user_id from auth context
    try:
        consent = await manager.get_consent(user_id)
        return {
            "has_consent": True,
            "user_id": user_id,
            "stream": consent.stream.value if hasattr(consent.stream, "value") else str(consent.stream),
            "granted_at": consent.granted_at.isoformat() if hasattr(consent, "granted_at") else None,
            "expires_at": consent.expires_at.isoformat() if hasattr(consent, "expires_at") else None,
        }
    except ConsentNotFoundError:
        # No consent exists yet - user hasn't interacted
        return {
            "has_consent": False,
            "user_id": user_id,
            "message": "No consent record found. Consent will be created on first interaction.",
        }


@router.get("/query")
async def query_consents(
    status: Optional[str] = None,
    user_id: Optional[str] = None,
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> dict:
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
        is_active = consent_status.stream in [ConsentStream.TEMPORARY, ConsentStream.PERSISTENT]

        # Filter by status if requested
        if status == "ACTIVE" and not is_active:
            consents = []
        else:
            consent_dict = _build_consent_dict(consent_status, user_id, status)
            consents = [consent_dict]
    except Exception:
        # No consent found
        consents = []

    return {"consents": consents, "total": len(consents)}


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
    return await manager.get_audit_trail(user_id, limit)


@router.get("/streams", response_model=dict)
async def get_consent_streams() -> dict:
    """
    Get available consent streams and their descriptions.
    """
    return {
        "streams": STREAM_METADATA,
        "default": ConsentStream.TEMPORARY,
    }


@router.get("/categories", response_model=dict)
async def get_consent_categories() -> dict:
    """
    Get available consent categories for PARTNERED stream.
    """
    return {
        "categories": CATEGORY_METADATA,
    }


@router.get("/partnership/status", response_model=dict)
async def check_partnership_status(
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentService = Depends(get_consent_manager),
) -> dict:
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

    response = {
        "current_stream": current_stream,
        "partnership_status": status or "none",
    }

    # Use the message lookup to eliminate duplicate if/elif chains
    message_key = status if status in PARTNERSHIP_MESSAGES else "none"
    response["message"] = PARTNERSHIP_MESSAGES[message_key]

    return response


@router.post("/cleanup", response_model=dict)
async def cleanup_expired(
    _auth: AuthContext = Depends(require_observer),
    manager: ConsentService = Depends(get_consent_manager),
) -> dict:
    """
    Clean up expired TEMPORARY consents (admin only).

    HARD DELETE after 14 days - NO GRACE PERIOD.
    """
    count = await manager.cleanup_expired()
    return {
        "cleaned": count,
        "message": f"Cleaned up {count} expired consent records",
    }
