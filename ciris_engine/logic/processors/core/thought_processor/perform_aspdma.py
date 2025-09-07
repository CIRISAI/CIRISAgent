"""
Action Selection Phase - H3ERE Pipeline Step 3.

ASPDMA (Action Selection Powered Decision Making Algorithm) uses LLM
to synthesize the 3 parallel DMA results into a specific action selection.
"""

import logging
from typing import Any

from ciris_engine.logic.dma.exceptions import DMAFailure
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.processors.core.step_decorators import streaming_step, step_point
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.schemas.actions.parameters import DeferParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType

logger = logging.getLogger(__name__)


class ActionSelectionPhase:
    """
    Phase 3: Action Selection (ASPDMA)
    
    Uses LLM-powered Action Selection to synthesize the 3 parallel DMA results:
    - Analyzes all DMA perspectives
    - Selects optimal action based on comprehensive analysis
    - Handles Wise Authority deferrals
    """

    @streaming_step(StepPoint.PERFORM_ASPDMA)
    @step_point(StepPoint.PERFORM_ASPDMA)
    async def _perform_aspdma_step(self, thought_item: ProcessingQueueItem, thought_context, dma_results):
        """Step 3: LLM-powered action selection."""
        thought = await self._fetch_thought(thought_item.thought_id)
        
        # Check for WA deferral first
        if dma_results and hasattr(dma_results, 'should_defer_to_wise_authority') and dma_results.should_defer_to_wise_authority:
            return self._create_deferral_result(dma_results, thought)

        profile_name = self._get_profile_name(thought)
        try:
            action_result = await self.dma_orchestrator.run_action_selection(
                thought_item=thought_item,
                actual_thought=thought,
                processing_context=thought_context,  # This is the ThoughtContext
                dma_results=dma_results,
                profile_name=profile_name,
            )
            return action_result
        except DMAFailure as dma_err:
            logger.error(
                f"DMA failure during action selection for {thought_item.thought_id}: {dma_err}",
                exc_info=True,
            )
            defer_params = DeferParams(reason="DMA timeout", context={"error": str(dma_err)}, defer_until=None)
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.DEFER,
                action_parameters=defer_params,
                rationale="DMA timeout",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )