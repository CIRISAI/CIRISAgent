"""
Authentication API routes for CIRIS.

Implements session management endpoints:
- POST /v1/auth/login - Authenticate user
- POST /v1/auth/logout - End session
- GET /v1/auth/me - Current user info (includes permissions)
- POST /v1/auth/refresh - Refresh token

Note: OAuth endpoints are in api_auth_v2.py
"""

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ciris_engine.logic.adapters.api.services.oauth_security import validate_oauth_picture_url
from ciris_engine.schemas.api.auth import (
    AuthContext,
    LoginRequest,
    LoginResponse,
    TokenRefreshRequest,
    UserInfo,
    UserRole,
)
from ciris_engine.schemas.runtime.api import APIRole

from ..dependencies.auth import check_permissions, get_auth_context, get_auth_service, optional_auth
from ..services.auth_service import APIAuthService

# Constants
OAUTH_CONFIG_PATH = Path("/home/ciris/shared/oauth/oauth.json")
OAUTH_CONFIG_DIR = ".ciris"
OAUTH_CONFIG_FILE = "oauth.json"
PROVIDER_NAME_DESC = "Provider name"
# Get agent ID from environment, default to 'datum' if not set
AGENT_ID = os.getenv("CIRIS_AGENT_ID", "datum")
OAUTH_CALLBACK_PATH = f"/v1/auth/oauth/{AGENT_ID}/{{provider}}/callback"
DEFAULT_OAUTH_BASE_URL = "https://agents.ciris.ai"
# Error messages
FETCH_USER_INFO_ERROR = "Failed to fetch user info"


# Helper functions
def get_oauth_callback_url(provider: str, base_url: Optional[str] = None) -> str:
    """Get the OAuth callback URL for a specific provider."""
    if base_url is None:
        base_url = os.getenv("OAUTH_CALLBACK_BASE_URL", DEFAULT_OAUTH_BASE_URL)
    return base_url + OAUTH_CALLBACK_PATH.replace("{provider}", provider)


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])


@router.post("/auth/login", response_model=LoginResponse)
async def login(
    request: LoginRequest, req: Request, auth_service: APIAuthService = Depends(get_auth_service)
) -> LoginResponse:
    """
    Authenticate with username/password.

    Currently supports system admin user only. In production, this would
    integrate with a proper user database.
    """
    getattr(req.app.state, "config_service", None)

    # Verify username and password using secure bcrypt verification
    user = await auth_service.verify_user_password(request.username, request.password)

    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    # Generate API key based on user's role
    api_key = f"ciris_{user.api_role.value.lower()}_{secrets.token_urlsafe(32)}"
    expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    # Map APIRole to UserRole for API key storage
    user_role_map = {
        APIRole.OBSERVER: UserRole.OBSERVER,
        APIRole.ADMIN: UserRole.ADMIN,
        APIRole.AUTHORITY: UserRole.AUTHORITY,
        APIRole.SYSTEM_ADMIN: UserRole.SYSTEM_ADMIN,
    }

    # Store API key
    auth_service.store_api_key(
        key=api_key,
        user_id=user.wa_id,
        role=user_role_map[user.api_role],
        expires_at=expires_at,
        description="Login session",
    )

    logger.info(f"User {user.name} logged in successfully")

    return LoginResponse(
        access_token=api_key,
        token_type="Bearer",
        expires_in=86400,  # 24 hours
        role=user_role_map[user.api_role],
        user_id=user.wa_id,
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    auth: AuthContext = Depends(get_auth_context), auth_service: APIAuthService = Depends(get_auth_service)
) -> None:
    """
    End the current session by revoking the API key.

    This endpoint invalidates the current authentication token,
    effectively logging out the user.
    """
    if auth.api_key_id:
        auth_service.revoke_api_key(auth.api_key_id)
        # Don't log sensitive API key ID
        logger.info(f"User {auth.user_id} logged out, API key revoked")

    return None


