import json
import logging
import uuid
from typing import Any

from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import FinalAction, Task, TaskContext, TaskOutcome, Thought, ThoughtContext

logger = logging.getLogger(__name__)


def map_row_to_task(row: Any) -> Task:
    row_dict = dict(row)
    # Get agent_occurrence_id from row (defaults to "default" for backwards compatibility)
    agent_occurrence_id = row_dict.get("agent_occurrence_id", "default")

    # Handle PostgreSQL JSONB vs SQLite TEXT for JSON columns
    # PostgreSQL JSONB returns parsed Python objects, SQLite TEXT returns JSON strings
    if row_dict.get("context_json"):
        try:
            ctx_json = row_dict["context_json"]
            ctx_data = ctx_json if isinstance(ctx_json, dict) else json.loads(ctx_json)
            if isinstance(ctx_data, dict):
                # Extract only the fields that TaskContext expects
                # This makes us resilient to schema changes
                row_dict["context"] = TaskContext(
                    channel_id=ctx_data.get("channel_id"),
                    user_id=ctx_data.get("user_id"),
                    correlation_id=ctx_data.get("correlation_id", str(uuid.uuid4())),
                    parent_task_id=ctx_data.get("parent_task_id"),
                    agent_occurrence_id=ctx_data.get("agent_occurrence_id", agent_occurrence_id),
                )
            else:
                # Provide required fields for TaskContext
                row_dict["context"] = TaskContext(
                    channel_id=None,
                    user_id=None,
                    correlation_id=str(uuid.uuid4()),
                    parent_task_id=None,
                    agent_occurrence_id=agent_occurrence_id,
                )
        except Exception as e:
            logger.warning(f"Failed to decode context_json for task {row_dict.get('task_id')}: {e}")
            row_dict["context"] = TaskContext(
                channel_id=None,
                user_id=None,
                correlation_id=str(uuid.uuid4()),
                parent_task_id=None,
                agent_occurrence_id=agent_occurrence_id,
            )
    else:
        row_dict["context"] = TaskContext(
            channel_id=None,
            user_id=None,
            correlation_id=str(uuid.uuid4()),
            parent_task_id=None,
            agent_occurrence_id=agent_occurrence_id,
        )
    if row_dict.get("outcome_json"):
        try:
            outcome_json = row_dict["outcome_json"]
            outcome_data = outcome_json if isinstance(outcome_json, dict) else json.loads(outcome_json)
            # Only set outcome if it's a non-empty dict with required fields
            if isinstance(outcome_data, dict) and outcome_data:
                row_dict["outcome"] = TaskOutcome.model_validate(outcome_data)
            else:
                row_dict["outcome"] = None
        except Exception:
            logger.warning(f"Failed to decode outcome_json for task {row_dict.get('task_id')}")
            row_dict["outcome"] = None
    else:
        row_dict["outcome"] = None

    # Handle PostgreSQL TIMESTAMP vs SQLite TEXT for datetime columns
    # PostgreSQL TIMESTAMP returns datetime objects, SQLite TEXT returns ISO strings
    from datetime import datetime, timezone

    for dt_field in ["created_at", "updated_at", "signed_at"]:
        if dt_field in row_dict and row_dict[dt_field]:
            if isinstance(row_dict[dt_field], datetime):
                # Ensure timezone-aware datetime (assume UTC if naive)
                dt = row_dict[dt_field]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                row_dict[dt_field] = dt.isoformat()

    # Handle images_json for native multimodal vision support
    if row_dict.get("images_json"):
        try:
            from ciris_engine.schemas.runtime.models import ImageContent

            images_json = row_dict["images_json"]
            images_data = images_json if isinstance(images_json, list) else json.loads(images_json)
            if isinstance(images_data, list) and images_data:
                row_dict["images"] = [ImageContent.model_validate(img) for img in images_data]
            else:
                row_dict["images"] = []
        except Exception as e:
            logger.warning(f"Failed to decode images_json for task {row_dict.get('task_id')}: {e}")
            row_dict["images"] = []
    else:
        row_dict["images"] = []

    # Remove database-specific columns that aren't in the Task schema
    for k in ["context_json", "outcome_json", "retry_count", "images_json"]:
        if k in row_dict:
            del row_dict[k]

    try:
        row_dict["status"] = TaskStatus(row_dict["status"])
    except Exception:
        logger.warning(
            f"Invalid status value '{row_dict['status']}' for task {row_dict.get('task_id')}. Defaulting to PENDING."
        )
        row_dict["status"] = TaskStatus.PENDING
    return Task(**row_dict)


