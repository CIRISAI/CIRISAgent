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

    model_config = ConfigDict(extra="forbid")  # No arbitrary fields allowed
