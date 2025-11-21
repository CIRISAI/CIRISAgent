"""
Authentication and authorization schemas for CIRIS API v2.0.

Implements role-based access control with clear hierarchy:
OBSERVER < ADMIN < AUTHORITY < ROOT
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field


class UserRole(str, Enum):
    """User roles in order of increasing privilege."""

    OBSERVER = "OBSERVER"
    ADMIN = "ADMIN"
    AUTHORITY = "AUTHORITY"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"  # Renamed from ROOT to avoid confusion with WA ROOT
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

    def has_permission(self, required_role: "UserRole") -> bool:
        """Check if this role meets or exceeds required role."""
        return self.level >= required_role.level


class Permission(str, Enum):
    """Granular permissions for fine-grained access control."""

    # Observer permissions
    VIEW_MESSAGES = "view_messages"
    VIEW_TELEMETRY = "view_telemetry"
    VIEW_REASONING = "view_reasoning"
    VIEW_CONFIG = "view_config"
    VIEW_MEMORY = "view_memory"
    VIEW_AUDIT = "view_audit"
    VIEW_TOOLS = "view_tools"
    VIEW_LOGS = "view_logs"
    SEND_MESSAGES = "send_messages"  # Permission to send messages via API

    # Admin permissions
    MANAGE_CONFIG = "manage_config"
    RUNTIME_CONTROL = "runtime_control"
    MANAGE_INCIDENTS = "manage_incidents"
    MANAGE_TASKS = "manage_tasks"
    MANAGE_FILTERS = "manage_filters"
    TRIGGER_ANALYSIS = "trigger_analysis"

    # Authority permissions
    RESOLVE_DEFERRALS = "resolve_deferrals"
    PROVIDE_GUIDANCE = "provide_guidance"
    GRANT_PERMISSIONS = "grant_permissions"
    MANAGE_USER_PERMISSIONS = "manage_user_permissions"

    # System Admin permissions
    FULL_ACCESS = "full_access"
    EMERGENCY_SHUTDOWN = "emergency_shutdown"
    MANAGE_SENSITIVE_CONFIG = "manage_sensitive_config"


# Role to permissions mapping
ROLE_PERMISSIONS: Dict[UserRole, Set[Permission]] = {
    UserRole.OBSERVER: {
        Permission.VIEW_MESSAGES,
        Permission.VIEW_TELEMETRY,
        Permission.VIEW_REASONING,
        Permission.VIEW_CONFIG,
        Permission.VIEW_MEMORY,
        Permission.VIEW_AUDIT,
        Permission.VIEW_TOOLS,
        Permission.VIEW_LOGS,
        Permission.SEND_MESSAGES,  # OBSERVER can send messages (gated by billing/credit system)
    },
    UserRole.ADMIN: {
        # Includes all OBSERVER permissions
        Permission.VIEW_MESSAGES,
        Permission.VIEW_TELEMETRY,
        Permission.VIEW_REASONING,
        Permission.VIEW_CONFIG,
        Permission.VIEW_MEMORY,
        Permission.VIEW_AUDIT,
        Permission.VIEW_TOOLS,
        Permission.VIEW_LOGS,
        Permission.SEND_MESSAGES,  # ADMIN can send messages
        # Plus admin permissions
        Permission.MANAGE_CONFIG,
        Permission.RUNTIME_CONTROL,
        Permission.MANAGE_INCIDENTS,
        Permission.MANAGE_TASKS,
        Permission.MANAGE_FILTERS,
        Permission.TRIGGER_ANALYSIS,
    },
    UserRole.AUTHORITY: {
        # Includes all ADMIN permissions
        Permission.VIEW_MESSAGES,
        Permission.VIEW_TELEMETRY,
        Permission.VIEW_REASONING,
        Permission.VIEW_CONFIG,
        Permission.VIEW_MEMORY,
        Permission.VIEW_AUDIT,
        Permission.VIEW_TOOLS,
        Permission.VIEW_LOGS,
        Permission.SEND_MESSAGES,  # AUTHORITY can send messages
        Permission.MANAGE_CONFIG,
        Permission.RUNTIME_CONTROL,
        Permission.MANAGE_INCIDENTS,
        Permission.MANAGE_TASKS,
        Permission.MANAGE_FILTERS,
        Permission.TRIGGER_ANALYSIS,
        # Plus authority permissions
        Permission.RESOLVE_DEFERRALS,
        Permission.PROVIDE_GUIDANCE,
        Permission.GRANT_PERMISSIONS,
        Permission.MANAGE_USER_PERMISSIONS,
    },
    UserRole.SYSTEM_ADMIN: {
        # System admin has all permissions explicitly
        # (includes all lower role permissions plus system-level permissions)
        Permission.VIEW_MESSAGES,
        Permission.VIEW_TELEMETRY,
        Permission.VIEW_REASONING,
        Permission.VIEW_CONFIG,
        Permission.VIEW_MEMORY,
        Permission.VIEW_AUDIT,
        Permission.VIEW_TOOLS,
        Permission.VIEW_LOGS,
        Permission.SEND_MESSAGES,
        Permission.MANAGE_CONFIG,
        Permission.RUNTIME_CONTROL,
        Permission.MANAGE_INCIDENTS,
        Permission.MANAGE_TASKS,
        Permission.MANAGE_FILTERS,
        Permission.TRIGGER_ANALYSIS,
        Permission.RESOLVE_DEFERRALS,  # SYSTEM_ADMIN can resolve deferrals
        Permission.PROVIDE_GUIDANCE,
        Permission.GRANT_PERMISSIONS,
        Permission.MANAGE_USER_PERMISSIONS,
        Permission.FULL_ACCESS,
        Permission.EMERGENCY_SHUTDOWN,
        Permission.MANAGE_SENSITIVE_CONFIG,
    },
    UserRole.SERVICE_ACCOUNT: {
        # Permissions for service-to-service operations and system administration
        Permission.VIEW_TELEMETRY,
        Permission.VIEW_CONFIG,
        Permission.RUNTIME_CONTROL,  # For shutdown operations
        Permission.VIEW_TOOLS,
        Permission.VIEW_LOGS,
        Permission.SEND_MESSAGES,  # For system admin agent interaction and testing
    },
}


class AuthContext(BaseModel):
    """Authentication context for API requests."""

    user_id: str = Field(..., description="Unique user identifier")
    role: UserRole = Field(..., description="User's role")
    permissions: Set[Permission] = Field(..., description="Granted permissions")
    api_key_id: Optional[str] = Field(None, description="API key ID if using key auth")
    session_id: Optional[str] = Field(None, description="Session ID if using session auth")
    authenticated_at: datetime = Field(..., description="When authentication occurred")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # Request object (not serialized)
    request: Optional[Any] = Field(None, exclude=True)

    @classmethod
    def from_api_key(cls, api_key: "APIKey") -> "AuthContext":
        """Create context from API key."""
        return cls(
            user_id=api_key.user_id,
            role=api_key.role,
            permissions=ROLE_PERMISSIONS.get(api_key.role, set()),
            api_key_id=api_key.id,
            session_id=None,
            authenticated_at=datetime.now(timezone.utc),
            request=None,
        )

    def has_permission(self, permission: Permission) -> bool:
        """Check if user has specific permission."""
        if self.role == UserRole.SYSTEM_ADMIN:
            return True  # SYSTEM_ADMIN has all permissions
        return permission in self.permissions


class APIKey(BaseModel):
    """API key model for authentication."""

    id: str = Field(..., description="Unique key identifier")
    key_hash: str = Field(..., description="Hashed API key")
    user_id: str = Field(..., description="User who owns this key")
    role: UserRole = Field(..., description="Role granted by this key")
    description: str = Field("", description="Human-readable description")
    created_at: datetime = Field(..., description="When key was created")
    last_used: Optional[datetime] = Field(None, description="Last time key was used")
    expires_at: Optional[datetime] = Field(None, description="When key expires")
    is_active: bool = Field(True, description="Whether key is active")

    def is_valid(self) -> bool:
        """Check if key is currently valid."""
        if not self.is_active:
            return False

        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
            return False

        return True


class LoginRequest(BaseModel):
    """Request to authenticate with username/password."""

    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


class LoginResponse(BaseModel):
    """Response after successful login."""

    access_token: str = Field(..., description="JWT access token")
    token_type: str = Field("bearer", description="Token type")
    expires_in: int = Field(..., description="Token lifetime in seconds")
    user_id: str = Field(..., description="Authenticated user ID")
    role: UserRole = Field(..., description="User's role")


class TokenRefreshRequest(BaseModel):
    """Request to refresh access token."""

    refresh_token: str = Field(..., description="Refresh token")


class UserInfo(BaseModel):
    """Current user information."""

    user_id: str = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    role: UserRole = Field(..., description="User's role")
    permissions: List[str] = Field(..., description="List of permissions")
    created_at: datetime = Field(..., description="Account creation time")
    last_login: Optional[datetime] = Field(None, description="Last login time")


class TokenResponse(BaseModel):
    """Token information response."""

    user_id: str
    role: UserRole
    scopes: List[str]
    expires_at: Optional[datetime] = None


class OAuth2StartRequest(BaseModel):
    """OAuth2 flow start request."""

    redirect_uri: Optional[str] = Field(None, description="Custom redirect URI after authentication")


class OAuth2CallbackResponse(BaseModel):
    """OAuth2 callback response with API key."""

    access_token: str = Field(..., description="API key for accessing CIRIS API")
    token_type: str = Field("Bearer", description="Token type")
    expires_in: int = Field(..., description="Token expiration in seconds")
    role: UserRole = Field(..., description="User role")
    user_id: str = Field(..., description="User identifier")
    provider: str = Field(..., description="OAuth provider used")
    email: Optional[str] = Field(None, description="User email from OAuth provider")
    name: Optional[str] = Field(None, description="User name from OAuth provider")


class APIKeyCreateRequest(BaseModel):
    """Request to create a new API key."""

    description: Optional[str] = Field(None, description="Description of the key's purpose")
    expires_in_minutes: int = Field(
        ...,
        ge=30,
        le=10080,
        description="Expiry time in minutes (30 minutes to 7 days). 30min=30, 1day=1440, 7days=10080",
    )


class APIKeyResponse(BaseModel):
    """Response with created API key."""

    api_key: str = Field(..., description="The generated API key (show only once!)")
    role: UserRole = Field(..., description="Role assigned to the key")
    expires_at: Optional[datetime] = Field(None, description="When the key expires")
    description: Optional[str] = Field(None, description="Key description")
    created_at: datetime = Field(..., description="When the key was created")
    created_by: str = Field(..., description="User who created the key")


class APIKeyInfo(BaseModel):
    """API key information (without the actual key)."""

    key_id: str = Field(..., description="Key identifier (partial)")
    role: UserRole = Field(..., description="Role assigned to the key")
    expires_at: Optional[datetime] = Field(None, description="When the key expires")
    description: Optional[str] = Field(None, description="Key description")
    created_at: datetime = Field(..., description="When the key was created")
    created_by: str = Field(..., description="User who created the key")
    last_used: Optional[datetime] = Field(None, description="Last time the key was used")
    is_active: bool = Field(..., description="Whether the key is active")


class APIKeyListResponse(BaseModel):
    """List of API keys."""

    api_keys: List[APIKeyInfo] = Field(..., description="List of API keys")
    total: int = Field(..., description="Total number of keys")


class PermissionRequestResponse(BaseModel):
    """Response for permission request operation."""

    success: bool = Field(..., description="Whether the request was successful")
    status: str = Field(
        ..., description="Status of the request (already_granted, already_requested, request_submitted)"
    )
    message: str = Field(..., description="Human-readable message")
    requested_at: Optional[datetime] = Field(None, description="When the permission was requested")


class PermissionRequestUser(BaseModel):
    """User with permission request information."""

    id: str = Field(..., description="User ID")
    email: Optional[str] = Field(None, description="User email")
    oauth_name: Optional[str] = Field(None, description="Name from OAuth provider")
    oauth_picture: Optional[str] = Field(None, description="Profile picture URL from OAuth provider")
    role: UserRole = Field(..., description="Current role")
    permission_requested_at: datetime = Field(..., description="When permissions were requested")
    has_send_messages: bool = Field(..., description="Whether user already has SEND_MESSAGES permission")
