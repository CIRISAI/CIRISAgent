"""Discord message handling component for the Discord adapter."""

import asyncio
import logging
from typing import Any, List, Optional

import discord

from ciris_engine.schemas.runtime.messages import DiscordMessage, FetchedMessage

logger = logging.getLogger(__name__)


class DiscordMessageHandler:
    """Handles Discord message operations including sending, fetching, and splitting."""

    def __init__(self, client: Optional[discord.Client] = None) -> None:
        """Initialize the message handler.

        Args:
            client: Discord client instance
        """
        self.client = client

    def set_client(self, client: discord.Client) -> None:
        """Set the Discord client after initialization.

        Args:
            client: Discord client instance
        """
        self.client = client

    async def send_message_to_channel(self, channel_id: str, content: str) -> None:
        """Send a message to a Discord channel, splitting if necessary.

        Args:
            channel_id: The Discord channel ID
            content: Message content to send

        Raises:
            RuntimeError: If client is not initialized or channel not found
        """
        if not self.client:
            raise ValueError("Discord client is not initialized")

        # Wait for client to be ready - this will wait through reconnections
        # wait_until_ready() handles the case where the client is closed and reconnecting
        if hasattr(self.client, "wait_until_ready"):
            # This method waits until the client's internal cache is ready
            # It will wait through disconnections and reconnections
            await self.client.wait_until_ready()

        channel = await self._resolve_channel(channel_id)
        if not channel:
            raise ValueError(f"Discord channel {channel_id} not found")

        chunks = self._split_message(content)

        for i, chunk in enumerate(chunks):
            if len(chunks) > 1:
                if i == 0:
                    chunk = f"{chunk}\n\n*(Message continues...)*"
                elif i < len(chunks) - 1:
                    chunk = f"*(Continued from previous message)*\n\n{chunk}\n\n*(Message continues...)*"
                else:
                    chunk = f"*(Continued from previous message)*\n\n{chunk}"

            await channel.send(chunk)

            if i < len(chunks) - 1:
                await asyncio.sleep(0.5)

    async def fetch_messages_from_channel(self, channel_id: str, limit: int) -> List[FetchedMessage]:
        """Fetch messages from a Discord channel.

        Args:
            channel_id: The Discord channel ID
            limit: Maximum number of messages to fetch

        Returns:
            List of fetched messages

        Raises:
            RuntimeError: If client is not initialized
        """
        if not self.client:
            raise ValueError("Discord client is not initialized")

        channel = await self._resolve_channel(channel_id)
        if not channel or not hasattr(channel, "history"):
            logger.error(f"Could not find Discord channel with ID {channel_id}")
            return []

        messages: List[FetchedMessage] = []
        async for message in channel.history(limit=limit):
            messages.append(
                FetchedMessage(
                    id=str(message.id),
                    content=message.content,
                    author_id=str(message.author.id),
                    author_name=message.author.display_name,
                    timestamp=message.created_at.isoformat(),
                    is_bot=message.author.bot,
                )
            )
        return messages

    def convert_to_discord_message(self, message: discord.Message) -> DiscordMessage:
        """Convert a discord.py message to DiscordMessage schema.

        Args:
            message: The discord.py message object

        Returns:
            DiscordMessage schema object
        """
        return DiscordMessage(
            message_id=str(message.id),
            content=message.content,
            author_id=str(message.author.id),
            author_name=message.author.display_name,
            channel_id=str(message.channel.id),
            is_bot=message.author.bot,
            is_dm=getattr(getattr(message.channel, "__class__", None), "__name__", "") == "DMChannel",
            raw_message=message,
        )

    def _split_message(self, content: str, max_length: int = 1950) -> List[str]:
        """Split a message into chunks that fit Discord's character limit.

        Args:
            content: The message content to split
            max_length: Maximum length per message (default 1950 to leave room for formatting)

        Returns:
            List of message chunks
        """
        if len(content) <= max_length:
            return [content]

        chunks = []
        lines = content.split("\n")
        current_chunk = ""

        for line in lines:
            if len(line) > max_length:
                if current_chunk:
                    chunks.append(current_chunk.rstrip())
                    current_chunk = ""

                for i in range(0, len(line), max_length):
                    chunks.append(line[i : i + max_length])
            else:
                if len(current_chunk) + len(line) + 1 > max_length:
                    chunks.append(current_chunk.rstrip())
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"

        if current_chunk:
            chunks.append(current_chunk.rstrip())

        return chunks

    async def _resolve_channel(self, channel_id: str) -> Optional[Any]:
        """Resolve a Discord channel by ID.

        Args:
            channel_id: The Discord channel ID
                Supported formats:
                - discord_channelid (e.g., discord_1382010877171073108)
                - discord_guildid_channelid (e.g., discord_1364300186003968060_1382010877171073108)
                - channelid (e.g., 1382010877171073108)

        Returns:
            Discord channel object or None if not found
        """
        if not self.client:
            return None

        # Parse the channel ID from various formats
        parsed_channel_id = channel_id

        # Handle discord_guildid_channelid format
        if channel_id.startswith("discord_") and channel_id.count("_") == 2:
            # Format: discord_guildid_channelid
            parts = channel_id.split("_")
            parsed_channel_id = parts[2]  # Get the channel ID part
            logger.debug(f"Parsed channel ID from discord_guild_channel format: {parsed_channel_id}")

        # Handle discord_channelid format
        elif channel_id.startswith("discord_"):
            # Format: discord_channelid
            parsed_channel_id = channel_id.replace("discord_", "")
            logger.debug(f"Parsed channel ID from discord_channel format: {parsed_channel_id}")

        # Otherwise assume it's already a plain channel ID

        try:
            channel_id_int = int(parsed_channel_id)
            channel = self.client.get_channel(channel_id_int)
            if channel is None:
                channel = await self.client.fetch_channel(channel_id_int)
            return channel
        except (ValueError, discord.NotFound, discord.Forbidden):
            logger.error(f"Could not resolve Discord channel {channel_id} (parsed as {parsed_channel_id})")
            return None
