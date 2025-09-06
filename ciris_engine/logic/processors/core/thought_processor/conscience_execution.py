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
        """
        Step 4: Apply ethical safety validation to selected action.
        
        This decorated method automatically handles:
        - Real-time streaming of conscience validation progress
        - Single-step pause/resume capability
        - Comprehensive conscience result processing
        
        Args:
            thought_item: The thought being processed
            action_result: Action selected in ASPDMA step
            
        Returns:
            Conscience result with validation outcome and any overrides
        """
        if not action_result:
            logger.warning(f"No action result to validate for thought {thought_item.thought_id}")
            return action_result
            
        try:
            logger.debug(f"Applying consciences for thought {thought_item.thought_id}")
            
            # Apply all registered consciences to the selected action
            conscience_results = await self.conscience_registry.apply_all_consciences(
                action_result, thought_item
            )
            
            logger.info(f"Conscience validation completed for thought {thought_item.thought_id}")
            return conscience_results
            
        except Exception as e:
            logger.error(f"Conscience execution failed for thought {thought_item.thought_id}: {e}")
            # Return the original action if conscience fails
            return action_result