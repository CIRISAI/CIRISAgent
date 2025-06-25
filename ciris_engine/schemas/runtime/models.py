"""
Core models for CIRIS Trinity Architecture.

Task and Thought are the fundamental units of agent processing.
NO Dict[str, Any] - everything is typed.
"""
from typing import List, Optional, Any
from pydantic import BaseModel, Field

from .enums import TaskStatus, ThoughtStatus, ThoughtType
from pydantic import Field

class TaskContext(BaseModel):
    """Typed context for tasks."""
    channel_id: Optional[str] = Field(None, description="Channel where task originated")
    user_id: Optional[str] = Field(None, description="User who created task")
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    parent_task_id: Optional[str] = Field(None, description="Parent task if nested")
    
    class Config:
        extra = "forbid"

class TaskOutcome(BaseModel):
    """Typed outcome for completed tasks."""
    status: str = Field(..., description="Final status: success, partial, failure")
    summary: str = Field(..., description="Human-readable summary")
    actions_taken: List[str] = Field(default_factory=list, description="Actions performed")
    memories_created: List[str] = Field(default_factory=list, description="Memory node IDs created")
    errors: List[str] = Field(default_factory=list, description="Errors encountered")
    
    class Config:
        extra = "forbid"

class ThoughtContext(BaseModel):
    """Typed context for thoughts."""
    task_id: str = Field(..., description="Parent task ID")
    round_number: int = Field(0, description="Processing round")
    depth: int = Field(0, description="Ponder depth (max 7)")
    parent_thought_id: Optional[str] = Field(None, description="Parent thought if pondering")
    correlation_id: str = Field(..., description="Correlation ID")
    
    class Config:
        extra = "forbid"

class FinalAction(BaseModel):
    """Typed final action from thought processing."""
    action_type: str = Field(..., description="Action type chosen")
    action_params: dict = Field(..., description="Action parameters (will be typed per action)")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in action")
    reasoning: str = Field(..., description="Why this action was chosen")
    
    class Config:
        extra = "forbid"

class Task(BaseModel):
    """Core task object - the unit of work."""
    task_id: str = Field(..., description="Unique task identifier")
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
    
    class Config:
        extra = "forbid"

class Thought(BaseModel):
    """Core thought object - a single reasoning step."""
    thought_id: str = Field(..., description="Unique thought identifier")
    source_task_id: str = Field(..., description="Task that generated this thought")
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
    
    class Config:
        extra = "forbid"

__all__ = [
    "Task",
    "Thought", 
    "TaskContext",
    "TaskOutcome",
    "ThoughtContext",
    "FinalAction",
]