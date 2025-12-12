import json
import logging
from typing import TYPE_CHECKING, Any, List, Optional

from ciris_engine.logic.persistence.db import get_db_connection
from ciris_engine.logic.persistence.db.dialect import get_adapter
from ciris_engine.logic.persistence.utils import map_row_to_task
from ciris_engine.protocols.services.graph.audit import AuditServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext

if TYPE_CHECKING:
    from ciris_engine.protocols.services.infrastructure.authentication import AuthenticationServiceProtocol

logger = logging.getLogger(__name__)


def get_task_by_id_any_occurrence(task_id: str, db_path: Optional[str] = None) -> Optional[Task]:
    """
    Get a task by ID without filtering by occurrence_id.

    This is needed for task completion handlers that need to read the task's
    actual occurrence_id before updating it. Unlike get_task_by_id() which filters
    by occurrence_id, this function retrieves the task regardless of occurrence.

    Args:
        task_id: The task ID to look up
        db_path: Optional database path (defaults to main database)

    Returns:
        The Task object, or None if task not found

    Examples:
        >>> task = get_task_by_id_any_occurrence("SHUTDOWN_SHARED_20251031")
        >>> task.agent_occurrence_id
        '__shared__'
    """
    sql = "SELECT * FROM tasks WHERE task_id = ? LIMIT 1"
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (task_id,))
            row = cursor.fetchone()
            if row:
                return map_row_to_task(row)
            logger.warning(f"Task {task_id} not found (any occurrence)")
            return None
    except Exception as e:
        logger.exception(f"Failed to get task {task_id} (any occurrence): {e}")
        return None


def get_task_occurrence_id_for_update(task_id: str, db_path: Optional[str] = None) -> Optional[str]:
    """
    Get the correct occurrence_id for updating a task's status.

    This handles 6 scenarios robustly:
    1. SQLite single agent (default) - returns "default"
    2. SQLite multi-occurrence claiming agent - returns actual occurrence_id
    3. SQLite multi-occurrence non-claimant - returns "__shared__"
    4. PostgreSQL single agent (default) - returns "default"
    5. PostgreSQL multi-occurrence claiming agent - returns actual occurrence_id
    6. PostgreSQL multi-occurrence non-claimant - returns "__shared__"

    Args:
        task_id: The task ID to look up
        db_path: Optional database path (defaults to main database)

    Returns:
        The occurrence_id to use for UPDATE queries, or None if task not found

    Examples:
        >>> get_task_occurrence_id_for_update("SHUTDOWN_SHARED_20251031")
        '__shared__'
        >>> get_task_occurrence_id_for_update("regular-task-123")
        'default'
    """
    sql = "SELECT agent_occurrence_id FROM tasks WHERE task_id = ? LIMIT 1"
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (task_id,))
            row = cursor.fetchone()
            if row:
                return str(row[0])
            logger.warning(f"Task {task_id} not found when looking up occurrence_id for update")
            return None
    except Exception as e:
        logger.exception(f"Failed to get occurrence_id for task {task_id}: {e}")
        return None


def get_tasks_by_status(
    status: TaskStatus, occurrence_id: str = "default", db_path: Optional[str] = None
) -> List[Task]:
    """Returns all tasks with the given status and occurrence from the tasks table as Task objects."""
    if not isinstance(status, TaskStatus):
        raise TypeError(f"Expected TaskStatus enum, got {type(status)}: {status}")
    status_val = status.value
    sql = "SELECT * FROM tasks WHERE status = ? AND agent_occurrence_id = ? ORDER BY created_at ASC"
    tasks_list: List[Any] = []
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (status_val, occurrence_id))
            rows = cursor.fetchall()
            for row in rows:
                tasks_list.append(map_row_to_task(row))
    except Exception as e:
        logger.exception(f"Failed to get tasks with status {status_val} for occurrence {occurrence_id}: {e}")
    return tasks_list


