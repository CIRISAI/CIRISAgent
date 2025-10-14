"""
Thought management functionality for the CIRISAgent processor.
Handles thought generation, queueing, and processing using v1 schemas.
"""

import collections
import logging
import uuid
from typing import Any, Deque, List, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.utils.thought_utils import generate_thought_id
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import Task, TaskContext, Thought, ThoughtContext

logger = logging.getLogger(__name__)


class ThoughtManager:
    """Manages thought generation, queueing, and processing."""

    def __init__(
        self,
        time_service: TimeServiceProtocol,
        max_active_thoughts: int = 50,
        default_channel_id: Optional[str] = None,
        agent_occurrence_id: str = "default",
    ) -> None:
        self.time_service = time_service
        self.max_active_thoughts = max_active_thoughts
        self.default_channel_id = default_channel_id
        self.agent_occurrence_id = agent_occurrence_id
        self.processing_queue: Deque[ProcessingQueueItem] = collections.deque()

    def generate_seed_thought(self, task: Task, round_number: int = 0) -> Optional[Thought]:
        """Generate a seed thought for a task - elegantly copy the context."""
        now_iso = self.time_service.now().isoformat()

        # Convert TaskContext to ThoughtContext for the thought
        # TaskContext and ThoughtContext are different types
        thought_context = None
        if task.context and isinstance(task.context, TaskContext):
            # Create ThoughtContext from TaskContext
            thought_context = ThoughtContext(
                task_id=task.task_id,
                channel_id=task.context.channel_id if hasattr(task.context, "channel_id") else None,
                round_number=round_number,
                depth=0,
                parent_thought_id=None,
                correlation_id=(
                    task.context.correlation_id if hasattr(task.context, "correlation_id") else str(uuid.uuid4())
                ),
                agent_occurrence_id=task.agent_occurrence_id,  # Inherit from task
            )
        elif task.context:
            # If it's already some other type of context, create a new ThoughtContext
            # We can't just copy a TaskContext to ThoughtContext - they're different types
            thought_context = ThoughtContext(
                task_id=task.task_id,
                channel_id=getattr(task.context, "channel_id", None),
                round_number=round_number,
                depth=0,
                parent_thought_id=None,
                correlation_id=getattr(task.context, "correlation_id", str(uuid.uuid4())),
                agent_occurrence_id=task.agent_occurrence_id,  # Inherit from task
            )

        # Extract channel_id from task for the thought
        channel_id: Optional[str] = None
        if task.context and hasattr(task.context, "channel_id"):
            channel_id = task.context.channel_id
        elif task.channel_id:
            channel_id = task.channel_id

        # Log for debugging but don't modify the context
        if thought_context:
            logger.debug(f"SEED_THOUGHT: Copying context for task {task.task_id}")
            # Check if we have channel context in the proper location
            # For logging purposes, check the original task context
            if channel_id:
                logger.debug(f"SEED_THOUGHT: Found channel_id='{channel_id}' in task's context")
            else:
                logger.warning(f"SEED_THOUGHT: No channel context found for task {task.task_id}")
        else:
            logger.critical(f"SEED_THOUGHT: Task {task.task_id} has NO context - POTENTIAL SECURITY BREACH")
            # Delete the malicious task immediately
            try:
                persistence.update_task_status(task.task_id, TaskStatus.FAILED, task.agent_occurrence_id, self.time_service)
                logger.critical(f"SEED_THOUGHT: Marked malicious task {task.task_id} as FAILED")
            except Exception as e:
                logger.critical(f"SEED_THOUGHT: Failed to mark malicious task {task.task_id} as FAILED: {e}")
            return None

        thought = Thought(
            thought_id=generate_thought_id(thought_type=ThoughtType.STANDARD, task_id=task.task_id, is_seed=True),
            source_task_id=task.task_id,
            agent_occurrence_id=task.agent_occurrence_id,  # Inherit from task
            channel_id=channel_id,  # Set channel_id on the thought
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=now_iso,
            updated_at=now_iso,
            round_number=round_number,
            content=f"Initial seed thought for task: {task.description}",
            context=thought_context,
            thought_depth=0,
        )

        try:
            persistence.add_thought(thought)
            logger.debug(f"Generated seed thought {thought.thought_id} for task {task.task_id} (occurrence: {task.agent_occurrence_id})")
            return thought
        except Exception as e:
            logger.error(f"Failed to add seed thought for task {task.task_id}: {e}")
            return None

    def generate_seed_thoughts(self, tasks: List[Task], round_number: int) -> int:
        """Generate seed thoughts for multiple tasks."""
        generated_count = 0

        for task in tasks:
            thought = self.generate_seed_thought(task, round_number)
            if thought:
                generated_count += 1

        if generated_count > 0:
            logger.info(f"Generated {generated_count} seed thoughts")
        else:
            logger.debug("No seed thoughts needed")
        return generated_count

    def populate_queue(self, round_number: int) -> int:
        """
        Populate the processing queue for the current round.
        Returns the number of thoughts added to queue.
        """
        self.processing_queue.clear()

        if self.max_active_thoughts <= 0:
            logger.warning("max_active_thoughts is zero or negative")
            return 0

        pending_thoughts = persistence.get_pending_thoughts_for_active_tasks(self.agent_occurrence_id, limit=self.max_active_thoughts)

        memory_meta = [t for t in pending_thoughts if t.thought_type == ThoughtType.MEMORY]
        if memory_meta:
            pending_thoughts = memory_meta
            logger.info("Memory meta-thoughts detected; processing them exclusively")

        added_count = 0
        for thought in pending_thoughts:
            if len(self.processing_queue) < self.max_active_thoughts:
                queue_item = ProcessingQueueItem.from_thought(thought)
                self.processing_queue.append(queue_item)
                added_count += 1
            else:
                logger.warning(
                    f"Queue capacity ({self.max_active_thoughts}) reached. "
                    f"Thought {thought.thought_id} will not be processed this round."
                )
                break

        if added_count > 0:
            logger.debug(f"Round {round_number}: Populated queue with {added_count} thoughts for occurrence {self.agent_occurrence_id}")
        else:
            logger.debug(f"Round {round_number}: No thoughts to queue for occurrence {self.agent_occurrence_id}")
        return added_count

    def get_queue_batch(self) -> List[ProcessingQueueItem]:
        """Get all items from the processing queue as a batch."""
        return list(self.processing_queue)

    def mark_thoughts_processing(
        self, batch: List[ProcessingQueueItem], round_number: int
    ) -> List[ProcessingQueueItem]:
        """
        Mark thoughts as PROCESSING before sending to workflow coordinator.
        Returns the successfully updated items.
        """
        updated_items: List[Any] = []

        for item in batch:
            try:
                success = persistence.update_thought_status(
                    thought_id=item.thought_id,
                    status=ThoughtStatus.PROCESSING,
                    occurrence_id=self.agent_occurrence_id,
                )
                if success:
                    updated_items.append(item)
                else:
                    logger.warning(f"Failed to mark thought {item.thought_id} as PROCESSING in occurrence {self.agent_occurrence_id}")
            except Exception as e:
                logger.error(f"Error marking thought {item.thought_id} as PROCESSING: {e}")

        return updated_items

    def create_follow_up_thought(
        self,
        parent_thought: Thought,
        content: str,
        thought_type: ThoughtType = ThoughtType.FOLLOW_UP,
        round_number: int = 0,
    ) -> Optional[Thought]:
        """Create a follow-up thought from a parent thought."""
        now_iso = self.time_service.now().isoformat()
        context = (
            parent_thought.context.model_copy()
            if parent_thought.context
            else ThoughtContext(
                task_id=parent_thought.source_task_id,
                correlation_id=str(uuid.uuid4()),
                agent_occurrence_id=parent_thought.agent_occurrence_id,
            )
        )
        thought = Thought(
            thought_id=generate_thought_id(
                thought_type=ThoughtType.FOLLOW_UP,
                task_id=parent_thought.source_task_id,
                parent_thought_id=parent_thought.thought_id,
            ),
            source_task_id=parent_thought.source_task_id,
            agent_occurrence_id=parent_thought.agent_occurrence_id,  # Inherit from parent
            thought_type=thought_type,
            status=ThoughtStatus.PENDING,
            created_at=now_iso,
            updated_at=now_iso,
            round_number=round_number,
            content=content,
            parent_thought_id=parent_thought.thought_id,
            context=context,
            thought_depth=parent_thought.thought_depth + 1,
            ponder_notes=None,
            final_action={},
        )
        try:
            persistence.add_thought(thought)
            logger.debug(f"Created follow-up thought {thought.thought_id} (occurrence: {parent_thought.agent_occurrence_id})")
            return thought
        except Exception as e:
            logger.error(f"Failed to create follow-up thought: {e}")
            return None

    def handle_idle_state(self, round_number: int) -> bool:
        """
        Handle idle state when no thoughts are pending.
        DISABLED: Idle mode is disabled.
        Returns False (no job thoughts created).
        """
        # Idle mode disabled - no automatic job creation
        logger.debug("ThoughtManager.handle_idle_state called but idle mode is disabled for round %s", round_number)
        return False

    def get_pending_thought_count(self) -> int:
        """Get count of pending thoughts for active tasks (strict gating)."""
        return persistence.count_pending_thoughts_for_active_tasks(self.agent_occurrence_id)

    def get_processing_thought_count(self) -> int:
        """Get count of thoughts currently processing."""
        return persistence.count_thoughts_by_status(ThoughtStatus.PROCESSING, self.agent_occurrence_id)
