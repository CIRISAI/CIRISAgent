import asyncio
import json
import logging
from typing import Any, List, Optional

from ciris_engine.logic.persistence.db import get_db_connection
from ciris_engine.logic.persistence.utils import map_row_to_thought
from ciris_engine.schemas.persistence.core import ThoughtSummary
from ciris_engine.schemas.runtime.enums import ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought

logger = logging.getLogger(__name__)


def get_thoughts_by_status(status: ThoughtStatus, db_path: Optional[str] = None) -> List[Thought]:
    """Returns all thoughts with the given status from the thoughts table as Thought objects."""
    if not isinstance(status, ThoughtStatus):
        raise TypeError(f"Expected ThoughtStatus enum, got {type(status)}: {status}")
    status_val = status.value
    sql = "SELECT * FROM thoughts WHERE status = ? ORDER BY created_at ASC"
    thoughts: List[Any] = []
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (status_val,))
            rows = cursor.fetchall()
            for row in rows:
                thoughts.append(map_row_to_thought(row))
    except Exception as e:
        logger.exception(f"Failed to get thoughts with status {status_val}: {e}")
    return thoughts


def add_thought(thought: Thought, db_path: Optional[str] = None) -> str:
    thought_dict = thought.model_dump(mode="json")
    sql = """
        INSERT INTO thoughts (thought_id, source_task_id, channel_id, thought_type, status, created_at, updated_at,
                              round_number, content, context_json, thought_depth, ponder_notes_json,
                              parent_thought_id, final_action_json)
        VALUES (:thought_id, :source_task_id, :channel_id, :thought_type, :status, :created_at, :updated_at,
                :round_number, :content, :context, :thought_depth, :ponder_notes, :parent_thought_id, :final_action)
    """
    params = {
        **thought_dict,
        "status": thought.status.value,
        "context": json.dumps(thought_dict.get("context")) if thought_dict.get("context") is not None else None,
        "ponder_notes": (
            json.dumps(thought_dict.get("ponder_notes")) if thought_dict.get("ponder_notes") is not None else None
        ),
        "final_action": (
            json.dumps(thought_dict.get("final_action")) if thought_dict.get("final_action") is not None else None
        ),
    }
    try:
        with get_db_connection(db_path=db_path) as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.info(f"Added thought ID {thought.thought_id} to database.")
        return thought.thought_id
    except Exception as e:
        logger.exception(f"Failed to add thought {thought.thought_id}: {e}")
        raise


def get_thought_by_id(thought_id: str, db_path: Optional[str] = None) -> Optional[Thought]:
    sql = "SELECT * FROM thoughts WHERE thought_id = ?"
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (thought_id,))
            row = cursor.fetchone()
            if row:
                return map_row_to_thought(row)
            return None
    except Exception as e:
        logger.exception(f"Failed to get thought {thought_id}: {e}")
        return None


async def async_get_thought_by_id(thought_id: str, db_path: Optional[str] = None) -> Optional[Thought]:
    """Asynchronous wrapper for get_thought_by_id using asyncio.to_thread."""
    return await asyncio.to_thread(get_thought_by_id, thought_id, db_path)


def get_thoughts_by_ids(thought_ids: List[str], db_path: Optional[str] = None) -> dict[str, Thought]:
    """Fetch multiple thoughts by their IDs in a single query.

    Returns a dict mapping thought_id to Thought object.
    More efficient than multiple individual queries.
    """
    if not thought_ids:
        return {}

    placeholders = ",".join(["?"] * len(thought_ids))
    sql = f"SELECT * FROM thoughts WHERE thought_id IN ({placeholders})"  # nosec B608 - placeholders are '?' strings, not user input

    result = {}
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, thought_ids)
            rows = cursor.fetchall()
            for row in rows:
                thought = map_row_to_thought(row)
                result[thought.thought_id] = thought
    except Exception as e:
        logger.exception(f"Failed to batch fetch thoughts: {e}")

    return result


async def async_get_thoughts_by_ids(thought_ids: List[str], db_path: Optional[str] = None) -> dict[str, Thought]:
    """Asynchronous wrapper for get_thoughts_by_ids."""
    return await asyncio.to_thread(get_thoughts_by_ids, thought_ids, db_path)


async def async_get_thought_status(thought_id: str, db_path: Optional[str] = None) -> Optional[ThoughtStatus]:
    """Retrieve just the status of a thought asynchronously."""

    def _query() -> Optional[ThoughtStatus]:
        sql = "SELECT status FROM thoughts WHERE thought_id = ?"
        try:
            with get_db_connection(db_path=db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(sql, (thought_id,))
                row = cursor.fetchone()
                if row:
                    return ThoughtStatus(row[0])
        except Exception as exc:
            logger.exception(f"Failed to fetch status for thought {thought_id}: {exc}")
        return None

    return await asyncio.to_thread(_query)


def get_thoughts_by_task_id(task_id: str, db_path: Optional[str] = None) -> List[Thought]:
    """Return all thoughts for a given source_task_id as Thought objects."""
    sql = "SELECT * FROM thoughts WHERE source_task_id = ? ORDER BY created_at ASC"
    thoughts: List[Any] = []
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (task_id,))
            rows = cursor.fetchall()
            for row in rows:
                thoughts.append(map_row_to_thought(row))
    except Exception as e:
        logger.exception(f"Failed to get thoughts for task {task_id}: {e}")
    return thoughts


