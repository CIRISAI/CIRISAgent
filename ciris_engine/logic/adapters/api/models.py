"""
Shared models for API responses.
"""

from datetime import datetime
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class StandardResponse(BaseModel):
    """Standard API response format."""

    success: bool = Field(..., description="Whether the request was successful")
    data: Optional[Any] = Field(None, description="Response data")
    message: Optional[str] = Field(None, description="Human-readable message")
    error: Optional[str] = Field(None, description="Error message if success is False")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Additional metadata")


class TokenData(BaseModel):
    """Token data for authenticated users."""

    username: str = Field(..., description="Username")
    email: Optional[str] = Field(None, description="User email")
    role: str = Field("OBSERVER", description="User role (OBSERVER, ADMIN, AUTHORITY, SYSTEM_ADMIN)")
    exp: Optional[datetime] = Field(None, description="Token expiration")
