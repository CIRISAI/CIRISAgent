"""Discord connection resilience and auto-reconnect component."""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Dict, Optional

import discord

from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class ConnectionState(Enum):
    """Discord connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    FAILED = "failed"


class DiscordConnectionManager:
    """Manages Discord connection resilience and auto-reconnect."""

    def __init__(
        self,
        token: str,
        client: Optional[discord.Client] = None,
        time_service: Optional["TimeServiceProtocol"] = None,
        max_reconnect_attempts: int = 10,
        base_reconnect_delay: float = 5.0,
        max_reconnect_delay: float = 300.0,
    ) -> None:
        """Initialize the connection manager.

        Args:
            token: Discord bot token
            client: Discord client instance
            time_service: Time service for consistent time operations
            max_reconnect_attempts: Maximum reconnection attempts
            base_reconnect_delay: Base delay between reconnect attempts (seconds)
            max_reconnect_delay: Maximum delay between reconnect attempts (seconds)
        """
        self.token = token
        self.client = client
        self.max_reconnect_attempts = max_reconnect_attempts
        self.base_reconnect_delay = base_reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay

        # State tracking
        self.state = ConnectionState.DISCONNECTED
        self.reconnect_attempts = 0
        self.last_connected: Optional[datetime] = None
        self.last_disconnected: Optional[datetime] = None
        self.connection_task: Optional[asyncio.Task[Any]] = None

        # Callbacks
        self.on_connected: Optional[Callable[[], Awaitable[None]]] = None
        self.on_disconnected: Optional[Callable[[Optional[Exception]], Awaitable[None]]] = None
        self.on_reconnecting: Optional[Callable[[int], Awaitable[None]]] = None
        self.on_failed: Optional[Callable[[str], Awaitable[None]]] = None
        self._time_service: TimeServiceProtocol

        # Ensure we have a time service
        if time_service is None:
            from ciris_engine.logic.services.lifecycle.time import TimeService

            self._time_service = TimeService()
        else:
            self._time_service = time_service

    def set_client(self, client: discord.Client) -> None:
        """Set the Discord client after initialization.

        Args:
            client: Discord client instance
        """
        self.client = client
        self._setup_event_handlers()

    def _setup_event_handlers(self) -> None:
        """Set up Discord event handlers for connection management."""
        logger.info("DiscordConnectionManager._setup_event_handlers: Event handlers now managed by CIRISDiscordClient")

        if not self.client:
            logger.error("DiscordConnectionManager._setup_event_handlers: No client available!")
            return

        # Event handlers are now managed by the CIRISDiscordClient class
        # This avoids overriding Discord.py's internal handlers

    async def _handle_connected(self) -> None:
        """Handle successful connection."""
        logger.info("DiscordConnectionManager._handle_connected: on_ready event triggered!")
        previous_state = self.state
        self.state = ConnectionState.CONNECTED
        self.reconnect_attempts = 0
        self.last_connected = self._time_service.now()

        if self.client:
            logger.info(f"Discord connected successfully! User: {self.client.user}, Guilds: {len(self.client.guilds)}")
            logger.info(f"Discord client is_ready: {self.client.is_ready()}, is_closed: {self.client.is_closed()}")
            logger.info(f"Connection state transition: {previous_state.value} -> {self.state.value}")

            # Log reconnection if this was not the initial connection
            if previous_state == ConnectionState.DISCONNECTED:
                logger.info("Discord successfully reconnected after disconnection")

            for guild in self.client.guilds:
                logger.info(f"  - Guild: {guild.name} (ID: {guild.id})")
        else:
            logger.error("Discord on_ready called but client is None!")

        if self.on_connected:
            try:
                await self.on_connected()
            except Exception as e:
                logger.error(f"Error in on_connected callback: {e}")

    async def _handle_disconnected(self, error: Optional[Exception]) -> None:
        """Handle disconnection.

        Args:
            error: Exception that caused disconnection, if any
        """
        self.state = ConnectionState.DISCONNECTED
        self.last_disconnected = self._time_service.now()

        if error:
            logger.error(f"Discord disconnected with error: {error}")
        else:
            logger.warning("Discord disconnected")

        if self.on_disconnected:
            try:
                await self.on_disconnected(error)
            except Exception as e:
                logger.error(f"Error in on_disconnected callback: {e}")

        # Discord.py handles reconnection automatically when using start() with reconnect=True
        # We don't need to manually reconnect
        logger.info("Discord disconnected. Discord.py will handle reconnection automatically.")

    async def _handle_failed(self, reason: str) -> None:
        """Handle connection failure.

        Args:
            reason: Reason for failure
        """
        self.state = ConnectionState.FAILED
        logger.error(f"Discord connection failed: {reason}")

        if self.on_failed:
            try:
                await self.on_failed(reason)
            except Exception as e:
                logger.error(f"Error in on_failed callback: {e}")

    def _reconnect(self) -> None:
        """Note: Discord.py handles reconnection automatically when using start() with reconnect=True.
        This method is deprecated and should not be called."""
        logger.warning("_reconnect() called but Discord.py handles reconnection automatically")
        # Do nothing - let Discord.py handle reconnection

    async def connect(self) -> None:
        """Setup connection monitoring for Discord client.
        Note: The actual connection is managed by DiscordPlatform."""
        if self.state == ConnectionState.CONNECTED:
            logger.debug("Already connected to Discord")
            return

        if self.state == ConnectionState.CONNECTING:
            logger.debug("Connection already in progress")
            return

        self.state = ConnectionState.CONNECTING

        try:
            if self.client:
                # Client was provided externally, just set up event handlers
                self._setup_event_handlers()
                logger.info("Discord connection manager configured with existing client")
                # The DiscordPlatform handles the actual connection
            else:
                logger.error("No Discord client provided to connection manager")
                raise ValueError("Discord client must be provided by DiscordPlatform")

            self.state = ConnectionState.CONNECTING
            logger.info("Discord connection manager ready to monitor connection")

        except Exception as e:
            logger.error(f"Failed to setup Discord connection monitoring: {e}")
            await self._handle_disconnected(e)

    async def disconnect(self) -> None:
        """Disconnect from Discord gracefully."""
        if self.client and not self.client.is_closed():
            self.state = ConnectionState.DISCONNECTED
            await self.client.close()

        if self.connection_task:
            self.connection_task.cancel()
            try:
                await self.connection_task
            except asyncio.CancelledError:
                # Re-raise CancelledError to maintain cancellation chain
                raise

    def is_connected(self) -> bool:
        """Check if currently connected to Discord.

        Returns:
            True if connected
        """
        # If we have a client, check its actual state
        if self.client is not None:
            is_closed = self.client.is_closed()
            is_ready = self.client.is_ready()
            # During startup, consider the adapter healthy if the client exists and is not closed
            # This prevents the circuit breaker from opening while Discord is connecting
            result = not is_closed
            logger.debug(
                f"DiscordConnectionManager.is_connected: client exists, is_closed={is_closed}, is_ready={is_ready}, result={result}"
            )
            return result
        logger.debug("DiscordConnectionManager.is_connected: client is None, returning False")
        return False

    def get_connection_info(self) -> JSONDict:
        """Get current connection information.

        Returns:
            Dictionary with connection details
        """
        info: JSONDict = {
            "state": self.state.value,
            "reconnect_attempts": self.reconnect_attempts,
            "is_connected": self.is_connected(),
            "last_connected": self.last_connected.isoformat() if self.last_connected else None,
            "last_disconnected": self.last_disconnected.isoformat() if self.last_disconnected else None,
        }

        if self.client and self.is_connected():
            info.update(
                {
                    "guilds": len(self.client.guilds),
                    "users": len(self.client.users),
                    "latency_ms": int(self.client.latency * 1000) if hasattr(self.client, "latency") else None,
                }
            )

        return info

    async def wait_until_ready(self, timeout: float = 30.0) -> bool:
        """Wait until the client is ready or timeout.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if ready, False if timeout
        """
        logger.info(f"DiscordConnectionManager.wait_until_ready: Starting wait with timeout={timeout}s")

        if not self.client:
            logger.error("DiscordConnectionManager.wait_until_ready: No client available!")
            return False

        try:
            # First wait for the client to start connecting
            # Discord.py's wait_until_ready() only works after connection has begun
            start_time = asyncio.get_event_loop().time()
            logger.info("DiscordConnectionManager.wait_until_ready: Waiting for client to start connecting...")

            while asyncio.get_event_loop().time() - start_time < timeout:
                is_closed = self.client.is_closed()
                is_ready = self.client.is_ready()
                logger.debug(f"DiscordConnectionManager.wait_until_ready: is_closed={is_closed}, is_ready={is_ready}")

                # Check if client has started (is_closed() returns False when connecting/connected)
                if not is_closed:
                    logger.info(
                        "DiscordConnectionManager.wait_until_ready: Client is not closed, calling wait_until_ready()"
                    )
                    # Now we can use wait_until_ready()
                    remaining_timeout = timeout - (asyncio.get_event_loop().time() - start_time)
                    logger.info(
                        f"DiscordConnectionManager.wait_until_ready: Remaining timeout: {remaining_timeout:.1f}s"
                    )
                    await asyncio.wait_for(self.client.wait_until_ready(), timeout=remaining_timeout)
                    logger.info(
                        f"DiscordConnectionManager.wait_until_ready: Client is ready! is_ready={self.client.is_ready()}"
                    )
                    return True
                # Client hasn't started connecting yet, wait a bit
                await asyncio.sleep(0.1)

            # Timeout waiting for client to start
            logger.error(f"DiscordConnectionManager.wait_until_ready: Timeout after {timeout}s - client never started")
            return False
        except asyncio.TimeoutError:
            logger.error("DiscordConnectionManager.wait_until_ready: TimeoutError waiting for client to be ready")
            return False
        except Exception as e:
            logger.error(f"DiscordConnectionManager.wait_until_ready: Unexpected error: {e}", exc_info=True)
            return False
