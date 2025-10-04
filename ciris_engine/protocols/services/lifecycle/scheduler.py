"""Task Scheduler Service Protocol."""

from abc import abstractmethod
from typing import Any, Dict, List, Optional, Protocol

from ciris_engine.schemas.runtime.extended import ScheduledTask, ScheduledTaskInfo

from ...runtime.base import ServiceProtocol


class TaskSchedulerServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for task scheduler service."""

    @abstractmethod
    async def schedule_task(
        self,
        name: str,
        goal_description: str,
        trigger_prompt: str,
        origin_thought_id: str,
        defer_until: Optional[str] = None,
        schedule_cron: Optional[str] = None,
    ) -> ScheduledTask:
        """Schedule a new task."""
        ...

    @abstractmethod
    async def cancel_task(self, task_id: str) -> bool:
        """Cancel a scheduled task."""
        ...

    @abstractmethod
    async def get_scheduled_tasks(self) -> List[ScheduledTaskInfo]:
        """Get all scheduled tasks."""
        ...

    @abstractmethod
    async def schedule_deferred_task(
        self, thought_id: str, task_id: str, defer_until: str, reason: str, context: Optional[Dict[str, Any]] = None
    ) -> ScheduledTask:
        """Schedule a deferred task for future reactivation."""
        ...
