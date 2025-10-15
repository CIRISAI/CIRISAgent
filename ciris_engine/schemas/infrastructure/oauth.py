"""
Schemas for OAuth authentication flows.

These replace all Dict[str, Any] usage in wa_cli_oauth.py.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from ciris_engine.schemas.types import JSONDict


class OAuthProviderConfig(BaseModel):
    """Configuration for an OAuth provider."""

    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret")
    auth_url: str = Field(..., description="OAuth authorization URL")
    token_url: str = Field(..., description="OAuth token exchange URL")
    scopes: str = Field(..., description="OAuth scopes to request")
    created: datetime = Field(..., description="When provider was configured")
    metadata: Optional[JSONDict] = Field(None, description="Custom provider metadata")


class OAuthSetupRequest(BaseModel):
    """Request to setup OAuth provider."""

    provider: str = Field(..., description="OAuth provider name")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret")
    custom_metadata: Optional[JSONDict] = Field(None, description="Custom metadata")


class OAuthOperationResult(BaseModel):
    """Result of an OAuth operation."""

    status: str = Field(..., description="Operation status (success/error)")
    provider: Optional[str] = Field(None, description="OAuth provider name")
    callback_url: Optional[str] = Field(None, description="OAuth callback URL")
    error: Optional[str] = Field(None, description="Error message if failed")
    details: Optional[JSONDict] = Field(None, description="Additional details")


class OAuthLoginResult(BaseModel):
    """Result of OAuth login attempt."""

    status: str = Field(..., description="Login status")
    provider: str = Field(..., description="OAuth provider used")
    auth_url: Optional[str] = Field(None, description="Authorization URL")
    certificate: Optional[JSONDict] = Field(None, description="WA certificate if successful")
    error: Optional[str] = Field(None, description="Error message if failed")


class OAuthProviderList(BaseModel):
    """List of configured OAuth providers."""

    providers: List[str] = Field(..., description="List of provider names")
    count: int = Field(..., description="Number of providers")


class OAuthProviderDetails(BaseModel):
    """Details about a specific OAuth provider."""

    provider: str = Field(..., description="Provider name")
    client_id: str = Field(..., description="OAuth client ID")
    created: datetime = Field(..., description="When configured")
    has_metadata: bool = Field(..., description="Whether custom metadata exists")
    metadata: Optional[JSONDict] = Field(None, description="Custom metadata if any")


class OAuthCallbackData(BaseModel):
    """Data received from OAuth callback."""

    code: str = Field(..., description="Authorization code")
    state: str = Field(..., description="OAuth state parameter")
    error: Optional[str] = Field(None, description="Error from provider")
    error_description: Optional[str] = Field(None, description="Error details")


class OAuthTokenExchange(BaseModel):
    """OAuth token exchange request/response."""

    grant_type: str = Field("authorization_code", description="OAuth grant type")
    code: str = Field(..., description="Authorization code")
    redirect_uri: str = Field(..., description="Redirect URI")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret")


class OAuthTokenResponse(BaseModel):
    """Response from OAuth token endpoint."""

    access_token: str = Field(..., description="Access token")
    token_type: str = Field(..., description="Token type (e.g., Bearer)")
    expires_in: Optional[int] = Field(None, description="Token expiry in seconds")
    refresh_token: Optional[str] = Field(None, description="Refresh token")
    scope: Optional[str] = Field(None, description="Granted scopes")


class OAuthUserInfo(BaseModel):
    """User information from OAuth provider."""

    id: str = Field(..., description="User ID from provider")
    email: Optional[str] = Field(None, description="User email")
    name: Optional[str] = Field(None, description="User display name")
    picture: Optional[str] = Field(None, description="User avatar URL")
    provider_data: JSONDict = Field(default_factory=dict, description="Raw provider data")


class OAuthProviderConfigDB(BaseModel):
    """Database model for storing OAuth provider configurations."""

    provider: str = Field(..., description="OAuth provider name")
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret (encrypted)")
    auth_url: str = Field(..., description="OAuth authorization URL")
    token_url: str = Field(..., description="OAuth token exchange URL")
    userinfo_url: str = Field(..., description="OAuth user info URL")
    scopes: str = Field(..., description="OAuth scopes to request")
    created_at: datetime = Field(..., description="When provider was configured")
    updated_at: datetime = Field(..., description="When provider was last updated")
    is_active: bool = Field(True, description="Whether provider is active")
    custom_metadata: Optional[JSONDict] = Field(None, description="Custom provider metadata")


class OAuthUserProfile(BaseModel):
    """Standardized user profile from any OAuth provider."""

    provider: str = Field(..., description="OAuth provider name")
    user_id: str = Field(..., description="User ID from provider")
    email: Optional[str] = Field(None, description="User email address")
    email_verified: bool = Field(False, description="Whether email is verified")
    name: Optional[str] = Field(None, description="User full name")
    given_name: Optional[str] = Field(None, description="User given/first name")
    family_name: Optional[str] = Field(None, description="User family/last name")
    picture: Optional[str] = Field(None, description="User profile picture URL")
    locale: Optional[str] = Field(None, description="User locale/language")
    created_at: datetime = Field(..., description="When profile was created")
    raw_data: JSONDict = Field(default_factory=dict, description="Raw provider response")


class OAuthProviderSummary(BaseModel):
    """Summary information for listing OAuth providers."""

    provider: str = Field(..., description="OAuth provider name")
    client_id: str = Field(..., description="OAuth client ID")
    is_active: bool = Field(..., description="Whether provider is active")
    created_at: datetime = Field(..., description="When provider was configured")
    updated_at: datetime = Field(..., description="When provider was last updated")
    user_count: int = Field(0, description="Number of users authenticated")


class OAuthProviderInfo(BaseModel):
    """Public information about an OAuth provider."""

    provider: str = Field(..., description="OAuth provider name")
    display_name: str = Field(..., description="Human-readable provider name")
    icon_url: Optional[str] = Field(None, description="Provider icon/logo URL")
    auth_url: str = Field(..., description="OAuth authorization URL")
    scopes: List[str] = Field(..., description="OAuth scopes requested")
    description: Optional[str] = Field(None, description="Provider description")
    is_available: bool = Field(True, description="Whether provider is available")


class OAuthCallbackResponse(BaseModel):
    """Response from OAuth callback processing."""

    success: bool = Field(..., description="Whether callback was successful")
    access_token: Optional[str] = Field(None, description="OAuth access token")
    refresh_token: Optional[str] = Field(None, description="OAuth refresh token")
    user_profile: Optional[OAuthUserProfile] = Field(None, description="User profile from provider")
    error: Optional[str] = Field(None, description="Error message if failed")
    error_description: Optional[str] = Field(None, description="Detailed error description")
