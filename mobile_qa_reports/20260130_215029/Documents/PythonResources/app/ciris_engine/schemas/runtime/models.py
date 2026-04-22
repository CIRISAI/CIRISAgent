"""
Core models for CIRIS Trinity Architecture.

Task and Thought are the fundamental units of agent processing.
NO Dict[str, Any] - everything is typed.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.types import JSONDict

from .enums import TaskStatus, ThoughtStatus, ThoughtType


class ImageContent(BaseModel):
    """
    Image content for multimodal tasks.

    Supports both base64-encoded images and URLs for native vision processing.
    Used by adapters to attach images to tasks that flow through the pipeline
    to DMAs and ultimately to vision-capable LLMs.
    """

    source_type: Literal["base64", "url"] = Field(..., description="How image is stored")
    data: str = Field(..., description="Base64 data or URL")
    media_type: str = Field(default="image/jpeg", description="MIME type: image/jpeg, image/png, image/gif, image/webp")
    filename: Optional[str] = Field(default=None, description="Original filename if available")
    size_bytes: Optional[int] = Field(default=None, description="File size in bytes for tracking")

    model_config = ConfigDict(extra="forbid")

    def to_data_url(self) -> str:
        """Convert to data URL format for LLM APIs."""
        if self.source_type == "url":
            return self.data
        return f"data:{self.media_type};base64,{self.data}"


class TaskContext(BaseModel):
    """Typed context for tasks."""

    channel_id: Optional[str] = Field(None, description="Channel where task originated")
    user_id: Optional[str] = Field(None, description="User who created task")
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    parent_task_id: Optional[str] = Field(None, description="Parent task if nested")
    agent_occurrence_id: str = Field(default="default", description="Runtime occurrence ID that owns this task")

    model_config = ConfigDict(extra="forbid")


class TaskOutcome(BaseModel):
    """Typed outcome for completed tasks."""

    status: str = Field(..., description="Final status: success, partial, failure")
    summary: str = Field(..., description="Human-readable summary")
    actions_taken: List[str] = Field(default_factory=list, description="Actions performed")
    memories_created: List[str] = Field(default_factory=list, description="Memory node IDs created")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")

    model_config = ConfigDict(extra="forbid")


class ThoughtContext(BaseModel):
    """Typed context for thoughts."""

    task_id: str = Field(..., description="Parent task ID")
    channel_id: Optional[str] = Field(None, description="Channel where thought operates")
    round_number: int = Field(0, description="Processing round")
    depth: int = Field(0, description="Ponder depth (max 7)")
    parent_thought_id: Optional[str] = Field(None, description="Parent thought if pondering")
    correlation_id: str = Field(..., description="Correlation ID")
    agent_occurrence_id: str = Field(default="default", description="Runtime occurrence ID (inherited from task)")

    model_config = ConfigDict(extra="forbid")


class FinalAction(BaseModel):
    """Typed final action from thought processing."""

    action_type: str = Field(..., description="Action type chosen")
    action_params: JSONDict = Field(..., description="Action parameters (will be typed per action)")
    reasoning: str = Field(..., description="Why this action was chosen")

    model_config = ConfigDict(extra="forbid")


class Task(BaseModel):
    """Core task object - the unit of work."""

    task_id: str = Field(..., description="Unique task identifier")
    channel_id: str = Field(..., description="Channel where task originated/reports to")
    agent_occurrence_id: str = Field(default="default", description="Runtime occurrence ID that owns this task")
    description: str = Field(..., description="What needs to be done")
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    priority: int = Field(default=0, ge=0, le=10, description="Priority 0-10")
    created_at: str = Field(..., description="ISO8601 timestamp")
    updated_at: str = Field(..., description="ISO8601 timestamp")
    parent_task_id: Optional[str] = Field(None, description="Parent task for nested work")
    context: Optional[TaskContext] = Field(None, description="Task context")
    outcome: Optional[TaskOutcome] = Field(None, description="Outcome when complete")
    # Task signing fields
    signed_by: Optional[str] = Field(None, description="WA ID that signed this task")
    signature: Optional[str] = Field(None, description="Cryptographic signature of task")
    signed_at: Optional[str] = Field(None, description="ISO8601 timestamp when signed")
    # Updated info tracking
    updated_info_available: bool = Field(
        default=False, description="Flag indicating new observation arrived for this task"
    )
    updated_info_content: Optional[str] = Field(
        None, description="New observation content that arrived after task creation"
    )
    # Native multimodal support - images attached to task flow through to LLM
    images: List[ImageContent] = Field(
        default_factory=list, description="Images attached to this task for multimodal processing"
    )

    model_config = ConfigDict(extra="forbid")


class Thought(BaseModel):
    """Core thought object - a single reasoning step."""

    thought_id: str = Field(..., description="Unique thought identifier")
    source_task_id: str = Field(..., description="Task that generated this thought")
    agent_occurrence_id: str = Field(default="default", description="Runtime occurrence ID (inherited from task)")
    channel_id: Optional[str] = Field(None, description="Channel where thought operates")
    thought_type: ThoughtType = Field(default=ThoughtType.STANDARD)
    status: ThoughtStatus = Field(default=ThoughtStatus.PENDING)
    created_at: str = Field(..., description="ISO8601 timestamp")
    updated_at: str = Field(..., description="ISO8601 timestamp")
    round_number: int = Field(0, ge=0, description="Processing round")
    content: str = Field(..., description="Thought content/reasoning")
    context: Optional[ThoughtContext] = Field(None, description="Thought context")
    thought_depth: int = Field(0, ge=0, le=7, description="Pondering depth")
    ponder_notes: Optional[List[str]] = Field(None, description="Notes from pondering")
    parent_thought_id: Optional[str] = Field(None, description="Parent if pondering")
    final_action: Optional[FinalAction] = Field(None, description="Action chosen")
    # Native multimodal support - images inherited from source task
    images: List[ImageContent] = Field(
        default_factory=list, description="Images from source task for multimodal processing"
    )

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "ImageContent",
    "Task",
    "Thought",
    "TaskContext",
    "TaskOutcome",
    "ThoughtContext",
    "FinalAction",
]
