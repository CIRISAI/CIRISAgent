"""
Conscience Execution Phase - H3ERE Pipeline Step 4.

Applies ethical safety validation to the selected action using the
conscience registry to ensure alignment with ethical principles.
"""

import logging
from typing import Any, Optional

from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.logic.processors.core.step_decorators import streaming_step, step_point
from ciris_engine.schemas.services.runtime_control import StepPoint

logger = logging.getLogger(__name__)


class ConscienceExecutionPhase:
    """
    Phase 4: Conscience Execution
    
    Applies ethical safety validation through conscience registry:
    - Validates selected action against ethical principles
    - Can override actions that fail safety checks
    - Provides guidance for retry attempts
    """

    @streaming_step(StepPoint.CONSCIENCE_EXECUTION)
    @step_point(StepPoint.CONSCIENCE_EXECUTION)
    async def _conscience_execution_step(self, thought_item: ProcessingQueueItem, action_result):
        """Step 4: Ethical safety validation."""
        if not action_result:
            return action_result
            
        try:
            conscience_results = await self.conscience_registry.apply_all_consciences(
                action_result, thought_item
            )
            
            # Check if conscience passed
            conscience_passed = all(result.passed for result in conscience_results)
            action_result.conscience_passed = conscience_passed
            
            return action_result, conscience_results
        except Exception as e:
            logger.error(f"Conscience execution failed for thought {thought_item.thought_id}: {e}")
            return action_result, []