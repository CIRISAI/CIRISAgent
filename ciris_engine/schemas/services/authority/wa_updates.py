"""
WA certificate update schemas for CIRIS.

Provides type-safe structures for updating WA certificates with partial updates.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ciris_engine.schemas.services.authority_core import WARole
from ciris_engine.schemas.types import JSONDict


class WACertificateUpdate(BaseModel):
    """Request to update an existing WA certificate with partial updates."""

    # Identity fields (read-only, included for validation only)
    wa_id: Optional[str] = Field(None, description="WA ID to update (read-only)")

    # Updatable fields
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="Update display name")
    role: Optional[WARole] = Field(None, description="Update role (requires authority permission)")

    # Authentication updates
    password: Optional[str] = Field(None, description="New password (will be hashed)")
    api_key: Optional[str] = Field(None, description="New API key (will be hashed)")

    # OAuth updates
    oauth_provider: Optional[str] = Field(None, description="Update OAuth provider")
    oauth_external_id: Optional[str] = Field(None, description="Update OAuth external ID")

    # Veilid updates
    veilid_id: Optional[str] = Field(None, description="Update Veilid ID")

    # Trust chain updates (requires authority permission)
    parent_wa_id: Optional[str] = Field(None, description="Update parent WA ID")
    parent_signature: Optional[str] = Field(None, description="Update parent signature")

    # Scope updates
    scopes: Optional[List[str]] = Field(None, description="Replace all scopes")
    add_scopes: Optional[List[str]] = Field(None, description="Add new scopes")
    remove_scopes: Optional[List[str]] = Field(None, description="Remove existing scopes")

    # Adapter updates
    adapter_id: Optional[str] = Field(None, description="Update adapter ID")
    adapter_name: Optional[str] = Field(None, description="Update adapter name")
    adapter_metadata: Optional[Dict[str, str]] = Field(None, description="Update adapter metadata")

    @field_validator("scopes", "add_scopes", "remove_scopes")
    def validate_scope_lists(cls, v: Optional[List[str]]) -> Optional[List[str]]:
        """Ensure scope lists contain unique values."""
        if v is not None:
            return list(set(v))
        return v

    @field_validator("password", "api_key")
    def validate_credentials(cls, v: Optional[str]) -> Optional[str]:
        """Ensure credentials meet minimum requirements."""
        if v is not None and len(v) < 8:
            raise ValueError("Credentials must be at least 8 characters long")
        return v

    def has_updates(self) -> bool:
        """Check if any fields are set for update."""
        exclude_fields = {"wa_id"}  # Fields that don't count as updates
        for field_name, field_value in self.model_dump(exclude_unset=True).items():
            if field_name not in exclude_fields and field_value is not None:
                return True
        return False

    def get_update_fields(self) -> JSONDict:
        """Get only the fields that are being updated."""
        updates: JSONDict = {}
        exclude_fields = {"wa_id", "add_scopes", "remove_scopes"}

        for field_name, field_value in self.model_dump(exclude_unset=True).items():
            if field_name not in exclude_fields and field_value is not None:
                updates[field_name] = field_value

        return updates

    model_config = ConfigDict(extra="forbid")


class WACertificateUpdateResponse(BaseModel):
    """Response after updating a WA certificate."""

    success: bool = Field(..., description="Whether update succeeded")
    wa_id: str = Field(..., description="ID of updated certificate")
    updated_fields: List[str] = Field(..., description="List of fields that were updated")
    updated_at: datetime = Field(..., description="When certificate was updated")
    message: Optional[str] = Field(None, description="Additional information about the update")

    model_config = ConfigDict(extra="forbid")


class WABulkUpdate(BaseModel):
    """Request to update multiple WA certificates."""

    wa_ids: List[str] = Field(..., min_length=1, description="List of WA IDs to update")
    update: WACertificateUpdate = Field(..., description="Update to apply to all certificates")

    @field_validator("wa_ids")
    def validate_wa_ids(cls, v: List[str]) -> List[str]:
        """Ensure WA IDs are unique and valid."""
        unique_ids = list(set(v))
        if len(unique_ids) != len(v):
            raise ValueError("WA IDs must be unique")

        # Validate each ID matches expected pattern
        import re

        pattern = re.compile(r"^wa-\d{4}-\d{2}-\d{2}-[A-Z0-9]{6}$")
        for wa_id in unique_ids:
            if not pattern.match(wa_id):
                raise ValueError(f"Invalid WA ID format: {wa_id}")

        return unique_ids

    model_config = ConfigDict(extra="forbid")


class WABulkUpdateResponse(BaseModel):
    """Response after bulk updating WA certificates."""

    total_requested: int = Field(..., description="Number of certificates requested to update")
    total_updated: int = Field(..., description="Number of certificates successfully updated")
    failures: List[Dict[str, str]] = Field(
        default_factory=list, description="List of failures with wa_id and error message"
    )
    updated_at: datetime = Field(..., description="When bulk update was completed")

    model_config = ConfigDict(extra="forbid")


__all__ = ["WACertificateUpdate", "WACertificateUpdateResponse", "WABulkUpdate", "WABulkUpdateResponse"]
