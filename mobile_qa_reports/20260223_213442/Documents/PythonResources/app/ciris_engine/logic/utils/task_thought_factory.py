"""
Centralized factory for creating tasks and thoughts with proper occurrence_id handling.

This module provides high-quality helpers that ensure:
1. Proper occurrence_id propagation in single and multi-occurrence deployments
2. Consistent timestamp handling
3. Proper context creation and inheritance
4. Type safety with Pydantic models

Key principles:
- Every task/thought MUST have an agent_occurrence_id
- "default" is just another occurrence_id, not special
- Contexts must properly inherit occurrence_id
- No direct Task() or Thought() construction outside this module (goal)
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from ciris_engine.logic.utils.thought_utils import generate_thought_id
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus, ThoughtType
from ciris_engine.schemas.runtime.models import ImageContent, Task, TaskContext, Thought, ThoughtContext

logger = logging.getLogger(__name__)


def create_task(
    *,
    description: str,
    channel_id: str,
    agent_occurrence_id: str,
    correlation_id: str,
    time_service: Optional[TimeServiceProtocol] = None,
    status: TaskStatus = TaskStatus.PENDING,
    priority: int = 5,
    task_id: Optional[str] = None,
    user_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    context: Optional[TaskContext] = None,
    images: Optional[List[ImageContent]] = None,
) -> Task:
    """
    Create a Task with proper occurrence_id handling.

    Args:
        description: Human-readable task description
        channel_id: Channel where task originated
        agent_occurrence_id: Occurrence ID that owns this task (required, no default)
        correlation_id: Correlation ID for tracing (required)
        time_service: Time service for timestamps (uses UTC if None)
        status: Task status (default: PENDING)
        priority: Task priority 0-10 (default: 5)
        task_id: Optional explicit task_id (generates UUID if None)
        user_id: Optional user ID who created task
        parent_task_id: Optional parent task ID
        context: Optional pre-built TaskContext (will be validated)
        images: Optional list of images for multimodal tasks

    Returns:
        Task with proper occurrence_id in both task and context

    Example:
        task = create_task(
            description="Respond to user message",
            channel_id="discord_123456",
            agent_occurrence_id="002",
            correlation_id="msg_abc",
            time_service=time_service,
            user_id="user_789",
        )
    """
    if not agent_occurrence_id:
        raise ValueError("agent_occurrence_id is required and cannot be empty")

    if not correlation_id:
        raise ValueError("correlation_id is required and cannot be empty")

    task_id = task_id or str(uuid.uuid4())
    now_iso = time_service.now_iso() if time_service else datetime.now(timezone.utc).isoformat()

    # Build or verify context - TaskContext requires correlation_id
    if context is None:
        # Create new context with required fields
        context = TaskContext(
            channel_id=channel_id,
            user_id=user_id,
            correlation_id=correlation_id,
            parent_task_id=parent_task_id,
            agent_occurrence_id=agent_occurrence_id,
        )
    else:
        # Verify existing context has correct occurrence_id
        if context.agent_occurrence_id != agent_occurrence_id:
            logger.warning(
                f"Context occurrence_id '{context.agent_occurrence_id}' doesn't match task occurrence_id '{agent_occurrence_id}' - overwriting"
            )
            # Cannot modify Pydantic model after creation, must recreate
            context = TaskContext(
                channel_id=context.channel_id,
                user_id=context.user_id if hasattr(context, "user_id") else user_id,
                correlation_id=context.correlation_id,
                parent_task_id=context.parent_task_id if hasattr(context, "parent_task_id") else parent_task_id,
                agent_occurrence_id=agent_occurrence_id,  # Override with correct one
            )

    task = Task(
        task_id=task_id,
        channel_id=channel_id,
        agent_occurrence_id=agent_occurrence_id,
        description=description,
        status=status,
        priority=priority,
        created_at=now_iso,
        updated_at=now_iso,
        parent_task_id=parent_task_id,
        context=context,
        images=images or [],
    )

    image_count = len(images) if images else 0
    if image_count > 0:
        logger.info(f"[VISION] Created task {task_id} with {image_count} images attached")
    logger.debug(
        f"Created task {task_id} for occurrence '{agent_occurrence_id}' in channel '{channel_id}' with {image_count} images"
    )

    return task


def create_thought(
    *,
    source_task_id: str,
    agent_occurrence_id: str,
    content: str,
    correlation_id: str,
    time_service: Optional[TimeServiceProtocol] = None,
    thought_type: ThoughtType = ThoughtType.STANDARD,
    status: ThoughtStatus = ThoughtStatus.PENDING,
    channel_id: Optional[str] = None,
    round_number: int = 0,
    thought_depth: int = 0,
    parent_thought_id: Optional[str] = None,
    thought_id: Optional[str] = None,
    context: Optional[ThoughtContext] = None,
    is_seed: bool = False,
    images: Optional[List[ImageContent]] = None,
) -> Thought:
    """
    Create a Thought with proper occurrence_id handling.

    Args:
        source_task_id: Task this thought belongs to
        agent_occurrence_id: Occurrence ID that owns this thought (required, no default)
        content: Thought content
        correlation_id: Correlation ID for tracing (required)
        time_service: Time service for timestamps (uses UTC if None)
        thought_type: Type of thought (default: STANDARD)
        status: Thought status (default: PENDING)
        channel_id: Channel context
        round_number: Processing round number (default: 0)
        thought_depth: Depth in thought tree (default: 0)
        parent_thought_id: Parent thought if this is a follow-up
        thought_id: Optional explicit thought_id (generates if None)
        context: Optional pre-built ThoughtContext (will be validated)
        is_seed: Whether this is a seed thought for task
        images: Optional list of images for multimodal thoughts

    Returns:
        Thought with proper occurrence_id in both thought and context

    Example:
        thought = create_thought(
            source_task_id="task_123",
            agent_occurrence_id="002",
            content="Processing user request...",
            correlation_id="msg_abc",
            time_service=time_service,
            channel_id="discord_123456",
        )
    """
    if not agent_occurrence_id:
        raise ValueError("agent_occurrence_id is required and cannot be empty")

    if not correlation_id:
        raise ValueError("correlation_id is required and cannot be empty")

    # Generate thought_id if not provided
    if thought_id is None:
        thought_id = generate_thought_id(
            thought_type=thought_type,
            task_id=source_task_id,
            is_seed=is_seed,
        )

    now_iso = time_service.now_iso() if time_service else datetime.now(timezone.utc).isoformat()

    # Build or verify context - ThoughtContext requires correlation_id
    if context is None:
        # Create new context with required fields
        context = ThoughtContext(
            task_id=source_task_id,
            channel_id=channel_id,
            round_number=round_number,
            depth=thought_depth,
            parent_thought_id=parent_thought_id,
            correlation_id=correlation_id,
            agent_occurrence_id=agent_occurrence_id,
        )
    else:
        # Verify existing context has correct occurrence_id
        if context.agent_occurrence_id != agent_occurrence_id:
            logger.warning(
                f"Context occurrence_id '{context.agent_occurrence_id}' doesn't match thought occurrence_id '{agent_occurrence_id}' - overwriting"
            )
            # Cannot modify Pydantic model after creation, must recreate
            context = ThoughtContext(
                task_id=context.task_id,
                channel_id=context.channel_id,
                round_number=context.round_number,
                depth=context.depth,
                parent_thought_id=context.parent_thought_id,
                correlation_id=context.correlation_id,
                agent_occurrence_id=agent_occurrence_id,  # Override with correct one
            )

    thought = Thought(
        thought_id=thought_id,
        source_task_id=source_task_id,
        agent_occurrence_id=agent_occurrence_id,
        channel_id=channel_id,
        thought_type=thought_type,
        status=status,
        created_at=now_iso,
        updated_at=now_iso,
        round_number=round_number,
        content=content,
        thought_depth=thought_depth,
        parent_thought_id=parent_thought_id,
        context=context,
        images=images or [],
    )

    image_count = len(images) if images else 0
    if image_count > 0:
        logger.info(f"[VISION] Created thought {thought_id} with {image_count} images inherited from task")
    logger.debug(
        f"Created {thought_type.value} thought {thought_id} for task {source_task_id}, occurrence '{agent_occurrence_id}', round {round_number}, with {image_count} images"
    )

    return thought


def create_seed_thought_for_task(
    *,
    task: Task,
    time_service: Optional[TimeServiceProtocol] = None,
    round_number: int = 0,
) -> Thought:
    """
    Create a seed thought for a task, inheriting occurrence_id and context from task.

    This is a convenience wrapper around create_thought() that properly inherits
    all context from the task, including occurrence_id.

    Args:
        task: Task to create seed thought for
        time_service: Time service for timestamps
        round_number: Starting round number (default: 0)

    Returns:
        Seed thought with occurrence_id inherited from task

    Example:
        seed_thought = create_seed_thought_for_task(
            task=task,
            time_service=time_service,
        )
    """
    # Extract channel_id from task
    channel_id: Optional[str] = None
    if task.context and hasattr(task.context, "channel_id"):
        channel_id = task.context.channel_id
    elif task.channel_id:
        channel_id = task.channel_id

    # Extract correlation_id from task context
    correlation_id = str(uuid.uuid4())
    if task.context and hasattr(task.context, "correlation_id"):
        correlation_id = task.context.correlation_id

    # Build thought context from task context
    thought_context = ThoughtContext(
        task_id=task.task_id,
        channel_id=channel_id,
        round_number=round_number,
        depth=0,
        parent_thought_id=None,
        correlation_id=correlation_id,
        agent_occurrence_id=task.agent_occurrence_id,  # Inherit from task
    )

    return create_thought(
        source_task_id=task.task_id,
        agent_occurrence_id=task.agent_occurrence_id,  # Inherit from task
        content=task.description,
        correlation_id=correlation_id,
        time_service=time_service,
        thought_type=ThoughtType.STANDARD,
        status=ThoughtStatus.PENDING,
        channel_id=channel_id,
        round_number=round_number,
        thought_depth=0,
        parent_thought_id=None,
        context=thought_context,
        is_seed=True,
        images=task.images,  # Inherit images from task
    )


def create_follow_up_thought(
    *,
    parent_thought: Thought,
    content: str,
    time_service: Optional[TimeServiceProtocol] = None,
    thought_type: ThoughtType = ThoughtType.STANDARD,
    increment_round: bool = True,
    increment_depth: bool = False,
) -> Thought:
    """
    Create a follow-up thought from a parent thought, inheriting occurrence_id and context.

    Args:
        parent_thought: Parent thought to build from
        content: New thought content
        time_service: Time service for timestamps
        thought_type: Type of follow-up thought
        increment_round: Whether to increment round_number (default: True)
        increment_depth: Whether to increment thought_depth (default: False)

    Returns:
        Follow-up thought with occurrence_id inherited from parent

    Example:
        follow_up = create_follow_up_thought(
            parent_thought=original_thought,
            content="Continuing from previous thought...",
            time_service=time_service,
        )
    """
    # Inherit values from parent
    round_number = parent_thought.round_number + 1 if increment_round else parent_thought.round_number
    # CRITICAL: Always cap thought_depth at 7 (max allowed by schema)
    raw_depth = parent_thought.thought_depth + 1 if increment_depth else parent_thought.thought_depth
    thought_depth = min(raw_depth, 7)

    # Copy parent context and update for follow-up
    follow_up_context = None
    if parent_thought.context:
        # Create new context based on parent
        correlation_id = (
            parent_thought.context.correlation_id
            if hasattr(parent_thought.context, "correlation_id")
            else str(uuid.uuid4())
        )
        follow_up_context = ThoughtContext(
            task_id=parent_thought.source_task_id,
            channel_id=parent_thought.channel_id,
            round_number=round_number,
            depth=thought_depth,
            parent_thought_id=parent_thought.thought_id,
            correlation_id=correlation_id,
            agent_occurrence_id=parent_thought.agent_occurrence_id,  # Inherit from parent
        )

    # Extract correlation_id from parent
    correlation_id = parent_thought.context.correlation_id if parent_thought.context else str(uuid.uuid4())

    return create_thought(
        source_task_id=parent_thought.source_task_id,
        agent_occurrence_id=parent_thought.agent_occurrence_id,  # Inherit from parent
        content=content,
        correlation_id=correlation_id,
        time_service=time_service,
        thought_type=thought_type,
        status=ThoughtStatus.PENDING,
        channel_id=parent_thought.channel_id,
        round_number=round_number,
        thought_depth=thought_depth,
        parent_thought_id=parent_thought.thought_id,
        context=follow_up_context,
        is_seed=False,
        images=parent_thought.images,  # Inherit images from parent thought
    )


__all__ = [
    "create_task",
    "create_thought",
    "create_seed_thought_for_task",
    "create_follow_up_thought",
]
