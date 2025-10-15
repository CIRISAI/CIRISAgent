"""Discord channel management component for client and channel operations."""

import logging
from typing import Any, Awaitable, Callable, Dict, List, Optional

import discord
from discord.errors import Forbidden, NotFound

from ciris_engine.logic.utils.privacy import sanitize_correlation_parameters
from ciris_engine.schemas.runtime.messages import DiscordMessage
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class DiscordChannelManager:
    """Handles Discord client management and channel operations."""

    def __init__(
        self,
        token: str,
        client: Optional[discord.Client] = None,
        on_message_callback: Optional[Callable[[DiscordMessage], Awaitable[None]]] = None,
        monitored_channel_ids: Optional[List[str]] = None,
        filter_service: Optional[Any] = None,
        consent_service: Optional[Any] = None,
    ) -> None:
        """Initialize the channel manager.

        Args:
            token: Discord bot token
            client: Optional Discord client instance
            on_message_callback: Callback for message handling
            monitored_channel_ids: List of channel IDs to monitor
            filter_service: Optional filter service for consent checking
            consent_service: Optional consent service for privacy handling
        """
        self.token = token
        self.client = client
        self.on_message_callback = on_message_callback
        self.monitored_channel_ids = monitored_channel_ids or []
        self.filter_service = filter_service
        self.consent_service = consent_service

    def set_client(self, client: discord.Client) -> None:
        """Set the Discord client after initialization.

        Args:
            client: Discord client instance
        """
        self.client = client

    def set_message_callback(self, callback: Callable[[DiscordMessage], Awaitable[None]]) -> None:
        """Set the message callback after initialization.

        Args:
            callback: Callback function for message events
        """
        self.on_message_callback = callback

    async def resolve_channel(self, channel_id: str) -> Optional[Any]:
        """Resolve a Discord channel by ID.

        Args:
            channel_id: The Discord channel ID as string

        Returns:
            Discord channel object or None if not found
        """
        if not self.client:
            logger.error("Discord client is not initialized")
            return None

        try:
            channel_id_int = int(channel_id)

            channel = self.client.get_channel(channel_id_int)
            if channel is not None:
                return channel

            try:
                channel = await self.client.fetch_channel(channel_id_int)
                return channel
            except (NotFound, Forbidden) as e:
                logger.error(f"Cannot access Discord channel {channel_id}: {e}")
                return None

        except ValueError:
            logger.error(f"Invalid Discord channel ID format: {channel_id}")
            return None
        except Exception as e:
            logger.exception(f"Unexpected error resolving channel {channel_id}: {e}")
            return None

    async def validate_channel_access(self, channel_id: str) -> bool:
        """Validate that the bot has access to a channel.

        Args:
            channel_id: The Discord channel ID

        Returns:
            True if channel is accessible, False otherwise
        """
        channel = await self.resolve_channel(channel_id)
        if not channel:
            return False

        if not hasattr(channel, "send"):
            logger.warning(f"Channel {channel_id} does not support sending messages")
            return False

        return True

    def is_client_ready(self) -> bool:
        """Check if the Discord client is ready and connected.

        Returns:
            True if client is ready, False otherwise
        """
        if not self.client:
            return False

        try:
            return not self.client.is_closed()
        except Exception:
            return False

    async def wait_for_client_ready(self, timeout: float = 30.0) -> bool:
        """Wait for the Discord client to be ready.

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            True if client became ready, False if timeout
        """
        if not self.client:
            return False

        try:
            if hasattr(self.client, "wait_until_ready"):
                await self.client.wait_until_ready()
                return True
            return self.is_client_ready()
        except Exception as e:
            logger.exception(f"Error waiting for Discord client: {e}")
            return False

    async def on_message(self, message: discord.Message) -> None:
        """Handle incoming Discord messages.

        Args:
            message: The Discord message object
        """
        # Skip creating passive observations for the bot's own messages
        if self.client and self.client.user and message.author.id == self.client.user.id:
            return

        # Format channel_id as discord_guildid_channelid for proper routing
        guild_id = str(message.guild.id) if hasattr(message, "guild") and message.guild else "dm"
        channel_id = f"discord_{guild_id}_{message.channel.id}"

        incoming = DiscordMessage(
            message_id=str(message.id),
            content=message.content,
            author_id=str(message.author.id),
            author_name=message.author.display_name,
            channel_id=channel_id,
            is_bot=message.author.bot,
            is_dm=getattr(getattr(message.channel, "__class__", None), "__name__", "") == "DMChannel",
            raw_message=message,
        )

        # Only create correlations for monitored channels
        should_create_correlation = (
            not self.monitored_channel_ids  # If no channels specified, monitor all
            or channel_id in self.monitored_channel_ids  # Or if this channel is monitored
            or str(message.channel.id) in self.monitored_channel_ids  # Check raw channel ID too
        )

        # Create an "observe" correlation for this incoming message (only if monitoring this channel)
        if should_create_correlation:
            try:
                import uuid
                from datetime import datetime, timezone

                from ciris_engine.logic import persistence
                from ciris_engine.schemas.telemetry.core import (
                    ServiceCorrelation,
                    ServiceCorrelationStatus,
                    ServiceRequestData,
                    ServiceResponseData,
                )

                now = datetime.now(timezone.utc)
                correlation_id = str(uuid.uuid4())

                correlation = ServiceCorrelation(
                    correlation_id=correlation_id,
                    service_type="discord",
                    handler_name="DiscordAdapter",
                    action_type="observe",
                    request_data=ServiceRequestData(
                        service_type="discord",
                        method_name="observe",
                        channel_id=channel_id,  # Use the full format discord_guildid_channelid
                        parameters=await self._sanitize_message_parameters(
                            {
                                "content": message.content,
                                "author_id": str(message.author.id),
                                "author_name": message.author.display_name,
                                "message_id": str(message.id),
                            },
                            str(message.author.id),
                        ),
                        request_timestamp=now,
                    ),
                    response_data=ServiceResponseData(
                        success=True, result_summary="Message observed", execution_time_ms=0, response_timestamp=now
                    ),
                    status=ServiceCorrelationStatus.COMPLETED,
                    created_at=now,
                    updated_at=now,
                    timestamp=now,
                )

                persistence.add_correlation(correlation, None)  # Discord doesn't have time_service
                logger.debug(f"Created observe correlation for Discord message {message.id} from channel {channel_id}")
            except Exception as e:
                logger.warning(f"Failed to create observe correlation: {e}")
        else:
            logger.debug(f"Skipping correlation for message {message.id} from unmonitored channel {channel_id}")

        if self.on_message_callback:
            try:
                await self.on_message_callback(incoming)
            except Exception as e:
                logger.exception(f"Error in message callback: {e}")

    def attach_to_client(self, client: discord.Client) -> None:
        """Attach message handler to a Discord client.

        Args:
            client: Discord client to attach to
        """
        self.client = client
        # Event handling is now done by CIRISDiscordClient

    def get_client_info(self) -> JSONDict:
        """Get information about the Discord client.

        Returns:
            Dictionary with client information
        """
        if not self.client:
            return {"status": "not_initialized", "user": None, "guilds": 0}

        try:
            return {
                "status": "ready" if not self.client.is_closed() else "closed",
                "user": str(self.client.user) if self.client.user else None,
                "guilds": len(self.client.guilds) if hasattr(self.client, "guilds") else 0,
                "latency": getattr(self.client, "latency", None),
            }
        except Exception as e:
            logger.exception(f"Error getting client info: {e}")
            return {"status": "error", "error": str(e)}

    async def get_channel_info(self, channel_id: str) -> JSONDict:
        """Get information about a Discord channel.

        Args:
            channel_id: The Discord channel ID

        Returns:
            Dictionary with channel information
        """
        channel = await self.resolve_channel(channel_id)
        if not channel:
            return {"exists": False, "accessible": False}

        try:
            info: JSONDict = {
                "exists": True,
                "accessible": True,
                "type": type(channel).__name__,
                "can_send": hasattr(channel, "send"),
                "can_read_history": hasattr(channel, "history"),
            }

            if hasattr(channel, "guild") and channel.guild:
                info["guild_name"] = channel.guild.name
                info["guild_id"] = str(channel.guild.id)

            if hasattr(channel, "name"):
                info["name"] = channel.name

            return info

        except Exception as e:
            logger.exception(f"Error getting channel info for {channel_id}: {e}")
            info_error: JSONDict = {"exists": True, "accessible": False, "error": str(e)}
            return info_error

    async def _sanitize_message_parameters(self, params: JSONDict, author_id: str) -> JSONDict:
        """
        Sanitize message parameters based on user consent.

        Checks user consent and applies privacy filters if needed.
        """
        try:
            # Try to get user consent stream
            consent_stream = await self._get_user_consent_stream(author_id)

            # If user is anonymous, sanitize the parameters
            if consent_stream in ["anonymous", "expired", "revoked"]:
                return sanitize_correlation_parameters(params, consent_stream)

            return params
        except Exception as e:
            logger.debug(f"Could not sanitize parameters: {e}")
            return params

    async def _get_user_consent_stream(self, user_id: str) -> Optional[str]:
        """
        Get user's consent stream for privacy handling.

        Returns consent stream or None if not found.
        """
        try:
            # Try to get consent from consent service if available
            if self.consent_service:
                try:
                    consent = await self.consent_service.get_consent(user_id)
                    return consent.stream.value if consent else None
                except Exception:
                    pass

            # Try to get from filter service if available
            if self.filter_service:
                if hasattr(self.filter_service, "_config") and self.filter_service._config:
                    if user_id in self.filter_service._config.user_profiles:
                        profile = self.filter_service._config.user_profiles[user_id]
                        consent_stream_value = profile.consent_stream
                        # Return as string if it exists, otherwise None
                        return str(consent_stream_value) if consent_stream_value is not None else None

            return None
        except Exception as e:
            logger.debug(f"Could not get consent stream for {user_id}: {e}")
            return None
