"""Discord audit logging component."""

import json
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

from ciris_engine.schemas.audit.core import EventPayload
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.protocols.services.graph.audit import AuditServiceProtocol
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol

logger = logging.getLogger(__name__)


class DiscordAuditLogger:
    """Handles audit logging for Discord operations."""

    def __init__(
        self,
        time_service: Optional["TimeServiceProtocol"] = None,
        audit_service: Optional["AuditServiceProtocol"] = None,
    ) -> None:
        """Initialize the audit logger.

        Args:
            time_service: Time service for consistent timestamps
            audit_service: Audit service for storing audit entries
        """
        self._time_service = time_service
        self._audit_service = audit_service

        # Ensure we have a time service
        if self._time_service is None:
            from ciris_engine.logic.services.lifecycle.time import TimeService

            self._time_service = TimeService()

    def set_audit_service(self, audit_service: "AuditServiceProtocol") -> None:
        """Set the audit service after initialization.

        Args:
            audit_service: Audit service instance
        """
        self._audit_service = audit_service

    async def log_operation(
        self,
        operation: str,
        actor: str,
        context: JSONDict,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> None:
        """Log a Discord operation to the audit trail.

        Args:
            operation: Operation name (e.g., "send_message", "fetch_guidance")
            actor: Who performed the operation (user ID or system component)
            context: Operation context and parameters
            success: Whether the operation succeeded
            error_message: Error message if operation failed
        """
        if not self._audit_service:
            # Fall back to standard logging
            if success:
                logger.info(f"Discord operation: {operation} by {actor} - {context}")
            else:
                logger.error(f"Discord operation failed: {operation} by {actor} - {error_message}")
            return

        try:
            # Create action description
            action = f"discord.{operation}"
            if not success:
                action = f"discord.{operation}.failed"

            # Create audit event data using EventPayload
            event_data = EventPayload(
                action=action,
                result="success" if success else "failure",
                error=error_message,
                user_id=actor,
                channel_id=context.get("channel_id", "unknown"),
                service_name="discord_adapter",
            )

            # Log to audit service
            await self._audit_service.log_event(event_type=action, event_data=event_data)

        except Exception as e:
            logger.error(f"Failed to log audit entry: {e}")

    async def log_message_sent(
        self, channel_id: str, author_id: str, message_content: str, correlation_id: Optional[str] = None
    ) -> None:
        """DEPRECATED: Message sends are already audited via speak handler action.

        This method is kept for backwards compatibility but does nothing.
        """
        pass

    async def log_message_received(self, channel_id: str, author_id: str, author_name: str, message_id: str) -> None:
        """DEPRECATED: Message receives don't need auditing - too verbose.

        This method is kept for backwards compatibility but does nothing.
        """
        pass

    async def log_tool_execution(
        self,
        user_id: str,
        tool_name: str,
        parameters: JSONDict,
        success: bool,
        execution_time_ms: float,
        error: Optional[str] = None,
    ) -> None:
        """Log a tool execution operation.

        Args:
            user_id: Who executed the tool
            tool_name: Name of the tool
            parameters: Tool parameters
            success: Whether execution succeeded
            execution_time_ms: Execution time in milliseconds
            error: Error message if failed
        """
        await self.log_operation(
            operation="execute_tool",
            actor=user_id,
            context={
                "tool_name": tool_name,
                "parameters": json.dumps(parameters) if parameters else "{}",
                "execution_time_ms": execution_time_ms,
            },
            success=success,
            error_message=error,
        )

    async def log_connection_event(
        self, event_type: str, guild_count: int, user_count: int, error: Optional[str] = None
    ) -> None:
        """DEPRECATED: Connection events are too verbose for audit trail.

        This method is kept for backwards compatibility but does nothing.
        Connection issues are already logged to standard logs.
        """
        pass
