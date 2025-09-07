"""
Context Gathering Phase - H3ERE Pipeline Step 1.

Responsible for building the ThoughtContext that provides necessary
background information for DMA processing.
"""

import logging
from typing import Optional, Any

from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.processors.core.step_decorators import streaming_step, step_point
from ciris_engine.schemas.services.runtime_control import StepPoint

logger = logging.getLogger(__name__)


class ContextGatheringPhase:
    """
    Phase 1: Context Gathering
    
    Builds comprehensive context for thought processing including:
    - User context and permissions
    - Conversation history
    - Task-specific context
    - Environmental state
    """

    @streaming_step(StepPoint.GATHER_CONTEXT)
    @step_point(StepPoint.GATHER_CONTEXT)
    async def _gather_context_step(self, thought_item: ProcessingQueueItem, context: Optional[dict] = None):
        """Step 1: Build context for DMA processing."""
        thought = await self._fetch_thought(thought_item.thought_id)
        
        batch_context_data = context.get("batch_context") if context else None
        if batch_context_data:
            logger.debug(f"Using batch context for thought {thought_item.thought_id}")
            from ciris_engine.logic.context.batch_context import build_system_snapshot_with_batch

            system_snapshot = await build_system_snapshot_with_batch(
                task=None,
                thought=thought,
                batch_data=batch_context_data,
                memory_service=self.context_builder.memory_service if self.context_builder else None,
                graphql_provider=None,
            )
            thought_context = await self.context_builder.build_thought_context(thought, system_snapshot=system_snapshot)
        else:
            logger.debug(f"Building full context for thought {thought_item.thought_id} (no batch context)")
            thought_context = await self.context_builder.build_thought_context(thought)
        
        # Store context on queue item
        if hasattr(thought_context, "model_dump"):
            thought_item.initial_context = thought_context.model_dump()
        else:
            thought_item.initial_context = thought_context
            
        return thought_context