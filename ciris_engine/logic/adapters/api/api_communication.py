"""
Communication service for API adapter.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.protocols.services.governance.communication import CommunicationServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import FetchedMessage

if TYPE_CHECKING:
    from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus

logger = logging.getLogger(__name__)


class APICommunicationService(CommunicationServiceProtocol):
    """Communication service for API responses."""

    def __init__(self, config: Optional[Any] = None) -> None:
        """Initialize API communication service."""
        self._response_queue: asyncio.Queue = asyncio.Queue()
        self._websocket_clients: Dict[str, Any] = {}
        self._is_started = False
        self._config = config  # Store the API adapter config

        # Metrics tracking
        self._requests_handled = 0
        self._error_count = 0
        self._response_times: List[float] = []  # Track last N response times
        self._max_response_times = 100  # Keep last 100 response times
        self._start_time: Optional[datetime] = None
        self._time_service: Optional[Any] = None  # Will be injected from adapter

    async def send_message(self, channel_id: str, content: str) -> bool:
        """Send message through API response or WebSocket."""
        start_time = datetime.now(timezone.utc)
        try:
            # Create a "speak" correlation for this outgoing message
            import uuid

            from ciris_engine.logic import persistence
            from ciris_engine.schemas.telemetry.core import (
                ServiceCorrelation,
                ServiceCorrelationStatus,
                ServiceRequestData,
                ServiceResponseData,
            )

            correlation_id = str(uuid.uuid4())
            now = datetime.now(timezone.utc)

            # Create correlation for the outgoing message
            correlation = ServiceCorrelation(
                correlation_id=correlation_id,
                service_type="api",
                handler_name="APIAdapter",
                action_type="speak",
                request_data=ServiceRequestData(
                    service_type="api",
                    method_name="speak",
                    channel_id=channel_id,
                    parameters={"content": content, "channel_id": channel_id},
                    request_timestamp=now,
                ),
                response_data=ServiceResponseData(
                    success=True, result_summary="Message sent", execution_time_ms=0, response_timestamp=now
                ),
                status=ServiceCorrelationStatus.COMPLETED,
                created_at=now,
                updated_at=now,
                timestamp=now,
            )

            # Get time service if available (passed from adapter)
            time_service = getattr(self, "_time_service", None)
            persistence.add_correlation(correlation, time_service)
            logger.debug(f"Created speak correlation for channel {channel_id}")
            # If it's a WebSocket channel, send through WebSocket
            if channel_id and channel_id.startswith("ws:"):
                client_id = channel_id[3:]  # Remove "ws:" prefix
                if client_id in self._websocket_clients:
                    ws = self._websocket_clients[client_id]
                    await ws.send_json(
                        {
                            "type": "message",
                            "data": {"content": content, "timestamp": datetime.now(timezone.utc).isoformat()},
                        }
                    )
                    return True
                else:
                    logger.warning(f"WebSocket client not found: {client_id}")
                    return False

            # Otherwise, queue for HTTP response
            await self._response_queue.put({"channel_id": channel_id, "content": content})

            # Check if there's a waiting interact request for this channel
            if channel_id and channel_id.startswith("api_"):
                # Try to find the message ID for this channel
                try:
                    # Access the app state through the runtime's adapter
                    if hasattr(self, "_app_state"):
                        message_channel_map = getattr(self._app_state, "message_channel_map", {})
                        message_id = message_channel_map.get(channel_id)
                        if message_id:
                            from ciris_engine.logic.adapters.api.routes.agent import notify_interact_response

                            await notify_interact_response(message_id, content)
                            logger.info(f"Notified interact response for message {message_id} in channel {channel_id}")
                            # Clean up the mapping
                            del message_channel_map[channel_id]
                except Exception as e:
                    logger.debug(f"Could not notify interact response: {e}")

            # Track successful request
            self._requests_handled += 1
            elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
            self._response_times.append(elapsed_ms)
            if len(self._response_times) > self._max_response_times:
                self._response_times = self._response_times[-self._max_response_times :]

            return True

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self._error_count += 1
            return False

    def register_websocket(self, client_id: str, websocket: Any) -> None:
        """Register a WebSocket client."""
        self._websocket_clients[client_id] = websocket
        logger.info(f"WebSocket client registered: {client_id}")

    def unregister_websocket(self, client_id: str) -> None:
        """Unregister a WebSocket client."""
        if client_id in self._websocket_clients:
            del self._websocket_clients[client_id]
            logger.info(f"WebSocket client unregistered: {client_id}")

    async def fetch_messages(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        before: Optional[datetime] = None,
    ) -> List[FetchedMessage]:
        """Retrieve messages from a channel using the correlations database."""
        from ciris_engine.logic.persistence import get_correlations_by_channel

        try:
            # Get correlations for this channel
            correlations = get_correlations_by_channel(channel_id=channel_id, limit=limit, before=before)

            messages = []
            for corr in correlations:
                # Extract message data from correlation
                if corr.action_type == "speak" and corr.request_data:
                    # This is an outgoing message from the agent
                    content = ""
                    # Handle both dict and Pydantic model cases
                    if hasattr(corr.request_data, "get"):
                        params = corr.request_data.get("parameters", {})
                        content = params.get("content", "")
                    elif hasattr(corr.request_data, "parameters") and corr.request_data.parameters:
                        content = corr.request_data.parameters.get("content", "")

                    messages.append(
                        FetchedMessage(
                            message_id=corr.correlation_id,
                            author_id="ciris",  # Agent messages
                            author_name="CIRIS",
                            content=content,
                            timestamp=(
                                (corr.timestamp or corr.created_at).isoformat()
                                if (corr.timestamp or corr.created_at)
                                else None
                            ),
                            is_bot=True,
                        )
                    )
                elif corr.action_type == "observe" and corr.request_data:
                    # This is an incoming message from a user
                    content = ""
                    author_id = "unknown"
                    author_name = "User"

                    # Handle both dict and Pydantic model cases
                    if hasattr(corr.request_data, "get"):
                        params = corr.request_data.get("parameters", {})
                        content = params.get("content", "")
                        author_id = params.get("author_id", "unknown")
                        author_name = params.get("author_name", "User")
                    elif hasattr(corr.request_data, "parameters") and corr.request_data.parameters:
                        params = corr.request_data.parameters
                        content = params.get("content", "")
                        author_id = params.get("author_id", "unknown")
                        author_name = params.get("author_name", "User")

                    messages.append(
                        FetchedMessage(
                            message_id=corr.correlation_id,
                            author_id=author_id,
                            author_name=author_name,
                            content=content,
                            timestamp=(
                                (corr.timestamp or corr.created_at).isoformat()
                                if (corr.timestamp or corr.created_at)
                                else None
                            ),
                            is_bot=False,
                        )
                    )

            # Sort by timestamp
            messages.sort(key=lambda m: str(m.timestamp))

            return messages

        except Exception as e:
            logger.error(f"Failed to fetch messages from correlations for channel {channel_id}: {e}")
            return []

    async def start(self) -> None:
        """Start the communication service."""
        self._is_started = True
        self._start_time = datetime.now(timezone.utc) if not self._time_service else self._time_service.now()
        logger.info("API communication service started")

    async def stop(self) -> None:
        """Stop the communication service."""
        self._is_started = False
        # Clear any pending responses
        while not self._response_queue.empty():
            try:
                self._response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.info("API communication service stopped")

    async def is_healthy(self) -> bool:
        """Check if the service is healthy."""
        return self._is_started

    def get_service_type(self) -> ServiceType:
        """Get the type of this service."""
        return ServiceType.ADAPTER

    def get_home_channel_id(self) -> Optional[str]:
        """Get the home channel ID for this API adapter.

        Returns:
            The formatted channel ID (e.g., 'api_0.0.0.0_8080')
            or None if no home channel is configured.
        """
        if self._config and hasattr(self._config, "get_home_channel_id"):
            # Use the config method if available
            host = getattr(self._config, "host", "0.0.0.0")
            port = getattr(self._config, "port", 8080)
            return self._config.get_home_channel_id(host, port)

        # Default fallback
        return "api_0.0.0.0_8080"

    def get_status(self) -> "ServiceStatus":
        """Get the service status."""
        from ciris_engine.schemas.services.core import ServiceStatus

        # Calculate uptime
        uptime_seconds = 0.0
        if self._start_time:
            current_time = datetime.now(timezone.utc) if not self._time_service else self._time_service.now()
            uptime_seconds = (current_time - self._start_time).total_seconds()

        # Calculate average response time
        avg_response_time = 0.0
        if self._response_times:
            avg_response_time = sum(self._response_times) / len(self._response_times)

        return ServiceStatus(
            service_name="APICommunicationService",
            service_type="communication",
            is_healthy=self._is_started,
            uptime_seconds=uptime_seconds,
            last_error=None,  # Could track last error message
            metrics={
                "requests_handled": float(self._requests_handled),
                "error_count": float(self._error_count),
                "avg_response_time_ms": avg_response_time,
                "queued_responses": float(self._response_queue.qsize()),
                "websocket_clients": float(
                    len(self._websocket_clients) if hasattr(self._websocket_clients, "__len__") else 0
                ),
            },
        )

    def get_capabilities(self) -> "ServiceCapabilities":
        """Get the service capabilities."""
        from ciris_engine.schemas.services.core import ServiceCapabilities

        return ServiceCapabilities(
            service_name="APICommunicationService",
            actions=[
                "send_message",
                "fetch_messages",
                "broadcast",
                "get_response",
                "register_websocket",
                "unregister_websocket",
            ],
            version="1.0.0",
            metadata={
                "http_responses": True,
                "websocket_broadcast": True,
                "message_queueing": True,
                "channel_based_routing": True,
            },
        )
