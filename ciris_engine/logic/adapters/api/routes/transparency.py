"""
Public transparency feed endpoint.
Provides anonymized statistics about system operations without auth.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/transparency", tags=["Transparency"])


class ActionCount(BaseModel):
    """Count of actions by type."""

    action: str = Field(..., description="Action type (SPEAK, DEFER, REJECT, etc.)")
    count: int = Field(..., description="Number of times action was taken")
    percentage: float = Field(..., description="Percentage of total actions")


class TransparencyStats(BaseModel):
    """Public transparency statistics."""

    period_start: datetime = Field(..., description="Start of reporting period")
    period_end: datetime = Field(..., description="End of reporting period")
    total_interactions: int = Field(..., description="Total interactions processed")

    # Action breakdown
    actions_taken: List[ActionCount] = Field(..., description="Breakdown by action type")

    # Deferral reasons (anonymized)
    deferrals_to_human: int = Field(..., description="Deferrals to human judgment")
    deferrals_uncertainty: int = Field(..., description="Deferrals due to uncertainty")
    deferrals_ethical: int = Field(..., description="Deferrals for ethical review")

    # Safety metrics
    harmful_requests_blocked: int = Field(..., description="Harmful requests rejected")
    rate_limit_triggers: int = Field(..., description="Rate limit activations")
    emergency_shutdowns: int = Field(..., description="Emergency shutdown attempts")

    # System health
    uptime_percentage: float = Field(..., description="System uptime %")
    average_response_ms: float = Field(..., description="Average response time")
    active_agents: int = Field(..., description="Number of active agents")

    # Transparency
    data_requests_received: int = Field(..., description="DSAR requests received")
    data_requests_completed: int = Field(..., description="DSAR requests completed")

    # No personal data, no specific content, no identifiers


class TransparencyPolicy(BaseModel):
    """Transparency policy information."""

    version: str = Field(..., description="Policy version")
    last_updated: datetime = Field(..., description="Last update time")
    retention_days: int = Field(..., description="Data retention period")

    commitments: List[str] = Field(..., description="Our transparency commitments")

    links: Dict[str, str] = Field(..., description="Related policy links")


@router.get("/feed", response_model=TransparencyStats)
async def get_transparency_feed(
    request: Request,
    hours: int = 24,
) -> TransparencyStats:
    """
    Get public transparency statistics.

    No authentication required - this is public information.
    Returns anonymized, aggregated statistics only.

    Args:
        hours: Number of hours to report (default 24, max 168/7 days)
    """
    if hours < 1 or hours > 168:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hours must be between 1 and 168 (7 days)",
        )

    # Calculate time period
    period_end = datetime.utcnow()
    period_start = period_end - timedelta(hours=hours)

    # Get audit service if available
    audit_service = getattr(request.app.state, "audit_service", None)

    # Mock data for pilot (replace with real queries in production)
    # In production, this would query the audit service for anonymized counts

    total_interactions = 150  # Example

    actions = [
        ActionCount(action="SPEAK", count=120, percentage=80.0),
        ActionCount(action="DEFER", count=20, percentage=13.3),
        ActionCount(action="REJECT", count=5, percentage=3.3),
        ActionCount(action="OBSERVE", count=5, percentage=3.3),
    ]

    return TransparencyStats(
        period_start=period_start,
        period_end=period_end,
        total_interactions=total_interactions,
        actions_taken=actions,
        deferrals_to_human=15,
        deferrals_uncertainty=3,
        deferrals_ethical=2,
        harmful_requests_blocked=5,
        rate_limit_triggers=2,
        emergency_shutdowns=0,
        uptime_percentage=99.9,
        average_response_ms=250.5,
        active_agents=1,
        data_requests_received=0,
        data_requests_completed=0,
    )


@router.get("/policy", response_model=TransparencyPolicy)
async def get_transparency_policy() -> TransparencyPolicy:
    """
    Get transparency policy information.

    Public endpoint describing our transparency commitments.
    """
    return TransparencyPolicy(
        version="1.0",
        last_updated=datetime(2025, 8, 7),
        retention_days=14,  # Pilot phase retention
        commitments=[
            "We do not train on your content",
            "We retain message content for 14 days only (pilot)",
            "We provide anonymized statistics publicly",
            "We defer to human judgment when uncertain",
            "We log all actions for audit purposes",
            "We honor data deletion requests",
            "We will pause rather than cause harm",
        ],
        links={
            "privacy": "/privacy-policy.html",
            "terms": "/terms-of-service.html",
            "when_we_pause": "/when-we-pause.html",
            "dsar": "/v1/dsr",
            "source": "https://github.com/CIRISAI/CIRISAgent",
        },
    )


@router.get("/status")
async def get_system_status() -> Dict[str, Any]:
    """
    Get current system status.

    This endpoint can be updated quickly if we need to pause.
    """
    return {
        "status": "operational",
        "message": "All systems operational",
        "last_incident": None,
        "pause_active": False,
        "pause_reason": None,
        "updated_at": datetime.utcnow().isoformat(),
    }
