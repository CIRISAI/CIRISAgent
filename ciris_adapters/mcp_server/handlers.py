"""
MCP Server Request Handlers.

Simple handlers exposing 3 tools:
- status: Get agent status
- message: Send a message to user's channel
- history: Get message history from user's channel
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from ciris_adapters.mcp_common.protocol import (
    MCPErrorCode,
    MCPMessage,
    MCPMessageType,
    create_error_response,
    create_success_response,
)
from ciris_adapters.mcp_common.schemas import (
    MCPListToolsResult,
    MCPToolCallResult,
    MCPToolInfo,
    MCPToolInputSchema,
)

logger = logging.getLogger(__name__)


# Tool definitions - these are the only 3 tools exposed
TOOLS: List[MCPToolInfo] = [
    MCPToolInfo(
        name="status",
        description="Get the current status of the CIRIS agent including cognitive state and health",
        inputSchema=MCPToolInputSchema(
            type="object",
            properties={},
            required=[],
        ),
    ),
    MCPToolInfo(
        name="message",
        description="Send a message to the CIRIS agent and receive a response",
        inputSchema=MCPToolInputSchema(
            type="object",
            properties={
                "content": {
                    "type": "string",
                    "description": "The message content to send to the agent",
                },
            },
            required=["content"],
        ),
    ),
    MCPToolInfo(
        name="history",
        description="Get recent message history from your conversation with the agent",
        inputSchema=MCPToolInputSchema(
            type="object",
            properties={
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of messages to return (default: 20)",
                    "default": 20,
                },
            },
            required=[],
        ),
    ),
]


class MCPServerHandler:
    """Handler for MCP server requests.

    Provides 3 simple tools:
    - status: Agent status check
    - message: Send message to user's channel
    - history: Get message history
    """

    def __init__(
        self,
        runtime: Any,
        communication_service: Optional[Any] = None,
    ) -> None:
        """Initialize handler.

        Args:
            runtime: CIRIS runtime instance
            communication_service: Communication service for messaging
        """
        self._runtime = runtime
        self._communication = communication_service
        self._user_channels: Dict[str, str] = {}  # user_id -> channel_id mapping

    def set_user_channel(self, user_id: str, channel_id: str) -> None:
        """Set the channel ID for an authenticated user.

        Args:
            user_id: Authenticated user ID
            channel_id: Channel ID (typically api_{user_id})
        """
        self._user_channels[user_id] = channel_id

    def get_user_channel(self, user_id: str) -> str:
        """Get the channel ID for an authenticated user.

        Args:
            user_id: Authenticated user ID

        Returns:
            Channel ID (defaults to api_{user_id} if not set)
        """
        return self._user_channels.get(user_id, f"api_{user_id}")

    def _get_request_id(self, message: MCPMessage) -> Union[str, int]:
        """Get request ID from message, defaulting to 0 if None."""
        return message.id if message.id is not None else 0

    async def handle_request(
        self,
        message: MCPMessage,
        user_id: Optional[str] = None,
    ) -> MCPMessage:
        """Handle an incoming MCP request.

        Args:
            message: MCP request message
            user_id: Authenticated user ID (required for message/history)

        Returns:
            MCP response message
        """
        method = message.method
        rid = self._get_request_id(message)

        if method == "tools/list":
            return await self._handle_list_tools(message)
        elif method == "tools/call":
            return await self._handle_call_tool(message, user_id)
        elif method == "ping":
            return create_success_response(rid, {})
        else:
            return create_error_response(
                rid,
                MCPErrorCode.METHOD_NOT_FOUND,
                f"Method not supported: {method}",
            )

    async def _handle_list_tools(self, message: MCPMessage) -> MCPMessage:
        """Handle tools/list request."""
        rid = self._get_request_id(message)
        result = MCPListToolsResult(tools=TOOLS)
        return create_success_response(rid, result.model_dump())

    async def _handle_call_tool(
        self,
        message: MCPMessage,
        user_id: Optional[str] = None,
    ) -> MCPMessage:
        """Handle tools/call request."""
        rid = self._get_request_id(message)
        params = message.params or {}
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "status":
            return await self._execute_status(rid)
        elif tool_name == "message":
            if not user_id:
                return create_error_response(
                    rid,
                    MCPErrorCode.INVALID_REQUEST,
                    "Authentication required for message tool",
                )
            return await self._execute_message(rid, user_id, arguments)
        elif tool_name == "history":
            if not user_id:
                return create_error_response(
                    rid,
                    MCPErrorCode.INVALID_REQUEST,
                    "Authentication required for history tool",
                )
            return await self._execute_history(rid, user_id, arguments)
        else:
            return create_error_response(
                rid,
                MCPErrorCode.INVALID_REQUEST,
                f"Unknown tool: {tool_name}",
            )

    async def _execute_status(self, rid: Union[str, int]) -> MCPMessage:
        """Execute status tool - get agent status."""
        try:
            status: Dict[str, Any] = {
                "healthy": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Get cognitive state if runtime available
            if self._runtime:
                if hasattr(self._runtime, "cognitive_state"):
                    status["cognitive_state"] = str(self._runtime.cognitive_state)
                if hasattr(self._runtime, "is_running"):
                    status["is_running"] = self._runtime.is_running
                if hasattr(self._runtime, "get_status"):
                    runtime_status = await self._runtime.get_status()
                    if isinstance(runtime_status, dict):
                        status.update(runtime_status)

            result = MCPToolCallResult(
                content=[{"type": "text", "text": str(status)}],
                isError=False,
            )
            return create_success_response(rid, result.model_dump())

        except Exception as e:
            logger.error(f"Error executing status tool: {e}")
            result = MCPToolCallResult(
                content=[{"type": "text", "text": f"Error: {e}"}],
                isError=True,
            )
            return create_success_response(rid, result.model_dump())

    async def _execute_message(
        self,
        rid: Union[str, int],
        user_id: str,
        arguments: Dict[str, Any],
    ) -> MCPMessage:
        """Execute message tool - send message to user's channel.

        This tool allows MCP clients to send messages to the CIRIS agent.
        The message is submitted through the runtime's message handler if available,
        or queued for processing.
        """
        content = arguments.get("content", "")
        if not content:
            result = MCPToolCallResult(
                content=[{"type": "text", "text": "Error: content is required"}],
                isError=True,
            )
            return create_success_response(rid, result.model_dump())

        try:
            import uuid

            channel_id = self.get_user_channel(user_id)
            message_id = str(uuid.uuid4())

            # Create the incoming message
            from ciris_engine.schemas.runtime.messages import IncomingMessage

            message = IncomingMessage(
                message_id=message_id,
                channel_id=channel_id,
                author_id=user_id,
                author_name=user_id,
                content=content,
                timestamp=datetime.now(timezone.utc),
                platform="mcp",
            )

            # Try to submit through various available handlers
            submitted = False

            # Option 1: Use runtime's message handler (API adapter pattern)
            if self._runtime and hasattr(self._runtime, "on_message"):
                await self._runtime.on_message(message)
                submitted = True
                logger.info(f"Message {message_id} submitted via runtime.on_message")

            # Option 2: Use runtime's message observer if available
            elif self._runtime and hasattr(self._runtime, "message_observer"):
                observer = self._runtime.message_observer
                if observer and hasattr(observer, "handle_incoming_message"):
                    await observer.handle_incoming_message(message)
                    submitted = True
                    logger.info(f"Message {message_id} submitted via message_observer")

            # Option 3: Use processor's message queue if available
            elif self._runtime and hasattr(self._runtime, "processor"):
                processor = self._runtime.processor
                if processor and hasattr(processor, "submit_message"):
                    await processor.submit_message(message)
                    submitted = True
                    logger.info(f"Message {message_id} submitted via processor")

            if not submitted:
                # No handler available - message cannot be processed
                result = MCPToolCallResult(
                    content=[{
                        "type": "text",
                        "text": "Error: No message handler available. The MCP server may not be fully integrated with the runtime.",
                    }],
                    isError=True,
                )
                return create_success_response(rid, result.model_dump())

            result = MCPToolCallResult(
                content=[{
                    "type": "text",
                    "text": f"Message submitted to channel {channel_id}. Message ID: {message_id}",
                }],
                isError=False,
            )
            return create_success_response(rid, result.model_dump())

        except Exception as e:
            logger.error(f"Error executing message tool: {e}")
            result = MCPToolCallResult(
                content=[{"type": "text", "text": f"Error: {e}"}],
                isError=True,
            )
            return create_success_response(rid, result.model_dump())

    async def _execute_history(
        self,
        rid: Union[str, int],
        user_id: str,
        arguments: Dict[str, Any],
    ) -> MCPMessage:
        """Execute history tool - get message history from user's channel."""
        limit = arguments.get("limit", 20)

        try:
            channel_id = self.get_user_channel(user_id)

            if not self._communication:
                result = MCPToolCallResult(
                    content=[{"type": "text", "text": "Error: Communication service not available"}],
                    isError=True,
                )
                return create_success_response(rid, result.model_dump())

            # Get message history
            if hasattr(self._communication, "get_channel_history"):
                history = await self._communication.get_channel_history(
                    channel_id=channel_id,
                    limit=limit,
                )
            elif hasattr(self._communication, "fetch_messages"):
                history = await self._communication.fetch_messages(
                    channel_id=channel_id,
                    limit=limit,
                )
            else:
                history = []

            # Format history for response
            formatted = []
            for msg in history:
                if hasattr(msg, "model_dump"):
                    formatted.append(msg.model_dump())
                elif isinstance(msg, dict):
                    formatted.append(msg)
                else:
                    formatted.append(str(msg))

            result = MCPToolCallResult(
                content=[{
                    "type": "text",
                    "text": str({
                        "channel_id": channel_id,
                        "message_count": len(formatted),
                        "messages": formatted,
                    }),
                }],
                isError=False,
            )
            return create_success_response(rid, result.model_dump())

        except Exception as e:
            logger.error(f"Error executing history tool: {e}")
            result = MCPToolCallResult(
                content=[{"type": "text", "text": f"Error: {e}"}],
                isError=True,
            )
            return create_success_response(rid, result.model_dump())


__all__ = ["MCPServerHandler", "TOOLS"]
