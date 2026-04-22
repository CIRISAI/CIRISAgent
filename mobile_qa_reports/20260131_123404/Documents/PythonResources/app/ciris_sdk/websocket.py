"""
WebSocket client for CIRIS v1 API streaming endpoints.

Provides real-time streaming with automatic reconnection and channel-based filtering.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

import backoff
import websockets
from websockets.asyncio.client import ClientConnection
from websockets.exceptions import WebSocketException

from .auth_store import AuthStore
from .exceptions import CIRISConnectionError

logger = logging.getLogger(__name__)


class EventChannel(str, Enum):
    """WebSocket event channels."""

    ALL = "*"  # All events
    AGENT_STATE = "agent.state"  # Cognitive state changes
    AGENT_METRICS = "agent.metrics"  # Resource usage, performance
    MEMORY_CHANGES = "memory.changes"  # Graph node updates
    SYSTEM_HEALTH = "system.health"  # Service health updates
    RUNTIME_EVENTS = "runtime.events"  # Lifecycle events
    TELEMETRY = "telemetry"  # Telemetry data stream
    CUSTOM = "custom"  # User-defined events


class ConnectionState(str, Enum):
    """WebSocket connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    CLOSING = "closing"
    CLOSED = "closed"


class ChannelFilter:
    """Filter for channel-based event routing."""

    def __init__(self, channels: Optional[Set[EventChannel]] = None):
        """
        Initialize channel filter.

        Args:
            channels: Set of channels to include (None = all channels)
        """
        self.channels = channels or {EventChannel.ALL}

    def matches(self, channel: str) -> bool:
        """Check if event channel matches filter."""
        if EventChannel.ALL in self.channels:
            return True

        # Check exact match
        if channel in self.channels:
            return True

        # Check prefix match (e.g., "agent.state.work" matches "agent.state")
        for allowed in self.channels:
            if channel.startswith(f"{allowed}."):
                return True

        return False


