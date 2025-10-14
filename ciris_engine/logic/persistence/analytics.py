from typing import List, Optional

from ciris_engine.logic.persistence.models.tasks import count_tasks, get_tasks_by_status
from ciris_engine.logic.persistence.models.thoughts import (
    count_thoughts,
    get_thoughts_by_status,
    get_thoughts_by_task_id,
)
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought


def get_pending_thoughts_for_active_tasks(occurrence_id: str = "default", limit: Optional[int] = None) -> List[Thought]:
    """Return all thoughts pending or processing for ACTIVE tasks."""
    active_tasks = get_tasks_by_status(TaskStatus.ACTIVE, occurrence_id)
    active_task_ids = {t.task_id for t in active_tasks}
    pending_thoughts = get_thoughts_by_status(ThoughtStatus.PENDING, occurrence_id)
    processing_thoughts = get_thoughts_by_status(ThoughtStatus.PROCESSING, occurrence_id)
    all_thoughts = pending_thoughts + processing_thoughts
    filtered = [th for th in all_thoughts if th.source_task_id in active_task_ids]
    if limit is not None:
        return filtered[:limit]
    return filtered


def count_pending_thoughts_for_active_tasks(occurrence_id: str = "default") -> int:
    """Return the count of thoughts pending or processing for ACTIVE tasks."""
    active_tasks = get_tasks_by_status(TaskStatus.ACTIVE, occurrence_id)
    active_task_ids = {t.task_id for t in active_tasks}
    pending_thoughts = get_thoughts_by_status(ThoughtStatus.PENDING, occurrence_id)
    processing_thoughts = get_thoughts_by_status(ThoughtStatus.PROCESSING, occurrence_id)
    all_thoughts = pending_thoughts + processing_thoughts
    filtered = [th for th in all_thoughts if th.source_task_id in active_task_ids]
    return len(filtered)


def count_active_tasks(occurrence_id: str = "default") -> int:
    """Count tasks with ACTIVE status."""
    return count_tasks(TaskStatus.ACTIVE, occurrence_id)


def get_tasks_needing_seed_thought(occurrence_id: str = "default", limit: Optional[int] = None) -> List[Task]:
    """Get active tasks that don't yet have thoughts."""
    active_tasks = get_tasks_by_status(TaskStatus.ACTIVE, occurrence_id)
    tasks_needing_seed: List[Task] = []
    for task in active_tasks:
        thoughts = get_thoughts_by_task_id(task.task_id, occurrence_id)
        if not thoughts:
            tasks_needing_seed.append(task)
    if limit:
        return tasks_needing_seed[:limit]
    return tasks_needing_seed


def pending_thoughts(occurrence_id: str = "default") -> bool:
    """Check if there are any pending thoughts."""
    return count_thoughts(occurrence_id) > 0


def thought_exists_for(task_id: str, occurrence_id: str = "default") -> bool:
    """Check if any thoughts exist for the given task."""
    thoughts = get_thoughts_by_task_id(task_id, occurrence_id)
    return len(thoughts) > 0


def count_thoughts_by_status(status: ThoughtStatus, occurrence_id: str = "default") -> int:
    """Count thoughts with the given status."""
    thoughts = get_thoughts_by_status(status, occurrence_id)
    return len(thoughts)
