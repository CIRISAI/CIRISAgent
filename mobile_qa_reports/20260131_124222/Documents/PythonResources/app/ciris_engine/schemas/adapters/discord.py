"""Discord adapter specific schemas."""

from datetime import datetime
from enum import Enum
from typing import List, Literal, Optional, Union

from pydantic import BaseModel, Field


class DiscordMessageData(BaseModel):
    """Schema for Discord message data."""

    id: str = Field(..., description="Message ID")
    author_id: str = Field(..., description="Author Discord ID")
    author_name: str = Field(..., description="Author display name")
    content: str = Field(..., description="Message content")
    timestamp: Optional[str] = Field(None, description="ISO timestamp")
    channel_id: str = Field(..., description="Channel ID")
    is_bot: bool = Field(default=False, description="Whether author is a bot")


class DiscordGuidanceData(BaseModel):
    """Schema for guidance request data."""

    deferral_id: str = Field(..., description="Deferral ID")
    task_id: str = Field(..., description="Task ID")
    thought_id: str = Field(..., description="Thought ID")
    reason: str = Field(..., description="Reason for deferral")
    defer_until: Optional[datetime] = Field(None, description="When to reconsider")
    context: dict[str, str] = Field(default_factory=dict, description="Additional context")


class DiscordApprovalData(BaseModel):
    """Schema for approval request data."""

    action: str = Field(..., description="Action requiring approval")
    task_id: Optional[str] = Field(None, description="Task ID")
    thought_id: Optional[str] = Field(None, description="Thought ID")
    requester_id: str = Field(..., description="Requester ID")
    action_name: Optional[str] = Field(None, description="Action type name")
    action_params: dict[str, Union[str, int, bool]] = Field(default_factory=dict, description="Action parameters")
    channel_id: Optional[str] = Field(None, description="Channel ID")


class DiscordToolResult(BaseModel):
    """Schema for tool execution results in Discord context."""

    success: bool = Field(..., description="Whether execution succeeded")
    output: Optional[str] = Field(None, description="Tool output")
    error: Optional[str] = Field(None, description="Error message if failed")
    execution_time: Optional[float] = Field(None, description="Execution time in ms")
    status: str = Field(..., description="Execution status")


class DiscordTaskData(BaseModel):
    """Schema for task status data."""

    id: str = Field(..., description="Task ID")
    status: Literal["pending", "in_progress", "completed", "failed", "deferred"] = Field(..., description="Task status")
    description: Optional[str] = Field(None, description="Task description")
    priority: Literal["low", "normal", "high", "critical"] = Field(default="normal", description="Task priority")
    progress: Optional[int] = Field(None, description="Progress percentage", ge=0, le=100)
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    subtasks: List[dict[str, Union[str, bool]]] = Field(default_factory=list, description="Subtask list")


class DiscordAuditData(BaseModel):
    """Schema for audit log entries."""

    action: str = Field(..., description="Action performed")
    actor: str = Field(..., description="Who performed the action")
    service: str = Field(..., description="Service that performed action")
    timestamp: Optional[datetime] = Field(None, description="When action occurred")
    context: dict[str, str] = Field(default_factory=dict, description="Additional context")
    success: Optional[bool] = Field(None, description="Whether action succeeded")


class ErrorSeverity(str, Enum):
    """Error severity levels."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class DiscordErrorInfo(BaseModel):
    """Schema for error information."""

    severity: ErrorSeverity = Field(..., description="Error severity")
    message: str = Field(..., description="Error message")
    error_type: str = Field(..., description="Exception type name")
    operation: Optional[str] = Field(None, description="Operation being performed")
    channel_id: Optional[str] = Field(None, description="Channel where error occurred")
    can_retry: bool = Field(default=True, description="Whether operation can be retried")
    suggested_fix: Optional[str] = Field(None, description="Suggested fix action")
    fallback_action: Optional[str] = Field(None, description="Fallback action to take")
    retry_after: Optional[float] = Field(None, description="Seconds to wait before retry")
    endpoint: Optional[str] = Field(None, description="API endpoint that failed")
    recovery_action: Optional[str] = Field(None, description="Recovery action for connection errors")


class DiscordChannelInfo(BaseModel):
    """Schema for Discord channel information."""

    channel_id: str = Field(..., description="Discord channel ID")
    channel_name: Optional[str] = Field(None, description="Channel display name")
    channel_type: Literal["discord"] = Field(default="discord", description="Channel type")
    display_name: Optional[str] = Field(None, description="Display name with prefix")
    is_active: bool = Field(default=True, description="Whether channel is active")
    created_at: Optional[str] = Field(None, description="ISO timestamp of creation")
    last_activity: Optional[str] = Field(None, description="ISO timestamp of last activity")
    message_count: int = Field(default=0, description="Number of messages")
    is_monitored: Optional[bool] = Field(None, description="Whether channel is monitored")
    is_home: Optional[bool] = Field(None, description="Whether channel is home channel")
    is_deferral: Optional[bool] = Field(None, description="Whether channel is deferral channel")
    guild_id: Optional[str] = Field(None, description="Guild ID")
    guild_name: Optional[str] = Field(None, description="Guild name")


class DiscordGuildInfo(BaseModel):
    """Schema for guild information."""

    id: str = Field(..., description="Guild ID")
    name: str = Field(..., description="Guild name")
