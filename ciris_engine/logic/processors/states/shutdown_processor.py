"""
Shutdown processor for graceful agent shutdown.

This processor implements the SHUTDOWN state handling by creating
a standard task that the agent processes through normal cognitive flow.
"""

import logging
import uuid
from typing import TYPE_CHECKING, Any, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.core.base_processor import BaseProcessor
from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
from ciris_engine.logic.processors.support.thought_manager import ThoughtManager
from ciris_engine.logic.utils.shutdown_manager import get_shutdown_manager
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.processors.results import ShutdownResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.extended import ShutdownContext
from ciris_engine.schemas.runtime.models import Task, TaskContext

if TYPE_CHECKING:
    from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher

logger = logging.getLogger(__name__)


class ShutdownProcessor(BaseProcessor):
    """
    Handles the SHUTDOWN state by creating a standard task
    that the agent processes through normal cognitive flow.
    """

    def __init__(
        self,
        config_accessor: ConfigAccessor,
        thought_processor: ThoughtProcessor,
        action_dispatcher: "ActionDispatcher",
        services: dict,
        time_service: TimeServiceProtocol,
        runtime: Optional[Any] = None,
        auth_service: Optional[Any] = None,
    ) -> None:
        super().__init__(config_accessor, thought_processor, action_dispatcher, services)
        self.runtime = runtime
        self._time_service = time_service
        self.auth_service = auth_service
        self.shutdown_task: Optional[Task] = None
        self.shutdown_complete = False
        self.shutdown_result: Optional[dict] = None

        # Initialize thought manager for seed thought generation
        # Use config accessor to get limits
        max_active_thoughts = 50  # Default, could get from config_accessor if needed
        self.thought_manager = ThoughtManager(time_service=self._time_service, max_active_thoughts=max_active_thoughts)

    def get_supported_states(self) -> List[AgentState]:
        """We only handle SHUTDOWN state."""
        return [AgentState.SHUTDOWN]

    def can_process(self, state: AgentState) -> bool:
        """We can always process shutdown state."""
        return state == AgentState.SHUTDOWN

    async def process(self, round_number: int) -> ShutdownResult:
        """
        Execute shutdown processing for one round.
        Creates a task on first round, monitors for completion.
        When called directly (not in main loop), also processes thoughts.
        """
        start_time = self.time_service.now()
        result = await self._process_shutdown(round_number)
        duration = (self.time_service.now() - start_time).total_seconds()

        # Convert dict result to ShutdownResult
        tasks_cleaned = result.get("tasks_cleaned", 0)
        shutdown_ready = result.get("shutdown_ready", False) or result.get("status") == "completed"
        errors = 1 if result.get("status") == "error" else 0

        logger.info(
            f"ShutdownProcessor.process: status={result.get('status')}, shutdown_ready from dict={result.get('shutdown_ready')}, final shutdown_ready={shutdown_ready}"
        )

        shutdown_result = ShutdownResult(
            tasks_cleaned=tasks_cleaned, shutdown_ready=shutdown_ready, errors=errors, duration_seconds=duration
        )

        # Log the result we're returning
        logger.info(
            f"ShutdownProcessor returning: shutdown_ready={shutdown_result.shutdown_ready}, full result={shutdown_result}"
        )

        return shutdown_result

    async def _process_shutdown(self, round_number: int) -> dict:
        """Internal method that returns dict for backward compatibility."""
        logger.info(f"Shutdown processor: round {round_number}")

        try:
            # Create shutdown task if not exists
            if not self.shutdown_task:
                await self._create_shutdown_task()

            # Check if task is complete
            if not self.shutdown_task:
                logger.error("Shutdown task is None after creation")
                return {"status": "error", "message": "Failed to create shutdown task"}
            current_task = persistence.get_task_by_id(self.shutdown_task.task_id)
            if not current_task:
                logger.error("Shutdown task disappeared!")
                return {"status": "error", "message": "Shutdown task not found"}

            # If task is pending, activate it
            if current_task.status == TaskStatus.PENDING:
                persistence.update_task_status(self.shutdown_task.task_id, TaskStatus.ACTIVE, self.time_service)
                logger.info("Activated shutdown task")

            # Generate seed thought if needed
            if current_task.status == TaskStatus.ACTIVE:
                existing_thoughts = persistence.get_thoughts_by_task_id(self.shutdown_task.task_id)
                if not existing_thoughts:
                    # Use thought manager to generate seed thought
                    generated = self.thought_manager.generate_seed_thoughts([current_task], round_number)
                    logger.info(f"Generated {generated} seed thoughts for shutdown task")

            # Process pending thoughts if we're being called directly (not in main loop)
            # This allows shutdown negotiation to happen when runtime calls us manually
            await self._process_shutdown_thoughts()

            # Re-fetch task to check updated status
            current_task = persistence.get_task_by_id(self.shutdown_task.task_id)

            # Check task completion status
            if not current_task:
                logger.error("Current task is None after fetching")
                return {"status": "error", "message": "Task not found"}
            if current_task.status == TaskStatus.COMPLETED:
                if not self.shutdown_complete:
                    self.shutdown_complete = True
                    self.shutdown_result = {
                        "status": "completed",
                        "action": "shutdown_accepted",
                        "message": "Agent acknowledged shutdown",
                        "shutdown_ready": True,  # Add this field that main processor checks
                    }
                    logger.info("✓ Shutdown task completed - agent accepted shutdown")
                    # Signal the runtime to proceed with shutdown
                    logger.info("Shutdown processor signaling completion to runtime")
                else:
                    # Already reported completion, just wait
                    logger.debug(f"Shutdown already complete, self.shutdown_complete = {self.shutdown_complete}")
                    import asyncio

                    await asyncio.sleep(1.0)
                return self.shutdown_result or {"status": "shutdown_complete", "reason": "system shutdown"}
            elif current_task.status == TaskStatus.FAILED:
                # Task failed - could be REJECT or error
                self.shutdown_complete = True
                self.shutdown_result = await self._check_failure_reason(current_task)
                return self.shutdown_result

            # Still processing
            thoughts = persistence.get_thoughts_by_task_id(self.shutdown_task.task_id)
            thought_statuses = [(t.thought_id, t.status.value) for t in thoughts] if thoughts else []

            return {
                "status": "in_progress",
                "task_status": current_task.status.value,
                "thoughts": thought_statuses,
                "message": "Waiting for agent response",
            }

        except Exception as e:
            logger.error(f"Error in shutdown processor: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def _create_shutdown_task(self) -> None:
        """Create the shutdown task."""
        from ciris_engine.logic.persistence.models.tasks import add_system_task

        shutdown_manager = get_shutdown_manager()
        reason = shutdown_manager.get_shutdown_reason() or "Graceful shutdown requested"

        # Check if this is an emergency shutdown (force=True)
        is_emergency = shutdown_manager.is_force_shutdown() if hasattr(shutdown_manager, "is_force_shutdown") else False

        # For emergency shutdown, verify the requester has root or authority role
        if is_emergency and self.auth_service:
            requester_wa_id = (
                shutdown_manager.get_requester_wa_id() if hasattr(shutdown_manager, "get_requester_wa_id") else None
            )
            if requester_wa_id:
                requester_wa = await self.auth_service.get_wa(requester_wa_id)
                if requester_wa:
                    from ciris_engine.schemas.services.authority_core import WARole

                    if requester_wa.role not in [WARole.ROOT, WARole.AUTHORITY]:
                        logger.error(
                            f"Emergency shutdown requested by {requester_wa.role.value} {requester_wa_id} - DENIED"
                        )
                        # Reject the emergency shutdown
                        raise ValueError(
                            f"Emergency shutdown requires ROOT or AUTHORITY role, not {requester_wa.role.value}"
                        )
                    logger.info(f"Emergency shutdown authorized by {requester_wa.role.value} {requester_wa_id}")
                else:
                    logger.error(f"Emergency shutdown requester {requester_wa_id} not found")
                    raise ValueError("Emergency shutdown requester not found")
            else:
                logger.warning("Emergency shutdown requested without requester ID")

        now_iso = self._time_service.now().isoformat()

        # Create task context with shutdown details and proper channel context
        # Get channel ID from runtime if available
        channel_id = None
        if self.runtime and hasattr(self.runtime, "startup_channel_id"):
            channel_id = self.runtime.startup_channel_id
        elif self.runtime and hasattr(self.runtime, "get_primary_channel_id"):
            channel_id = self.runtime.get_primary_channel_id()

        # If no channel ID available, try to get from communication bus
        if not channel_id:
            comm_bus = self.services.get("communication_bus")
            if comm_bus:
                try:
                    channel_id = await comm_bus.get_default_channel()
                    if channel_id:
                        logger.info(f"Using default channel from communication bus: {channel_id}")
                except Exception as e:
                    logger.warning(f"Failed to get default channel from communication bus: {e}")

            # Final fallback - empty string (will be handled by communication bus routing)
            if not channel_id:
                channel_id = ""
                logger.warning("No channel ID available for shutdown task, using empty string for adapter routing")

        # Create proper TaskContext for the shutdown task
        context = TaskContext(
            channel_id=channel_id,
            user_id="system",
            correlation_id=f"shutdown_{uuid.uuid4().hex[:8]}",
            parent_task_id=None,
        )

        # Store shutdown context in runtime for system snapshot
        if self.runtime:
            self.runtime.current_shutdown_context = ShutdownContext(
                is_terminal=is_emergency,  # Emergency shutdowns are terminal
                reason=reason,
                initiated_by="runtime",
                allow_deferral=not is_emergency,  # No deferral for emergency
                expected_reactivation=None,
                agreement_context=None,
            )

        self.shutdown_task = Task(
            task_id=f"shutdown_{uuid.uuid4().hex[:8]}",
            channel_id=channel_id,
            description=f"{'EMERGENCY' if is_emergency else 'System'} shutdown requested: {reason}",
            priority=10,  # Maximum priority (was 100, but max is 10)
            status=TaskStatus.ACTIVE,  # Set as ACTIVE to prevent orphan deletion
            created_at=now_iso,
            updated_at=now_iso,
            context=context,
            parent_task_id=None,  # Root-level task
        )

        await add_system_task(self.shutdown_task, auth_service=self.auth_service)
        logger.info(f"Created {'emergency' if is_emergency else 'normal'} shutdown task: {self.shutdown_task.task_id}")

    def _check_failure_reason(self, task: Task) -> dict:
        """Check why the task failed - could be REJECT or actual error."""
        # Look at the final thought to determine reason
        thoughts = persistence.get_thoughts_by_task_id(task.task_id)
        if thoughts:
            # Get the most recent thought with a final action
            for thought in reversed(thoughts):
                if hasattr(thought, "final_action") and thought.final_action:
                    action = thought.final_action
                    if action.action_type == "REJECT":
                        reason = (
                            action.action_params.get("reason", "No reason provided")
                            if isinstance(action.action_params, dict)
                            else "No reason provided"
                        )
                        logger.warning(f"Agent REJECTED shutdown: {reason}")
                        # Human override available via emergency shutdown API with Ed25519 signature
                        return {
                            "status": "rejected",
                            "action": "shutdown_rejected",
                            "reason": reason,
                            "message": f"Agent rejected shutdown: {reason}",
                        }

        # Task failed for other reasons
        return {"status": "error", "action": "shutdown_error", "message": "Shutdown task failed"}

    async def _process_shutdown_thoughts(self) -> None:
        """
        Process pending shutdown thoughts when called directly.
        This enables graceful shutdown when not in the main processing loop.
        """
        if not self.shutdown_task:
            return

        # Get pending thoughts for our shutdown task
        thoughts = persistence.get_thoughts_by_task_id(self.shutdown_task.task_id)
        pending_thoughts = [t for t in thoughts if t.status == ThoughtStatus.PENDING]

        if not pending_thoughts:
            return

        logger.info(f"Processing {len(pending_thoughts)} pending shutdown thoughts")

        for thought in pending_thoughts:
            try:
                # Mark as processing
                persistence.update_thought_status(thought_id=thought.thought_id, status=ThoughtStatus.PROCESSING)

                # Process through thought processor
                from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem

                item = ProcessingQueueItem.from_thought(thought)

                # Use our process_thought_item method to handle it
                result = await self.process_thought_item(item, context={"origin": "shutdown_direct"})

                if result:
                    # Dispatch the action
                    task = persistence.get_task_by_id(thought.source_task_id)
                    from ciris_engine.logic.utils.context_utils import build_dispatch_context

                    # Get action from final_action (result is ConscienceApplicationResult)
                    action_result = result.final_action if hasattr(result, "final_action") else result
                    action_type = action_result.selected_action if action_result else None

                    dispatch_context = build_dispatch_context(
                        thought=thought,
                        time_service=self.time_service,
                        task=task,
                        app_config=self.config,  # Use config accessor
                        round_number=0,
                        action_type=action_type,
                    )

                    await self.action_dispatcher.dispatch(
                        action_selection_result=action_result, thought=thought, dispatch_context=dispatch_context
                    )

                    logger.info(f"Dispatched {action_type} action for shutdown thought")
                else:
                    logger.warning(f"No result from processing shutdown thought {thought.thought_id}")

            except Exception as e:
                logger.error(f"Error processing shutdown thought {thought.thought_id}: {e}", exc_info=True)
                persistence.update_thought_status(
                    thought_id=thought.thought_id, status=ThoughtStatus.FAILED, final_action={"error": str(e)}
                )

    def cleanup(self) -> bool:
        """Cleanup when transitioning out of SHUTDOWN state."""
        logger.info("Cleaning up shutdown processor")
        # Clear runtime shutdown context
        if self.runtime and hasattr(self.runtime, "current_shutdown_context"):
            self.runtime.current_shutdown_context = None
        return True
