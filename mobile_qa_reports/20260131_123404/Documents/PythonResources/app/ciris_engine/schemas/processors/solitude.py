"""
Schemas for solitude processor operations.

These replace all Dict[str, Any] usage in logic/processors/states/solitude_processor.py.
"""

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ReflectionData(BaseModel):
    """Tracking data for reflection activities."""

    tasks_reviewed: int = Field(0, description="Number of tasks reviewed")
    thoughts_reviewed: int = Field(0, description="Number of thoughts reviewed")
    memories_consolidated: int = Field(0, description="Number of memories consolidated")
    cleanup_performed: bool = Field(False, description="Whether cleanup was performed")


class SolitudeProcessingResult(BaseModel):
    """Result from a solitude processing round."""

    round_number: int = Field(..., description="Processing round number")
    critical_tasks_found: int = Field(0, description="Number of critical tasks found")
    maintenance_performed: bool = Field(False, description="Whether maintenance was performed")
    should_exit_solitude: bool = Field(False, description="Whether to exit solitude state")
    reflection_summary: Optional["ReflectionResult"] = Field(None)
    maintenance_summary: Optional["MaintenanceResult"] = Field(None, description="Maintenance results if performed")
    exit_reason: Optional[str] = Field(None, description="Reason for exiting solitude")
    error: Optional[str] = Field(None, description="Error message if processing failed")


class MaintenanceResult(BaseModel):
    """Result from maintenance operations."""

    old_completed_tasks_cleaned: int = Field(0, description="Number of old completed tasks cleaned")
    old_thoughts_cleaned: int = Field(0, description="Number of old thoughts cleaned")
    database_optimized: bool = Field(False, description="Whether database was optimized")
    errors: List[str] = Field(default_factory=list, description="Any errors during maintenance")


class TaskTypePattern(BaseModel):
    """Identified pattern in task types."""

    pattern: str = Field(..., description="Pattern type")
    value: str = Field(..., description="Pattern value")
    count: int = Field(..., description="Occurrence count")


class ReflectionResult(BaseModel):
    """Result from reflection and learning activities."""

    recent_tasks_analyzed: int = Field(0, description="Number of recent tasks analyzed")
    patterns_identified: List[TaskTypePattern] = Field(default_factory=list, description="Identified patterns")
    memories_consolidated: int = Field(0, description="Number of memories consolidated")
    insights: List[str] = Field(default_factory=list, description="Insights from reflection")


class ExitConditions(BaseModel):
    """Conditions for exiting solitude state."""

    should_exit: bool = Field(False, description="Whether to exit solitude")
    reason: Optional[str] = Field(None, description="Reason for exit decision")
    pending_tasks: int = Field(0, description="Number of pending tasks")
    time_in_solitude: Optional[float] = Field(None, description="Time spent in solitude (seconds)")
    resource_usage: Optional[float] = Field(None, description="Current resource usage percentage")


class TaskTypeStats(BaseModel):
    """Statistics about task types."""

    task_types: Dict[str, int] = Field(default_factory=dict, description="Count by task type")
    most_common_type: Optional[str] = Field(None, description="Most common task type")
    most_common_count: int = Field(0, description="Count of most common type")


# Fix forward references
SolitudeProcessingResult.model_rebuild()
