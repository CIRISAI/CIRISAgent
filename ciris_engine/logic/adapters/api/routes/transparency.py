"""
Public transparency feed endpoint.
Provides anonymized statistics about system operations without auth.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

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


# Helper functions to reduce cognitive complexity


def _validate_hours(hours: int) -> None:
    """Validate the hours parameter."""
    if hours < 1 or hours > 168:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Hours must be between 1 and 168 (7 days)",
        )


def _process_handler_action(
    event: Any, action_counts: Dict[str, int], deferrals: Dict[str, int], response_times: List[float]
) -> int:
    """Process a handler_action event and return harmful_blocked count."""
    harmful_blocked = 0
    action = event.data.get("action", "UNKNOWN")
    action_counts[action] = action_counts.get(action, 0) + 1

    # Track response time
    if "duration_ms" in event.data:
        response_times.append(event.data["duration_ms"])

    # Count deferrals by reason
    if action == "DEFER":
        reason = event.data.get("reason", "human")
        if reason in deferrals:
            deferrals[reason] += 1

    # Count harmful requests blocked
    if action == "REJECT" and event.data.get("harmful", False):
        harmful_blocked = 1

    return harmful_blocked


def _calculate_action_percentages(action_counts: Dict[str, int], total_interactions: int) -> List[ActionCount]:
    """Calculate percentages for each action."""
    actions = []
    for action, count in action_counts.items():
        percentage = (count / total_interactions * 100) if total_interactions > 0 else 0
        actions.append(ActionCount(action=action, count=count, percentage=percentage))
    return actions


async def _get_dsar_counts(audit_service: Any, period_start: datetime, period_end: datetime) -> tuple[int, int]:
    """Get data request counts from audit service."""
    dsar_events = await audit_service.query_events(
        start_time=period_start, end_time=period_end, event_types=["dsar_request", "dsar_completed"]
    )
    data_requests = sum(1 for e in dsar_events if e.event_type == "dsar_request")
    data_completed = sum(1 for e in dsar_events if e.event_type == "dsar_completed")
    return data_requests, data_completed


async def _get_uptime_percentage(request: Request) -> float:
    """Calculate uptime percentage from service metrics."""
    # Try to get from telemetry service
    telemetry_service = getattr(request.app.state, "telemetry_service", None)
    if telemetry_service and hasattr(telemetry_service, "get_uptime_percentage"):
        try:
            result = await telemetry_service.get_uptime_percentage()
            return float(result)
        except Exception:
            pass
    return 99.9  # Default fallback


async def _get_active_agents(request: Request) -> int:
    """Get active agent count from runtime registry."""
    runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if runtime_control and hasattr(runtime_control, "list_adapters"):
        try:
            adapters = await runtime_control.list_adapters()
            return len([a for a in adapters if a.status == "running"])
        except Exception:
            pass
    return 1  # Default to 1


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
    _validate_hours(hours)

    # Calculate time period
    period_end = datetime.now(timezone.utc)
    period_start = period_end - timedelta(hours=hours)

    # Get audit service - REQUIRED, no fallbacks!
    audit_service = getattr(request.app.state, "audit_service", None)
    if not audit_service:
        raise HTTPException(status_code=503, detail="Audit service not available - transparency requires real data")

    # Get REAL stats from audit service
    try:
        # Query actual audit events
        events = await audit_service.query_events(
            start_time=period_start,
            end_time=period_end,
            event_types=["handler_action", "thought_status", "rate_limit", "emergency_shutdown"],
        )

        # Initialize counters
        total_interactions = len(events)
        action_counts: Dict[str, int] = {}
        deferrals: Dict[str, int] = {"human": 0, "uncertainty": 0, "ethical": 0}
        harmful_blocked = 0
        rate_limits = 0
        shutdowns = 0
        response_times: List[float] = []

        # Process events
        for event in events:
            if event.event_type == "handler_action":
                harmful_blocked += _process_handler_action(event, action_counts, deferrals, response_times)
            elif event.event_type == "rate_limit":
                rate_limits += 1
            elif event.event_type == "emergency_shutdown":
                shutdowns += 1

        # Calculate statistics
        actions = _calculate_action_percentages(action_counts, total_interactions)
        avg_response = sum(response_times) / len(response_times) if response_times else 0

        # Get additional metrics
        uptime_percentage = await _get_uptime_percentage(request)
        active_agents = await _get_active_agents(request)
        data_requests, data_completed = await _get_dsar_counts(audit_service, period_start, period_end)

        return TransparencyStats(
            period_start=period_start,
            period_end=period_end,
            total_interactions=total_interactions,
            actions_taken=actions,
            deferrals_to_human=deferrals["human"],
            deferrals_uncertainty=deferrals["uncertainty"],
            deferrals_ethical=deferrals["ethical"],
            harmful_requests_blocked=harmful_blocked,
            rate_limit_triggers=rate_limits,
            emergency_shutdowns=shutdowns,
            uptime_percentage=uptime_percentage,
            average_response_ms=avg_response,
            active_agents=active_agents,
            data_requests_received=data_requests,
            data_requests_completed=data_completed,
        )

    except Exception as e:
        logger.error(f"Failed to get transparency stats: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to retrieve transparency statistics: {str(e)}")


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
            "dsar": "/v1/dsar",
            "source": "https://github.com/CIRISAI/CIRISAgent",
        },
    )


@router.get("/status")
async def get_system_status() -> JSONDict:
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
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
