"""
Partnership Management API endpoints for admin dashboard.

Provides endpoints for reviewing and managing partnership requests:
- View pending partnership requests
- Manually approve/reject/defer partnerships
- View partnership metrics and history
- Monitor aging requests requiring attention
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.schemas.consent.core import (
    PartnershipHistory,
    PartnershipMetrics,
    PartnershipOutcome,
    PartnershipRequest,
)

from ..auth import get_current_user
from ..models import StandardResponse, TokenData

router = APIRouter(prefix="/partnership", tags=["Partnership"])


class PartnershipActionRequest(BaseModel):
    """Request for manual partnership action."""

    notes: Optional[str] = Field(None, description="Optional admin notes about decision")


@router.get("/pending", response_model=StandardResponse)
async def list_pending_partnerships(
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    List all pending partnership requests (admin only).

    Returns list of pending requests with aging status and priority.
    Useful for admin dashboard to show requests requiring review.

    Requires: ADMIN or SYSTEM_ADMIN role
    """
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view pending partnerships",
        )

    # Get consent service from app state
    from ciris_engine.logic.services.governance.consent import ConsentService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    if hasattr(req.app.state, "consent_manager") and req.app.state.consent_manager:
        consent_manager = req.app.state.consent_manager
    else:
        # Create default instance if not initialized
        time_service = TimeService()
        consent_manager = ConsentService(time_service=time_service)

    # Get partnership manager
    partnership_manager = consent_manager._partnership_manager

    # Get typed pending partnerships
    pending: list[PartnershipRequest] = partnership_manager.list_pending_partnerships_typed()

    # Classify by aging status for dashboard summary
    normal = [p for p in pending if p.aging_status.value == "normal"]
    warning = [p for p in pending if p.aging_status.value == "warning"]
    critical = [p for p in pending if p.aging_status.value == "critical"]

    return StandardResponse(
        success=True,
        data={
            "requests": [p.model_dump() for p in pending],
            "total": len(pending),
            "by_status": {
                "normal": len(normal),
                "warning": len(warning),
                "critical": len(critical),
            },
        },
        message=f"Found {len(pending)} pending partnership requests",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "critical_count": len(critical),
        },
    )


