"""
Global reasoning event streaming for H3ERE pipeline.

Provides always-on streaming of 5 simplified reasoning events with auth-gated access.
All reasoning events are broadcast to connected clients in real-time.

SECURITY: Multimodal content (images) is EXCLUDED from SSE events to prevent:
1. Large payloads causing mobile client issues
2. Visual prompt injection attacks reaching monitoring interfaces
3. Base64 data bloating SSE event sizes

Images remain available in OpenTelemetry traces for debugging purposes.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict
from weakref import WeakSet

from ciris_engine.schemas.streaming.reasoning_stream import ReasoningEventUnion, ReasoningStreamUpdate
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


def _sanitize_for_sse(data: Any) -> Any:
    """
    Remove multimodal content from SSE event data.

    SECURITY: This prevents images from being broadcast over SSE while they
    remain available in OpenTelemetry traces for debugging purposes.

    Recursively removes:
    - 'images' fields (List[ImageContent])
    - 'image_url' fields (from ImageContentBlock)
    - 'data_url' fields (base64 image data)
    - Any field containing base64 image data patterns

    Args:
        data: The data to sanitize (dict, list, or primitive)

    Returns:
        Sanitized data with multimodal content removed
    """
    if isinstance(data, dict):
        sanitized: Dict[str, Any] = {}
        for key, value in data.items():
            # Skip image-related fields entirely
            if key in ("images", "image_url", "data_url", "image_data", "image_content"):
                continue
            # Skip fields that look like base64 image data
            if isinstance(value, str) and value.startswith("data:image/"):
                continue
            # Recursively sanitize nested structures
            sanitized[key] = _sanitize_for_sse(value)
        return sanitized
    elif isinstance(data, list):
        return [_sanitize_for_sse(item) for item in data]
    else:
        # Primitives pass through unchanged
        return data


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

        # SECURITY: Remove multimodal content from SSE events
        # Images remain in OpenTelemetry traces for debugging
        update_dict = _sanitize_for_sse(update_dict)

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
