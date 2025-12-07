"""
Sample adapter service implementations.

This module demonstrates how to implement services for each bus type:
- TOOL: SampleToolService
- COMMUNICATION: SampleCommunicationService
- WISE_AUTHORITY: SampleWisdomService

Each service shows the minimum required interface plus best practices.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class SampleToolService:
    """Sample tool service demonstrating TOOL bus registration.

    Tools are callable actions that CIRIS can execute to interact with
    external systems or perform specific operations.

    This service provides:
    - echo: Returns input back (for testing)
    - status: Returns adapter status
    - config: Returns current configuration

    Example tool handler result:
        {
            "success": True,
            "data": {"echoed": "hello world"},
            "tool_name": "sample:echo"
        }
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        """Initialize the tool service.

        Args:
            config: Optional configuration dictionary from manifest
        """
        self.config = config or {}
        self._call_count = 0
        logger.info("SampleToolService initialized")

    async def start(self) -> None:
        """Start the service (required lifecycle method)."""
        logger.info("SampleToolService started")

    async def stop(self) -> None:
        """Stop the service (required lifecycle method)."""
        logger.info("SampleToolService stopped")

    def get_tools(self) -> List[Dict[str, Any]]:
        """Return list of available tools.

        Returns:
            List of tool definitions with name, description, and parameters
        """
        return [
            {
                "name": "sample:echo",
                "description": "Echo back the input message",
                "parameters": {
                    "message": {"type": "string", "required": True},
                },
            },
            {
                "name": "sample:status",
                "description": "Get adapter status and metrics",
                "parameters": {},
            },
            {
                "name": "sample:config",
                "description": "Get current adapter configuration",
                "parameters": {},
            },
        ]

    async def execute_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a tool and return results.

        Args:
            tool_name: Name of the tool to execute
            parameters: Tool parameters

        Returns:
            Tool execution result
        """
        self._call_count += 1

        if tool_name == "sample:echo":
            message = parameters.get("message", "")
            return {
                "success": True,
                "data": {"echoed": message, "timestamp": datetime.now(timezone.utc).isoformat()},
                "tool_name": tool_name,
            }

        elif tool_name == "sample:status":
            return {
                "success": True,
                "data": {
                    "status": "running",
                    "call_count": self._call_count,
                    "uptime_seconds": 0,  # Would track actual uptime in production
                },
                "tool_name": tool_name,
            }

        elif tool_name == "sample:config":
            # Return safe subset of config (no secrets)
            safe_config = {
                k: v for k, v in self.config.items() if "token" not in k.lower() and "secret" not in k.lower()
            }
            return {
                "success": True,
                "data": {"config": safe_config},
                "tool_name": tool_name,
            }

        return {
            "success": False,
            "error": f"Unknown tool: {tool_name}",
            "tool_name": tool_name,
        }


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
