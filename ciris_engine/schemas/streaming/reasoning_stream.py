"""
Reasoning stream for H3ERE pipeline.

9 event types for monitoring pipeline execution:
- 7 pipeline events (always emitted; one per H3ERE step)
- 1 optional pipeline event (TSASPDMA_RESULT, only when TOOL selected)
- 1 sub-pipeline event (LLM_CALL, fires N times per pipeline event — see
  FSD/TRACE_EVENT_LOG_PERSISTENCE.md §5.2)

Pure data events, no UI metadata (SVG locations, etc).
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.services.runtime_control import (
    ActionResultEvent,
    ASPDMAResultEvent,
    ConscienceResultEvent,
    DMAResultsEvent,
    IDMAResultEvent,
    LLMCallEvent,
    ReasoningEvent,
    SnapshotAndContextResult,
    ThoughtStartEvent,
    TSASPDMAResultEvent,
    VerbSecondPassResultEvent,
)

# Union of all 10 reasoning event types (7 pipeline + 2 optional + 1 sub-pipeline)
ReasoningEventUnion = Union[
    ThoughtStartEvent,
    SnapshotAndContextResult,
    DMAResultsEvent,
    IDMAResultEvent,  # IDMA fragility check (always emitted after DMAs)
    ASPDMAResultEvent,
    TSASPDMAResultEvent,  # DEPRECATED legacy: Tool-specific ASPDMA (kept during transition)
    VerbSecondPassResultEvent,  # Generic verb-specific second pass — replaces TSASPDMA_RESULT
    ConscienceResultEvent,
    ActionResultEvent,
    LLMCallEvent,  # Sub-pipeline: per-provider-call observation
]


class ReasoningStreamUpdate(BaseModel):
    """A single reasoning stream update containing one or more events."""

    sequence_number: int = Field(..., description="Monotonic sequence number for ordering")
    timestamp: str = Field(..., description="Stream update timestamp")
    events: List[ReasoningEventUnion] = Field(..., description="Reasoning events in this update")


def create_reasoning_event(
    event_type: ReasoningEvent,
    thought_id: Optional[str],
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
    elif event_type == ReasoningEvent.IDMA_RESULT:
        return IDMAResultEvent(**base_data, **event_data)
    elif event_type == ReasoningEvent.ASPDMA_RESULT:
        return ASPDMAResultEvent(**base_data, **event_data)
    elif event_type == ReasoningEvent.TSASPDMA_RESULT:
        return TSASPDMAResultEvent(**base_data, **event_data)
    elif event_type == ReasoningEvent.CONSCIENCE_RESULT:
        return ConscienceResultEvent(**base_data, **event_data)
    elif event_type == ReasoningEvent.ACTION_RESULT:
        return ActionResultEvent(**base_data, **event_data)
    elif event_type == ReasoningEvent.LLM_CALL:
        # LLM_CALL events may fire from contexts where thought_id is None
        # (LLM calls outside thought processing — e.g. dream-state introspection
        # in future). Allow None to flow through; the schema permits it.
        return LLMCallEvent(**base_data, **event_data)
    elif event_type == ReasoningEvent.VERB_SECOND_PASS_RESULT:
        return VerbSecondPassResultEvent(**base_data, **event_data)
    else:
        raise ValueError(f"Unknown reasoning event type: {event_type}")


__all__ = [
    "ReasoningEvent",
    "ReasoningEventUnion",
    "ReasoningStreamUpdate",
    "ThoughtStartEvent",
    "SnapshotAndContextResult",
    "DMAResultsEvent",
    "IDMAResultEvent",
    "ASPDMAResultEvent",
    "TSASPDMAResultEvent",
    "VerbSecondPassResultEvent",
    "ConscienceResultEvent",
    "ActionResultEvent",
    "LLMCallEvent",
    "create_reasoning_event",
]
