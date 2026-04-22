"""
Solitude processor for minimal processing and reflection state.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.processors.core.base_processor import BaseProcessor

# ServiceProtocol import removed - processors aren't services
from ciris_engine.logic.registries.base import ServiceRegistry
from ciris_engine.schemas.processors.results import SolitudeResult
from ciris_engine.schemas.processors.solitude import (
    ExitConditions,
    MaintenanceResult,
    ReflectionData,
    ReflectionResult,
    TaskTypePattern,
)
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.processors.status import ProcessorInfo, SolitudeStats
from ciris_engine.schemas.runtime.enums import TaskStatus

logger = logging.getLogger(__name__)


class SolitudeProcessor(BaseProcessor):
    """
    Handles the SOLITUDE state for minimal processing and reflection.
    In this state, the agent:
    - Only responds to critical/high-priority tasks
    - Performs maintenance and cleanup
    - Reflects on past activities
    - Conserves resources
    """

    def __init__(self, *args: Any, critical_priority_threshold: int = 8, **kwargs: Any) -> None:
        """
        Initialize solitude processor.

        Args:
            critical_priority_threshold: Minimum priority to consider a task critical
        """
        super().__init__(*args, **kwargs)
        self.critical_priority_threshold = critical_priority_threshold
        self.reflection_data = ReflectionData()
        self.solitude_reason: Optional[str] = None  # Why agent entered solitude
        self.solitude_start_time: Optional[datetime] = None
        self._time_service: Optional[Any] = None

        # Initialize time service if service registry is available
        if hasattr(self, "services") and self.services.service_registry:
            from typing import cast

            from ciris_engine.logic.registries.base import ServiceRegistry

            service_registry = cast(ServiceRegistry, self.services.service_registry)
            self._initialize_time_service(service_registry)

    def get_supported_states(self) -> List[AgentState]:
        """Solitude processor only handles SOLITUDE state."""
        return [AgentState.SOLITUDE]

    async def can_process(self, state: AgentState) -> bool:
        """Check if we can process the given state."""
        return state == AgentState.SOLITUDE

    async def process(self, round_number: int) -> SolitudeResult:
        """
        Execute solitude processing.
        Performs minimal work focusing on critical tasks and maintenance.
        """
        logger.info(f"Solitude round {round_number}: Minimal processing mode")

        # Log why we're in solitude if this is the first round
        if round_number == 0 and hasattr(self, "solitude_reason") and self.solitude_reason:
            logger.info(f"Solitude: {self.solitude_reason}")
        else:
            logger.debug(f"Solitude round {round_number}: Minimal processing mode")

        start_time = self.time_service.now()

        try:
            critical_count = self._check_critical_tasks()

            if critical_count > 0:
                logger.info(f"Found {critical_count} critical tasks - exiting solitude")
                # Check if we've been in solitude long enough to handle critical tasks
                if self._ready_to_exit_solitude():
                    logger.info(f"Found {critical_count} critical tasks - exiting solitude")
                    duration = (self.time_service.now() - start_time).total_seconds()
                    return SolitudeResult(thoughts_processed=0, errors=0, duration_seconds=duration)
                else:
                    logger.info(f"Found {critical_count} critical tasks but need more solitude time")
                    # Continue in solitude despite critical tasks

            # Minimal viable - skip maintenance and reflection for now
            # Can add back later if needed

            self.metrics.rounds_completed += 1

        except Exception as e:
            logger.error(f"Error in solitude round {round_number}: {e}", exc_info=True)
            self.metrics.errors += 1
            duration = (self.time_service.now() - start_time).total_seconds()
            return SolitudeResult(thoughts_processed=0, errors=1, duration_seconds=duration)

        # No critical tasks, stay in solitude
        duration = (self.time_service.now() - start_time).total_seconds()
        return SolitudeResult(thoughts_processed=0, errors=0, duration_seconds=duration)

    def _check_critical_tasks(self) -> int:
        """Check for critical tasks that require immediate attention."""
        # Get pending tasks ordered by priority
        pending_tasks = persistence.get_pending_tasks_for_activation(limit=20)

        critical_count = 0
        for task in pending_tasks:
            if task.priority >= self.critical_priority_threshold:
                critical_count += 1
                logger.info(f"Critical task found: {task.task_id} " f"(Priority: {task.priority}) - {task.description}")

        return critical_count

    def _perform_maintenance(self) -> MaintenanceResult:
        """Perform system maintenance tasks."""
        logger.info("Performing maintenance tasks")

        maintenance_result = MaintenanceResult()

        try:
            cutoff_date = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
            cutoff_date = cutoff_date.replace(day=cutoff_date.day - 7)

            old_tasks = persistence.get_tasks_older_than(cutoff_date.isoformat())
            completed_old = [t for t in old_tasks if t.status == TaskStatus.COMPLETED]

            if completed_old:
                task_ids = [t.task_id for t in completed_old]
                deleted = persistence.delete_tasks_by_ids(task_ids)
                maintenance_result.old_completed_tasks_cleaned = deleted
                logger.info(f"Cleaned up {deleted} old completed tasks")

            old_thoughts = persistence.get_thoughts_older_than(cutoff_date.isoformat())
            if old_thoughts:
                thought_ids = [t.thought_id for t in old_thoughts]
                deleted_thoughts = persistence.delete_thoughts_by_ids(thought_ids)
                maintenance_result.old_thoughts_cleaned = deleted_thoughts
                logger.info(f"Cleaned up {deleted_thoughts} old thoughts")

            self.reflection_data.cleanup_performed = True

        except Exception as e:
            logger.error(f"Error during maintenance: {e}")

        return maintenance_result

    def _reflect_and_learn(self) -> ReflectionResult:
        """
        Perform reflection and learning activities.
        This could include analyzing patterns, consolidating memories, etc.
        """
        logger.info("Performing reflection and learning")

        reflection_result = ReflectionResult()

        try:
            recent_completed = persistence.get_recent_completed_tasks(limit=20)
            reflection_result.recent_tasks_analyzed = len(recent_completed)

            task_types: Dict[str, int] = {}
            for task in recent_completed:
                task_type = getattr(task.context, "type", "unknown") if task.context else "unknown"
                task_types[task_type] = task_types.get(task_type, 0) + 1

            if task_types:
                most_common = max(task_types.items(), key=lambda x: x[1])
                reflection_result.patterns_identified.append(
                    TaskTypePattern(pattern="most_common_task_type", value=most_common[0], count=most_common[1])
                )

            self.reflection_data.tasks_reviewed += len(recent_completed)

            if self.services.memory_service:
                reflection_result.memories_consolidated = 0

        except Exception as e:
            logger.error(f"Error during reflection: {e}")

        return reflection_result

    def _check_exit_conditions(self) -> ExitConditions:
        """
        Check if conditions warrant exiting solitude state.

        Returns:
            Dict with 'should_exit' bool and optional 'reason' string
        """
        conditions = ExitConditions()

        state_duration = 0
        if hasattr(self, "state_manager"):
            state_duration = self.state_manager.get_state_duration()

        if state_duration > 1800:
            conditions.should_exit = True
            conditions.reason = "Maximum solitude duration reached"
            return conditions

        pending_count = persistence.count_tasks(TaskStatus.PENDING)
        if pending_count > 5:
            conditions.should_exit = True
            conditions.reason = f"Accumulated {pending_count} pending tasks"
            return conditions

        return conditions

    async def start_processing(self, num_rounds: Optional[int] = None) -> None:
        """Start the solitude processing loop."""
        import asyncio

        round_num = 0
        self._running = True

        while self._running and (num_rounds is None or round_num < num_rounds):
            result = await self.process(round_num)
            round_num += 1

            # Check if we should exit solitude
            if result.should_exit_solitude:
                logger.info(f"Exiting solitude: {result.exit_reason or 'Unknown reason'}")
                break

            await asyncio.sleep(2)  # Slower pace in solitude

    def stop_processing(self) -> None:
        """Stop solitude processing and clean up resources."""
        self._running = False
        logger.info("Solitude processor stopped")

    def get_status(self) -> ProcessorInfo:
        """Get current solitude processor status and metrics."""
        solitude_stats = SolitudeStats(
            reflection_data=self.reflection_data,
            critical_threshold=self.critical_priority_threshold,
            total_rounds=self.metrics.rounds_completed,
            cleanup_performed=self.reflection_data.cleanup_performed,
        )
        return ProcessorInfo(
            processor_type="solitude",
            supported_states=[state.value for state in self.get_supported_states()],
            is_running=getattr(self, "_running", False),
            solitude_stats=solitude_stats,
            metrics=self.metrics,
            critical_threshold=self.critical_priority_threshold,
        )

    def _ready_to_exit_solitude(self) -> bool:
        """Check if agent has had enough solitude time."""
        if not hasattr(self, "solitude_start_time") or not self.solitude_start_time:
            return True  # No start time tracked, can exit

        # Minimum solitude duration based on reason
        min_duration_minutes = {
            "overwhelmed": 30,
            "emotional_recovery": 20,
            "boundary_setting": 15,
            "self_care": 10,
            "user_requested": 5,
        }.get(str(getattr(self, "solitude_reason", None)), 5)

        duration = (
            (self._time_service.now() if self._time_service else datetime.now(timezone.utc)) - self.solitude_start_time
        ).total_seconds() / 60
        return duration >= min_duration_minutes

    def _get_solitude_duration_minutes(self) -> float:
        """Get how long we've been in solitude."""
        if not hasattr(self, "solitude_start_time") or not self.solitude_start_time:
            return 0.0
        return (
            (self._time_service.now() if self._time_service else datetime.now(timezone.utc)) - self.solitude_start_time
        ).total_seconds() / 60

    def set_solitude_reason(self, reason: str) -> None:
        """Set why the agent entered solitude."""
        self.solitude_reason = reason
        self.solitude_start_time = self._time_service.now() if self._time_service else datetime.now(timezone.utc)
        logger.info(f"Entering solitude: {reason}")

    def _initialize_time_service(self, service_registry: "ServiceRegistry") -> None:
        """Initialize time service from registry."""
        try:
            from ciris_engine.schemas.runtime.enums import ServiceType

            # Get time service synchronously
            services = service_registry.get_services_by_type(ServiceType.TIME)
            if services:
                self._time_service = services[0]
            else:
                logger.warning("TimeService not found in registry, time operations may fail")
        except Exception as e:
            logger.error(f"Failed to get TimeService: {e}")
