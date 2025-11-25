"""
Wise Authority service schemas.

Provides typed schemas in WA service operations.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class PermissionEntry(BaseModel):
    """A single permission entry for a WA."""

    action: str = Field(..., description="The action permitted")
    resource: Optional[str] = Field(None, description="Resource this permission applies to (* for all)")
    granted_at: str = Field(..., description="ISO timestamp when granted")
    granted_by: str = Field(..., description="Who granted this permission")


class ApprovalRequestContext(BaseModel):
    """Context for approval requests."""

    wa_id: str = Field(..., description="WA requesting approval")
    resource: Optional[str] = Field(None, description="Resource being accessed")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional context")


class AuthenticationResult(BaseModel):
    """Result of WA authentication."""

    authenticated: bool = Field(..., description="Whether authentication succeeded")
    wa_id: str = Field(..., description="Wise Authority identifier")
    name: str = Field(..., description="WA name")
    role: str = Field(..., description="WA role")
    expires_at: datetime = Field(..., description="Token expiration time")
    permissions: List[str] = Field(default_factory=list, description="Granted permissions")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")


class WAUpdate(BaseModel):
    """Updates to apply to a WA certificate."""

    name: Optional[str] = Field(None, description="New name")
    role: Optional[str] = Field(None, description="New role")
    permissions: Optional[List[str]] = Field(None, description="New permissions")
    metadata: Optional[Dict[str, str]] = Field(None, description="Metadata updates")
    is_active: Optional[bool] = Field(None, description="Active status")


class TokenVerification(BaseModel):
    """Result of token verification."""

    valid: bool = Field(..., description="Whether token is valid")
    wa_id: Optional[str] = Field(None, description="WA ID if valid")
    name: Optional[str] = Field(None, description="WA name if valid")
    role: Optional[str] = Field(None, description="WA role if valid")
    expires_at: Optional[datetime] = Field(None, description="Expiration if valid")
    error: Optional[str] = Field(None, description="Error message if invalid")


class PendingDeferral(BaseModel):
    """A deferral awaiting WA review."""

    deferral_id: str = Field(..., description="Unique deferral identifier")
    created_at: datetime = Field(..., description="When deferral was created")
    deferred_by: str = Field(..., description="Agent that deferred")

    # Deferral details
    task_id: str = Field(..., description="Associated task ID")
    thought_id: str = Field(..., description="Associated thought ID")
    reason: str = Field(..., description="Reason for deferral")

    # Context
    channel_id: Optional[str] = Field(None, description="Channel where deferred")
    user_id: Optional[str] = Field(None, description="User involved")
    priority: str = Field("normal", description="Deferral priority")

    # WA assignment
    assigned_wa_id: Optional[str] = Field(None, description="Assigned WA if any")
    requires_role: Optional[str] = Field(None, description="Required WA role")

    # Resolution
    status: str = Field("pending", description="Current status")
    resolution: Optional[str] = Field(None, description="Resolution if completed")
    resolved_at: Optional[datetime] = Field(None, description="Resolution time")

    # UI compatibility fields
    question: Optional[str] = Field(None, description="Question/description for UI display")
    context: JSONDict = Field(default_factory=dict, description="Additional context for UI")
    timeout_at: Optional[str] = Field(None, description="When deferral times out (ISO format)")


class DeferralResolution(BaseModel):
    """Resolution of a deferral by WA."""

    deferral_id: str = Field(..., description="Deferral being resolved")
    wa_id: str = Field(..., description="WA resolving it")
    resolution: str = Field(..., description="approve, reject, or modify")

    # Guidance
    guidance: Optional[str] = Field(None, description="WA guidance")
    modified_action: Optional[str] = Field(None, description="Modified action if changed")
    modified_parameters: Optional[Dict[str, Union[str, int, float, bool, List[Any]]]] = Field(
        None, description="Modified parameters"
    )

    # Constraints
    new_constraints: List[str] = Field(default_factory=list, description="New constraints added")
    removed_constraints: List[str] = Field(default_factory=list, description="Constraints removed")

    # Metadata
    resolution_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolution_metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")


class WAResource(BaseModel):
    """Resource accessible to a WA."""

    resource_id: str = Field(..., description="Resource identifier")
    resource_type: str = Field(..., description="Type of resource")
    resource_name: str = Field(..., description="Resource name")

    # Access control
    permissions: List[str] = Field(..., description="Permissions on resource")
    granted_at: datetime = Field(..., description="When access was granted")
    granted_by: str = Field(..., description="Who granted access")

    # Constraints
    expires_at: Optional[datetime] = Field(None, description="Access expiration")
    usage_limit: Optional[int] = Field(None, description="Usage limit if any")
    usage_count: int = Field(0, description="Current usage count")

    # Metadata
    resource_metadata: Dict[str, str] = Field(default_factory=dict, description="Resource metadata")


class OAuthConfig(BaseModel):
    """OAuth provider configuration."""

    provider: str = Field(..., description="OAuth provider name")
    enabled: bool = Field(True, description="Whether provider is enabled")

    # OAuth settings
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret")
    redirect_uri: str = Field(..., description="OAuth redirect URI")

    # Scopes and permissions
    scopes: List[str] = Field(default_factory=list, description="OAuth scopes")

    # Provider-specific settings
    authorization_url: Optional[str] = Field(None, description="Auth URL if custom")
    token_url: Optional[str] = Field(None, description="Token URL if custom")
    userinfo_url: Optional[str] = Field(None, description="User info URL if custom")

    # Mapping
    id_field: str = Field("id", description="Field for user ID")
    name_field: str = Field("name", description="Field for user name")
    email_field: str = Field("email", description="Field for user email")
