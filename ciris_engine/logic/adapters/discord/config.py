"""Configuration schema for Discord adapter."""

from typing import TYPE_CHECKING, Any, Callable, List, Optional

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


class DiscordAdapterConfig(BaseModel):
    """Configuration for the Discord adapter."""

    bot_token: Optional[str] = Field(default=None, description="Discord bot token")

    monitored_channel_ids: List[str] = Field(
        default_factory=list, description="List of Discord channel IDs to monitor for incoming messages"
    )
    home_channel_id: Optional[str] = Field(
        default=None, description="Home channel ID for wakeup and primary agent communication"
    )
    deferral_channel_id: Optional[str] = Field(
        default=None, description="Channel ID for Discord deferrals and guidance from WA"
    )

    respond_to_mentions: bool = Field(default=True, description="Respond when the bot is mentioned")
    respond_to_dms: bool = Field(default=True, description="Respond to direct messages")

    max_message_length: int = Field(default=2000, description="Maximum Discord message length")
    enable_threads: bool = Field(default=True, description="Enable thread creation for long conversations")
    delete_commands: bool = Field(default=False, description="Delete user commands after processing")

    message_rate_limit: float = Field(default=1.0, description="Minimum seconds between messages")
    max_messages_per_minute: int = Field(default=30, description="Maximum messages per minute")

    allowed_user_ids: List[str] = Field(
        default_factory=list, description="List of allowed user IDs (empty = all users)"
    )
    allowed_role_ids: List[str] = Field(default_factory=list, description="List of allowed role IDs")
    admin_user_ids: List[str] = Field(
        default_factory=list, description="List of admin user IDs with elevated permissions"
    )

    status: str = Field(default="online", description="Bot status: online, idle, dnd, invisible")
    activity_type: str = Field(default="watching", description="Activity type: playing, watching, listening, streaming")
    activity_name: str = Field(default="for ethical dilemmas", description="Activity description")

    enable_message_content: bool = Field(default=True, description="Enable message content intent")
    enable_guild_messages: bool = Field(default=True, description="Enable guild messages intent")
    enable_dm_messages: bool = Field(default=True, description="Enable DM messages intent")

    def get_intents(self) -> Any:
        """Get Discord intents based on configuration."""
        import discord

        intents = discord.Intents.default()
        intents.message_content = self.enable_message_content
        intents.guild_messages = self.enable_guild_messages
        intents.dm_messages = self.enable_dm_messages

        # Additional intents needed for full functionality
        intents.reactions = True  # For reaction handling (approvals/deferrals)
        intents.members = True  # For member info and user profiles
        intents.guilds = True  # For guild info

        # Note: When inviting the bot to a server, ensure these permissions are granted:
        # - Send Messages
        # - Embed Links (for rich embeds)
        # - Read Messages/View Channels
        # - Add Reactions
        # - Read Message History
        # - Manage Messages (optional, for deleting commands)
        #
        # Permission integer for bot invite: 412317240384
        # This includes: VIEW_CHANNEL, SEND_MESSAGES, EMBED_LINKS,
        #                ADD_REACTIONS, READ_MESSAGE_HISTORY, MANAGE_MESSAGES

        return intents

    def get_status(self) -> Any:
        """Get Discord status based on configuration."""
        import discord

        status_map = {
            "online": discord.Status.online,
            "idle": discord.Status.idle,
            "dnd": discord.Status.dnd,
            "invisible": discord.Status.invisible,
        }
        return status_map.get(self.status.lower(), discord.Status.online)

    def get_home_channel_id(self) -> Optional[str]:
        """Get the home channel ID for this Discord adapter."""
        if self.home_channel_id:
            return self.home_channel_id
        if self.monitored_channel_ids:
            return self.monitored_channel_ids[0]  # Default to first monitored channel if no explicit home channel
        return None

    def get_formatted_startup_channel_id(self, guild_id: Optional[str] = None) -> Optional[str]:
        """Get the formatted startup channel ID with discord_ prefix.

        Args:
            guild_id: Optional guild ID to include in format

        Returns:
            Formatted channel ID like 'discord_channelid' or 'discord_guildid_channelid'
        """
        home_channel = self.get_home_channel_id()
        if not home_channel:
            return None

        # If already formatted, return as-is
        if home_channel.startswith("discord_"):
            return home_channel

        # Format with guild ID if provided
        if guild_id:
            return f"discord_{guild_id}_{home_channel}"
        else:
            # Just add discord_ prefix for now
            return f"discord_{home_channel}"

    def load_env_vars(self) -> None:
        """Load configuration from environment variables if present."""
        from ciris_engine.logic.config.env_utils import get_env_var

        self._load_bot_token(get_env_var)
        self._load_channel_configuration(get_env_var)
        self._load_user_permissions(get_env_var)

    def _load_bot_token(self, get_env_var: Callable[[str], Optional[str]]) -> None:
        """Load bot token from environment variables."""
        env_token = get_env_var("DISCORD_BOT_TOKEN")
        if env_token:
            self.bot_token = env_token

    def _load_channel_configuration(self, get_env_var: Callable[[str], Optional[str]]) -> None:
        """Load channel configuration from environment variables."""
        # Home channel ID
        env_home_channel = get_env_var("DISCORD_HOME_CHANNEL_ID")
        if env_home_channel:
            self.home_channel_id = env_home_channel
            self._add_channel_to_monitored(env_home_channel)

        # Legacy support for DISCORD_CHANNEL_ID -> home channel
        env_legacy_channel = get_env_var("DISCORD_CHANNEL_ID")
        if env_legacy_channel and not self.home_channel_id:
            self.home_channel_id = env_legacy_channel
            self._add_channel_to_monitored(env_legacy_channel)

        # Multiple channels from comma-separated list
        env_channels = get_env_var("DISCORD_CHANNEL_IDS")
        if env_channels:
            channel_list = [ch.strip() for ch in env_channels.split(",") if ch.strip()]
            for channel_id in channel_list:
                self._add_channel_to_monitored(channel_id)

        # Deferral channel
        env_deferral = get_env_var("DISCORD_DEFERRAL_CHANNEL_ID")
        if env_deferral:
            self.deferral_channel_id = env_deferral

    def _load_user_permissions(self, get_env_var: Callable[[str], Optional[str]]) -> None:
        """Load user permissions from environment variables."""
        env_admin = get_env_var("WA_USER_IDS")
        if env_admin:
            # Parse comma-separated list of WA user IDs
            user_id_list = [uid.strip() for uid in env_admin.split(",") if uid.strip()]
            for user_id in user_id_list:
                if user_id not in self.admin_user_ids:
                    self.admin_user_ids.append(user_id)

    def _add_channel_to_monitored(self, channel_id: str) -> None:
        """Add channel to monitored list if not already present."""
        if channel_id not in self.monitored_channel_ids:
            self.monitored_channel_ids.append(channel_id)
