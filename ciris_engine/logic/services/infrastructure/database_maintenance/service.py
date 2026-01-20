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
        db_path: Optional[str] = None,
        bus_manager: Optional[Any] = None,
    ) -> None:
        # Initialize BaseScheduledService with hourly maintenance interval
        super().__init__(time_service=time_service, run_interval_seconds=3600)  # Run every hour
        self.time_service = time_service
        self.archive_dir = Path(archive_dir_path)
        self.archive_older_than_hours = archive_older_than_hours
        self.config_service = config_service
        self.db_path = db_path
        self.bus_manager = bus_manager

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
        """Run periodic maintenance tasks including stale task cleanup."""
        logger.info("Periodic maintenance tasks starting.")
        # Increment vacuum operations counter for periodic maintenance
        self._vacuum_runs += 1

        # Clean up stale wakeup/shutdown tasks from dead occurrences
        # This is critical for multi-occurrence deployments where an occurrence
        # may die mid-wakeup, leaving shared tasks in ACTIVE state forever
        await self._cleanup_stale_wakeup_tasks()

        # Clean up old active tasks that may have been orphaned
        await self._cleanup_old_active_tasks()

        logger.info("Periodic maintenance tasks completed.")

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
        from datetime import datetime, timedelta, timezone

        # Use provided time_service or fallback to instance time_service
        ts = time_service or self.time_service
        logger.info("Starting database cleanup")
        self.archive_dir.mkdir(parents=True, exist_ok=True)

        # --- Clean up thoughts with invalid/malformed context ---
        await self._cleanup_invalid_thoughts()

        # --- Clean up runtime-specific configuration from previous runs ---
        await self._cleanup_runtime_config()

        # --- Dedupe adapter configs with identical settings ---
        await self._dedupe_adapter_configs()

        # --- Clean up adapter configs without persist=True ---
        await self._cleanup_non_persistent_adapters()

        # --- Clean up stale wakeup tasks from interrupted startups ---
        await self._cleanup_stale_wakeup_tasks()

        # --- Clean up old active tasks from previous runs ---
        await self._cleanup_old_active_tasks()

        # --- Clean up duplicate temporal edges (v1.5.6 PostgreSQL bug) ---
        await self._cleanup_duplicate_temporal_edges()

        # --- 1. Remove orphaned active tasks and thoughts ---
        orphaned_tasks_deleted_count = 0
        orphaned_thoughts_deleted_count = 0

        active_tasks = get_tasks_by_status(TaskStatus.ACTIVE, db_path=self.db_path)
        task_ids_to_delete: List[Any] = []

        for task in active_tasks:
            if not hasattr(task, "task_id"):
                logger.error(f"Item in active_tasks is not a Task object, it's a {type(task)}: {task}")
                continue  # Skip this item

            # CRITICAL: Multi-occurrence race condition protection
            # Skip tasks created within last 2 minutes to prevent deleting tasks
            # created by another occurrence that just started up
            task_created_at = datetime.fromisoformat(task.created_at.replace("Z", "+00:00"))
            task_age = ts.now() - task_created_at
            if task_age < timedelta(minutes=2):
                logger.debug(
                    f"Skipping orphan check for recent task {task.task_id} (age: {task_age}). "
                    "Will check in next cleanup cycle if still orphaned."
                )
                continue

            is_orphan = False
            if task.task_id.startswith("shutdown_") and task.parent_task_id is None:
                pass  # Shutdown tasks are valid root tasks
            elif task.parent_task_id:
                # CRITICAL: Pass task's own occurrence_id to find parent in same namespace
                # This prevents shared tasks from being marked as orphans in multi-occurrence setups
                parent_task = get_task_by_id(task.parent_task_id, task.agent_occurrence_id, db_path=self.db_path)
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
            orphaned_tasks_deleted_count = delete_tasks_by_ids(task_ids_to_delete, db_path=self.db_path)
            logger.info(
                f"Deleted {orphaned_tasks_deleted_count} orphaned active tasks (and their thoughts via cascade)."
            )

        pending_thoughts = get_thoughts_by_status(ThoughtStatus.PENDING, db_path=self.db_path)
        processing_thoughts = get_thoughts_by_status(ThoughtStatus.PROCESSING, db_path=self.db_path)
        all_potentially_orphaned_thoughts = pending_thoughts + processing_thoughts
        thought_ids_to_delete_orphan: List[Any] = []

        for thought in all_potentially_orphaned_thoughts:
            # CRITICAL: Pass thought's own occurrence_id to find task in same namespace
            source_task = get_task_by_id(thought.source_task_id, thought.agent_occurrence_id, db_path=self.db_path)
            if not source_task or source_task.status != TaskStatus.ACTIVE:
                logger.info(
                    f"Orphaned thought found: {thought.thought_id} (Task: {thought.source_task_id} not found or not active). Marking for deletion."
                )
                thought_ids_to_delete_orphan.append(thought.thought_id)

        if thought_ids_to_delete_orphan:
            unique_thought_ids_to_delete = list(set(thought_ids_to_delete_orphan))
            count = delete_thoughts_by_ids(unique_thought_ids_to_delete, db_path=self.db_path)
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

        thoughts_to_archive = get_thoughts_older_than(older_than_timestamp, db_path=self.db_path)
        if thoughts_to_archive:
            thought_archive_file = self.archive_dir / f"archive_thoughts_{archive_timestamp_str}.jsonl"
            thought_ids_to_delete_for_archive: List[Any] = []

            async with aiofiles.open(thought_archive_file, "w") as f:
                for thought in thoughts_to_archive:
                    # Archive all thoughts older than threshold
                    await f.write(thought.model_dump_json() + "\n")
                    thought_ids_to_delete_for_archive.append(thought.thought_id)

            if thought_ids_to_delete_for_archive:
                archived_thoughts_count = delete_thoughts_by_ids(
                    thought_ids_to_delete_for_archive, db_path=self.db_path
                )
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
        from ciris_engine.logic.persistence.db.dialect import get_adapter

        logger.info("Cleaning up thoughts with invalid context...")

        # Get adapter to detect database type
        adapter = get_adapter()

        # Different SQL for PostgreSQL (JSONB) vs SQLite (TEXT)
        if adapter.is_postgresql():
            # PostgreSQL: Cast JSONB to text for LIKE operations
            sql = """
                SELECT thought_id, context_json
                FROM thoughts
                WHERE context_json::text = '{}'
                   OR context_json IS NULL
                   OR context_json::text NOT LIKE '%task_id%'
                   OR context_json::text NOT LIKE '%correlation_id%'
            """
        else:
            # SQLite: context_json is TEXT, use LIKE directly
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
            with get_db_connection(db_path=self.db_path) as conn:
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

    # Config patterns that should be cleaned up on startup (unless preserved)
    _RUNTIME_CONFIG_PATTERNS = ("adapter.", "runtime.", "session.", "temp.")

    def _should_preserve_config(self, key: str, config_node: Any) -> tuple[bool, str]:
        """Check if a config should be preserved during cleanup.

        Args:
            key: The config key
            config_node: The config node object with updated_by attribute

        Returns:
            Tuple of (should_preserve, reason) where reason is logged if preserved
        """
        # Preserve configs created by system_bootstrap (essential configs)
        if config_node.updated_by == "system_bootstrap":
            return True, f"Preserving bootstrap config: {key}"

        # Adapter configs are handled separately by _cleanup_non_persistent_adapters
        # This method doesn't need to check them - they're deleted based on persist flag
        if key.startswith("adapter.") and config_node.updated_by == "runtime_adapter_manager":
            # Don't delete here - let _cleanup_non_persistent_adapters handle it
            return True, f"Adapter config handled by persist check: {key}"

        return False, ""

    async def _cleanup_runtime_config(self) -> None:
        """Clean up runtime-specific configuration from previous runs."""
        if not self.config_service:
            logger.warning("Cannot clean up runtime config - config service not available")
            return

        try:
            all_configs = await self.config_service.list_configs()
            deleted_count = await self._delete_ephemeral_configs(all_configs)
            self._log_cleanup_result(deleted_count)
        except Exception as e:
            logger.error(f"Failed to clean up runtime config: {e}", exc_info=True)

    async def _delete_ephemeral_configs(self, all_configs: Dict[str, Any]) -> int:
        """Delete ephemeral configs that should not persist across restarts.

        Args:
            all_configs: Dictionary of all config entries

        Returns:
            Count of deleted configs

        Note: Caller must ensure config_service is not None before calling.
        """
        assert self.config_service is not None  # Guaranteed by caller
        deleted_count = 0

        for key in all_configs:
            if not self._is_runtime_config(key):
                continue

            config_node = await self.config_service.get_config(key)
            if not config_node:
                continue

            should_preserve, reason = self._should_preserve_config(key, config_node)
            if should_preserve:
                logger.debug(reason)
                continue

            # Delete the ephemeral config
            graph_node = config_node.to_graph_node()
            await self.config_service.graph.forget(graph_node)
            deleted_count += 1
            logger.debug(f"Deleted runtime config node: {key}")

        return deleted_count

    def _is_runtime_config(self, key: str) -> bool:
        """Check if a config key matches runtime config patterns."""
        return any(key.startswith(pattern) for pattern in self._RUNTIME_CONFIG_PATTERNS)

    def _log_cleanup_result(self, deleted_count: int) -> None:
        """Log the result of config cleanup."""
        if deleted_count > 0:
            logger.info(f"Cleaned up {deleted_count} runtime-specific configuration entries from previous runs")
        else:
            logger.info("No runtime-specific configuration entries to clean up")

    async def _dedupe_adapter_configs(self) -> None:
        """Remove duplicate adapter configs with identical settings.

        When the same adapter type is loaded multiple times with the same config,
        this creates duplicate entries (adapter.{id1}.*, adapter.{id2}.*, etc.).
        This method keeps only the newest entry per (adapter_type, occurrence_id, config_hash).

        Adapters with DIFFERENT configs are preserved (valid multi-instance use case).
        """
        import hashlib
        import json

        if not self.config_service:
            logger.debug("Cannot dedupe adapter configs - config service not available")
            return

        try:
            all_configs = await self.config_service.list_configs(prefix="adapter.")
            if not all_configs:
                return

            # Find all adapter.*.type entries to identify adapter instances
            adapter_instances: Dict[str, Dict[str, Any]] = {}
            for key in all_configs:
                if key.endswith(".type") and key.startswith("adapter."):
                    # Extract adapter_id from "adapter.{adapter_id}.type"
                    parts = key.split(".")
                    if len(parts) == 3:
                        adapter_id = parts[1]
                        adapter_instances[adapter_id] = {"type_key": key}

            if not adapter_instances:
                return

            # Fetch full details for each adapter instance
            for adapter_id, info in adapter_instances.items():
                type_node = await self.config_service.get_config(f"adapter.{adapter_id}.type")
                config_node = await self.config_service.get_config(f"adapter.{adapter_id}.config")
                occurrence_node = await self.config_service.get_config(f"adapter.{adapter_id}.occurrence_id")

                info["adapter_type"] = self._extract_config_value(type_node)
                info["config"] = self._extract_config_value(config_node)
                info["occurrence_id"] = self._extract_config_value(occurrence_node) or "default"
                info["created_at"] = getattr(type_node, "created_at", None) if type_node else None

                # Hash the config for comparison
                config_str = json.dumps(info["config"], sort_keys=True) if info["config"] else ""
                info["config_hash"] = hashlib.sha256(config_str.encode()).hexdigest()[:16]

            # Group by (adapter_type, occurrence_id, config_hash)
            # Same config on different occurrences is valid (not a duplicate)
            # Duplicates are: same type + same occurrence + same config (different adapter_id with UUID)
            groups: Dict[tuple[str, str, str], List[str]] = {}
            for adapter_id, info in adapter_instances.items():
                if not info.get("adapter_type"):
                    continue
                group_key = (info["adapter_type"], info["occurrence_id"], info["config_hash"])
                if group_key not in groups:
                    groups[group_key] = []
                groups[group_key].append(adapter_id)

            # For each group with duplicates, keep newest, delete rest
            deleted_count = 0
            for group_key, adapter_ids in groups.items():
                if len(adapter_ids) <= 1:
                    continue

                # Sort by created_at descending (newest first)
                adapter_ids_sorted = sorted(
                    adapter_ids,
                    key=lambda aid: adapter_instances[aid].get("created_at") or "",
                    reverse=True,
                )

                # Keep the first (newest), delete the rest
                to_delete = adapter_ids_sorted[1:]
                adapter_type, occurrence_id, _ = group_key

                for adapter_id in to_delete:
                    await self._delete_adapter_config_entries(adapter_id)
                    deleted_count += 1
                    logger.info(
                        f"Deleted duplicate adapter config: {adapter_id} "
                        f"(type={adapter_type}, occurrence={occurrence_id})"
                    )

            if deleted_count > 0:
                logger.info(f"Deduped {deleted_count} duplicate adapter config(s)")

        except Exception as e:
            logger.error(f"Error deduping adapter configs: {e}", exc_info=True)

    async def _cleanup_non_persistent_adapters(self) -> None:
        """Remove adapter configs that don't have persist=True.

        On startup, delete adapter configs that were not marked for persistence.
        Only adapters with adapter.{adapter_id}.persist = True survive restart.
        """
        if not self.config_service:
            logger.debug("Cannot cleanup non-persistent adapters - config service not available")
            return

        try:
            all_configs = await self.config_service.list_configs(prefix="adapter.")
            if not all_configs:
                return

            # Find all adapter.*.type entries to identify adapter instances
            adapter_ids: set[str] = set()
            for key in all_configs:
                if key.endswith(".type") and key.startswith("adapter."):
                    parts = key.split(".")
                    if len(parts) == 3:
                        adapter_ids.add(parts[1])

            if not adapter_ids:
                return

            deleted_count = 0
            for adapter_id in adapter_ids:
                # Check if this adapter has persist=True
                persist_node = await self.config_service.get_config(f"adapter.{adapter_id}.persist")
                persist_value = self._extract_config_value(persist_node)

                if persist_value is True:
                    logger.debug(f"Adapter {adapter_id} marked for persistence, keeping")
                    continue

                # Not marked for persistence - delete all config entries for this adapter
                logger.info(f"Deleting non-persistent adapter config: {adapter_id}")
                await self._delete_adapter_config_entries(adapter_id)
                deleted_count += 1

            if deleted_count > 0:
                logger.info(f"Cleaned up {deleted_count} non-persistent adapter config(s)")

        except Exception as e:
            logger.error(f"Error cleaning up non-persistent adapters: {e}", exc_info=True)

    def _extract_config_value(self, config_node: Any) -> Any:
        """Extract the actual value from a ConfigNode."""
        if config_node is None:
            return None
        if hasattr(config_node, "value"):
            val = config_node.value
            # Handle ConfigValue typed structure
            if hasattr(val, "string_value") and val.string_value is not None:
                return val.string_value
            if hasattr(val, "dict_value") and val.dict_value is not None:
                return val.dict_value
            if hasattr(val, "int_value") and val.int_value is not None:
                return val.int_value
            if hasattr(val, "bool_value") and val.bool_value is not None:
                return val.bool_value
            if hasattr(val, "list_value") and val.list_value is not None:
                return val.list_value
            if hasattr(val, "float_value") and val.float_value is not None:
                return val.float_value
            return val
        return config_node

    async def _delete_adapter_config_entries(self, adapter_id: str) -> None:
        """Delete all config entries for an adapter instance."""
        if not self.config_service:
            return

        keys_to_delete = [
            f"adapter.{adapter_id}.type",
            f"adapter.{adapter_id}.config",
            f"adapter.{adapter_id}.occurrence_id",
        ]

        # Also find any additional keys like adapter.{id}.{setting}
        all_configs = await self.config_service.list_configs(prefix=f"adapter.{adapter_id}.")
        for key in all_configs:
            if key not in keys_to_delete:
                keys_to_delete.append(key)

        for key in keys_to_delete:
            try:
                config_node = await self.config_service.get_config(key)
                if config_node:
                    graph_node = config_node.to_graph_node()
                    await self.config_service.graph.forget(graph_node)
            except Exception as e:
                logger.debug(f"Could not delete config {key}: {e}")

    async def _cleanup_old_active_tasks(self) -> None:
        """Mark old active tasks from previous runs as completed."""
        try:
            from ciris_engine.logic.persistence import update_task_status

            logger.info("Checking for old PENDING/ACTIVE tasks from previous runs")

            # Get current time
            current_time = self.time_service.now()

            # Get all active tasks from all occurrences by querying the database directly
            # We need to check ALL occurrences for old active tasks
            from ciris_engine.logic.persistence import get_db_connection

            # Check both PENDING and ACTIVE tasks - PENDING tasks that are old
            # indicate messages that were received but never processed
            stale_tasks = []
            with get_db_connection(db_path=self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT * FROM tasks WHERE status IN (?, ?)",
                    (TaskStatus.PENDING.value, TaskStatus.ACTIVE.value),
                )
                rows = cursor.fetchall()
                from ciris_engine.logic.persistence.utils import map_row_to_task

                for row in rows:
                    stale_tasks.append(map_row_to_task(row))

            old_task_ids = []

            for task in stale_tasks:
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

            # Mark old tasks as completed and notify channels
            if old_task_ids:
                for task in stale_tasks:
                    if task.task_id in old_task_ids:
                        # CRITICAL: Use task's own occurrence_id, not hardcoded "default"
                        update_task_status(
                            task.task_id,
                            TaskStatus.COMPLETED,
                            task.agent_occurrence_id,
                            self.time_service,
                            db_path=self.db_path,
                        )
                        # Send notification to the channel that the task was auto-completed
                        await self._notify_stale_task_completed(task)
                logger.info(f"Marked {len(old_task_ids)} old active tasks as completed")
            else:
                logger.info("No old PENDING/ACTIVE tasks found")

        except Exception as e:
            logger.error(f"Failed to clean up old active tasks: {e}", exc_info=True)

    async def _notify_stale_task_completed(self, task: Any) -> None:
        """Send a notification to the channel that a stale task was auto-completed due to restart."""
        if not self.bus_manager:
            logger.debug("No bus_manager available - skipping stale task notification")
            return

        channel_id = getattr(task, "channel_id", None)
        if not channel_id:
            logger.debug(f"Task {task.task_id} has no channel_id - skipping notification")
            return

        # Skip internal/system channels
        if channel_id.startswith("__") or channel_id == "system":
            return

        try:
            msg = (
                "I was restarted while processing your request. "
                "The previous task was auto-completed. Please resend your message if you still need a response."
            )
            await self.bus_manager.communication.send_message_sync(
                channel_id=channel_id,
                content=msg,
                handler_name="DatabaseMaintenanceService",
            )
            logger.info(f"Sent stale task notification to channel {channel_id}")
        except Exception as e:
            logger.warning(f"Failed to send stale task notification to {channel_id}: {e}")

    async def _cleanup_stale_wakeup_tasks(self) -> None:
        """
        Clean up stale wakeup and shutdown thoughts from previous runs while preserving completed tasks for history.

        This prevents infinite loops where old PENDING/ACTIVE shutdown tasks with completed thoughts
        get reused on restart, causing the shutdown processor to wait forever for an LLM response.
        """
        try:
            logger.info("Checking for stale wakeup and shutdown tasks from previous runs")

            # Get current time for comparison
            current_time = self.time_service.now()

            # Get all wakeup and shutdown related tasks from __shared__ occurrence
            # Wakeup tasks are always in the shared namespace
            all_tasks = get_all_tasks("__shared__", db_path=self.db_path)
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
                    or task.task_id.startswith("SHUTDOWN_")  # Also match uppercase SHUTDOWN_ tasks
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
                    # CRITICAL: Pass task's occurrence_id to fetch thoughts in same namespace
                    thoughts = get_thoughts_by_task_id(task.task_id, task.agent_occurrence_id, db_path=self.db_path)
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
                deleted_thoughts = delete_thoughts_by_ids(stale_thought_ids, db_path=self.db_path)
                logger.info(f"Deleted {deleted_thoughts} stale wakeup thoughts from previous runs")

            # Then delete stale active tasks (only ACTIVE ones from interrupted startups)
            if stale_task_ids:
                deleted_tasks = delete_tasks_by_ids(stale_task_ids, db_path=self.db_path)
                logger.info(f"Deleted {deleted_tasks} stale active wakeup tasks from interrupted startups")

            if not stale_task_ids and not stale_thought_ids:
                logger.info("No stale wakeup tasks or thoughts found")

        except Exception as e:
            logger.error(f"Failed to clean up stale wakeup tasks: {e}", exc_info=True)

    async def _cleanup_duplicate_temporal_edges(self) -> None:
        """
        Clean up duplicate temporal edges created by v1.5.5 PostgreSQL bug.

        Bug: edge_manager.py used hardcoded ? placeholders instead of adapter.placeholder(),
        causing DELETE and INSERT to fail on PostgreSQL, creating duplicate TEMPORAL_NEXT
        and TEMPORAL_PREV edges.

        This cleanup:
        1. Finds summaries with multiple TEMPORAL_NEXT/PREV edges
        2. Keeps only the most recent edge for each relationship type
        3. Deletes older duplicates

        Safe to run multiple times - idempotent.
        """
        try:
            from ciris_engine.logic.persistence.db.core import get_db_connection
            from ciris_engine.logic.persistence.db.dialect import get_adapter

            logger.info("Checking for duplicate temporal edges from v1.5.5 PostgreSQL bug")

            with get_db_connection(db_path=self.db_path) as conn:
                # CRITICAL: Get adapter AFTER opening connection to ensure dialect is initialized
                # for the correct database backend (PostgreSQL vs SQLite)
                adapter = get_adapter()
                ph = adapter.placeholder()
                cursor = conn.cursor()

                # Find summaries with duplicate temporal edges
                cursor.execute(
                    f"""
                    SELECT source_node_id, relationship, COUNT(*) as edge_count
                    FROM graph_edges
                    WHERE relationship IN ('TEMPORAL_NEXT', 'TEMPORAL_PREV')
                    GROUP BY source_node_id, relationship
                    HAVING COUNT(*) > 1
                    ORDER BY edge_count DESC
                """
                )

                duplicates = cursor.fetchall()

                if not duplicates:
                    logger.info("No duplicate temporal edges found")
                    return

                total_duplicates_deleted = 0
                logger.info(f"Found {len(duplicates)} summaries with duplicate temporal edges")

                for row in duplicates:
                    if adapter.is_postgresql():
                        source_id, relationship, count = row["source_node_id"], row["relationship"], row["edge_count"]
                    else:
                        source_id, relationship, count = row[0], row[1], row[2]

                    logger.info(f"  {source_id} has {count} duplicate {relationship} edges")

                    # Get all edges for this source + relationship, ordered by created_at DESC
                    cursor.execute(
                        f"""
                        SELECT edge_id, created_at
                        FROM graph_edges
                        WHERE source_node_id = {ph}
                          AND relationship = {ph}
                        ORDER BY created_at DESC
                    """,
                        (source_id, relationship),
                    )

                    edges = cursor.fetchall()

                    if len(edges) <= 1:
                        continue  # No duplicates to clean

                    # Keep the first (most recent), delete the rest
                    edges_to_delete = []
                    for i, edge_row in enumerate(edges):
                        if i == 0:
                            continue  # Keep first edge
                        if adapter.is_postgresql():
                            edges_to_delete.append(edge_row["edge_id"])
                        else:
                            edges_to_delete.append(edge_row[0])

                    if edges_to_delete:
                        # Delete duplicate edges
                        placeholders = ",".join([ph] * len(edges_to_delete))
                        cursor.execute(
                            f"""
                            DELETE FROM graph_edges
                            WHERE edge_id IN ({placeholders})
                        """,
                            edges_to_delete,
                        )

                        deleted = cursor.rowcount
                        total_duplicates_deleted += deleted
                        logger.info(f"    Deleted {deleted} duplicate {relationship} edges from {source_id}")

                conn.commit()

                if total_duplicates_deleted > 0:
                    logger.info(f"✓ Cleaned up {total_duplicates_deleted} duplicate temporal edges from PostgreSQL bug")

        except Exception as e:
            logger.error(f"Failed to clean up duplicate temporal edges: {e}", exc_info=True)

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

    async def migrate_audit_key_to_ed25519(self, backup: bool = True) -> Dict[str, Any]:
        """Migrate audit signing key from RSA-2048 to Ed25519.

        This is a one-time migration operation that:
        1. Creates a backup of the current state
        2. Generates or uses unified Ed25519 key
        3. Re-signs the entire audit chain
        4. Verifies chain integrity
        5. Archives the old RSA key

        Args:
            backup: Create backup before migration (recommended)

        Returns:
            Dict with migration result details
        """
        from ciris_engine.logic.audit import migrate_audit_key_to_ed25519

        logger.info("=" * 70)
        logger.info("🔐 AUDIT KEY MIGRATION REQUESTED")
        logger.info("=" * 70)

        # Determine key path (default is audit_keys/)
        key_path = "audit_keys"
        if hasattr(self, "key_path"):
            key_path = str(self.key_path)

        # Get database path
        db_path = self.db_path
        if not db_path:
            from ciris_engine.logic.persistence import get_sqlite_db_full_path

            db_path = get_sqlite_db_full_path()

        result = await migrate_audit_key_to_ed25519(
            db_path=str(db_path),
            key_path=key_path,
            time_service=self.time_service,
            backup=backup,
        )

        return {
            "success": result.success,
            "message": result.message,
            "entries_migrated": result.entries_migrated,
            "old_key_id": result.old_key_id,
            "new_key_id": result.new_key_id,
            "backup_path": result.backup_path,
            "errors": result.errors,
        }
