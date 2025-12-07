"""
Visibility and transparency schemas for CIRIS services.

These schemas support agent introspection and monitoring.
"""

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field

# CorrelationNode was removed in the cleanup
from ciris_engine.schemas.handlers.schemas import HandlerResult
from ciris_engine.schemas.runtime.models import Task, Thought
from ciris_engine.schemas.types import ConfigDict


class VisibilitySnapshot(BaseModel):
    """Snapshot of agent's reasoning state for transparency.

    This is focused on TRACES - showing the "why" of agent behavior.
    Service health, metrics, and correlations belong in telemetry/metrics services.
    """

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Current reasoning context
    current_task: Optional[Task] = Field(None, description="Current task being processed")
    active_thoughts: List[Thought] = Field(default_factory=list, description="Active thoughts in reasoning chain")
    recent_decisions: List[Thought] = Field(
        default_factory=list, description="Recent thoughts with their decisions (final_action)"
    )

    # Reasoning metrics
    reasoning_depth: int = Field(0, description="Current depth of reasoning chain")


class ThoughtStep(BaseModel):
    """Single step in the reasoning trace."""

    thought: Thought = Field(..., description="The full thought object")
    conscience_results: Optional[ConfigDict] = Field(
        None, description="Conscience evaluation results (non-terminal actions)"
    )
    handler_result: Optional[HandlerResult] = Field(None, description="Result from action handler")
    followup_thoughts: List[str] = Field(default_factory=list, description="IDs of followup thoughts generated")


class ReasoningTrace(BaseModel):
    """Complete reasoning trace for a task."""

    task: Task = Field(..., description="The task being traced")

    # Chain of thoughts
    thought_steps: List[ThoughtStep] = Field(default_factory=list, description="All thought steps in order")

    # Summary
    total_thoughts: int = Field(0, description="Total thoughts generated")
    actions_taken: List[str] = Field(default_factory=list, description="All actions taken")

    # Metadata
    processing_time_ms: float = Field(0.0, description="Total time taken")


class DecisionRecord(BaseModel):
    """Record of a decision made for a task."""

    decision_id: str = Field(..., description="Unique decision ID")
    timestamp: datetime = Field(..., description="When decision was made")
    thought_id: str = Field(..., description="Thought that made the decision")

    # Decision details
    action_type: str = Field(..., description="Type of action decided")
    parameters: ConfigDict = Field(default_factory=dict, description="Parameters for the action")
    rationale: str = Field(..., description="Reasoning for the decision")
    alternatives_considered: List[str] = Field(default_factory=list, description="Other options considered")

    # Outcome
    executed: bool = Field(False, description="Whether decision was executed")
    result: Optional[str] = Field(None, description="Result of execution")
    success: bool = Field(False, description="Whether execution succeeded")


class TaskDecisionHistory(BaseModel):
    """Complete decision history for a task."""

    task_id: str = Field(..., description="Task ID")
    task_description: str = Field(..., description="What the task was")
    created_at: datetime = Field(..., description="When task was created")

    # Decision records
    decisions: List[DecisionRecord] = Field(default_factory=list, description="All decisions made")
    total_decisions: int = Field(0, description="Total number of decisions")
    successful_decisions: int = Field(0, description="Number of successful decisions")

    # Summary
    final_status: str = Field("unknown", description="Final task status")
    completion_time: Optional[datetime] = Field(None, description="When task completed")
