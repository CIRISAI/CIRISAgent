"""
Schemas for Time Service.

Provides configuration and data structures for time operations.
"""

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class TimeServiceConfig(BaseModel):
    """Configuration for Time Service."""

    enable_mocking: bool = Field(default=True, description="Whether to allow time mocking for tests")
    default_timezone: str = Field(default="UTC", description="Default timezone (always UTC for CIRIS)")


class TimeSnapshot(BaseModel):
    """A snapshot of time information."""

    current_time: datetime = Field(..., description="Current time in UTC")
    current_iso: str = Field(..., description="Current time as ISO string")
    current_timestamp: float = Field(..., description="Current Unix timestamp")
    is_mocked: bool = Field(..., description="Whether time is mocked")
    mock_time: Optional[datetime] = Field(None, description="Mock time if set")


class LocalizedTimeData(BaseModel):
    """Localized time information for multiple timezones - flexible for future time sources."""

    utc: str = Field(..., description="UTC time in ISO format")
    london: str = Field(..., description="London time in ISO format")
    chicago: str = Field(..., description="Chicago time in ISO format")
    tokyo: str = Field(..., description="Tokyo time in ISO format")
    source_service: str = Field(default="TimeService", description="Time service that provided this data")
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc), description="When this data was generated"
    )


class TimeServiceStatus(BaseModel):
    """Extended status for Time Service."""

    service_name: str = Field(default="TimeService")
    is_healthy: bool = Field(..., description="Service health")
    uptime_seconds: float = Field(..., description="Service uptime")
    is_mocked: bool = Field(..., description="Whether time is mocked")
    calls_served: int = Field(default=0, description="Total time requests served")
