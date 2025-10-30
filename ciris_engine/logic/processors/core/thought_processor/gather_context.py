"""
Context Gathering Phase - H3ERE Pipeline Step 1.

Responsible for building the ThoughtContext that provides necessary
background information for DMA processing.
"""

import logging
from typing import TYPE_CHECKING, Optional

from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.processors.context import ProcessorContext
from ciris_engine.schemas.runtime.processing_context import ProcessingThoughtContext
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.context.builder import ContextBuilder
    from ciris_engine.schemas.runtime.models import Thought

logger = logging.getLogger(__name__)


class ContextGatheringPhase:
    """
    Phase 1: Context Gathering

    Builds comprehensive context for thought processing including:
    - User context and permissions
    - Conversation history
    - Task-specific context
    - Environmental state

    Mixin class - expects parent to provide:
    - context_builder: ContextBuilder
    - _fetch_thought: async method to fetch Thought by ID
    """

    # Type hints for attributes provided by ThoughtProcessor
    context_builder: "ContextBuilder"

    async def _fetch_thought(self, thought_id: str, occurrence_id: str = "default") -> Optional["Thought"]:
        """Fetch thought - implemented in ThoughtProcessor."""
        raise NotImplementedError("Must be implemented by ThoughtProcessor")

    @streaming_step(StepPoint.GATHER_CONTEXT)
    @step_point(StepPoint.GATHER_CONTEXT)
    async def _gather_context_step(
        self, thought_item: ProcessingQueueItem, context: Optional[JSONDict] = None
    ) -> ProcessingThoughtContext:
        """
        Step 1: Build context for DMA processing.

        UNIFIED BATCH APPROACH:
        - Always fetches the task from thought.source_task_id for user context
        - Always uses build_system_snapshot_with_batch (creates minimal batch if needed)
        - Ensures consistent snapshot building for both batch and single thoughts
        """
        from ciris_engine.logic import persistence
        from ciris_engine.logic.context.batch_context import build_system_snapshot_with_batch

        thought = await self._fetch_thought(thought_item.thought_id, thought_item.agent_occurrence_id)

        # Validate thought was successfully fetched
        if thought is None:
            raise ValueError(f"Failed to fetch thought {thought_item.thought_id}")

        # ALWAYS fetch task for user context extraction
        task = None
        source_task_id = getattr(thought, "source_task_id", None)
        logger.info(f"[UNIFIED CONTEXT] Thought {thought_item.thought_id} source_task_id: {source_task_id}")

        if source_task_id:
            logger.info(f"[UNIFIED CONTEXT] Fetching task {source_task_id} for user context")
            task = persistence.get_task_by_id(source_task_id)
            task_user_id = getattr(task.context, "user_id", None) if task and task.context else None
            log_msg = (
                f"Fetched task {task.task_id} with context user_id={task_user_id}"
                if task
                else f"Could not fetch task {source_task_id} for thought {thought_item.thought_id}"
            )
            log_fn = logger.info if task else logger.warning
            log_fn(f"[UNIFIED CONTEXT] {log_msg}")

        # Get pre-fetched batch context if available, otherwise will create on-demand
        batch_context_data_raw = context.get("batch_context") if context else None
        # Type narrow: batch_context could be dict or BatchContextData
        from ciris_engine.logic.context.batch_context import BatchContextData

        batch_context_data = batch_context_data_raw if isinstance(batch_context_data_raw, BatchContextData) else None

        # ALWAYS use unified batch approach
        system_snapshot = await build_system_snapshot_with_batch(
            task=task,  # Always pass task for user enrichment
            thought=thought,
            batch_data=batch_context_data,  # Pre-fetched or None (will create minimal)
            memory_service=self.context_builder.memory_service if self.context_builder else None,
            graphql_provider=None,
            time_service=self.context_builder.time_service if self.context_builder else None,
            # Additional services for on-demand batch creation
            secrets_service=self.context_builder.secrets_service if self.context_builder else None,
            service_registry=self.context_builder.service_registry if self.context_builder else None,
            resource_monitor=self.context_builder.resource_monitor if self.context_builder else None,
            telemetry_service=self.context_builder.telemetry_service if self.context_builder else None,
            runtime=self.context_builder.runtime if self.context_builder else None,
        )

        # Build thought context with the unified snapshot
        thought_context = await self.context_builder.build_thought_context(
            thought, task=task, system_snapshot=system_snapshot
        )

        # Store context on queue item
        if hasattr(thought_context, "model_dump"):
            thought_item.initial_context = thought_context.model_dump()
        else:
            thought_item.initial_context = thought_context

        return thought_context
