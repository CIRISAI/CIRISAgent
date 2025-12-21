"""
Communication service for API adapter.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services.governance.communication import CommunicationServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import FetchedMessage
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus

logger = logging.getLogger(__name__)


class APICommunicationService(BaseService, CommunicationServiceProtocol):
    """Communication service for API responses."""

    def __init__(self, config: Optional[Any] = None) -> None:
        """Initialize API communication service."""
        # Initialize BaseService for telemetry
        super().__init__(time_service=None, service_name="APICommunicationService")

        self._response_queue: asyncio.Queue[Any] = asyncio.Queue()
        self._websocket_clients: JSONDict = {}
        self._config = config  # Store the API adapter config

        # Metrics tracking
        self._response_times: List[float] = []  # Track last N response times
        self._max_response_times = 100  # Keep last 100 response times
        self._requests_handled = 0
        self._error_count = 0
        self._start_time = None
        self._time_service = None

    def _create_speak_correlation(self, channel_id: str, content: str) -> None:
        """Create and store a speak correlation for outgoing message."""
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

        time_service = getattr(self, "_time_service", None)
        persistence.add_correlation(correlation, time_service)
        logger.debug(f"Created speak correlation for channel {channel_id}")

    async def _send_websocket_message(self, channel_id: str, content: str) -> bool:
        """Send message through WebSocket if channel is WebSocket type."""
        if not (channel_id and channel_id.startswith("ws:")):
            return False

        client_id = channel_id[3:]  # Remove "ws:" prefix
        if client_id not in self._websocket_clients:
            logger.warning(f"WebSocket client not found: {client_id}")
            return False

        ws = self._websocket_clients.get(client_id)
        # Type guard: ensure ws has send_json method
        if ws is None or not hasattr(ws, "send_json"):
            logger.warning(f"Invalid WebSocket client: {client_id}")
            return False

        await ws.send_json(
            {
                "type": "message",
                "data": {"content": content, "timestamp": datetime.now(timezone.utc).isoformat()},
            }
        )
        return True

    async def _handle_api_interaction_response(self, channel_id: str, content: str) -> None:
        """Handle API interaction response storage if applicable."""
        if not (channel_id and channel_id.startswith("api_")):
            logger.debug(f"[API_INTERACTION] Skipping non-API channel: {channel_id}")
            return

        logger.info(
            f"[API_INTERACTION] Processing channel_id={channel_id}, content_len={len(content)}, content_preview={content[:100] if content else 'EMPTY'}"
        )
        try:
            if not hasattr(self, "_app_state"):
                logger.warning("[API_INTERACTION] No _app_state attribute found")
                return

            message_channel_map = getattr(self._app_state, "message_channel_map", {})
            logger.debug(f"[API_INTERACTION] message_channel_map keys: {list(message_channel_map.keys())}")
            message_id = message_channel_map.get(channel_id)
            if not message_id:
                logger.warning(f"[API_INTERACTION] No message_id found for channel {channel_id}")
                return

            from ciris_engine.logic.adapters.api.routes.agent import store_message_response

            logger.info(f"[API_INTERACTION] About to store: message_id={message_id}, content='{content}'")
            await store_message_response(message_id, content)
            logger.info(f"Stored interact response for message {message_id} in channel {channel_id}")
            # Clean up the mapping
            del message_channel_map[channel_id]
        except Exception as e:
            logger.debug(f"Could not store interact response: {e}")

    def _track_response_time(self, start_time: datetime) -> None:
        """Track response time metrics."""
        elapsed_ms = (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        self._response_times.append(elapsed_ms)
        if len(self._response_times) > self._max_response_times:
            self._response_times = self._response_times[-self._max_response_times :]

    async def send_system_message(
        self, channel_id: str, content: str, message_type: str = "system", author_name: str = "System"
    ) -> bool:
        """
        Send a system or error message to a channel.

        Args:
            channel_id: Target channel
            content: Message content
            message_type: Type of message (system, error)
            author_name: Name to display as author (default: System)

        Returns:
            True if message was sent successfully
        """
        import uuid

        from ciris_engine.logic import persistence
        from ciris_engine.schemas.telemetry.core import (
            ServiceCorrelation,
            ServiceCorrelationStatus,
            ServiceRequestData,
            ServiceResponseData,
        )

        start_time = datetime.now(timezone.utc)
        logger.info(
            f"[SEND_SYSTEM_MESSAGE] channel_id={channel_id}, message_type={message_type}, content_len={len(content)}"
        )

        try:
            # Create correlation for tracking with message_type in parameters
            correlation_id = str(uuid.uuid4())
            correlation = ServiceCorrelation(
                correlation_id=correlation_id,
                service_type="api",
                handler_name="APIAdapter",
                action_type="speak",
                request_data=ServiceRequestData(
                    service_type="api",
                    method_name="speak",
                    channel_id=channel_id,
                    parameters={"content": content, "channel_id": channel_id, "message_type": message_type},
                    request_timestamp=start_time,
                ),
                response_data=ServiceResponseData(
                    success=True, result_summary=f"{message_type} message sent", execution_time_ms=0, response_timestamp=start_time
                ),
                status=ServiceCorrelationStatus.COMPLETED,
                created_at=start_time,
                updated_at=start_time,
                timestamp=start_time,
            )

            time_service = getattr(self, "_time_service", None)
            persistence.add_correlation(correlation, time_service)
            logger.debug(f"Created {message_type} message correlation for channel {channel_id}")

            # Try WebSocket first
            if await self._send_websocket_message(channel_id, content):
                return True

            # Queue for HTTP response
            await self._response_queue.put({"channel_id": channel_id, "content": content})

            # Track successful request
            self._track_request()
            self._track_response_time(start_time)

            return True

        except Exception as e:
            logger.error(f"Failed to send {message_type} message: {e}")
            self._track_error(e)
            return False

    async def send_message(self, channel_id: str, content: str) -> bool:
        """Send message through API response or WebSocket."""
        start_time = datetime.now(timezone.utc)
        logger.info(
            f"[SEND_MESSAGE] channel_id={channel_id}, content_len={len(content)}, content_preview={content[:100] if content else 'EMPTY'}"
        )
        try:
            # Create correlation for tracking
            self._create_speak_correlation(channel_id, content)

            # Try WebSocket first
            if await self._send_websocket_message(channel_id, content):
                return True

            # Queue for HTTP response
            await self._response_queue.put({"channel_id": channel_id, "content": content})

            # Handle API interaction response if applicable
            await self._handle_api_interaction_response(channel_id, content)

            # Track successful request
            self._track_request()
            self._track_response_time(start_time)

            return True

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self._track_error(e)
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

    def _extract_parameters(self, request_data: Any) -> JSONDict:
        """Extract parameters from request data handling both dict and Pydantic model cases."""
        if hasattr(request_data, "get"):
            params = request_data.get("parameters", {})
            return params if isinstance(params, dict) else {}
        elif hasattr(request_data, "parameters") and request_data.parameters:
            params = request_data.parameters
            return params if isinstance(params, dict) else {}
        return {}

    def _create_speak_message(self, correlation: Any) -> FetchedMessage:
        """Create a FetchedMessage from a 'speak' correlation (outgoing agent message)."""
        params = self._extract_parameters(correlation.request_data)
        content = params.get("content", "")
        message_type = params.get("message_type", "agent")

        return FetchedMessage(
            message_id=correlation.correlation_id,
            author_id="ciris",
            author_name="CIRIS",
            content=content,
            timestamp=self._format_timestamp(correlation),
            is_bot=True,
            message_type=message_type,
        )

    def _create_observe_message(self, correlation: Any) -> FetchedMessage:
        """Create a FetchedMessage from an 'observe' correlation (incoming user message)."""
        params = self._extract_parameters(correlation.request_data)

        return FetchedMessage(
            message_id=params.get("message_id", correlation.correlation_id),
            author_id=params.get("author_id", "unknown"),
            author_name=params.get("author_name", "User"),
            content=params.get("content", ""),
            timestamp=self._format_timestamp(correlation),
            is_bot=False,
            message_type="user",
        )

    def _format_timestamp(self, correlation: Any) -> Optional[str]:
        """Format correlation timestamp for FetchedMessage."""
        timestamp = correlation.timestamp or correlation.created_at
        return timestamp.isoformat() if timestamp else None

    def _process_correlation(self, correlation: Any) -> Optional[FetchedMessage]:
        """Process a single correlation into a FetchedMessage if applicable."""
        if not correlation.request_data:
            return None

        if correlation.action_type == "speak":
            return self._create_speak_message(correlation)
        elif correlation.action_type == "observe":
            return self._create_observe_message(correlation)

        return None

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
            correlations = get_correlations_by_channel(channel_id=channel_id, limit=limit, before=before)

            messages = []
            for corr in correlations:
                message = self._process_correlation(corr)
                if message:
                    messages.append(message)

            # Sort by timestamp
            messages.sort(key=lambda m: str(m.timestamp))
            return messages

        except Exception as e:
            logger.error(f"Failed to fetch messages from correlations for channel {channel_id}: {e}")
            return []

    async def start(self) -> None:
        """Start the communication service."""
        await BaseService.start(self)
        logger.info("API communication service started")

    async def stop(self) -> None:
        """Stop the communication service."""
        # Clear any pending responses
        while not self._response_queue.empty():
            try:
                self._response_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        await BaseService.stop(self)
        logger.info("API communication service stopped")

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are satisfied."""
        return True  # No hard dependencies

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect API communication specific metrics."""
        avg_response_time = sum(self._response_times) / len(self._response_times) if self._response_times else 0.0
        return {
            "websocket_clients": float(len(self._websocket_clients)),
            "queue_size": float(self._response_queue.qsize()),
            "avg_response_time_ms": avg_response_time,
            "response_times_tracked": float(len(self._response_times)),
        }

    def _get_actions(self) -> List[str]:
        """Get the list of actions this service supports."""
        return ["send_message", "fetch_messages", "queue_response", "dequeue_response"]

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
            result = self._config.get_home_channel_id(host, port)
            return str(result) if result is not None else None

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
            is_healthy=self._started,
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
            metadata=None,
        )
