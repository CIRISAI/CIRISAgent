"""Discord error handling and recovery component."""

import logging
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Optional, Union

import discord
from discord.errors import ConnectionClosed, Forbidden, HTTPException, LoginFailure, NotFound, RateLimited

from ciris_engine.schemas.adapters.discord import DiscordErrorInfo
from ciris_engine.schemas.adapters.discord import ErrorSeverity as SchemaErrorSeverity

logger = logging.getLogger(__name__)


# Use ErrorSeverity from schema
ErrorSeverity = SchemaErrorSeverity


class DiscordErrorHandler:
    """Centralized error handling for Discord operations."""

    def __init__(self, on_critical_error: Optional[Callable[[str, Exception], Awaitable[None]]] = None):
        """Initialize error handler.

        Args:
            on_critical_error: Callback for critical errors
        """
        self.on_critical_error = on_critical_error
        self._error_counts: dict[str, int] = {}
        self._last_errors: dict[str, datetime] = {}
        self._error_threshold = 5  # Errors before escalation
        self._error_window = timedelta(minutes=5)  # Time window for error counting

    def handle_channel_error(self, channel_id: str, error: Exception, operation: str = "unknown") -> DiscordErrorInfo:
        """Handle channel-related errors.

        Args:
            channel_id: Discord channel ID
            error: The exception that occurred
            operation: What operation was being performed

        Returns:
            Error handling result with severity and suggested action
        """
        error_key = f"channel_{channel_id}_{type(error).__name__}"
        severity = ErrorSeverity.MEDIUM
        can_retry = True
        fallback_action = None

        if isinstance(error, NotFound):
            severity = ErrorSeverity.HIGH
            can_retry = False
            fallback_action = "remove_channel"
            message = f"Channel {channel_id} not found - it may have been deleted"

        elif isinstance(error, Forbidden):
            severity = ErrorSeverity.HIGH
            can_retry = False
            fallback_action = "check_permissions"
            message = f"No permission to access channel {channel_id} for {operation}"

        elif isinstance(error, HTTPException):
            if error.status == 429:  # Rate limited
                severity = ErrorSeverity.MEDIUM
                can_retry = True
                fallback_action = "wait_and_retry"
                message = f"Rate limited on channel {channel_id}"
            else:
                severity = ErrorSeverity.MEDIUM
                message = f"HTTP error {error.status} on channel {channel_id}: {error.text}"

        else:
            message = f"Unexpected error with channel {channel_id}: {str(error)}"

        # Track error frequency
        self._track_error(error_key, severity)

        result = DiscordErrorInfo(
            severity=severity,
            message=message,
            can_retry=can_retry,
            fallback_action=fallback_action,
            error_type=type(error).__name__,
            channel_id=channel_id,
            operation=operation,
        )

        logger.error(f"Channel error: {result.model_dump()}")
        return result

    def handle_message_error(
        self, error: Exception, message_content: Optional[str] = None, channel_id: Optional[str] = None
    ) -> DiscordErrorInfo:
        """Handle message-related errors.

        Args:
            error: The exception that occurred
            message_content: Content of the message (for context)
            channel_id: Channel where message was being sent

        Returns:
            Error handling result
        """
        error_key = f"message_{type(error).__name__}"
        severity = ErrorSeverity.LOW
        can_retry = True
        suggested_fix = None

        if isinstance(error, HTTPException) and error.status == 400:
            # Bad request - likely message too long or invalid
            severity = ErrorSeverity.MEDIUM
            can_retry = False
            if message_content and len(message_content) > 2000:
                suggested_fix = "split_message"
                message = "Message too long (>2000 chars)"
            else:
                suggested_fix = "validate_content"
                message = f"Invalid message content: {error.text}"

        elif isinstance(error, Forbidden):
            severity = ErrorSeverity.HIGH
            can_retry = False
            suggested_fix = "check_channel_permissions"
            message = f"Cannot send message to channel {channel_id}"

        else:
            message = f"Message send error: {str(error)}"

        self._track_error(error_key, severity)

        result = DiscordErrorInfo(
            severity=severity,
            message=message,
            can_retry=can_retry,
            suggested_fix=suggested_fix,
            error_type=type(error).__name__,
            channel_id=channel_id,
        )

        logger.error(f"Message error: {result.model_dump()}")
        return result

    async def handle_connection_error(self, error: Exception) -> DiscordErrorInfo:
        """Handle connection-related errors.

        Args:
            error: The connection error

        Returns:
            Error handling result
        """
        error_key = f"connection_{type(error).__name__}"
        severity = ErrorSeverity.CRITICAL
        recovery_action = "reconnect"

        if isinstance(error, LoginFailure):
            severity = ErrorSeverity.CRITICAL
            recovery_action = "check_token"
            message = "Failed to login - check bot token"

        elif isinstance(error, ConnectionClosed):
            severity = ErrorSeverity.HIGH
            recovery_action = "reconnect"
            message = f"Connection closed: {error.code} - {error.reason}"

        else:
            message = f"Connection error: {str(error)}"

        self._track_error(error_key, severity)

        # Notify critical error handler if available
        if severity == ErrorSeverity.CRITICAL and self.on_critical_error:
            await self.on_critical_error(message, error)

        result = DiscordErrorInfo(
            severity=severity,
            message=message,
            recovery_action=recovery_action,
            error_type=type(error).__name__,
            can_retry=True,  # Connection errors are generally retryable
        )

        logger.critical(f"Connection error: {result.model_dump()}")
        return result

    def handle_api_error(self, error: Exception, endpoint: str) -> DiscordErrorInfo:
        """Handle Discord API errors.

        Args:
            error: The API error
            endpoint: API endpoint that failed

        Returns:
            Error handling result
        """
        error_key = f"api_{endpoint}_{type(error).__name__}"
        severity = ErrorSeverity.MEDIUM
        retry_after = None

        if isinstance(error, RateLimited):
            severity = ErrorSeverity.LOW
            retry_after = error.retry_after
            message = f"Rate limited on {endpoint}, retry after {retry_after}s"

        elif isinstance(error, HTTPException):
            if 500 <= error.status < 600:
                severity = ErrorSeverity.MEDIUM
                message = f"Discord server error on {endpoint}: {error.status}"
            else:
                message = f"Discord API error on {endpoint}: {error.status} - {error.text}"

        else:
            message = f"API error on {endpoint}: {str(error)}"

        self._track_error(error_key, severity)

        result = DiscordErrorInfo(
            severity=severity,
            message=message,
            retry_after=retry_after,
            error_type=type(error).__name__,
            endpoint=endpoint,
            can_retry=True,  # API errors are generally retryable
        )

        logger.error(f"API error: {result.model_dump()}")
        return result

    def _track_error(self, error_key: str, severity: ErrorSeverity) -> None:
        """Track error frequency and escalate if needed.

        Args:
            error_key: Unique key for this error type
            severity: Error severity
        """
        now = datetime.now(timezone.utc)

        # Clean old errors
        cutoff = now - self._error_window
        self._error_counts = {
            k: v for k, v in self._error_counts.items() if k not in self._last_errors or self._last_errors[k] > cutoff
        }

        # Track this error
        self._error_counts[error_key] = self._error_counts.get(error_key, 0) + 1
        self._last_errors[error_key] = now

        # Check for escalation
        if self._error_counts[error_key] >= self._error_threshold:
            logger.warning(
                f"Error threshold reached for {error_key}: "
                f"{self._error_counts[error_key]} errors in {self._error_window}"
            )

            # Escalate severity
            if severity == ErrorSeverity.LOW:
                severity = ErrorSeverity.MEDIUM
            elif severity == ErrorSeverity.MEDIUM:
                severity = ErrorSeverity.HIGH

    def get_error_stats(self) -> dict[str, Union[dict[str, int], int, float]]:
        """Get current error statistics.

        Returns:
            Error statistics
        """
        return {
            "error_counts": self._error_counts.copy(),
            "threshold": self._error_threshold,
            "window_minutes": self._error_window.total_seconds() / 60,
        }

    def create_error_embed(self, error_info: DiscordErrorInfo) -> discord.Embed:
        """Create a Discord embed for error reporting.

        Args:
            error_info: Error information dictionary

        Returns:
            Discord embed for the error
        """
        # Color based on severity
        colors = {
            ErrorSeverity.LOW: 0x3498DB,  # Blue
            ErrorSeverity.MEDIUM: 0xF39C12,  # Orange
            ErrorSeverity.HIGH: 0xE74C3C,  # Red
            ErrorSeverity.CRITICAL: 0x992D22,  # Dark red
        }

        embed = discord.Embed(
            title=f"⚠️ Error: {error_info.error_type}",
            description=error_info.message,
            color=colors.get(error_info.severity, 0x95A5A6),
            timestamp=datetime.now(timezone.utc),
        )

        # Add fields
        if error_info.operation:
            embed.add_field(name="Operation", value=error_info.operation, inline=True)

        if error_info.channel_id:
            embed.add_field(name="Channel", value=f"<#{error_info.channel_id}>", inline=True)

        embed.add_field(name="Severity", value=error_info.severity.value.upper(), inline=True)
        embed.add_field(name="Retryable", value="Yes" if error_info.can_retry else "No", inline=True)

        if error_info.suggested_fix:
            embed.add_field(name="Suggested Fix", value=error_info.suggested_fix, inline=False)

        if error_info.retry_after:
            embed.add_field(name="Retry After", value=f"{error_info.retry_after} seconds", inline=True)

        embed.set_footer(text="Discord Error Handler")

        return embed
