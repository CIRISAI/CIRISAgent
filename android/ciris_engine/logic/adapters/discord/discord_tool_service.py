"""
Discord Tool Service - provides Discord-specific tools following the ToolService protocol.
"""

import logging
import uuid
from datetime import timedelta
from typing import Any, Dict, List, Optional

import discord

from ciris_engine.protocols.services import ToolService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


class DiscordToolService(ToolService):
    """Tool service providing Discord-specific moderation and management tools."""

    def __init__(
        self, client: Optional[discord.Client] = None, time_service: Optional[TimeServiceProtocol] = None
    ) -> None:
        super().__init__()
        self._client = client
        self._time_service = time_service
        self._results: Dict[str, ToolExecutionResult] = {}
        self._tool_executions = 0
        self._tool_failures = 0

        # Define available tools
        self._tools = {
            "discord_send_message": self._send_message,
            "discord_send_embed": self._send_embed,
            "discord_delete_message": self._delete_message,
            "discord_timeout_user": self._timeout_user,
            "discord_ban_user": self._ban_user,
            "discord_kick_user": self._kick_user,
            "discord_add_role": self._add_role,
            "discord_remove_role": self._remove_role,
            "discord_get_user_info": self._get_user_info,
            "discord_get_channel_info": self._get_channel_info,
            "discord_get_guild_moderators": self._get_guild_moderators,
        }

    def set_client(self, client: discord.Client) -> None:
        """Update the Discord client instance."""
        self._client = client

    async def start(self) -> None:
        """Start the Discord tool service."""
        logger.info("Discord tool service started")

    async def stop(self) -> None:
        """Stop the Discord tool service."""
        logger.info("Discord tool service stopped")

    async def execute_tool(self, tool_name: str, parameters: JSONDict) -> ToolExecutionResult:
        """Execute a Discord tool and return the result."""
        logger.info(f"[DISCORD_TOOLS] execute_tool called with tool_name={tool_name}, parameters={parameters}")

        correlation_id_raw = parameters.get("correlation_id", str(uuid.uuid4()))
        correlation_id = str(correlation_id_raw) if correlation_id_raw else str(uuid.uuid4())
        self._tool_executions += 1

        if not self._client:
            self._tool_failures += 1
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error="Discord client not initialized",
                correlation_id=correlation_id,
            )

        if tool_name not in self._tools:
            self._tool_executions += 1  # Must increment total count
            self._tool_failures += 1  # Unknown tool is a failure!
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown Discord tool: {tool_name}",
                correlation_id=correlation_id,
            )

        try:
            # Remove correlation_id from parameters before passing to tool
            tool_params = {k: v for k, v in parameters.items() if k != "correlation_id"}
            result = await self._tools[tool_name](tool_params)

            success = result.get("success", False)
            error_msg = result.get("error")

            tool_result = ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.COMPLETED if success else ToolExecutionStatus.FAILED,
                success=success,
                data=result.get("data"),
                error=error_msg,
                correlation_id=correlation_id,
            )

            if correlation_id:
                self._results[correlation_id] = tool_result

            return tool_result

        except Exception as e:
            logger.error(f"Error executing Discord tool {tool_name}: {e}", exc_info=True)
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )

    # Tool implementations
    async def _send_message(self, params: JSONDict) -> JSONDict:
        """Send a message to a Discord channel."""
        channel_id_raw = params.get("channel_id")
        content_raw = params.get("content")

        if not channel_id_raw or not content_raw:
            return {"success": False, "error": "channel_id and content are required"}

        channel_id = str(channel_id_raw)
        content = str(content_raw)

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            channel = self._client.get_channel(int(channel_id))
            if not channel:
                channel = await self._client.fetch_channel(int(channel_id))

            # Type narrowing for channels that support sending
            if isinstance(
                channel,
                (discord.TextChannel, discord.DMChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel),
            ):
                message = await channel.send(content)
            else:
                return {
                    "success": False,
                    "error": f"Channel type {type(channel).__name__} does not support sending messages",
                }
            return {"success": True, "data": {"message_id": str(message.id), "channel_id": str(channel_id)}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _send_embed(self, params: JSONDict) -> JSONDict:
        """Send an embed message to a Discord channel."""
        channel_id_raw = params.get("channel_id")
        title_raw = params.get("title", "")
        description_raw = params.get("description", "")
        color_raw = params.get("color", 0x3498DB)
        fields_raw = params.get("fields", [])

        if not channel_id_raw:
            return {"success": False, "error": "Channel ID is required"}

        channel_id = str(channel_id_raw)
        title = str(title_raw)
        description = str(description_raw)
        color = int(color_raw) if isinstance(color_raw, (int, float, str)) else 0x3498DB
        fields = fields_raw if isinstance(fields_raw, list) else []

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            channel = self._client.get_channel(int(channel_id))
            if not channel:
                channel = await self._client.fetch_channel(int(channel_id))

            embed = discord.Embed(title=title, description=description, color=color)
            for field in fields:
                if isinstance(field, dict):
                    embed.add_field(
                        name=str(field.get("name", "")),
                        value=str(field.get("value", "")),
                        inline=bool(field.get("inline", False)),
                    )

            # Type narrowing for channels that support sending
            if isinstance(
                channel,
                (discord.TextChannel, discord.DMChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel),
            ):
                message = await channel.send(embed=embed)
            else:
                return {
                    "success": False,
                    "error": f"Channel type {type(channel).__name__} does not support sending messages",
                }
            return {"success": True, "data": {"message_id": str(message.id), "channel_id": str(channel_id)}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _delete_message(self, params: JSONDict) -> JSONDict:
        """Delete a message from a Discord channel."""
        channel_id_raw = params.get("channel_id")
        message_id_raw = params.get("message_id")

        if not channel_id_raw or not message_id_raw:
            return {"success": False, "error": "channel_id and message_id are required"}

        channel_id = str(channel_id_raw)
        message_id = str(message_id_raw)

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            channel = self._client.get_channel(int(channel_id))
            if not channel:
                channel = await self._client.fetch_channel(int(channel_id))

            # Type narrowing for channels that support fetching messages
            if isinstance(
                channel,
                (discord.TextChannel, discord.DMChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel),
            ):
                message = await channel.fetch_message(int(message_id))
            else:
                return {
                    "success": False,
                    "error": f"Channel type {type(channel).__name__} does not support fetching messages",
                }
            await message.delete()

            return {"success": True, "data": {"message_id": str(message_id), "channel_id": str(channel_id)}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _timeout_user(self, params: JSONDict) -> JSONDict:
        """Timeout a user in a guild."""
        guild_id_raw = params.get("guild_id")
        user_id_raw = params.get("user_id")
        duration_seconds_raw = params.get("duration_seconds", 300)  # Default 5 minutes
        reason_raw = params.get("reason")

        if not guild_id_raw or not user_id_raw:
            return {"success": False, "error": "guild_id and user_id are required"}

        guild_id = str(guild_id_raw)
        user_id = str(user_id_raw)
        duration_seconds = int(duration_seconds_raw) if isinstance(duration_seconds_raw, (int, float, str)) else 300
        reason = str(reason_raw) if reason_raw else None

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            guild = self._client.get_guild(int(guild_id))
            if not guild:
                return {"success": False, "error": f"Guild {guild_id} not found"}

            member = guild.get_member(int(user_id))
            if not member:
                member = await guild.fetch_member(int(user_id))

            until = discord.utils.utcnow() + timedelta(seconds=duration_seconds)
            await member.timeout(until, reason=reason)

            return {
                "success": True,
                "data": {
                    "user_id": str(user_id),
                    "guild_id": str(guild_id),
                    "until": until.isoformat(),
                    "duration_seconds": duration_seconds,
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _ban_user(self, params: JSONDict) -> JSONDict:
        """Ban a user from a guild."""
        guild_id_raw = params.get("guild_id")
        user_id_raw = params.get("user_id")
        reason_raw = params.get("reason")
        delete_message_days_raw = params.get("delete_message_days", 0)

        if not guild_id_raw or not user_id_raw:
            return {"success": False, "error": "guild_id and user_id are required"}

        guild_id = str(guild_id_raw)
        user_id = str(user_id_raw)
        reason = str(reason_raw) if reason_raw else None
        delete_message_days = (
            int(delete_message_days_raw) if isinstance(delete_message_days_raw, (int, float, str)) else 0
        )

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            guild = self._client.get_guild(int(guild_id))
            if not guild:
                return {"success": False, "error": f"Guild {guild_id} not found"}

            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            user = await self._client.fetch_user(int(user_id))
            await guild.ban(user, reason=reason, delete_message_days=delete_message_days)

            return {"success": True, "data": {"user_id": str(user_id), "guild_id": str(guild_id)}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _kick_user(self, params: JSONDict) -> JSONDict:
        """Kick a user from a guild."""
        guild_id_raw = params.get("guild_id")
        user_id_raw = params.get("user_id")
        reason_raw = params.get("reason")

        if not guild_id_raw or not user_id_raw:
            return {"success": False, "error": "guild_id and user_id are required"}

        guild_id = str(guild_id_raw)
        user_id = str(user_id_raw)
        reason = str(reason_raw) if reason_raw else None

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            guild = self._client.get_guild(int(guild_id))
            if not guild:
                return {"success": False, "error": f"Guild {guild_id} not found"}

            member = guild.get_member(int(user_id))
            if not member:
                member = await guild.fetch_member(int(user_id))

            await member.kick(reason=reason)

            return {"success": True, "data": {"user_id": str(user_id), "guild_id": str(guild_id)}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _add_role(self, params: JSONDict) -> JSONDict:
        """Add a role to a user."""
        guild_id_raw = params.get("guild_id")
        user_id_raw = params.get("user_id")
        role_name_raw = params.get("role_name")

        if not guild_id_raw or not user_id_raw or not role_name_raw:
            return {"success": False, "error": "guild_id, user_id, and role_name are required"}

        guild_id = str(guild_id_raw)
        user_id = str(user_id_raw)
        role_name = str(role_name_raw)

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            guild = self._client.get_guild(int(guild_id))
            if not guild:
                return {"success": False, "error": f"Guild {guild_id} not found"}

            member = guild.get_member(int(user_id))
            if not member:
                member = await guild.fetch_member(int(user_id))

            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                return {"success": False, "error": f"Role '{role_name}' not found"}

            await member.add_roles(role)

            return {
                "success": True,
                "data": {
                    "user_id": str(user_id),
                    "guild_id": str(guild_id),
                    "role_name": role_name,
                    "role_id": str(role.id),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _remove_role(self, params: JSONDict) -> JSONDict:
        """Remove a role from a user."""
        guild_id_raw = params.get("guild_id")
        user_id_raw = params.get("user_id")
        role_name_raw = params.get("role_name")

        if not guild_id_raw or not user_id_raw or not role_name_raw:
            return {"success": False, "error": "guild_id, user_id, and role_name are required"}

        guild_id = str(guild_id_raw)
        user_id = str(user_id_raw)
        role_name = str(role_name_raw)

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            guild = self._client.get_guild(int(guild_id))
            if not guild:
                return {"success": False, "error": f"Guild {guild_id} not found"}

            member = guild.get_member(int(user_id))
            if not member:
                member = await guild.fetch_member(int(user_id))

            role = discord.utils.get(guild.roles, name=role_name)
            if not role:
                return {"success": False, "error": f"Role '{role_name}' not found"}

            await member.remove_roles(role)

            return {
                "success": True,
                "data": {
                    "user_id": str(user_id),
                    "guild_id": str(guild_id),
                    "role_name": role_name,
                    "role_id": str(role.id),
                },
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _get_user_info(self, params: JSONDict) -> JSONDict:
        """Get information about a Discord user."""
        user_id_raw = params.get("user_id")
        guild_id_raw = params.get("guild_id")  # Optional, for guild-specific info

        if not user_id_raw:
            return {"success": False, "error": "user_id is required"}

        user_id = str(user_id_raw)
        guild_id = str(guild_id_raw) if guild_id_raw else None

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            user = await self._client.fetch_user(int(user_id))

            data: JSONDict = {
                "user_id": str(user.id),
                "username": user.name,
                "discriminator": user.discriminator,
                "avatar_url": str(user.avatar.url) if user.avatar else None,
                "bot": user.bot,
                "created_at": user.created_at.isoformat(),
            }

            # Add guild-specific info if guild_id provided
            if guild_id:
                if not self._client:
                    return {"success": False, "error": "Discord client not initialized"}
                guild = self._client.get_guild(int(guild_id))
                if guild:
                    member = guild.get_member(int(user_id))
                    if member:
                        data["nickname"] = member.nick
                        data["joined_at"] = member.joined_at.isoformat() if member.joined_at else None
                        data["roles"] = [role.name for role in member.roles if role.name != "@everyone"]

            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _get_channel_info(self, params: JSONDict) -> JSONDict:
        """Get information about a Discord channel."""
        channel_id_raw = params.get("channel_id")

        if not channel_id_raw:
            return {"success": False, "error": "Channel ID is required"}

        channel_id = str(channel_id_raw)

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}
            channel = self._client.get_channel(int(channel_id))
            if not channel:
                channel = await self._client.fetch_channel(int(channel_id))

            data = {
                "channel_id": str(channel.id),
                "name": getattr(channel, "name", "Unknown"),
                "type": str(getattr(channel, "type", "Unknown")),
                "created_at": (
                    channel.created_at.isoformat() if hasattr(channel, "created_at") and channel.created_at else None
                ),
            }

            # Add guild info if it's a guild channel
            if hasattr(channel, "guild"):
                data["guild_id"] = str(channel.guild.id)
                data["guild_name"] = channel.guild.name

            # Add text channel specific info
            if hasattr(channel, "topic"):
                data["topic"] = channel.topic

            return {"success": True, "data": data}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _get_guild_moderators(self, params: JSONDict) -> JSONDict:
        """Get list of guild members with moderator permissions, excluding ECHO users."""
        guild_id_raw = params.get("guild_id")

        if not guild_id_raw:
            return {"success": False, "error": "guild_id is required"}

        guild_id = str(guild_id_raw)

        try:
            if not self._client:
                return {"success": False, "error": "Discord client not initialized"}

            guild = self._client.get_guild(int(guild_id))
            if not guild:
                guild = await self._client.fetch_guild(int(guild_id))

            if not guild:
                return {"success": False, "error": f"Guild with ID {guild_id} not found"}

            moderators = []

            # Iterate through guild members to find those with moderator permissions
            async for member in guild.fetch_members(limit=None):
                # Check if user has moderator permissions (can manage messages, kick, ban, etc.)
                if (
                    member.guild_permissions.manage_messages
                    or member.guild_permissions.kick_members
                    or member.guild_permissions.ban_members
                    or member.guild_permissions.manage_roles
                ):

                    # Filter out ECHO users
                    if "ECHO" not in str(member.display_name).upper() and "ECHO" not in str(member.name).upper():
                        moderators.append(
                            {
                                "user_id": str(member.id),
                                "username": member.name,
                                "display_name": member.display_name,
                                "nickname": member.nick,
                            }
                        )

            return {"success": True, "data": {"moderators": moderators}}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_available_tools(self) -> List[str]:
        """Get list of available Discord tools."""
        return list(self._tools.keys())

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of a tool execution by correlation ID."""
        # All Discord tools are synchronous, so results are available immediately
        return self._results.get(correlation_id)

    async def validate_parameters(self, tool_name: str, parameters: JSONDict) -> bool:
        """Validate parameters for a Discord tool."""
        required_params = {
            "discord_send_message": ["channel_id", "content"],
            "discord_send_embed": ["channel_id"],
            "discord_delete_message": ["channel_id", "message_id"],
            "discord_timeout_user": ["guild_id", "user_id"],
            "discord_ban_user": ["guild_id", "user_id"],
            "discord_kick_user": ["guild_id", "user_id"],
            "discord_add_role": ["guild_id", "user_id", "role_name"],
            "discord_remove_role": ["guild_id", "user_id", "role_name"],
            "discord_get_user_info": ["user_id"],
            "discord_get_channel_info": ["channel_id"],
            "discord_get_guild_moderators": ["guild_id"],
        }

        if tool_name not in required_params:
            return False

        return all(param in parameters for param in required_params[tool_name])

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed information about a specific Discord tool."""
        tool_schemas = {
            "discord_send_message": ToolParameterSchema(
                type="object",
                properties={
                    "channel_id": {"type": "string", "description": "Discord channel ID"},
                    "content": {"type": "string", "description": "Message content to send"},
                },
                required=["channel_id", "content"],
            ),
            "discord_send_embed": ToolParameterSchema(
                type="object",
                properties={
                    "channel_id": {"type": "string", "description": "Discord channel ID"},
                    "title": {"type": "string", "description": "Embed title"},
                    "description": {"type": "string", "description": "Embed description"},
                    "color": {"type": "integer", "description": "Embed color (hex)"},
                    "fields": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "name": {"type": "string"},
                                "value": {"type": "string"},
                                "inline": {"type": "boolean"},
                            },
                        },
                    },
                },
                required=["channel_id"],
            ),
            "discord_delete_message": ToolParameterSchema(
                type="object",
                properties={
                    "channel_id": {"type": "string", "description": "Discord channel ID"},
                    "message_id": {"type": "string", "description": "Message ID to delete"},
                },
                required=["channel_id", "message_id"],
            ),
            "discord_timeout_user": ToolParameterSchema(
                type="object",
                properties={
                    "guild_id": {"type": "string", "description": "Discord guild ID"},
                    "user_id": {"type": "string", "description": "User ID to timeout"},
                    "duration_seconds": {
                        "type": "integer",
                        "description": "Timeout duration in seconds",
                        "default": 300,
                    },
                    "reason": {"type": "string", "description": "Reason for timeout"},
                },
                required=["guild_id", "user_id"],
            ),
            "discord_ban_user": ToolParameterSchema(
                type="object",
                properties={
                    "guild_id": {"type": "string", "description": "Discord guild ID"},
                    "user_id": {"type": "string", "description": "User ID to ban"},
                    "reason": {"type": "string", "description": "Reason for ban"},
                    "delete_message_days": {
                        "type": "integer",
                        "description": "Days of messages to delete",
                        "default": 0,
                    },
                },
                required=["guild_id", "user_id"],
            ),
            "discord_kick_user": ToolParameterSchema(
                type="object",
                properties={
                    "guild_id": {"type": "string", "description": "Discord guild ID"},
                    "user_id": {"type": "string", "description": "User ID to kick"},
                    "reason": {"type": "string", "description": "Reason for kick"},
                },
                required=["guild_id", "user_id"],
            ),
            "discord_add_role": ToolParameterSchema(
                type="object",
                properties={
                    "guild_id": {"type": "string", "description": "Discord guild ID"},
                    "user_id": {"type": "string", "description": "User ID"},
                    "role_name": {"type": "string", "description": "Name of role to add"},
                },
                required=["guild_id", "user_id", "role_name"],
            ),
            "discord_remove_role": ToolParameterSchema(
                type="object",
                properties={
                    "guild_id": {"type": "string", "description": "Discord guild ID"},
                    "user_id": {"type": "string", "description": "User ID"},
                    "role_name": {"type": "string", "description": "Name of role to remove"},
                },
                required=["guild_id", "user_id", "role_name"],
            ),
            "discord_get_user_info": ToolParameterSchema(
                type="object",
                properties={
                    "user_id": {"type": "string", "description": "User ID to get info for"},
                    "guild_id": {"type": "string", "description": "Optional guild ID for guild-specific info"},
                },
                required=["user_id"],
            ),
            "discord_get_channel_info": ToolParameterSchema(
                type="object",
                properties={"channel_id": {"type": "string", "description": "Channel ID to get info for"}},
                required=["channel_id"],
            ),
            "discord_get_guild_moderators": ToolParameterSchema(
                type="object",
                properties={"guild_id": {"type": "string", "description": "Guild ID to get moderators for"}},
                required=["guild_id"],
            ),
        }

        tool_descriptions = {
            "discord_send_message": "Send a text message to a Discord channel",
            "discord_send_embed": "Send an embedded message to a Discord channel",
            "discord_delete_message": "Delete a message from a Discord channel",
            "discord_timeout_user": "Timeout (mute) a user in a Discord guild",
            "discord_ban_user": "Ban a user from a Discord guild",
            "discord_kick_user": "Kick a user from a Discord guild",
            "discord_add_role": "Add a role to a user in a Discord guild",
            "discord_remove_role": "Remove a role from a user in a Discord guild",
            "discord_get_user_info": "Get information about a Discord user",
            "discord_get_channel_info": "Get information about a Discord channel",
            "discord_get_guild_moderators": "Get list of guild members with moderator permissions, excluding ECHO users",
        }

        if tool_name not in tool_schemas:
            return None

        return ToolInfo(
            name=tool_name,
            description=tool_descriptions.get(tool_name, ""),
            parameters=tool_schemas[tool_name],
            category="discord",
        )

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get detailed information about all available Discord tools."""
        infos = []
        for tool_name in self._tools:
            info = await self.get_tool_info(tool_name)
            if info:
                infos.append(info)
        return infos

    async def is_healthy(self) -> bool:
        """Check if the Discord tool service is healthy."""
        return self._client is not None and not self._client.is_closed()

    def get_service_type(self) -> ServiceType:
        """Get the type of this service."""
        return ServiceType.TOOL

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="DiscordToolService",
            actions=[
                "execute_tool",
                "get_available_tools",
                "get_tool_result",
                "validate_parameters",
                "get_tool_info",
                "get_all_tool_info",
            ],
            version="1.0.0",
            dependencies=[],
            metadata=None,
        )

    def get_status(self) -> Any:
        """Get service status."""
        from datetime import datetime, timezone

        from ciris_engine.schemas.services.core import ServiceStatus

        return ServiceStatus(
            service_name="DiscordToolService",
            service_type="TOOL",
            is_healthy=self._client is not None and not self._client.is_closed(),
            uptime_seconds=0.0,  # Would need to track start time
            last_error=None,
            metrics={
                "tools_available": len(self._tools),
                "client_connected": (
                    self._client is not None and not self._client.is_closed() if self._client else False
                ),
            },
            last_health_check=datetime.now(timezone.utc) if self._time_service is None else self._time_service.now(),
        )

    async def list_tools(self) -> List[str]:
        """List available tools - required by ToolServiceProtocol."""
        return list(self._tools.keys())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a specific tool - required by ToolServiceProtocol."""
        tool_info = await self.get_tool_info(tool_name)
        if tool_info:
            return tool_info.parameters
        return None