def get_all_tasks(occurrence_id: str = "default", db_path: Optional[str] = None) -> List[Task]:
    sql = "SELECT * FROM tasks WHERE agent_occurrence_id = ? ORDER BY created_at ASC"
    tasks_list: List[Any] = []
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (occurrence_id,))
            rows = cursor.fetchall()
            for row in rows:
                tasks_list.append(map_row_to_task(row))
    except Exception as e:
        logger.exception(f"Failed to get all tasks for occurrence {occurrence_id}: {e}")
    return tasks_list


def _is_correlation_id_constraint_violation(error_msg: str) -> bool:
    """
    Check if error message indicates a unique constraint violation on correlation_id.

    Args:
        error_msg: Lowercase error message from database exception

    Returns:
        True if this is a correlation_id constraint violation
    """
    return "unique constraint" in error_msg and ("correlation" in error_msg or "json_extract" in error_msg)


def _get_correlation_id_from_task(task: Task) -> Optional[str]:
    """
    Extract correlation_id from task context if available.

    Args:
        task: Task object to extract correlation_id from

    Returns:
        correlation_id if present, None otherwise
    """
    if not task.context:
        return None
    return getattr(task.context, "correlation_id", None)


def _handle_duplicate_task(task: Task, db_path: Optional[str]) -> str:
    """
    Handle duplicate task detection by returning existing task_id.

    Args:
        task: Task that triggered duplicate constraint
        db_path: Optional database path

    Returns:
        Existing task_id if found, otherwise the attempted task_id
    """
    correlation_id = _get_correlation_id_from_task(task)
    logger.info(
        f"Task with correlation_id={correlation_id} already exists for occurrence {task.agent_occurrence_id}, "
        "skipping duplicate (race condition prevented)"
    )

    # Treat empty string as None
    if not correlation_id:
        return task.task_id

    existing_task = get_task_by_correlation_id(correlation_id, task.agent_occurrence_id, db_path)
    if existing_task:
        return existing_task.task_id

    return task.task_id


def add_task(task: Task, db_path: Optional[str] = None) -> str:
    task_dict = task.model_dump(mode="json")

    # Serialize images for storage
    images_data = task_dict.get("images", [])
    images_json = json.dumps(images_data) if images_data else None

    sql = """
        INSERT INTO tasks (task_id, channel_id, agent_occurrence_id, description, status, priority,
                           created_at, updated_at, parent_task_id, context_json, outcome_json,
                           signed_by, signature, signed_at, updated_info_available, updated_info_content,
                           images_json)
        VALUES (:task_id, :channel_id, :agent_occurrence_id, :description, :status, :priority,
                :created_at, :updated_at, :parent_task_id, :context, :outcome,
                :signed_by, :signature, :signed_at, :updated_info_available, :updated_info_content,
                :images)
    """
    params = {
        **task_dict,
        "status": task.status.value,
        "agent_occurrence_id": task.agent_occurrence_id,
        "context": json.dumps(task_dict.get("context")) if task_dict.get("context") is not None else None,
        "outcome": json.dumps(task_dict.get("outcome")) if task_dict.get("outcome") is not None else None,
        "signed_by": task_dict.get("signed_by"),
        "signature": task_dict.get("signature"),
        "signed_at": task_dict.get("signed_at"),
        "updated_info_available": 1 if task_dict.get("updated_info_available") else 0,
        "updated_info_content": task_dict.get("updated_info_content"),
        "images": images_json,
    }
    try:
        with get_db_connection(db_path) as conn:
            conn.execute(sql, params)
            conn.commit()
        image_count = len(images_data) if images_data else 0
        if image_count > 0:
            logger.info(
                f"Added task ID {task.task_id} (occurrence: {task.agent_occurrence_id}) with {image_count} images."
            )
        else:
            logger.info(f"Added task ID {task.task_id} (occurrence: {task.agent_occurrence_id}) to database.")
        return task.task_id
    except Exception as e:
        error_msg = str(e).lower()
        if _is_correlation_id_constraint_violation(error_msg):
            return _handle_duplicate_task(task, db_path)
        logger.exception(f"Failed to add task {task.task_id}: {e}")
        raise


