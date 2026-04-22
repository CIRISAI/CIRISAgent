"""
Action Execution Phase - H3ERE Pipeline Step 7.

Handles the final execution steps including action dispatch
and completion tracking.
"""

import logging
from typing import Any, Dict

from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class ActionExecutionPhase:
    """
    Phase 7: Action Execution

    Handles the final execution steps:
    - PERFORM_ACTION: Dispatch action to appropriate handler
    - ACTION_COMPLETE: Track completion and results
    """

    @streaming_step(StepPoint.PERFORM_ACTION)
    @step_point(StepPoint.PERFORM_ACTION)
    async def _perform_action_step(self, thought_item: ProcessingQueueItem, result: Any, context: JSONDict) -> Any:
        """Step 6: Dispatch action to handler."""
        # This step is handled by base_processor dispatch_action method
        # Just pass through the result - actual dispatch happens after this
        return result

    @streaming_step(StepPoint.ACTION_COMPLETE)
    @step_point(StepPoint.ACTION_COMPLETE)
    async def _action_complete_step(self, thought_item: ProcessingQueueItem, dispatch_result: Any) -> JSONDict:
        """Step 7: Action execution completed."""
        # This step is handled by base_processor after dispatch
        # Mark the completion status
        return {
            "thought_id": thought_item.thought_id,
            "action_completed": True,
            "dispatch_success": dispatch_result.get("success", True) if isinstance(dispatch_result, dict) else True,
            "execution_time_ms": (
                dispatch_result.get("execution_time_ms", 0.0) if isinstance(dispatch_result, dict) else 0.0
            ),
        }
