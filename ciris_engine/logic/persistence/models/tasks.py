import json
from typing import List, Optional, Any, TYPE_CHECKING
from ciris_engine.logic.persistence import get_db_connection
from ciris_engine.logic.persistence.utils import map_row_to_task
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
import logging

if TYPE_CHECKING:
    from ciris_engine.protocols.services.infrastructure.authentication import AuthenticationServiceProtocol

logger = logging.getLogger(__name__)

def get_tasks_by_status(status: TaskStatus, db_path: Optional[str] = None) -> List[Task]:
    """Returns all tasks with the given status from the tasks table as Task objects."""
    if not isinstance(status, TaskStatus):
        raise TypeError(f"Expected TaskStatus enum, got {type(status)}: {status}")
    status_val = status.value
    sql = "SELECT * FROM tasks WHERE status = ? ORDER BY created_at ASC"
    tasks_list: List[Any] = []
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (status_val,))
            rows = cursor.fetchall()
            for row in rows:
                tasks_list.append(map_row_to_task(row))
    except Exception as e:
        logger.exception(f"Failed to get tasks with status {status_val}: {e}")
    return tasks_list

def get_all_tasks(db_path: Optional[str] = None) -> List[Task]:
    sql = "SELECT * FROM tasks ORDER BY created_at ASC"
    tasks_list: List[Any] = []
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            for row in rows:
                tasks_list.append(map_row_to_task(row))
    except Exception as e:
        logger.exception(f"Failed to get all tasks: {e}")
    return tasks_list

def add_task(task: Task, db_path: Optional[str] = None) -> str:
    task_dict = task.model_dump(mode='json')
    sql = """
        INSERT INTO tasks (task_id, channel_id, description, status, priority, created_at, updated_at,
                           parent_task_id, context_json, outcome_json, signed_by, signature, signed_at)
        VALUES (:task_id, :channel_id, :description, :status, :priority, :created_at, :updated_at,
                :parent_task_id, :context, :outcome, :signed_by, :signature, :signed_at)
    """
    params = {
        **task_dict,
        "status": task.status.value,
        "context": json.dumps(task_dict.get("context")) if task_dict.get("context") is not None else None,
        "outcome": json.dumps(task_dict.get("outcome")) if task_dict.get("outcome") is not None else None,
        "signed_by": task_dict.get("signed_by"),
        "signature": task_dict.get("signature"),
        "signed_at": task_dict.get("signed_at"),
    }
    try:
        with get_db_connection(db_path) as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.info(f"Added task ID {task.task_id} to database.")
        return task.task_id
    except Exception as e:
        logger.exception(f"Failed to add task {task.task_id}: {e}")
        raise

def get_task_by_id(task_id: str, db_path: Optional[str] = None) -> Optional[Task]:
    sql = "SELECT * FROM tasks WHERE task_id = ?"
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (task_id,))
            row = cursor.fetchone()
            if row:
                return map_row_to_task(row)
            return None
    except Exception as e:
        logger.exception(f"Failed to get task {task_id}: {e}")
        return None

def update_task_status(task_id: str, new_status: TaskStatus, time_service: TimeServiceProtocol, db_path: Optional[str] = None) -> bool:
    sql = "UPDATE tasks SET status = ?, updated_at = ? WHERE task_id = ?"
    params = (new_status.value, time_service.now_iso(), task_id)
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.execute(sql, params)
            conn.commit()
            if cursor.rowcount > 0:
                logger.info(f"Updated status of task ID {task_id} to {new_status.value}.")
                return True
            logger.warning(f"Task ID {task_id} not found for status update.")
            return False
    except Exception as e:
        logger.exception(f"Failed to update task status for {task_id}: {e}")
        return False

def task_exists(task_id: str, db_path: Optional[str] = None) -> bool:
    return get_task_by_id(task_id, db_path=db_path) is not None

async def add_system_task(task: Task, auth_service: Optional["AuthenticationServiceProtocol"] = None, db_path: Optional[str] = None) -> str:
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

def get_recent_completed_tasks(limit: int = 10, db_path: Optional[str] = None) -> List[Task]:
    tasks_list = get_all_tasks(db_path=db_path)
    completed = [t for t in tasks_list if getattr(t, 'status', None) == TaskStatus.COMPLETED]
    completed_sorted = sorted(completed, key=lambda t: getattr(t, 'updated_at', ''), reverse=True)
    return completed_sorted[:limit]

def get_top_tasks(limit: int = 10, db_path: Optional[str] = None) -> List[Task]:
    tasks_list = get_all_tasks(db_path=db_path)
    sorted_tasks = sorted(tasks_list, key=lambda t: (-getattr(t, 'priority', 0), getattr(t, 'created_at', '')))
    return sorted_tasks[:limit]

def get_pending_tasks_for_activation(limit: int = 10, db_path: Optional[str] = None) -> List[Task]:
    """Get pending tasks ordered by priority (highest first) then by creation date, with optional limit."""
    pending_tasks = get_tasks_by_status(TaskStatus.PENDING, db_path=db_path)
    # Sort by priority (descending) then by created_at (ascending for oldest first)
    sorted_tasks = sorted(pending_tasks, key=lambda t: (-getattr(t, 'priority', 0), getattr(t, 'created_at', '')))
    return sorted_tasks[:limit]

def count_tasks(status: Optional[TaskStatus] = None, db_path: Optional[str] = None) -> int:
    tasks_list = get_all_tasks(db_path=db_path)
    if status:
        return sum(1 for t in tasks_list if getattr(t, 'status', None) == status)
    return len(tasks_list)

def delete_tasks_by_ids(task_ids: List[str], db_path: Optional[str] = None) -> bool:
    """Deletes tasks and their associated thoughts and feedback_mappings with the given IDs from the database."""
    if not task_ids:
        logger.warning("No task IDs provided for deletion.")
        return False

    logger.warning(f"DELETE_OPERATION: delete_tasks_by_ids called with {len(task_ids)} tasks: {task_ids}")
    import traceback
    logger.warning(f"DELETE_OPERATION: Called from: {''.join(traceback.format_stack()[-3:-1])}")

    placeholders = ','.join('?' for _ in task_ids)

    sql_get_thought_ids = f"SELECT thought_id FROM thoughts WHERE source_task_id IN ({placeholders})"
    sql_delete_feedback_mappings = "DELETE FROM feedback_mappings WHERE target_thought_id IN ({})"
    sql_delete_thoughts = f"DELETE FROM thoughts WHERE source_task_id IN ({placeholders})"
    sql_delete_tasks = f"DELETE FROM tasks WHERE task_id IN ({placeholders})"

    deleted_count = 0
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()

            cursor.execute(sql_get_thought_ids, task_ids)
            thought_rows = cursor.fetchall()
            thought_ids_to_delete = [row['thought_id'] for row in thought_rows]

            if thought_ids_to_delete:
                feedback_placeholders = ','.join('?' for _ in thought_ids_to_delete)
                current_sql_delete_feedback_mappings = sql_delete_feedback_mappings.format(feedback_placeholders)
                cursor.execute(current_sql_delete_feedback_mappings, thought_ids_to_delete)
                logger.info(f"Deleted {cursor.rowcount} associated feedback mappings for thought IDs: {thought_ids_to_delete}.")
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

def get_tasks_older_than(older_than_timestamp: str, db_path: Optional[str] = None) -> List[Task]:
    """Get all tasks with created_at older than the given ISO timestamp, returning Task objects."""
    sql = "SELECT * FROM tasks WHERE created_at < ?"
    tasks_list: List[Any] = []
    try:
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (older_than_timestamp,))
            rows = cursor.fetchall()
            for row in rows:
                tasks_list.append(map_row_to_task(row))
    except Exception as e:
        logger.exception(f"Failed to get tasks older than {older_than_timestamp}: {e}")
    return tasks_list
