import logging
from typing import TYPE_CHECKING, Any, Dict

from ciris_engine.schemas.runtime.enums import ThoughtStatus
from ciris_engine.schemas.runtime.models import Thought

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)

__all__ = [
    "escalate_due_to_action_limit",
    "escalate_due_to_sla",
    "escalate_due_to_conscience",
    "escalate_due_to_failure",
    "escalate_dma_failure",
    "escalate_due_to_max_thought_rounds",
]


def _append_escalation(thought: Thought, event: Dict[str, str]) -> Thought:
    """Append an escalation event to the thought (no-op for v1 schema)."""
    # Escalation events are not tracked in v1 schema.
    return thought


def escalate_due_to_action_limit(thought: Thought, reason: str, time_service: "TimeServiceProtocol") -> Thought:
    """Escalate when a thought exceeds its action limit."""
    now = time_service.now().isoformat()
    event = {
        "timestamp": now,
        "reason": reason,
        "type": "action_limit",
    }
    return _append_escalation(thought, event)


def escalate_due_to_sla(thought: Thought, reason: str, time_service: "TimeServiceProtocol") -> Thought:
    """Escalate when a thought breaches its SLA."""
    now = time_service.now().isoformat()
    event = {
        "timestamp": now,
        "reason": reason,
        "type": "sla_breach",
    }
    return _append_escalation(thought, event)


def escalate_due_to_conscience(thought: Thought, reason: str, time_service: "TimeServiceProtocol") -> Thought:
    """Escalate when a conscience violation occurs."""
    now = time_service.now().isoformat()
    event = {
        "timestamp": now,
        "reason": reason,
        "type": "conscience_violation",
    }
    return _append_escalation(thought, event)


def escalate_due_to_failure(thought: Thought, reason: str, time_service: "TimeServiceProtocol") -> Thought:
    """Escalate due to internal failure or deferral."""
    now = time_service.now().isoformat()
    event = {
        "timestamp": now,
        "reason": reason,
        "type": "internal_failure",
    }
    return _append_escalation(thought, event)


def escalate_dma_failure(
    thought: Any, dma_name: str, error: Exception, retry_limit: int, time_service: "TimeServiceProtocol"
) -> None:
    """Escalate when a DMA repeatedly fails.

    Supports both ``Thought`` objects and ``ProcessingQueueItem``s. When a queue
    item is provided we update the persisted ``Thought`` directly via the
    persistence layer.
    """

    from ciris_engine.logic import persistence
    from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem

    now = time_service.now().isoformat()
    reason = f"DMA failed after {retry_limit} attempts: {error}"
    event = {
        "timestamp": now,
        "dma": dma_name,
        "reason": reason,
        "type": "dma_failure",
    }

    if isinstance(thought, ProcessingQueueItem):
        persistence.update_thought_status(
            thought_id=thought.thought_id,
            status=ThoughtStatus.DEFERRED,
            final_action={"error": reason},
        )
        return

    thought.status = ThoughtStatus.DEFERRED
    _append_escalation(thought, event)


def escalate_due_to_max_thought_rounds(
    thought: Thought, max_rounds: int, time_service: "TimeServiceProtocol"
) -> Thought:
    """Escalate when a thought exceeds the allowed action rounds per thought."""
    now = time_service.now().isoformat()
    event = {
        "timestamp": now,
        "reason": f"Thought action count exceeded maximum rounds of {max_rounds}",
        "type": "max_thought_rounds",
    }
    return _append_escalation(thought, event)