@router.get("/metrics", response_model=StandardResponse)
async def get_partnership_metrics(
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Get partnership system metrics (admin only).

    Includes:
    - Total requests, approvals, rejections, deferrals
    - Approval/rejection/deferral rates
    - Average pending time
    - Count of critical aging requests

    Requires: ADMIN or SYSTEM_ADMIN role
    """
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view partnership metrics",
        )

    # Get consent service from app state
    from ciris_engine.logic.services.governance.consent import ConsentService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    if hasattr(req.app.state, "consent_manager") and req.app.state.consent_manager:
        consent_manager = req.app.state.consent_manager
    else:
        # Create default instance if not initialized
        time_service = TimeService()
        consent_manager = ConsentService(time_service=time_service)

    # Get partnership manager
    partnership_manager = consent_manager._partnership_manager

    # Get typed metrics
    metrics: PartnershipMetrics = partnership_manager.get_partnership_metrics_typed()

    return StandardResponse(
        success=True,
        data=metrics.model_dump(),
        message="Partnership metrics retrieved",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@router.post("/{user_id}/approve", response_model=StandardResponse)
async def approve_partnership(
    user_id: str,
    action: PartnershipActionRequest,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Manually approve a partnership request (admin only).

    This bypasses the agent approval task and immediately grants PARTNERED status.
    The user's consent stream is upgraded to PARTNERED with the requested categories.

    Requires: ADMIN or SYSTEM_ADMIN role
    """
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can approve partnerships",
        )

    # Get consent service from app state
    from ciris_engine.logic.services.governance.consent import ConsentService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    if hasattr(req.app.state, "consent_manager") and req.app.state.consent_manager:
        consent_manager = req.app.state.consent_manager
    else:
        # Create default instance if not initialized
        time_service = TimeService()
        consent_manager = ConsentService(time_service=time_service)

    # Get partnership manager
    partnership_manager = consent_manager._partnership_manager

    # Manual approval
    try:
        outcome: PartnershipOutcome = await partnership_manager.manual_approve(
            user_id=user_id,
            admin_username=current_user.username,
            notes=action.notes,
        )

        # Finalize the approval (upgrade consent stream)
        partnership_manager.finalize_partnership_approval(user_id, outcome.task_id)

        # Log the action
        import logging

        from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log, sanitize_username

        logger = logging.getLogger(__name__)
        safe_user_id = sanitize_for_log(user_id, max_length=100)
        safe_admin = sanitize_username(current_user.username)
        logger.info(f"Partnership approved for {safe_user_id} by admin {safe_admin}")

        return StandardResponse(
            success=True,
            data=outcome.model_dump(),
            message=f"Partnership approved for {user_id}",
            metadata={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "approved_by": current_user.username,
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error approving partnership for {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not approve partnership: {str(e)}",
        )


@router.post("/{user_id}/reject", response_model=StandardResponse)
async def reject_partnership(
    user_id: str,
    action: PartnershipActionRequest,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Manually reject a partnership request (admin only).

    The request is removed from pending queue and marked as rejected.
    The user remains in TEMPORARY stream with 14-day retention.

    Requires: ADMIN or SYSTEM_ADMIN role
    """
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can reject partnerships",
        )

    # Get consent service from app state
    from ciris_engine.logic.services.governance.consent import ConsentService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    if hasattr(req.app.state, "consent_manager") and req.app.state.consent_manager:
        consent_manager = req.app.state.consent_manager
    else:
        # Create default instance if not initialized
        time_service = TimeService()
        consent_manager = ConsentService(time_service=time_service)

    # Get partnership manager
    partnership_manager = consent_manager._partnership_manager

    # Manual rejection
    try:
        outcome: PartnershipOutcome = await partnership_manager.manual_reject(
            user_id=user_id,
            admin_username=current_user.username,
            reason=action.notes or "Manually rejected by admin",
            notes=action.notes,
        )

        # Log the action
        import logging

        from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log, sanitize_username

        logger = logging.getLogger(__name__)
        safe_user_id = sanitize_for_log(user_id, max_length=100)
        safe_admin = sanitize_username(current_user.username)
        logger.info(f"Partnership rejected for {safe_user_id} by admin {safe_admin}")

        return StandardResponse(
            success=True,
            data=outcome.model_dump(),
            message=f"Partnership rejected for {user_id}",
            metadata={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "rejected_by": current_user.username,
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error rejecting partnership for {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not reject partnership: {str(e)}",
        )


@router.post("/{user_id}/defer", response_model=StandardResponse)
async def defer_partnership(
    user_id: str,
    action: PartnershipActionRequest,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Defer a partnership decision (admin only).

    Marks the request as deferred for later review.
    The request remains in the pending queue but marked as deferred.

    Requires: ADMIN or SYSTEM_ADMIN role
    """
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can defer partnerships",
        )

    # Get consent service from app state
    from ciris_engine.logic.services.governance.consent import ConsentService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    if hasattr(req.app.state, "consent_manager") and req.app.state.consent_manager:
        consent_manager = req.app.state.consent_manager
    else:
        # Create default instance if not initialized
        time_service = TimeService()
        consent_manager = ConsentService(time_service=time_service)

    # Get partnership manager
    partnership_manager = consent_manager._partnership_manager

    # Manual deferral
    try:
        outcome: PartnershipOutcome = await partnership_manager.manual_defer(
            user_id=user_id,
            admin_username=current_user.username,
            reason=action.notes or "Deferred for further review",
            notes=action.notes,
        )

        # Log the action
        import logging

        from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log, sanitize_username

        logger = logging.getLogger(__name__)
        safe_user_id = sanitize_for_log(user_id, max_length=100)
        safe_admin = sanitize_username(current_user.username)
        logger.info(f"Partnership deferred for {safe_user_id} by admin {safe_admin}")

        return StandardResponse(
            success=True,
            data=outcome.model_dump(),
            message=f"Partnership deferred for {user_id}",
            metadata={
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "deferred_by": current_user.username,
            },
        )

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        logger.error(f"Error deferring partnership for {user_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not defer partnership: {str(e)}",
        )


@router.get("/history/{user_id}", response_model=StandardResponse)
async def get_partnership_history(
    user_id: str,
    req: Request,
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    Get partnership history for a user (admin only).

    Returns all historical partnership decisions for a specific user,
    including approved, rejected, deferred, and expired requests.

    Requires: ADMIN or SYSTEM_ADMIN role
    """
    if current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only administrators can view partnership history",
        )

    # Get consent service from app state
    from ciris_engine.logic.services.governance.consent import ConsentService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    if hasattr(req.app.state, "consent_manager") and req.app.state.consent_manager:
        consent_manager = req.app.state.consent_manager
    else:
        # Create default instance if not initialized
        time_service = TimeService()
        consent_manager = ConsentService(time_service=time_service)

    # Get partnership manager
    partnership_manager = consent_manager._partnership_manager

    # Get history
    history: PartnershipHistory = partnership_manager.get_partnership_history(user_id)

    return StandardResponse(
        success=True,
        data=history.model_dump(),
        message=f"Partnership history retrieved for {user_id}",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_requests": history.total_requests,
        },
    )