def get_task_by_id(task_id: str, occurrence_id: str = "default", db_path: Optional[str] = None) -> Optional[Task]:
    sql = "SELECT * FROM tasks WHERE task_id = ? AND agent_occurrence_id = ?"
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (task_id, occurrence_id))
            row = cursor.fetchone()
            if row:
                return map_row_to_task(row)
            return None
    except Exception as e:
        logger.exception(f"Failed to get task {task_id} for occurrence {occurrence_id}: {e}")
        return None


def update_task_status(
    task_id: str,
    new_status: TaskStatus,
    occurrence_id: str,
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None,
) -> bool:
    sql = "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ? AND agent_occurrence_id = ?"
    params = (new_status.value, time_service.now_iso(), task_id, occurrence_id)
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Updated status of task ID {task_id} to {new_status.value}.")
                return True
            logger.warning(f"Task ID {task_id} not found for status update in occurrence {occurrence_id}.")
            return False
    except Exception as e:
        logger.exception(f"Failed to update task status for {task_id}: {e}")
        return False


def transfer_task_ownership(
    task_id: str,
    from_occurrence_id: str,
    to_occurrence_id: str,
    time_service: TimeServiceProtocol,
    audit_service: AuditServiceProtocol,
    db_path: Optional[str] = None,
) -> bool:
    """Transfer task ownership from one occurrence to another.

    This is used when claiming shared tasks to transfer ownership from '__shared__'
    to the claiming occurrence so seed thoughts can be processed.

    Args:
        task_id: The task ID to transfer
        from_occurrence_id: Current occurrence ID (typically '__shared__')
        to_occurrence_id: New occurrence ID (the claiming occurrence)
        time_service: Time service for timestamp
        audit_service: Audit service for logging ownership transfer events
        db_path: Optional database path

    Returns:
        True if transfer successful, False otherwise
    """
    sql = "UPDATE tasks SET agent_occurrence_id = ?, updated_at = ? WHERE task_id = ? AND agent_occurrence_id = ?"
    params = (to_occurrence_id, time_service.now_iso(), task_id, from_occurrence_id)

    success = False
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Transferred ownership of task {task_id} from {from_occurrence_id} to {to_occurrence_id}")
                success = True
            else:
                logger.warning(f"Task {task_id} not found with occurrence {from_occurrence_id} for ownership transfer")
    except Exception as e:
        logger.exception(f"Failed to transfer task ownership for {task_id}: {e}")
        success = False

    # Log audit event for ownership transfer (fire and forget)
    import asyncio
    from typing import cast

    from ciris_engine.schemas.audit.core import EventPayload
    from ciris_engine.schemas.services.graph.audit import AuditEventData

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
        # Try to get the running event loop
        loop = asyncio.get_running_loop()
        # Schedule the audit event as a task - cast to EventPayload for protocol compatibility
        loop.create_task(audit_service.log_event("task_ownership_transfer", cast(EventPayload, audit_event)))
    except RuntimeError:
        # No event loop running - this is expected in sync contexts like tests
        # The audit service will still track the call via the mock
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

    context_json = json.dumps(context.model_dump(mode="json"))
    sql = """
        UPDATE tasks
        SET context_json = ?,
            signed_by = ?,
            signature = ?,
            signed_at = ?,
            updated_at = ?
        WHERE task_id = ? AND agent_occurrence_id = ?
    """
    params = (
        context_json,
        signed_by,
        signature,
        signed_at,
        time_service.now_iso(),
        task_id,
        occurrence_id,
    )

    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(
                    "Updated context and signing metadata for task %s (occurrence: %s)",
                    task_id,
                    occurrence_id,
                )
                return True
            logger.warning(
                "Task %s not found when updating context/signature for occurrence %s",
                task_id,
                occurrence_id,
            )
            return False
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
    """Clear images from a task (for privacy/storage cleanup on completion).

    Args:
        task_id: The task ID to clear images from
        occurrence_id: The occurrence ID for the task
        time_service: Time service for timestamp
        db_path: Optional database path

    Returns:
        True if images were cleared, False otherwise
    """
    sql = "UPDATE tasks SET images_json = NULL, updated_at = ? WHERE task_id = ? AND agent_occurrence_id = ?"
    params = (time_service.now_iso(), task_id, occurrence_id)

    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Cleared images from task {task_id} (occurrence: {occurrence_id})")
                return True
            logger.debug(f"Task {task_id} not found or no images to clear (occurrence: {occurrence_id})")
            return False
    except Exception as e:
        logger.exception(f"Failed to clear images for task {task_id}: {e}")
        return False