def map_row_to_thought(row: Any) -> Thought:
    row_dict = dict(row)
    # Get agent_occurrence_id from row (defaults to "default" for backwards compatibility)
    agent_occurrence_id = row_dict.get("agent_occurrence_id", "default")

    # Handle PostgreSQL JSONB vs SQLite TEXT for JSON columns
    # PostgreSQL JSONB returns parsed Python objects, SQLite TEXT returns JSON strings
    if row_dict.get("context_json"):
        try:
            ctx_json = row_dict["context_json"]
            ctx_data = ctx_json if isinstance(ctx_json, dict) else json.loads(ctx_json)
            if isinstance(ctx_data, dict) and ctx_data:  # Check if dict is not empty
                # Extract only the fields that ThoughtContext expects
                # This makes us resilient to schema changes
                # Note: task_id and correlation_id are required fields
                task_id = ctx_data.get("task_id")
                correlation_id = ctx_data.get("correlation_id")

                if task_id and correlation_id:
                    row_dict["context"] = ThoughtContext(
                        task_id=task_id,
                        channel_id=ctx_data.get("channel_id"),
                        round_number=ctx_data.get("round_number", 0),
                        depth=ctx_data.get("depth", 0),
                        parent_thought_id=ctx_data.get("parent_thought_id"),
                        correlation_id=correlation_id,
                        agent_occurrence_id=ctx_data.get("agent_occurrence_id", agent_occurrence_id),
                    )
                else:
                    # Missing required fields, set to None
                    row_dict["context"] = None
            else:
                # For empty or invalid context, set to None instead of trying to create invalid ThoughtContext
                row_dict["context"] = None
        except Exception as e:
            logger.warning(f"Failed to decode context_json for thought {row_dict.get('thought_id')}: {e}")
            # For failed decoding, set to None instead of trying to create invalid ThoughtContext
            row_dict["context"] = None
    else:
        # No context provided, set to None
        row_dict["context"] = None
    if row_dict.get("ponder_notes_json"):
        try:
            ponder_json = row_dict["ponder_notes_json"]
            row_dict["ponder_notes"] = ponder_json if isinstance(ponder_json, list) else json.loads(ponder_json)
        except Exception:
            logger.warning(f"Failed to decode ponder_notes_json for thought {row_dict.get('thought_id')}")
            row_dict["ponder_notes"] = None
    else:
        row_dict["ponder_notes"] = None
    if row_dict.get("final_action_json"):
        try:
            action_json = row_dict["final_action_json"]
            action_data = action_json if isinstance(action_json, dict) else json.loads(action_json)
            # Only set final_action if it's a non-empty dict with required fields
            if isinstance(action_data, dict) and action_data:
                row_dict["final_action"] = FinalAction.model_validate(action_data)
            else:
                row_dict["final_action"] = None
        except Exception:
            logger.warning(f"Failed to decode final_action_json for thought {row_dict.get('thought_id')}")
            row_dict["final_action"] = None
    else:
        row_dict["final_action"] = None

    # Handle PostgreSQL TIMESTAMP vs SQLite TEXT for datetime columns
    # PostgreSQL TIMESTAMP returns datetime objects, SQLite TEXT returns ISO strings
    from datetime import datetime, timezone

    for dt_field in ["created_at", "updated_at"]:
        if dt_field in row_dict and row_dict[dt_field]:
            if isinstance(row_dict[dt_field], datetime):
                # Ensure timezone-aware datetime (assume UTC if naive)
                dt = row_dict[dt_field]
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                row_dict[dt_field] = dt.isoformat()

    # Note: Images are stored at the TASK level, not THOUGHT level.
    # Thoughts inherit images from their source task when loaded via ProcessingQueueItem.from_thought()
    # which looks up the task and copies its images.
    row_dict["images"] = []

    for k in ["context_json", "ponder_notes_json", "final_action_json"]:
        if k in row_dict:
            del row_dict[k]
    try:
        row_dict["status"] = ThoughtStatus(row_dict["status"])
    except Exception:
        logger.warning(
            f"Invalid status value '{row_dict['status']}' for thought {row_dict.get('thought_id')}. Defaulting to PENDING."
        )
        row_dict["status"] = ThoughtStatus.PENDING
    return Thought(**row_dict)
