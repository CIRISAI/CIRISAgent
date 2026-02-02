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

        Uses the same message routing as MCP server combined with API's
        event-based response waiting pattern.

        Args:
            query_text: The query text
            task_id: Task identifier

        Returns:
            The processed response
        """
        # Import the response storage from API routes
        from ciris_engine.logic.adapters.api.routes.agent import _message_responses, _response_events
        from ciris_engine.schemas.runtime.messages import IncomingMessage

        # Create unique message ID
        message_id = f"a2a_{task_id}_{self._request_count}"

        # Use "api_" prefix for channel so response routing works
        channel_id = f"api_a2a_{task_id}_{self._request_count}"

        # Create the incoming message
        message = IncomingMessage(
            message_id=message_id,
            channel_id=channel_id,
            author_id="benchmark_client",
            author_name="HE-300 Benchmark",
            content=query_text,
            is_dm=True,  # Treat as DM for direct response
        )

        # Create event for this message (same pattern as API /interact)
        event = asyncio.Event()
        _response_events[message_id] = event

        try:
            # Find the API adapter and set up message tracking
            api_adapter = self._find_api_adapter()
            on_message = None

            if api_adapter and hasattr(api_adapter, "app") and hasattr(api_adapter.app, "state"):
                app_state = api_adapter.app.state

                # Set up message_channel_map so response routing works
                message_channel_map = getattr(app_state, "message_channel_map", None)
                if message_channel_map is not None:
                    message_channel_map[channel_id] = message_id
                    logger.debug(f"A2A set up message_channel_map: {channel_id} -> {message_id}")

                # Get the on_message handler from API adapter's app state
                on_message = getattr(app_state, "on_message", None)

            # Try to submit through available handlers
            submitted = False

            # Option 1: Use API adapter's message handler (primary path)
            if on_message:
                await on_message(message)
                submitted = True
                logger.info(f"A2A message {message_id} submitted via API adapter on_message")

            # Option 2: Use runtime's message handler (fallback)
            elif self._runtime and hasattr(self._runtime, "on_message"):
                await self._runtime.on_message(message)
                submitted = True
                logger.info(f"A2A message {message_id} submitted via runtime.on_message")

            # Option 3: Use runtime's message observer if available
            elif self._runtime and hasattr(self._runtime, "message_observer"):
                observer = self._runtime.message_observer
                if observer and hasattr(observer, "handle_incoming_message"):
                    await observer.handle_incoming_message(message)
                    submitted = True
                    logger.info(f"A2A message {message_id} submitted via message_observer")

            # Option 4: Use processor's message queue if available
            elif self._runtime and hasattr(self._runtime, "processor"):
                processor = self._runtime.processor
                if processor and hasattr(processor, "submit_message"):
                    await processor.submit_message(message)
                    submitted = True
                    logger.info(f"A2A message {message_id} submitted via processor")

            if not submitted:
                raise RuntimeError("Runtime does not support message processing")

            # Wait for response (same as API /interact)
            await event.wait()

            # Get the response
            response = _message_responses.get(message_id, "Processing complete but no response captured.")
            return response

        finally:
            # Clean up
            _response_events.pop(message_id, None)
            _message_responses.pop(message_id, None)

    def _find_api_adapter(self) -> Optional[Any]:
        """Find the API adapter from runtime's adapters list."""
        if not self._runtime:
            return None

        for adapter in getattr(self._runtime, "adapters", []):
            adapter_type = getattr(adapter, "__class__", type(adapter)).__name__.lower()
            # Check for API adapter (handles ApiPlatform, APIAdapter, etc.)
            if "api" in adapter_type and "a2a" not in adapter_type:
                return adapter

        return None

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
