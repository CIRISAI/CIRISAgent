"""
Action Selection Phase - H3ERE Pipeline Step 3.

ASPDMA (Action Selection Powered Decision Making Algorithm) uses LLM
to synthesize the 3 parallel DMA results into a specific action selection.
"""

import logging
from typing import TYPE_CHECKING, Any

from ciris_engine.logic.dma.exceptions import DMAFailure
from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.actions.parameters import DeferParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.services.runtime_control import StepPoint

if TYPE_CHECKING:
    from ciris_engine.logic.processors.support.dma_orchestrator import DMAOrchestrator

logger = logging.getLogger(__name__)


class ActionSelectionPhase:
    """
    Phase 3: Action Selection (ASPDMA)

    Uses LLM-powered Action Selection to synthesize the 3 parallel DMA results:
    - Analyzes all DMA perspectives
    - Selects optimal action based on comprehensive analysis
    - Handles Wise Authority deferrals

    Attributes (provided by ThoughtProcessor):
        dma_orchestrator: DMA orchestration service
    """

    if TYPE_CHECKING:
        dma_orchestrator: "DMAOrchestrator"

        async def _fetch_thought(self, thought_id: str, occurrence_id: str = "default") -> Thought | None: ...
        def _create_deferral_result(self, dma_results: Any, thought: Thought) -> ActionSelectionDMAResult: ...
        def _get_profile_name(self, thought: Thought) -> str: ...

    @streaming_step(StepPoint.PERFORM_ASPDMA)
    @step_point(StepPoint.PERFORM_ASPDMA)
    async def _perform_aspdma_step(
        self, thought_item: ProcessingQueueItem, thought_context: Any, dma_results: Any
    ) -> ActionSelectionDMAResult:
        """Step 3: LLM-powered action selection."""
        thought = await self._fetch_thought(thought_item.thought_id, thought_item.agent_occurrence_id)

        # Check for WA deferral first
        if (
            dma_results
            and hasattr(dma_results, "should_defer_to_wise_authority")
            and dma_results.should_defer_to_wise_authority
        ):
            return self._create_deferral_result(dma_results, thought)  # type: ignore[arg-type]

        profile_name = self._get_profile_name(thought)  # type: ignore[arg-type]
        try:
            action_result = await self.dma_orchestrator.run_action_selection(
                thought_item=thought_item,
                actual_thought=thought,  # type: ignore[arg-type]
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