def delete_thoughts_by_ids(thought_ids: List[str], db_path: Optional[str] = None) -> int:
    """Delete thoughts by a list of IDs. Returns the number deleted."""
    if not thought_ids:
        return 0

    logger.warning(f"DELETE_OPERATION: delete_thoughts_by_ids called with {len(thought_ids)} thoughts: {thought_ids}")
    import traceback

    logger.warning(f"DELETE_OPERATION: Called from: {''.join(traceback.format_stack()[-3:-1])}")

    sql = f"DELETE FROM thoughts WHERE thought_id IN ({','.join(['?']*len(thought_ids))})"  # nosec B608 - placeholders are '?' strings, not user input
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.execute(sql, thought_ids)
            conn.commit()
            deleted_count = cursor.rowcount
            logger.warning(f"DELETE_OPERATION: Successfully deleted {deleted_count} thoughts")
            return deleted_count
    except Exception as e:
        logger.exception(f"Failed to delete thoughts by ids: {e}")
        return 0


def count_thoughts(db_path: Optional[str] = None) -> int:
    """Return the count of thoughts that are PENDING or PROCESSING."""
    sql = "SELECT COUNT(*) FROM thoughts WHERE status = ? OR status = ?"
    count = 0
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (ThoughtStatus.PENDING.value, ThoughtStatus.PROCESSING.value))
            result = cursor.fetchone()
            if result:
                count = result[0]
    except Exception as e:
        logger.exception(f"Failed to count PENDING or PROCESSING thoughts: {e}")
    return count


def update_thought_status(
    thought_id: str, status: ThoughtStatus, db_path: Optional[str] = None, final_action: Optional[Any] = None
) -> bool:
    """Update the status of a thought by ID and optionally final_action.

    Args:
        thought_id: The ID of the thought to update
        status: ThoughtStatus enum value
        db_path: Optional database path
        final_action: ActionSelectionDMAResult object or other serializable data
        **kwargs: Additional parameters for compatibility

    Returns:
        bool: True if updated, False otherwise
    """
    from ..db import get_db_connection

    status_val = getattr(status, "value", status)

    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()

            # Build dynamic SQL based on what needs to be updated
            updates = ["status = ?"]
            params = [status_val]

            # DELETED: Legacy JSON serialization. Protocol-driven approach stores schemas directly.
            # final_action storage removed - use proper schema relationships instead

            params.append(thought_id)

            sql = f"UPDATE thoughts SET {', '.join(updates)} WHERE thought_id = ?"  # nosec B608 - updates are hardcoded strings like 'status = ?', not user input
            cursor.execute(sql, params)
            conn.commit()

            updated = cursor.rowcount > 0
            if not updated:
                logger.warning(f"No thought found with id {thought_id} to update status.")
            else:
                logger.info(f"Updated thought {thought_id} status to {status_val}")
            return updated
    except Exception as e:
        logger.exception(f"Failed to update status for thought {thought_id}: {e}")
        return False


# DELETED: Legacy pydantic_to_dict function. Use protocol-driven schemas directly.


def get_thoughts_older_than(older_than_timestamp: str, db_path: Optional[str] = None) -> List[Thought]:
    """Returns all thoughts with created_at older than the given ISO timestamp as Thought objects."""
    sql = "SELECT * FROM thoughts WHERE created_at < ? ORDER BY created_at ASC"
    thoughts: List[Any] = []
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (older_than_timestamp,))
            rows = cursor.fetchall()
            for row in rows:
                thoughts.append(map_row_to_thought(row))
    except Exception as e:
        logger.exception(f"Failed to get thoughts older than {older_than_timestamp}: {e}")
    return thoughts


def get_recent_thoughts(limit: int = 10, db_path: Optional[str] = None) -> List[ThoughtSummary]:
    """Get recent thoughts as typed summaries for status reporting."""
    sql = "SELECT * FROM thoughts ORDER BY created_at DESC LIMIT ?"
    thoughts = []
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(sql, (limit,))
            rows = cursor.fetchall()
            for row in rows:
                thoughts.append(
                    ThoughtSummary(
                        thought_id=row["thought_id"],
                        thought_type=row["thought_type"],
                        status=row["status"],
                        created_at=row["created_at"],
                        content=row["content"],
                        source_task_id=row["source_task_id"],
                    )
                )
    except Exception as e:
        logger.exception(f"Failed to get recent thoughts: {e}")
    return thoughts
