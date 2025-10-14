"""
Work processor handling normal task and thought processing.
Enhanced with proper context building and service passing.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
    from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher

from ciris_engine.logic import persistence
from ciris_engine.logic.processors.core.base_processor import BaseProcessor
from ciris_engine.logic.processors.support.task_manager import TaskManager
from ciris_engine.logic.processors.support.thought_manager import ThoughtManager

# ServiceProtocol import removed - processors aren't services
from ciris_engine.logic.utils.context_utils import build_dispatch_context
from ciris_engine.schemas.processors.results import WorkResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import ThoughtStatus

logger = logging.getLogger(__name__)


class WorkProcessor(BaseProcessor):
    """Handles the WORK state for normal task/thought processing."""

    def __init__(
        self,
        config_accessor: Any,  # ConfigAccessor
        thought_processor: "ThoughtProcessor",
        action_dispatcher: "ActionDispatcher",
        services: Any,  # JSONDict - using Any to avoid circular import issues
        startup_channel_id: Optional[str] = None,
        agent_occurrence_id: str = "default",
        **kwargs: Any,
    ) -> None:
        """Initialize work processor."""
        self.startup_channel_id = startup_channel_id
        self.agent_occurrence_id = agent_occurrence_id
        super().__init__(config_accessor, thought_processor, action_dispatcher, services, **kwargs)

        workflow_config = getattr(self.config, "workflow", None)
        if workflow_config:
            max_active_tasks = getattr(workflow_config, "max_active_tasks", 10)
            max_active_thoughts = getattr(workflow_config, "max_active_thoughts", 50)
        else:
            max_active_tasks = 10
            max_active_thoughts = 50

        time_service = services.get("time_service")
        if not time_service:
            raise ValueError("time_service is required in services")
        self.time_service = time_service
        self.task_manager = TaskManager(
            max_active_tasks=max_active_tasks,
            time_service=self.time_service,
            agent_occurrence_id=self.agent_occurrence_id,
        )
        self.thought_manager = ThoughtManager(
            time_service=self.time_service,
            max_active_thoughts=max_active_thoughts,
            default_channel_id=self.startup_channel_id,
            agent_occurrence_id=self.agent_occurrence_id,
        )
        self.last_activity_time = self.time_service.now()
        self.idle_rounds = 0

    def get_supported_states(self) -> List[AgentState]:
        """Work processor handles WORK and PLAY states."""
        return [AgentState.WORK, AgentState.PLAY]

    async def can_process(self, state: AgentState) -> bool:
        """Check if we can process the given state."""
        return state in self.get_supported_states()

    async def process(self, round_number: int) -> WorkResult:
        """Execute one round of work processing."""
        logger.debug(f"WorkProcessor.process called for round {round_number}")
        start_time = self.time_service.now()

        round_metrics: JSONDict = {
            "round_number": round_number,
            "tasks_activated": 0,
            "thoughts_generated": 0,
            "thoughts_processed": 0,
            "errors": 0,
            "was_idle": False,
        }

        try:
            # Phase 1: Task activation
            logger.debug("Phase 1: Activating pending tasks...")
            activated = self.task_manager.activate_pending_tasks()
            logger.debug(f"Activated {activated} tasks")
            round_metrics["tasks_activated"] = activated

            # Phase 2: Seed thought generation
            logger.debug("Phase 2: Generating seed thoughts...")
            tasks_needing_seed = self.task_manager.get_tasks_needing_seed()
            logger.debug(f"Found {len(tasks_needing_seed)} tasks needing seed thoughts")
            generated = self.thought_manager.generate_seed_thoughts(tasks_needing_seed, round_number)
            logger.debug(f"Generated {generated} seed thoughts")
            round_metrics["thoughts_generated"] = generated

            # Phase 3: Populate processing queue
            logger.debug("Phase 3: Populating processing queue...")
            queue_size = self.thought_manager.populate_queue(round_number)
            logger.debug(f"Queue size after population: {queue_size}")

            if queue_size > 0:
                # Phase 4: Process thought batch
                logger.debug("Phase 4: Processing thought batch...")
                batch = self.thought_manager.get_queue_batch()
                logger.debug(f"Got batch of {len(batch)} thoughts to process")
                processed = await self._process_batch(batch, round_number)
                logger.debug(f"Processed {processed} thoughts")
                round_metrics["thoughts_processed"] = processed

                # Update activity tracking
                self.last_activity_time = start_time
                self.idle_rounds = 0
                round_metrics["was_idle"] = False
            else:
                # Handle idle state - DISABLED
                round_metrics["was_idle"] = True
                # Idle mode disabled - no automatic transitions
                # self.idle_rounds += 1
                # await self._handle_idle_state(round_number)

            # Update metrics
            self.metrics.rounds_completed += 1

        except Exception as e:
            logger.error(f"Error in work round {round_number}: {e}", exc_info=True)
            round_metrics["errors"] += 1
            self.metrics.errors += 1

        # Calculate round duration
        end_time = self.time_service.now()
        duration = (end_time - start_time).total_seconds()
        round_metrics["duration_seconds"] = duration

        # Only log at INFO level if work was actually done
        if round_metrics["thoughts_processed"] > 0 or round_metrics["tasks_activated"] > 0:
            logger.info(
                f"Work round {round_number}: completed "
                f"({round_metrics['thoughts_processed']} thoughts, {duration:.2f}s)"
            )
        else:
            logger.debug(f"Work round {round_number}: idle (no pending work)")

        return WorkResult(
            tasks_processed=round_metrics.get("tasks_activated", 0),
            thoughts_processed=round_metrics.get("thoughts_processed", 0),
            errors=round_metrics.get("errors", 0),
            duration_seconds=duration,
        )

    async def _process_batch(self, batch: List[Any], round_number: int) -> int:
        """Process a batch of thoughts."""
        if not batch:
            return 0

        logger.debug(f"Processing batch of {len(batch)} thoughts")

        batch = self.thought_manager.mark_thoughts_processing(batch, round_number)
        if not batch:
            logger.warning("No thoughts could be marked as PROCESSING")
            return 0

        processed_count = 0

        for item in batch:
            try:
                result = await self._process_single_thought(item)
                processed_count += 1

                if result is None:
                    logger.debug(f"Thought {item.thought_id} was re-queued")
                else:
                    await self._dispatch_thought_result(item, result)

            except Exception as e:
                logger.error(f"Error processing thought {item.thought_id}: {e}", exc_info=True)
                self._mark_thought_failed(item.thought_id, str(e))

        return processed_count

    async def _process_single_thought(self, item: Any) -> Any:
        """Process a single thought item."""
        return await self.process_thought_item(item)

    async def _dispatch_thought_result(self, item: Any, result: Any) -> None:
        """Dispatch the result of thought processing."""
        thought_id = item.thought_id

        # Extract action from ConscienceApplicationResult if needed
        action_result = result.final_action if hasattr(result, "final_action") else result
        selected_action = action_result.selected_action if hasattr(action_result, "selected_action") else "unknown"

        logger.debug(f"Dispatching action {selected_action} for thought {thought_id}")

        thought_obj = await persistence.async_get_thought_by_id(thought_id, self.agent_occurrence_id)
        if not thought_obj:
            logger.error(f"Could not retrieve thought {thought_id} for dispatch")
            return

        task = persistence.get_task_by_id(item.source_task_id, self.agent_occurrence_id)
        dispatch_context = build_dispatch_context(
            thought=thought_obj,
            time_service=self.time_service,
            task=task,
            app_config=self.config,
            round_number=getattr(item, "round_number", 0),
            extra_context=getattr(item, "initial_context", {}),
            action_type=selected_action if result else None,
        )

        try:
            await self.dispatch_action(result, thought_obj, dispatch_context.model_dump())
        except Exception as e:
            logger.error(f"Error dispatching action for thought {thought_id}: {e}")
            self._mark_thought_failed(thought_id, f"Dispatch failed: {str(e)}")

    def _handle_idle_state(self, round_number: int) -> None:
        """Handle idle state when no thoughts are pending."""
        logger.info(f"Round {round_number}: No thoughts to process (idle rounds: {self.idle_rounds})")

        # Create job thought if needed
        created_job = self.thought_manager.handle_idle_state(round_number)

        if created_job:
            logger.info("Created job thought for idle monitoring")
        else:
            logger.debug("No job thought needed")

    def _mark_thought_failed(self, thought_id: str, error: str) -> None:
        """Mark a thought as failed."""
        persistence.update_thought_status(
            thought_id=thought_id, status=ThoughtStatus.FAILED, final_action={"error": error}
        )

    def get_idle_duration(self) -> float:
        """Get duration in seconds since last activity."""
        return (self.time_service.now() - self.last_activity_time).total_seconds()

    def should_transition_to_dream(self) -> bool:
        """
        Check if we should recommend transitioning to DREAM state.

        DISABLED: Idle mode transitions are disabled.

        Returns:
            Always returns False (idle mode disabled)
        """
        # Idle mode disabled - no automatic transitions
        return False

    # ServiceProtocol implementation
    async def start_processing(self, num_rounds: Optional[int] = None) -> None:
        """Start the work processing loop."""
        import asyncio

        round_num = 0
        self._running = True

        while self._running and (num_rounds is None or round_num < num_rounds):
            await self.process(round_num)
            round_num += 1

            if self.should_transition_to_dream():
                logger.info("Work processor recommends transitioning to DREAM state due to inactivity")
                break

            await asyncio.sleep(1)  # Brief pause between rounds

    def stop_processing(self) -> None:
        """Stop work processing and clean up resources."""
        self._running = False
        logger.info("Work processor stopped")

    def get_status(self) -> JSONDict:
        """Get current work processor status and metrics."""
        work_stats = {
            "last_activity": self.last_activity_time.isoformat(),
            "idle_duration_seconds": self.get_idle_duration(),
            "idle_rounds": self.idle_rounds,
            "active_tasks": self.task_manager.get_active_task_count(),
            "pending_tasks": self.task_manager.get_pending_task_count(),
            "pending_thoughts": self.thought_manager.get_pending_thought_count(),
            "processing_thoughts": self.thought_manager.get_processing_thought_count(),
            "total_rounds": self.metrics.rounds_completed,
            "total_processed": self.metrics.items_processed,
            "total_errors": self.metrics.errors,
        }
        return {
            "processor_type": "work",
            "supported_states": [state.value for state in self.get_supported_states()],
            "is_running": getattr(self, "_running", False),
            "work_stats": work_stats,
            "metrics": getattr(self, "metrics", {}),
            "startup_channel_id": self.startup_channel_id,
            "should_transition_to_dream": self.should_transition_to_dream(),
        }
