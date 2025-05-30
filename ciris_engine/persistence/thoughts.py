import json
from datetime import datetime
from typing import List, Optional
from ciris_engine.persistence.db import get_db_connection
from ciris_engine.persistence.utils import map_row_to_thought
from ciris_engine.schemas.foundational_schemas_v1 import ThoughtStatus
from ciris_engine.schemas.agent_core_schemas_v1 import Thought
import logging

logger = logging.getLogger(__name__)

def get_thoughts_by_status(status, db_path=None):
    """Returns all thoughts with the given status from the thoughts table as a list of dicts."""
    # Accept both enums and strings
    status_val = getattr(status, "value", status)
    sql = "SELECT * FROM thoughts WHERE status = ? ORDER BY created_at ASC"
    thoughts = []
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

def add_thought(thought: Thought, db_path=None) -> str:
    thought_dict = thought.model_dump(mode='json')
    sql = """
        INSERT INTO thoughts (thought_id, source_task_id, thought_type, status, created_at, updated_at,
                              round_number, content, context_json, ponder_count, ponder_notes_json,
                              parent_thought_id, final_action_json)
        VALUES (:thought_id, :source_task_id, :thought_type, :status, :created_at, :updated_at,
                :round_number, :content, :context, :ponder_count, :ponder_notes, :parent_thought_id, :final_action)
    """
    params = {
        **thought_dict,
        "status": thought.status.value,
        "context": json.dumps(thought_dict.get("context")) if thought_dict.get("context") is not None else None,
        "ponder_notes": json.dumps(thought_dict.get("ponder_notes")) if thought_dict.get("ponder_notes") is not None else None,
        "final_action": json.dumps(thought_dict.get("final_action")) if thought_dict.get("final_action") is not None else None,
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

def get_thought_by_id(thought_id: str, db_path=None) -> Optional[Thought]:
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

def get_thoughts_by_task_id(task_id: str, db_path=None) -> list[Thought]:
    """Return all thoughts for a given source_task_id as Thought objects."""
    sql = "SELECT * FROM thoughts WHERE source_task_id = ? ORDER BY created_at ASC"
    thoughts = []
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

def delete_thoughts_by_ids(thought_ids: list[str], db_path=None) -> int:
    """Delete thoughts by a list of IDs. Returns the number deleted."""
    if not thought_ids:
        return 0
    sql = f"DELETE FROM thoughts WHERE thought_id IN ({','.join(['?']*len(thought_ids))})"
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.execute(sql, thought_ids)
            conn.commit()
            return cursor.rowcount
    except Exception as e:
        logger.exception(f"Failed to delete thoughts by ids: {e}")
        return 0

def count_thoughts(db_path=None) -> int:
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

def update_thought_status(thought_id, status, db_path=None, final_action=None, **kwargs):
    """Update the status of a thought by ID and optionally final_action. Returns True if updated, False otherwise. Ignores extra kwargs for compatibility."""
    from .db import get_db_connection
    status_val = getattr(status, "value", status)
    
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            
            # Build dynamic SQL based on what needs to be updated
            updates = ["status = ?"]
            params = [status_val]
            
            if final_action is not None:
                # Ensure final_action is JSON serializable
                if hasattr(final_action, 'model_dump'):
                    # Convert Pydantic models to dict to avoid serialization warnings
                    final_action = final_action.model_dump(mode="json")
                elif not isinstance(final_action, (dict, list, str, int, float, bool, type(None))):
                    # Convert other objects to string representation
                    final_action = {"result": str(final_action)}
                
                updates.append("final_action_json = ?")
                params.append(json.dumps(final_action))
            
            params.append(thought_id)
            
            sql = f"UPDATE thoughts SET {', '.join(updates)} WHERE thought_id = ?"
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

def pydantic_to_dict(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    elif isinstance(obj, dict):
        return {k: pydantic_to_dict(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [pydantic_to_dict(v) for v in obj]
    else:
        return obj
