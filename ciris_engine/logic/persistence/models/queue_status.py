"""Queue status functions for centralized access to task and thought counts."""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional

from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus

from .tasks import count_tasks
from .thoughts import get_thoughts_by_status


@dataclass
class QueueStatus:
    """Queue status with pending tasks and thoughts counts."""

    pending_tasks: int
    pending_thoughts: int
    processing_thoughts: int = 0
    total_tasks: int = 0
    total_thoughts: int = 0

    def get_metrics(self) -> Dict[str, float]:
        """
        Return the exact metrics from the v1.4.3 set.

        Returns:
            Dict containing exactly these metrics:
            - queue_size: Current queue size
            - queue_processed_total: Total items processed
            - queue_errors_total: Total processing errors
            - queue_avg_wait_ms: Average wait time in ms
        """
        # Queue size is pending + processing
        queue_size = float(self.pending_thoughts + self.processing_thoughts)

        # Completed and failed counts (via persist substrate)
        completed_thoughts = get_thoughts_by_status(ThoughtStatus.COMPLETED)
        queue_processed_total = float(len(completed_thoughts))

        failed_count = len(get_thoughts_by_status(ThoughtStatus.FAILED))
        queue_errors_total = float(failed_count)

        # Average wait time: derive from the COMPLETED thoughts we already
        # loaded above. Persist returns DESC by created_at; take the most
        # recent 100 to match the legacy LIMIT 100 / ORDER BY updated_at DESC
        # window. Skips the secondary "no thought_delete" cascade window
        # since 100 is a small fixed cap.
        queue_avg_wait_ms = 0.0
        try:
            sample = completed_thoughts[:100]
            total_wait_ms = 0.0
            valid_count = 0
            for thought in sample:
                try:
                    created_at = datetime.fromisoformat(
                        str(thought.created_at).replace("Z", "+00:00")
                    )
                    updated_at = datetime.fromisoformat(
                        str(thought.updated_at).replace("Z", "+00:00")
                    )
                    wait_time_ms = (updated_at - created_at).total_seconds() * 1000
                    if wait_time_ms >= 0:
                        total_wait_ms += wait_time_ms
                        valid_count += 1
                except (ValueError, TypeError):
                    continue
            if valid_count > 0:
                queue_avg_wait_ms = total_wait_ms / valid_count
        except Exception:
            queue_avg_wait_ms = 0.0

        return {
            "queue_size": queue_size,
            "queue_processed_total": queue_processed_total,
            "queue_errors_total": queue_errors_total,
            "queue_avg_wait_ms": queue_avg_wait_ms,
        }


def get_queue_status() -> QueueStatus:
    """
    Get current queue status with task and thought counts.

    This is the centralized function for getting queue counts,
    used by both the system context builder and the agent processor.

    Returns:
        QueueStatus object with counts
    """
    # Get task counts
    pending_tasks = count_tasks(TaskStatus.PENDING)
    total_tasks = count_tasks()

    # Get thought counts
    # Note: count_thoughts() already returns PENDING + PROCESSING count
    pending_thoughts = len(get_thoughts_by_status(ThoughtStatus.PENDING))
    processing_thoughts = len(get_thoughts_by_status(ThoughtStatus.PROCESSING))

    # For total thoughts, we need all statuses
    total_thoughts = (
        pending_thoughts
        + processing_thoughts
        + len(get_thoughts_by_status(ThoughtStatus.COMPLETED))
        + len(get_thoughts_by_status(ThoughtStatus.FAILED))
    )

    return QueueStatus(
        pending_tasks=pending_tasks,
        pending_thoughts=pending_thoughts,
        processing_thoughts=processing_thoughts,
        total_tasks=total_tasks,
        total_thoughts=total_thoughts,
    )
