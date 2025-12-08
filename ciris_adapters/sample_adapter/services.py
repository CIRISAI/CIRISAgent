"""
Sample adapter service implementations.

This module demonstrates how to implement services for each bus type:
- TOOL: SampleToolService
- COMMUNICATION: SampleCommunicationService
- WISE_AUTHORITY: SampleWisdomService

Each service shows the minimum required interface plus best practices.

Includes context enrichment tools that are automatically executed during
context gathering to provide additional information for action selection.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema

logger = logging.getLogger(__name__)


class SampleToolService:
    """Sample tool service demonstrating TOOL bus registration.

    Tools are callable actions that CIRIS can execute to interact with
    external systems or perform specific operations.

    This service provides:
    - sample:echo: Returns input back (for testing)
    - sample:status: Returns adapter status
    - sample:config: Returns current configuration
    - sample:list_items: Lists available items (CONTEXT ENRICHMENT TOOL)

    The sample:list_items tool is marked with context_enrichment=True,
    demonstrating how adapters can provide automatic context during
    action selection.

    Example tool handler result:
        {
            "success": True,
            "data": {"echoed": "hello world"},
            "tool_name": "sample:echo"
        }
    """

    # Tool definitions using ToolInfo schema for full protocol compliance
    TOOL_DEFINITIONS: Dict[str, ToolInfo] = {
        "sample:echo": ToolInfo(
            name="sample:echo",
            description="Echo back the input message",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "message": {
                        "type": "string",
                        "description": "Message to echo back",
                    },
                },
                required=["message"],
            ),
        ),
        "sample:status": ToolInfo(
            name="sample:status",
            description="Get adapter status and metrics",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            ),
        ),
        "sample:config": ToolInfo(
            name="sample:config",
            description="Get current adapter configuration (secrets redacted)",
            parameters=ToolParameterSchema(
                type="object",
                properties={},
                required=[],
            ),
        ),
        # CONTEXT ENRICHMENT TOOL - automatically executed during context gathering
        "sample:list_items": ToolInfo(
            name="sample:list_items",
            description="List all available sample items. Used for context enrichment.",
            parameters=ToolParameterSchema(
                type="object",
                properties={
                    "category": {
                        "type": "string",
                        "description": "Filter by category (optional)",
                    },
                },
                required=[],
            ),
            # Mark for automatic context enrichment during action selection
            context_enrichment=True,
            # Default params when run for enrichment (empty = list all)
            context_enrichment_params={},
        ),
    }

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service.

        Args:
            config: Optional configuration dictionary from manifest
        """
        self.config = config or {}
        self._call_count = 0
        # Mock items for context enrichment demo
        self._items = [
            {"id": "item_1", "name": "Widget A", "category": "widgets", "status": "active"},
            {"id": "item_2", "name": "Widget B", "category": "widgets", "status": "active"},
            {"id": "item_3", "name": "Gadget X", "category": "gadgets", "status": "inactive"},
            {"id": "item_4", "name": "Gadget Y", "category": "gadgets", "status": "active"},
        ]
        logger.info("SampleToolService initialized")

    async def start(self) -> None:
        """Start the service (required lifecycle method)."""
        logger.info("SampleToolService started")

    async def stop(self) -> None:
        """Stop the service (required lifecycle method)."""
        logger.info("SampleToolService stopped")

    # =========================================================================
    # ToolServiceProtocol Implementation
    # =========================================================================

    async def get_available_tools(self) -> List[str]:
        """Get available tool names. Used by system snapshot tool collection."""
        return list(self.TOOL_DEFINITIONS.keys())

    async def list_tools(self) -> List[str]:
        """Legacy alias for get_available_tools()."""
        return await self.get_available_tools()

    async def get_tool_info(self, tool_name: str) -> Optional[ToolInfo]:
        """Get detailed info for a specific tool. Used by system snapshot."""
        return self.TOOL_DEFINITIONS.get(tool_name)

    async def get_all_tool_info(self) -> List[ToolInfo]:
        """Get info for all tools. Used by /tools API endpoint."""
        return list(self.TOOL_DEFINITIONS.values())

    async def get_tool_schema(self, tool_name: str) -> Optional[ToolParameterSchema]:
        """Get parameter schema for a tool."""
        tool_info = self.TOOL_DEFINITIONS.get(tool_name)
        return tool_info.parameters if tool_info else None

    async def validate_parameters(self, tool_name: str, parameters: Dict[str, Any]) -> bool:
        """Validate parameters for a tool without executing it."""
        if tool_name not in self.TOOL_DEFINITIONS:
            return False
        tool_info = self.TOOL_DEFINITIONS[tool_name]
        if not tool_info.parameters:
            return True
        # Basic validation: check required fields are present
        required = tool_info.parameters.required or []
        return all(param in parameters for param in required)

    async def get_tool_result(self, correlation_id: str, timeout: float = 30.0) -> Optional[ToolExecutionResult]:
        """Get result of previously executed tool. Not implemented for sync tools."""
        return None

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of available tools (legacy format).

        Returns:
            List of tool definitions with name, description, and parameters
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters.model_dump() if tool.parameters else {},
            }
            for tool in self.TOOL_DEFINITIONS.values()
        ]

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> ToolExecutionResult:
        """Execute a tool and return results.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            context: Optional execution context

        Returns:
            ToolExecutionResult with status, success, data, and error
        """
        self._call_count += 1
        correlation_id = str(uuid4())

        if tool_name not in self.TOOL_DEFINITIONS:
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.NOT_FOUND,
                success=False,
                data=None,
                error=f"Unknown tool: {tool_name}",
                correlation_id=correlation_id,
            )

        try:
            if tool_name == "sample:echo":
                message = parameters.get("message", "")
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.COMPLETED,
                    success=True,
                    data={"echoed": message, "timestamp": datetime.now(timezone.utc).isoformat()},
                    error=None,
                    correlation_id=correlation_id,
                )

            elif tool_name == "sample:status":
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.COMPLETED,
                    success=True,
                    data={
                        "status": "running",
                        "call_count": self._call_count,
                        "uptime_seconds": 0,  # Would track actual uptime in production
                    },
                    error=None,
                    correlation_id=correlation_id,
                )

            elif tool_name == "sample:config":
                # Return safe subset of config (no secrets)
                safe_config = {
                    k: v for k, v in self.config.items() if "token" not in k.lower() and "secret" not in k.lower()
                }
                return ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.COMPLETED,
                    success=True,
                    data={"config": safe_config},
                    error=None,
                    correlation_id=correlation_id,
                )

            elif tool_name == "sample:list_items":
                # Context enrichment tool - list available items
                category = parameters.get("category")
                items = self._items
                if category:
                    items = [i for i in items if i.get("category") == category]

                return ToolExecutionResult(
                    tool_name=tool_name,
                    status=ToolExecutionStatus.COMPLETED,
                    success=True,
                    data={
                        "count": len(items),
                        "items": items,
                        "filtered_by_category": category,
                    },
                    error=None,
                    correlation_id=correlation_id,
                )

            # Fallback - should not reach here
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=f"Tool not implemented: {tool_name}",
                correlation_id=correlation_id,
            )

        except Exception as e:
            logger.error(f"Error executing tool {tool_name}: {e}")
            return ToolExecutionResult(
                tool_name=tool_name,
                status=ToolExecutionStatus.FAILED,
                success=False,
                data=None,
                error=str(e),
                correlation_id=correlation_id,
            )


