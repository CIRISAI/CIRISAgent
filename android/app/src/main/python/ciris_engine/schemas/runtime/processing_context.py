"""
Processing context schemas for CIRIS.

Provides context objects for thought and task processing that carry
system state and metadata through the processing pipeline.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .models import TaskContext
from .system_context import SystemSnapshot, UserProfile


class ProcessingThoughtContext(BaseModel):
    """Context passed through thought processing pipeline.

    This is different from ThoughtContext which represents a thought entity.
    This context carries processing metadata and system state.
    """

    # System state snapshot
    system_snapshot: SystemSnapshot = Field(..., description="Current system state")

    # User and profile data
    user_profiles: Dict[str, UserProfile] = Field(
        default_factory=dict, description="User profile data keyed by user_id"
    )

    # Task history
    task_history: List[Any] = Field(default_factory=list, description="Recent task history")

    # Identity context
    identity_context: Optional[str] = Field(None, description="Agent identity context")

    # Initial task context
    initial_task_context: Optional[TaskContext] = Field(None, description="Original task context")

    model_config = ConfigDict(extra="allow")  # Allow additional fields for flexibility


__all__ = ["ProcessingThoughtContext"]