def task_exists(task_id: str, db_path: Optional[str] = None) -> bool:
    return get_task_by_id(task_id, db_path=db_path) is not None


async def add_system_task(
    task: Task, auth_service: Optional["AuthenticationServiceProtocol"] = None, db_path: Optional[str] = None
) -> str:
    """Add a system task with automatic signing by the system WA.

    This should be used by authorized processors (wakeup, dream, shutdown) to create
    system tasks that are properly signed.

    Args:
        task: The task to add
        auth_service: Authentication service for signing (optional)
        db_path: Database path (optional)

    Returns:
        The task ID
    """
    # If auth service is available, sign the task
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
            # Continue without signature

    # Add the task (with or without signature)
    return add_task(task, db_path=db_path)


def get_recent_completed_tasks(
    occurrence_id: str = "default", limit: int = 10, db_path: Optional[str] = None
) -> List[Task]:
    tasks_list = get_all_tasks(occurrence_id, db_path=db_path)
    completed = [t for t in tasks_list if getattr(t, "status", None) == TaskStatus.COMPLETED]
    completed_sorted = sorted(completed, key=lambda t: getattr(t, "updated_at", ""), reverse=True)
    return completed_sorted[:limit]


def get_top_tasks(occurrence_id: str = "default", limit: int = 10, db_path: Optional[str] = None) -> List[Task]:
    """Get top pending tasks for occurrence ordered by priority (highest first) then by creation date."""
    tasks_list = get_all_tasks(occurrence_id, db_path=db_path)
    # Filter to PENDING tasks only - exclude COMPLETED, DEFERRED, FAILED, REJECTED
    pending = [t for t in tasks_list if getattr(t, "status", None) == TaskStatus.PENDING]
    sorted_tasks = sorted(pending, key=lambda t: (-getattr(t, "priority", 0), getattr(t, "created_at", "")))
    return sorted_tasks[:limit]


def get_pending_tasks_for_activation(
    occurrence_id: str = "default", limit: int = 10, db_path: Optional[str] = None
) -> List[Task]:
    """Get pending tasks for occurrence ordered by priority (highest first) then by creation date, with optional limit."""
    pending_tasks = get_tasks_by_status(TaskStatus.PENDING, occurrence_id, db_path=db_path)
    # Sort by priority (descending) then by created_at (ascending for oldest first)
    sorted_tasks = sorted(pending_tasks, key=lambda t: (-getattr(t, "priority", 0), getattr(t, "created_at", "")))
    return sorted_tasks[:limit]


def count_tasks(
    status: Optional[TaskStatus] = None, occurrence_id: str = "default", db_path: Optional[str] = None
) -> int:
    """
    Count tasks using SQL COUNT(*) for performance.

    This function uses a SQL COUNT(*) query instead of loading all tasks into memory,
    which prevents event loop blocking when counting large numbers of tasks.

    Args:
        status: Optional task status to filter by
        occurrence_id: Agent occurrence ID (default: "default")
        db_path: Optional database path

    Returns:
        Number of tasks matching the criteria
    """
    try:
        with get_db_connection(db_path) as conn:
            # Get adapter AFTER connection is established to ensure correct dialect
            # (get_db_connection calls init_dialect which sets the global adapter)
            adapter = get_adapter()
            cursor = conn.cursor()

            if status:
                sql = adapter.translate_placeholders(
                    "SELECT COUNT(*) FROM tasks WHERE agent_occurrence_id = ? AND status = ?"
                )
                cursor.execute(sql, (occurrence_id, status.value))
            else:
                sql = adapter.translate_placeholders("SELECT COUNT(*) FROM tasks WHERE agent_occurrence_id = ?")
                cursor.execute(sql, (occurrence_id,))

            result = cursor.fetchone()
            return adapter.extract_scalar(result) or 0
    except Exception as e:
        logger.exception(f"Failed to count tasks for occurrence {occurrence_id}: {e}")
        return 0


