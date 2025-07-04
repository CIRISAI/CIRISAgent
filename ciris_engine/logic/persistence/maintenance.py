import logging
from datetime import timedelta
from pathlib import Path
import asyncio
from typing import List, Optional, Any

from ciris_engine.logic.persistence import (
    get_all_tasks,
    update_task_status,
    get_task_by_id,
    get_tasks_by_status,
    delete_tasks_by_ids,
    get_tasks_older_than,
    get_thoughts_by_status,
    get_thoughts_by_task_id,
    delete_thoughts_by_ids,
    update_thought_status,
    get_thoughts_older_than,
)
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)

class DatabaseMaintenanceService:
    """
    Service for performing database maintenance tasks like cleanup and archiving.
    """
    def __init__(self, time_service: TimeServiceProtocol, archive_dir_path: str = "data_archive", archive_older_than_hours: int = 24) -> None:
        self.time_service = time_service
        self.archive_dir = Path(archive_dir_path)
        self.archive_older_than_hours = archive_older_than_hours
        self.valid_root_task_ids = {"WAKEUP_ROOT"}
        self._maintenance_task: Optional[asyncio.Task] = None
        self._shutdown_event: Optional[asyncio.Event] = None

    def _ensure_shutdown_event(self) -> None:
        """Ensure shutdown event is created when needed in async context."""
        if self._shutdown_event is None:
            try:
                self._shutdown_event = asyncio.Event()
            except RuntimeError:
                logger.warning("Cannot create shutdown event outside of async context")

    async def start(self) -> None:
        """Start the maintenance service with periodic tasks."""
        self._ensure_shutdown_event()
        self._maintenance_task = asyncio.create_task(self._maintenance_loop())

    async def stop(self) -> None:
        """Properly stop the maintenance service."""
        if self._shutdown_event:
            self._shutdown_event.set()
        if self._maintenance_task:
            try:
                await asyncio.wait_for(self._maintenance_task, timeout=5.0)
            except asyncio.TimeoutError:
                logger.warning("Maintenance task did not finish in time")
                self._maintenance_task.cancel()
        await self._final_cleanup()

    async def _maintenance_loop(self) -> None:
        """Periodic maintenance loop."""
        while not (self._shutdown_event and self._shutdown_event.is_set()):
            try:
                if self._shutdown_event:
                    await asyncio.wait_for(
                        self._shutdown_event.wait(),
                        timeout=3600  # Run every hour
                    )
                else:
                    await asyncio.sleep(3600)  # Run every hour
            except asyncio.TimeoutError:
                await self._perform_periodic_maintenance()

    async def _perform_periodic_maintenance(self) -> None:
        """Run periodic maintenance tasks."""
        logger.info("Periodic maintenance tasks executed.")

    async def _final_cleanup(self) -> None:
        """Final cleanup before shutdown."""
        logger.info("Final maintenance cleanup executed.")

    async def perform_startup_cleanup(self, time_service: Optional[TimeServiceProtocol] = None) -> None:
        """
        Performs database cleanup at startup:
        1. Removes orphaned active tasks and thoughts.
        2. Archives tasks and thoughts older than the configured threshold.
        3. Cleans up thoughts with invalid context.
        Logs actions taken.
        """
        # Use provided time_service or fallback to instance time_service
        ts = time_service or self.time_service
        logger.info("--- Starting Startup Database Cleanup ---")
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # --- Clean up thoughts with invalid/malformed context ---
        await self._cleanup_invalid_thoughts()

        # --- 0. Cleanup Incomplete Wakeup Steps from Previous Runs ---
        WAKEUP_ROOT_TASK_ID = "WAKEUP_ROOT" # Define if not already available class-wide
        stale_wakeup_steps_failed_count = 0
        stale_wakeup_thoughts_failed_count = 0

        all_tasks = get_all_tasks()  # Assuming a function to get all tasks
        wakeup_step_tasks = [t for t in all_tasks if t.parent_task_id == WAKEUP_ROOT_TASK_ID]

        for step_task in wakeup_step_tasks:
            if step_task.status not in [TaskStatus.COMPLETED, TaskStatus.FAILED]: # Removed TaskStatus.ARCHIVED
                logger.info(f"Found stale, non-terminal wakeup step task: {step_task.task_id} ('{step_task.description}') with status {step_task.status}. Marking as FAILED.")
                update_task_status(step_task.task_id, TaskStatus.FAILED, self.time_service)
                stale_wakeup_steps_failed_count += 1

                step_thoughts = get_thoughts_by_task_id(step_task.task_id)
                for thought in step_thoughts:
                    if thought.status not in [ThoughtStatus.COMPLETED, ThoughtStatus.FAILED, ThoughtStatus.DEFERRED, ThoughtStatus.COMPLETED]:
                        logger.info(f"Marking thought {thought.thought_id} (for stale step {step_task.task_id}) as FAILED.")
                        update_thought_status(
                            thought.thought_id,
                            ThoughtStatus.FAILED,
                            final_action={"status": "Task marked stale by maintenance"},
                        )
                        stale_wakeup_thoughts_failed_count += 1

        if stale_wakeup_steps_failed_count > 0 or stale_wakeup_thoughts_failed_count > 0:
            logger.info(f"Startup cleanup: Marked {stale_wakeup_steps_failed_count} stale wakeup step tasks and {stale_wakeup_thoughts_failed_count} related thoughts as FAILED.")

        # --- 1. Remove orphaned active tasks and thoughts ---
        orphaned_tasks_deleted_count = 0
        orphaned_thoughts_deleted_count = 0

        active_tasks = get_tasks_by_status(TaskStatus.ACTIVE)
        task_ids_to_delete: List[Any] = []

        for task in active_tasks:
            if not hasattr(task, 'task_id'):
                logger.error(f"Item in active_tasks is not a Task object, it's a {type(task)}: {task}")
                continue # Skip this item

            is_orphan = False
            if task.task_id in self.valid_root_task_ids and task.parent_task_id is None:
                pass # Allowed active root tasks
            elif task.task_id.startswith("shutdown_") and task.parent_task_id is None:
                pass # Shutdown tasks are valid root tasks
            elif task.parent_task_id:
                parent_task = get_task_by_id(task.parent_task_id)
                if not parent_task or parent_task.status not in [TaskStatus.ACTIVE, TaskStatus.COMPLETED]:
                    is_orphan = True
            elif task.task_id not in self.valid_root_task_ids:
                logger.info(f"Task {task.task_id} ('{task.description}') is active but not a recognized root task. Marking as orphaned.")
                is_orphan = True

            if is_orphan:
                logger.info(f"Orphaned active task found: {task.task_id} ('{task.description}'). Parent missing or not active/completed. Marking for deletion.")
                task_ids_to_delete.append(task.task_id)

        if task_ids_to_delete:
            orphaned_tasks_deleted_count = delete_tasks_by_ids(task_ids_to_delete)
            logger.info(f"Deleted {orphaned_tasks_deleted_count} orphaned active tasks (and their thoughts via cascade).")

        pending_thoughts = get_thoughts_by_status(ThoughtStatus.PENDING)
        processing_thoughts = get_thoughts_by_status(ThoughtStatus.PROCESSING)
        all_potentially_orphaned_thoughts = pending_thoughts + processing_thoughts
        thought_ids_to_delete_orphan: List[Any] = []

        for thought in all_potentially_orphaned_thoughts:
            source_task = get_task_by_id(thought.source_task_id)
            if not source_task or source_task.status != TaskStatus.ACTIVE:
                logger.info(f"Orphaned thought found: {thought.thought_id} (Task: {thought.source_task_id} not found or not active). Marking for deletion.")
                thought_ids_to_delete_orphan.append(thought.thought_id)

        if thought_ids_to_delete_orphan:
            unique_thought_ids_to_delete = list(set(thought_ids_to_delete_orphan))
            count = delete_thoughts_by_ids(unique_thought_ids_to_delete)
            orphaned_thoughts_deleted_count += count
            logger.info(f"Deleted {count} additional orphaned active/processing thoughts.")

        logger.info(f"Orphan cleanup: {orphaned_tasks_deleted_count} tasks, {orphaned_thoughts_deleted_count} thoughts removed.")

        # --- 2. Archive tasks/thoughts older than configured hours ---
        archived_tasks_count = 0
        archived_thoughts_count = 0

        now = ts.now()
        archive_timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        older_than_timestamp = (now - timedelta(hours=self.archive_older_than_hours)).isoformat()

        tasks_to_archive = get_tasks_older_than(older_than_timestamp)
        task_ids_actually_archived_and_deleted = set()

        if tasks_to_archive:
            task_archive_file = self.archive_dir / f"archive_tasks_{archive_timestamp_str}.jsonl"
            task_ids_to_delete_for_archive: List[Any] = []
            with open(task_archive_file, "w") as f:
                for task in tasks_to_archive:
                    if task.task_id not in self.valid_root_task_ids:
                        f.write(task.model_dump_json() + "\n")
                        task_ids_to_delete_for_archive.append(task.task_id)

            if task_ids_to_delete_for_archive:
                archived_tasks_count = delete_tasks_by_ids(task_ids_to_delete_for_archive)
                task_ids_actually_archived_and_deleted.update(task_ids_to_delete_for_archive)
                logger.info(f"Archived and deleted {archived_tasks_count} tasks older than {self.archive_older_than_hours} hours to {task_archive_file}.")
            else:
                logger.info(f"No non-essential tasks older than {self.archive_older_than_hours} hours to archive.")
        else:
            logger.info(f"No tasks older than {self.archive_older_than_hours} hours found for archiving.")

        thoughts_to_archive = get_thoughts_older_than(older_than_timestamp)
        if thoughts_to_archive:
            thought_archive_file = self.archive_dir / f"archive_thoughts_{archive_timestamp_str}.jsonl"
            thought_ids_to_delete_for_archive: List[Any] = []

            with open(thought_archive_file, "w") as f:
                for thought in thoughts_to_archive:
                    if thought.source_task_id in task_ids_actually_archived_and_deleted:
                        f.write(thought.model_dump_json() + "\n")
                        thought_ids_to_delete_for_archive.append(thought.thought_id)

            if thought_ids_to_delete_for_archive:
                archived_thoughts_count = delete_thoughts_by_ids(thought_ids_to_delete_for_archive)
                logger.info(f"Archived and deleted {archived_thoughts_count} thoughts (linked to archived tasks) older than {self.archive_older_than_hours} hours to {thought_archive_file}.")
            else:
                logger.info(f"No thoughts (linked to archivable tasks) older than {self.archive_older_than_hours} hours to archive.")
        else:
            logger.info(f"No thoughts older than {self.archive_older_than_hours} hours found for archiving.")

        logger.info(f"Archival: {archived_tasks_count} tasks, {archived_thoughts_count} thoughts archived and removed.")
        logger.info("--- Finished Startup Database Cleanup ---")

    async def _cleanup_invalid_thoughts(self) -> None:
        """Clean up thoughts with invalid or malformed context."""
        from ciris_engine.logic.persistence import get_db_connection

        logger.info("Cleaning up thoughts with invalid context...")

        # Get all thoughts with empty or invalid context
        sql = """
            SELECT thought_id, context_json
            FROM thoughts
            WHERE context_json = '{}'
               OR context_json IS NULL
               OR context_json NOT LIKE '%task_id%'
               OR context_json NOT LIKE '%correlation_id%'
        """

        invalid_thought_ids = []

        try:
            with get_db_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(sql)
                rows = cursor.fetchall()

                for row in rows:
                    invalid_thought_ids.append(row["thought_id"])

                if invalid_thought_ids:
                    # Delete these invalid thoughts
                    placeholders = ",".join("?" * len(invalid_thought_ids))
                    delete_sql = f"DELETE FROM thoughts WHERE thought_id IN ({placeholders})"
                    cursor.execute(delete_sql, invalid_thought_ids)
                    conn.commit()

                    logger.info(f"Deleted {len(invalid_thought_ids)} thoughts with invalid context")
                else:
                    logger.info("No thoughts with invalid context found")

        except Exception as e:
            logger.error(f"Failed to clean up invalid thoughts: {e}", exc_info=True)
