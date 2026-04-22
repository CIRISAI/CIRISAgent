"""
DMA Execution Phase - H3ERE Pipeline Step 2.

Responsible for running 3 Decision Making Algorithms (DMAs) to gather
comprehensive multi-perspective analysis before action selection.
"""

import logging
from typing import TYPE_CHECKING, Any, Union

from ciris_engine.logic.dma.exceptions import DMAFailure
from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.actions.parameters import DeferParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.runtime_control import StepPoint

if TYPE_CHECKING:
    from ciris_engine.logic.processors.support.dma_orchestrator import DMAOrchestrator
    from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol

logger = logging.getLogger(__name__)


class DMAExecutionPhase:
    """
    Phase 2: DMA Execution

    Runs 3 Decision Making Algorithms in parallel through the DMA orchestrator:
    - 3 parallel DMAs for comprehensive analysis
    - Multi-perspective decision insights
    - Preparation for action selection

    Attributes (provided by ThoughtProcessor):
        dma_orchestrator: DMA orchestration service
        telemetry_service: Optional telemetry service for metrics
    """

    if TYPE_CHECKING:
        dma_orchestrator: "DMAOrchestrator"
        telemetry_service: "TelemetryServiceProtocol | None"

    @streaming_step(StepPoint.PERFORM_DMAS)
    @step_point(StepPoint.PERFORM_DMAS)
    async def _perform_dmas_step(
        self, thought_item: ProcessingQueueItem, thought_context: Any
    ) -> Union[Any, ActionSelectionDMAResult]:
        """
        Step 2: Execute 3 parallel Decision Making Algorithms.

        This decorated method automatically handles:
        - Real-time streaming of DMA execution progress
        - Single-step pause/resume capability
        - Comprehensive error handling with deferral
        - Telemetry recording for critical failures

        Args:
            thought_item: The thought being processed
            thought_context: Context built in previous step

        Returns:
            DMA results (from 3 parallel algorithms) or ActionSelectionDMAResult (deferral on failure)
        """
        try:
            logger.debug(f"Starting DMA execution for thought {thought_item.thought_id}")

            dma_results = await self.dma_orchestrator.run_initial_dmas(
                thought_item=thought_item,
                processing_context=thought_context,
            )

            logger.info(f"DMA execution completed for thought {thought_item.thought_id}")
            return dma_results

        except DMAFailure as dma_err:
            logger.error(
                f"DMA failure during initial processing for {thought_item.thought_id}: {dma_err}",
                exc_info=True,
            )

            # Record telemetry for critical DMA failure
            if self.telemetry_service:
                await self.telemetry_service.record_metric(
                    "dma_failure",
                    value=1.0,
                    tags={
                        "thought_id": thought_item.thought_id,
                        "error": str(dma_err)[:100],
                        "path_type": "critical",  # Critical failure
                        "source_module": "thought_processor",
                    },
                )

            # Return deferral result for DMA failures
            defer_params = DeferParams(reason="DMA timeout", context={"error": str(dma_err)}, defer_until=None)

            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.DEFER,
                action_parameters=defer_params,
                rationale=f"DMA failure: {dma_err}",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )
