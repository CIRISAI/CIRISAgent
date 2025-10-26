"""Utilities for channel context management."""

from typing import Optional, Union

from ciris_engine.schemas.runtime.system_context import ChannelContext


def create_channel_context(
    channel_id: Union[str, ChannelContext, None],
    channel_name: Optional[str] = None,
    channel_type: Optional[str] = None,
) -> Optional[ChannelContext]:
    """
    Create a ChannelContext from various inputs.

    Args:
        channel_id: Channel ID string or existing ChannelContext
        channel_name: Human-readable channel name
        channel_type: Type of channel (discord, cli, api, etc.)

    Returns:
        ChannelContext instance or None if no valid input
    """
    if channel_id is None:
        return None

    if isinstance(channel_id, ChannelContext):
        return channel_id

    # Must be a string at this point
    channel_id_str = channel_id

    # Infer channel type from ID patterns if not provided
    if channel_type is None:
        if channel_id_str.startswith("cli_") or channel_id_str.startswith("cli-"):
            channel_type = "cli"
        elif channel_id_str.startswith("api_") or channel_id_str.startswith("api-"):
            channel_type = "api"
        elif channel_id_str.startswith("discord_"):
            channel_type = "discord"
        elif channel_id_str.startswith("reddit:"):
            channel_type = "reddit"
        elif channel_id_str.isdigit() and len(channel_id_str) >= 17:  # Discord IDs are 17-19 digits
            channel_type = "discord"
        else:
            channel_type = "unknown"

    from datetime import datetime, timezone

    return ChannelContext(
        channel_id=channel_id_str,
        channel_name=channel_name,
        channel_type=channel_type,
        created_at=datetime.now(timezone.utc),
        is_private=False,
        is_active=True,
    )


def extract_channel_id(channel_context: Optional[Union[str, ChannelContext]]) -> Optional[str]:
    """
    Extract channel ID from either a string or ChannelContext.

    Args:
        channel_context: Channel ID string or ChannelContext instance

    Returns:
        Channel ID string or None
    """
    if channel_context is None:
        return None
    if isinstance(channel_context, str):
        return channel_context
    # Must be ChannelContext at this point
    return channel_context.channel_id
