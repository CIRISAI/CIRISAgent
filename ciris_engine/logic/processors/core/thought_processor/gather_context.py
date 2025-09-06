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
    async def _gather_context_step(
        self, thought_item: ProcessingQueueItem, context: Optional[dict] = None
    ):
        """
        Step 1: Build comprehensive context for thought processing.
        
        This decorated method automatically handles:
        - Real-time streaming of context building progress
        - Single-step pause/resume capability
        - Proper error handling and reporting
        
        Args:
            thought_item: The thought being processed
            context: Optional initial context dict
            
        Returns:
            ThoughtContext: Complete context for DMA processing
        """
        logger.debug(f"Building context for thought {thought_item.thought_id}")

        # Build comprehensive thought context
        thought_context = await self.context_builder.build_context(
            thought_item=thought_item, 
            initial_context=context
        )

        # Store context on thought item for later phases
        if hasattr(thought_item, 'set_initial_context'):
            thought_item.set_initial_context(thought_context)
        elif hasattr(thought_item, 'initial_context'):
            thought_item.initial_context = thought_context
            
        logger.info(f"Context built for thought {thought_item.thought_id}")
        return thought_context