def delete_tasks_by_ids(task_ids: List[str], db_path: Optional[str] = None) -> bool:
    """Deletes tasks and their associated thoughts and feedback_mappings with the given IDs from the database."""
    if not task_ids:
        logger.warning("No task IDs provided for deletion.")
        return False

    logger.warning(f"DELETE_OPERATION: delete_tasks_by_ids called with {len(task_ids)} tasks: {task_ids}")
    import traceback

    logger.warning(f"DELETE_OPERATION: Called from: {''.join(traceback.format_stack()[-3:-1])}")

    placeholders = ",".join("?" for _ in task_ids)

    sql_get_thought_ids = f"SELECT thought_id FROM thoughts WHERE source_task_id IN ({placeholders})"  # nosec B608 - placeholders are '?' strings
    sql_delete_feedback_mappings = "DELETE FROM feedback_mappings WHERE target_thought_id IN ({})"
    sql_delete_thoughts = (
        f"DELETE FROM thoughts WHERE source_task_id IN ({placeholders})"  # nosec B608 - placeholders are '?' strings
    )
    sql_delete_tasks = (
        f"DELETE FROM tasks WHERE task_id IN ({placeholders})"  # nosec B608 - placeholders are '?' strings
    )

    deleted_count = 0
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(sql_get_thought_ids, task_ids)
            thought_rows = cursor.fetchall()
            thought_ids_to_delete = [row["thought_id"] for row in thought_rows]

            if thought_ids_to_delete:
                feedback_placeholders = ",".join("?" for _ in thought_ids_to_delete)
                current_sql_delete_feedback_mappings = sql_delete_feedback_mappings.format(
                    feedback_placeholders
                )  # nosec B608 - placeholders are '?' strings
                cursor.execute(current_sql_delete_feedback_mappings, thought_ids_to_delete)
                logger.info(
                    f"Deleted {cursor.rowcount} associated feedback mappings for thought IDs: {thought_ids_to_delete}."
                )
            else:
                logger.info(f"No associated feedback mappings found for task IDs: {task_ids}.")

            cursor.execute(sql_delete_thoughts, task_ids)
            thoughts_deleted = cursor.rowcount
            logger.warning(f"DELETE_OPERATION: Deleted {thoughts_deleted} thoughts for tasks: {task_ids}")
            logger.info(f"Deleted {thoughts_deleted} associated thoughts for task IDs: {task_ids}.")

            cursor.execute(sql_delete_tasks, task_ids)
            deleted_count = cursor.rowcount

            conn.commit()

            if deleted_count > 0:
                logger.info(f"Successfully deleted {deleted_count} task(s) with IDs: {task_ids}.")
                return True
            logger.warning(f"No tasks found with IDs: {task_ids} for deletion (or they were already deleted).")
            return False
    except Exception as e:
        logger.exception(f"Failed to delete tasks with IDs {task_ids}: {e}")
        return False


def get_tasks_older_than(
    older_than_timestamp: str, occurrence_id: str = "default", db_path: Optional[str] = None
) -> List[Task]:
    """Get all tasks for occurrence with created_at older than the given ISO timestamp, returning Task objects."""
    sql = "SELECT * FROM tasks WHERE created_at < ? AND agent_occurrence_id = ?"
    tasks_list: List[Any] = []
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (older_than_timestamp, occurrence_id))
            rows = cursor.fetchall()
            for row in rows:
                tasks_list.append(map_row_to_task(row))
    except Exception as e:
        logger.exception(f"Failed to get tasks older than {older_than_timestamp} for occurrence {occurrence_id}: {e}")
    return tasks_list


