"""
Global step result streaming for H3ERE pipeline.

Provides always-on streaming of step results with auth-gated access.
All step results are broadcast to connected clients in real-time.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Set
from weakref import WeakSet

from ciris_engine.schemas.services.runtime_control import StepResultData

logger = logging.getLogger(__name__)


class StepResultStream:
    """Global broadcaster for H3ERE step results."""

    def __init__(self):
        self._subscribers: WeakSet = WeakSet()
        self._step_count = 0
        self._is_enabled = True

    def subscribe(self, queue: asyncio.Queue) -> None:
        """Subscribe a queue to receive step results."""
        self._subscribers.add(queue)
        logger.debug(f"New subscriber added, total: {len(self._subscribers)}")

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unsubscribe a queue from step results."""
        self._subscribers.discard(queue)
        logger.debug(f"Subscriber removed, total: {len(self._subscribers)}")

    async def broadcast_step_result(self, step_result: StepResultData) -> None:
        """
        Broadcast a step result to all connected subscribers.

        Args:
            step_result: Typed step result from pipeline controller
        """
        if not self._is_enabled or not self._subscribers:
            return

        self._step_count += 1

        # Convert typed step result to UI-friendly stream update
        from ciris_engine.schemas.streaming.reasoning_stream import create_stream_update_from_step_results

        stream_update = create_stream_update_from_step_results(
            step_results=[step_result], stream_sequence=self._step_count
        )

        # Convert to dict for JSON serialization
        enriched_result = stream_update.model_dump()
        enriched_result.update(
            {"broadcast_timestamp": datetime.now().isoformat(), "subscriber_count": len(self._subscribers)}
        )

        # Broadcast to all subscribers
        dead_queues = []
        for queue in self._subscribers:
            try:
                # Use put_nowait to avoid blocking
                queue.put_nowait(enriched_result)
            except asyncio.QueueFull:
                logger.warning("Subscriber queue is full, dropping step result")
            except Exception as e:
                logger.error(f"Error broadcasting to subscriber: {e}")
                dead_queues.append(queue)

        # Clean up dead queues
        for queue in dead_queues:
            self._subscribers.discard(queue)

        logger.debug(f"Broadcasted step result {self._step_count} to {len(self._subscribers)} subscribers")

    def get_stats(self) -> Dict[str, Any]:
        """Get streaming statistics."""
        return {
            "enabled": self._is_enabled,
            "subscriber_count": len(self._subscribers),
            "steps_broadcast": self._step_count,
        }

    def enable(self) -> None:
        """Enable step result streaming."""
        self._is_enabled = True
        logger.info("Step result streaming enabled")

    def disable(self) -> None:
        """Disable step result streaming."""
        self._is_enabled = False
        logger.info("Step result streaming disabled")


# Global instance
step_result_stream = StepResultStream()
