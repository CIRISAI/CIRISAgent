import uuid
import logging

from ciris_engine.schemas.runtime.models import Thought
from ciris_engine.schemas.runtime.enums import ThoughtStatus, ThoughtType
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)

def create_follow_up_thought(
    parent: Thought, 
    time_service: TimeServiceProtocol,
    content: str = "", 
    thought_type: ThoughtType = ThoughtType.FOLLOW_UP
) -> Thought:
    """Return a new Thought linked to ``parent``.

    The original Thought instance is never mutated.
    ``source_task_id`` is inherited and ``parent_thought_id`` references the
    parent thought's ID to maintain lineage.
    """
    now = time_service.now().isoformat()
    parent_round = parent.round_number if hasattr(parent, 'round_number') else 0
    
    # Just copy the context directly - channel_id flows through the schemas
    follow_up = Thought(
        thought_id=str(uuid.uuid4()),
        source_task_id=parent.source_task_id,
        thought_type=thought_type,
        status=ThoughtStatus.PENDING,
        created_at=now,
        updated_at=now,
        round_number=parent_round,
        content=content,
        context=parent.context.model_copy() if parent.context else None,
        thought_depth=parent.thought_depth + 1,
        ponder_notes=None,
        parent_thought_id=parent.thought_id,
        final_action=None,
    )
    return follow_up
