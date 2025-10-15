"""
Global reasoning event streaming for H3ERE pipeline.

Provides always-on streaming of 5 simplified reasoning events with auth-gated access.
All reasoning events are broadcast to connected clients in real-time.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict
from weakref import WeakSet

from ciris_engine.schemas.streaming.reasoning_stream import ReasoningEventUnion, ReasoningStreamUpdate
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class ReasoningEventStream:
    """Global broadcaster for H3ERE reasoning events (5 simplified events only)."""

    def __init__(self) -> None:
        self._subscribers: WeakSet[asyncio.Queue[Any]] = WeakSet()
        self._sequence_number = 0
        self._is_enabled = True

    def subscribe(self, queue: asyncio.Queue[Any]) -> None:
        """Subscribe a queue to receive reasoning events."""
        self._subscribers.add(queue)
        logger.debug(f"New subscriber added, total: {len(self._subscribers)}")

    def unsubscribe(self, queue: asyncio.Queue[Any]) -> None:
        """Unsubscribe a queue from reasoning events."""
        self._subscribers.discard(queue)
        logger.debug(f"Subscriber removed, total: {len(self._subscribers)}")

    async def broadcast_reasoning_event(self, event: ReasoningEventUnion) -> None:
        """
        Broadcast a reasoning event to all connected subscribers.

        Args:
            event: One of the 5 reasoning events (SNAPSHOT_AND_CONTEXT, DMA_RESULTS, etc)
        """
        if not self._is_enabled or not self._subscribers:
            return

        self._sequence_number += 1

        # Wrap event in stream update
        stream_update = ReasoningStreamUpdate(
            sequence_number=self._sequence_number,
            timestamp=datetime.now().isoformat(),
            events=[event],
        )

        # Convert to dict for JSON serialization
        update_dict = stream_update.model_dump()

        # Broadcast to all subscribers
        dead_queues = []
        for queue in self._subscribers:
            try:
                # Use put_nowait to avoid blocking
                queue.put_nowait(update_dict)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue is full, dropping reasoning event")
            except Exception as e:
                logger.error(f"Error broadcasting to subscriber: {e}")
                dead_queues.append(queue)

        # Clean up dead queues
        for queue in dead_queues:
            self._subscribers.discard(queue)

        logger.debug(
            f"Broadcasted {event.event_type} event #{self._sequence_number} to {len(self._subscribers)} subscribers"
        )

    def get_stats(self) -> JSONDict:
        """Get streaming statistics."""
        return {
            "enabled": self._is_enabled,
            "subscriber_count": len(self._subscribers),
            "events_broadcast": self._sequence_number,
        }

    def enable(self) -> None:
        """Enable reasoning event streaming."""
        self._is_enabled = True
        logger.info("Reasoning event streaming enabled")

    def disable(self) -> None:
        """Disable reasoning event streaming."""
        self._is_enabled = False
        logger.info("Reasoning event streaming disabled")


# Global instance
reasoning_event_stream = ReasoningEventStream()
