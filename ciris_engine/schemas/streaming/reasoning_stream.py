"""
Simplified reasoning stream for H3ERE pipeline.

6 clear result events, no UI metadata (SVG locations, etc).
Pure data events for monitoring pipeline execution.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.services.runtime_control import (
    ActionResultEvent,
    ASPDMAResultEvent,
    ConscienceResultEvent,
    DMAResultsEvent,
    ReasoningEvent,
    SnapshotAndContextResult,
    ThoughtStartEvent,
)

# Union of all 6 reasoning event types
ReasoningEventUnion = Union[
    ThoughtStartEvent,
    SnapshotAndContextResult,
    DMAResultsEvent,
    ASPDMAResultEvent,
    ConscienceResultEvent,
    ActionResultEvent,
]


class ReasoningStreamUpdate(BaseModel):
    """A single reasoning stream update containing one or more events."""

    sequence_number: int = Field(..., description="Monotonic sequence number for ordering")
    timestamp: str = Field(..., description="Stream update timestamp")
    events: List[ReasoningEventUnion] = Field(..., description="Reasoning events in this update")


def create_reasoning_event(
    event_type: ReasoningEvent,
    thought_id: str,
    task_id: Optional[str],
    timestamp: str,
    **event_data: Any,
) -> ReasoningEventUnion:
    """
    Create a typed reasoning event.

    Args:
        event_type: Type of reasoning event
        thought_id: Thought being processed
        task_id: Parent task if any
        timestamp: Event timestamp
        **event_data: Event-specific data

    Returns:
        Typed reasoning event
    """
    base_data = {
        "thought_id": thought_id,
        "task_id": task_id,
        "timestamp": timestamp,
    }

    if event_type == ReasoningEvent.THOUGHT_START:
        return ThoughtStartEvent(**base_data, **event_data)
    elif event_type == ReasoningEvent.SNAPSHOT_AND_CONTEXT:
        return SnapshotAndContextResult(**base_data, **event_data)
    elif event_type == ReasoningEvent.DMA_RESULTS:
        return DMAResultsEvent(**base_data, **event_data)
    elif event_type == ReasoningEvent.ASPDMA_RESULT:
        return ASPDMAResultEvent(**base_data, **event_data)
    elif event_type == ReasoningEvent.CONSCIENCE_RESULT:
        return ConscienceResultEvent(**base_data, **event_data)
    elif event_type == ReasoningEvent.ACTION_RESULT:
        return ActionResultEvent(**base_data, **event_data)
    else:
        raise ValueError(f"Unknown reasoning event type: {event_type}")


__all__ = [
    "ReasoningEvent",
    "ReasoningEventUnion",
    "ReasoningStreamUpdate",
    "ThoughtStartEvent",
    "SnapshotAndContextResult",
    "DMAResultsEvent",
    "ASPDMAResultEvent",
    "ConscienceResultEvent",
    "ActionResultEvent",
    "create_reasoning_event",
]
