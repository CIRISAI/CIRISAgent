"""
Partnership Management API - Bilateral Consent for Consensual Evolution Protocol.

CIRIS partnerships are bilateral agreements requiring mutual consent from BOTH parties:
- Agent and User have EQUAL moral agency and autonomy
- Either party can initiate a partnership request
- Either party can accept, reject, or defer the other's request
- No admin bypass or manual override - both parties must consent

Endpoint Categories:
1. **Observability** (Admin-only, Read-only):
   - GET /pending: View all pending partnership requests
   - GET /metrics: View partnership system metrics
   - GET /history/{user_id}: View partnership history for a user

2. **Bilateral Decision** (User/Agent via SDK):
   - POST /decide: Accept/reject/defer a partnership request
     - Used by humans responding to agent-initiated requests
     - Used by agents responding to user-initiated requests (via SDK)
     - Both parties have equal autonomy in this process

Partnership Flow:
1. Either party requests partnership (user via grant_consent, agent via upgrade_relationship tool)
2. Creates task for the OTHER party to review
3. Recipient decides: accept (PARTNERED), reject (stays current stream), or defer (more info needed)
4. System updates consent status based on bilateral agreement

Philosophy: "No Bypass Patterns" - partnerships require genuine bilateral consent, not admin override.
"""

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ciris_engine.schemas.consent.core import PartnershipHistory, PartnershipMetrics, PartnershipRequest
from ciris_engine.schemas.runtime.enums import TaskStatus

from ..auth import get_current_user
from ..models import StandardResponse, TokenData


def _handle_partnership_accept(
    partnership_user_id: str,
    task_id: str,
    task: Any,
    partnership_manager: Any,
    current_user: TokenData,
) -> StandardResponse:
    """Handle partnership acceptance - creates PARTNERED consent status.

    Args:
        partnership_user_id: User ID for the partnership
        task_id: Partnership task ID
        task: Task object
        partnership_manager: Partnership manager instance
        current_user: Current authenticated user

    Returns:
        StandardResponse with partnership acceptance confirmation

    Raises:
        HTTPException: If partnership approval fails
    """
    import uuid

    from ciris_engine.logic.persistence import add_graph_node
    from ciris_engine.logic.persistence.models.tasks import update_task_status
    from ciris_engine.logic.services.lifecycle.time.service import TimeService
    from ciris_engine.schemas.consent.core import ConsentCategory, ConsentStatus, ConsentStream
    from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

    # Finalize the partnership approval
    partnership_data = partnership_manager.finalize_partnership_approval(partnership_user_id, task_id)

    if not partnership_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Partnership approval failed - request may have expired or already been processed",
        )

    # Create PARTNERED consent status
    now = datetime.now(timezone.utc)
    categories = partnership_data.get("categories", [ConsentCategory.INTERACTION])

    partnered_status = ConsentStatus(
        user_id=partnership_user_id,
        stream=ConsentStream.PARTNERED,
        categories=categories,
        granted_at=now,
        expires_at=None,  # PARTNERED doesn't expire
        last_modified=now,
        impact_score=0.0,
        attribution_count=0,
    )

    # Persist to graph
    node = GraphNode(
        id=f"consent/{partnership_user_id}",
        type=NodeType.CONSENT,
        scope=GraphScope.LOCAL,
        attributes={
            "stream": (
                partnered_status.stream.value if hasattr(partnered_status.stream, "value") else partnered_status.stream
            ),
            "categories": [c.value if hasattr(c, "value") else c for c in partnered_status.categories],
            "granted_at": partnered_status.granted_at.isoformat(),
            "expires_at": None,
            "last_modified": partnered_status.last_modified.isoformat(),
            "impact_score": partnered_status.impact_score,
            "attribution_count": partnered_status.attribution_count,
            "partnership_approved": True,
            "approval_task_id": task_id,
        },
        updated_by="consent_manager",
        updated_at=now,
    )

    time_service = TimeService()
    add_graph_node(node, time_service, None)

    # Update task status to COMPLETED
    update_task_status(
        task_id=task.task_id,
        new_status=TaskStatus.COMPLETED,
        occurrence_id=str(uuid.uuid4()),
        time_service=time_service,
        db_path=None,
    )

    return StandardResponse(
        success=True,
        data={
            "user_id": partnership_user_id,
            "decision": "accepted",
            "consent_status": partnered_status.model_dump(),
            "task_id": task_id,
        },
        message=f"Partnership accepted for {partnership_user_id}",
        metadata={
            "timestamp": now.isoformat(),
            "decided_by": current_user.username,
        },
    )


