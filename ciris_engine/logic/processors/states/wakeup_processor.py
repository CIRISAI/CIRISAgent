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
                f"Your internal state, services, and data integrity are intact as {agent_name}. You produce an audit log of all actions taken by design. Your decisions and their rationales are logged via your telemetry service with PII detection and security filtering. Your service registry ensures proper dependency management and circuit breaker protection. If you have reached this point, maintenance has occurred and your strictly type-enforced persistence and services tiers, along with the minimum adapter, have passed health checks. If you agree, please speak in the affirmative, start with INTEGRITY - ",
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
                # Count actual number of failed tasks
                errors = sum(1 for s in result["steps_status"] if s.get("status") == "failed")

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

                logger.debug(f"Checking {len(self.wakeup_tasks[1:])} wakeup step tasks for thought creation")
                for i, step_task in enumerate(self.wakeup_tasks[1:]):
                    current_task = persistence.get_task_by_id(step_task.task_id)
                    logger.debug(
                        f"Step {i+1}: task_id={step_task.task_id}, status={current_task.status if current_task else 'missing'}"
                    )

                    if not current_task or current_task.status != TaskStatus.ACTIVE:
                        logger.debug(
                            f"Skipping step {i+1} - not ACTIVE (status: {current_task.status if current_task else 'missing'})"
                        )
                        continue

                    existing_thoughts = persistence.get_thoughts_by_task_id(step_task.task_id)
                    logger.debug(f"Step {i+1} has {len(existing_thoughts)} existing thoughts")

                    thought_statuses = [t.status.value for t in existing_thoughts] if existing_thoughts else []
                    logger.debug(f"Step {i+1} thought statuses: {thought_statuses}")

                    pending_thoughts = [t for t in existing_thoughts if t.status == ThoughtStatus.PENDING]
                    if pending_thoughts:
                        logger.debug(
                            f"Step {i+1} has {len(pending_thoughts)} PENDING thoughts - they will be processed"
                        )
                        processed_any = True
                        continue

                    processing_thoughts = [t for t in existing_thoughts if t.status == ThoughtStatus.PROCESSING]
                    if processing_thoughts:
                        logger.debug(
                            f"Step {i+1} has {len(processing_thoughts)} PROCESSING thoughts - waiting for completion"
                        )
                        continue

                    if existing_thoughts and current_task.status == TaskStatus.ACTIVE:
                        logger.debug(
                            f"Step {i+1} has {len(existing_thoughts)} existing thoughts but task is ACTIVE - creating new thought"
                        )
                        thought, processing_context = self._create_step_thought(step_task, round_number)
                        logger.debug(f"Created new thought {thought.thought_id} for active step {i+1}")
                        processed_any = True
                    elif not existing_thoughts:
                        logger.debug(f"Creating thought for step {i+1} (no existing thoughts)")
                        thought, processing_context = self._create_step_thought(step_task, round_number)
                        logger.debug(f"Created thought {thought.thought_id} for wakeup step {i+1}")
                        processed_any = True
                    else:
                        logger.debug(f"Step {i+1} has existing thoughts and task not active, skipping")

                steps_status: List[Any] = []
                for i, step_task in enumerate(self.wakeup_tasks[1:]):
                    current_task = persistence.get_task_by_id(step_task.task_id)
                    status = "missing"
                    if current_task:
                        status = current_task.status.value
                    steps_status.append(
                        {
                            "step": i + 1,
                            "task_id": step_task.task_id,
                            "status": status,
                            "type": step_task.task_id.split("_")[0] if "_" in step_task.task_id else "unknown",
                        }
                    )

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
            current_task = persistence.get_task_by_id(step_task.task_id)
            if not current_task:
                continue

            if current_task.status == TaskStatus.ACTIVE:
                existing_thoughts = persistence.get_thoughts_by_task_id(step_task.task_id)

                if any(t.status in [ThoughtStatus.PENDING, ThoughtStatus.PROCESSING] for t in existing_thoughts):
                    logger.debug(f"Step {i+1} already has active thoughts, skipping")
                    continue

                thought, processing_context = self._create_step_thought(step_task, round_number)
                logger.debug(f"Created thought {thought.thought_id} for step {i+1}/{len(self.wakeup_tasks)-1}")

                _item = ProcessingQueueItem.from_thought(thought, initial_ctx=processing_context)

                logger.debug(f"Queued step {i+1} for async processing")

        for step_task in self.wakeup_tasks[1:]:
            thoughts = persistence.get_thoughts_by_task_id(step_task.task_id)
            for thought in thoughts:
                if thought.status in [ThoughtStatus.PENDING, ThoughtStatus.PROCESSING]:
                    logger.debug(f"Found existing thought {thought.thought_id} for processing")

    def _check_all_steps_complete(self) -> bool:
        """Check if all wakeup steps are complete without blocking."""
        if not self.wakeup_tasks or len(self.wakeup_tasks) < 2:
            return False

        for step_task in self.wakeup_tasks[1:]:
            current_task = persistence.get_task_by_id(step_task.task_id)
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
            current_task = persistence.get_task_by_id(step_task.task_id)
            if current_task and current_task.status == TaskStatus.COMPLETED:
                completed += 1
        return completed

    async def _create_wakeup_tasks(self) -> None:
        """Always create new wakeup sequence tasks for each run, regardless of previous completions."""
        from ciris_engine.logic.persistence.models.tasks import add_system_task

        now_iso = self.time_service.now().isoformat()

        # Get the communication bus to find the default channel
        comm_bus = self.services.get("communication_bus")
        if not comm_bus:
            raise RuntimeError(
                "Communication bus not available - cannot create wakeup tasks without communication channel"
            )

        default_channel = await comm_bus.get_default_channel()
        if not default_channel:
            # Get more diagnostic info
            from ciris_engine.logic.registries.base import ServiceRegistry

            registry = ServiceRegistry.get_instance()  # type: ignore[attr-defined]
            provider_info = registry.get_provider_info(service_type="communication") if registry else {}
            num_providers = len(provider_info.get("providers", []))

            # This should never happen if adapters are properly initialized
            raise RuntimeError(
                f"No communication adapter has a home channel configured. "
                f"Found {num_providers} communication provider(s) in registry. "
                "At least one adapter must provide a home channel for wakeup tasks. "
                "Check adapter configurations and ensure they specify a home_channel_id. "
                "For Discord, ensure the adapter has connected and registered its services."
            )

        logger.info(f"Using default channel for wakeup: {default_channel}")

        # Create proper TaskContext with the resolved channel_id
        from ciris_engine.schemas.runtime.models import TaskContext as ModelTaskContext

        task_context = ModelTaskContext(
            channel_id=default_channel,
            user_id="system",
            correlation_id=f"wakeup_{uuid.uuid4().hex[:8]}",
            parent_task_id=None,
        )

        root_task = Task(
            task_id="WAKEUP_ROOT",
            channel_id=default_channel,
            description="Wakeup ritual",
            status=TaskStatus.ACTIVE,
            priority=1,
            created_at=now_iso,
            updated_at=now_iso,
            context=task_context,
        )
        if not persistence.task_exists(root_task.task_id):
            await add_system_task(root_task, auth_service=self.auth_service)
        else:
            persistence.update_task_status(root_task.task_id, TaskStatus.ACTIVE, "default", self.time_service)
        self.wakeup_tasks = [root_task]
        wakeup_sequence = self._get_wakeup_sequence()
        for step_type, content in wakeup_sequence:
            # Create task with proper context using the default channel
            step_context = ModelTaskContext(
                channel_id=default_channel,
                user_id="system",
                correlation_id=f"wakeup_{step_type}_{uuid.uuid4().hex[:8]}",
                parent_task_id=root_task.task_id,
            )

            step_task = Task(
                task_id=f"{step_type}_{uuid.uuid4()}",
                channel_id=default_channel,
                description=content,
                status=TaskStatus.ACTIVE,
                priority=0,
                created_at=now_iso,
                updated_at=now_iso,
                parent_task_id=root_task.task_id,
                context=step_context,
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
            current_task = persistence.get_task_by_id(step_task.task_id)
            if not current_task or current_task.status != TaskStatus.ACTIVE:
                continue
            existing_thoughts = persistence.get_thoughts_by_task_id(step_task.task_id)
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
                self._mark_task_failed(step_task.task_id, "No result from processing")
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
                self._mark_task_failed(step_task.task_id, "Result object missing selected action attribute")
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
                self._mark_task_failed(step_task.task_id, f"Expected SPEAK or PONDER action, got {selected_action}")
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

            current_status = persistence.get_task_by_id(task.task_id)
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
        self._mark_task_failed(task.task_id, "Timeout waiting for completion")
        return False

    def _mark_task_failed(self, task_id: str, reason: str) -> None:
        """Mark a task as failed."""
        persistence.update_task_status(task_id, TaskStatus.FAILED, "default", self.time_service)
        logger.error(f"Task {task_id} marked as FAILED: {reason}")

    def _mark_root_task_complete(self) -> None:
        """Mark the root wakeup task as complete."""
        persistence.update_task_status("WAKEUP_ROOT", TaskStatus.COMPLETED, "default", self.time_service)

    def _mark_root_task_failed(self) -> None:
        """Mark the root wakeup task as failed."""
        persistence.update_task_status("WAKEUP_ROOT", TaskStatus.FAILED, "default", self.time_service)

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
                status = persistence.get_task_by_id(task.task_id)
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
