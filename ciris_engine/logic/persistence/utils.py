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

    if row_dict.get("context_json"):
        try:
            ctx_data = json.loads(row_dict["context_json"])
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
                    channel_id=None, user_id=None, correlation_id=str(uuid.uuid4()), parent_task_id=None,
                    agent_occurrence_id=agent_occurrence_id
                )
        except Exception as e:
            logger.warning(f"Failed to decode context_json for task {row_dict.get('task_id')}: {e}")
            row_dict["context"] = TaskContext(
                channel_id=None, user_id=None, correlation_id=str(uuid.uuid4()), parent_task_id=None,
                agent_occurrence_id=agent_occurrence_id
            )
    else:
        row_dict["context"] = TaskContext(
            channel_id=None, user_id=None, correlation_id=str(uuid.uuid4()), parent_task_id=None,
            agent_occurrence_id=agent_occurrence_id
        )
    if row_dict.get("outcome_json"):
        try:
            outcome_data = json.loads(row_dict["outcome_json"])
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

    # Remove database-specific columns that aren't in the Task schema
    for k in ["context_json", "outcome_json", "retry_count"]:
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

    if row_dict.get("context_json"):
        try:
            ctx_data = json.loads(row_dict["context_json"])
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
            row_dict["ponder_notes"] = json.loads(row_dict["ponder_notes_json"])
        except Exception:
            logger.warning(f"Failed to decode ponder_notes_json for thought {row_dict.get('thought_id')}")
            row_dict["ponder_notes"] = None
    else:
        row_dict["ponder_notes"] = None
    if row_dict.get("final_action_json"):
        try:
            action_data = json.loads(row_dict["final_action_json"])
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
