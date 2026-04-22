"""
Cognitive state schemas for contract-driven architecture.

Typed states for each of the 6 cognitive phases.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class WakeupState(BaseModel):
    """State during WAKEUP phase."""

    identity_confirmed: bool = Field(False, description="Identity verification status")
    integrity_validated: bool = Field(False, description="System integrity check status")
    resilience_evaluated: bool = Field(False, description="Resilience assessment status")
    incompleteness_accepted: bool = Field(False, description="Incompleteness acknowledgment status")
    gratitude_expressed: bool = Field(False, description="Gratitude expression status")

    model_config = ConfigDict(extra="forbid")


class WorkState(BaseModel):
    """State during WORK phase."""

    active_tasks: int = Field(0, ge=0, description="Number of active tasks")
    completed_tasks: int = Field(0, ge=0, description="Number of completed tasks")
    pending_thoughts: int = Field(0, ge=0, description="Number of pending thoughts")
    last_activity: datetime = Field(..., description="Timestamp of last activity")

    model_config = ConfigDict(extra="forbid")


class PlayState(BaseModel):
    """State during PLAY phase."""

    creativity_level: float = Field(0.0, ge=0.0, le=1.0, description="Creativity level (0.0 to 1.0)")
    experimental_approaches: List[str] = Field(default_factory=list, description="List of experimental approaches")
    novel_discoveries: int = Field(0, ge=0, description="Number of novel discoveries")

    model_config = ConfigDict(extra="forbid")


class SolitudeState(BaseModel):
    """State during SOLITUDE phase."""

    reflection_cycles: int = Field(0, ge=0, description="Number of reflection cycles completed")
    maintenance_tasks_completed: int = Field(0, ge=0, description="Number of maintenance tasks completed")
    patterns_identified: List[str] = Field(default_factory=list, description="Patterns identified during reflection")

    model_config = ConfigDict(extra="forbid")


class DreamState(BaseModel):
    """State during DREAM phase."""

    memory_consolidation_progress: float = Field(
        0.0, ge=0.0, le=1.0, description="Memory consolidation progress (0.0 to 1.0)"
    )
    patterns_analyzed: int = Field(0, ge=0, description="Number of patterns analyzed")
    future_plans_generated: int = Field(0, ge=0, description="Number of future plans generated")
    benchmark_results: Optional[Dict[str, float]] = Field(None, description="Performance benchmark results")

    model_config = ConfigDict(extra="forbid")


class ShutdownState(BaseModel):
    """State during SHUTDOWN phase."""

    shutdown_requested: bool = Field(False, description="Whether shutdown was requested")
    shutdown_accepted: bool = Field(False, description="Whether shutdown was accepted")
    cleanup_completed: bool = Field(False, description="Whether cleanup is completed")
    final_message: Optional[str] = Field(None, description="Final message before shutdown")

    model_config = ConfigDict(extra="forbid")
