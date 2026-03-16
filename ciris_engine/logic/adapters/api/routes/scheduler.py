"""
Scheduler endpoints for CIRIS API v1.

Provides access to scheduled tasks and task scheduling functionality.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any, List, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from ciris_engine.schemas.api.responses import ResponseMetadata, SuccessResponse
from ciris_engine.schemas.runtime.extended import ScheduledTaskInfo

from ._common import RESPONSES_400, RESPONSES_500_503, AuthAdminDep, AuthObserverDep

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/scheduler", tags=["scheduler"])


# Request/Response models


class ScheduledTaskResponse(BaseModel):
    """Scheduled task information for API responses."""

    task_id: str = Field(..., description="Unique task identifier")
    name: str = Field(..., description="Human-readable task name")
    goal_description: str = Field(..., description="What the task aims to achieve")
    status: str = Field(..., description="Task status: PENDING, ACTIVE, COMPLETE, FAILED, CANCELLED")
    defer_until: Optional[str] = Field(None, description="ISO timestamp for one-time execution")
    schedule_cron: Optional[str] = Field(None, description="Cron expression for recurring tasks")
    created_at: str = Field(..., description="Creation timestamp (ISO format)")
    last_triggered_at: Optional[str] = Field(None, description="Last execution timestamp (ISO format)")
    deferral_count: int = Field(default=0, description="Number of times task was deferred")
    is_recurring: bool = Field(..., description="Whether this is a recurring task")


class ScheduledTasksListResponse(BaseModel):
    """Response containing list of scheduled tasks."""

    tasks: List[ScheduledTaskResponse] = Field(..., description="List of scheduled tasks")
    total: int = Field(..., description="Total number of tasks")
    active_count: int = Field(..., description="Number of active/pending tasks")
    recurring_count: int = Field(..., description="Number of recurring tasks")


class CreateScheduledTaskRequest(BaseModel):
    """Request to create a new scheduled task."""

    name: str = Field(..., min_length=1, max_length=200, description="Human-readable task name")
    goal_description: str = Field(..., min_length=1, max_length=1000, description="What the task aims to achieve")
    trigger_prompt: str = Field(..., min_length=1, max_length=2000, description="Prompt to execute when triggered")
    defer_until: Optional[str] = Field(
        None, description="ISO timestamp for one-time execution (mutually exclusive with schedule_cron)"
    )
    schedule_cron: Optional[str] = Field(
        None, description="Cron expression for recurring tasks (e.g., '0 9 * * *' for daily at 9am)"
    )


class CancelTaskResponse(BaseModel):
    """Response after canceling a task."""

    success: bool = Field(..., description="Whether the task was cancelled")
    task_id: str = Field(..., description="ID of the cancelled task")
    message: str = Field(..., description="Status message")


class SchedulerStatsResponse(BaseModel):
    """Scheduler statistics."""

    tasks_scheduled_total: int = Field(..., description="Total tasks ever scheduled")
    tasks_completed_total: int = Field(..., description="Total tasks completed")
    tasks_failed_total: int = Field(..., description="Total tasks that failed")
    tasks_pending: int = Field(..., description="Currently pending tasks")
    recurring_tasks: int = Field(..., description="Number of recurring tasks")
    oneshot_tasks: int = Field(..., description="Number of one-time tasks")
    scheduler_uptime_seconds: float = Field(..., description="Scheduler service uptime")


# Helper functions


def _get_task_scheduler(request: Request) -> Any:
    """Get task scheduler from app state with validation."""
    task_scheduler = getattr(request.app.state, "task_scheduler", None)
    if not task_scheduler:
        raise HTTPException(status_code=503, detail="Task scheduler service not available")
    return task_scheduler


def _convert_to_response(task_info: ScheduledTaskInfo) -> ScheduledTaskResponse:
    """Convert ScheduledTaskInfo to API response format."""
    return ScheduledTaskResponse(
        task_id=task_info.task_id,
        name=task_info.name,
        goal_description=task_info.goal_description,
        status=task_info.status,
        defer_until=task_info.defer_until,
        schedule_cron=task_info.schedule_cron,
        created_at=task_info.created_at,
        last_triggered_at=task_info.last_triggered_at,
        deferral_count=task_info.deferral_count,
        is_recurring=task_info.schedule_cron is not None,
    )


async def _get_dream_schedules_from_graph(request: Request) -> List[ScheduledTaskInfo]:
    """Query graph memory for scheduled dream sessions."""
    from ciris_engine.schemas.services.graph.memory import GraphQuery
    from ciris_engine.schemas.services.graph_core import GraphScope

    memory_service = getattr(request.app.state, "memory_service", None)
    if not memory_service:
        logger.debug("Memory service not available for dream schedule query")
        return []

    try:
        # Query for scheduled_dream tasks in the graph
        query = GraphQuery(
            scope=GraphScope.LOCAL,
            node_types=["task"],
            metadata_filter={"task_type": "scheduled_dream"},
        )

        results = await memory_service.query(query)
        dream_tasks: List[ScheduledTaskInfo] = []

        now = datetime.now(timezone.utc)

        for node in results.nodes:
            # Extract scheduled time from metadata
            metadata = node.metadata or {}
            scheduled_for = metadata.get("scheduled_for")

            # Determine status based on scheduled time
            status = "PENDING"
            if scheduled_for:
                try:
                    scheduled_dt = datetime.fromisoformat(scheduled_for.replace("Z", "+00:00"))
                    if scheduled_dt <= now:
                        status = "ACTIVE"  # Due or past due
                except (ValueError, AttributeError):
                    pass

            dream_tasks.append(
                ScheduledTaskInfo(
                    task_id=node.id,
                    name="Dream Session",
                    goal_description="Scheduled introspection and memory consolidation",
                    status=status,
                    defer_until=scheduled_for,
                    schedule_cron=None,  # Dream sessions are one-time, then rescheduled
                    created_at=(
                        node.created_at.isoformat()
                        if hasattr(node, "created_at") and node.created_at
                        else scheduled_for or now.isoformat()
                    ),
                    last_triggered_at=None,
                    deferral_count=0,
                )
            )

        logger.debug(f"Found {len(dream_tasks)} dream schedules in graph")
        return dream_tasks

    except Exception as e:
        logger.warning(f"Failed to query dream schedules from graph: {e}")
        return []


# Endpoints


@router.get("/tasks", response_model=None, responses=RESPONSES_500_503)
async def list_scheduled_tasks(
    request: Request,
    auth: AuthObserverDep,
    status: Annotated[
        Optional[str], Query(description="Filter by status: PENDING, ACTIVE, COMPLETE, FAILED, CANCELLED")
    ] = None,
    limit: Annotated[int, Query(ge=1, le=200, description="Maximum tasks to return")] = 50,
) -> SuccessResponse[ScheduledTasksListResponse]:
    """
    List all scheduled tasks.

    Returns information about scheduled tasks including their status,
    schedule (one-time or recurring), and execution history.
    Also includes dream schedules from the graph memory.
    """
    task_scheduler = _get_task_scheduler(request)

    try:
        # Get all scheduled tasks from TaskSchedulerService
        tasks: List[ScheduledTaskInfo] = await task_scheduler.get_scheduled_tasks()

        # Also get dream schedules from graph memory
        dream_tasks = await _get_dream_schedules_from_graph(request)

        # Merge task lists (dream tasks won't have duplicates since they have different IDs)
        all_tasks = tasks + dream_tasks

        # Apply status filter if provided
        if status:
            all_tasks = [t for t in all_tasks if t.status.upper() == status.upper()]

        # Sort by defer_until (soonest first), with None values at end
        all_tasks.sort(key=lambda t: t.defer_until or "9999-12-31")

        # Apply limit
        all_tasks = all_tasks[:limit]

        # Convert to response format
        task_responses = [_convert_to_response(t) for t in all_tasks]

        # Calculate stats
        active_count = sum(1 for t in task_responses if t.status in ("PENDING", "ACTIVE"))
        recurring_count = sum(1 for t in task_responses if t.is_recurring)

        response = ScheduledTasksListResponse(
            tasks=task_responses, total=len(task_responses), active_count=active_count, recurring_count=recurring_count
        )

        return SuccessResponse(
            data=response,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list scheduled tasks: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats", response_model=None, responses=RESPONSES_500_503)
async def get_scheduler_stats(
    request: Request,
    auth: AuthObserverDep,
) -> SuccessResponse[SchedulerStatsResponse]:
    """
    Get scheduler statistics.

    Returns metrics about the task scheduler including total tasks,
    completion rates, and service uptime.
    """
    task_scheduler = _get_task_scheduler(request)

    try:
        # Get metrics from scheduler
        metrics = await task_scheduler.get_metrics()

        response = SchedulerStatsResponse(
            tasks_scheduled_total=int(metrics.get("tasks_scheduled_total", 0)),
            tasks_completed_total=int(metrics.get("tasks_completed_total", 0)),
            tasks_failed_total=int(metrics.get("tasks_failed_total", 0)),
            tasks_pending=int(metrics.get("tasks_pending", 0)),
            recurring_tasks=int(metrics.get("recurring_tasks", 0)),
            oneshot_tasks=int(metrics.get("oneshot_tasks", 0)),
            scheduler_uptime_seconds=float(metrics.get("scheduler_uptime_seconds", 0)),
        )

        return SuccessResponse(
            data=response,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get scheduler stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/tasks", response_model=None, responses={**RESPONSES_400, **RESPONSES_500_503})
async def create_scheduled_task(
    request: Request,
    task_request: CreateScheduledTaskRequest,
    auth: AuthAdminDep,
) -> SuccessResponse[ScheduledTaskResponse]:
    """
    Create a new scheduled task.

    Requires ADMIN role. Tasks can be scheduled as one-time (using defer_until)
    or recurring (using schedule_cron with cron expression format).

    Cron format: minute hour day-of-month month day-of-week
    Examples:
    - "0 9 * * *" - Daily at 9:00 AM
    - "0 9 * * 1" - Every Monday at 9:00 AM
    - "0 */2 * * *" - Every 2 hours
    """
    task_scheduler = _get_task_scheduler(request)

    # Validate: must have either defer_until or schedule_cron, not both
    if task_request.defer_until and task_request.schedule_cron:
        raise HTTPException(
            status_code=400, detail="Cannot specify both defer_until and schedule_cron. Use one or the other."
        )

    if not task_request.defer_until and not task_request.schedule_cron:
        raise HTTPException(
            status_code=400, detail="Must specify either defer_until (for one-time) or schedule_cron (for recurring)."
        )

    try:
        # Create the task
        # origin_thought_id is set to a placeholder since this is API-created
        scheduled_task = await task_scheduler.schedule_task(
            name=task_request.name,
            goal_description=task_request.goal_description,
            trigger_prompt=task_request.trigger_prompt,
            origin_thought_id=f"api_created_{uuid.uuid4().hex[:8]}",
            defer_until=task_request.defer_until,
            schedule_cron=task_request.schedule_cron,
        )

        # Convert to response format
        response = ScheduledTaskResponse(
            task_id=scheduled_task.task_id,
            name=scheduled_task.name,
            goal_description=scheduled_task.goal_description,
            status=scheduled_task.status,
            defer_until=scheduled_task.defer_until.isoformat() if scheduled_task.defer_until else None,
            schedule_cron=scheduled_task.schedule_cron,
            created_at=(
                scheduled_task.created_at.isoformat()
                if isinstance(scheduled_task.created_at, datetime)
                else scheduled_task.created_at
            ),
            last_triggered_at=(
                scheduled_task.last_triggered_at.isoformat() if scheduled_task.last_triggered_at else None
            ),
            deferral_count=scheduled_task.deferral_count,
            is_recurring=scheduled_task.schedule_cron is not None,
        )

        logger.info(f"Created scheduled task: {scheduled_task.task_id} - {scheduled_task.name}")

        return SuccessResponse(
            data=response,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )

    except ValueError as e:
        # Invalid cron expression or other validation error
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create scheduled task: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/tasks/{task_id}", response_model=None, responses={**RESPONSES_400, **RESPONSES_500_503})
async def cancel_scheduled_task(
    request: Request,
    task_id: str,
    auth: AuthAdminDep,
) -> SuccessResponse[CancelTaskResponse]:
    """
    Cancel a scheduled task.

    Requires ADMIN role. Cancels the specified task, preventing future executions.
    For recurring tasks, this stops all future executions.
    """
    task_scheduler = _get_task_scheduler(request)

    try:
        success = await task_scheduler.cancel_task(task_id)

        if not success:
            raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")

        logger.info(f"Cancelled scheduled task: {task_id}")

        response = CancelTaskResponse(success=True, task_id=task_id, message=f"Task {task_id} has been cancelled")

        return SuccessResponse(
            data=response,
            metadata=ResponseMetadata(
                timestamp=datetime.now(timezone.utc), request_id=str(uuid.uuid4()), duration_ms=0
            ),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to cancel task {task_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
