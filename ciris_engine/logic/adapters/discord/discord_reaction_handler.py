"""Discord reaction handling component for approval workflows."""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Awaitable, Callable, Dict, Optional

import discord

if TYPE_CHECKING:
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class ApprovalStatus(Enum):
    """Status of an approval request."""

    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"
    TIMEOUT = "timeout"


class ApprovalRequest:
    """Represents a pending approval request."""

    def __init__(
        self, message_id: int, channel_id: int, request_type: str, context: Dict[str, str], timeout_seconds: int = 300
    ):
        self.message_id = message_id
        self.channel_id = channel_id
        self.request_type = request_type
        self.context = context
        self.timeout_seconds = timeout_seconds
        self.status = ApprovalStatus.PENDING
        self.created_at = datetime.now()
        self.resolved_at: Optional[datetime] = None
        self.resolver_id: Optional[str] = None
        self.resolver_name: Optional[str] = None


class DiscordReactionHandler:
    """Handles Discord reactions for approval workflows."""

    APPROVE_EMOJI = "✅"
    DENY_EMOJI = "❌"

    def __init__(
        self, client: Optional[discord.Client] = None, time_service: Optional["TimeServiceProtocol"] = None
    ) -> None:
        """Initialize the reaction handler.

        Args:
            client: Discord client instance
            time_service: Time service for consistent time operations
        """
        self.client = client
        self._pending_approvals: Dict[int, ApprovalRequest] = {}
        self._approval_callbacks: Dict[int, Callable[[ApprovalRequest], Awaitable[None]]] = {}
        self._timeout_task: Optional[asyncio.Task[None]] = None
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

    async def request_approval(
        self,
        channel_id: int,
        message: str,
        request_type: str,
        context: Dict[str, str],
        timeout_seconds: int = 300,
        callback: Optional[Callable[[ApprovalRequest], Awaitable[None]]] = None,
    ) -> Optional[ApprovalRequest]:
        """Send an approval request message and wait for reactions.

        Args:
            channel_id: Discord channel ID
            message: Message content to send
            request_type: Type of approval request
            context: Additional context for the request
            timeout_seconds: Timeout in seconds
            callback: Optional callback when approval is resolved

        Returns:
            ApprovalRequest object or None if failed
        """
        if not self.client:
            logger.error("Discord client not initialized")
            return None

        try:
            # Get channel
            channel = self.client.get_channel(channel_id)
            if not channel:
                channel = await self.client.fetch_channel(channel_id)

            # Check if channel supports sending messages
            if not isinstance(
                channel,
                (discord.TextChannel, discord.DMChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel),
            ):
                logger.error(f"Channel {channel_id} does not support sending messages")
                return None

            # Send message
            sent_message = await channel.send(message)

            # Add reactions
            await sent_message.add_reaction(self.APPROVE_EMOJI)
            await sent_message.add_reaction(self.DENY_EMOJI)

            # Create approval request
            approval = ApprovalRequest(
                message_id=sent_message.id,
                channel_id=channel_id,
                request_type=request_type,
                context=context,
                timeout_seconds=timeout_seconds,
            )

            # Store in pending
            self._pending_approvals[sent_message.id] = approval
            if callback:
                self._approval_callbacks[sent_message.id] = callback

            # Schedule timeout
            self._timeout_task = asyncio.create_task(self._handle_timeout(approval))

            return approval

        except Exception as e:
            logger.exception(f"Failed to create approval request: {e}")
            return None

    async def handle_reaction(self, payload: discord.RawReactionActionEvent) -> None:
        """Handle a reaction event.

        Args:
            payload: Discord reaction event payload
        """
        # Check if this is a reaction we care about
        if payload.message_id not in self._pending_approvals:
            return

        # Check if it's an approval/denial emoji
        if str(payload.emoji) not in [self.APPROVE_EMOJI, self.DENY_EMOJI]:
            return

        # Get the approval request
        approval = self._pending_approvals[payload.message_id]

        # Check if already resolved
        if approval.status != ApprovalStatus.PENDING:
            return

        # Resolve the approval
        if str(payload.emoji) == self.APPROVE_EMOJI:
            approval.status = ApprovalStatus.APPROVED
        else:
            approval.status = ApprovalStatus.DENIED

        approval.resolved_at = self._time_service.now()
        approval.resolver_id = str(payload.user_id)

        # Get resolver name if possible
        if self.client:
            try:
                user = self.client.get_user(payload.user_id)
                if not user:
                    user = await self.client.fetch_user(payload.user_id)
                approval.resolver_name = user.name
            except Exception as e:
                logger.warning(
                    f"Failed to fetch Discord user {payload.user_id} for approval resolution: {e}. Resolver name will be omitted."
                )

        # Remove from pending
        del self._pending_approvals[payload.message_id]

        # Call callback if registered
        if payload.message_id in self._approval_callbacks:
            callback = self._approval_callbacks.pop(payload.message_id)
            await callback(approval)

        # Update message to show resolution
        await self._update_approval_message(approval)

    async def _handle_timeout(self, approval: ApprovalRequest) -> None:
        """Handle timeout for an approval request.

        Args:
            approval: The approval request
        """
        await asyncio.sleep(approval.timeout_seconds)

        # Check if still pending
        if approval.message_id in self._pending_approvals:
            approval.status = ApprovalStatus.TIMEOUT
            approval.resolved_at = self._time_service.now()

            # Remove from pending
            del self._pending_approvals[approval.message_id]

            # Call callback if registered
            if approval.message_id in self._approval_callbacks:
                callback = self._approval_callbacks.pop(approval.message_id)
                await callback(approval)

            # Update message
            await self._update_approval_message(approval)

    async def _update_approval_message(self, approval: ApprovalRequest) -> None:
        """Update the approval message to show resolution.

        Args:
            approval: The resolved approval request
        """
        if not self.client:
            return

        try:
            # Get channel and message
            channel = self.client.get_channel(approval.channel_id)
            if not channel:
                channel = await self.client.fetch_channel(approval.channel_id)

            # Check if channel supports fetching messages
            if not isinstance(
                channel,
                (discord.TextChannel, discord.DMChannel, discord.Thread, discord.VoiceChannel, discord.StageChannel),
            ):
                logger.error(f"Channel {approval.channel_id} does not support fetching messages")
                return

            message = await channel.fetch_message(approval.message_id)

            # Build status line
            status_line = f"\n\n**RESOLVED**: {approval.status.value.upper()}"
            if approval.resolver_name:
                status_line += f" by {approval.resolver_name}"
            if approval.resolved_at:
                status_line += f" at {approval.resolved_at.isoformat()}"

            # Update message
            new_content = message.content + status_line
            await message.edit(content=new_content)

        except Exception as e:
            logger.error(f"Failed to update approval message: {e}")

    def get_pending_approvals(self) -> Dict[int, ApprovalRequest]:
        """Get all pending approval requests.

        Returns:
            Dictionary of message ID to ApprovalRequest
        """
        return self._pending_approvals.copy()

    def clear_pending_approvals(self) -> None:
        """Clear all pending approvals (for cleanup)."""
        self._pending_approvals.clear()
        self._approval_callbacks.clear()
