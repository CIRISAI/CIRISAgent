"""
Service metadata schemas for contract-driven architecture.

Replaces all Dict[str, Any] metadata in service method calls.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ServiceMetadata(BaseModel):
    """Typed metadata for all service method calls."""

    service_name: str = Field(..., description="Name of the calling service")
    method_name: str = Field(..., description="Method being called")
    correlation_id: UUID = Field(..., description="Correlation ID for tracing")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), description="Call timestamp")
    caller_id: Optional[str] = Field(None, description="ID of the caller")
    trace_id: Optional[str] = Field(None, description="Distributed trace ID")
    span_id: Optional[str] = Field(None, description="Span ID within trace")

    # Infrastructure-specific fields
    category: Optional[str] = Field(None, description="Service category (e.g., 'infrastructure')")
    critical: Optional[bool] = Field(None, description="Whether the service is critical for system operation")

    # LLM service fields
    model: Optional[str] = Field(None, description="LLM model name")
    instructor_mode: Optional[str] = Field(None, description="Instructor mode (JSON, TOOLS, etc.)")
    timeout_seconds: Optional[int] = Field(None, description="Operation timeout in seconds")
    max_retries: Optional[int] = Field(None, description="Maximum retry attempts")
    circuit_breaker_state: Optional[str] = Field(None, description="Circuit breaker state")

    # Tool service fields
    adapter: Optional[str] = Field(None, description="Adapter name providing tools")
    tool_count: Optional[int] = Field(None, description="Number of tools available")

    # Scheduler service fields
    active_tasks: Optional[int] = Field(None, description="Number of active scheduled tasks")
    total_tasks: Optional[int] = Field(None, description="Total tasks scheduled")
    features: Optional[list[str]] = Field(None, description="List of supported features")
    cron_support: Optional[bool] = Field(None, description="Whether cron scheduling is available")
    description: Optional[str] = Field(None, description="Service description")

    # Runtime control service fields
    processors_active: Optional[int] = Field(None, description="Number of active processors")
    adapters_loaded: Optional[int] = Field(None, description="Number of loaded adapters")
    stepping_enabled: Optional[bool] = Field(None, description="Whether pipeline stepping is enabled")
    queue_depth: Optional[int] = Field(None, description="Current processor queue depth")

    model_config = ConfigDict(extra="forbid")  # No arbitrary fields allowed