class WebSocketClient:
    """
    WebSocket client with automatic reconnection and channel filtering.

    Features:
    - Automatic reconnection with exponential backoff
    - Channel-based event filtering
    - Health monitoring and heartbeat
    - Graceful shutdown
    """

    def __init__(
        self,
        base_url: str,
        api_key: Optional[str] = None,
        channels: Optional[List[EventChannel]] = None,
        reconnect: bool = True,
        heartbeat_interval: float = 30.0,
        use_auth_store: bool = True,
    ):
        """
        Initialize WebSocket client.

        Args:
            base_url: Base URL of CIRIS API
            api_key: API key for authentication
            channels: List of channels to subscribe to
            reconnect: Whether to auto-reconnect on disconnect
            heartbeat_interval: Heartbeat interval in seconds
            use_auth_store: Whether to use persistent auth storage
        """
        # Convert http(s) to ws(s)
        self.ws_url = base_url.replace("http://", "ws://").replace("https://", "wss://")
        self.ws_url = f"{self.ws_url}/v1/stream"

        self.api_key = api_key
        self.auth_store = AuthStore() if use_auth_store else None

        # Load stored auth if needed
        if use_auth_store and not api_key and self.auth_store:
            stored_key = self.auth_store.get_api_key(base_url)
            if stored_key:
                self.api_key = stored_key

        self.channels = set(channels) if channels else {EventChannel.ALL}
        self.filter = ChannelFilter(self.channels)
        self.reconnect = reconnect
        self.heartbeat_interval = heartbeat_interval

        self._websocket: Optional[ClientConnection] = None
        self._state = ConnectionState.DISCONNECTED
        self._event_handlers: Dict[str, List[Callable[..., Any]]] = {}
        self._running = False
        self._tasks: Set[asyncio.Task[Any]] = set()

        # Connection stats
        self._connected_at: Optional[datetime] = None
        self._reconnect_count = 0
        self._last_heartbeat: Optional[datetime] = None

    @property
    def state(self) -> ConnectionState:
        """Get current connection state."""
        return self._state

    @property
    def is_connected(self) -> bool:
        """Check if currently connected."""
        return self._state == ConnectionState.CONNECTED

    def on(self, event: str, handler: Callable[..., Any]) -> None:
        """
        Register event handler.

        Args:
            event: Event name to handle (e.g., "message", "state_change")
            handler: Async function to call on event
        """
        if event not in self._event_handlers:
            self._event_handlers[event] = []
        self._event_handlers[event].append(handler)

    def off(self, event: str, handler: Callable[..., Any]) -> None:
        """
        Unregister event handler.

        Args:
            event: Event name
            handler: Handler to remove
        """
        if event in self._event_handlers:
            self._event_handlers[event].remove(handler)

    async def _emit(self, event: str, *args: Any, **kwargs: Any) -> None:
        """Emit event to all registered handlers."""
        for handler in self._event_handlers.get(event, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler(*args, **kwargs)
                else:
                    handler(*args, **kwargs)
            except Exception as e:
                logger.error(f"Error in event handler for {event}: {e}")

    async def connect(self) -> None:
        """Connect to WebSocket server."""
        if self._state != ConnectionState.DISCONNECTED:
            return

        self._running = True
        self._set_state(ConnectionState.CONNECTING)

        try:
            await self._connect()
        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self._set_state(ConnectionState.DISCONNECTED)
            raise

    @backoff.on_exception(backoff.expo, WebSocketException, max_tries=10, max_time=300, factor=2)
    async def _connect(self) -> None:
        """Internal connection with retry logic."""
        headers = {}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        # Add channel subscription header
        if self.channels != {EventChannel.ALL}:
            headers["X-Subscribe-Channels"] = ",".join(self.channels)

        logger.info(f"Connecting to {self.ws_url}")

        self._websocket = await websockets.connect(self.ws_url, extra_headers=headers)

        self._set_state(ConnectionState.CONNECTED)
        self._connected_at = datetime.now(timezone.utc)
        logger.info("WebSocket connected")

        # Start background tasks
        self._tasks.add(asyncio.create_task(self._receive_loop()))
        self._tasks.add(asyncio.create_task(self._heartbeat_loop()))

        await self._emit("connected")

    def _set_state(self, state: ConnectionState) -> None:
        """Update connection state."""
        old_state = self._state
        self._state = state

        if old_state != state:
            logger.info(f"Connection state: {old_state} -> {state}")
            asyncio.create_task(self._emit("state_change", old_state, state))

    async def _receive_loop(self) -> None:
        """Main message receive loop."""
        if not self._websocket:
            logger.error("Cannot start receive loop: WebSocket not connected")
            return

        try:
            async for message in self._websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON received: {e}")
                except Exception as e:
                    logger.error(f"Error handling message: {e}")

        except websockets.ConnectionClosed as e:
            logger.warning(f"Connection closed: {e}")
        except Exception as e:
            logger.error(f"Receive loop error: {e}")

        finally:
            await self._handle_disconnect()

    async def _handle_message(self, data: Dict[str, Any]) -> None:
        """Handle incoming message."""
        # Extract message metadata
        msg_type = data.get("type", "message")
        channel = data.get("channel", EventChannel.ALL)
        timestamp = data.get("timestamp")

        # Check channel filter
        if not self.filter.matches(channel):
            return

        # Handle different message types
        if msg_type == "ping":
            # Respond to ping
            await self.send({"type": "pong", "timestamp": timestamp})

        elif msg_type == "error":
            logger.error(f"Server error: {data.get('message', 'Unknown error')}")
            await self._emit("error", data)

        elif msg_type == "subscription_update":
            # Channel subscription confirmed
            logger.info(f"Subscribed to channels: {data.get('channels', [])}")
            await self._emit("subscription_update", data)

        else:
            # Regular message
            await self._emit("message", data)

            # Emit channel-specific event
            if channel:
                await self._emit(f"channel:{channel}", data)

    async def _heartbeat_loop(self) -> None:
        """Send periodic heartbeats."""
        while self._running and self.is_connected:
            try:
                await self.send({"type": "heartbeat", "timestamp": datetime.now(timezone.utc).isoformat()})
                self._last_heartbeat = datetime.now(timezone.utc)

                await asyncio.sleep(self.heartbeat_interval)

            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                break

    async def _handle_disconnect(self) -> None:
        """Handle disconnection and reconnection."""
        self._set_state(ConnectionState.DISCONNECTED)

        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        # Close websocket if still open
        if self._websocket:
            await self._websocket.close()
            self._websocket = None

        await self._emit("disconnected")

        # Attempt reconnection if enabled
        if self.reconnect and self._running:
            self._reconnect_count += 1
            self._set_state(ConnectionState.RECONNECTING)

            logger.info(f"Attempting reconnection #{self._reconnect_count}")

            try:
                await self._connect()
            except Exception as e:
                logger.error(f"Reconnection failed: {e}")
                self._set_state(ConnectionState.DISCONNECTED)

    async def send(self, data: Dict[str, Any]) -> None:
        """
        Send message to server.

        Args:
            data: Message data to send
        """
        if not self.is_connected or not self._websocket:
            raise CIRISConnectionError("WebSocket not connected")

        message = json.dumps(data)
        await self._websocket.send(message)

    async def subscribe(self, channels: List[EventChannel]) -> None:
        """
        Subscribe to additional channels.

        Args:
            channels: List of channels to subscribe to
        """
        self.channels.update(channels)
        self.filter = ChannelFilter(self.channels)

        if self.is_connected:
            await self.send({"type": "subscribe", "channels": list(self.channels)})

    async def unsubscribe(self, channels: List[EventChannel]) -> None:
        """
        Unsubscribe from channels.

        Args:
            channels: List of channels to unsubscribe from
        """
        for channel in channels:
            self.channels.discard(channel)
        self.filter = ChannelFilter(self.channels)

        if self.is_connected:
            await self.send({"type": "unsubscribe", "channels": channels})

    async def close(self) -> None:
        """Close WebSocket connection."""
        self._running = False
        self._set_state(ConnectionState.CLOSING)

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()

        # Close websocket
        if self._websocket:
            await self._websocket.close()
            self._websocket = None

        self._set_state(ConnectionState.CLOSED)
        await self._emit("closed")

    def get_stats(self) -> Dict[str, Any]:
        """Get connection statistics."""
        uptime = None
        if self._connected_at and self.is_connected:
            uptime = (datetime.now(timezone.utc) - self._connected_at).total_seconds()

        return {
            "state": self._state,
            "connected_at": self._connected_at.isoformat() if self._connected_at else None,
            "uptime_seconds": uptime,
            "reconnect_count": self._reconnect_count,
            "last_heartbeat": self._last_heartbeat.isoformat() if self._last_heartbeat else None,
            "subscribed_channels": list(self.channels),
        }
