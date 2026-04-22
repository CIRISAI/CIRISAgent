"""
Discord Tool Suite: Moderation, Channel Management, and Info Tools
Implements async tool handlers and registration for CIRIS ToolRegistry.
"""

from typing import Any, Optional

import discord

from ciris_engine.schemas.adapters.tools import ToolResult


async def discord_delete_message(bot: discord.Client, channel_id: int, message_id: int) -> ToolResult:
    try:
        channel = bot.get_channel(channel_id) or await bot.fetch_channel(channel_id)
        if hasattr(channel, "fetch_message"):
            msg = await channel.fetch_message(message_id)
            await msg.delete()
        else:
            raise ValueError(f"Channel {channel_id} does not support message fetching")
        return ToolResult(success=True, data={"message_id": str(message_id), "channel_id": str(channel_id)}, error=None)
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


async def discord_timeout_user(
    bot: discord.Client, guild_id: int, user_id: int, duration_seconds: int, reason: Optional[str] = None
) -> ToolResult:
    try:
        guild = bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)
        member = guild.get_member(user_id) or await guild.fetch_member(user_id)
        from datetime import timedelta

        until = discord.utils.utcnow() + timedelta(seconds=duration_seconds)
        await member.timeout(until, reason=reason)
        return ToolResult(
            success=True,
            data={"user_id": str(user_id), "guild_id": str(guild_id), "until": until.isoformat()},
            error=None,
        )
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


async def discord_ban_user(
    bot: discord.Client, guild_id: int, user_id: int, reason: Optional[str] = None, delete_message_days: int = 0
) -> ToolResult:
    try:
        guild = bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)
        user = await guild.fetch_member(user_id)
        await guild.ban(user, reason=reason, delete_message_days=delete_message_days)
        return ToolResult(success=True, data={"user_id": str(user_id), "guild_id": str(guild_id)}, error=None)
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


async def discord_kick_user(
    bot: discord.Client, guild_id: int, user_id: int, reason: Optional[str] = None
) -> ToolResult:
    try:
        guild = bot.get_guild(guild_id) or await bot.fetch_guild(guild_id)
        user = await guild.fetch_member(user_id)
        await guild.kick(user, reason=reason)
        return ToolResult(success=True, data={"user_id": str(user_id), "guild_id": str(guild_id)}, error=None)
    except Exception as e:
        return ToolResult(success=False, data=None, error=str(e))


def register_discord_tools(registry: Any, bot: Any) -> None:
    """Register Discord tools in the ToolRegistry."""
    registry.register_tool(
        "discord_delete_message",
        schema={"channel_id": int, "message_id": int},
        handler=lambda args: discord_delete_message(bot, **args),
    )
    registry.register_tool(
        "discord_timeout_user",
        schema={"guild_id": int, "user_id": int, "duration_seconds": int, "reason": (str, type(None))},
        handler=lambda args: discord_timeout_user(bot, **args),
    )
    registry.register_tool(
        "discord_ban_user",
        schema={"guild_id": int, "user_id": int, "reason": (str, type(None)), "delete_message_days": int},
        handler=lambda args: discord_ban_user(bot, **args),
    )
    registry.register_tool(
        "discord_kick_user",
        schema={"guild_id": int, "user_id": int, "reason": (str, type(None))},
        handler=lambda args: discord_kick_user(bot, **args),
    )
