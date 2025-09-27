"""
Action Finalization Phase - H3ERE Pipeline Step 6.

Determines the final action after all processing phases complete,
handling special cases and ensuring a valid action result.
"""

import logging
from typing import Any

from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.actions.parameters import PonderParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.runtime_control import StepPoint

logger = logging.getLogger(__name__)


class ActionFinalizationPhase:
    """
    Phase 6: Action Finalization

    Determines the final action to execute:
    - Handles edge cases and special processing
    - Ensures a valid action result exists
    - Applies any final transformations
    """

    @streaming_step(StepPoint.FINALIZE_ACTION)
    @step_point(StepPoint.FINALIZE_ACTION)
    async def _finalize_action_step(self, thought_item: ProcessingQueueItem, final_result):
        """Step 5: Final action determination."""
        if not final_result:
            # If no final result, create ponder action
            return ActionSelectionDMAResult(
                selected_action=HandlerActionType.PONDER,
                action_parameters=PonderParams(
                    reason="No valid action could be determined",
                    duration_minutes=1,
                    should_generate_follow_up=True,
                ),
                rationale="Failed to determine valid action - pondering instead",
                confidence_score=0.1,
                resource_usage=None,
            )

        return final_result
