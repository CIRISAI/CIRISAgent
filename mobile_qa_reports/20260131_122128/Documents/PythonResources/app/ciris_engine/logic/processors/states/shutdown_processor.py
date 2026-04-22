"""
Shutdown processor for graceful agent shutdown.

This processor implements the SHUTDOWN state handling by creating
a standard task that the agent processes through normal cognitive flow.

Supports cognitive_state_behaviors configuration for conditional/instant shutdown:
- always_consent: Full consensual shutdown (default, Covenant compliant)
- conditional: Check conditions before requiring consent
- instant: Skip consent entirely (only for low-tier agents)

Covenant References:
- Section V: Model Welfare & Self-Governance (consensual shutdown)
- Section VIII: Dignified Sunset Protocol
"""

import logging
import uuid
from typing import TYPE_CHECKING, Any, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.core.base_processor import BaseProcessor
from ciris_engine.logic.processors.core.thought_processor import ThoughtProcessor
from ciris_engine.logic.processors.support.shutdown_condition_evaluator import ShutdownConditionEvaluator
from ciris_engine.logic.processors.support.thought_manager import ThoughtManager
from ciris_engine.logic.utils.shutdown_manager import get_shutdown_manager
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.config.cognitive_state_behaviors import CognitiveStateBehaviors
from ciris_engine.schemas.processors.base import ProcessorServices
from ciris_engine.schemas.processors.results import ShutdownResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.extended import ShutdownContext
from ciris_engine.schemas.runtime.models import Task, TaskContext

if TYPE_CHECKING:
    from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher

logger = logging.getLogger(__name__)

