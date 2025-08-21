"""
Consent management API endpoints - FAIL FAST, NO FAKE DATA.

Implements Consensual Evolution Protocol v0.2.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from ciris_engine.logic.services.consent.consent_manager import (
    ConsentManager,
    ConsentNotFoundError,
    ConsentValidationError,
)
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


def get_consent_manager(request: Request) -> ConsentManager:
    """Get the consent manager instance from app state."""
    if not hasattr(request.app.state, "consent_manager") or not request.app.state.consent_manager:
        # Create a default instance if not initialized
        from ciris_engine.logic.services.infrastructure.time_service import TimeService

        time_service = TimeService()
        request.app.state.consent_manager = ConsentManager(time_service=time_service)

    return request.app.state.consent_manager


@router.get("/status", response_model=ConsentStatus)
async def get_consent_status(
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentManager = Depends(get_consent_manager),
) -> ConsentStatus:
    """
    Get current consent status for authenticated user.

    Returns default TEMPORARY (14-day) consent if none exists.
    """
    user_id = auth.username  # Use username as user_id
    try:
        return await manager.get_consent(user_id)
    except ConsentNotFoundError:
        # Create default TEMPORARY consent
        request = ConsentRequest(
            user_id=user_id,
            stream=ConsentStream.TEMPORARY,
            categories=[],
            reason="Default TEMPORARY consent on first API access",
        )
        return await manager.grant_consent(request)


@router.post("/grant", response_model=ConsentStatus)
async def grant_consent(
    request: ConsentRequest,
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentManager = Depends(get_consent_manager),
) -> ConsentStatus:
    """
    Grant or update consent.

    Streams:
    - TEMPORARY: 14-day auto-forget (default)
    - PARTNERED: Explicit consent for mutual growth
    - ANONYMOUS: Statistics only, no identity
    """
    # Ensure user can only update their own consent
    request.user_id = auth.username

    try:
        result = await manager.grant_consent(request)

        # Check if this created a pending partnership request
        if request.stream == ConsentStream.PARTNERED:
            # Check if there's a pending partnership
            partnership_status = await manager.check_pending_partnership(auth.username)
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
    manager: ConsentManager = Depends(get_consent_manager),
) -> ConsentDecayStatus:
    """
    Revoke consent and start decay protocol.

    - Immediate identity severance
    - 90-day pattern decay
    - Safety patterns may be retained (anonymized)
    """
    user_id = auth.username
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
    manager: ConsentManager = Depends(get_consent_manager),
) -> ConsentImpactReport:
    """
    Get impact report showing contribution to collective learning.

    Shows:
    - Patterns contributed
    - Users helped
    - Impact score
    - Example contributions (anonymized)
    """
    user_id = auth.username
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
    manager: ConsentManager = Depends(get_consent_manager),
) -> list[ConsentAuditEntry]:
    """
    Get consent change history - IMMUTABLE AUDIT TRAIL.
    """
    user_id = auth.username
    return await manager.get_audit_trail(user_id, limit)


@router.get("/streams", response_model=dict)
async def get_consent_streams() -> dict:
    """
    Get available consent streams and their descriptions.
    """
    return {
        "streams": {
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
        },
        "default": ConsentStream.TEMPORARY,
    }


@router.get("/categories", response_model=dict)
async def get_consent_categories() -> dict:
    """
    Get available consent categories for PARTNERED stream.
    """
    return {
        "categories": {
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
        },
    }


@router.get("/partnership/status", response_model=dict)
async def check_partnership_status(
    auth: AuthContext = Depends(get_auth_context),
    manager: ConsentManager = Depends(get_consent_manager),
) -> dict:
    """
    Check status of pending partnership request.

    Returns current status and any pending partnership request outcome.
    """
    user_id = auth.username

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

    if status == "accepted":
        response["message"] = "Partnership approved! You now have PARTNERED consent."
    elif status == "rejected":
        response["message"] = "Partnership request was declined by the agent."
    elif status == "deferred":
        response["message"] = "Agent needs more information about the partnership."
    elif status == "pending":
        response["message"] = "Partnership request is being considered by the agent."
    else:
        response["message"] = "No pending partnership request."

    return response


@router.post("/cleanup", response_model=dict)
async def cleanup_expired(
    _auth: AuthContext = Depends(require_observer),
    manager: ConsentManager = Depends(get_consent_manager),
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
