"""Initialization service schemas."""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class InitializationStatus(BaseModel):
    """Status of system initialization."""

    complete: bool = Field(..., description="Whether initialization is complete")
    start_time: Optional[datetime] = Field(None, description="When initialization started")
    duration_seconds: Optional[float] = Field(None, description="How long initialization took")
    completed_steps: List[str] = Field(default_factory=list, description="Steps that completed successfully")
    phase_status: Dict[str, str] = Field(default_factory=dict, description="Status of each phase")
    error: Optional[str] = Field(None, description="Error message if initialization failed")
    total_steps: int = Field(0, description="Total number of steps registered")

    model_config = ConfigDict()

    @field_serializer("start_time")
    def serialize_datetime(self, dt: Optional[datetime]) -> Optional[str]:
        return dt.isoformat() if dt else None


class InitializationVerification(BaseModel):
    """Results of initialization verification."""

    system_initialized: bool = Field(..., description="Whether system is fully initialized")
    no_errors: bool = Field(..., description="Whether there were no errors")
    all_steps_completed: bool = Field(..., description="Whether all steps completed")
    phase_results: Dict[str, bool] = Field(default_factory=dict, description="Results for each phase")
