"""Discord guidance handling component for wise authority operations."""

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import discord
from discord import ui

from ciris_engine.logic.utils.jsondict_helpers import get_list, get_str
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.protocols.services.graph.memory import MemoryServiceProtocol
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class DiscordGuidanceHandler:
    """Handles Discord wise authority guidance and deferral operations."""

    def __init__(
        self,
        client: Optional[discord.Client] = None,
        time_service: Optional["TimeServiceProtocol"] = None,
        memory_service: Optional["MemoryServiceProtocol"] = None,
    ) -> None:
        """Initialize the guidance handler.

        Args:
            client: Discord client instance
            time_service: Time service for consistent time operations
            memory_service: Memory service for WA lookups
        """
        self.client = client
        self._memory_service = memory_service
        self._wa_cache: Dict[str, bool] = {}  # Cache WA status
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

    def set_memory_service(self, memory_service: "MemoryServiceProtocol") -> None:
        """Set the memory service after initialization.

        Args:
            memory_service: Memory service instance
        """
        self._memory_service = memory_service

    async def _is_registered_wa(self, discord_id: str) -> bool:
        """Check if a Discord user is a registered WA.

        Args:
            discord_id: Discord user ID

        Returns:
            True if user is a registered WA
        """
        # Check cache first
        if discord_id in self._wa_cache:
            return self._wa_cache[discord_id]

        # For bot's own ID, always return True
        if self.client and self.client.user and str(self.client.user.id) == discord_id:
            self._wa_cache[discord_id] = True
            return True

        # If no memory service, check Discord roles
        if not self._memory_service:
            return self._check_discord_roles(discord_id)

        try:
            # Query memory for Discord WA node
            query = f"node_type:DISCORD_WA discord_id:{discord_id}"

            nodes = await self._memory_service.search(query)
            is_wa = len(nodes) > 0

            # Cache result
            self._wa_cache[discord_id] = is_wa
            return is_wa

        except Exception as e:
            logger.error(f"Failed to check WA status for {discord_id}: {e}")
            # Fall back to Discord role check
            return self._check_discord_roles(discord_id)

    def _check_discord_roles(self, discord_id: str) -> bool:
        """Check if user has AUTHORITY or OBSERVER role in Discord.

        Args:
            discord_id: Discord user ID

        Returns:
            True if user has appropriate role
        """
        if not self.client:
            return False

        try:
            # Check all guilds
            for guild in self.client.guilds:
                member = guild.get_member(int(discord_id))
                if member:
                    role_names = [role.name.upper() for role in member.roles]
                    if "AUTHORITY" in role_names or "OBSERVER" in role_names:
                        return True
            return False
        except Exception as e:
            logger.error(f"Failed to check Discord roles for {discord_id}: {e}")
            return False

    async def fetch_guidance_from_channel(self, deferral_channel_id: str, context: JSONDict) -> JSONDict:
        """Send a guidance request to a Discord channel and check for responses.

        Args:
            deferral_channel_id: The Discord channel ID for guidance requests
            context: Context information for the guidance request

        Returns:
            Dictionary containing guidance information or None if no guidance found

        Raises:
            RuntimeError: If client is not initialized or channel not found
        """
        if not self.client:
            raise RuntimeError("Discord client is not initialized")

        channel = await self._resolve_channel(deferral_channel_id)
        if not channel:
            raise RuntimeError(f"Deferral channel {deferral_channel_id} not found")

        request_content = f"[CIRIS Guidance Request]\nContext: ```json\n{context}\n```"

        if not hasattr(channel, "send"):
            logger.error(f"Channel {deferral_channel_id} does not support sending messages")
            return {"guidance": None}

        chunks = self._split_message(request_content)
        request_message = None

        for i, chunk in enumerate(chunks):
            if len(chunks) > 1 and i > 0:
                chunk = f"*(Continued from previous message)*\n\n{chunk}"
            sent_msg = await channel.send(chunk)
            if i == 0:
                request_message = sent_msg  # Track first message for replies

        if hasattr(channel, "history"):
            async for message in channel.history(limit=10):
                if message.author.bot or (request_message and message.id == request_message.id):
                    continue

                # Check if author is a registered WA
                if not await self._is_registered_wa(str(message.author.id)):
                    logger.debug(f"Skipping guidance from non-WA user {message.author.name}")
                    continue

                guidance_content = message.content.strip()

                is_reply = bool(
                    hasattr(message, "reference")
                    and message.reference
                    and request_message
                    and hasattr(message.reference, "message_id")
                    and message.reference.message_id == request_message.id
                )

                return {
                    "guidance": guidance_content,
                    "is_reply": is_reply,
                    "is_unsolicited": not is_reply,
                    "author_id": str(message.author.id),
                    "author_name": message.author.display_name,
                }

        logger.warning("No guidance found in deferral channel")
        return {"guidance": None}

    async def send_deferral_to_channel(
        self, deferral_channel_id: str, thought_id: str, reason: str, context: Optional[JSONDict] = None
    ) -> None:
        """Send a deferral report to a Discord channel with helper buttons.

        Args:
            deferral_channel_id: The Discord channel ID for deferral reports
            thought_id: The ID of the thought being deferred
            reason: Reason for deferral
            context: Additional context about the thought and task

        Raises:
            RuntimeError: If client is not initialized or channel not found
        """
        if not self.client:
            raise RuntimeError("Discord client is not initialized")

        channel = await self._resolve_channel(deferral_channel_id)
        if not channel:
            raise RuntimeError(f"Deferral channel {deferral_channel_id} not found")

        # Create embed for better formatting
        embed = discord.Embed(
            title="CIRIS Deferral Report",
            description=f"**Reason:** {reason}",
            color=discord.Color.orange(),
            timestamp=self._time_service.now(),
        )

        embed.add_field(name="Thought ID", value=f"`{thought_id}`", inline=True)

        if context:
            if "task_id" in context:
                embed.add_field(name="Task ID", value=f"`{context['task_id']}`", inline=True)

            if "priority" in context:
                embed.add_field(name="Priority", value=context["priority"], inline=True)

            if "task_description" in context:
                task_desc = self._truncate_text(get_str(context, "task_description", ""), 1024)
                embed.add_field(name="Task Description", value=task_desc, inline=False)

            if "thought_content" in context:
                thought_content = self._truncate_text(get_str(context, "thought_content", ""), 1024)
                embed.add_field(name="Thought Content", value=thought_content, inline=False)

            if "attempted_action" in context:
                embed.add_field(name="Attempted Action", value=context["attempted_action"], inline=True)

            if "max_rounds_reached" in context and context["max_rounds_reached"]:
                embed.add_field(name="Note", value="Maximum processing rounds reached", inline=False)

        # Create view with helper buttons
        view = DeferralHelperView(thought_id, context)

        # Send embed with view
        await channel.send(embed=embed, view=view)

    def _build_deferral_report(self, thought_id: str, reason: str, context: Optional[JSONDict] = None) -> str:
        """Build a formatted deferral report.

        Args:
            thought_id: The ID of the thought being deferred
            reason: Reason for deferral
            context: Additional context information

        Returns:
            Formatted deferral report as a string
        """
        report_lines = [
            "**[CIRIS Deferral Report]**",
            f"**Thought ID:** `{thought_id}`",
            f"**Reason:** {reason}",
            f"**Timestamp:** {self._time_service.now_iso()}",
        ]

        if context:
            if "task_id" in context:
                report_lines.append(f"**Task ID:** `{context['task_id']}`")

            if "task_description" in context:
                task_desc = self._truncate_text(get_str(context, "task_description", ""), 200)
                report_lines.append(f"**Task:** {task_desc}")

            if "thought_content" in context:
                thought_content = self._truncate_text(get_str(context, "thought_content", ""), 300)
                report_lines.append(f"**Thought:** {thought_content}")

            if "conversation_context" in context:
                conv_context = self._truncate_text(get_str(context, "conversation_context", ""), 400)
                report_lines.append(f"**Context:** {conv_context}")

            if "priority" in context:
                report_lines.append(f"**Priority:** {context['priority']}")

            if "attempted_action" in context:
                report_lines.append(f"**Attempted Action:** {context['attempted_action']}")

            if "max_rounds_reached" in context and context["max_rounds_reached"]:
                report_lines.append("**Note:** Maximum processing rounds reached")

        return "\n".join(report_lines)

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to a maximum length with ellipsis.

        Args:
            text: Text to truncate
            max_length: Maximum length allowed

        Returns:
            Truncated text with ellipsis if needed
        """
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."

    def _split_message(self, content: str, max_length: int = 1950) -> List[str]:
        """Split a message into chunks that fit Discord's character limit.

        Args:
            content: The message content to split
            max_length: Maximum length per message

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

        Returns:
            Discord channel object or None if not found
        """
        if not self.client:
            return None

        try:
            channel_id_int = int(channel_id)
            channel = self.client.get_channel(channel_id_int)
            if channel is None:
                channel = await self.client.fetch_channel(channel_id_int)
            return channel
        except (ValueError, discord.NotFound, discord.Forbidden):
            logger.error(f"Could not resolve Discord channel {channel_id}")
            return None


class DeferralHelperView(ui.View):
    """Simple Discord UI View with helper buttons for deferral responses."""

    def __init__(self, thought_id: str, context: Optional[JSONDict] = None):
        super().__init__(timeout=3600)  # 1 hour timeout
        self.thought_id = thought_id
        self.context = context or {}

    @ui.button(label="Approve", style=discord.ButtonStyle.success, emoji="✅")
    async def approve_button(self, interaction: discord.Interaction, button: ui.Button[Any]) -> None:
        """Provide template response for approval."""
        await interaction.response.send_message(
            f"To approve this deferral, reply with:\n```\nAPPROVE {self.thought_id}\n```", ephemeral=True
        )

    @ui.button(label="Reject", style=discord.ButtonStyle.danger, emoji="❌")
    async def reject_button(self, interaction: discord.Interaction, button: ui.Button[Any]) -> None:
        """Provide template response for rejection."""
        await interaction.response.send_message(
            f"To reject this deferral, reply with:\n```\nREJECT {self.thought_id}\n```", ephemeral=True
        )

    @ui.button(label="Request Info", style=discord.ButtonStyle.secondary, emoji="❓")
    async def info_button(self, interaction: discord.Interaction, button: ui.Button[Any]) -> None:
        """Provide detailed context about the deferred task/thought."""
        # Build detailed info message
        info_lines = ["**Detailed Task/Thought Information**\n"]

        # Add thought ID
        info_lines.append(f"**Thought ID:** `{self.thought_id}`")

        # Add task information if available
        if "task_id" in self.context:
            info_lines.append(f"**Task ID:** `{self.context['task_id']}`")

        if "task_description" in self.context:
            task_desc = self._truncate_text(get_str(self.context, "task_description", ""), 500)
            info_lines.append(f"\n**Task Description:**\n{task_desc}")

        # Add thought history if available
        if "thought_history" in self.context:
            info_lines.append("\n**Recent Thought History:**")
            thought_history = get_list(self.context, "thought_history", [])
            for i, thought in enumerate(thought_history[-5:], 1):  # Last 5 thoughts
                if isinstance(thought, dict):
                    thought_summary = self._truncate_text(thought.get("content", "No content"), 200)
                    info_lines.append(f"{i}. {thought_summary}")

        # Add ponder notes if available
        if "ponder_notes" in self.context:
            ponder_notes = get_list(self.context, "ponder_notes", [])
            if ponder_notes:
                info_lines.append("\n**Ponder Notes (Questions/Ambiguities):**")
                for i, note in enumerate(ponder_notes, 1):
                    if isinstance(note, str):
                        info_lines.append(f"{i}. {note}")

        # Add processing rounds info
        if "current_round" in self.context:
            info_lines.append(
                f"\n**Processing Round:** {self.context['current_round']}/{self.context.get('max_rounds', 5)}"
            )

        # Add attempted actions if available
        if "attempted_actions" in self.context:
            attempted_actions = get_list(self.context, "attempted_actions", [])
            if attempted_actions:
                info_lines.append("\n**Attempted Actions:**")
                for action in attempted_actions:
                    if isinstance(action, str):
                        info_lines.append(f"- {action}")

        # Add template for requesting more info
        info_lines.append(
            f"\n**To request specific information:**\n```\nINFO {self.thought_id} - [your question here]\n```"
        )

        # Join all lines and ensure it fits Discord's limit
        full_message = "\n".join(info_lines)
        if len(full_message) > 2000:
            # Truncate to fit Discord's message limit
            full_message = full_message[:1997] + "..."

        await interaction.response.send_message(full_message, ephemeral=True)

    def _truncate_text(self, text: str, max_length: int) -> str:
        """Truncate text to a maximum length with ellipsis."""
        if len(text) <= max_length:
            return text
        return text[: max_length - 3] + "..."
