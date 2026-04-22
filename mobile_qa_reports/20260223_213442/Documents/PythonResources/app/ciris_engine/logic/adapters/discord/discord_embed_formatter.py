"""Discord embed formatting component for rich message presentation."""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

import discord

from ciris_engine.schemas.adapters.discord import (
    DiscordApprovalData,
    DiscordAuditData,
    DiscordErrorInfo,
    DiscordGuidanceData,
    DiscordTaskData,
    DiscordToolResult,
)

from .constants import (
    DEFAULT_PAGE_SIZE,
    EMBED_HOW_TO_RESPOND,
    EMBED_RESPOND_INSTRUCTIONS,
    FIELD_NAME_ACTION_TYPE,
    FIELD_NAME_ACTOR,
    FIELD_NAME_CONTEXT,
    FIELD_NAME_CREATED,
    FIELD_NAME_DEFER_UNTIL,
    FIELD_NAME_DEFERRAL_ID,
    FIELD_NAME_ERROR,
    FIELD_NAME_EXECUTION_TIME,
    FIELD_NAME_OPERATION,
    FIELD_NAME_OUTPUT,
    FIELD_NAME_PARAMETERS,
    FIELD_NAME_PRIORITY,
    FIELD_NAME_PROGRESS,
    FIELD_NAME_REQUESTER,
    FIELD_NAME_RESULT,
    FIELD_NAME_RETRYABLE,
    FIELD_NAME_SERVICE,
    FIELD_NAME_SEVERITY,
    FIELD_NAME_SUBTASKS,
    FIELD_NAME_SUGGESTED_FIX,
    FIELD_NAME_TASK_ID,
    FIELD_NAME_THOUGHT_ID,
    FIELD_NAME_TIME,
    STATUS_EMOJI_COMPLETED,
    STATUS_EMOJI_DEFERRED,
    STATUS_EMOJI_FAILED,
    STATUS_EMOJI_IN_PROGRESS,
    STATUS_EMOJI_PENDING,
    STATUS_EMOJI_UNKNOWN,
    STATUS_MESSAGE_COMPLETED,
    STATUS_MESSAGE_EXECUTING,
    STATUS_MESSAGE_FAILED,
    STATUS_MESSAGE_FAILED_WITH_ICON,
    STATUS_MESSAGE_SUCCESS,
)


class EmbedType(Enum):
    """Types of embeds for different purposes."""

    INFO = ("ℹ️", 0x3498DB)  # Blue
    SUCCESS = ("✅", 0x2ECC71)  # Green
    WARNING = ("⚠️", 0xF39C12)  # Orange
    ERROR = ("❌", 0xE74C3C)  # Red
    GUIDANCE = ("🤔", 0x9B59B6)  # Purple
    DEFERRAL = ("⏳", 0x95A5A6)  # Gray
    APPROVAL = ("🔒", 0xE67E22)  # Dark orange
    TOOL = ("🔧", 0x1ABC9C)  # Turquoise
    AUDIT = ("📋", 0x34495E)  # Dark gray
    TASK = ("📝", 0x3498DB)  # Blue


