import logging
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import aiofiles

if TYPE_CHECKING:
    from ciris_engine.schemas.services.core import ServiceCapabilities

from ciris_engine.constants import UTC_TIMEZONE_SUFFIX
from ciris_engine.logic.persistence import (
    delete_tasks_by_ids,
    delete_thoughts_by_ids,
    get_all_tasks,
    get_task_by_id,
    get_tasks_by_status,
    get_thoughts_by_status,
    get_thoughts_by_task_id,
    get_thoughts_older_than,
)
from ciris_engine.logic.services.base_scheduled_service import BaseScheduledService
from ciris_engine.protocols.services.infrastructure.database_maintenance import DatabaseMaintenanceServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType, TaskStatus, ThoughtStatus

logger = logging.getLogger(__name__)


class DatabaseMaintenanceService(BaseScheduledService, DatabaseMaintenanceServiceProtocol):
    """
    Service for performing database maintenance tasks like cleanup and archiving.
    """

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        archive_dir_path: str = "data_archive",
        archive_older_than_hours: int = 24,
        config_service: Optional[Any] = None,
    ) -> None:
        # Initialize BaseScheduledService with hourly maintenance interval
        super().__init__(time_service=time_service, run_interval_seconds=3600)  # Run every hour
        self.time_service = time_service
        self.archive_dir = Path(archive_dir_path)
        self.archive_older_than_hours = archive_older_than_hours
        self.config_service = config_service

        # Tracking variables for metrics
        self._cleanup_runs = 0
        self._records_deleted = 0
        self._vacuum_runs = 0
        self._archive_runs = 0
        self._last_cleanup_duration = 0.0
        self._start_time = time_service.now()

    async def _run_scheduled_task(self) -> None:
        """
        Execute scheduled maintenance tasks.

        This is called periodically by BaseScheduledService.
        """
        await self._perform_periodic_maintenance()

    async def _perform_periodic_maintenance(self) -> None:
        """Run periodic maintenance tasks."""
        logger.info("Periodic maintenance tasks executed.")
        # Increment vacuum operations counter for periodic maintenance
        self._vacuum_runs += 1
        # The actual maintenance logic would go here
        # For now, this is a placeholder

    async def _on_stop(self) -> None:
        """Stop hook for cleanup."""
        await self._final_cleanup()

    async def _final_cleanup(self) -> None:
        """Final cleanup before shutdown."""
        logger.info("Final maintenance cleanup executed.")

    def _get_archive_size_mb(self) -> float:
        """Calculate archive directory size in MB."""
        if not self.archive_dir.exists():
            return 0.0
        total_size = sum(f.stat().st_size for f in self.archive_dir.rglob("*") if f.is_file())
        return total_size / (1024 * 1024)

    def _time_until_next_run(self) -> int:
        """Calculate seconds until next scheduled run."""
        if hasattr(self, "_next_run_time") and self._next_run_time:
            delta = (self._next_run_time - self.time_service.now()).total_seconds()
            return max(0, int(delta))
        return 0

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
        logger.info("Starting database cleanup")
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # --- Clean up thoughts with invalid/malformed context ---
        await self._cleanup_invalid_thoughts()

        # --- Clean up runtime-specific configuration from previous runs ---
        await self._cleanup_runtime_config()

        # --- Clean up stale wakeup tasks from interrupted startups ---
        await self._cleanup_stale_wakeup_tasks()

        # --- Clean up old active tasks from previous runs ---
        await self._cleanup_old_active_tasks()

        # --- 1. Remove orphaned active tasks and thoughts ---
        orphaned_tasks_deleted_count = 0
        orphaned_thoughts_deleted_count = 0

        active_tasks = get_tasks_by_status(TaskStatus.ACTIVE)
        task_ids_to_delete: List[Any] = []

        for task in active_tasks:
            if not hasattr(task, "task_id"):
                logger.error(f"Item in active_tasks is not a Task object, it's a {type(task)}: {task}")
                continue  # Skip this item

            is_orphan = False
            if task.task_id.startswith("shutdown_") and task.parent_task_id is None:
                pass  # Shutdown tasks are valid root tasks
            elif task.parent_task_id:
                parent_task = get_task_by_id(task.parent_task_id)
                if not parent_task or parent_task.status not in [TaskStatus.ACTIVE, TaskStatus.COMPLETED]:
                    is_orphan = True
            elif task.parent_task_id is None:
                # Root tasks without parents are allowed
                pass

            if is_orphan:
                logger.info(
                    f"Orphaned active task found: {task.task_id} ('{task.description}'). Parent missing or not active/completed. Marking for deletion."
                )
                task_ids_to_delete.append(task.task_id)

        if task_ids_to_delete:
            orphaned_tasks_deleted_count = delete_tasks_by_ids(task_ids_to_delete)
            logger.info(
                f"Deleted {orphaned_tasks_deleted_count} orphaned active tasks (and their thoughts via cascade)."
            )

        pending_thoughts = get_thoughts_by_status(ThoughtStatus.PENDING)
        processing_thoughts = get_thoughts_by_status(ThoughtStatus.PROCESSING)
        all_potentially_orphaned_thoughts = pending_thoughts + processing_thoughts
        thought_ids_to_delete_orphan: List[Any] = []

        for thought in all_potentially_orphaned_thoughts:
            source_task = get_task_by_id(thought.source_task_id)
            if not source_task or source_task.status != TaskStatus.ACTIVE:
                logger.info(
                    f"Orphaned thought found: {thought.thought_id} (Task: {thought.source_task_id} not found or not active). Marking for deletion."
                )
                thought_ids_to_delete_orphan.append(thought.thought_id)

        if thought_ids_to_delete_orphan:
            unique_thought_ids_to_delete = list(set(thought_ids_to_delete_orphan))
            count = delete_thoughts_by_ids(unique_thought_ids_to_delete)
            orphaned_thoughts_deleted_count += count
            logger.info(f"Deleted {count} additional orphaned active/processing thoughts.")

        logger.info(
            f"Orphan cleanup: {orphaned_tasks_deleted_count} tasks, {orphaned_thoughts_deleted_count} thoughts removed."
        )

        # Increment cleanup operations counter
        self._cleanup_runs += 1

        # --- 2. Archive thoughts older than configured hours ---
        # Tasks are now managed by TSDB consolidator, not archived here
        archived_tasks_count = 0
        archived_thoughts_count = 0

        now = ts.now()
        archive_timestamp_str = now.strftime("%Y%m%d_%H%M%S")
        older_than_timestamp = (now - timedelta(hours=self.archive_older_than_hours)).isoformat()

        # Skip task archival - handled by TSDB consolidator
        logger.info("Task archival skipped - tasks are now managed by TSDB consolidator")
        task_ids_actually_archived_and_deleted: set[str] = set()

        thoughts_to_archive = get_thoughts_older_than(older_than_timestamp)
        if thoughts_to_archive:
            thought_archive_file = self.archive_dir / f"archive_thoughts_{archive_timestamp_str}.jsonl"
            thought_ids_to_delete_for_archive: List[Any] = []

            async with aiofiles.open(thought_archive_file, "w") as f:
                for thought in thoughts_to_archive:
                    # Archive all thoughts older than threshold
                    await f.write(thought.model_dump_json() + "\n")
                    thought_ids_to_delete_for_archive.append(thought.thought_id)

            if thought_ids_to_delete_for_archive:
                archived_thoughts_count = delete_thoughts_by_ids(thought_ids_to_delete_for_archive)
                logger.info(
                    f"Archived and deleted {archived_thoughts_count} thoughts older than {self.archive_older_than_hours} hours to {thought_archive_file}."
                )
            else:
                logger.info(f"No thoughts older than {self.archive_older_than_hours} hours to archive.")
        else:
            logger.info(f"No thoughts older than {self.archive_older_than_hours} hours found for archiving.")

        logger.info(f"Archival: {archived_tasks_count} tasks, {archived_thoughts_count} thoughts archived and removed.")
        logger.info("Database cleanup completed")

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
                    delete_sql = f"DELETE FROM thoughts WHERE thought_id IN ({placeholders})"  # nosec B608 - placeholders are '?' strings, not user input
                    cursor.execute(delete_sql, invalid_thought_ids)
                    conn.commit()

                    logger.info(f"Deleted {len(invalid_thought_ids)} thoughts with invalid context")
                else:
                    logger.info("No thoughts with invalid context found")

        except Exception as e:
            logger.error(f"Failed to clean up invalid thoughts: {e}", exc_info=True)

    async def _cleanup_runtime_config(self) -> None:
        """Clean up runtime-specific configuration from previous runs."""
        try:
            # Use injected config service
            if not self.config_service:
                logger.warning("Cannot clean up runtime config - config service not available")
                return

            # Get all config entries
            all_configs = await self.config_service.list_configs()

            runtime_config_patterns = [
                "adapter.",  # Adapter configurations
                "runtime.",  # Runtime-specific settings
                "session.",  # Session-specific data
                "temp.",  # Temporary configurations
            ]

            deleted_count = 0

            for key, value in all_configs.items():
                # Check if this is a runtime-specific config
                is_runtime_config = any(key.startswith(pattern) for pattern in runtime_config_patterns)

                if is_runtime_config:
                    # Get the actual config node to check if it should be deleted
                    config_node = await self.config_service.get_config(key)
                    if config_node:
                        # Skip configs created by system_bootstrap (essential configs)
                        if config_node.updated_by == "system_bootstrap":
                            logger.debug(f"Preserving bootstrap config: {key}")
                            continue

                        # Convert to GraphNode and use memory service to forget it
                        graph_node = config_node.to_graph_node()
                        await self.config_service.graph.forget(graph_node)
                        deleted_count += 1
                        logger.debug(f"Deleted runtime config node: {key}")

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} runtime-specific configuration entries from previous runs")
            else:
                logger.info("No runtime-specific configuration entries to clean up")

        except Exception as e:
            logger.error(f"Failed to clean up runtime config: {e}", exc_info=True)

    async def _cleanup_old_active_tasks(self) -> None:
        """Mark old active tasks from previous runs as completed."""
        try:
            from ciris_engine.logic.persistence import update_task_status

            logger.info("Checking for old active tasks from previous runs")

            # Get current time
            current_time = self.time_service.now()

            # Get all active tasks
            active_tasks = get_tasks_by_status(TaskStatus.ACTIVE)
            old_task_ids = []

            for task in active_tasks:
                if not hasattr(task, "task_id"):
                    continue

                # Skip wakeup and shutdown tasks (handled by _cleanup_stale_wakeup_tasks)
                if (
                    task.task_id.startswith("WAKEUP_")
                    or task.task_id.startswith("VERIFY_IDENTITY_")
                    or task.task_id.startswith("VALIDATE_INTEGRITY_")
                    or task.task_id.startswith("EVALUATE_RESILIENCE_")
                    or task.task_id.startswith("ACCEPT_INCOMPLETENESS_")
                    or task.task_id.startswith("EXPRESS_GRATITUDE_")
                    or task.task_id.startswith("shutdown_")
                ):
                    continue

                # Check task age
                if isinstance(task.created_at, str):
                    from datetime import datetime

                    task_created = datetime.fromisoformat(task.created_at.replace("Z", UTC_TIMEZONE_SUFFIX))
                else:
                    task_created = task.created_at

                task_age = current_time - task_created
                # Mark tasks older than 5 minutes as completed
                is_old = task_age.total_seconds() > 300  # 5 minutes

                if is_old:
                    logger.info(
                        f"Found old active task from previous run: {task.task_id} (age: {task_age.total_seconds():.0f}s) - marking as completed"
                    )
                    old_task_ids.append(task.task_id)

            # Mark old tasks as completed
            if old_task_ids:
                for task_id in old_task_ids:
                    update_task_status(task_id, TaskStatus.COMPLETED, self.time_service)
                logger.info(f"Marked {len(old_task_ids)} old active tasks as completed")
            else:
                logger.info("No old active tasks found")

        except Exception as e:
            logger.error(f"Failed to clean up old active tasks: {e}", exc_info=True)

    async def _cleanup_stale_wakeup_tasks(self) -> None:
        """Clean up stale wakeup and shutdown thoughts from previous runs while preserving completed tasks for history."""
        try:
            logger.info("Checking for stale wakeup and shutdown tasks from previous runs")

            # Get current time for comparison
            current_time = self.time_service.now()

            # Get all wakeup and shutdown related tasks
            all_tasks = get_all_tasks()
            stale_tasks = []
            for task in all_tasks:
                if not hasattr(task, "task_id"):
                    continue
                # Check for wakeup and shutdown tasks by ID pattern
                if (
                    task.task_id.startswith("WAKEUP_")
                    or task.task_id.startswith("VERIFY_IDENTITY_")
                    or task.task_id.startswith("VALIDATE_INTEGRITY_")
                    or task.task_id.startswith("EVALUATE_RESILIENCE_")
                    or task.task_id.startswith("ACCEPT_INCOMPLETENESS_")
                    or task.task_id.startswith("EXPRESS_GRATITUDE_")
                    or task.task_id.startswith("shutdown_")
                ):
                    stale_tasks.append(task)

            # Clean up thoughts and interfering tasks from old wakeup runs
            stale_task_ids = []  # For PENDING/ACTIVE tasks that would interfere
            stale_thought_ids = []

            for task in stale_tasks:
                # Check if this task is from a previous run (more than 5 minutes old)
                # Convert string timestamp to datetime if needed
                if isinstance(task.created_at, str):
                    from datetime import datetime

                    task_created = datetime.fromisoformat(task.created_at.replace("Z", UTC_TIMEZONE_SUFFIX))
                else:
                    task_created = task.created_at

                task_age = current_time - task_created
                is_old_task = task_age.total_seconds() > 300  # 5 minutes

                if is_old_task:
                    # For old tasks, clean up any pending/processing thoughts
                    thoughts = get_thoughts_by_task_id(task.task_id)
                    for thought in thoughts:
                        if thought.status in [ThoughtStatus.PENDING, ThoughtStatus.PROCESSING]:
                            logger.info(
                                f"Found stale wakeup thought from old task {task.task_id}: {thought.thought_id} (status: {thought.status})"
                            )
                            stale_thought_ids.append(thought.thought_id)

                    # Delete old PENDING or ACTIVE tasks as they would interfere
                    if task.status in [TaskStatus.PENDING, TaskStatus.ACTIVE]:
                        logger.info(f"Found stale {task.status} wakeup task from previous run: {task.task_id}")
                        stale_task_ids.append(task.task_id)

            # Delete stale thoughts first
            if stale_thought_ids:
                deleted_thoughts = delete_thoughts_by_ids(stale_thought_ids)
                logger.info(f"Deleted {deleted_thoughts} stale wakeup thoughts from previous runs")

            # Then delete stale active tasks (only ACTIVE ones from interrupted startups)
            if stale_task_ids:
                deleted_tasks = delete_tasks_by_ids(stale_task_ids)
                logger.info(f"Deleted {deleted_tasks} stale active wakeup tasks from interrupted startups")

            if not stale_task_ids and not stale_thought_ids:
                logger.info("No stale wakeup tasks or thoughts found")

        except Exception as e:
            logger.error(f"Failed to clean up stale wakeup tasks: {e}", exc_info=True)

    def get_capabilities(self) -> "ServiceCapabilities":
        """Get service capabilities."""
        from ciris_engine.schemas.services.core import ServiceCapabilities

        return ServiceCapabilities(
            service_name="DatabaseMaintenanceService",
            actions=["cleanup", "archive", "maintenance"],
            version="1.0.0",
            dependencies=["TimeService"],
            metadata=None,
        )

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.MAINTENANCE

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return ["cleanup", "archive", "maintenance"]

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        return self.time_service is not None

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect database maintenance metrics."""
        metrics = super()._collect_custom_metrics()

        # Calculate database size
        db_size_mb = 0.0
        try:
            import os

            from ciris_engine.logic.persistence import get_sqlite_db_full_path

            db_path = get_sqlite_db_full_path()
            if os.path.exists(db_path):
                db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
        except (OSError, IOError, ImportError):
            # Ignore file system and import errors when checking database size
            pass

        metrics.update(
            {
                "cleanup_runs": float(self._cleanup_runs),
                "records_deleted": float(self._records_deleted),
                "vacuum_runs": float(self._vacuum_runs),
                "archive_runs": float(self._archive_runs),
                "database_size_mb": db_size_mb,
                "last_cleanup_duration_s": self._last_cleanup_duration,
                "cleanup_due": 1.0 if self._is_cleanup_due() else 0.0,
                "archive_due": 1.0 if self._is_archive_due() else 0.0,
            }
        )

        return metrics

    def _is_cleanup_due(self) -> bool:
        """Check if cleanup is due."""
        # Placeholder - implement based on schedule
        return False

    def _is_archive_due(self) -> bool:
        """Check if archive is due."""
        # Placeholder - implement based on schedule
        return False

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all database maintenance metrics including base, custom, and v1.4.3 specific.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()
        # Calculate database size
        db_size_mb = 0.0
        try:
            import os

            from ciris_engine.logic.persistence import get_sqlite_db_full_path

            db_path = get_sqlite_db_full_path()
            if os.path.exists(db_path):
                db_size_mb = os.path.getsize(db_path) / (1024 * 1024)
        except (OSError, IOError, ImportError):
            # Ignore file system and import errors when checking database size
            pass

        # Calculate uptime in seconds
        uptime_seconds = 0.0
        if hasattr(self, "_start_time") and self._start_time is not None:
            current_time = self.time_service.now()
            uptime_delta = current_time - self._start_time
            uptime_seconds = uptime_delta.total_seconds()

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "db_vacuum_operations": float(self._vacuum_runs),
                "db_cleanup_operations": float(self._cleanup_runs),
                "db_size_mb": db_size_mb,
                "db_maintenance_uptime_seconds": uptime_seconds,
            }
        )

        return metrics
