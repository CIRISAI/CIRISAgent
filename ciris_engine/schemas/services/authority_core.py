"""
Wise Authority schemas for CIRIS.

Provides type-safe structures for WA authentication and authorization.
"""

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WARole(str, Enum):
    """WA role levels."""

    ROOT = "root"
    AUTHORITY = "authority"
    OBSERVER = "observer"


class TokenType(str, Enum):
    """Token type classifications."""

    STANDARD = "standard"
    CHANNEL = "channel"
    OAUTH = "oauth"


class JWTSubType(str, Enum):
    """JWT sub_type values."""

    ANON = "anon"
    OAUTH = "oauth"
    USER = "user"
    AUTHORITY = "authority"


class OAuthIdentityLink(BaseModel):
    """Linked OAuth identity for a Wise Authority."""

    provider: str = Field(..., description="OAuth provider identifier (e.g., google, discord)")
    external_id: str = Field(..., description="Provider-scoped user identifier")
    account_name: Optional[str] = Field(None, description="Display name supplied by the provider")
    linked_at: Optional[datetime] = Field(None, description="Timestamp when the link was created")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Provider-specific metadata")
    is_primary: bool = Field(False, description="Whether this identity is the primary OAuth mapping")


class WACertificate(BaseModel):
    """Wise Authority certificate record."""

    wa_id: str = Field(..., pattern="^wa-\\d{4}-\\d{2}-\\d{2}-[A-Z0-9]{6}$")
    name: str = Field(..., min_length=1, max_length=255)
    role: WARole

    # Cryptographic identity
    pubkey: str = Field(..., description="Base64url encoded Ed25519 public key")
    jwt_kid: str = Field(..., description="JWT key identifier")

    # Authentication methods
    password_hash: Optional[str] = None
    api_key_hash: Optional[str] = None

    # OAuth integration
    oauth_provider: Optional[str] = None
    oauth_external_id: Optional[str] = None
    oauth_links: List[OAuthIdentityLink] = Field(default_factory=list, description="Additional linked OAuth identities")
    auto_minted: bool = Field(default=False, description="True if auto-created via OAuth")

    # Veilid integration
    veilid_id: Optional[str] = None

    # Trust chain
    parent_wa_id: Optional[str] = None
    parent_signature: Optional[str] = None

    # Scopes and permissions
    scopes_json: str = Field(..., description="JSON array of scope strings")
    custom_permissions_json: Optional[str] = Field(None, description="JSON array of custom permission strings")

    # Adapter-based observers
    adapter_id: Optional[str] = None
    adapter_name: Optional[str] = None
    adapter_metadata_json: Optional[str] = None

    # Timestamps
    created_at: datetime
    last_auth: Optional[datetime] = None

    @field_validator("scopes_json")
    def validate_scopes_json(cls, v: str) -> str:
        """Ensure scopes_json is valid JSON."""
        import json

        try:
            json.loads(v)
        except json.JSONDecodeError:
            raise ValueError("scopes_json must be valid JSON")
        return v

    @field_validator("custom_permissions_json")
    def validate_custom_permissions_json(cls, v: Optional[str]) -> Optional[str]:
        """Ensure custom_permissions_json is valid JSON if provided."""
        if v is None:
            return v
        import json

        try:
            json.loads(v)
        except json.JSONDecodeError:
            raise ValueError("custom_permissions_json must be valid JSON")
        return v

    @property
    def scopes(self) -> List[str]:
        """Get scopes as a list."""
        import json

        return json.loads(self.scopes_json) if self.scopes_json else []

    @property
    def custom_permissions(self) -> List[str]:
        """Get custom permissions as a list."""
        import json

        if not self.custom_permissions_json:
            return []
        try:
            permissions = json.loads(self.custom_permissions_json)
            # Ensure we return a list of strings
            if isinstance(permissions, list):
                assert isinstance(permissions, list)  # Help type checker
                return [str(p) for p in permissions]
            return []
        except json.JSONDecodeError:
            return []

    def has_scope(self, scope: str) -> bool:
        """Check if certificate has a specific scope."""
        return scope in self.scopes

    model_config = ConfigDict(extra="forbid")


class ChannelIdentity(BaseModel):
    """Identity context from channel/adapter."""

    adapter_type: str
    adapter_instance_id: str
    external_user_id: str
    external_username: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class AuthorizationContext(BaseModel):
    """Context for authorization decisions."""

    wa_id: str
    role: WARole
    token_type: TokenType
    sub_type: JWTSubType
    scopes: List[str]
    action: Optional[str] = None
    resource: Optional[str] = None
    channel_id: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class WACertificateRequest(BaseModel):
    """Request to create a new WA certificate."""

    name: str = Field(..., min_length=1, max_length=255)
    role: WARole = Field(default=WARole.OBSERVER)
    parent_wa_id: Optional[str] = None
    parent_signature: Optional[str] = None
    password: Optional[str] = None
    scopes: List[str] = Field(default_factory=list)
    oauth_provider: Optional[str] = None
    oauth_external_id: Optional[str] = None
    oauth_links: List[OAuthIdentityLink] = Field(default_factory=list)
    adapter_id: Optional[str] = None
    adapter_name: Optional[str] = None
    adapter_metadata: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class WAToken(BaseModel):
    """WA authentication token."""

    token: str = Field(..., description="JWT token string")
    token_type: TokenType
    expires_at: datetime
    scopes: List[str]
    wa_id: str

    model_config = ConfigDict(extra="forbid")


