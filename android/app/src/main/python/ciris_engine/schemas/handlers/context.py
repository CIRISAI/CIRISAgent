"""
Handler context schemas for CIRIS.

Provides typed contexts for all handler operations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class HandlerData(BaseModel):
    """Base class for handler-specific data."""

    handler_name: str = Field(..., description="Name of the handler")


class SpeakHandlerData(HandlerData):
    """Data specific to SPEAK handler."""

    message_type: str = Field("response", description="Type of message")
    reply_to_message_id: Optional[str] = Field(None, description="Message being replied to")
    formatting_hints: Optional[Dict[str, str]] = Field(None, description="Formatting hints")


class ToolHandlerData(HandlerData):
    """Data specific to TOOL handler."""

    tool_timeout: float = Field(30.0, description="Tool execution timeout")
    requires_confirmation: bool = Field(False, description="Whether user confirmation needed")
    sandbox_mode: bool = Field(True, description="Whether to run in sandbox")


class MemoryHandlerData(HandlerData):
    """Data specific to memory handlers (MEMORIZE, RECALL, FORGET)."""

    operation_type: str = Field(..., description="memorize, recall, or forget")
    allow_duplicates: bool = Field(False, description="Whether to allow duplicate memories")
    cascade_delete: bool = Field(False, description="Whether to cascade delete related memories")


class HandlerRequest(BaseModel):
    """Request passed to all handlers - fully typed."""

    task_id: str = Field(..., description="ID of the task being handled")
    thought_id: str = Field(..., description="ID of the thought being processed")
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    channel_id: Optional[str] = Field(None, description="Channel ID if applicable")
    user_id: Optional[str] = Field(None, description="User ID if applicable")
    trace_context: Dict[str, str] = Field(default_factory=dict, description="Distributed tracing context")

    # Handler-specific context - typed based on handler
    handler_data: Optional[Union[SpeakHandlerData, ToolHandlerData, MemoryHandlerData, HandlerData]] = Field(
        None, description="Handler-specific typed data"
    )


class ActionContextParams(BaseModel):
    """Base class for action parameters in audit context."""

    action_type: str = Field(..., description="Type of action")


class SpeakActionParams(ActionContextParams):
    """Parameters for SPEAK action."""

    message: str = Field(..., description="Message content")
    channel_id: str = Field(..., description="Target channel")
    message_type: str = Field("response", description="Type of message")


class ToolActionParams(ActionContextParams):
    """Parameters for TOOL action."""

    tool_name: str = Field(..., description="Tool to execute")
    tool_args: JSONDict = Field(..., description="Tool arguments")


class MemoryActionParams(ActionContextParams):
    """Parameters for memory actions."""

    operation: str = Field(..., description="memorize, recall, or forget")
    node_id: Optional[str] = Field(None, description="Node ID for recall/forget")
    query: Optional[str] = Field(None, description="Query for recall")
    content: Optional[JSONDict] = Field(None, description="Content for memorize")


class ActionContext(BaseModel):
    """Context for an action being audited - fully typed."""

    action_type: str = Field(..., description="Type of action performed")
    action_params: Union[SpeakActionParams, ToolActionParams, MemoryActionParams, ActionContextParams] = Field(
        ..., description="Typed action parameters"
    )
    initiated_by: str = Field(..., description="Who initiated the action")
    reason: Optional[str] = Field(None, description="Reason for the action")

    # Audit trail
    task_id: str = Field(..., description="Associated task ID")
    thought_id: str = Field(..., description="Associated thought ID")
    correlation_id: str = Field(..., description="Correlation ID")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


__all__ = [
    "HandlerData",
    "SpeakHandlerData",
    "ToolHandlerData",
    "MemoryHandlerData",
    "HandlerRequest",
    "ActionContextParams",
    "SpeakActionParams",
    "ToolActionParams",
    "MemoryActionParams",
    "ActionContext",
]
