"""
Agent resource for CIRIS v1 API (Pre-Beta).

Primary interface for communicating with the CIRIS agent.

**WARNING**: This SDK is for the v1 API which is in pre-beta stage.
The API interfaces may change without notice.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ..model_types import LineageInfo
from ..telemetry_models import InteractionContext
from ..transport import Transport

# Request/Response models matching the API


class MessageRequest(BaseModel):
    """Request to submit a message to the agent (async pattern)."""

    message: str = Field(..., description="Message to send to the agent")
    context: Optional[InteractionContext] = Field(None, description="Optional context")


class MessageSubmissionResponse(BaseModel):
    """Response from message submission (returns immediately with task ID or rejection)."""

    message_id: str = Field(..., description="Unique message ID for tracking")
    task_id: Optional[str] = Field(None, description="Task ID if accepted (null if rejected)")
    channel_id: str = Field(..., description="Channel where message was sent")
    submitted_at: str = Field(..., description="ISO timestamp of submission")
    accepted: bool = Field(..., description="Whether message was accepted for processing")
    rejection_reason: Optional[str] = Field(None, description="Reason if rejected")
    rejection_detail: Optional[str] = Field(None, description="Additional rejection details")


class InteractRequest(BaseModel):
    """Request to interact with the agent."""

    message: str = Field(..., description="Message to send to the agent")
    context: Optional[InteractionContext] = Field(None, description="Optional context")


class InteractResponse(BaseModel):
    """Response from agent interaction."""

    message_id: str = Field(..., description="Unique message ID")
    response: str = Field(..., description="Agent's response")
    state: str = Field(..., description="Agent's cognitive state after processing")
    processing_time_ms: int = Field(..., description="Time taken to process")

    # Aliases for backward compatibility
    @property
    def interaction_id(self) -> str:
        """Alias for message_id for backward compatibility."""
        return self.message_id

    @property
    def timestamp(self) -> datetime:
        """Current timestamp for backward compatibility."""
        return datetime.now(timezone.utc)


class ConversationMessage(BaseModel):
    """Message in conversation history."""

    id: str = Field(..., description="Message ID")
    author: str = Field(..., description="Message author")
    content: str = Field(..., description="Message content")
    timestamp: datetime = Field(..., description="When sent")
    is_agent: bool = Field(..., description="Whether this was from the agent")


class ConversationHistory(BaseModel):
    """Conversation history."""

    messages: List[ConversationMessage] = Field(..., description="Message history")
    total_count: int = Field(..., description="Total messages")
    has_more: bool = Field(..., description="Whether more messages exist")

    # Aliases for backward compatibility
    @property
    def interactions(self) -> List[ConversationMessage]:
        """Alias for messages for backward compatibility."""
        return self.messages

    @property
    def total(self) -> int:
        """Alias for total_count for backward compatibility."""
        return self.total_count


class AgentStatus(BaseModel):
    """Agent status and cognitive state."""

    # Core identity
    agent_id: str = Field(..., description="Agent identifier")
    name: str = Field(..., description="Agent name")

    # State information
    cognitive_state: str = Field(..., description="Current cognitive state")
    uptime_seconds: float = Field(..., description="Time since startup")

    # Activity metrics
    messages_processed: int = Field(..., description="Total messages processed")
    last_activity: Optional[datetime] = Field(None, description="Last activity timestamp")
    current_task: Optional[str] = Field(None, description="Current task description")

    # System state
    services_active: int = Field(..., description="Number of active services")
    memory_usage_mb: float = Field(..., description="Current memory usage in MB")

    # Alias for backward compatibility
    @property
    def processor_state(self) -> str:
        """Alias for cognitive_state for backward compatibility."""
        return self.cognitive_state


class AgentIdentity(BaseModel):
    """Agent identity and capabilities."""

    # Identity
    agent_id: str = Field(..., description="Unique agent identifier")
    name: str = Field(..., description="Agent name")
    purpose: str = Field(..., description="Agent's purpose")
    created_at: datetime = Field(..., description="When agent was created")
    lineage: LineageInfo = Field(..., description="Agent lineage information")
    variance_threshold: float = Field(..., description="Identity variance threshold")

    # Capabilities
    tools: List[str] = Field(..., description="Available tools")
    handlers: List[str] = Field(..., description="Active handlers")
    services: Dict[str, int] = Field(..., description="Service availability")
    permissions: List[str] = Field(..., description="Agent permissions")

    # Alias for backward compatibility
    @property
    def version(self) -> str:
        """Version from lineage for backward compatibility."""
        if isinstance(self.lineage, LineageInfo):
            return self.lineage.version
        elif isinstance(self.lineage, dict):
            return self.lineage.get("version", "1.0")
        return "1.0"


class AgentResource:
    """
    Resource for agent interaction endpoints (v1 API Pre-Beta).

    This is the primary interface for interacting with the CIRIS agent,
    providing methods to send messages, retrieve conversation history,
    and check agent status.

    Note: The v1 API consolidates many previous endpoints into this
    streamlined interface focused on interaction over control.
    """

    def __init__(self, transport: Transport) -> None:
        self._transport = transport

    async def submit_message(
        self, message: str, context: Optional[Union[InteractionContext, Dict[str, Any]]] = None
    ) -> MessageSubmissionResponse:
        """Submit a message to the agent (async pattern - returns immediately).

        This endpoint returns immediately with a task_id for tracking or rejection reason.
        Use get_history() to poll for the agent's response later, or use the SSE stream
        to monitor reasoning events in real-time.

        This is recommended for fire-and-forget interactions or when using SSE streaming.

        Args:
            message: The message to send to the agent
            context: Optional context for the interaction

        Returns:
            MessageSubmissionResponse with message_id, task_id, and acceptance status
        """
        # Convert dict context to InteractionContext if needed
        if context and isinstance(context, dict):
            context = InteractionContext(**context)
        request = MessageRequest(message=message, context=context)

        request_data = request.model_dump()

        result = await self._transport.request("POST", "/v1/agent/message", json=request_data)

        return MessageSubmissionResponse(**result)

    async def interact(
        self, message: str, context: Optional[Union[InteractionContext, Dict[str, Any]]] = None
    ) -> InteractResponse:
        """Send message and get response (blocking - waits for response).

        This method combines sending a message and waiting for the agent's response.
        It's the primary way to interact with the agent when you need a synchronous response.

        For async fire-and-forget interactions, use submit_message() instead.

        Args:
            message: The message to send to the agent
            context: Optional context for the interaction

        Returns:
            InteractResponse with message_id, response, state, and timing
        """
        # Convert dict context to InteractionContext if needed
        if context and isinstance(context, dict):
            context = InteractionContext(**context)
        request = InteractRequest(message=message, context=context)

        request_data = request.model_dump()

        result = await self._transport.request("POST", "/v1/agent/interact", json=request_data)

        return InteractResponse(**result)

    async def get_history(self, limit: int = 50, before: Optional[datetime] = None) -> ConversationHistory:
        """Get conversation history.

        Args:
            limit: Maximum number of messages to return (1-200, default 50)
            before: Get messages before this time

        Returns:
            ConversationHistory with messages and metadata
        """
        params = {"limit": limit}
        if before:
            params["before"] = before.isoformat()

        result = await self._transport.request("GET", "/v1/agent/history", params=params)

        # Parse timestamps in messages
        for msg in result["messages"]:
            msg["timestamp"] = datetime.fromisoformat(msg["timestamp"])

        return ConversationHistory(**result)

    async def get_status(self) -> AgentStatus:
        """Get agent status and cognitive state.

        Returns:
            AgentStatus with comprehensive state information
        """
        result = await self._transport.request("GET", "/v1/agent/status")

        # Parse timestamp if present
        if result.get("last_activity"):
            result["last_activity"] = datetime.fromisoformat(result["last_activity"])

        return AgentStatus(**result)

    async def get_identity(self) -> AgentIdentity:
        """Get agent identity and capabilities.

        Returns:
            AgentIdentity with comprehensive identity information
        """
        result = await self._transport.request("GET", "/v1/agent/identity")

        # Parse timestamp
        result["created_at"] = datetime.fromisoformat(result["created_at"])

        # Parse lineage if it's a dict
        if isinstance(result.get("lineage"), dict):
            result["lineage"] = LineageInfo(**result["lineage"])

        return AgentIdentity(**result)

    async def stream(self, websocket_url: Optional[str] = None):
        """
        WebSocket streaming interface (placeholder).

        Note: Full WebSocket support will be added in a future release.
        For now, this method exists to satisfy interface requirements.
        """
        # This is a placeholder - actual WebSocket implementation would go here
        raise NotImplementedError("WebSocket streaming not yet implemented in SDK")

    # Convenience methods for common patterns

    async def ask(self, question: str, context: Optional[Union[InteractionContext, Dict[str, Any]]] = None) -> str:
        """Ask a question and get response.

        Convenience method that wraps interact() for simple Q&A.

        Args:
            question: Question to ask
            context: Optional context

        Returns:
            Agent's response text
        """
        response = await self.interact(question, context)
        return response.response

    # Backward compatibility methods (deprecated)

    async def send_message(
        self,
        content: str,
        channel_id: str = "api_default",
        author_id: str = "api_user",
        author_name: str = "API User",
        reference_message_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """[DEPRECATED] Use interact() instead.

        Send a message to the agent.

        This method is maintained for backward compatibility.
        New code should use interact() instead.
        """
        import warnings

        warnings.warn("send_message() is deprecated. Use interact() instead.", DeprecationWarning, stacklevel=2)

        response = await self.interact(content)
        return {"message_id": response.message_id, "status": "sent"}

    async def get_messages(
        self, channel_id: str, limit: int = 100, after_message_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """[DEPRECATED] Use get_history() instead.

        Get messages from a channel.

        This method is maintained for backward compatibility.
        New code should use get_history() instead.
        """
        import warnings

        warnings.warn("get_messages() is deprecated. Use get_history() instead.", DeprecationWarning, stacklevel=2)

        history = await self.get_history(limit=limit)

        # Convert to old format
        messages = []
        for msg in history.messages:
            messages.append(
                {
                    "id": msg.id,
                    "content": msg.content,
                    "author_id": "ciris_agent" if msg.is_agent else "api_user",
                    "author_name": msg.author,
                    "channel_id": channel_id,
                    "timestamp": msg.timestamp.isoformat(),
                }
            )

        return {"messages": messages}

    async def list_channels(self) -> Dict[str, Any]:
        """[DEPRECATED] Channels are now implicit per user.

        This method is maintained for backward compatibility.
        Returns a single default channel.
        """
        import warnings

        warnings.warn(
            "list_channels() is deprecated. Channels are now implicit per user.", DeprecationWarning, stacklevel=2
        )

        return {"channels": [{"id": "api_default", "name": "Default API Channel", "active": True}]}

    async def get_capabilities(self) -> Dict[str, Any]:
        """[DEPRECATED] Use get_identity() instead.

        Get agent capabilities.

        This method is maintained for backward compatibility.
        New code should use get_identity() instead.
        """
        import warnings

        warnings.warn("get_capabilities() is deprecated. Use get_identity() instead.", DeprecationWarning, stacklevel=2)

        identity = await self.get_identity()

        return {
            "tools": identity.tools,
            "handlers": identity.handlers,
            "services": identity.services,
            "permissions": identity.permissions,
        }
