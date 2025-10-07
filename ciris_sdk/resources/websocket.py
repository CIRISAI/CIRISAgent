"""
WebSocket streaming resource for CIRIS v1 API (Pre-Beta).

**WARNING**: This SDK is for the v1 API which is in pre-beta stage.
The API interfaces may change without notice.

Enhanced WebSocket design with channel-specific filters, backpressure handling,
and automatic reconnection support.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, AsyncIterator, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from websockets.asyncio.client import (  # noqa: F401 (used in type annotations)
        ClientConnection as WebSocketClientProtocol,
    )

logger = logging.getLogger(__name__)


class WebSocketState(Enum):
    """WebSocket connection states."""

    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    DISCONNECTED = "disconnected"
    FAILED = "failed"


class ChannelFilter(BaseModel):
    """Filters for a specific channel subscription."""

    # Telemetry channel filters
    services: Optional[List[str]] = Field(None, description="Filter by service names")
    metrics: Optional[List[str]] = Field(None, description="Filter by metric names")

    # Log channel filters
    level: Optional[str] = Field(None, description="Minimum log level (DEBUG, INFO, WARNING, ERROR)")
    service: Optional[str] = Field(None, description="Filter logs by service")

    # Message channel filters
    author: Optional[str] = Field(None, description="Filter by message author")

    # Reasoning channel filters
    task_id: Optional[str] = Field(None, description="Filter by specific task")
    min_depth: Optional[int] = Field(None, description="Minimum reasoning depth")


class SubscribeRequest(BaseModel):
    """WebSocket subscription request with channel filters."""

    action: Literal["subscribe"] = Field(default="subscribe")
    channels: Dict[str, ChannelFilter] = Field(
        ...,
        description="Channels to subscribe with optional filters",
        examples=[
            {
                "telemetry": {"services": ["memory", "llm"]},
                "logs": {"level": "ERROR", "service": "audit"},
                "messages": {},
                "reasoning": {"min_depth": 3},
            }
        ],
    )


class UnsubscribeRequest(BaseModel):
    """WebSocket unsubscribe request."""

    action: Literal["unsubscribe"] = Field(default="unsubscribe")
    channels: List[str] = Field(..., description="Channels to unsubscribe from")


class WebSocketMessage(BaseModel):
    """Message received from WebSocket."""

    channel: str = Field(..., description="Channel this message belongs to")
    event_type: str = Field(..., description="Type of event")
    timestamp: datetime = Field(..., description="When the event occurred")
    data: Dict[str, Any] = Field(..., description="Event data")
    sequence: int = Field(..., description="Message sequence number for ordering")


class WebSocketResource:
    """
    WebSocket streaming client for real-time updates.

    Features:
    - Channel-specific filtering
    - Automatic reconnection with exponential backoff
    - Backpressure handling with configurable buffer
    - Message sequencing for order guarantees
    - Heartbeat/keepalive support

    Example:
        async with client.websocket() as ws:
            # Subscribe with filters
            await ws.subscribe({
                "telemetry": {"services": ["memory", "llm"]},
                "logs": {"level": "ERROR"}
            })

            # Process messages
            async for message in ws.messages():
                if message.channel == "telemetry":
                    print(f"Metric: {message.data}")
    """

    def __init__(
        self,
        url: str,
        api_key: Optional[str] = None,
        reconnect: bool = True,
        reconnect_interval: float = 1.0,
        max_reconnect_interval: float = 60.0,
        message_buffer_size: int = 1000,
        heartbeat_interval: float = 30.0,
    ):
        self.url = url.replace("http://", "ws://").replace("https://", "wss://")
        if not self.url.endswith("/v1/stream"):
            self.url = self.url.rstrip("/") + "/v1/stream"

        self.api_key = api_key
        self.reconnect = reconnect
        self.reconnect_interval = reconnect_interval
        self.max_reconnect_interval = max_reconnect_interval
        self.message_buffer_size = message_buffer_size
        self.heartbeat_interval = heartbeat_interval

        self.state = WebSocketState.DISCONNECTED
        self.ws: Optional["WebSocketClientProtocol"] = None
        self._message_queue: asyncio.Queue[WebSocketMessage] = asyncio.Queue(maxsize=message_buffer_size)
        self._reconnect_attempts = 0
        self._last_sequence = 0
        self._subscriptions: Dict[str, ChannelFilter] = {}
        self._tasks: List[asyncio.Task[Any]] = []

    async def __aenter__(self) -> "WebSocketResource":
        await self.connect()
        return self

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self.disconnect()

    async def connect(self) -> None:
        """Establish WebSocket connection with authentication."""
        import websockets

        self.state = WebSocketState.CONNECTING
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        try:
            self.ws = await websockets.connect(
                self.url, extra_headers=headers, ping_interval=self.heartbeat_interval, ping_timeout=10
            )
            self.state = WebSocketState.CONNECTED
            self._reconnect_attempts = 0

            # Start message receiver and heartbeat tasks
            self._tasks.append(asyncio.create_task(self._receive_messages()))
            self._tasks.append(asyncio.create_task(self._heartbeat()))

            # Resubscribe to previous channels after reconnection
            if self._subscriptions:
                # Re-subscribe with type ignore as the types are compatible
                await self.subscribe(self._subscriptions)  # type: ignore[arg-type]

            logger.info(f"WebSocket connected to {self.url}")

        except Exception as e:
            self.state = WebSocketState.FAILED
            logger.error(f"WebSocket connection failed: {e}")
            if self.reconnect:
                await self._schedule_reconnect()
            else:
                raise

    async def disconnect(self) -> None:
        """Gracefully disconnect WebSocket."""
        self.state = WebSocketState.DISCONNECTED

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Close WebSocket
        if self.ws:
            await self.ws.close()

        logger.info("WebSocket disconnected")

    async def subscribe(self, channels: Dict[str, Optional[ChannelFilter]]) -> None:
        """
        Subscribe to channels with optional filters.

        Args:
            channels: Dict of channel names to optional filters

        Example:
            await ws.subscribe({
                "telemetry": ChannelFilter(services=["memory"]),
                "logs": ChannelFilter(level="ERROR"),
                "messages": None  # No filters
            })
        """
        if self.state != WebSocketState.CONNECTED:
            raise RuntimeError("WebSocket not connected")

        # Build subscription request
        channel_filters = {}
        for channel, filter_obj in channels.items():
            if filter_obj:
                channel_filters[channel] = filter_obj.model_dump(exclude_none=True)
            else:
                channel_filters[channel] = {}

        request = SubscribeRequest(channels=channel_filters)

        # Send subscription
        if self.ws:
            await self.ws.send(request.json())

        # Track subscriptions for reconnection
        for ch, filt in channels.items():
            if filt:
                self._subscriptions[ch] = filt
            else:
                self._subscriptions.pop(ch, None)

        logger.info(f"Subscribed to channels: {list(channels.keys())}")

    async def unsubscribe(self, channels: List[str]) -> None:
        """
        Unsubscribe from channels.

        Args:
            channels: List of channel names to unsubscribe from
        """
        if self.state != WebSocketState.CONNECTED:
            raise RuntimeError("WebSocket not connected")

        request = UnsubscribeRequest(channels=channels)
        if self.ws:
            await self.ws.send(request.json())

        # Remove from tracked subscriptions
        for channel in channels:
            self._subscriptions.pop(channel, None)

        logger.info(f"Unsubscribed from channels: {channels}")

    async def messages(self) -> AsyncIterator[WebSocketMessage]:
        """
        Iterate over incoming messages.

        Handles backpressure by buffering messages. If the buffer fills,
        oldest messages are dropped and a warning is logged.

        Yields:
            WebSocketMessage objects in order
        """
        while True:
            try:
                message = await self._message_queue.get()
                yield message
            except asyncio.CancelledError:
                break

    async def send(self, data: Dict[str, Any]) -> None:
        """
        Send arbitrary data to the server.

        Args:
            data: JSON-serializable data to send
        """
        if self.state != WebSocketState.CONNECTED:
            raise RuntimeError("WebSocket not connected")

        if self.ws:
            await self.ws.send(json.dumps(data))

    async def _receive_messages(self) -> None:
        """Background task to receive and queue messages."""
        try:
            if self.ws:
                async for message in self.ws:
                    try:
                        # Decode bytes if necessary
                        if isinstance(message, bytes):
                            message_str = message.decode("utf-8")
                        else:
                            message_str = message
                        data = json.loads(message_str)

                        # Handle different message types
                        if data.get("type") == "error":
                            logger.error(f"Server error: {data.get('message')}")
                            continue

                        if data.get("type") == "pong":
                            # Heartbeat response
                            continue

                        # Parse as WebSocketMessage
                        ws_message = WebSocketMessage(**data)

                        # Check sequence for gaps
                        if ws_message.sequence > self._last_sequence + 1:
                            logger.warning(
                                f"Message gap detected: expected {self._last_sequence + 1}, "
                                f"got {ws_message.sequence}"
                            )
                        self._last_sequence = ws_message.sequence

                        # Queue message with backpressure handling
                        try:
                            self._message_queue.put_nowait(ws_message)
                        except asyncio.QueueFull:
                            # Drop oldest message and retry
                            try:
                                self._message_queue.get_nowait()
                                self._message_queue.put_nowait(ws_message)
                                logger.warning("Message buffer full, dropped oldest message")
                            except asyncio.QueueEmpty:
                                pass

                    except json.JSONDecodeError:
                        # Use message_str (already decoded) instead of message (might be bytes)
                        msg_preview = message_str[:100] if len(message_str) > 100 else message_str
                        logger.error(f"Invalid JSON received: {msg_preview}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")

        except Exception as e:
            if "ConnectionClosed" in str(type(e).__name__):
                logger.info("WebSocket connection closed by server")
                if self.reconnect:
                    await self._schedule_reconnect()

    async def _heartbeat(self) -> None:
        """Send periodic heartbeat to keep connection alive."""
        while self.state == WebSocketState.CONNECTED:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self.send({"type": "ping", "timestamp": datetime.now(timezone.utc).isoformat()})
            except Exception as e:
                logger.error(f"Heartbeat failed: {e}")
                break

    async def _schedule_reconnect(self) -> None:
        """Schedule reconnection with exponential backoff."""
        if self.state == WebSocketState.RECONNECTING:
            return

        self.state = WebSocketState.RECONNECTING
        self._reconnect_attempts += 1

        # Calculate backoff interval
        interval = min(self.reconnect_interval * (2**self._reconnect_attempts), self.max_reconnect_interval)

        logger.info(f"Reconnecting in {interval}s (attempt {self._reconnect_attempts})")
        await asyncio.sleep(interval)

        try:
            await self.connect()
        except Exception as e:
            logger.error(f"Reconnection failed: {e}")
            # Will retry again via recursive call


class ReconnectionPolicy(BaseModel):
    """Configuration for reconnection behavior."""

    enabled: bool = Field(True, description="Whether to automatically reconnect")
    initial_interval: float = Field(1.0, description="Initial reconnection interval in seconds")
    max_interval: float = Field(60.0, description="Maximum reconnection interval")
    max_attempts: Optional[int] = Field(None, description="Maximum reconnection attempts (None=infinite)")


class BackpressurePolicy(BaseModel):
    """Configuration for handling backpressure."""

    buffer_size: int = Field(1000, description="Maximum messages to buffer")
    drop_policy: str = Field("oldest", description="Which messages to drop when full (oldest/newest)")
    warn_threshold: float = Field(0.8, description="Warn when buffer is this full (0.0-1.0)")
