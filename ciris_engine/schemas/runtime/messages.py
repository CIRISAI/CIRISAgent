"""
Message schemas for CIRIS Trinity Architecture.

Typed message structures for all communication types.
"""

from enum import Enum
from typing import TYPE_CHECKING, Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from ciris_engine.schemas.runtime.models import ImageContent


class MessageHandlingStatus(str, Enum):
    """Status of message handling after submission."""

    TASK_CREATED = "TASK_CREATED"  # Task successfully created
    AGENT_OWN_MESSAGE = "AGENT_OWN_MESSAGE"  # Message from agent itself (ignored)
    FILTERED_OUT = "FILTERED_OUT"  # Filtered by adaptive filter
    CREDIT_DENIED = "CREDIT_DENIED"  # Insufficient credits
    CREDIT_CHECK_FAILED = "CREDIT_CHECK_FAILED"  # Credit provider error
    PROCESSOR_PAUSED = "PROCESSOR_PAUSED"  # Agent processor paused
    RATE_LIMITED = "RATE_LIMITED"  # Rate limit exceeded
    CHANNEL_RESTRICTED = "CHANNEL_RESTRICTED"  # Channel access denied
    UPDATED_EXISTING_TASK = "UPDATED_EXISTING_TASK"  # Flagged existing task with new info


class PassiveObservationResult(BaseModel):
    """Result of creating a passive observation (task + thought)."""

    task_id: str = Field(..., description="Task ID (newly created or existing task that was updated)")
    task_created: bool = Field(..., description="True if new task created, False if existing task updated")
    thought_id: Optional[str] = Field(None, description="Thought ID if created")
    existing_task_updated: bool = Field(default=False, description="Whether an existing task was updated")


class MessageHandlingResult(BaseModel):
    """Result of handling an incoming message through the observer pipeline."""

    status: MessageHandlingStatus = Field(..., description="Status of message handling")
    task_id: Optional[str] = Field(None, description="Task ID if created or updated")
    message_id: str = Field(..., description="Original message ID")
    channel_id: str = Field(..., description="Channel ID where message was sent")
    filtered: bool = Field(default=False, description="Whether message was filtered out")
    filter_reasoning: Optional[str] = Field(None, description="Filter reasoning if filtered")
    credit_denied: bool = Field(default=False, description="Whether denied by credit policy")
    credit_denial_reason: Optional[str] = Field(None, description="Credit denial reason")
    task_priority: int = Field(default=0, description="Priority of created task (0=passive, 5=high, 10=critical)")
    existing_task_updated: bool = Field(default=False, description="Whether an existing task was updated")


class IncomingMessage(BaseModel):
    """Schema for incoming messages from various sources."""

    message_id: str = Field(..., description="Unique message identifier")
    author_id: str = Field(..., description="Message author ID")
    author_name: str = Field(..., description="Message author name")
    content: str = Field(..., description="Message content")
    destination_id: Optional[str] = Field(default=None, alias="channel_id")
    reference_message_id: Optional[str] = Field(None, description="ID of message being replied to")
    timestamp: Optional[str] = Field(None, description="Message timestamp")
    # Native multimodal support - images attached to the message
    images: List[Any] = Field(default_factory=list, description="Images attached to this message (List[ImageContent])")

    model_config = ConfigDict(populate_by_name=True, extra="allow")

    @property
    def channel_id(self) -> Optional[str]:
        """Backward compatibility alias for destination_id."""
        return self.destination_id


class DiscordMessage(IncomingMessage):
    """Incoming message specific to the Discord platform."""

    is_bot: bool = Field(default=False, description="Whether author is a bot")
    is_dm: bool = Field(default=False, description="Whether this is a DM")
    raw_message: Optional[Any] = Field(default=None, exclude=True)  # Discord.py message object

    def __init__(self, **data: Any) -> None:
        if "destination_id" not in data and "channel_id" in data:
            data["destination_id"] = data.get("channel_id")
        super().__init__(**data)


class FetchedMessage(BaseModel):
    """Message returned by CommunicationService.fetch_messages."""

    message_id: Optional[str] = Field(default=None, alias="id")
    content: Optional[str] = None
    author_id: Optional[str] = None
    author_name: Optional[str] = None
    timestamp: Optional[str] = None
    is_bot: Optional[bool] = False
    message_type: Optional[str] = Field(
        default="user", description="Type of message (user, agent, system, error)"
    )

    model_config = ConfigDict(populate_by_name=True, extra="allow")


__all__ = [
    "MessageHandlingStatus",
    "PassiveObservationResult",
    "MessageHandlingResult",
    "IncomingMessage",
    "DiscordMessage",
    "FetchedMessage",
]