def get_active_task_for_channel(
    channel_id: str, occurrence_id: str = "default", db_path: Optional[str] = None
) -> Optional[Task]:
    """Get the active task for a specific channel and occurrence, if one exists.

    Args:
        channel_id: The channel to check
        occurrence_id: Runtime occurrence ID (default: "default")
        db_path: Optional database path

    Returns:
        The active task for the channel in this occurrence, or None if no active task exists
    """
    sql = """SELECT * FROM tasks
             WHERE channel_id = ? AND status = ? AND agent_occurrence_id = ?
             ORDER BY created_at DESC LIMIT 1"""
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (channel_id, TaskStatus.ACTIVE.value, occurrence_id))
            row = cursor.fetchone()
            if row:
                task = map_row_to_task(row)
                logger.info(
                    f"[GET_ACTIVE_TASK] Found active task for channel {channel_id}: task_id={task.task_id}, description={task.description[:100] if task.description else 'N/A'}"
                )
                return task
            else:
                logger.info(f"[GET_ACTIVE_TASK] No active task found for channel {channel_id}")
            return None
    except Exception as e:
        logger.exception(f"Failed to get active task for channel {channel_id} occurrence {occurrence_id}: {e}")
        return None


def set_task_updated_info_flag(
    task_id: str,
    updated_content: str,
    occurrence_id: str,
    time_service: TimeServiceProtocol,
    db_path: Optional[str] = None,
) -> bool:
    """Set the updated_info_available flag on a task with new observation content.

    This function checks if the task has already passed conscience checks. If the task
    has passed conscience with any action OTHER than PONDER, it returns False (too late).
    If the task hasn't passed conscience yet, or passed with PONDER, it sets the flag
    and returns True.

    Args:
        task_id: The task to update
        updated_content: The new observation content
        occurrence_id: Runtime occurrence ID for safety check
        time_service: Time service for timestamps
        db_path: Optional database path

    Returns:
        True if flag was set successfully, False if task already committed to action or
        doesn't belong to this occurrence
    """
    # First, verify the task belongs to this occurrence
    task = get_task_by_id(task_id, occurrence_id, db_path)
    if not task or task.agent_occurrence_id != occurrence_id:
        logger.warning(
            f"Task {task_id} does not belong to occurrence {occurrence_id}, cannot set updated_info_available flag"
        )
        return False

    # Check if task has any completed thoughts with non-PONDER action
    from ciris_engine.logic.persistence.models.thoughts import get_thoughts_by_task_id

    thoughts = get_thoughts_by_task_id(task_id, occurrence_id, db_path)

    # Check if any thought is completed with a non-PONDER action
    for thought in thoughts:
        if thought.status == ThoughtStatus.COMPLETED:  # Thoughts use ThoughtStatus enum
            # Check if final_action exists and is not PONDER
            if thought.final_action:
                action_type = thought.final_action.action_type
                # If action is anything other than PONDER, it's too late
                if action_type != "PONDER" and action_type != HandlerActionType.PONDER.value:
                    logger.info(
                        f"Task {task_id} already committed to action {action_type}, "
                        f"cannot set updated_info_available flag"
                    )
                    return False

    # Safe to update - either no thoughts completed yet, or only PONDER actions
    sql = """
        UPDATE tasks
        SET updated_info_available = 1,
            updated_info_content = ?,
            updated_at = ?
        WHERE task_id = ? AND agent_occurrence_id = ?
    """
    params = (updated_content, time_service.now_iso(), task_id, occurrence_id)
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Set updated_info_available flag for task {task_id}")
                return True
            logger.warning(f"Task {task_id} not found for update in occurrence {occurrence_id}")
            return False
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

    Uses deterministic task_id based on date to prevent race conditions when
    multiple occurrences try to create the same shared task simultaneously.

    The task is created with agent_occurrence_id="__shared__" to make it visible
    to all occurrences of the agent.

    Args:
        task_type: Type of task (e.g., "wakeup", "shutdown")
        channel_id: Channel where task originated
        description: Task description
        priority: Task priority (0-10)
        time_service: Time service for timestamps
        db_path: Optional database path

    Returns:
        Tuple of (Task, was_created) where was_created=True if this call created
        the task, False if it already existed.

    Example:
        >>> task, created = try_claim_shared_task("wakeup", "system", "Identity affirmation", 10, time_service)
        >>> if created:
        ...     print("This occurrence will process wakeup")
        ... else:
        ...     print("Another occurrence already claimed wakeup")
    """
    from datetime import datetime, timezone

    # Create deterministic task ID based on type and date
    date_str = datetime.now(timezone.utc).strftime("%Y%m%d")
    task_id = f"{task_type.upper()}_SHARED_{date_str}"

    # First, check if task already exists
    existing = get_task_by_id(task_id, "__shared__", db_path)
    if existing:
        # CRITICAL: Only reuse task if it's in a valid reusable state
        # Stale tasks (completed, failed, or very old active tasks) should NOT be reused
        # This prevents infinite loops from reusing tasks with completed seed thoughts

        from datetime import timedelta

        # Parse created_at string to datetime for age calculation
        created_at = datetime.fromisoformat(existing.created_at.replace("Z", "+00:00"))
        task_age = time_service.now() - created_at
        is_fresh = task_age < timedelta(minutes=10)  # Fresh if created within last 10 minutes
        is_reusable_status = existing.status in [TaskStatus.PENDING, TaskStatus.ACTIVE]

        if not is_reusable_status:
            logger.warning(
                f"Shared task {task_id} exists but has terminal status {existing.status.value}. "
                "This stale task should have been cleaned up. Creating new task instead."
            )
            # Delete the stale task and create a new one
            delete_tasks_by_ids([task_id], db_path)
        elif not is_fresh:
            logger.warning(
                f"Shared task {task_id} exists but is stale (age: {task_age}). "
                "This old active task should have been cleaned up. Creating new task instead."
            )
            # Delete the stale task and create a new one
            delete_tasks_by_ids([task_id], db_path)
        else:
            # Task is fresh and in valid state - safe to reuse
            logger.info(
                f"Shared task {task_id} already exists (status={existing.status.value}, age={task_age}), "
                "returning existing task"
            )
            return (existing, False)

    # Try to create the task with INSERT OR IGNORE for race safety
    # Use dialect adapter for database compatibility
    from ciris_engine.logic.persistence.db.dialect import get_adapter

    adapter = get_adapter()
    now = time_service.now_iso()

    columns = [
        "task_id",
        "channel_id",
        "agent_occurrence_id",
        "description",
        "status",
        "priority",
        "created_at",
        "updated_at",
        "parent_task_id",
        "context_json",
        "outcome_json",
        "signed_by",
        "signature",
        "signed_at",
        "updated_info_available",
        "updated_info_content",
        "images_json",
    ]
    conflict_columns = ["task_id"]  # Primary key constraint (task_id only)

    sql = adapter.insert_or_ignore("tasks", columns, conflict_columns)
    params = (
        task_id,
        channel_id,
        "__shared__",
        description,
        TaskStatus.PENDING.value,
        priority,
        now,
        now,
        None,  # parent_task_id
        None,  # context_json
        None,  # outcome_json
        None,  # signed_by
        None,  # signature
        None,  # signed_at
        0,  # updated_info_available
        None,  # updated_info_content
        None,  # images_json (shared tasks don't have images)
    )

    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()

            if cursor.rowcount > 0:
                # We successfully created the task
                logger.info(f"Successfully claimed shared task {task_id}")
                created_task = get_task_by_id(task_id, "__shared__", db_path)
                if created_task:
                    return (created_task, True)
                else:
                    # This shouldn't happen, but handle gracefully
                    logger.error(f"Created shared task {task_id} but couldn't retrieve it")
                    raise RuntimeError(f"Failed to retrieve newly created shared task {task_id}")
            else:
                # INSERT OR IGNORE returned 0 rows - another occurrence created it between our check and insert
                logger.info(f"Another occurrence claimed shared task {task_id} during race")
                existing = get_task_by_id(task_id, "__shared__", db_path)
                if existing:
                    return (existing, False)
                else:
                    # This shouldn't happen, but handle gracefully
                    logger.error(f"INSERT OR IGNORE for {task_id} returned 0 rows but task doesn't exist")
                    raise RuntimeError(f"Shared task {task_id} creation race condition failed")

    except Exception as e:
        logger.exception(f"Failed to claim shared task {task_id}: {e}")
        raise


def get_shared_task_status(
    task_type: str, within_hours: int = 24, db_path: Optional[str] = None
) -> Optional[TaskStatus]:
    """Get the status of the most recent shared task of a given type.

    Args:
        task_type: Type of task (e.g., "wakeup", "shutdown")
        within_hours: Only consider tasks created within this many hours (default: 24)
        db_path: Optional database path

    Returns:
        TaskStatus enum if task found, None if no recent task exists
    """
    from datetime import datetime, timedelta, timezone

    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    cutoff_iso = cutoff_time.isoformat()

    sql = """
        SELECT status FROM tasks
        WHERE agent_occurrence_id = '__shared__'
          AND task_id LIKE ?
          AND created_at > ?
        ORDER BY created_at DESC
        LIMIT 1
    """
    pattern = f"{task_type.upper()}_SHARED_%"

    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            # Note: PostgreSQLCursorWrapper automatically translates ? to %s
            cursor.execute(sql, (pattern, cutoff_iso))
            row = cursor.fetchone()
            if row:
                return TaskStatus(row["status"])
            return None
    except Exception as e:
        logger.exception(f"Failed to get shared task status for {task_type}: {e}")
        return None


def is_shared_task_completed(task_type: str, within_hours: int = 24, db_path: Optional[str] = None) -> bool:
    """Check if a shared task of the given type has been completed recently.

    Args:
        task_type: Type of task (e.g., "wakeup", "shutdown")
        within_hours: Only consider tasks created within this many hours (default: 24)
        db_path: Optional database path

    Returns:
        True if a completed task exists, False otherwise
    """
    status = get_shared_task_status(task_type, within_hours, db_path)
    return status == TaskStatus.COMPLETED if status else False


def get_latest_shared_task(task_type: str, within_hours: int = 24, db_path: Optional[str] = None) -> Optional[Task]:
    """Get the most recent shared task of a given type.

    Args:
        task_type: Type of task (e.g., "wakeup", "shutdown")
        within_hours: Only consider tasks created within this many hours (default: 24)
        db_path: Optional database path

    Returns:
        Task object if found, None otherwise
    """
    from datetime import datetime, timedelta, timezone

    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    cutoff_iso = cutoff_time.isoformat()

    sql = """
        SELECT * FROM tasks
        WHERE agent_occurrence_id = '__shared__'
          AND task_id LIKE ?
          AND created_at > ?
        ORDER BY created_at DESC
        LIMIT 1
    """
    pattern = f"{task_type.upper()}_SHARED_%"

    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            # Note: PostgreSQLCursorWrapper automatically translates ? to %s
            cursor.execute(sql, (pattern, cutoff_iso))
            row = cursor.fetchone()
            if row:
                return map_row_to_task(row)
            return None
    except Exception as e:
        logger.exception(f"Failed to get latest shared task for {task_type}: {e}")
        return None


def get_task_by_correlation_id(
    correlation_id: str, occurrence_id: str = "default", db_path: Optional[str] = None
) -> Optional[Task]:
    """
    Query for a task by correlation_id (e.g., Reddit post/comment ID).

    Args:
        correlation_id: The correlation ID to search for (stored in context_json)
        occurrence_id: Agent occurrence ID (default: "default")
        db_path: Optional database path

    Returns:
        Task if found, None otherwise
    """
    from ciris_engine.logic.config.db_paths import get_sqlite_db_full_path
    from ciris_engine.logic.persistence.db.dialect import get_adapter, init_dialect

    # Initialize dialect based on db_path BEFORE building SQL
    # This ensures the correct dialect (SQLite or PostgreSQL) is used
    init_dialect(db_path if db_path else get_sqlite_db_full_path())

    # Use dialect adapter for JSON extraction (SQLite vs PostgreSQL)
    adapter = get_adapter()
    json_expr = adapter.json_extract("context_json", "$.correlation_id")

    sql = f"""
        SELECT * FROM tasks
        WHERE agent_occurrence_id = {adapter.placeholder()}
          AND {json_expr} = {adapter.placeholder()}
        ORDER BY created_at DESC
        LIMIT 1
    """

    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (occurrence_id, correlation_id))
            row = cursor.fetchone()
            if row:
                return map_row_to_task(row)
            return None
    except Exception as e:
        logger.exception(f"Failed to get task by correlation_id {correlation_id}: {e}")
        return None