@router.get("/auth/me", response_model=UserInfo)
async def get_current_user(auth: AuthContext = Depends(get_auth_context)) -> UserInfo:
    """
    Get current authenticated user information.

    Returns details about the currently authenticated user including
    their role and all permissions based on that role.
    """
    # Use permissions from the auth context which includes custom permissions
    permissions = [p.value for p in auth.permissions]

    # For API key auth, we don't have a traditional username
    # Use the user_id as username
    username = auth.user_id

    return UserInfo(
        user_id=auth.user_id,
        username=username,
        role=auth.role,
        permissions=permissions,
        created_at=auth.authenticated_at,  # Use auth time as proxy
        last_login=auth.authenticated_at,
    )


@router.post("/auth/refresh", response_model=LoginResponse)
async def refresh_token(
    request: TokenRefreshRequest,
    auth: Optional[AuthContext] = Depends(optional_auth),
    auth_service: APIAuthService = Depends(get_auth_service),
) -> LoginResponse:
    """
    Refresh access token.

    Creates a new access token and revokes the old one. Supports both
    API key and OAuth refresh flows. The user must be authenticated
    to refresh their token.
    """
    # For now, we require the user to be authenticated to refresh
    # In a full implementation, we'd validate the refresh token separately
    if not auth:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required to refresh token")

    # Generate new API key
    new_api_key = f"ciris_{auth.role.value.lower()}_{secrets.token_urlsafe(32)}"

    # Set expiration based on role
    if auth.role == UserRole.SYSTEM_ADMIN:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
        expires_in = 86400  # 24 hours
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)
        expires_in = 2592000  # 30 days

    # Store new API key
    auth_service.store_api_key(
        key=new_api_key, user_id=auth.user_id, role=auth.role, expires_at=expires_at, description="Refreshed token"
    )

    # Revoke old API key if it exists
    if auth.api_key_id:
        auth_service.revoke_api_key(auth.api_key_id)

    logger.info(f"Token refreshed for user {auth.user_id}")

    return LoginResponse(
        access_token=new_api_key, token_type="Bearer", expires_in=expires_in, role=auth.role, user_id=auth.user_id
    )


# ========== OAuth Management Endpoints ==========


class OAuthProviderInfo(BaseModel):
    """OAuth provider information."""

    provider: str = Field(..., description=PROVIDER_NAME_DESC)
    client_id: str = Field(..., description="OAuth client ID")
    created: Optional[str] = Field(None, description="Creation timestamp")
    callback_url: str = Field(..., description="OAuth callback URL")
    metadata: Dict[str, str] = Field(default_factory=dict, description="Additional metadata")


class OAuthProvidersResponse(BaseModel):
    """OAuth providers list response."""

    providers: List[OAuthProviderInfo] = Field(default_factory=list, description="List of configured providers")


@router.get("/auth/oauth/providers", response_model=OAuthProvidersResponse)
async def list_oauth_providers(
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    _: None = Depends(check_permissions(["users.write"])),  # SYSTEM_ADMIN only
) -> OAuthProvidersResponse:
    """
    List configured OAuth providers.

    Requires: users.write permission (SYSTEM_ADMIN only)
    """
    import json
    from pathlib import Path

    # Check shared volume first (managed mode), then fall back to local (standalone)
    oauth_config_file = OAUTH_CONFIG_PATH
    if not oauth_config_file.exists():
        oauth_config_file = Path.home() / OAUTH_CONFIG_DIR / OAUTH_CONFIG_FILE
        logger.debug(f"Using local OAuth config: {oauth_config_file}")
    else:
        logger.debug(f"Using shared OAuth config: {oauth_config_file}")

    if not oauth_config_file.exists():
        return OAuthProvidersResponse(providers=[])

    try:
        config = json.loads(oauth_config_file.read_text())
        providers = []

        for provider, settings in config.items():
            providers.append(
                OAuthProviderInfo(
                    provider=provider,
                    client_id=settings.get("client_id", ""),
                    created=settings.get("created"),
                    callback_url=f"{request.headers.get('x-forwarded-proto', request.url.scheme)}://{request.headers.get('host', 'localhost')}{OAUTH_CALLBACK_PATH}",
                    metadata=settings.get("metadata", {}),
                )
            )

        return OAuthProvidersResponse(providers=providers)
    except Exception as e:
        logger.error(f"Failed to read OAuth config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to read OAuth configuration"
        )