class SampleCommunicationService:
    """Sample communication service demonstrating COMMUNICATION bus registration.

    Communication services handle message sending and receiving through
    external channels (Discord, Slack, email, etc.).

    This mock service stores messages in memory for testing.

    Example message format:
        {
            "id": "msg_123",
            "channel": "sample:channel_1",
            "content": "Hello world",
            "author_id": "user_456",
            "timestamp": "2024-01-15T10:30:00Z"
        }
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the communication service.

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self._messages: List[Dict[str, Any]] = []
        self._sent_messages: List[Dict[str, Any]] = []
        logger.info("SampleCommunicationService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("SampleCommunicationService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("SampleCommunicationService stopped")

    async def send_message(self, channel: str, content: str, **kwargs: Any) -> Dict[str, Any]:
        """Send a message to a channel.

        Args:
            channel: Target channel identifier
            content: Message content
            **kwargs: Additional message options

        Returns:
            Send result with message ID
        """
        msg_id = f"msg_{uuid4().hex[:8]}"
        message = {
            "id": msg_id,
            "channel": channel,
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sent": True,
        }
        self._sent_messages.append(message)

        logger.info(f"Sample: Sent message {msg_id} to {channel}")
        return {"success": True, "message_id": msg_id}

    async def fetch_messages(self, channel: Optional[str] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Fetch messages from channel(s).

        Args:
            channel: Optional channel filter
            limit: Maximum messages to return

        Returns:
            List of messages
        """
        messages = self._messages
        if channel:
            messages = [m for m in messages if m.get("channel") == channel]
        return messages[:limit]

    def inject_test_message(self, channel: str, content: str, author_id: str = "test_user") -> str:
        """Inject a test message for QA testing.

        Args:
            channel: Channel identifier
            content: Message content
            author_id: Author ID

        Returns:
            Message ID
        """
        msg_id = f"msg_{uuid4().hex[:8]}"
        self._messages.append(
            {
                "id": msg_id,
                "channel": channel,
                "content": content,
                "author_id": author_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        return msg_id


class SampleWisdomService:
    """Sample wisdom service demonstrating WISE_AUTHORITY bus registration.

    Wisdom services provide domain-specific guidance when the agent faces
    uncertainty or needs external expert input.

    This mock service provides simple echo-based guidance for testing.

    Example guidance response:
        {
            "guidance": "Sample guidance for your question",
            "confidence": 0.8,
            "source": "sample_adapter",
            "domain": "sample"
        }
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the wisdom service.

        Args:
            config: Optional configuration dictionary
        """
        self.config = config or {}
        self._guidance_count = 0
        logger.info("SampleWisdomService initialized")

    async def start(self) -> None:
        """Start the service."""
        logger.info("SampleWisdomService started")

    async def stop(self) -> None:
        """Stop the service."""
        logger.info("SampleWisdomService stopped")

    def get_capabilities(self) -> List[str]:
        """Return list of capabilities this wisdom source provides.

        Returns:
            List of capability strings
        """
        return [
            "get_guidance",
            "fetch_guidance",
            "domain:sample",
        ]

    async def get_guidance(self, question: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Get guidance for a question.

        Args:
            question: The question or uncertainty to address
            context: Optional context about the situation

        Returns:
            Guidance response with recommendation and confidence
        """
        self._guidance_count += 1

        # Simple mock guidance - in production this would query domain experts
        guidance = (
            f"Sample guidance for: '{question[:50]}...'" if len(question) > 50 else f"Sample guidance for: '{question}'"
        )

        return {
            "guidance": guidance,
            "confidence": 0.75,
            "source": "sample_adapter",
            "domain": "sample",
            "reasoning": "This is mock guidance from the sample adapter for testing purposes.",
            "request_count": self._guidance_count,
        }

    async def fetch_guidance(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Fetch previously requested guidance by ID.

        For async guidance flows where response is not immediate.

        Args:
            request_id: ID of the guidance request

        Returns:
            Guidance if available, None if pending/not found
        """
        # Mock implementation - always returns completed guidance
        return {
            "request_id": request_id,
            "status": "completed",
            "guidance": f"Fetched guidance for request {request_id}",
            "confidence": 0.8,
            "source": "sample_adapter",
        }
