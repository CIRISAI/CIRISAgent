"""
Runtime API schemas for CIRIS.

Provides types needed for API authentication and user management.
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.services.authority_core import WARole


class APIRole(str, Enum):
    """API role levels (separate from UserRole for compatibility)."""

    OBSERVER = "OBSERVER"
    ADMIN = "ADMIN"
    AUTHORITY = "AUTHORITY"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    SERVICE_ACCOUNT = "SERVICE_ACCOUNT"  # For service-to-service authentication

    @property
    def level(self) -> int:
        """Numeric privilege level for comparison."""
        return {
            "OBSERVER": 1,
            "ADMIN": 2,
            "AUTHORITY": 3,
            "SYSTEM_ADMIN": 4,
            "SERVICE_ACCOUNT": 2,  # Same level as ADMIN for shutdown operations
        }[self.value]


class APIUserInfo(BaseModel):
    """User information from API authentication."""

    user_id: str = Field(..., description="Unique user identifier")
    username: str = Field(..., description="User's display name")
    role: APIRole = Field(..., description="User's API role")
    wa_id: Optional[str] = Field(None, description="Associated WA ID if any")
    wa_role: Optional[WARole] = Field(None, description="Associated WA role if any")
    email: Optional[str] = Field(None, description="User email if available")
    auth_type: str = Field(..., description="Authentication type: password, oauth, api_key")
    permissions: List[str] = Field(default_factory=list, description="List of granted permissions")


class PaginatedResponse(BaseModel):
    """Generic paginated response for list endpoints."""

    items: List[BaseModel] = Field(..., description="List of items in current page")
    total: int = Field(..., description="Total number of items")
    page: int = Field(..., description="Current page number (1-based)")
    page_size: int = Field(..., description="Number of items per page")
    pages: int = Field(..., description="Total number of pages")

    model_config = ConfigDict(arbitrary_types_allowed=True)
