"""
Action Finalization Phase - H3ERE Pipeline Step 6.

Determines the final action after all processing phases complete,
handling special cases and ensuring a valid action result.
"""

import logging
from typing import TYPE_CHECKING, Any

from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.actions.parameters import PonderParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.runtime_control import StepPoint

if TYPE_CHECKING:
    from ciris_engine.schemas.processors.core import ConscienceApplicationResult

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
    async def _finalize_action_step(
        self, thought_item: ProcessingQueueItem, conscience_result: Any
    ) -> "ConscienceApplicationResult":
        """Step 5: Final action determination with full conscience data."""
        # Import here to avoid circular imports
        from ciris_engine.schemas.processors.core import ConscienceApplicationResult

        if not conscience_result:
            # If no conscience result, create ponder action and wrap in ConscienceApplicationResult
            from ciris_engine.schemas.conscience.core import EpistemicData

            ponder_action = ActionSelectionDMAResult(
                selected_action=HandlerActionType.PONDER,
                action_parameters=PonderParams(questions=["No valid action could be determined - what should I do?"]),
                rationale="Failed to determine valid action - pondering instead",
                resource_usage=None,
            )
            return ConscienceApplicationResult(
                original_action=ponder_action,
                final_action=ponder_action,
                overridden=False,
                override_reason=None,
                epistemic_data=EpistemicData(
                    entropy_level=0.5,  # Moderate uncertainty
                    coherence_level=0.5,  # Moderate coherence
                    uncertainty_acknowledged=True,  # System is aware of failure
                    reasoning_transparency=1.0,  # Fully transparent about the issue
                ),
            )

        return conscience_result  # type: ignore[no-any-return]