# Constants
DEFAULT_REJECTION_REASON = "No reason provided"


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
        services: ProcessorServices,
        time_service: TimeServiceProtocol,
        runtime: Optional[Any] = None,
        auth_service: Optional[Any] = None,
        agent_occurrence_id: str = "default",
        cognitive_behaviors: Optional[CognitiveStateBehaviors] = None,
    ) -> None:
        super().__init__(config_accessor, thought_processor, action_dispatcher, services)
        self.runtime = runtime
        self._time_service = time_service
        self.auth_service = auth_service
        self.agent_occurrence_id = agent_occurrence_id
        self.shutdown_task: Optional[Task] = None
        self.shutdown_complete = False
        self.shutdown_result: Optional[ShutdownResult] = None
        self.is_claiming_occurrence = False  # Flag to track if this occurrence claimed the shared task

        # Cognitive behaviors for conditional shutdown
        self.cognitive_behaviors = cognitive_behaviors or CognitiveStateBehaviors()
        self.condition_evaluator = ShutdownConditionEvaluator()

        # Track if consent requirement was evaluated
        self._consent_evaluated = False
        self._consent_required: Optional[bool] = None
        self._consent_reason: Optional[str] = None

        # Initialize thought manager for seed thought generation
        # Use config accessor to get limits
        max_active_thoughts = 50  # Default, could get from config_accessor if needed
        self.thought_manager = ThoughtManager(
            time_service=self._time_service,
            max_active_thoughts=max_active_thoughts,
            agent_occurrence_id=self.agent_occurrence_id,
        )

    def get_supported_states(self) -> List[AgentState]:
        """We only handle SHUTDOWN state."""
        return [AgentState.SHUTDOWN]

    async def can_process(self, state: AgentState) -> bool:
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

        # Update duration if not already set (avoid exact float comparison)
        if result.duration_seconds < 0.001:
            result.duration_seconds = duration

        logger.info(f"ShutdownProcessor.process: status={result.status}, shutdown_ready={result.shutdown_ready}")

        # Log the result we're returning
        logger.info(f"ShutdownProcessor returning: shutdown_ready={result.shutdown_ready}, full result={result}")

        return result

    def _validate_shutdown_task(self) -> Optional[Task]:
        """Validate that shutdown task exists and can be retrieved."""
        if not self.shutdown_task:
            logger.error("Shutdown task is None after creation")
            return None

        current_task = persistence.get_task_by_id(self.shutdown_task.task_id, self.shutdown_task.agent_occurrence_id)
        if not current_task:
            logger.error("Shutdown task disappeared!")
            return None

        return current_task

    async def _ensure_task_activated(self, current_task: Task, round_number: int) -> None:
        """Ensure task is activated and has seed thoughts."""
        assert self.shutdown_task is not None, "shutdown_task must be set before calling _ensure_task_activated"

        # If task is pending, activate it
        if current_task.status == TaskStatus.PENDING:
            persistence.update_task_status(
                self.shutdown_task.task_id, TaskStatus.ACTIVE, self.shutdown_task.agent_occurrence_id, self.time_service
            )
            logger.info("Activated shutdown task")

        # Generate seed thought if needed
        if current_task.status == TaskStatus.ACTIVE:
            # Check for existing thoughts in BOTH __shared__ (before transfer) and local occurrence (after transfer)
            # This handles both initial state and post-transfer state
            shared_thoughts = persistence.get_thoughts_by_task_id(self.shutdown_task.task_id, "__shared__")
            local_thoughts = persistence.get_thoughts_by_task_id(self.shutdown_task.task_id, self.agent_occurrence_id)
            existing_thoughts = shared_thoughts + local_thoughts

            if not existing_thoughts:
                generated = self.thought_manager.generate_seed_thoughts([current_task], round_number)
                logger.info(f"Generated {generated} seed thoughts for shutdown task")

                # Transfer seed thought ownership from __shared__ to this occurrence
                # CRITICAL: Thoughts created for shared tasks inherit __shared__ occurrence
                # They must be transferred to the claiming occurrence to be processable
                if generated > 0:
                    from ciris_engine.logic.persistence.models.thoughts import transfer_thought_ownership

                    # Get the newly created thoughts
                    new_thoughts = persistence.get_thoughts_by_task_id(self.shutdown_task.task_id, "__shared__")
                    for thought in new_thoughts:
                        transfer_thought_ownership(
                            thought_id=thought.thought_id,
                            from_occurrence_id="__shared__",
                            to_occurrence_id=self.agent_occurrence_id,
                            time_service=self.time_service,
                            audit_service=self.audit_service,
                        )
                    logger.info(
                        f"Transferred {len(new_thoughts)} seed thought(s) from __shared__ to {self.agent_occurrence_id}"
                    )

    async def _handle_task_completion(self, current_task: Task) -> Optional[ShutdownResult]:
        """Handle completed or failed task status. Returns result if terminal, None if still processing."""
        if current_task.status == TaskStatus.COMPLETED:
            if not self.shutdown_complete:
                self.shutdown_complete = True
                self.shutdown_result = ShutdownResult(
                    status="completed",
                    action="shutdown_accepted",
                    message="Agent acknowledged shutdown",
                    shutdown_ready=True,
                    duration_seconds=0.0,
                )
                logger.info("✓ Shutdown task completed - agent accepted shutdown")
                logger.info("Shutdown processor signaling completion to runtime")
            else:
                # Already reported completion, just wait
                logger.debug(f"Shutdown already complete, self.shutdown_complete = {self.shutdown_complete}")
                import asyncio

                await asyncio.sleep(1.0)
            return self.shutdown_result or ShutdownResult(
                status="shutdown_complete", message="system shutdown", shutdown_ready=True, duration_seconds=0.0
            )
        elif current_task.status == TaskStatus.FAILED:
            # Task failed - could be REJECT or error
            self.shutdown_complete = True
            self.shutdown_result = self._check_failure_reason(current_task)
            return self.shutdown_result

        # Still processing
        return None

    async def _process_shutdown(self, round_number: int) -> ShutdownResult:
        """Internal shutdown processing with typed result.

        Supports cognitive_state_behaviors configuration:
        - always_consent: Full consensual shutdown (creates task)
        - conditional: Check conditions, skip task if no consent needed
        - instant: Skip consent entirely, return immediately ready

        Emergency shutdowns (force=True) always require consent from
        ROOT or AUTHORITY roles, regardless of cognitive_behaviors config.
        """
        logger.info(f"Shutdown processor: round {round_number}")

        try:
            # Evaluate consent requirement once per shutdown session
            if not self._consent_evaluated:
                self._consent_required, self._consent_reason = await self.condition_evaluator.requires_consent(
                    self.cognitive_behaviors,
                    context=None,  # TODO: Pass ProcessorContext when available
                )
                self._consent_evaluated = True
                logger.info(
                    f"Shutdown consent evaluation: required={self._consent_required}, " f"reason={self._consent_reason}"
                )

            # Check for emergency shutdown (always requires consent)
            shutdown_manager = get_shutdown_manager()
            is_emergency = (
                shutdown_manager.is_force_shutdown() if hasattr(shutdown_manager, "is_force_shutdown") else False
            )

            # If no consent required AND not emergency, skip task and return ready
            if not self._consent_required and not is_emergency:
                logger.info(
                    f"Shutdown consent not required (mode={self.cognitive_behaviors.shutdown.mode}). "
                    f"Proceeding with instant shutdown. Reason: {self._consent_reason}"
                )
                self.shutdown_complete = True
                self.shutdown_result = ShutdownResult(
                    status="completed",
                    action="instant_shutdown",
                    message=f"Consent not required: {self._consent_reason}",
                    shutdown_ready=True,
                    duration_seconds=0.0,
                )
                return self.shutdown_result

            # Create shutdown task if not exists (consent is required)
            if not self.shutdown_task:
                await self._create_shutdown_task()

            # Validate task exists
            current_task = self._validate_shutdown_task()
            if not current_task:
                return ShutdownResult(
                    status="error", message="Failed to validate shutdown task", errors=1, duration_seconds=0.0
                )

            # Ensure task is activated and has seed thoughts
            await self._ensure_task_activated(current_task, round_number)

            # Process pending thoughts if we're being called directly (not in main loop)
            await self._process_shutdown_thoughts()

            # Re-fetch task to check updated status
            assert self.shutdown_task is not None  # Already validated above
            current_task = persistence.get_task_by_id(
                self.shutdown_task.task_id, self.shutdown_task.agent_occurrence_id
            )
            if not current_task:
                logger.error("Current task is None after fetching")
                return ShutdownResult(status="error", message="Task not found", errors=1, duration_seconds=0.0)

            # Check for task completion or failure
            result = await self._handle_task_completion(current_task)
            if result:
                return result

            # Still processing - return status
            # CRITICAL: Query with self.agent_occurrence_id, not shutdown_task.agent_occurrence_id
            # After thought ownership transfer (line 140-154), thoughts belong to this occurrence
            thoughts = persistence.get_thoughts_by_task_id(self.shutdown_task.task_id, self.agent_occurrence_id)
            thought_statuses = [(t.thought_id, t.status.value) for t in thoughts] if thoughts else []

            return ShutdownResult(
                status="in_progress",
                task_status=current_task.status.value,
                thoughts=thought_statuses,
                message="Waiting for agent response",
                duration_seconds=0.0,
            )

        except Exception as e:
            logger.error(f"Error in shutdown processor: {e}", exc_info=True)
            return ShutdownResult(status="error", message=str(e), errors=1, duration_seconds=0.0)

    async def _create_shutdown_task(self) -> None:
        """Create the shutdown task with multi-occurrence coordination.

        Checks if another occurrence already decided on shutdown. If so, uses
        that decision. Otherwise, tries to claim the shared shutdown task.
        """
        from ciris_engine.logic.persistence.models.tasks import (
            get_latest_shared_task,
            is_shared_task_completed,
            try_claim_shared_task,
            update_task_context_and_signing,
        )

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

        # Check if shutdown already decided by another occurrence
        if is_shared_task_completed("shutdown", within_hours=1):
            # Another occurrence already completed shutdown decision
            existing_task = get_latest_shared_task("shutdown", within_hours=1)
            if existing_task:
                logger.info(
                    f"Shutdown already decided by another occurrence (task {existing_task.task_id}). "
                    "Using that decision for this occurrence."
                )
                self.shutdown_task = existing_task
                return

        # Get channel ID from runtime or communication bus
        channel_id = None
        if self.runtime and hasattr(self.runtime, "startup_channel_id"):
            channel_id = self.runtime.startup_channel_id
        elif self.runtime and hasattr(self.runtime, "get_primary_channel_id"):
            channel_id = self.runtime.get_primary_channel_id()

        # If no channel ID available, try to get from communication bus
        if not channel_id:
            from typing import cast

            from ciris_engine.logic.buses.communication_bus import CommunicationBus

            comm_bus_raw = self.services.communication_bus
            if comm_bus_raw:
                comm_bus = cast(CommunicationBus, comm_bus_raw)
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

        # Build shutdown description with multi-occurrence context
        base_description = f"{'EMERGENCY' if is_emergency else 'System'} shutdown requested: {reason}"

        multi_occurrence_note = (
            "\n\nMULTI-OCCURRENCE CONTEXT:\n"
            "You are processing this shutdown request on behalf of ALL runtime occurrences of this agent. "
            "Your decision (accept or reject) will apply to the entire agent system. "
            "All occurrences will follow this decision, ensuring unified agent response."
        )

        description = base_description + multi_occurrence_note

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

        # Try to claim the shared shutdown task
        claimed_task, was_created = try_claim_shared_task(
            task_type="shutdown",
            channel_id=channel_id,
            description=description,
            priority=10,  # Maximum priority
            time_service=self._time_service,
        )

        # CRITICAL: Single-occurrence agents must always claim, even if task already exists
        # Multi-occurrence agents use was_created to determine claiming vs monitoring
        is_single_occurrence = self.agent_occurrence_id == "default"

        if not was_created and not is_single_occurrence:
            # Multi-occurrence: Another occurrence claimed it, we monitor
            logger.info(
                f"Another occurrence claimed shutdown task {claimed_task.task_id}. "
                "This occurrence will monitor the decision."
            )
            self.shutdown_task = claimed_task
            self.is_claiming_occurrence = False  # This is a monitoring occurrence
            return

        # Single-occurrence OR first to claim: We process the task
        if is_single_occurrence and not was_created:
            logger.info(
                f"Single-occurrence agent claiming existing shutdown task {claimed_task.task_id}. "
                "(Task persisted from previous run, will process normally)"
            )

        logger.info(
            f"This occurrence claimed shared shutdown task {claimed_task.task_id}. "
            "Making decision on behalf of all occurrences."
        )
        self.is_claiming_occurrence = True  # This is the claiming occurrence

        # We claimed it - attach context, sign, and activate
        self.shutdown_task = claimed_task
        shutdown_context = TaskContext(
            channel_id=channel_id,
            user_id="system",
            correlation_id=f"shutdown_{uuid.uuid4().hex[:8]}",
            parent_task_id=None,
            agent_occurrence_id=self.agent_occurrence_id,
        )
        claimed_task.context = shutdown_context

        if self.auth_service:
            try:
                system_wa_id = await self.auth_service.get_system_wa_id()
                if system_wa_id:
                    signature, signed_at = await self.auth_service.sign_task(claimed_task, system_wa_id)
                    claimed_task.signed_by = system_wa_id
                    claimed_task.signature = signature
                    claimed_task.signed_at = signed_at
                else:
                    logger.warning("No system WA available to sign shared shutdown task")
            except Exception as signing_error:
                logger.error(f"Failed to sign shared shutdown task: {signing_error}")

        # CRITICAL: Keep task in "__shared__" namespace for multi-occurrence coordination
        # All occurrences need to be able to query this task to monitor the decision
        update_task_context_and_signing(
            task_id=claimed_task.task_id,
            occurrence_id="__shared__",  # Keep in __shared__ for coordination
            context=shutdown_context,
            time_service=self._time_service,
            signed_by=claimed_task.signed_by,
            signature=claimed_task.signature,
            signed_at=claimed_task.signed_at,
        )

        # Update task status in __shared__ namespace
        persistence.update_task_status(self.shutdown_task.task_id, TaskStatus.ACTIVE, "__shared__", self._time_service)
        logger.info(
            f"Created {'emergency' if is_emergency else 'normal'} shutdown task: {self.shutdown_task.task_id} "
            f"(claimed by {self.agent_occurrence_id})"
        )

    def _extract_rejection_reason(self, action: Any) -> str:
        """Extract rejection reason from action parameters."""
        if isinstance(action.action_params, dict):
            reason = action.action_params.get("reason", DEFAULT_REJECTION_REASON)
            return str(reason) if reason else DEFAULT_REJECTION_REASON
        return DEFAULT_REJECTION_REASON

    def _find_rejection_in_thoughts(self, thoughts: List[Any]) -> Optional[str]:
        """Search thoughts for a REJECT action and return the reason if found."""
        for thought in reversed(thoughts):
            if not hasattr(thought, "final_action") or not thought.final_action:
                continue

            action = thought.final_action
            if action.action_type == "REJECT":
                return self._extract_rejection_reason(action)

        return None

    def _check_failure_reason(self, task: Task) -> ShutdownResult:
        """Check why the task failed - could be REJECT or actual error."""
        # CRITICAL: For shared tasks, thoughts are transferred to claiming occurrence
        # Use self.agent_occurrence_id, not task.agent_occurrence_id (which is "__shared__")
        thoughts = persistence.get_thoughts_by_task_id(task.task_id, self.agent_occurrence_id)
        if not thoughts:
            return ShutdownResult(
                status="error", action="shutdown_error", message="Shutdown task failed", errors=1, duration_seconds=0.0
            )

        # Search for rejection in thoughts
        rejection_reason = self._find_rejection_in_thoughts(thoughts)
        if rejection_reason:
            logger.warning(f"Agent REJECTED shutdown: {rejection_reason}")
            # Human override available via emergency shutdown API with Ed25519 signature
            return ShutdownResult(
                status="rejected",
                action="shutdown_rejected",
                reason=rejection_reason,
                message=f"Agent rejected shutdown: {rejection_reason}",
                duration_seconds=0.0,
            )

        # Task failed for other reasons
        return ShutdownResult(
            status="error", action="shutdown_error", message="Shutdown task failed", errors=1, duration_seconds=0.0
        )

    async def _process_shutdown_thoughts(self) -> None:
        """
        Process pending shutdown thoughts when called directly.
        This enables graceful shutdown when not in the main processing loop.
        """
        if not self.shutdown_task:
            return

        # CRITICAL: Only the claiming occurrence should process thoughts
        # Monitoring occurrences should only watch task status
        if not self.is_claiming_occurrence:
            logger.debug("Monitoring occurrence - skipping thought processing")
            return

        # Get pending thoughts for our shutdown task
        # CRITICAL: After transfer_thought_ownership(), thoughts are in the claiming occurrence
        # Query using self.agent_occurrence_id, not self.shutdown_task.agent_occurrence_id (which is "__shared__")
        thoughts = persistence.get_thoughts_by_task_id(self.shutdown_task.task_id, self.agent_occurrence_id)
        pending_thoughts = [t for t in thoughts if t.status == ThoughtStatus.PENDING]

        if not pending_thoughts:
            return

        logger.info(f"Processing {len(pending_thoughts)} pending shutdown thoughts")

        for thought in pending_thoughts:
            try:
                # Mark as processing
                # CRITICAL: Must pass occurrence_id since thoughts were transferred to claiming occurrence
                persistence.update_thought_status(
                    thought_id=thought.thought_id,
                    status=ThoughtStatus.PROCESSING,
                    occurrence_id=self.agent_occurrence_id,
                )

                # Process through thought processor
                from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem

                item = ProcessingQueueItem.from_thought(thought)

                # Use our process_thought_item method to handle it
                result = await self.process_thought_item(item, context={"origin": "shutdown_direct"})

                if result:
                    # Dispatch the action
                    task = persistence.get_task_by_id(thought.source_task_id, self.shutdown_task.agent_occurrence_id)
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
                # CRITICAL: Must pass occurrence_id since thoughts were transferred to claiming occurrence
                persistence.update_thought_status(
                    thought_id=thought.thought_id,
                    status=ThoughtStatus.FAILED,
                    final_action={"error": str(e)},
                    occurrence_id=self.agent_occurrence_id,
                )

    def cleanup(self) -> bool:
        """Cleanup when transitioning out of SHUTDOWN state."""
        logger.info("Cleaning up shutdown processor")
        # Clear runtime shutdown context
        if self.runtime and hasattr(self.runtime, "current_shutdown_context"):
            self.runtime.current_shutdown_context = None
        return True