class ConfigureOAuthProviderRequest(BaseModel):
    """Request to configure an OAuth provider."""

    provider: str = Field(..., description=PROVIDER_NAME_DESC)
    client_id: str = Field(..., description="OAuth client ID")
    client_secret: str = Field(..., description="OAuth client secret")
    metadata: Optional[Dict[str, str]] = Field(None, description="Additional metadata")


class ConfigureOAuthProviderResponse(BaseModel):
    """Response from OAuth provider configuration."""

    provider: str = Field(..., description=PROVIDER_NAME_DESC)
    callback_url: str = Field(..., description="OAuth callback URL")
    message: str = Field(..., description="Status message")


@router.post("/auth/oauth/providers", response_model=ConfigureOAuthProviderResponse)
async def configure_oauth_provider(
    body: ConfigureOAuthProviderRequest,
    request: Request,
    auth: AuthContext = Depends(get_auth_context),
    _: None = Depends(check_permissions(["users.write"])),  # SYSTEM_ADMIN only
) -> ConfigureOAuthProviderResponse:
    """
    Configure an OAuth provider.

    Requires: users.write permission (SYSTEM_ADMIN only)
    """
    import json
    from pathlib import Path

    # Check shared volume first (managed mode), then fall back to local (standalone)
    oauth_config_file = OAUTH_CONFIG_PATH
    if not oauth_config_file.exists():
        oauth_config_file = Path.home() / OAUTH_CONFIG_DIR / OAUTH_CONFIG_FILE
        logger.debug(f"Using local OAuth config: {oauth_config_file}")
    else:
        logger.debug(f"Using shared OAuth config: {oauth_config_file}")
    oauth_config_file.parent.mkdir(exist_ok=True, mode=0o700)

    # Load existing config
    config = {}
    if oauth_config_file.exists():
        try:
            config = json.loads(oauth_config_file.read_text())
        except (json.JSONDecodeError, IOError, OSError) as e:
            logger.warning(f"Failed to load OAuth config file: {e}")
            pass

    # Add/update provider
    config[body.provider] = {
        "client_id": body.client_id,
        "client_secret": body.client_secret,
        "created": datetime.now(timezone.utc).isoformat(),
        "metadata": body.metadata or {},
    }

    # Save config
    try:
        oauth_config_file.write_text(json.dumps(config, indent=2))
        oauth_config_file.chmod(0o600)

        logger.info(f"OAuth provider '{body.provider}' configured by {auth.user_id}")

        return ConfigureOAuthProviderResponse(
            provider=body.provider,
            callback_url=f"{request.headers.get('x-forwarded-proto', request.url.scheme)}://{request.headers.get('host', 'localhost')}{OAUTH_CALLBACK_PATH}",
            message="OAuth provider configured successfully",
        )
    except Exception as e:
        logger.error(f"Failed to save OAuth config: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to save OAuth configuration"
        )


class OAuthLoginResponse(BaseModel):
    """OAuth login initiation response."""

    authorization_url: str = Field(..., description="URL to redirect user to for authorization")
    state: str = Field(..., description="State parameter for CSRF protection")