class WAAuthRequest(BaseModel):
    """Authentication request."""

    wa_id: Optional[str] = None
    password: Optional[str] = None
    api_key: Optional[str] = None
    oauth_token: Optional[str] = None
    channel_identity: Optional[ChannelIdentity] = None
    requested_scopes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class WAAuthResponse(BaseModel):
    """Authentication response."""

    success: bool
    token: Optional[WAToken] = None
    certificate: Optional[WACertificate] = None
    error: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class WARoleMintRequest(BaseModel):
    """Request to mint a new role certificate."""

    name: str
    role: WARole
    password: Optional[str] = None
    parent_wa_id: str
    parent_signature: str
    scopes: List[str] = Field(default_factory=list)

    model_config = ConfigDict(extra="forbid")


class DeferralRequest(BaseModel):
    """Request for WA deferral approval."""

    task_id: str
    thought_id: str
    reason: str
    defer_until: datetime
    context: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class DeferralResponse(BaseModel):
    """WA response to deferral request."""

    approved: bool
    reason: Optional[str] = None
    modified_time: Optional[datetime] = None
    wa_id: str
    signature: str

    model_config = ConfigDict(extra="forbid")


class GuidanceRequest(BaseModel):
    """Request for WA guidance."""

    context: str
    options: List[str]
    recommendation: Optional[str] = None
    urgency: str = Field(default="normal", pattern="^(low|normal|high|critical)$")

    # NEW: Optional capability fields for wisdom extension system
    capability: Optional[str] = Field(
        default=None, description="Domain capability tag (e.g., 'domain:navigation', 'modality:audio')"
    )
    provider_type: Optional[str] = Field(
        default=None, description="Provider family hint (audio|geo|sensor|policy|vision)"
    )
    inputs: Optional[Dict[str, str]] = Field(default=None, description="Structured inputs for non-text modalities")

    model_config = ConfigDict(extra="forbid")


class WisdomAdvice(BaseModel):
    """Capability-tagged advice from a wisdom provider."""

    capability: str = Field(..., description="Domain capability (e.g., 'domain:navigation')")
    provider_type: Optional[str] = None
    provider_name: Optional[str] = None
    confidence: Optional[float] = Field(None, ge=0.0, le=1.0)
    risk: Optional[str] = None
    explanation: Optional[str] = None
    data: Optional[Dict[str, str]] = None

    # CRITICAL: Liability management
    disclaimer: str = Field(
        default="This is informational only, not professional advice",
        description="Required disclaimer for capability domain",
    )
    requires_professional: bool = Field(default=False, description="True if domain requires licensed professional")

    model_config = ConfigDict(extra="forbid")


class GuidanceResponse(BaseModel):
    """WA guidance response."""

    selected_option: Optional[str] = None
    custom_guidance: Optional[str] = None
    reasoning: str
    wa_id: str
    signature: str

    # NEW: Aggregated advice from multiple providers
    advice: Optional[List[WisdomAdvice]] = Field(default=None, description="Per-provider capability-tagged advice")

    model_config = ConfigDict(extra="forbid")


class DeferralApprovalContext(BaseModel):
    """Context for deferral approval requests."""

    task_id: str
    thought_id: str
    action_name: str
    action_params: Dict[str, str] = Field(default_factory=dict)
    requester_id: str
    channel_id: Optional[str] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


class WAPermission(BaseModel):
    """Permission granted to a WA."""

    permission_id: str
    wa_id: str
    permission_type: str  # e.g., "action", "resource", "scope"
    permission_name: str  # e.g., "approve_deferrals", "access_logs"
    resource: Optional[str] = None  # Optional resource identifier
    granted_by: str  # WA ID who granted this permission
    granted_at: datetime
    expires_at: Optional[datetime] = None
    metadata: Dict[str, str] = Field(default_factory=dict)

    model_config = ConfigDict(extra="forbid")


__all__ = [
    "WARole",
    "TokenType",
    "JWTSubType",
    "WACertificate",
    "ChannelIdentity",
    "AuthorizationContext",
    "WACertificateRequest",
    "WAToken",
    "WAAuthRequest",
    "WAAuthResponse",
    "WARoleMintRequest",
    "DeferralRequest",
    "DeferralResponse",
    "GuidanceRequest",
    "GuidanceResponse",
    "WisdomAdvice",
    "DeferralApprovalContext",
    "WAPermission",
]
