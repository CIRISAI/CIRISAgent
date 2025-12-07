"""
State-specific processing results for each AgentState.

These replace Dict[str, Any] returns from processors with type-safe schemas.
Each state has its own result type with state-specific fields.
"""

from typing import List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field


class WakeupResult(BaseModel):
    """Result from WAKEUP state processing."""

    thoughts_processed: int = Field(0)
    wakeup_complete: bool = Field(False)
    errors: int = Field(0)
    duration_seconds: float = Field(...)


class WorkResult(BaseModel):
    """Result from WORK state processing."""

    tasks_processed: int = Field(0)
    thoughts_processed: int = Field(0)
    errors: int = Field(0)
    duration_seconds: float = Field(...)


class PlayResult(BaseModel):
    """Result from PLAY state processing."""

    thoughts_processed: int = Field(0)
    errors: int = Field(0)
    duration_seconds: float = Field(...)


class SolitudeResult(BaseModel):
    """Result from SOLITUDE state processing."""

    thoughts_processed: int = Field(0)
    errors: int = Field(0)
    duration_seconds: float = Field(...)
    should_exit_solitude: bool = Field(False, description="Whether to exit solitude state")
    exit_reason: str = Field("Unknown reason", description="Reason for exiting solitude")


class DreamResult(BaseModel):
    """Result from DREAM state processing."""

    thoughts_processed: int = Field(0)
    errors: int = Field(0)
    duration_seconds: float = Field(...)


class ShutdownResult(BaseModel):
    """Result from SHUTDOWN state processing.

    This schema replaces all Dict[str, Any] returns from shutdown_processor.py
    with a fully-typed result structure.
    """

    # Core fields (used by process() method)
    tasks_cleaned: int = Field(0, description="Number of tasks cleaned up")
    shutdown_ready: bool = Field(False, description="Whether system is ready to shutdown")
    errors: int = Field(0, description="Number of errors encountered")
    duration_seconds: float = Field(..., description="Processing duration in seconds")

    # Status fields (used by _process_shutdown() internal method)
    status: Optional[Literal["completed", "rejected", "error", "in_progress", "shutdown_complete"]] = Field(
        None, description="Detailed status of shutdown processing"
    )
    action: Optional[str] = Field(
        None, description="Action taken: shutdown_accepted, shutdown_rejected, shutdown_error"
    )
    message: str = Field("", description="Human-readable message about shutdown state")
    reason: Optional[str] = Field(None, description="Reason for rejection or error")

    # Task tracking fields
    task_status: Optional[str] = Field(None, description="Status of shutdown task (PENDING, ACTIVE, COMPLETED, FAILED)")
    thoughts: Optional[List[Tuple[str, str]]] = Field(
        None, description="List of (thought_id, status) tuples for debugging"
    )


# Discriminated union of all possible results
ProcessingResult = Union[WakeupResult, WorkResult, PlayResult, SolitudeResult, DreamResult, ShutdownResult]


__all__ = [
    "WakeupResult",
    "WorkResult",
    "PlayResult",
    "SolitudeResult",
    "DreamResult",
    "ShutdownResult",
    "ProcessingResult",
]
