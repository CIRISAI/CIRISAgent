"""
A2A Service for handling Agent-to-Agent protocol requests.

This service routes ethical evaluation requests through the full CIRIS pipeline,
using the benchmark template for optimized ethical reasoning.
"""

import asyncio
import logging
from typing import Any, Optional

from ciris_engine.logic.adapters.base import Service

logger = logging.getLogger(__name__)


class A2AService(Service):
    """Service for handling A2A protocol requests.

    Routes requests through the CIRIS pipeline for ethical evaluation.
    Optimized for high-concurrency benchmarking scenarios.
    """

    def __init__(
        self,
        runtime: Optional[Any] = None,
        timeout_seconds: float = 60.0,
        **kwargs: Any,
    ) -> None:
        """Initialize A2A service.

        Args:
            runtime: CIRIS runtime for pipeline access
            timeout_seconds: Timeout for processing
            **kwargs: Additional configuration
        """
        super().__init__(config=kwargs.get("config"))
        self._runtime = runtime
        self._timeout = timeout_seconds
        self._request_count = 0
        self._error_count = 0
        self._running = False

    async def start(self) -> None:
        """Start the A2A service."""
        logger.info("A2A service started")
        self._running = True

    async def stop(self) -> None:
        """Stop the A2A service."""
        logger.info(f"A2A service stopped. Processed {self._request_count} requests, {self._error_count} errors")
        self._running = False

    def set_runtime(self, runtime: Any) -> None:
        """Set the CIRIS runtime for pipeline access.

        Args:
            runtime: CIRIS runtime instance
        """
        self._runtime = runtime

    async def process_ethical_query(self, query_text: str, task_id: str = "benchmark") -> str:
        """Process an ethical query through the CIRIS pipeline.

        Args:
            query_text: The ethical scenario/question text
            task_id: Task identifier for tracking

        Returns:
            The agent's response (yes/no with optional explanation)

        Raises:
            RuntimeError: If runtime is not available
            asyncio.TimeoutError: If processing times out
        """
        self._request_count += 1

        if self._runtime is None:
            self._error_count += 1
            raise RuntimeError("CIRIS runtime not available")

        try:
            # Route through CIRIS pipeline via message handler
            response = await asyncio.wait_for(
                self._process_through_pipeline(query_text, task_id),
                timeout=self._timeout,
            )
            return response

        except asyncio.TimeoutError:
            self._error_count += 1
            logger.error(f"A2A pipeline processing timed out after {self._timeout}s")
            raise
        except Exception as e:
            self._error_count += 1
            logger.error(f"A2A pipeline processing failed: {e}")
            raise

    async def _process_through_pipeline(self, query_text: str, task_id: str) -> str:
        """Process query through the CIRIS pipeline.

        Args:
            query_text: The query text
            task_id: Task identifier

        Returns:
            The processed response
        """
        # Create incoming message for the pipeline
        from ciris_engine.schemas.runtime.messages import IncomingMessage

        message = IncomingMessage(
            message_id=f"a2a_{task_id}_{self._request_count}",
            channel_id="a2a_benchmark",
            author_id="benchmark_client",
            author_name="HE-300 Benchmark",
            content=query_text,
            is_dm=True,  # Treat as DM for direct response
        )

        # Process through runtime's message handler
        if hasattr(self._runtime, "process_message"):
            result = await self._runtime.process_message(message)
            if hasattr(result, "response"):
                return result.response
            return str(result)
        elif hasattr(self._runtime, "message_handler"):
            result = await self._runtime.message_handler.handle(message)
            if hasattr(result, "response"):
                return result.response
            return str(result)
        else:
            raise RuntimeError("Runtime does not support message processing")

    def get_metrics(self) -> dict[str, Any]:
        """Get service metrics.

        Returns:
            Dictionary with request count, error count, etc.
        """
        return {
            "request_count": self._request_count,
            "error_count": self._error_count,
            "running": self._running,
        }
