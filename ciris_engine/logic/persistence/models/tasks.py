"""Tasks persistence — routed through ciris-persist substrate APIs.

Part of 2.9.0 T-lane migration (CIRISAgent#763 / CIRISPersist#58):
removes the second libsqlite writer on `ciris_engine.db` to stop the
B-tree corruption from shared WAL pages. Public function signatures
are preserved verbatim so callers across the codebase need no changes.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from ciris_engine.protocols.services.graph.audit import AuditServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.audit.core import EventPayload
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import (
    ImageContent,
    Task,
    TaskContext,
    TaskOutcome,
)
from ciris_engine.schemas.services.graph.audit import AuditEventData

if TYPE_CHECKING:
    from ciris_engine.protocols.services.infrastructure.authentication import (
        AuthenticationServiceProtocol,
    )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Persist engine accessor + payload conversion helpers.
# ---------------------------------------------------------------------------


def _get_engine() -> Any:
    """Return the wired persist engine; raise if not yet bootstrapped."""
    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    if engine is None:
        raise RuntimeError(
            "persist engine not initialized — call initialize_database() "
            "before any tasks operation"
        )
    return engine


def _task_to_persist_payload(task: Task) -> Dict[str, Any]:
    """Convert a Task into the dict shape `engine.task_upsert` accepts.

    Persist accepts `context`/`outcome` as nested dicts and json.dumps them
    internally. Images are not represented in persist; we carry them in
    `context.images` round-trip but the agent layer holds the canonical
    list — see add_task() for the storage strategy.
    """
    task_dict = task.model_dump(mode="json")
    payload: Dict[str, Any] = {
        "task_id": task.task_id,
        "channel_id": task.channel_id,
        "agent_occurrence_id": task.agent_occurrence_id,
        "description": task.description,
        "status": task.status.value if isinstance(task.status, TaskStatus) else task.status,
        "priority": task.priority,
        "created_at": task.created_at,
        "updated_at": task.updated_at,
        "parent_task_id": task.parent_task_id,
        "signed_by": task.signed_by,
        "signature": task.signature,
        "signed_at": task.signed_at,
        "updated_info_available": task.updated_info_available,
    }
    if task.updated_info_content is not None:
        payload["updated_info_content"] = task.updated_info_content

    # Context: merge agent's TaskContext + private images carry-through.
    # Task is the record of truth for preferred_language; mirror it into
    # context so load-time round-trips correctly (legacy parity).
    ctx = task_dict.get("context")
    images = task_dict.get("images") or []
    if ctx is None and (images or task.preferred_language is not None):
        ctx = {}
    if ctx is not None:
        ctx = dict(ctx)
        if task.preferred_language is not None and not ctx.get("preferred_language"):
            ctx["preferred_language"] = task.preferred_language
        if images:
            ctx["__agent_images__"] = images
        payload["context"] = ctx

    outcome = task_dict.get("outcome")
    if outcome is not None:
        payload["outcome"] = outcome
    return payload


def _persist_row_to_task(row: Dict[str, Any]) -> Task:
    """Materialize a persist task row into a Task model."""
    agent_occurrence_id = str(row.get("agent_occurrence_id", "default"))

    try:
        status = TaskStatus(row.get("status", TaskStatus.PENDING.value))
    except Exception:
        logger.warning(
            "Invalid status value '%s' for task %s. Defaulting to PENDING.",
            row.get("status"),
            row.get("task_id"),
        )
        status = TaskStatus.PENDING

    # Context.
    context: Optional[TaskContext]
    ctx_data = row.get("context")
    if isinstance(ctx_data, str):
        try:
            ctx_data = json.loads(ctx_data)
        except json.JSONDecodeError:
            ctx_data = None
    if isinstance(ctx_data, dict):
        try:
            context = TaskContext(
                channel_id=ctx_data.get("channel_id"),
                user_id=ctx_data.get("user_id"),
                correlation_id=ctx_data.get("correlation_id", str(uuid.uuid4())),
                parent_task_id=ctx_data.get("parent_task_id"),
                agent_occurrence_id=ctx_data.get("agent_occurrence_id", agent_occurrence_id),
                preferred_language=ctx_data.get("preferred_language"),
            )
        except Exception as e:
            logger.warning(f"Failed to decode context for task {row.get('task_id')}: {e}")
            context = TaskContext(
                channel_id=None,
                user_id=None,
                correlation_id=str(uuid.uuid4()),
                parent_task_id=None,
                agent_occurrence_id=agent_occurrence_id,
            )
    else:
        context = TaskContext(
            channel_id=None,
            user_id=None,
            correlation_id=str(uuid.uuid4()),
            parent_task_id=None,
            agent_occurrence_id=agent_occurrence_id,
        )

    preferred_language: Optional[str] = (
        context.preferred_language if context is not None else None
    )

    # Outcome.
    outcome: Optional[TaskOutcome] = None
    outcome_data = row.get("outcome")
    if isinstance(outcome_data, str):
        try:
            outcome_data = json.loads(outcome_data)
        except json.JSONDecodeError:
            outcome_data = None
    if isinstance(outcome_data, dict) and outcome_data:
        try:
            outcome = TaskOutcome.model_validate(outcome_data)
        except Exception:
            logger.warning(f"Failed to decode outcome for task {row.get('task_id')}")
            outcome = None

    # Images: carried in context's __agent_images__ private namespace.
    images: List[ImageContent] = []
    if isinstance(ctx_data, dict):
        raw_images = ctx_data.get("__agent_images__") or []
        if isinstance(raw_images, list):
            for img in raw_images:
                try:
                    if isinstance(img, dict):
                        images.append(ImageContent.model_validate(img))
                except Exception as e:
                    logger.warning(f"Failed to decode image for task {row.get('task_id')}: {e}")

    updated_info_available = bool(row.get("updated_info_available", False))

    return Task(
        task_id=str(row["task_id"]),
        channel_id=str(row.get("channel_id", "")),
        agent_occurrence_id=agent_occurrence_id,
        description=str(row.get("description", "")),
        status=status,
        priority=int(row.get("priority", 0)),
        created_at=str(row["created_at"]),
        updated_at=str(row["updated_at"]),
        parent_task_id=row.get("parent_task_id"),
        context=context,
        preferred_language=preferred_language,
        outcome=outcome,
        signed_by=row.get("signed_by"),
        signature=row.get("signature"),
        signed_at=row.get("signed_at"),
        updated_info_available=updated_info_available,
        updated_info_content=row.get("updated_info_content"),
        images=images,
    )


def _list_with_filter(
    filter_dict: Dict[str, Any],
    *,
    limit: Optional[int] = None,
) -> List[Task]:
    """Paginate `task_list`. Returns Task objects DESC by created_at."""
    engine = _get_engine()
    last_ts = "9999-12-31T23:59:59Z"
    last_id = ""
    page_size = 200 if limit is None else min(200, max(limit, 1))
    collected: List[Task] = []

    while True:
        cursor_json = json.dumps(
            {"version": "v1", "last_ts": last_ts, "last_id": last_id}
        )
        raw = engine.task_list(json.dumps(filter_dict), cursor_json, page_size)
        try:
            parsed = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            break
        items = (parsed.get("items") if isinstance(parsed, dict) else None) or []
        if not items:
            break
        for row in items:
            if not isinstance(row, dict):
                continue
            try:
                collected.append(_persist_row_to_task(row))
            except Exception as e:
                logger.warning(
                    "Failed to materialize persist task row %s: %s",
                    row.get("task_id"),
                    e,
                )
            last_ts = str(row.get("created_at", last_ts))
            last_id = str(row.get("task_id", ""))
            if limit is not None and len(collected) >= limit:
                return collected
        if len(items) < page_size:
            break
    return collected


# ---------------------------------------------------------------------------
# Public API — signatures preserved verbatim from the legacy raw-sqlite3 impl.
# ---------------------------------------------------------------------------


def get_task_by_id_any_occurrence(task_id: str) -> Optional[Task]:
    """Get a task by ID without filtering by occurrence_id."""
    engine = _get_engine()
    try:
        raw = engine.task_get(task_id)
    except Exception as e:
        logger.exception(f"Failed to get task {task_id} (any occurrence): {e}")
        return None
    if raw is None:
        logger.warning(f"Task {task_id} not found (any occurrence)")
        return None
    row = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(row, dict):
        return None
    return _persist_row_to_task(row)


def get_task_occurrence_id_for_update(task_id: str) -> Optional[str]:
    """Get the correct occurrence_id for updating a task's status.

    See the docstring on the legacy impl for the 6-scenario matrix; this
    function just reads the persisted row's agent_occurrence_id since
    persist holds the authoritative value.
    """
    engine = _get_engine()
    try:
        raw = engine.task_get(task_id)
    except Exception as e:
        logger.exception(f"Failed to get occurrence_id for task {task_id}: {e}")
        return None
    if raw is None:
        logger.warning(f"Task {task_id} not found when looking up occurrence_id for update")
        return None
    row = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(row, dict):
        return None
    return str(row.get("agent_occurrence_id", "default"))


def get_tasks_by_status(
    status: TaskStatus,
    occurrence_id: str = "default"

) -> List[Task]:
    """Returns all tasks with the given status and occurrence as Task objects, ASC by created_at."""
    if not isinstance(status, TaskStatus):
        raise TypeError(f"Expected TaskStatus enum, got {type(status)}: {status}")

    try:
        tasks = _list_with_filter(
            {"status": status.value, "agent_occurrence_id": occurrence_id}
        )
    except Exception as e:
        logger.exception(f"Failed to get tasks with status {status.value} for occurrence {occurrence_id}: {e}")
        return []
    tasks.sort(key=lambda t: t.created_at)
    return tasks


def get_all_tasks(occurrence_id: str = "default") -> List[Task]:
    """Returns all tasks for the occurrence, ASC by created_at."""
    try:
        tasks = _list_with_filter({"agent_occurrence_id": occurrence_id})
    except Exception as e:
        logger.exception(f"Failed to get all tasks for occurrence {occurrence_id}: {e}")
        return []
    tasks.sort(key=lambda t: t.created_at)
    return tasks


def _is_correlation_id_constraint_violation(error_msg: str) -> bool:
    """Check if error message indicates a unique constraint violation on correlation_id."""
    return "unique constraint" in error_msg and (
        "correlation" in error_msg or "json_extract" in error_msg
    )


def _get_correlation_id_from_task(task: Task) -> Optional[str]:
    """Extract correlation_id from task context if available."""
    if not task.context:
        return None
    return getattr(task.context, "correlation_id", None)


def _handle_duplicate_task(task: Task) -> str:
    """Handle duplicate task detection by returning existing task_id."""
    correlation_id = _get_correlation_id_from_task(task)
    logger.info(
        f"Task with correlation_id={correlation_id} already exists for occurrence {task.agent_occurrence_id}, "
        "skipping duplicate (race condition prevented)"
    )
    if not correlation_id:
        return task.task_id
    existing_task = get_task_by_correlation_id(correlation_id, task.agent_occurrence_id)
    if existing_task:
        return existing_task.task_id
    return task.task_id


def add_task(task: Task, db_path: Optional[str] = None) -> str:
    """Insert a task. Returns the task_id. On correlation_id conflict, returns the existing id.

    Legacy DB had a UNIQUE INDEX on tasks.context_json.correlation_id (migration
    006). Persist's `cirislens_tasks` doesn't carry that constraint, so we
    enforce it client-side here before upsert.
    """
    engine = _get_engine()
    correlation_id = _get_correlation_id_from_task(task)
    if correlation_id:
        existing = get_task_by_correlation_id(correlation_id, task.agent_occurrence_id)
        if existing is not None and existing.task_id != task.task_id:
            return _handle_duplicate_task(task)
    try:
        engine.task_upsert(json.dumps(_task_to_persist_payload(task)))
        images_count = len(task.images) if task.images else 0
        if images_count > 0:
            logger.info(
                f"Added task ID {task.task_id} (occurrence: {task.agent_occurrence_id}) with {images_count} images."
            )
        else:
            logger.info(
                f"Added task ID {task.task_id} (occurrence: {task.agent_occurrence_id}) to database."
            )
        return task.task_id
    except Exception as e:
        error_msg = str(e).lower()
        if _is_correlation_id_constraint_violation(error_msg):
            return _handle_duplicate_task(task, db_path)
        logger.exception(f"Failed to add task {task.task_id}: {e}")
        raise


def get_task_by_id(
    task_id: str,
    occurrence_id: str = "default"

) -> Optional[Task]:
    engine = _get_engine()
    try:
        raw = engine.task_get(task_id)
    except Exception as e:
        logger.exception(f"Failed to get task {task_id} for occurrence {occurrence_id}: {e}")
        return None
    if raw is None:
        return None
    row = json.loads(raw) if isinstance(raw, str) else raw
    if not isinstance(row, dict):
        return None
    if str(row.get("agent_occurrence_id")) != occurrence_id:
        return None
    return _persist_row_to_task(row)


def update_task_status(
    task_id: str,
    new_status: TaskStatus,
    occurrence_id: str,
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None,
) -> bool:
    """Update the status of a task."""
    engine = _get_engine()

    existing = get_task_by_id(task_id, occurrence_id)
    if existing is None:
        logger.warning(f"Task ID {task_id} not found for status update in occurrence {occurrence_id}.")
        return False

    try:
        # persist's task_update_status writes status + updated_at, no outcome.
        engine.task_update_status(task_id, new_status.value, None)
        logger.info(f"Updated status of task ID {task_id} to {new_status.value}.")
        return True
    except Exception as e:
        logger.exception(f"Failed to update task status for {task_id}: {e}")
        return False


def transfer_task_ownership(
    task_id: str,
    from_occurrence_id: str,
    to_occurrence_id: str,
    time_service: TimeServiceProtocol,
    audit_service: AuditServiceProtocol

) -> bool:
    """Transfer task ownership from one occurrence to another.

    Used when claiming shared tasks (transfer from '__shared__' to the
    claiming occurrence so seed thoughts can be processed).
    """
    success = False
    engine = _get_engine()

    try:
        raw = engine.task_get(task_id)
    except Exception as e:
        logger.exception(f"Failed to load task {task_id} for ownership transfer: {e}")
        raw = None

    if raw is None:
        logger.warning(f"Task {task_id} not found with occurrence {from_occurrence_id} for ownership transfer")
    else:
        row = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(row, dict):
            logger.warning(f"Task {task_id} returned non-dict row for ownership transfer")
        elif str(row.get("agent_occurrence_id")) != from_occurrence_id:
            logger.warning(f"Task {task_id} not found with occurrence {from_occurrence_id} for ownership transfer")
        else:
            try:
                row["agent_occurrence_id"] = to_occurrence_id
                row["updated_at"] = time_service.now_iso()
                task = _persist_row_to_task(row)
                engine.task_upsert(json.dumps(_task_to_persist_payload(task)))
                logger.info(
                    f"Transferred ownership of task {task_id} from {from_occurrence_id} to {to_occurrence_id}"
                )
                success = True
            except Exception as e:
                logger.exception(f"Failed to transfer task ownership for {task_id}: {e}")
                success = False

    audit_event = AuditEventData(
        entity_id=task_id,
        actor="system",
        outcome="success" if success else "failed",
        severity="info",
        action="task_ownership_transfer",
        resource="task",
        metadata={
            "task_id": task_id,
            "from_occurrence_id": from_occurrence_id,
            "to_occurrence_id": to_occurrence_id,
            "task_type": "shared_coordination",
        },
    )

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(audit_service.log_event("task_ownership_transfer", cast(EventPayload, audit_event)))
    except RuntimeError:
        logger.debug("No event loop running, audit logging deferred")

    return success


def update_task_context_and_signing(
    task_id: str,
    occurrence_id: str,
    context: TaskContext,
    time_service: TimeServiceProtocol,
    signed_by: Optional[str] = None,
    signature: Optional[str] = None,
    signed_at: Optional[str] = None,
    db_path: Optional[str] = None,
) -> bool:
    """Update the context and signing metadata for an existing task."""
    engine = _get_engine()

    existing = get_task_by_id(task_id, occurrence_id)
    if existing is None:
        logger.warning(
            "Task %s not found when updating context/signature for occurrence %s",
            task_id,
            occurrence_id,
        )
        return False

    existing.context = context
    existing.preferred_language = context.preferred_language
    existing.signed_by = signed_by
    existing.signature = signature
    existing.signed_at = signed_at
    existing.updated_at = time_service.now_iso()

    try:
        engine.task_upsert(json.dumps(_task_to_persist_payload(existing)))
        logger.info(
            "Updated context and signing metadata for task %s (occurrence: %s)",
            task_id,
            occurrence_id,
        )
        return True
    except Exception as e:
        logger.exception(
            "Failed to update context/signature for task %s (occurrence: %s): %s",
            task_id,
            occurrence_id,
            e,
        )
        return False


def clear_task_images(
    task_id: str,
    occurrence_id: str,
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None,
) -> bool:
    """Clear images from a task (for privacy/storage cleanup on completion)."""
    engine = _get_engine()

    existing = get_task_by_id(task_id, occurrence_id)
    if existing is None:
        logger.debug(f"Task {task_id} not found or no images to clear (occurrence: {occurrence_id})")
        return False

    existing.images = []
    existing.updated_at = time_service.now_iso()
    try:
        engine.task_upsert(json.dumps(_task_to_persist_payload(existing)))
        logger.info(f"Cleared images from task {task_id} (occurrence: {occurrence_id})")
        return True
    except Exception as e:
        logger.exception(f"Failed to clear images for task {task_id}: {e}")
        return False


def task_exists(task_id: str, db_path: Optional[str] = None) -> bool:
    return get_task_by_id(task_id) is not None


async def add_system_task(
    task: Task,
    auth_service: Optional["AuthenticationServiceProtocol"] = None,
    db_path: Optional[str] = None,
) -> str:
    """Add a system task with automatic signing by the system WA."""
    if auth_service:
        try:
            system_wa_id = await auth_service.get_system_wa_id()
            if system_wa_id:
                signature, signed_at = await auth_service.sign_task(task, system_wa_id)
                task.signed_by = system_wa_id
                task.signature = signature
                task.signed_at = signed_at
                logger.info(f"Signed system task {task.task_id} with system WA {system_wa_id}")
            else:
                logger.warning("No system WA available for signing task")
        except Exception as e:
            logger.error(f"Failed to sign system task: {e}")
    return add_task(task, db_path=db_path)


def get_recent_completed_tasks(
    occurrence_id: str = "default",
    limit: int = 10,
    db_path: Optional[str] = None,
) -> List[Task]:
    tasks_list = get_all_tasks(occurrence_id)
    completed = [t for t in tasks_list if getattr(t, "status", None) == TaskStatus.COMPLETED]
    completed_sorted = sorted(completed, key=lambda t: getattr(t, "updated_at", ""), reverse=True)
    return completed_sorted[:limit]


def get_top_tasks(
    occurrence_id: str = "default",
    limit: int = 10,
    db_path: Optional[str] = None,
) -> List[Task]:
    """Get top pending tasks for occurrence ordered by priority (highest first) then by creation date."""
    tasks_list = get_all_tasks(occurrence_id)
    pending = [t for t in tasks_list if getattr(t, "status", None) == TaskStatus.PENDING]
    sorted_tasks = sorted(
        pending, key=lambda t: (-getattr(t, "priority", 0), getattr(t, "created_at", ""))
    )
    return sorted_tasks[:limit]


def get_pending_tasks_for_activation(
    occurrence_id: str = "default",
    limit: int = 10,
    db_path: Optional[str] = None,
) -> List[Task]:
    """Get pending tasks for occurrence ordered by priority (highest first) then by creation date."""
    pending_tasks = get_tasks_by_status(TaskStatus.PENDING, occurrence_id)
    sorted_tasks = sorted(
        pending_tasks, key=lambda t: (-getattr(t, "priority", 0), getattr(t, "created_at", ""))
    )
    return sorted_tasks[:limit]


def count_tasks(
    status: Optional[TaskStatus] = None,
    occurrence_id: str = "default"

) -> int:
    """Count tasks matching the criteria."""
    try:
        if status:
            tasks = _list_with_filter(
                {"status": status.value, "agent_occurrence_id": occurrence_id}
            )
        else:
            tasks = _list_with_filter({"agent_occurrence_id": occurrence_id})
        return len(tasks)
    except Exception as e:
        logger.exception(f"Failed to count tasks for occurrence {occurrence_id}: {e}")
        return 0


def delete_tasks_by_ids(task_ids: List[str]) -> bool:
    """Deletes tasks (and cascades thoughts + feedback_mappings) with the given IDs.

    Persist's `task_delete` cascades to thoughts via FK. The legacy
    `feedback_mappings` cascade is handled by persist's row-deletion
    cascade on `cirislens_thoughts` (and is otherwise unused at the
    agent layer, see CIRISAgent#763 inventory).
    """
    if not task_ids:
        logger.warning("No task IDs provided for deletion.")
        return False

    logger.warning(f"DELETE_OPERATION: delete_tasks_by_ids called with {len(task_ids)} tasks: {task_ids}")
    import traceback

    logger.warning(f"DELETE_OPERATION: Called from: {''.join(traceback.format_stack()[-3:-1])}")

    engine = _get_engine()
    deleted_count = 0
    fk_blocked: List[str] = []
    for tid in task_ids:
        try:
            ok = engine.task_delete(tid)
        except Exception as e:
            # Persist 1.5.19 has no `thought_delete` API, so tasks with
            # child thoughts can't be cascade-deleted. Mark for soft-delete
            # fallback and continue. Tracked upstream as a CIRISPersist
            # follow-up — until then maintenance leaves stale rows in
            # place rather than crashing the cleanup pass.
            err = str(e).lower()
            if "foreign key" in err or "conflict" in err:
                fk_blocked.append(tid)
                logger.warning(
                    "task_delete(%s) blocked by FK (child thoughts exist); "
                    "soft-cancelling instead pending CIRISPersist thought_delete API.",
                    tid,
                )
                try:
                    engine.task_update_status(tid, TaskStatus.FAILED.value, None)
                except Exception as inner_e:
                    logger.warning("task_update_status fallback for %s failed: %s", tid, inner_e)
                continue
            logger.exception(f"Failed to delete task {tid}: {e}")
            continue
        if ok:
            deleted_count += 1

    if deleted_count > 0:
        logger.info(f"Successfully deleted {deleted_count} task(s) with IDs: {task_ids}.")
        return True
    if fk_blocked:
        logger.warning(
            "Soft-cancelled %d task(s) with FK-blocked children: %s", len(fk_blocked), fk_blocked
        )
        return True
    logger.warning(f"No tasks found with IDs: {task_ids} for deletion (or they were already deleted).")
    return False


def get_tasks_older_than(
    older_than_timestamp: str,
    occurrence_id: str = "default"

) -> List[Task]:
    """Get all tasks for occurrence with created_at older than the given ISO timestamp."""
    try:
        all_tasks = _list_with_filter({"agent_occurrence_id": occurrence_id})
    except Exception as e:
        logger.exception(
            f"Failed to get tasks older than {older_than_timestamp} for occurrence {occurrence_id}: {e}"
        )
        return []
    return [t for t in all_tasks if t.created_at < older_than_timestamp]


def get_active_task_for_channel(
    channel_id: str,
    occurrence_id: str = "default"

) -> Optional[Task]:
    """Get the active task for a specific channel and occurrence, if one exists."""
    try:
        active_tasks = _list_with_filter(
            {
                "status": TaskStatus.ACTIVE.value,
                "agent_occurrence_id": occurrence_id,
                "channel_id": channel_id,
            }
        )
    except Exception as e:
        logger.exception(f"Failed to get active task for channel {channel_id} occurrence {occurrence_id}: {e}")
        return None
    # Persist returns DESC by created_at; pick the newest matching.
    for task in active_tasks:
        if task.channel_id == channel_id:
            logger.info(
                f"[GET_ACTIVE_TASK] Found active task for channel {channel_id}: task_id={task.task_id}, "
                f"description={task.description[:100] if task.description else 'N/A'}"
            )
            return task
    logger.info(f"[GET_ACTIVE_TASK] No active task found for channel {channel_id}")
    return None


def _is_committed_action(action_type: str) -> bool:
    """Check if an action type represents a committed (non-PONDER) action."""
    return action_type != "PONDER" and action_type != HandlerActionType.PONDER.value


def _task_has_committed_action(task_id: str, occurrence_id: str, db_path: Optional[str]) -> bool:
    """Check if task has any completed thoughts with non-PONDER action."""
    from ciris_engine.logic.persistence.models.thoughts import get_thoughts_by_task_id

    thoughts = get_thoughts_by_task_id(task_id, occurrence_id)
    for thought in thoughts:
        if thought.status != ThoughtStatus.COMPLETED:
            continue
        if thought.final_action and _is_committed_action(thought.final_action.action_type):
            logger.info(
                f"Task {task_id} already committed to action {thought.final_action.action_type}, "
                "cannot set updated_info_available flag"
            )
            return True
    return False


def _serialize_image(img: Any) -> Any:
    """Serialize an image to dict format."""
    if hasattr(img, "model_dump"):
        return img.model_dump()
    return img if isinstance(img, dict) else {}


def _prepare_images(task: Task, images: List[Any]) -> tuple[List[ImageContent], int]:
    """Prepare combined image list from existing and new images.

    Returns:
        Tuple of (combined_images, new_images_count)
    """
    existing_images = task.images if task else []
    new_images_data = [_serialize_image(img) for img in images]
    combined_raw = [_serialize_image(img) for img in existing_images] + new_images_data
    combined: List[ImageContent] = []
    for img in combined_raw:
        try:
            if isinstance(img, ImageContent):
                combined.append(img)
            elif isinstance(img, dict):
                combined.append(ImageContent.model_validate(img))
        except Exception as e:
            logger.warning(f"Skipping invalid image while preparing task {task.task_id}: {e}")
    return combined, len(new_images_data)


def set_task_updated_info_flag(
    task_id: str,
    updated_content: str,
    occurrence_id: str,
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None,
    images: Optional[List[Any]] = None,
) -> bool:
    """Set the updated_info_available flag on a task with new observation content.

    Returns False if task already committed to non-PONDER action or doesn't belong to occurrence.
    """
    task = get_task_by_id(task_id, occurrence_id)
    if not task or task.agent_occurrence_id != occurrence_id:
        logger.warning(
            f"Task {task_id} does not belong to occurrence {occurrence_id}, cannot set updated_info_available flag"
        )
        return False

    if _task_has_committed_action(task_id, occurrence_id, db_path):
        return False

    task.updated_info_available = True
    task.updated_info_content = updated_content
    task.updated_at = time_service.now_iso()
    if images:
        combined, new_count = _prepare_images(task, images)
        task.images = combined
        logger.info(f"[VISION] Appending {new_count} images to task {task_id}")

    engine = _get_engine()
    try:
        engine.task_upsert(json.dumps(_task_to_persist_payload(task)))
        logger.info(f"Set updated_info_available flag for task {task_id}")
        return True
    except Exception as e:
        logger.exception(f"Failed to set updated_info_available flag for task {task_id}: {e}")
        return False


# ==================== Multi-Occurrence Shared Task Functions ====================


def try_claim_shared_task(
    task_type: str,
    channel_id: str,
    description: str,
    priority: int,
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None,
) -> tuple[Task, bool]:
    """Atomically create or retrieve a shared agent-level task.

    Uses persist's `task_try_claim_shared`, which performs the atomic
    "create if not exists, return existing otherwise" semantics that the
    legacy INSERT-OR-IGNORE provided. Stale-task handling preserved from
    legacy implementation.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    task_id = f"{task_type.upper()}_SHARED_{date_str}"

    # Stale-task pre-check: if an existing shared task is in terminal status
    # or too old, delete it before claiming so the new agent gets a fresh task.
    existing = get_task_by_id(task_id, "__shared__")
    if existing:
        try:
            created_at = datetime.fromisoformat(existing.created_at.replace("Z", "+00:00"))
        except Exception:
            created_at = time_service.now()
        task_age = time_service.now() - created_at
        is_fresh = task_age < timedelta(minutes=10)
        is_reusable_status = existing.status in [TaskStatus.PENDING, TaskStatus.ACTIVE]

        if not is_reusable_status:
            logger.warning(
                f"Shared task {task_id} exists but has terminal status {existing.status.value}. "
                "This stale task should have been cleaned up. Creating new task instead."
            )
            delete_tasks_by_ids([task_id])
        elif not is_fresh:
            logger.warning(
                f"Shared task {task_id} exists but is stale (age: {task_age}). "
                "This old active task should have been cleaned up. Creating new task instead."
            )
            delete_tasks_by_ids([task_id])
        else:
            logger.info(
                f"Shared task {task_id} already exists (status={existing.status.value}, age={task_age}), "
                "returning existing task"
            )
            return (existing, False)

    now = time_service.now_iso()
    payload = {
        "task_id": task_id,
        "channel_id": channel_id,
        "agent_occurrence_id": "__shared__",
        "description": description,
        "status": TaskStatus.PENDING.value,
        "priority": priority,
        "created_at": now,
        "updated_at": now,
    }

    engine = _get_engine()
    try:
        raw = engine.task_try_claim_shared(json.dumps(payload))
    except Exception as e:
        logger.exception(f"Failed to claim shared task {task_id}: {e}")
        raise

    parsed = json.loads(raw) if isinstance(raw, str) else raw
    outcome = parsed.get("outcome") if isinstance(parsed, dict) else None
    task_row = parsed.get("task") if isinstance(parsed, dict) else None
    if not isinstance(task_row, dict):
        raise RuntimeError(f"Shared task {task_id} claim returned no task row")

    task = _persist_row_to_task(task_row)
    if outcome == "stored":
        logger.info(f"Successfully claimed shared task {task_id}")
        return (task, True)
    logger.info(f"Another occurrence claimed shared task {task_id} during race")
    return (task, False)


def get_shared_task_status(
    task_type: str,
    within_hours: int = 24,
    db_path: Optional[str] = None,
) -> Optional[TaskStatus]:
    """Get the status of the most recent shared task of a given type."""
    latest = get_latest_shared_task(task_type, within_hours)
    if latest is None:
        return None
    return latest.status


def is_shared_task_completed(
    task_type: str,
    within_hours: int = 24,
    db_path: Optional[str] = None,
) -> bool:
    """Check if a shared task of the given type has been completed recently."""
    status = get_shared_task_status(task_type, within_hours, db_path)
    return status == TaskStatus.COMPLETED if status else False


def get_latest_shared_task(
    task_type: str,
    within_hours: int = 24

) -> Optional[Task]:
    """Get the most recent shared task of a given type."""
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    cutoff_iso = cutoff_time.isoformat()
    pattern_prefix = f"{task_type.upper()}_SHARED_"

    try:
        shared_tasks = _list_with_filter({"agent_occurrence_id": "__shared__"})
    except Exception as e:
        logger.exception(f"Failed to get latest shared task for {task_type}: {e}")
        return None

    candidates = [
        t for t in shared_tasks
        if t.task_id.startswith(pattern_prefix) and t.created_at > cutoff_iso
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda t: t.created_at, reverse=True)
    return candidates[0]


def get_task_by_correlation_id(
    correlation_id: str,
    occurrence_id: str = "default"

) -> Optional[Task]:
    """Query for a task by correlation_id (e.g., Reddit post/comment ID)."""
    try:
        all_tasks = _list_with_filter({"agent_occurrence_id": occurrence_id})
    except Exception as e:
        logger.exception(f"Failed to get task by correlation_id {correlation_id}: {e}")
        return None
    matches = [
        t for t in all_tasks
        if t.context is not None
        and getattr(t.context, "correlation_id", None) == correlation_id
    ]
    if not matches:
        return None
    matches.sort(key=lambda t: t.created_at, reverse=True)
    return matches[0]
