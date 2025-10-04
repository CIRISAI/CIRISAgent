"""
CIRIS Discord Client - Custom discord.py client with event handlers.

This module provides a custom Discord client that integrates with CIRIS's
adapter architecture, handling events like messages, reactions, threads, etc.
"""

import logging
from typing import TYPE_CHECKING, Any

import discord

if TYPE_CHECKING:
    from ciris_engine.logic.adapters.discord.adapter import DiscordPlatform

logger = logging.getLogger(__name__)


class CIRISDiscordClient(discord.Client):
    """Custom Discord client with CIRIS-specific event handling."""

    def __init__(self, platform: "DiscordPlatform", *args: Any, **kwargs: Any) -> None:
        """
        Initialize CIRIS Discord client.

        Args:
            platform: The DiscordPlatform instance this client belongs to
            *args: Positional arguments for discord.Client
            **kwargs: Keyword arguments for discord.Client
        """
        super().__init__(*args, **kwargs)
        self.platform = platform

    async def on_ready(self) -> None:
        """Called when the client is ready and connected to Discord."""
        logger.info("Discord client on_ready event")
        # Let the connection manager know
        if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
            conn_mgr = self.platform.discord_adapter._connection_manager
            if conn_mgr and hasattr(conn_mgr, "_handle_connected"):
                await conn_mgr._handle_connected()

        # Fetch and monitor threads in monitored channels
        await self._fetch_threads_in_monitored_channels()

    async def _fetch_threads_in_monitored_channels(self) -> None:
        """Fetch all threads in monitored channels and add them to monitoring."""
        if not (hasattr(self.platform, "config") and self.platform.config):
            return

        logger.info("Fetching threads in monitored channels...")
        threads_added = 0

        for channel_id in self.platform.config.monitored_channel_ids:
            try:
                channel = self.get_channel(int(channel_id))
                if channel and isinstance(channel, discord.TextChannel):
                    # Get active threads in this channel
                    for thread in channel.threads:
                        thread_id = str(thread.id)
                        # Add to observer if it exists and not already monitored
                        if hasattr(self.platform, "discord_observer") and self.platform.discord_observer:
                            if thread_id not in self.platform.discord_observer.monitored_channel_ids:
                                self.platform.discord_observer.monitored_channel_ids.append(thread_id)
                                threads_added += 1
                                logger.debug(f"Added thread {thread_id} to monitoring")
            except Exception as e:
                logger.warning(f"Could not fetch threads for channel {channel_id}: {e}")

        if threads_added > 0:
            logger.info(f"Added {threads_added} threads to monitoring")

    async def on_disconnect(self) -> None:
        """Called when the client disconnects from Discord."""
        logger.warning("Discord client on_disconnect event")
        # Let the connection manager know
        if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
            conn_mgr = self.platform.discord_adapter._connection_manager
            if conn_mgr and hasattr(conn_mgr, "_handle_disconnected"):
                await conn_mgr._handle_disconnected(None)

    async def on_message(self, message: discord.Message) -> None:
        """
        Called when a message is received.

        Args:
            message: The Discord message object
        """
        # Let the channel manager handle it
        if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
            channel_mgr = self.platform.discord_adapter._channel_manager
            if channel_mgr and hasattr(channel_mgr, "on_message"):
                await channel_mgr.on_message(message)

    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent) -> None:
        """
        Called when a reaction is added to a message.

        Args:
            payload: The reaction event payload
        """
        # Let the discord adapter handle it
        if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
            await self.platform.discord_adapter.on_raw_reaction_add(payload)

    async def on_thread_create(self, thread: discord.Thread) -> None:
        """
        Called when a thread is created in a monitored channel.

        Args:
            thread: The created thread object
        """
        logger.info(f"Thread created: {thread.name} (ID: {thread.id}) in parent {thread.parent_id}")
        # Check if parent channel is monitored
        if hasattr(self.platform, "discord_adapter") and self.platform.discord_adapter:
            if hasattr(self.platform, "discord_observer") and self.platform.discord_observer:
                observer = self.platform.discord_observer
                if hasattr(self.platform, "config") and self.platform.config:
                    parent_id = str(thread.parent_id)
                    if parent_id in self.platform.config.monitored_channel_ids:
                        # Add thread to monitored channels
                        thread_id = str(thread.id)
                        if thread_id not in observer.monitored_channel_ids:
                            observer.monitored_channel_ids.append(thread_id)
                            logger.info(
                                f"Added thread {thread_id} to monitored channels (parent {parent_id} is monitored)"
                            )

                            # Thread correlation persistence would require ServiceCorrelation,
                            # not CorrelationRequestData. This needs proper implementation
                            # with correlation_id, service_type, handler_name, etc.
                            # For now, in-memory tracking is sufficient for Discord threads.

    async def on_thread_join(self, thread: discord.Thread) -> None:
        """
        Called when the bot joins a thread.

        Args:
            thread: The thread that was joined
        """
        logger.info(f"Bot joined thread: {thread.name} (ID: {thread.id})")
        # Use same logic as on_thread_create
        await self.on_thread_create(thread)

    async def on_thread_delete(self, thread: discord.Thread) -> None:
        """
        Called when a thread is deleted.

        Args:
            thread: The deleted thread object
        """
        logger.info(f"Thread deleted: {thread.name} (ID: {thread.id})")
        # Remove from monitored channels if present
        if hasattr(self.platform, "discord_observer") and self.platform.discord_observer:
            observer = self.platform.discord_observer
            thread_id = str(thread.id)
            if thread_id in observer.monitored_channel_ids:
                observer.monitored_channel_ids.remove(thread_id)
                logger.info(f"Removed deleted thread {thread_id} from monitored channels")