@router.get("/auth/oauth/{provider}/login")
async def oauth_login(provider: str, request: Request, redirect_uri: Optional[str] = None) -> RedirectResponse:
    """
    Initiate OAuth login flow.

    Redirects to the OAuth provider's authorization URL.
    """
    import json
    import urllib.parse
    from pathlib import Path

    # Check shared volume first (managed mode), then fall back to local (standalone)
    oauth_config_file = OAUTH_CONFIG_PATH
    if not oauth_config_file.exists():
        oauth_config_file = Path.home() / OAUTH_CONFIG_DIR / OAUTH_CONFIG_FILE
        logger.debug(f"Using local OAuth config: {oauth_config_file}")
    else:
        logger.debug(f"Using shared OAuth config: {oauth_config_file}")

    if not oauth_config_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"OAuth provider '{provider}' not configured")

    try:
        config = json.loads(oauth_config_file.read_text())
        if provider not in config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"OAuth provider '{provider}' not configured"
            )

        provider_config = config[provider]
        client_id = provider_config["client_id"]

        # Generate state for CSRF protection
        state = secrets.token_urlsafe(32)

        # Store state in a temporary location (in production, use Redis or similar)
        # For now, we'll include it in the redirect_uri

        # Use OAUTH_CALLBACK_BASE_URL environment variable, or construct from request
        base_url = os.getenv("OAUTH_CALLBACK_BASE_URL")
        if not base_url:
            # Construct from request headers
            base_url = f"{request.headers.get('x-forwarded-proto', request.url.scheme)}://{request.headers.get('host', 'localhost')}"

        # Always use API callback URL for OAuth providers (this is what's registered in Google Console)
        callback_url = get_oauth_callback_url(provider, base_url)

        # Build authorization URL based on provider
        if provider == "google":
            auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
            params = {
                "client_id": client_id,
                "redirect_uri": callback_url,
                "response_type": "code",
                "scope": "openid email profile",
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
            }
        elif provider == "github":
            auth_url = "https://github.com/login/oauth/authorize"
            params = {
                "client_id": client_id,
                "redirect_uri": callback_url,
                "scope": "read:user user:email",
                "state": state,
            }
        elif provider == "discord":
            auth_url = "https://discord.com/api/oauth2/authorize"
            params = {
                "client_id": client_id,
                "redirect_uri": callback_url,
                "response_type": "code",
                "scope": "identify email",
                "state": state,
            }
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported OAuth provider: {provider}"
            )

        # Build full URL
        full_url = f"{auth_url}?{urllib.parse.urlencode(params)}"

        # Redirect user to OAuth provider
        return RedirectResponse(url=full_url, status_code=302)

    except Exception as e:
        logger.error(f"OAuth login initiation failed: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to initiate OAuth login")


