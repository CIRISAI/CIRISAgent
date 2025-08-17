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
        from ciris_engine.logic.persistence.db import get_db_connection

        # Queue size is pending + processing
        queue_size = float(self.pending_thoughts + self.processing_thoughts)

        # Get processed count (completed thoughts)
        completed_count = len(get_thoughts_by_status(ThoughtStatus.COMPLETED))
        queue_processed_total = float(completed_count)

        # Get error count (failed thoughts)
        failed_count = len(get_thoughts_by_status(ThoughtStatus.FAILED))
        queue_errors_total = float(failed_count)

        # Calculate average wait time from created_at to updated_at for completed thoughts
        queue_avg_wait_ms = 0.0
        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                # Get completed thoughts with timing data
                cursor.execute(
                    """
                    SELECT created_at, updated_at
                    FROM thoughts
                    WHERE status = ?
                    AND created_at IS NOT NULL
                    AND updated_at IS NOT NULL
                    ORDER BY updated_at DESC
                    LIMIT 100
                """,
                    (ThoughtStatus.COMPLETED.value,),
                )

                rows = cursor.fetchall()
                if rows:
                    total_wait_ms = 0.0
                    valid_count = 0

                    for row in rows:
                        try:
                            created_str = row[0]
                            updated_str = row[1]

                            # Parse timestamps
                            created_at = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                            updated_at = datetime.fromisoformat(updated_str.replace("Z", "+00:00"))

                            # Calculate wait time in milliseconds
                            wait_time_ms = (updated_at - created_at).total_seconds() * 1000
                            if wait_time_ms >= 0:  # Sanity check
                                total_wait_ms += wait_time_ms
                                valid_count += 1
                        except (ValueError, TypeError):
                            continue  # Skip invalid timestamps

                    if valid_count > 0:
                        queue_avg_wait_ms = total_wait_ms / valid_count

        except Exception:
            # If we can't calculate wait times, default to 0
            queue_avg_wait_ms = 0.0

        return {
            "queue_size": queue_size,
            "queue_processed_total": queue_processed_total,
            "queue_errors_total": queue_errors_total,
            "queue_avg_wait_ms": queue_avg_wait_ms,
        }


def get_queue_status(db_path: Optional[str] = None) -> QueueStatus:
    """
    Get current queue status with task and thought counts.

    This is the centralized function for getting queue counts,
    used by both the system context builder and the agent processor.

    Args:
        db_path: Optional database path override

    Returns:
        QueueStatus object with counts
    """
    # Get task counts
    pending_tasks = count_tasks(TaskStatus.PENDING, db_path=db_path)
    total_tasks = count_tasks(db_path=db_path)

    # Get thought counts
    # Note: count_thoughts() already returns PENDING + PROCESSING count
    pending_thoughts = len(get_thoughts_by_status(ThoughtStatus.PENDING, db_path=db_path))
    processing_thoughts = len(get_thoughts_by_status(ThoughtStatus.PROCESSING, db_path=db_path))

    # For total thoughts, we need all statuses
    total_thoughts = (
        pending_thoughts
        + processing_thoughts
        + len(get_thoughts_by_status(ThoughtStatus.COMPLETED, db_path=db_path))
        + len(get_thoughts_by_status(ThoughtStatus.FAILED, db_path=db_path))
    )

    return QueueStatus(
        pending_tasks=pending_tasks,
        pending_thoughts=pending_thoughts,
        processing_thoughts=processing_thoughts,
        total_tasks=total_tasks,
        total_thoughts=total_thoughts,
    )
