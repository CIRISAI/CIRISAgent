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
from ciris_engine.logic.utils.task_thought_factory import create_follow_up_thought, create_seed_thought_for_task
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
                persistence.update_task_status(
                    task.task_id, TaskStatus.FAILED, task.agent_occurrence_id, self.time_service
                )
                logger.critical(f"SEED_THOUGHT: Marked malicious task {task.task_id} as FAILED")
            except Exception as e:
                logger.critical(f"SEED_THOUGHT: Failed to mark malicious task {task.task_id} as FAILED: {e}")
            return None

        thought = create_seed_thought_for_task(
            task=task,
            time_service=self.time_service,
            round_number=round_number,
        )

        try:
            persistence.add_thought(thought)
            logger.debug(
                f"Generated seed thought {thought.thought_id} for task {task.task_id} (occurrence: {task.agent_occurrence_id})"
            )
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

    def generate_recovery_thought(self, task: Task, round_number: int = 0) -> Optional[Thought]:
        """Generate a recovery thought for a task that has updated_info_available but no active thoughts.

        This creates a new thought to process updated information (e.g., follow-up messages,
        documents) that came in after all existing thoughts completed/failed.
        """
        from ciris_engine.logic.persistence.db import get_db_connection

        # Get the updated_info_content from the task
        updated_content = getattr(task, "updated_info_content", None) or ""

        # Build recovery thought content
        thought_content = f"RECOVERY: New information received for task.\n\nOriginal task: {task.description}\n\n"
        if updated_content:
            thought_content += f"Updated information:\n{updated_content}\n\n"
        thought_content += "Please review the updated information and continue processing this task."

        # Create thought context from task
        thought_context = None
        if task.context and isinstance(task.context, TaskContext):
            thought_context = ThoughtContext(
                task_id=task.task_id,
                channel_id=task.context.channel_id if hasattr(task.context, "channel_id") else None,
                round_number=round_number,
                depth=0,
                parent_thought_id=None,
                correlation_id=(
                    task.context.correlation_id if hasattr(task.context, "correlation_id") else str(uuid.uuid4())
                ),
                agent_occurrence_id=task.agent_occurrence_id,
            )

        now_iso = self.time_service.now_iso()
        thought_id = generate_thought_id(ThoughtType.STANDARD, task.task_id)

        thought = Thought(
            thought_id=thought_id,
            source_task_id=task.task_id,
            agent_occurrence_id=task.agent_occurrence_id,
            thought_type=ThoughtType.STANDARD,
            status=ThoughtStatus.PENDING,
            created_at=now_iso,
            updated_at=now_iso,
            round_number=round_number,
            content=thought_content,
            context=thought_context,
            thought_depth=0,  # Start fresh for recovery
        )

        try:
            persistence.add_thought(thought)
            logger.info(
                f"[RECOVERY] Generated recovery thought {thought.thought_id} for task {task.task_id} "
                f"(occurrence: {task.agent_occurrence_id})"
            )

            # Clear the updated_info_available flag now that we've created a recovery thought
            try:
                with get_db_connection() as conn:
                    conn.execute(
                        "UPDATE tasks SET updated_info_available = 0 WHERE task_id = ?",
                        (task.task_id,),
                    )
                    conn.commit()
                logger.debug(f"[RECOVERY] Cleared updated_info_available flag for task {task.task_id}")
            except Exception as e:
                logger.warning(f"[RECOVERY] Failed to clear updated_info_available flag for task {task.task_id}: {e}")

            return thought
        except Exception as e:
            logger.error(f"[RECOVERY] Failed to add recovery thought for task {task.task_id}: {e}")
            return None

    def generate_recovery_thoughts(self, tasks: List[Task], round_number: int) -> int:
        """Generate recovery thoughts for multiple tasks with updated information."""
        generated_count = 0

        for task in tasks:
            thought = self.generate_recovery_thought(task, round_number)
            if thought:
                generated_count += 1

        if generated_count > 0:
            logger.info(f"[RECOVERY] Generated {generated_count} recovery thoughts")
        else:
            logger.debug("[RECOVERY] No recovery thoughts needed")
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

        pending_thoughts = persistence.get_pending_thoughts_for_active_tasks(
            self.agent_occurrence_id, limit=self.max_active_thoughts
        )

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
            logger.debug(
                f"Round {round_number}: Populated queue with {added_count} thoughts for occurrence {self.agent_occurrence_id}"
            )
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
                    logger.warning(
                        f"Failed to mark thought {item.thought_id} as PROCESSING in occurrence {self.agent_occurrence_id}"
                    )
            except Exception as e:
                logger.error(f"Error marking thought {item.thought_id} as PROCESSING: {e}")

        return updated_items

    def create_follow_up_thought(
        self,
        parent_thought: Thought,
        content: str,
        thought_type: ThoughtType = ThoughtType.FOLLOW_UP,
    ) -> Optional[Thought]:
        """Create a follow-up thought from a parent thought."""
        thought = create_follow_up_thought(
            parent_thought=parent_thought,
            content=content,
            time_service=self.time_service,
            thought_type=thought_type,
            increment_depth=True,  # Maintain original behavior: depth + 1
        )
        try:
            persistence.add_thought(thought)
            logger.debug(
                f"Created follow-up thought {thought.thought_id} (occurrence: {parent_thought.agent_occurrence_id})"
            )
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
