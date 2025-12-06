"""
Action context schemas for contract-driven architecture.

Replaces context: Dict[str, Any] for each action type.
"""

from datetime import datetime
from typing import Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BaseActionContext(BaseModel):
    """Base context shared by all actions."""

    task_id: UUID = Field(..., description="Current task ID")
    thought_id: UUID = Field(..., description="Current thought ID")
    correlation_id: UUID = Field(..., description="Correlation ID for tracing")
    channel_id: str = Field(..., description="Channel where action occurs")
    user_id: Optional[str] = Field(None, description="User requesting action")

    model_config = ConfigDict(extra="forbid")


class SpeakContext(BaseActionContext):
    """Context for SPEAK action."""

    message_type: Literal["response", "notification", "error"] = Field("response", description="Type of message")
    reply_to_message_id: Optional[str] = Field(None, description="Message being replied to")


class ToolContext(BaseActionContext):
    """Context for TOOL action."""

    tool_name: str = Field(..., description="Name of tool to execute")
    tool_version: Optional[str] = Field(None, description="Tool version")
    execution_timeout: Optional[float] = Field(30.0, description="Timeout in seconds")


class ObserveContext(BaseActionContext):
    """Context for OBSERVE action."""

    observation_type: Literal["channel", "user", "system"] = Field("channel", description="What to observe")
    observation_window: Optional[int] = Field(100, description="Number of messages to observe")


class MemorizeContext(BaseActionContext):
    """Context for MEMORIZE action."""

    memory_type: str = Field(..., description="Type of memory to store")
    memory_scope: Literal["task", "conversation", "global"] = Field("task", description="Scope of memory")
    retention_policy: Optional[str] = Field(None, description="How long to retain")


class RecallContext(BaseActionContext):
    """Context for RECALL action."""

    memory_type: str = Field(..., description="Type of memory to recall")
    memory_scope: Literal["task", "conversation", "global"] = Field("task", description="Scope to search")
    time_range: Optional[Dict[str, datetime]] = Field(None, description="Time range to search")


class ForgetContext(BaseActionContext):
    """Context for FORGET action."""

    memory_type: str = Field(..., description="Type of memory to forget")
    reason: str = Field(..., description="Reason for forgetting")
    permanent: bool = Field(False, description="Whether deletion is permanent")


class RejectContext(BaseActionContext):
    """Context for REJECT action."""

    rejection_reason: str = Field(..., description="Why request was rejected")
    rejection_category: Literal["ethical", "capability", "safety"] = Field(
        "safety", description="Category of rejection"
    )


class PonderContext(BaseActionContext):
    """Context for PONDER action."""

    questions: List[str] = Field(..., description="Questions to ponder")
    ponder_depth: int = Field(1, description="Depth of pondering")


class DeferContext(BaseActionContext):
    """Context for DEFER action."""

    deferral_reason: str = Field(..., description="Why deferring to authority")
    required_authority: str = Field("AUTHORITY", description="Required authority level")
    urgency: Literal["low", "medium", "high"] = Field("medium", description="Urgency level")


class TaskCompleteContext(BaseActionContext):
    """Context for TASK_COMPLETE action."""

    completion_status: Literal["success", "partial", "failure"] = Field("success", description="Completion status")
    completion_message: Optional[str] = Field(None, description="Completion message")
