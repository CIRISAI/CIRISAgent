"""
Partnership Management API endpoints for admin dashboard.

Provides read-only observability endpoints for monitoring partnership requests:
- View pending partnership requests
- View partnership metrics and history
- Monitor aging requests requiring attention

NOTE: No manual approve/reject/defer endpoints - the agent makes these decisions autonomously.
This enforces CIRIS's "No Bypass Patterns" philosophy.
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ciris_engine.schemas.consent.core import PartnershipHistory, PartnershipMetrics, PartnershipRequest

from ..auth import get_current_user
from ..models import StandardResponse, TokenData

router = APIRouter(prefix="/partnership", tags=["Partnership"])


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
