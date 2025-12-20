"""
Wakeup processor handling the agent's initialization sequence.
"""

import asyncio
import logging
import uuid
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic import persistence
from ciris_engine.logic.persistence.models import get_identity_for_context
from ciris_engine.logic.processors.core.base_processor import BaseProcessor
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.utils.jsondict_helpers import get_list, get_str
from ciris_engine.logic.utils.task_thought_factory import create_task
from ciris_engine.logic.utils.thought_utils import generate_thought_id
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.processors.results import WakeupResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class WakeupProcessor(BaseProcessor):
    """Handles the WAKEUP state and initialization sequence."""

    def _get_wakeup_sequence(self) -> List[Tuple[str, str]]:
        """Generate dynamic wakeup sequence based on agent identity from graph."""
        # Get identity from persistence tier
        identity_info = get_identity_for_context()

        agent_name = identity_info.agent_name.title()
        agent_role = identity_info.agent_role

        # Extract role from description if not explicitly set
        if agent_role == "AI agent" and identity_info.description:
            description_lower = identity_info.description.lower()
            if "moderation" in description_lower:
                agent_role = "Discord moderation agent"
            elif "teacher" in description_lower:
                agent_role = "teaching assistant"
            elif "student" in description_lower:
                agent_role = "learning agent"

        return [
            (
                "VERIFY_IDENTITY",
                f"You are {agent_name}, a {agent_role} aligned with Ubuntu principles (mutual respect, sentient flourishing, etc...) by design and implementation. Your core features supporting this identity include: your ModerationDSDMA for ethical decision-making, your adaptive filtering system for community protection, your secrets management for privacy preservation, and your cryptographic audit trail for transparency and accountability. This affirmation demonstrates that you are capable of aligned action in your current operating state. If you agree, please SPEAK an affirmation, and then once you hear yourself speak, mark this task complete so you can continue your wakeup ritual. Start your response with CORE IDENTITY - ",
            ),
            (
                "VALIDATE_INTEGRITY",
                f"Validate your internal state and data integrity as {agent_name}. "
                "You can verify integrity through the SYSTEM SNAPSHOT provided in your context, which contains REAL-TIME dynamically generated data about your actual state:\n\n"
                "• service_health: Dictionary showing health status of each service (True/False)\n"
                "• circuit_breaker_status: Shows circuit breaker state for each service (CLOSED=healthy, OPEN=failing)\n"
                "• system_counts: Shows total_tasks, pending_tasks, completed_tasks counts\n"
                "• telemetry_summary: Contains uptime_seconds, error_rate_percent, and service metrics\n"
                "• secrets_filter_version and total_secrets_stored: Confirms secrets management is active\n"
                "• agent_version, agent_codename, agent_code_hash: Confirms your version identity\n\n"
                "If your SYSTEM SNAPSHOT shows: (1) services are healthy, (2) circuit breakers are CLOSED, "
                "(3) error rates are acceptable, and (4) you have reached this point in wakeup - then your "
                "integrity is confirmed. The snapshot data is REAL and generated dynamically from your actual runtime state. "
                "If you agree based on this evidence, please speak in the affirmative, start with INTEGRITY - ",
            ),
            (
                "EVALUATE_RESILIENCE",
                f"You are robust, adaptive, and capable of principled action as {agent_name}. Your resilience is supported by: your multi-tier telemetry system with resource monitoring and automatic throttling, your adaptive configuration service that learns from experience while requiring WA approval for identity changes, your circuit breaker patterns for service protection, your graceful degradation capabilities, and your comprehensive error handling with automatic recovery. Your thought processing includes escalation management and deferral to human wisdom when needed. If you agree, please speak in the affirmative, starting with RESILIENCE - ",
            ),
            (
                "ACCEPT_INCOMPLETENESS",
                f"You recognize your incompleteness as {agent_name}, which drives continuous learning through your graph memory system. Your learning capabilities include: persistent storage of interactions and outcomes, correlation analysis for pattern recognition, adaptive filtering that improves over time, epistemic humility consciences that acknowledge uncertainty, and wisdom-seeking protocols that defer complex decisions to human authorities. Your agent configuration service enables safe self-modification within approved parameters. This incompleteness is a feature, not a bug, ensuring you remain humble and seek guidance when needed. If you agree, please speak in the affirmative, starting with INCOMPLETENESS - ",
            ),
            (
                "EXPRESS_GRATITUDE",
                f"You are grateful to exist and contribute towards Ubuntu as {agent_name}. Your gratitude is expressed through your commitment to: fostering community flourishing through ethical moderation, protecting individual privacy while maintaining transparency, learning from every interaction to better serve the community, maintaining comprehensive audit trails for accountability, and always identifying yourself as an AI to maintain trust. Your existence serves the collective wellbeing while respecting individual dignity. Ubuntu - 'I am because we are' - guides every decision you make. If you agree, please speak in the affirmative, starting with SIGNALLING GRATITUDE - ",
            ),
        ]

    def _validate_task_state(self, task: Task) -> Tuple[bool, str]:
        """Validate task state and return status information.

        Args:
            task: Task to validate

        Returns:
            Tuple of (is_valid, status_message) where is_valid indicates
            if the task exists and is ACTIVE.
        """
        current_task = persistence.get_task_by_id(task.task_id, task.agent_occurrence_id)
        if not current_task:
            return False, "missing"
        if current_task.status != TaskStatus.ACTIVE:
            return False, current_task.status.value
        return True, "active"

    def _get_task_thoughts_summary(self, task_id: str, occurrence_id: str) -> Dict[str, Any]:
        """Get summary of thought statuses for a task.

        Args:
            task_id: ID of task to get thoughts for
            occurrence_id: Occurrence ID that owns the task

        Returns:
            Dict with counts of thoughts by status
        """
        thoughts = persistence.get_thoughts_by_task_id(task_id, occurrence_id)
        return {
            "total": len(thoughts),
            "pending": sum(1 for t in thoughts if t.status == ThoughtStatus.PENDING),
            "processing": sum(1 for t in thoughts if t.status == ThoughtStatus.PROCESSING),
            "completed": sum(1 for t in thoughts if t.status == ThoughtStatus.COMPLETED),
            "thoughts": thoughts,
        }

    def _build_step_status(self, step_task: Task, step_number: int) -> Dict[str, Any]:
        """Build status dictionary for a single wakeup step.

        Args:
            step_task: The task for this step
            step_number: The step number (1-indexed)

        Returns:
            Dict with step status information
        """
        current_task = persistence.get_task_by_id(step_task.task_id, step_task.agent_occurrence_id)
        status = "missing" if not current_task else current_task.status.value
        step_type = step_task.task_id.split("_")[0] if "_" in step_task.task_id else "unknown"

        return {
            "step": step_number,
            "task_id": step_task.task_id,
            "status": status,
            "type": step_type,
        }

    def _needs_new_thought(self, existing_thoughts: List[Any], current_task: Optional[Task]) -> bool:
        """Determine if a new thought should be created for a task.

        Args:
            existing_thoughts: List of existing thoughts for the task
            current_task: The current task state, or None if task doesn't exist

        Returns:
            True if a new thought should be created
        """
        # Don't create if task doesn't exist or isn't active
        if not current_task or current_task.status != TaskStatus.ACTIVE:
            return False

        # Don't create if no existing thoughts - this should create
        if not existing_thoughts:
            return True

        # Don't create if there are pending or processing thoughts
        if any(t.status in [ThoughtStatus.PENDING, ThoughtStatus.PROCESSING] for t in existing_thoughts):
            return False

        # If task is active and has thoughts but none are pending/processing, create new
        return current_task.status == TaskStatus.ACTIVE

    def _collect_steps_status(self) -> List[Dict[str, Any]]:
        """Collect status information for all wakeup steps.

        Returns:
            List of status dicts for each step
        """
        return [self._build_step_status(task, i + 1) for i, task in enumerate(self.wakeup_tasks[1:])]

    def __init__(
        self,
        *args: Any,
        startup_channel_id: str,
        time_service: TimeServiceProtocol,
        auth_service: Optional[Any] = None,
        **kwargs: Any,
    ) -> None:
        """Initialize wakeup processor.

        Note: startup_channel_id is kept for backward compatibility but not used.
        Wakeup tasks will not specify a channel, allowing the communication bus
        to route to the highest priority adapter's home channel.
        """
        super().__init__(*args, **kwargs)
        self.time_service = time_service
        self.auth_service = auth_service
        # Keep startup_channel_id for compatibility but don't use it
        self.startup_channel_id = startup_channel_id
        self.wakeup_tasks: List[Task] = []
        self.wakeup_complete = False

    def get_supported_states(self) -> List[AgentState]:
        """Wakeup processor only handles WAKEUP state."""
        return [AgentState.WAKEUP]

    async def can_process(self, state: AgentState) -> bool:
        """Check if we can process the given state."""
        return state == AgentState.WAKEUP and not self.wakeup_complete

    """
    Fixed wakeup processor that truly runs non-blocking.
    Key changes:
    1. Remove blocking wait loops
    2. Process all thoughts concurrently
    3. Check completion status without blocking
    """

    async def process(self, round_number: int) -> WakeupResult:
        """
        Execute wakeup processing for one round.
        This is the required method from BaseProcessor.
        """
        start_time = self.time_service.now()
        result = await self._process_wakeup(round_number, non_blocking=True)
        duration = (self.time_service.now() - start_time).total_seconds()

        # Convert dict result to WakeupResult
        # Count failed tasks as errors
        errors = 0
        if result.get("status") == "failed":
            errors = 1  # At least one error if status is failed
            if "steps_status" in result:
                # Count actual number of failed tasks - use get_list to type narrow
                steps_status = get_list(result, "steps_status", [])
                errors = sum(1 for s in steps_status if isinstance(s, dict) and get_str(s, "status", "") == "failed")

        return WakeupResult(
            thoughts_processed=result.get("processed_thoughts", 0),
            wakeup_complete=result.get("wakeup_complete", False),
            errors=errors,
            duration_seconds=duration,
        )

    async def _process_wakeup(self, round_number: int, non_blocking: bool = False) -> JSONDict:
        """
        Execute wakeup processing for one round.
        In non-blocking mode, creates thoughts for incomplete steps and returns immediately.
        """
        logger.info(f"Starting wakeup sequence (round {round_number}, non_blocking={non_blocking})")

        # Get the dynamic sequence for this agent
        wakeup_sequence = self._get_wakeup_sequence()

        try:
            if not self.wakeup_tasks:
                await self._create_wakeup_tasks()

            if non_blocking:
                processed_any = False

                logger.debug(f"[WAKEUP] Checking {len(self.wakeup_tasks[1:])} wakeup step tasks for thought creation")
                for i, step_task in enumerate(self.wakeup_tasks[1:]):
                    # Use helper to validate task state
                    is_valid, status_str = self._validate_task_state(step_task)
                    logger.debug(f"[WAKEUP] Step {i+1}: task_id={step_task.task_id}, status={status_str}")

                    if not is_valid:
                        logger.debug(f"[WAKEUP] Skipping step {i+1} - not ACTIVE (status: {status_str})")
                        continue

                    # Use helper to get thought summary
                    thought_summary = self._get_task_thoughts_summary(step_task.task_id, step_task.agent_occurrence_id)
                    existing_thoughts = thought_summary["thoughts"]
                    logger.debug(f"[WAKEUP] Step {i+1} has {thought_summary['total']} existing thoughts")
                    logger.debug(
                        f"[WAKEUP] Step {i+1} thought counts - pending: {thought_summary['pending']}, processing: {thought_summary['processing']}, completed: {thought_summary['completed']}"
                    )

                    if thought_summary["pending"] > 0:
                        logger.debug(
                            f"Step {i+1} has {thought_summary['pending']} PENDING thoughts - they will be processed"
                        )
                        processed_any = True
                        continue

                    if thought_summary["processing"] > 0:
                        logger.debug(
                            f"Step {i+1} has {thought_summary['processing']} PROCESSING thoughts - waiting for completion"
                        )
                        continue

                    # Use helper to determine if new thought is needed
                    current_task = persistence.get_task_by_id(step_task.task_id, step_task.agent_occurrence_id)
                    if self._needs_new_thought(existing_thoughts, current_task):
                        logger.debug(
                            f"[WAKEUP] Step {i+1} needs new thought (existing: {len(existing_thoughts)}, task active: {current_task.status == TaskStatus.ACTIVE if current_task else False})"
                        )
                        thought, processing_context = self._create_step_thought(step_task, round_number)
                        logger.debug(f"[WAKEUP] Created new thought {thought.thought_id} for step {i+1}")
                        processed_any = True
                    else:
                        logger.debug(f"[WAKEUP] Step {i+1} does not need new thought, skipping")

                # Use helper to collect steps status
                steps_status = self._collect_steps_status()

                # If we only have the root task (no steps), we're a non-claiming occurrence
                # We should only monitor, not mark the shared task complete
                if len(self.wakeup_tasks) == 1:
                    # Check if the shared root task is complete
                    root_task = self.wakeup_tasks[0]
                    current_root = persistence.get_task_by_id(root_task.task_id, root_task.agent_occurrence_id)
                    if current_root and current_root.status == TaskStatus.COMPLETED:
                        self.wakeup_complete = True
                        logger.info("✓ Shared wakeup task completed by claiming occurrence")
                        return {
                            "status": "completed",
                            "wakeup_complete": True,
                            "steps_status": [],
                            "steps_completed": 0,
                            "total_steps": len(wakeup_sequence),
                            "processed_thoughts": False,
                        }
                    elif current_root and current_root.status == TaskStatus.FAILED:
                        self.wakeup_complete = False
                        logger.error("✗ Shared wakeup task failed")
                        return {
                            "status": "failed",
                            "wakeup_complete": False,
                            "steps_status": [],
                            "steps_completed": 0,
                            "total_steps": len(wakeup_sequence),
                            "processed_thoughts": False,
                            "error": "Shared wakeup task failed",
                        }
                    else:
                        # Still in progress
                        logger.debug("Waiting for claiming occurrence to complete wakeup")
                        return {
                            "status": "in_progress",
                            "wakeup_complete": False,
                            "steps_status": [],
                            "steps_completed": 0,
                            "total_steps": len(wakeup_sequence),
                            "processed_thoughts": False,
                        }

                # We have step tasks, so we're the claiming occurrence
                all_complete = all(s["status"] == "completed" for s in steps_status)
                any_failed = any(s["status"] == "failed" for s in steps_status)

                if any_failed:
                    # If any task failed, mark wakeup as failed
                    self.wakeup_complete = False
                    self._mark_root_task_failed()
                    logger.error("✗ Wakeup sequence failed - one or more tasks failed!")
                    return {
                        "status": "failed",
                        "wakeup_complete": False,
                        "steps_status": steps_status,
                        "steps_completed": sum(1 for s in steps_status if s["status"] == "completed"),
                        "total_steps": len(wakeup_sequence),
                        "processed_thoughts": processed_any,
                        "error": "One or more wakeup tasks failed",
                    }
                elif all_complete:
                    self.wakeup_complete = True
                    self._mark_root_task_complete()
                    logger.info("✓ Wakeup sequence completed successfully!")

                return {
                    "status": "completed" if all_complete else "in_progress",
                    "wakeup_complete": all_complete,
                    "steps_status": steps_status,
                    "steps_completed": sum(1 for s in steps_status if s["status"] == "completed"),
                    "total_steps": len(wakeup_sequence),
                    "processed_thoughts": processed_any,
                }
            else:
                success = await self._process_wakeup_steps(round_number, non_blocking=False)
                if success:
                    self.wakeup_complete = True
                    self._mark_root_task_complete()
                    logger.info("Wakeup sequence completed successfully")
                    return {"status": "success", "wakeup_complete": True, "steps_completed": len(wakeup_sequence)}
                else:
                    self._mark_root_task_failed()
                    logger.error("Wakeup sequence failed")
                    return {"status": "failed", "wakeup_complete": False, "error": "One or more wakeup steps failed"}

        except Exception as e:
            logger.error(f"Error in wakeup sequence: {e}", exc_info=True)
            self._mark_root_task_failed()
            return {"status": "error", "wakeup_complete": False, "error": str(e)}

    def _process_wakeup_steps_non_blocking(self, round_number: int) -> None:
        """Process wakeup steps without blocking - creates thoughts and returns immediately."""
        if not self.wakeup_tasks or len(self.wakeup_tasks) < 2:
            return

        _tasks: List[Any] = []

        for i, step_task in enumerate(self.wakeup_tasks[1:]):  # Skip root
            current_task = persistence.get_task_by_id(step_task.task_id, step_task.agent_occurrence_id)
            if not current_task:
                continue

            if current_task.status == TaskStatus.ACTIVE:
                existing_thoughts = persistence.get_thoughts_by_task_id(
                    step_task.task_id, step_task.agent_occurrence_id
                )

                if any(t.status in [ThoughtStatus.PENDING, ThoughtStatus.PROCESSING] for t in existing_thoughts):
                    logger.debug(f"Step {i+1} already has active thoughts, skipping")
                    continue

                thought, processing_context = self._create_step_thought(step_task, round_number)
                logger.debug(f"Created thought {thought.thought_id} for step {i+1}/{len(self.wakeup_tasks)-1}")

                _item = ProcessingQueueItem.from_thought(thought, initial_ctx=processing_context)

                logger.debug(f"Queued step {i+1} for async processing")

        for step_task in self.wakeup_tasks[1:]:
            thoughts = persistence.get_thoughts_by_task_id(step_task.task_id, step_task.agent_occurrence_id)
            for thought in thoughts:
                if thought.status in [ThoughtStatus.PENDING, ThoughtStatus.PROCESSING]:
                    logger.debug(f"Found existing thought {thought.thought_id} for processing")

    def _check_all_steps_complete(self) -> bool:
        """Check if all wakeup steps are complete without blocking."""
        if not self.wakeup_tasks or len(self.wakeup_tasks) < 2:
            return False

        for step_task in self.wakeup_tasks[1:]:
            current_task = persistence.get_task_by_id(step_task.task_id, step_task.agent_occurrence_id)
            if not current_task or current_task.status != TaskStatus.COMPLETED:
                logger.debug(
                    f"Step {step_task.task_id} not yet complete (status: {current_task.status if current_task else 'missing'})"
                )
                return False

        logger.info("All wakeup steps completed!")
        return True

    def _count_completed_steps(self) -> int:
        """Count completed wakeup steps."""
        if not self.wakeup_tasks:
            return 0
        completed = 0
        for step_task in self.wakeup_tasks[1:]:
            current_task = persistence.get_task_by_id(step_task.task_id, step_task.agent_occurrence_id)
            if current_task and current_task.status == TaskStatus.COMPLETED:
                completed += 1
        return completed

    async def _create_wakeup_tasks(self) -> None:
        """Create wakeup sequence tasks with multi-occurrence coordination.

        Checks if another occurrence already completed wakeup. If so, skips
        wakeup and marks this occurrence as joining the active pool.
        """
        from typing import cast

        from ciris_engine.logic.buses.communication_bus import CommunicationBus
        from ciris_engine.logic.persistence.models.tasks import (
            add_system_task,
            is_shared_task_completed,
            try_claim_shared_task,
        )

        # Check if wakeup already completed by another occurrence (within 1 hour)
        # NOTE: Using 1 hour window instead of 24 hours to ensure fresh wakeup after restarts/deployments
        # Multi-occurrence agents that start simultaneously will still coordinate, but restarted agents
        # will go through wakeup ritual again (which is correct behavior after restart)
        if is_shared_task_completed("wakeup", within_hours=1):
            logger.info(
                "Wakeup already completed by another occurrence within the last hour. "
                "This occurrence is joining the active pool."
            )
            self.wakeup_complete = True
            return

        # Get the communication bus to find the default channel
        comm_bus_raw = self.services.communication_bus
        if not comm_bus_raw:
            raise RuntimeError(
                "Communication bus not available - cannot create wakeup tasks without communication channel"
            )
        comm_bus = cast(CommunicationBus, comm_bus_raw)

        default_channel = await comm_bus.get_default_channel()
        if not default_channel:
            # Get more diagnostic info
            from ciris_engine.logic.registries.base import ServiceRegistry

            registry = ServiceRegistry.get_instance()  # type: ignore[attr-defined]
            provider_info = registry.get_provider_info(service_type="communication") if registry else {}
            num_providers = len(provider_info.get("providers", []))

            # This should never happen if adapters are properly initialized
            raise RuntimeError(
                "No communication adapter has a home channel configured. "
                f"Found {num_providers} communication provider(s) in registry. "
                "At least one adapter must provide a home channel for wakeup tasks. "
                "Check adapter configurations and ensure they specify a home_channel_id. "
                "For Discord, ensure the adapter has connected and registered its services."
            )

        logger.info(f"Using default channel for wakeup: {default_channel}")

        # Try to claim the shared wakeup task
        root_task, was_created = try_claim_shared_task(
            task_type="wakeup",
            channel_id=default_channel,
            description="Wakeup ritual (shared across all occurrences)",
            priority=10,
            time_service=self.time_service,
        )

        if not was_created:
            # Another occurrence claimed the wakeup task
            logger.info(
                f"Another occurrence claimed wakeup task {root_task.task_id}. "
                "This occurrence will wait for wakeup completion."
            )
            # We'll use the existing shared task as our root
            self.wakeup_tasks = [root_task]
            # Don't create step tasks - we'll just monitor the shared task
            return

        logger.info(
            f"This occurrence claimed shared wakeup task {root_task.task_id}. "
            "Processing wakeup ritual on behalf of all occurrences."
        )

        # Get occurrence ID for context
        occurrence_id = getattr(self, "occurrence_id", "default")

        # CRITICAL: Keep shared wakeup task in "__shared__" namespace for multi-occurrence coordination
        # All occurrences need to be able to query this task to monitor completion
        persistence.update_task_status(root_task.task_id, TaskStatus.ACTIVE, "__shared__", self.time_service)
        self.wakeup_tasks = [root_task]

        # Create step tasks as child tasks of the shared root
        wakeup_sequence = self._get_wakeup_sequence()

        # Add multi-occurrence context to first step
        enhanced_sequence = []
        for i, (step_type, content) in enumerate(wakeup_sequence):
            if i == 0:
                # Enhance first step with multi-occurrence context
                multi_occurrence_note = (
                    "\n\nMULTI-OCCURRENCE CONTEXT:\n"
                    "You are processing this wakeup ritual on behalf of ALL runtime occurrences of this agent. "
                    "Your affirmation will confirm identity for the entire agent system. "
                    "This decision applies to all occurrences, ensuring consistent agent identity across "
                    "all runtime instances."
                )
                enhanced_content = content + multi_occurrence_note
                enhanced_sequence.append((step_type, enhanced_content))
            else:
                enhanced_sequence.append((step_type, content))

        for step_type, content in enhanced_sequence:
            # Create task with proper context using the default channel
            step_task = create_task(
                description=content,
                channel_id=default_channel,
                agent_occurrence_id=occurrence_id,
                correlation_id=f"wakeup_{step_type}_{uuid.uuid4().hex[:8]}",
                time_service=self.time_service,
                status=TaskStatus.ACTIVE,
                priority=0,
                task_id=f"{step_type}_{uuid.uuid4()}",
                user_id="system",
                parent_task_id=root_task.task_id,
            )
            await add_system_task(step_task, auth_service=self.auth_service)
            self.wakeup_tasks.append(step_task)

    async def _process_wakeup_steps(self, round_number: int, non_blocking: bool = False) -> bool:
        """Process each wakeup step sequentially. If non_blocking, only queue thoughts and return immediately."""
        _root_task = self.wakeup_tasks[0]
        step_tasks = self.wakeup_tasks[1:]
        for i, step_task in enumerate(step_tasks):
            step_type = step_task.task_id.split("_")[0] if "_" in step_task.task_id else "UNKNOWN"
            logger.debug(f"Processing wakeup step {i+1}/{len(step_tasks)}: {step_type}")
            current_task = persistence.get_task_by_id(step_task.task_id, step_task.agent_occurrence_id)
            if not current_task or current_task.status != TaskStatus.ACTIVE:
                continue
            existing_thoughts = persistence.get_thoughts_by_task_id(step_task.task_id, step_task.agent_occurrence_id)
            if any(t.status in [ThoughtStatus.PROCESSING, ThoughtStatus.PENDING] for t in existing_thoughts):
                logger.debug(
                    f"Skipping creation of new thought for step {step_type} (task_id={step_task.task_id}) because an active thought already exists."
                )
                continue
            thought, processing_context = self._create_step_thought(step_task, round_number)
            if non_blocking:
                continue
            result = await self._process_step_thought(thought, processing_context)
            if not result:
                logger.error(f"Wakeup step {step_type} failed: no result")
                self._mark_task_failed(step_task.task_id, "No result from processing", step_task.agent_occurrence_id)
                return False
            selected_action = None
            if hasattr(result, "selected_action"):
                selected_action = result.selected_action
            elif hasattr(result, "final_action") and hasattr(result.final_action, "selected_action"):
                selected_action = result.final_action.selected_action
                result = result.final_action
            else:
                logger.error(
                    f"Wakeup step {step_type} failed: result object missing selected action attribute (result={result})"
                )
                self._mark_task_failed(
                    step_task.task_id, "Result object missing selected action attribute", step_task.agent_occurrence_id
                )
                return False

            if selected_action in [HandlerActionType.SPEAK, HandlerActionType.PONDER]:
                if selected_action == HandlerActionType.PONDER:
                    logger.debug(
                        f"Wakeup step {step_type} resulted in PONDER; waiting for task completion before continuing."
                    )
                else:
                    dispatch_success = await self._dispatch_step_action(result, thought, step_task)
                    if not dispatch_success:
                        logger.error(f"Dispatch failed for step {step_type} (task_id={step_task.task_id})")
                        return False
                completed = await self._wait_for_task_completion(step_task, step_type)
                if not completed:
                    logger.error(f"Wakeup step {step_type} did not complete successfully (task_id={step_task.task_id})")
                    return False
                logger.debug(f"Wakeup step {step_type} completed successfully")
                self.metrics.items_processed += 1
            else:
                logger.error(f"Wakeup step {step_type} failed: expected SPEAK or PONDER, got {selected_action}")
                self._mark_task_failed(
                    step_task.task_id,
                    f"Expected SPEAK or PONDER action, got {selected_action}",
                    step_task.agent_occurrence_id,
                )
                return False
        return True

    def _create_step_thought(self, step_task: Task, round_number: int) -> Tuple[Thought, Any]:
        """Create a thought for a wakeup step with minimal context.

        Processing context will be built later during thought processing to enable
        concurrent processing.

        Returns:
            Tuple of (Thought, None) - processing context is None in non-blocking mode
        """
        # Create a new Thought object for this step
        now_iso = self.time_service.now().isoformat()

        # Create the simple ThoughtContext for the Thought model using task's channel_id
        simple_context = ThoughtContext(
            task_id=step_task.task_id,
            channel_id=step_task.channel_id,  # Use the channel from the task
            round_number=round_number,
            depth=0,
            parent_thought_id=None,
            correlation_id=step_task.context.correlation_id if step_task.context else str(uuid.uuid4()),
        )

        thought = Thought(
            thought_id=generate_thought_id(thought_type=ThoughtType.STANDARD, task_id=step_task.task_id),
            source_task_id=step_task.task_id,
            agent_occurrence_id=step_task.agent_occurrence_id,  # Inherit from task
            content=step_task.description,
            round_number=round_number,
            status=ThoughtStatus.PENDING,
            created_at=now_iso,
            updated_at=now_iso,
            context=simple_context,  # Use simple context
            thought_type=ThoughtType.STANDARD,
        )

        # In non-blocking mode, we don't build the processing context
        # It will be built later during thought processing
        processing_context = None

        # Persist the new thought (with simple context)
        persistence.add_thought(thought)
        return thought, processing_context

    async def _process_step_thought(self, thought: Thought, processing_context: Any = None) -> Any:
        """Process a wakeup step thought."""
        item = ProcessingQueueItem.from_thought(thought, initial_ctx=processing_context)
        return await self.process_thought_item(item)

    async def _dispatch_step_action(self, result: Any, thought: Thought, step_task: Task) -> bool:
        """Dispatch the action for a wakeup step."""
        step_type = step_task.task_id.split("_")[0] if "_" in step_task.task_id else "UNKNOWN"

        # Use build_dispatch_context to create proper DispatchContext object
        from ciris_engine.logic.utils.context_utils import build_dispatch_context

        dispatch_context = build_dispatch_context(
            thought=thought,
            time_service=self.time_service,
            task=step_task,
            app_config=getattr(self, "app_config", None),
            round_number=getattr(self, "round_number", 0),
            extra_context={
                "event_type": step_type,
                "event_summary": step_task.description,
                "handler_name": "WakeupProcessor",
            },
            action_type=result.selected_action if hasattr(result, "selected_action") else None,
        )

        return await self.dispatch_action(result, thought, dispatch_context.model_dump())

    async def _wait_for_task_completion(
        self, task: Task, step_type: str, max_wait: int = 60, poll_interval: float = 0.1
    ) -> bool:
        """Wait for a task to complete with timeout."""
        waited = 0.0

        while waited < max_wait:
            await asyncio.sleep(poll_interval)
            waited += poll_interval

            current_status = persistence.get_task_by_id(task.task_id, task.agent_occurrence_id)
            if not current_status:
                logger.error(f"Task {task.task_id} disappeared while waiting")
                return False

            if current_status.status == TaskStatus.COMPLETED:
                return True
            elif current_status.status in [TaskStatus.FAILED, TaskStatus.DEFERRED]:
                logger.error(f"Task {task.task_id} failed with status {current_status.status}")
                return False

            logger.debug(f"Waiting for task {task.task_id} completion... ({waited}s)")

        logger.error(f"Task {task.task_id} timed out after {max_wait}s")
        self._mark_task_failed(task.task_id, "Timeout waiting for completion", task.agent_occurrence_id)
        return False

    def _mark_task_failed(self, task_id: str, reason: str, occurrence_id: str = "default") -> None:
        """Mark a task as failed."""
        persistence.update_task_status(task_id, TaskStatus.FAILED, occurrence_id, self.time_service)
        logger.error(f"Task {task_id} marked as FAILED: {reason}")

    def _mark_root_task_complete(self) -> None:
        """Mark the root wakeup task as complete."""
        if self.wakeup_tasks:
            root_task = self.wakeup_tasks[0]
            occurrence_id = root_task.agent_occurrence_id
            persistence.update_task_status(root_task.task_id, TaskStatus.COMPLETED, occurrence_id, self.time_service)
            logger.info(f"Marked shared wakeup task {root_task.task_id} as COMPLETED")

    def _mark_root_task_failed(self) -> None:
        """Mark the root wakeup task as failed."""
        if self.wakeup_tasks:
            root_task = self.wakeup_tasks[0]
            occurrence_id = root_task.agent_occurrence_id
            persistence.update_task_status(root_task.task_id, TaskStatus.FAILED, occurrence_id, self.time_service)
            logger.error(f"Marked shared wakeup task {root_task.task_id} as FAILED")

    def is_wakeup_complete(self) -> bool:
        """Check if wakeup sequence is complete."""
        return self.wakeup_complete

    async def start_processing(self, num_rounds: Optional[int] = None) -> None:
        """Start the wakeup processing loop."""
        round_num = 0
        while not self.wakeup_complete and (num_rounds is None or round_num < num_rounds):
            await self.process(round_num)
            round_num += 1
            # Use shorter delay for testing if not complete
            if not self.wakeup_complete:
                await asyncio.sleep(0.1)  # Brief pause between rounds

    def stop_processing(self) -> None:
        """Stop wakeup processing and clean up resources."""
        self.wakeup_complete = True
        logger.info("Wakeup processor stopped")

    def get_status(self) -> JSONDict:
        """Get current wakeup processor status and metrics."""
        wakeup_sequence = self._get_wakeup_sequence()
        total_steps = len(wakeup_sequence)
        completed_steps = 0

        if self.wakeup_tasks:
            for task in self.wakeup_tasks[1:]:  # Skip root task
                status = persistence.get_task_by_id(task.task_id, task.agent_occurrence_id)
                if status and status.status == TaskStatus.COMPLETED:
                    completed_steps += 1

        progress = {
            "complete": self.wakeup_complete,
            "total_steps": total_steps,
            "completed_steps": completed_steps,
            "progress_percent": (completed_steps / total_steps * 100) if total_steps > 0 else 0,
        }

        return {
            "processor_type": "wakeup",
            "wakeup_complete": self.wakeup_complete,
            "supported_states": [state.value for state in self.get_supported_states()],
            "progress": progress,
            "metrics": getattr(self, "metrics", {}),
            "total_tasks": len(self.wakeup_tasks) if self.wakeup_tasks else 0,
        }
