"""
Base Scheduled Service - Extends BaseService for services with background tasks.
"""

import asyncio
from abc import abstractmethod
from typing import Any, Dict, Optional

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.schemas.services.metadata import ServiceMetadata


class BaseScheduledService(BaseService):
    """
    Base class for services with scheduled background tasks.

    Provides:
    - Automatic task lifecycle management
    - Configurable run intervals
    - Error handling for scheduled tasks
    - Metrics for task execution

    Subclasses MUST implement:
    - _run_scheduled_task() -> None
    - (plus all BaseService abstract methods)
    """

    def __init__(self, *, run_interval_seconds: float = 60.0, **kwargs: Any) -> None:
        """
        Initialize scheduled service.

        Args:
            run_interval_seconds: How often to run the scheduled task
            **kwargs: Additional arguments passed to BaseService
        """
        super().__init__(**kwargs)
        self._run_interval = run_interval_seconds
        self._task: Optional[asyncio.Task[Any]] = None
        self._task_run_count = 0
        self._task_error_count = 0
        self._last_task_run: Optional[float] = None

    async def _on_start(self) -> None:
        """Start the scheduled task."""
        await super()._on_start()
        self._task = asyncio.create_task(self._run_loop())
        self._logger.info(f"{self.service_name}: Started scheduled task with interval {self._run_interval}s")

    async def _on_stop(self) -> None:
        """Stop the scheduled task."""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # NOSONAR - Expected when stopping the service in _on_stop()
            self._task = None
            self._logger.info(f"{self.service_name}: Stopped scheduled task")

        await super()._on_stop()

    async def _run_loop(self) -> None:
        """Main scheduled task loop."""
        while self._started:
            try:
                # Track task execution
                self._task_run_count += 1
                start_time = self._now()

                # Run the scheduled task
                await self._run_scheduled_task()

                # Update last run time
                self._last_task_run = start_time.timestamp()

                self._logger.debug(f"{self.service_name}: Completed scheduled task run #{self._task_run_count}")

            except asyncio.CancelledError:
                # Task was cancelled, exit cleanly
                self._logger.debug(f"{self.service_name}: Scheduled task cancelled")
                raise  # Re-raise to properly exit the task
            except Exception as e:
                # Track errors but continue running
                self._task_error_count += 1
                self._track_error(e)
                self._logger.error(f"{self.service_name}: Error in scheduled task: {e}", exc_info=True)

            # Wait for next interval
            try:
                await asyncio.sleep(self._run_interval)
            except asyncio.CancelledError:
                self._logger.debug(f"{self.service_name}: Sleep cancelled, exiting loop")
                raise  # Re-raise to properly exit the task

    @abstractmethod
    async def _run_scheduled_task(self) -> None:
        """
        Execute the scheduled task.

        This method is called periodically based on run_interval_seconds.
        Subclasses must implement this to define what the task does.

        Exceptions raised here are caught and logged but don't stop the loop.
        """
        ...

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect scheduled task metrics."""
        metrics = super()._collect_custom_metrics()

        # Calculate time since last run
        time_since_last_run = 0.0
        if self._last_task_run:
            time_since_last_run = self._now().timestamp() - self._last_task_run

        metrics.update(
            {
                "task_run_count": float(self._task_run_count),
                "task_error_count": float(self._task_error_count),
                "task_error_rate": float(self._task_error_count) / max(1, self._task_run_count),
                "task_interval_seconds": self._run_interval,
                "time_since_last_task_run": time_since_last_run,
                "task_running": 1.0 if self._task and not self._task.done() else 0.0,
            }
        )

        return metrics

    def _get_metadata(self) -> ServiceMetadata:
        """Add scheduled task metadata."""
        # Get base metadata from parent
        base_metadata = super()._get_metadata()

        # For now, we'll return the base metadata as-is
        # In a future refactor, we could extend ServiceMetadata to include additional fields
        return base_metadata