@router.get("/auth/oauth/{provider}/callback")
async def oauth_callback(
    provider: str, code: str, state: str, auth_service: APIAuthService = Depends(get_auth_service)
) -> LoginResponse:
    """
    Handle OAuth callback.

    Exchanges authorization code for tokens and creates/updates user.
    """
    import json
    from pathlib import Path

    import httpx

    # Load OAuth configuration
    # Check shared volume first (managed mode), then fall back to local (standalone)
    oauth_config_file = OAUTH_CONFIG_PATH
    if not oauth_config_file.exists():
        oauth_config_file = Path.home() / OAUTH_CONFIG_DIR / OAUTH_CONFIG_FILE
        logger.debug(f"Using local OAuth config: {oauth_config_file}")
    else:
        logger.debug(f"Using shared OAuth config: {oauth_config_file}")

    if not oauth_config_file.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"OAuth provider '{provider}' not configured")

    try:
        config = json.loads(oauth_config_file.read_text())
        if provider not in config:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail=f"OAuth provider '{provider}' not configured"
            )

        provider_config = config[provider]
        client_id = provider_config["client_id"]
        client_secret = provider_config["client_secret"]

        # Initialize profile variables
        picture = None

        # Exchange authorization code for access token
        async with httpx.AsyncClient() as client:
            if provider == "google":
                # Exchange code for token
                token_response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": get_oauth_callback_url(provider),
                        "grant_type": "authorization_code",
                    },
                )

                if token_response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to exchange code for token: {token_response.text}",
                    )

                token_data = token_response.json()
                access_token = token_data["access_token"]

                # Get user info
                user_response = await client.get(
                    "https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"}
                )

                if user_response.status_code != 200:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FETCH_USER_INFO_ERROR)

                user_info = user_response.json()
                external_id = user_info["id"]
                email = user_info.get("email")
                name = user_info.get("name", email)
                picture = user_info.get("picture")  # Google profile picture URL

            elif provider == "github":
                # Exchange code for token
                token_response = await client.post(
                    "https://github.com/login/oauth/access_token",
                    headers={"Accept": "application/json"},
                    data={
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": os.getenv("OAUTH_CALLBACK_BASE_URL", DEFAULT_OAUTH_BASE_URL)
                        + OAUTH_CALLBACK_PATH.replace("{provider}", provider),
                    },
                )

                if token_response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to exchange code for token: {token_response.text}",
                    )

                token_data = token_response.json()
                access_token = token_data["access_token"]

                # Get user info
                user_response = await client.get(
                    "https://api.github.com/user", headers={"Authorization": f"token {access_token}"}
                )

                if user_response.status_code != 200:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FETCH_USER_INFO_ERROR)

                user_info = user_response.json()
                external_id = str(user_info["id"])
                email = user_info.get("email")
                name = user_info.get("name", user_info.get("login"))
                picture = user_info.get("avatar_url")  # GitHub avatar URL

                # If email is private, fetch from emails endpoint
                if not email:
                    emails_response = await client.get(
                        "https://api.github.com/user/emails", headers={"Authorization": f"token {access_token}"}
                    )
                    if emails_response.status_code == 200:
                        emails = emails_response.json()
                        for e in emails:
                            if e.get("primary"):
                                email = e["email"]
                                break

            elif provider == "discord":
                # Exchange code for token
                token_response = await client.post(
                    "https://discord.com/api/oauth2/token",
                    headers={"Content-Type": "application/x-www-form-urlencoded"},
                    data={
                        "code": code,
                        "client_id": client_id,
                        "client_secret": client_secret,
                        "redirect_uri": get_oauth_callback_url(provider),
                        "grant_type": "authorization_code",
                    },
                )

                if token_response.status_code != 200:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to exchange code for token: {token_response.text}",
                    )

                token_data = token_response.json()
                access_token = token_data["access_token"]

                # Get user info
                user_response = await client.get(
                    "https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"}
                )

                if user_response.status_code != 200:
                    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FETCH_USER_INFO_ERROR)

                user_info = user_response.json()
                external_id = user_info["id"]
                email = user_info.get("email")
                name = user_info.get("username", email)
                # Construct Discord avatar URL if avatar exists
                avatar_hash = user_info.get("avatar")
                if avatar_hash:
                    picture = f"https://cdn.discordapp.com/avatars/{external_id}/{avatar_hash}.png"
                else:
                    picture = None

            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported OAuth provider: {provider}"
                )

        # Determine role based on email domain
        # Grant admin rights to @ciris.ai email addresses
        if email and email.endswith("@ciris.ai"):
            user_role = UserRole.ADMIN
            logger.info(f"Granting ADMIN role to @ciris.ai user: {email}")
        else:
            user_role = UserRole.OBSERVER  # Default role for non-CIRIS users

        # Create or update OAuth user
        oauth_user = auth_service.create_oauth_user(
            provider=provider,
            external_id=external_id,
            email=email,
            name=name,
            role=user_role,
        )

        # Store OAuth profile data if we have it
        if picture:
            # Validate the picture URL for security
            if validate_oauth_picture_url(picture):
                # Store additional OAuth profile data
                user = auth_service.get_user(oauth_user.user_id)
                if user:
                    user.oauth_name = name
                    user.oauth_picture = picture
                    # Store the updated user data
                    auth_service._users[oauth_user.user_id] = user
            else:
                logger.warning(f"Invalid OAuth picture URL rejected for user {oauth_user.user_id}: {picture}")

        # Generate API key for the user with appropriate prefix based on role
        role_prefix = "ciris_admin" if user_role == UserRole.ADMIN else "ciris_observer"
        api_key = f"{role_prefix}_{secrets.token_urlsafe(32)}"
        expires_at = datetime.now(timezone.utc) + timedelta(days=30)

        auth_service.store_api_key(
            key=api_key,
            user_id=oauth_user.user_id,
            role=oauth_user.role,
            expires_at=expires_at,
            description=f"OAuth login via {provider}",
        )

        logger.info(f"OAuth user {oauth_user.user_id} logged in successfully via {provider}")

        # Redirect to GUI OAuth callback page with token info
        # The GUI will handle storing the token and redirecting to dashboard
        gui_callback_url = f"/oauth/{AGENT_ID}/{provider}/callback"
        redirect_params = {
            "access_token": api_key,
            "token_type": "Bearer",
            "expires_in": "2592000",
            "role": oauth_user.role.value,
            "user_id": oauth_user.user_id,
        }

        # Build redirect URL with query parameters
        import urllib.parse

        query_string = urllib.parse.urlencode(redirect_params)
        redirect_url = f"{gui_callback_url}?{query_string}"

        return RedirectResponse(url=redirect_url, status_code=302)

    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"OAuth callback failed: {str(e)}"
        )
