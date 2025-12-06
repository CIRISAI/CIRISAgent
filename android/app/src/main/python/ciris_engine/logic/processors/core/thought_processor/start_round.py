"""
Round Initialization Phase - H3ERE Pipeline Step 0.

Responsible for setting up the processing round by transitioning thoughts
from PENDING to PROCESSING status and preparing them for the H3ERE pipeline.
"""

import logging
from typing import Any, Dict, Optional

from ciris_engine.logic import persistence
from ciris_engine.logic.processors.core.step_decorators import step_point, streaming_step
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem
from ciris_engine.schemas.runtime.enums import ThoughtStatus
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class RoundInitializationPhase:
    """
    Phase 0: Round Initialization

    Sets up the processing round by:
    - Moving thoughts from PENDING to PROCESSING status
    - Creating ProcessingQueueItem objects for pipeline execution
    - Preparing thoughts for H3ERE pipeline entry
    """

    @streaming_step(StepPoint.START_ROUND)
    @step_point(StepPoint.START_ROUND)
    async def _start_round_step(
        self, thought_item: ProcessingQueueItem, context: Optional[JSONDict] = None
    ) -> JSONDict:
        """Step 0: Initialize processing round and prepare thoughts for H3ERE pipeline."""

        # Get the thought ID and occurrence_id from the queue item
        thought_id = thought_item.thought_id
        occurrence_id = thought_item.agent_occurrence_id
        logger.debug(f"Starting round for thought {thought_id} (occurrence: {occurrence_id})")

        # Fetch the full Thought object from persistence
        full_thought = persistence.get_thought_by_id(thought_id, occurrence_id)
        if not full_thought:
            raise RuntimeError(
                f"Could not fetch thought {thought_id} (occurrence: {occurrence_id}) from persistence for START_ROUND"
            )

        # Update thought status from PENDING to PROCESSING
        persistence.update_thought_status(thought_id, ThoughtStatus.PROCESSING, occurrence_id)
        logger.info(f"Transitioned thought {thought_id} from PENDING to PROCESSING")

        # The ProcessingQueueItem is already created and passed in, so we just need to
        # ensure it's ready for the next phase

        return {
            "round_started": True,
            "thought_id": thought_id,
            "status_updated": "PENDING -> PROCESSING",
            "ready_for_context_gathering": True,
            "thought_type": full_thought.thought_type.value,
            "source_task_id": full_thought.source_task_id,
        }