def _handle_partnership_reject(
    partnership_user_id: str,
    task_id: str,
    task: Any,
    partnership_manager: Any,
    current_user: TokenData,
    reason: Optional[str],
) -> StandardResponse:
    """Handle partnership rejection.

    Args:
        partnership_user_id: User ID for the partnership
        task_id: Partnership task ID
        task: Task object
        partnership_manager: Partnership manager instance
        current_user: Current authenticated user
        reason: Optional reason for rejection

    Returns:
        StandardResponse with partnership rejection confirmation
    """
    import uuid

    from ciris_engine.logic.persistence.models.tasks import update_task_status
    from ciris_engine.logic.services.lifecycle.time.service import TimeService
    from ciris_engine.schemas.consent.core import PartnershipOutcome, PartnershipOutcomeType

    # Remove from pending partnerships
    if partnership_user_id in partnership_manager._pending_partnerships:
        del partnership_manager._pending_partnerships[partnership_user_id]

    # Update task status to REJECTED
    time_service = TimeService()
    update_task_status(
        task_id=task.task_id,
        new_status=TaskStatus.REJECTED,
        occurrence_id=str(uuid.uuid4()),
        time_service=time_service,
        db_path=None,
    )

    # Track rejection
    partnership_manager._partnership_rejections += 1

    # Create outcome record
    outcome = PartnershipOutcome(
        user_id=partnership_user_id,
        task_id=task_id,
        outcome_type=PartnershipOutcomeType.REJECTED,
        decided_by=current_user.username,
        decided_at=datetime.now(timezone.utc),
        reason=reason or "Partnership request was declined",
        notes=None,
    )

    # Record in history
    if partnership_user_id not in partnership_manager._partnership_history:
        partnership_manager._partnership_history[partnership_user_id] = []
    partnership_manager._partnership_history[partnership_user_id].append(outcome)

    return StandardResponse(
        success=True,
        data={
            "user_id": partnership_user_id,
            "decision": "rejected",
            "reason": reason or "Partnership request was declined",
            "task_id": task_id,
        },
        message=f"Partnership rejected for {partnership_user_id}",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decided_by": current_user.username,
        },
    )


def _handle_partnership_defer(
    partnership_user_id: str,
    task_id: str,
    task: Any,
    partnership_manager: Any,
    current_user: TokenData,
    reason: Optional[str],
) -> StandardResponse:
    """Handle partnership deferral.

    Args:
        partnership_user_id: User ID for the partnership
        task_id: Partnership task ID
        task: Task object
        partnership_manager: Partnership manager instance
        current_user: Current authenticated user
        reason: Optional reason for deferral

    Returns:
        StandardResponse with partnership deferral confirmation
    """
    import uuid

    from ciris_engine.logic.persistence.models.tasks import update_task_status
    from ciris_engine.logic.services.lifecycle.time.service import TimeService
    from ciris_engine.schemas.consent.core import PartnershipOutcome, PartnershipOutcomeType

    # Update task status to DEFERRED
    time_service = TimeService()
    update_task_status(
        task_id=task.task_id,
        new_status=TaskStatus.DEFERRED,
        occurrence_id=str(uuid.uuid4()),
        time_service=time_service,
        db_path=None,
    )

    # Track deferral
    partnership_manager._partnership_deferrals += 1

    # Create outcome record
    outcome = PartnershipOutcome(
        user_id=partnership_user_id,
        task_id=task_id,
        outcome_type=PartnershipOutcomeType.DEFERRED,
        decided_by=current_user.username,
        decided_at=datetime.now(timezone.utc),
        reason=reason or "More information needed before deciding",
        notes=None,
    )

    # Record in history
    if partnership_user_id not in partnership_manager._partnership_history:
        partnership_manager._partnership_history[partnership_user_id] = []
    partnership_manager._partnership_history[partnership_user_id].append(outcome)

    return StandardResponse(
        success=True,
        data={
            "user_id": partnership_user_id,
            "decision": "deferred",
            "reason": reason or "More information needed before deciding",
            "task_id": task_id,
        },
        message=f"Partnership deferred for {partnership_user_id}",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "decided_by": current_user.username,
        },
    )


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


@router.post("/decide", response_model=StandardResponse)
async def decide_partnership(
    req: Request,
    decision_data: dict[str, Any],
    current_user: TokenData = Depends(get_current_user),
) -> StandardResponse:
    """
    User decides on a partnership request (accept/reject/defer).

    This endpoint handles BOTH flows with equal moral agency:
    1. User responding to agent-initiated partnership request
    2. Agent responding to user-initiated partnership request (via SDK)

    Both parties have equal autonomy in the bilateral consent process.

    Request body:
        {
            "task_id": "partnership_user123_abc123",
            "decision": "accept" | "reject" | "defer",
            "reason": "Optional reason for decision"
        }

    Returns:
        StandardResponse with decision confirmation and updated consent status
    """
    # Get consent service from app state
    from ciris_engine.logic import persistence
    from ciris_engine.logic.services.governance.consent import ConsentService
    from ciris_engine.logic.services.lifecycle.time.service import TimeService

    if hasattr(req.app.state, "consent_manager") and req.app.state.consent_manager:
        consent_manager = req.app.state.consent_manager
    else:
        # Create default instance if not initialized
        time_service = TimeService()
        consent_manager = ConsentService(time_service=time_service)

    # Extract decision parameters
    task_id = decision_data.get("task_id")
    decision = decision_data.get("decision")
    reason = decision_data.get("reason")

    if not task_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="task_id is required",
        )

    if decision not in ["accept", "reject", "defer"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="decision must be 'accept', 'reject', or 'defer'",
        )

    # Get the task to verify it exists and extract user_id
    task = persistence.get_task_by_id(task_id)
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Partnership task {task_id} not found",
        )

    # Extract user_id from task context
    partnership_user_id = task.context.user_id if task.context else None
    if not partnership_user_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Task does not contain valid user context",
        )

    # Verify the current user has permission to decide on this partnership
    # Either the user involved in the partnership OR an admin can decide
    if current_user.username != partnership_user_id and current_user.role not in ["ADMIN", "SYSTEM_ADMIN"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can only decide on your own partnership requests",
        )

    # Handle the decision with extracted helper functions
    partnership_manager = consent_manager._partnership_manager

    if decision == "accept":
        return _handle_partnership_accept(partnership_user_id, task_id, task, partnership_manager, current_user)
    elif decision == "reject":
        return _handle_partnership_reject(partnership_user_id, task_id, task, partnership_manager, current_user, reason)
    else:  # defer
        return _handle_partnership_defer(partnership_user_id, task_id, task, partnership_manager, current_user, reason)
