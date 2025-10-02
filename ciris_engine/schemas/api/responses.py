"""
Base response schemas for CIRIS API v1.

All API responses follow these patterns - NO Dict[str, Any]!
"""

from datetime import datetime, timezone
from typing import Any, Dict, Generic, Optional, TypeVar

from pydantic import BaseModel, Field, field_serializer

from ciris_engine.schemas.types import JSONDict
from ciris_engine.utils.serialization import serialize_timestamp

T = TypeVar("T")


class ResponseMetadata(BaseModel):
    """Metadata included with all responses."""

    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: Optional[str] = Field(None, description="Request tracking ID")
    duration_ms: Optional[int] = Field(None, description="Request processing duration")

    @field_serializer("timestamp")
    def serialize_ts(self, timestamp: datetime, _info: Any) -> Optional[str]:
        return serialize_timestamp(timestamp, _info)


class SuccessResponse(BaseModel, Generic[T]):
    """Standard success response wrapper."""

    data: T = Field(..., description="Response data")
    metadata: ResponseMetadata = Field(
        default_factory=lambda: ResponseMetadata(
            timestamp=datetime.now(timezone.utc), request_id=None, duration_ms=None
        )
    )


class ErrorDetail(BaseModel):
    """Detailed error information."""

    code: str = Field(..., description="Error code (e.g., RESOURCE_NOT_FOUND)")
    message: str = Field(..., description="Human-readable error message")
    details: Optional[JSONDict] = Field(None, description="Additional error context")


class ErrorResponse(BaseModel):
    """Standard error response."""

    error: ErrorDetail = Field(..., description="Error information")
    metadata: ResponseMetadata = Field(
        default_factory=lambda: ResponseMetadata(
            timestamp=datetime.now(timezone.utc), request_id=None, duration_ms=None
        )
    )


# Common error codes
class ErrorCode:
    """Standard error codes used across the API."""

    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    INVALID_REQUEST = "INVALID_REQUEST"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    RATE_LIMITED = "RATE_LIMITED"
    CONFLICT = "CONFLICT"
    VALIDATION_ERROR = "VALIDATION_ERROR"
