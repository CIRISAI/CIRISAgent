"""
Round Complete Phase - H3ERE Pipeline Step 11.

Finalizes the processing round, updates metrics, and prepares for the next round.
"""

import logging
from typing import Any, Optional

from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.services.runtime_control import StepPoint

logger = logging.getLogger(__name__)


class RoundCompletePhase:
    """
    Phase 11: Round Complete

    Finalizes the processing round:
    - Updates round metrics
    - Cleans up round-specific resources
    - Prepares for next processing round
    """

    @streaming_step(StepPoint.ROUND_COMPLETE)
    @step_point(StepPoint.ROUND_COMPLETE)
    async def _round_complete_step(self, thought_item: ProcessingQueueItem, final_result: Any) -> Any:
        """Step 11: Finalize round and update metrics."""

        # Log round completion
        logger.info(f"Round complete for thought {thought_item.thought_id}")

        # Update round metrics if telemetry service is available
        if hasattr(self, "telemetry_service") and self.telemetry_service:
            try:
                await self.telemetry_service.record_metric(
                    "round_completed",
                    value=1.0,
                    tags={
                        "thought_id": thought_item.thought_id,
                        "round_number": str(getattr(self, "current_round_number", 0)),
                        "final_action": final_result.final_action.selected_action.value if final_result else "none",
                    },
                )
            except Exception as e:
                logger.error(f"Error recording round completion metric: {e}")
                # Don't let telemetry errors break the round completion

        # Return the final result unchanged
        return final_result