class DiscordEmbedFormatter:
    """Formats messages as rich Discord embeds."""

    @staticmethod
    def create_base_embed(embed_type: EmbedType, title: str, description: Optional[str] = None) -> discord.Embed:
        """Create a base embed with consistent styling.

        Args:
            embed_type: Type of embed
            title: Embed title
            description: Optional description

        Returns:
            Discord embed object
        """
        icon, color = embed_type.value

        embed = discord.Embed(
            title=f"{icon} {title}", description=description, color=color, timestamp=datetime.now(timezone.utc)
        )

        return embed

    @classmethod
    def format_guidance_request(cls, context: DiscordGuidanceData) -> discord.Embed:
        """Format a guidance request as an embed.

        Args:
            context: Guidance context data

        Returns:
            Formatted embed
        """
        embed = cls.create_base_embed(EmbedType.GUIDANCE, "Guidance Request", context.reason)

        # Add context fields
        embed.add_field(name=FIELD_NAME_THOUGHT_ID, value=f"`{context.thought_id}`", inline=True)
        embed.add_field(name=FIELD_NAME_TASK_ID, value=f"`{context.task_id}`", inline=True)

        if context.defer_until:
            embed.add_field(
                name=FIELD_NAME_DEFER_UNTIL, value=f"<t:{int(context.defer_until.timestamp())}:R>", inline=True
            )

        if context.context:
            context_str = "\n".join(f"**{k}**: {v}" for k, v in list(context.context.items())[:5])
            embed.add_field(name=FIELD_NAME_CONTEXT, value=context_str[:1024], inline=False)

        embed.set_footer(text="Please provide your guidance")
        return embed

    @classmethod
    def format_deferral_request(cls, deferral: DiscordGuidanceData) -> discord.Embed:
        """Format a deferral request as an embed.

        Args:
            deferral: Deferral information

        Returns:
            Formatted embed
        """
        embed = cls.create_base_embed(EmbedType.DEFERRAL, "Decision Deferred", deferral.reason)

        # Add deferral details
        embed.add_field(name=FIELD_NAME_DEFERRAL_ID, value=f"`{deferral.deferral_id}`", inline=True)
        embed.add_field(name=FIELD_NAME_TASK_ID, value=f"`{deferral.task_id}`", inline=True)
        embed.add_field(name=FIELD_NAME_THOUGHT_ID, value=f"`{deferral.thought_id}`", inline=True)

        if deferral.defer_until:
            embed.add_field(
                name=FIELD_NAME_DEFER_UNTIL, value=f"<t:{int(deferral.defer_until.timestamp())}:R>", inline=True
            )

        if deferral.context:
            context_str = "\n".join(f"**{k}**: {v}" for k, v in list(deferral.context.items())[:5])
            embed.add_field(name=FIELD_NAME_CONTEXT, value=context_str[:1024], inline=False)

        return embed

    @classmethod
    def format_approval_request(cls, action: str, context: DiscordApprovalData) -> discord.Embed:
        """Format an approval request as an embed.

        Args:
            action: Action requiring approval
            context: Approval context

        Returns:
            Formatted embed
        """
        embed = cls.create_base_embed(EmbedType.APPROVAL, "Approval Required", f"Action: **{action}**")

        # Add context
        embed.add_field(name=FIELD_NAME_REQUESTER, value=context.requester_id, inline=True)

        if context.task_id:
            embed.add_field(name=FIELD_NAME_TASK_ID.replace(" ID", ""), value=f"`{context.task_id}`", inline=True)

        if context.thought_id:
            embed.add_field(name=FIELD_NAME_THOUGHT_ID.replace(" ID", ""), value=f"`{context.thought_id}`", inline=True)

        if context.action_name:
            embed.add_field(name=FIELD_NAME_ACTION_TYPE, value=context.action_name, inline=True)

        if context.action_params:
            params_str = "\n".join(f"• **{k}**: {v}" for k, v in list(context.action_params.items())[:5])
            embed.add_field(name=FIELD_NAME_PARAMETERS, value=params_str[:1024], inline=False)

        embed.add_field(name=EMBED_HOW_TO_RESPOND, value=EMBED_RESPOND_INSTRUCTIONS, inline=False)

        return embed

    @classmethod
    def format_tool_execution(
        cls, tool_name: str, parameters: dict[str, str], result: Optional[DiscordToolResult] = None
    ) -> discord.Embed:
        """Format tool execution information as an embed.

        Args:
            tool_name: Name of the tool
            parameters: Tool parameters
            result: Execution result (if available)

        Returns:
            Formatted embed
        """
        if result is None:
            embed_type = EmbedType.TOOL
            status = STATUS_MESSAGE_EXECUTING
        elif result.success:
            embed_type = EmbedType.SUCCESS
            status = STATUS_MESSAGE_COMPLETED
        else:
            embed_type = EmbedType.ERROR
            status = STATUS_MESSAGE_FAILED

        embed = cls.create_base_embed(embed_type, f"Tool: {tool_name}", status)

        # Add parameters
        if parameters:
            params_str = "\n".join(f"• **{k}**: `{v}`" for k, v in list(parameters.items())[:5])
            embed.add_field(name=FIELD_NAME_PARAMETERS, value=params_str[:1024], inline=False)

        # Add result if available
        if result:
            if result.output:
                output = str(result.output)[:1024]
                embed.add_field(name=FIELD_NAME_OUTPUT, value=f"```\n{output}\n```", inline=False)

            if result.error:
                embed.add_field(name=FIELD_NAME_ERROR, value=result.error[:1024], inline=False)

            if result.execution_time:
                embed.add_field(name=FIELD_NAME_EXECUTION_TIME, value=f"{result.execution_time:.2f}ms", inline=True)

        return embed

    @classmethod
    def format_task_status(cls, task: DiscordTaskData) -> discord.Embed:
        """Format task status as an embed.

        Args:
            task: Task information

        Returns:
            Formatted embed
        """
        status_emoji = {
            "pending": STATUS_EMOJI_PENDING,
            "in_progress": STATUS_EMOJI_IN_PROGRESS,
            "completed": STATUS_EMOJI_COMPLETED,
            "failed": STATUS_EMOJI_FAILED,
            "deferred": STATUS_EMOJI_DEFERRED,
        }.get(task.status, STATUS_EMOJI_UNKNOWN)

        embed = cls.create_base_embed(
            EmbedType.TASK,
            f"Task Status: {status_emoji} {task.status.replace('_', ' ').title()}",
            task.description or "Task in progress",
        )

        # Add task details
        embed.add_field(name=FIELD_NAME_TASK_ID, value=f"`{task.id}`", inline=True)
        embed.add_field(name=FIELD_NAME_PRIORITY, value=task.priority.upper(), inline=True)

        if task.progress is not None:
            embed.add_field(name=FIELD_NAME_PROGRESS, value=f"{task.progress}%", inline=True)

        if task.created_at:
            embed.add_field(name=FIELD_NAME_CREATED, value=f"<t:{int(task.created_at.timestamp())}:R>", inline=True)

        if task.subtasks:
            subtask_str = "\n".join(
                f"{'✅' if st.get('completed') else '⬜'} {st.get('name', 'Subtask')}" for st in task.subtasks[:5]
            )
            embed.add_field(name=FIELD_NAME_SUBTASKS, value=subtask_str, inline=False)

        return embed

    @classmethod
    def format_audit_entry(cls, audit: DiscordAuditData) -> discord.Embed:
        """Format an audit log entry as an embed.

        Args:
            audit: Audit information

        Returns:
            Formatted embed
        """
        embed = cls.create_base_embed(EmbedType.AUDIT, "Audit Log Entry", audit.action)

        # Add audit details
        embed.add_field(name=FIELD_NAME_ACTOR, value=audit.actor, inline=True)
        embed.add_field(name=FIELD_NAME_SERVICE, value=audit.service, inline=True)

        if audit.timestamp:
            embed.add_field(name=FIELD_NAME_TIME, value=f"<t:{int(audit.timestamp.timestamp())}:F>", inline=True)

        if audit.context:
            context_str = "\n".join(f"• **{k}**: {v}" for k, v in list(audit.context.items())[:5])
            embed.add_field(name=FIELD_NAME_CONTEXT, value=context_str[:1024], inline=False)

        if audit.success is not None:
            embed.add_field(
                name=FIELD_NAME_RESULT,
                value=STATUS_MESSAGE_SUCCESS if audit.success else STATUS_MESSAGE_FAILED_WITH_ICON,
                inline=True,
            )

        return embed

    @classmethod
    def format_error_message(cls, error_info: DiscordErrorInfo) -> discord.Embed:
        """Format an error message as an embed.

        Args:
            error_info: Error information

        Returns:
            Formatted embed
        """
        embed_type = {
            "low": EmbedType.INFO,
            "medium": EmbedType.WARNING,
            "high": EmbedType.ERROR,
            "critical": EmbedType.ERROR,
        }.get(error_info.severity.value, EmbedType.ERROR)

        embed = cls.create_base_embed(embed_type, f"Error: {error_info.error_type}", error_info.message)

        # Add error details
        if error_info.operation:
            embed.add_field(name=FIELD_NAME_OPERATION, value=error_info.operation, inline=True)

        embed.add_field(name=FIELD_NAME_SEVERITY, value=error_info.severity.value.upper(), inline=True)
        embed.add_field(name=FIELD_NAME_RETRYABLE, value="Yes" if error_info.can_retry else "No", inline=True)

        if error_info.suggested_fix:
            embed.add_field(name=FIELD_NAME_SUGGESTED_FIX, value=error_info.suggested_fix, inline=False)

        return embed

    @classmethod
    def create_paginated_embed(
        cls,
        title: str,
        items: List[str],
        page: int = 1,
        per_page: int = DEFAULT_PAGE_SIZE,
        embed_type: EmbedType = EmbedType.INFO,
    ) -> discord.Embed:
        """Create a paginated embed for lists.

        Args:
            title: Embed title
            items: List of items to display
            page: Current page (1-indexed)
            per_page: Items per page
            embed_type: Type of embed

        Returns:
            Paginated embed
        """
        total_pages = (len(items) + per_page - 1) // per_page
        page = max(1, min(page, total_pages))

        start_idx = (page - 1) * per_page
        end_idx = min(start_idx + per_page, len(items))

        page_items = items[start_idx:end_idx]

        embed = cls.create_base_embed(embed_type, title, "\n".join(page_items))

        embed.set_footer(text=f"Page {page}/{total_pages} • Total items: {len(items)}")

        return embed
