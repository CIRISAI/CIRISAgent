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
from typing import Annotated, Any, Dict, List, Optional, Set

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from ciris_engine.logic.adapters.api.services.auth_service import OAuthUser
from ciris_engine.logic.adapters.api.services.oauth_security import validate_oauth_picture_url
from ciris_engine.logic.utils.path_resolution import is_managed
from ciris_engine.schemas.api.auth import (
    APIKeyCreateRequest,
    APIKeyInfo,
    APIKeyListResponse,
    APIKeyResponse,
    AuthContext,
    LoginRequest,
    LoginResponse,
    ServiceTokenRevokeRequest,
    ServiceTokenRevokeResponse,
    TokenRefreshRequest,
    UserInfo,
    UserRole,
)
from ciris_engine.schemas.runtime.api import APIRole

from ..dependencies.auth import check_permissions, get_auth_context, get_auth_service, optional_auth
from ..services.auth_service import APIAuthService
from ._common import AuthDep, AuthServiceDep, OptionalAuthDep

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

# Module-level flag to prevent multiple attestation triggers from the endpoint
_attestation_triggered_from_endpoint = False

# OAuth Frontend Redirect Configuration
# These environment variables control where users are redirected after OAuth and what parameters are included
OAUTH_FRONTEND_URL = os.getenv("OAUTH_FRONTEND_URL")  # e.g., https://scout.ciris.ai
OAUTH_FRONTEND_PATH = os.getenv("OAUTH_FRONTEND_PATH", "/oauth-complete.html")  # Default: /oauth-complete.html
# Comma-separated list of parameters to include in redirect
# Default includes all ScoutGUI requirements
OAUTH_REDIRECT_PARAMS = os.getenv(
    "OAUTH_REDIRECT_PARAMS", "access_token,token_type,role,user_id,expires_in,email,marketing_opt_in,agent,provider"
).split(",")
# Comma-separated list of allowed redirect domains for OAuth (security: prevents open redirect attacks)
# Always includes OAUTH_FRONTEND_URL if set. Relative paths (starting with /) are always allowed.
OAUTH_ALLOWED_REDIRECT_DOMAINS = os.getenv("OAUTH_ALLOWED_REDIRECT_DOMAINS", "").split(",")
OAUTH_ALLOWED_REDIRECT_DOMAINS = [d.strip().lower() for d in OAUTH_ALLOWED_REDIRECT_DOMAINS if d.strip()]


# Helper functions
def get_oauth_callback_url(provider: str, base_url: Optional[str] = None) -> str:
    """Get the OAuth callback URL for a specific provider."""
    if base_url is None:
        base_url = os.getenv("OAUTH_CALLBACK_BASE_URL", DEFAULT_OAUTH_BASE_URL)
    return base_url + OAUTH_CALLBACK_PATH.replace("{provider}", provider)


def extract_query_params(url: str) -> Dict[str, str]:
    """Extract query parameters from a URL."""
    import urllib.parse

    parsed = urllib.parse.urlparse(url)
    return dict(urllib.parse.parse_qsl(parsed.query))


def _extract_hostname_from_netloc(netloc: str) -> str:
    """
    Safely extract hostname from netloc, handling userinfo and port.

    netloc format: [user:password@]host[:port]

    Security: Using urlparse().hostname is more robust than string splitting,
    but we handle edge cases manually for compatibility.
    """
    # Strip userinfo if present (user:password@)
    if "@" in netloc:
        netloc = netloc.rsplit("@", 1)[-1]

    # Strip port if present
    # Handle IPv6 addresses in brackets: [::1]:8080
    if netloc.startswith("["):
        # IPv6 address
        bracket_end = netloc.find("]")
        if bracket_end != -1:
            return netloc[1:bracket_end].lower()
        return netloc.lower()

    # IPv4 or hostname - strip port
    if ":" in netloc:
        return netloc.rsplit(":", 1)[0].lower()

    return netloc.lower()


def _is_private_network_host(host: str) -> bool:
    """
    Check if a host is on a private/local network.

    Allows HTTP for local development and Home Assistant on local networks.
    """
    import ipaddress

    # Extract hostname properly (handles userinfo@host:port format)
    hostname = _extract_hostname_from_netloc(host)

    # Check for localhost variants
    if hostname in ("localhost", "127.0.0.1", "::1"):
        return True

    # Check for .local mDNS domains (common for Home Assistant)
    if hostname.endswith(".local"):
        return True

    # Check for private IP ranges
    try:
        ip = ipaddress.ip_address(hostname)
        return ip.is_private or ip.is_loopback
    except ValueError:
        # Not a valid IP address, check if it looks like a local hostname
        pass

    return False


def _validate_redirect_scheme(scheme: str, is_private: bool, redirect_uri: str, netloc: str) -> bool:
    """Validate URL scheme for redirect URI. Returns True if valid."""
    if scheme == "http":
        if not is_private:
            logger.warning("Rejected HTTP redirect_uri to public host")
            return False
        logger.debug(f"Allowing HTTP redirect to private network: {netloc}")
        return True
    if scheme == "https":
        return True
    logger.warning(f"Rejected redirect_uri with unsupported scheme: {scheme}")
    return False


def _get_allowed_redirect_domains() -> Set[str]:
    """Build set of allowed redirect domains from config."""
    import urllib.parse

    allowed_domains: Set[str] = set(OAUTH_ALLOWED_REDIRECT_DOMAINS)
    if OAUTH_FRONTEND_URL:
        frontend_parsed = urllib.parse.urlparse(OAUTH_FRONTEND_URL)
        if frontend_parsed.hostname:
            # Use hostname (not netloc) to get just the host without port/userinfo
            allowed_domains.add(frontend_parsed.hostname.lower())
        elif frontend_parsed.netloc:
            # Fallback: extract hostname from netloc manually
            allowed_domains.add(_extract_hostname_from_netloc(frontend_parsed.netloc))
    return allowed_domains


def _is_domain_allowed(redirect_domain: str, allowed_domains: Set[str]) -> bool:
    """Check if redirect domain is in allowed list or is a subdomain of an allowed domain."""
    if redirect_domain in allowed_domains:
        return True
    return any(redirect_domain.endswith("." + allowed) for allowed in allowed_domains)


def validate_redirect_uri(redirect_uri: Optional[str]) -> Optional[str]:
    """
    Validate redirect_uri to prevent open redirect attacks.

    Security: Only allows:
    - Relative paths (starting with /)
    - URLs matching OAUTH_FRONTEND_URL domain
    - URLs matching domains in OAUTH_ALLOWED_REDIRECT_DOMAINS
    - HTTP allowed for private/local networks (Home Assistant, local dev)

    Returns the redirect_uri if valid, None if invalid/untrusted.
    """
    import urllib.parse

    if not redirect_uri:
        return None

    # Relative paths are always safe (same-origin), but prevent //evil.com tricks
    if redirect_uri.startswith("/"):
        if redirect_uri.startswith("//"):
            logger.warning("Rejected redirect_uri with protocol-relative path")
            return None
        return redirect_uri

    try:
        parsed = urllib.parse.urlparse(redirect_uri)
        if not parsed.scheme or not parsed.netloc:
            logger.warning("Rejected malformed redirect_uri")
            return None

        # Use hostname for security validation (strips port and userinfo)
        # Fallback to manual extraction if hostname is None
        redirect_hostname = parsed.hostname or _extract_hostname_from_netloc(parsed.netloc)
        if not redirect_hostname:
            logger.warning("Rejected redirect_uri with invalid hostname")
            return None

        is_private = _is_private_network_host(redirect_hostname)
        if not _validate_redirect_scheme(parsed.scheme.lower(), is_private, redirect_uri, redirect_hostname):
            return None

        # Private network hosts are always allowed (Home Assistant, local dev)
        if is_private:
            logger.debug(f"Allowing redirect to private network host: {redirect_hostname}")
            return redirect_uri

        # Check against allowed domains for public URLs (hostname only, no port)
        redirect_domain = redirect_hostname.lower()
        allowed_domains = _get_allowed_redirect_domains()
        if _is_domain_allowed(redirect_domain, allowed_domains):
            return redirect_uri

        logger.warning(
            f"Rejected redirect_uri to untrusted domain: {redirect_domain}. "
            f"Allowed domains: {allowed_domains or '(none configured)'}"
        )
        return None

    except Exception as e:
        logger.warning(f"Failed to parse redirect_uri: {e}")
        return None


logger = logging.getLogger(__name__)

router = APIRouter(tags=["Authentication"])


@router.post("/auth/login")
async def login(request: LoginRequest, req: Request, auth_service: AuthServiceDep) -> LoginResponse:
    """
    Authenticate with username/password.

    Currently supports system admin user only. In production, this would
    integrate with a proper user database.
    """
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
async def logout(auth: AuthDep, auth_service: AuthServiceDep) -> None:
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


@router.get("/auth/me")
async def get_current_user(auth: AuthDep, auth_service: AuthServiceDep) -> UserInfo:
    """
    Get current authenticated user information.

    Returns details about the currently authenticated user including
    their role and all permissions based on that role.
    """
    # Use permissions from the auth context which includes custom permissions
    permissions = [p.value for p in auth.permissions]

    # Fetch actual username from auth service
    user = auth_service.get_user(auth.user_id)
    username = user.name if user else auth.user_id  # Fallback to user_id if not found

    return UserInfo(
        user_id=auth.user_id,
        username=username,
        role=auth.role,
        permissions=permissions,
        created_at=auth.authenticated_at,  # Use auth time as proxy
        last_login=auth.authenticated_at,
    )


@router.post("/auth/refresh")
async def refresh_token(
    request: TokenRefreshRequest,
    auth: OptionalAuthDep,
    auth_service: AuthServiceDep,
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


@router.get("/auth/oauth/providers")
async def list_oauth_providers(
    request: Request,
    auth: AuthDep,
    _: Annotated[None, Depends(check_permissions(["users.write"]))],  # SYSTEM_ADMIN only
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


@router.post("/auth/oauth/providers")
async def configure_oauth_provider(
    body: ConfigureOAuthProviderRequest,
    request: Request,
    auth: AuthDep,
    _: Annotated[None, Depends(check_permissions(["users.write"]))],  # SYSTEM_ADMIN only
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

        # Sanitize user-controlled data before logging
        from ciris_engine.logic.utils.log_sanitizer import sanitize_for_log

        logger.info(f"OAuth provider '{sanitize_for_log(body.provider, max_length=50)}' configured successfully")

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
    Accepts optional redirect_uri to specify where to send tokens after OAuth.
    """
    import base64
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

        # Generate CSRF token
        csrf_token = secrets.token_urlsafe(32)

        # Validate redirect_uri to prevent open redirect attacks (security)
        validated_redirect_uri = validate_redirect_uri(redirect_uri)
        if redirect_uri and not validated_redirect_uri:
            logger.warning(
                f"OAuth login rejected untrusted redirect_uri from {request.client.host if request.client else 'unknown'}"
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid redirect_uri: must be a relative path or trusted domain",
            )

        # Encode state with CSRF token and optional redirect_uri
        state_data = {"csrf": csrf_token}
        if validated_redirect_uri:
            state_data["redirect_uri"] = validated_redirect_uri
            logger.info("OAuth login initiated with validated redirect_uri")

        # Base64 encode the state JSON
        state = base64.urlsafe_b64encode(json.dumps(state_data).encode()).decode()

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


def _load_oauth_config(provider: str) -> Dict[str, str]:
    """Load OAuth configuration for the specified provider."""
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"OAuth provider '{provider}' not configured")

    config = json.loads(oauth_config_file.read_text())
    if provider not in config:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"OAuth provider '{provider}' not configured")

    provider_config: Dict[str, str] = config[provider]
    return provider_config


async def _handle_google_oauth(code: str, client_id: str, client_secret: str) -> Dict[str, Optional[str]]:
    """Handle Google OAuth token exchange and user info retrieval."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        # Exchange code for token
        async with session.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": get_oauth_callback_url("google"),
                "grant_type": "authorization_code",
            },
        ) as token_response:
            if token_response.status != 200:
                error_text = await token_response.text()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to exchange code for token: {error_text}",
                )

            token_data = await token_response.json()
            access_token = token_data["access_token"]

        # Get user info
        async with session.get(
            "https://www.googleapis.com/oauth2/v2/userinfo", headers={"Authorization": f"Bearer {access_token}"}
        ) as user_response:
            if user_response.status != 200:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FETCH_USER_INFO_ERROR)

            user_info = await user_response.json()
            return {
                "external_id": user_info["id"],
                "email": user_info.get("email"),
                "name": user_info.get("name", user_info.get("email")),
                "picture": user_info.get("picture"),
            }


async def _handle_github_oauth(code: str, client_id: str, client_secret: str) -> Dict[str, Optional[str]]:
    """Handle GitHub OAuth token exchange and user info retrieval."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        # Exchange code for token
        async with session.post(
            "https://github.com/login/oauth/access_token",
            headers={"Accept": "application/json"},
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": os.getenv("OAUTH_CALLBACK_BASE_URL", DEFAULT_OAUTH_BASE_URL)
                + OAUTH_CALLBACK_PATH.replace("{provider}", "github"),
            },
        ) as token_response:
            if token_response.status != 200:
                error_text = await token_response.text()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to exchange code for token: {error_text}",
                )

            token_data = await token_response.json()
            access_token = token_data["access_token"]

        # Get user info
        async with session.get(
            "https://api.github.com/user", headers={"Authorization": f"token {access_token}"}
        ) as user_response:
            if user_response.status != 200:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FETCH_USER_INFO_ERROR)

            user_info = await user_response.json()
            external_id = str(user_info["id"])
            email = user_info.get("email")
            name = user_info.get("name", user_info.get("login"))
            picture = user_info.get("avatar_url")

        # If email is private, fetch from emails endpoint
        if not email:
            async with session.get(
                "https://api.github.com/user/emails", headers={"Authorization": f"token {access_token}"}
            ) as emails_response:
                if emails_response.status == 200:
                    emails = await emails_response.json()
                    for e in emails:
                        if e.get("primary"):
                            email = e["email"]
                            break

        return {
            "external_id": external_id,
            "email": email,
            "name": name,
            "picture": picture,
        }


async def _handle_discord_oauth(code: str, client_id: str, client_secret: str) -> Dict[str, Optional[str]]:
    """Handle Discord OAuth token exchange and user info retrieval."""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        # Exchange code for token
        async with session.post(
            "https://discord.com/api/oauth2/token",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": get_oauth_callback_url("discord"),
                "grant_type": "authorization_code",
            },
        ) as token_response:
            if token_response.status != 200:
                error_text = await token_response.text()
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Failed to exchange code for token: {error_text}",
                )

            token_data = await token_response.json()
            access_token = token_data["access_token"]

        # Get user info
        async with session.get(
            "https://discord.com/api/users/@me", headers={"Authorization": f"Bearer {access_token}"}
        ) as user_response:
            if user_response.status != 200:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=FETCH_USER_INFO_ERROR)

            user_info = await user_response.json()
            external_id = user_info["id"]
            email = user_info.get("email")
            name = user_info.get("username", email)

            # Construct Discord avatar URL if avatar exists
            avatar_hash = user_info.get("avatar")
            picture = f"https://cdn.discordapp.com/avatars/{external_id}/{avatar_hash}.png" if avatar_hash else None

            return {
                "external_id": external_id,
                "email": email,
                "name": name,
                "picture": picture,
            }


# =============================================================================
# ROLE DETERMINATION HELPER FUNCTIONS (extracted for cognitive complexity reduction)
# =============================================================================


def _is_ciris_admin_email(email: Optional[str]) -> bool:
    """Check if the email is a @ciris.ai domain email (gets automatic ADMIN role)."""
    return email is not None and email.endswith("@ciris.ai")


def _get_oauth_users_dict(auth_service: "APIAuthService") -> Optional[Dict[str, Any]]:
    """Get the _oauth_users dictionary from auth_service, or None if unavailable."""
    return getattr(auth_service, "_oauth_users", None)


def _lookup_existing_user_role(oauth_users: Dict[str, Any], provider: str, external_id: str) -> Optional[UserRole]:
    """Look up an existing OAuth user and return their role if found.

    Returns None if user not found.
    """
    user_id = f"{provider}:{external_id}"
    existing_user = oauth_users.get(user_id)

    if not existing_user:
        logger.debug(
            f"[AUTH DEBUG] No existing OAuth user found for {user_id}"
        )  # NOSONAR - provider:id format, not secret
        logger.debug(f"[AUTH DEBUG] Existing OAuth user count: {len(oauth_users)}")
        return None

    logger.debug(
        f"[AUTH DEBUG] Found existing OAuth user: {user_id}, role={existing_user.role}"
    )  # NOSONAR - role is not sensitive
    role = existing_user.role
    if isinstance(role, UserRole):
        return role
    return UserRole(role) if role else UserRole.OBSERVER


def _is_first_oauth_user(oauth_users: Optional[Dict[str, Any]]) -> bool:
    """Check if this would be the first OAuth user (empty oauth_users dict)."""
    return oauth_users is not None and len(oauth_users) == 0


def _check_stored_user_role(auth_service: "APIAuthService", provider: str, external_id: str) -> Optional[UserRole]:
    """Check for existing user in _users dict and return their role if found."""
    user_id = f"{provider}:{external_id}"
    stored_users = getattr(auth_service, "_users", {})
    stored_user = stored_users.get(user_id)

    if not stored_user:
        return None

    # User exists in database - preserve their role!
    logger.debug(  # NOSONAR - user_id is provider:id, roles are not sensitive
        f"[AUTH DEBUG] Found existing user in _users dict: {user_id}, "
        f"api_role={stored_user.api_role}, wa_role={stored_user.wa_role}"
    )

    # Convert APIRole to UserRole
    api_role_to_user_role = {
        "OBSERVER": UserRole.OBSERVER,
        "ADMIN": UserRole.ADMIN,
        "AUTHORITY": UserRole.ADMIN,  # AUTHORITY maps to ADMIN
        "SYSTEM_ADMIN": UserRole.SYSTEM_ADMIN,
        "SERVICE_ACCOUNT": UserRole.SYSTEM_ADMIN,  # Service accounts get full access
    }
    role_str = stored_user.api_role.value if hasattr(stored_user.api_role, "value") else str(stored_user.api_role)
    existing_user_role = api_role_to_user_role.get(role_str.upper(), UserRole.OBSERVER)
    logger.debug(f"[AUTH DEBUG] Mapped API role {role_str} to UserRole {existing_user_role}")
    return existing_user_role


def _check_first_oauth_user_status(
    auth_service: "APIAuthService", oauth_users: Optional[Dict[str, Any]], provider: str, external_id: Optional[str]
) -> bool:
    """Check if this is the first OAuth user (setup wizard scenario).

    IMPORTANT: We must check the _users dict (loaded from database) not just
    _oauth_users (in-memory only). After app restart, _oauth_users is empty
    but _users contains all users loaded from the database.
    """
    # Get users loaded from database - this is the authoritative source
    stored_users = getattr(auth_service, "_users", {})

    # If ANY users exist in the database, this is not the first user
    if stored_users:
        logger.debug(f"[AUTH DEBUG] Database has {len(stored_users)} existing users - not first user")
        return False

    # Also check in-memory oauth_users cache
    if oauth_users and len(oauth_users) > 0:
        logger.debug(f"[AUTH DEBUG] OAuth cache has {len(oauth_users)} users - not first user")
        return False

    # Check if this specific user already exists
    user_id_check: Optional[str] = f"{provider}:{external_id}" if external_id else None
    if user_id_check and user_id_check in stored_users:
        logger.debug(f"[AUTH DEBUG] User {user_id_check} already exists - not first user")
        return False

    logger.debug("[AUTH DEBUG] No existing users found - this is the first OAuth user")
    return True


def _determine_user_role(
    email: Optional[str],
    auth_service: Optional["APIAuthService"] = None,
    external_id: Optional[str] = None,
    provider: str = "google",
) -> UserRole:
    """Determine user role based on email domain, existing user status, and first-user status.

    For Android/native OAuth flow during setup, the first OAuth user gets
    SYSTEM_ADMIN role so they can see the default API channel history
    where agent wakeup messages are sent.

    IMPORTANT: If the user already exists with a higher role (e.g., from initial
    login before setup), preserve that role instead of demoting to OBSERVER.
    """
    masked_email = (email[:3] + "***@" + email.split("@")[-1]) if email and "@" in email else "None"
    logger.debug(
        f"[AUTH DEBUG] _determine_user_role called: email={masked_email}, external_id={external_id}, provider={provider}"
    )  # NOSONAR - email masked, external_id is provider ID

    # @ciris.ai users always get ADMIN
    if _is_ciris_admin_email(email):
        logger.debug("[AUTH DEBUG] Granting ADMIN role to @ciris.ai user")
        return UserRole.ADMIN

    # No auth service - return default role
    if auth_service is None:
        logger.debug("[AUTH DEBUG] No auth_service provided - returning OBSERVER role")
        return UserRole.OBSERVER

    try:
        oauth_users = _get_oauth_users_dict(auth_service)
        logger.debug("[AUTH DEBUG] _oauth_users count: %d", len(oauth_users) if oauth_users else 0)

        # Check if this user already exists with a role - preserve their existing role
        if external_id and oauth_users:
            existing_role = _lookup_existing_user_role(oauth_users, provider, external_id)
            if existing_role is not None:
                return existing_role

        # Check _users dict (for users loaded from database via OAuth link during setup)
        if external_id:
            stored_role = _check_stored_user_role(auth_service, provider, external_id)
            if stored_role is not None:
                return stored_role

        # Check if this is the first OAuth user (setup wizard scenario)
        if _check_first_oauth_user_status(auth_service, oauth_users, provider, external_id):
            logger.debug("[AUTH DEBUG] First OAuth user detected - granting SYSTEM_ADMIN role for setup wizard user")
            return UserRole.SYSTEM_ADMIN

    except (TypeError, AttributeError) as e:
        # Mock objects or missing attributes - fall through to OBSERVER
        logger.warning("[AUTH DEBUG] Exception accessing auth_service: %s", type(e).__name__)

    logger.debug("[AUTH DEBUG] No special conditions met - returning OBSERVER role")
    return UserRole.OBSERVER


def _reject_observer_on_personal_install(user_role: UserRole, email: Optional[str]) -> None:
    """Reject OBSERVER role OAuth logins on mobile (Android/iOS) installs.

    Mobile installs are single-user partnership deployments on personal devices.
    Only the founding partner (setup user) should have access.
    Observer accounts are for server/desktop deployments where multiple users
    may need read-only access to the agent.

    Note: This only applies to mobile platforms where we can reliably detect
    "personal install". Desktop and standalone servers allow OBSERVER logins.

    Raises:
        HTTPException: If OBSERVER login attempted on mobile platform
    """
    from ciris_engine.logic.utils.path_resolution import is_android, is_ios

    is_mobile_platform = is_android() or is_ios()
    if user_role == UserRole.OBSERVER and is_mobile_platform:
        masked_email = (email[:3] + "***@" + email.split("@")[-1]) if email and "@" in email else "unknown"
        logger.warning(f"[AUTH] Rejecting OBSERVER login on personal install: {masked_email}")  # NOSONAR - email masked
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "auth_personal_install_observer_blocked",
                "message": "This is a personal CIRIS installation. Only the owner can sign in. "
                "If you are the owner, please use the same account you used during setup.",
            },
        )


def _store_oauth_profile(auth_service: APIAuthService, user_id: str, name: str, picture: Optional[str]) -> None:
    """Store OAuth profile data if valid."""
    if not picture:
        return

    if validate_oauth_picture_url(picture):
        user = auth_service.get_user(user_id)
        if user:
            user.oauth_name = name
            user.oauth_picture = picture
            auth_service._users[user_id] = user
    else:
        logger.warning(f"Invalid OAuth picture URL rejected for user {user_id}: {picture}")


def _update_billing_provider_token(google_id_token: str) -> None:
    """Update the billing provider with a fresh OAuth ID token.

    This is called after native Google/Apple token exchange to ensure billing
    is available immediately. The token is stored in the environment
    so the billing provider can use it for credit checks.
    """
    import os

    # Update both environment variables so billing provider picks it up
    # regardless of which env var it checks (Google on Android, Apple on iOS)
    os.environ["CIRIS_BILLING_GOOGLE_ID_TOKEN"] = google_id_token
    os.environ["CIRIS_BILLING_APPLE_ID_TOKEN"] = google_id_token
    logger.info(
        "[NativeAuth] Updated CIRIS_BILLING_GOOGLE_ID_TOKEN and CIRIS_BILLING_APPLE_ID_TOKEN in environment for billing provider"
    )

    # Try to reinitialize the billing provider if resource_monitor is available
    # This is done via a background task to not block the login response
    try:
        from ciris_engine.logic.services.infrastructure.resource_monitor import CIRISBillingProvider

        # Check if we have access to the app state (will be set by FastAPI)
        # The billing provider will be initialized on the next credit check if not done here
        logger.debug("[NativeAuth] Billing provider token updated")
    except Exception as e:
        logger.warning(f"[NativeAuth] Could not update billing provider directly: {e}")


def _generate_api_key_and_store(auth_service: APIAuthService, oauth_user: OAuthUser, provider: str) -> str:
    """Generate API key and store it for the OAuth user."""
    # SYSTEM_ADMIN, ADMIN, and AUTHORITY all get admin prefix (elevated roles)
    # OBSERVER gets observer prefix
    elevated_roles = (UserRole.ADMIN, UserRole.SYSTEM_ADMIN, UserRole.AUTHORITY)
    is_elevated = oauth_user.role in elevated_roles
    role_prefix = "ciris_admin" if is_elevated else "ciris_observer"
    logger.info(
        f"[AUTH DEBUG] Generating API key for user {oauth_user.user_id} with role {oauth_user.role}, prefix: {role_prefix}"
    )
    api_key = f"{role_prefix}_{secrets.token_urlsafe(32)}"
    expires_at = datetime.now(timezone.utc) + timedelta(days=30)

    auth_service.store_api_key(
        key=api_key,
        user_id=oauth_user.user_id,
        role=oauth_user.role,
        expires_at=expires_at,
        description=f"OAuth login via {provider}",
    )

    return api_key


def _build_redirect_response(
    api_key: str,
    oauth_user: OAuthUser,
    provider: str,
    redirect_uri: Optional[str] = None,
    email: Optional[str] = None,
    marketing_opt_in: Optional[bool] = None,
) -> RedirectResponse:
    """
    Build the redirect response for OAuth callback.

    Supports flexible parameter configuration via OAUTH_REDIRECT_PARAMS environment variable.

    Args:
        api_key: Generated API key for the user
        oauth_user: OAuth user object with role and user_id
        provider: OAuth provider name (google, github, discord)
        redirect_uri: Optional redirect URI from state parameter
        email: User email from OAuth provider
        marketing_opt_in: Marketing opt-in preference from redirect_uri

    Environment Variables:
        OAUTH_FRONTEND_URL: Frontend base URL (e.g., https://scout.ciris.ai)
        OAUTH_FRONTEND_PATH: Frontend callback path (default: /oauth-complete.html)
        OAUTH_REDIRECT_PARAMS: Comma-separated list of parameters to include in redirect
    """
    import urllib.parse

    VALID_PROVIDERS = {"google", "github", "discord"}
    if provider not in VALID_PROVIDERS:
        # Redirect to a safe default if provider is invalid
        return RedirectResponse(url="/", status_code=302)

    # Build all available parameters
    all_params = {
        "access_token": api_key,
        "token_type": "Bearer",
        "expires_in": "2592000",  # 30 days
        "role": oauth_user.role.value,
        "user_id": oauth_user.user_id,
        "email": email or "",
        "marketing_opt_in": str(marketing_opt_in).lower() if marketing_opt_in is not None else "",
        "agent": AGENT_ID,
        "provider": provider,
    }

    # Filter to only include configured parameters
    redirect_params = {k: v for k, v in all_params.items() if k in OAUTH_REDIRECT_PARAMS and v}

    query_string = urllib.parse.urlencode(redirect_params)

    # Determine redirect URL with priority:
    # 1. Explicit redirect_uri from state parameter (highest priority)
    # 2. OAUTH_FRONTEND_URL + OAUTH_FRONTEND_PATH
    # 3. Relative path fallback (backward compatibility)

    if redirect_uri:
        # Parse existing query parameters from redirect_uri
        parsed = urllib.parse.urlparse(redirect_uri)
        base_redirect_uri = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"

        # Merge existing params with new params (new params take precedence for security)
        existing_params = dict(urllib.parse.parse_qsl(parsed.query))
        merged_params = {**existing_params, **redirect_params}  # Server params override if conflict

        query_string = urllib.parse.urlencode(merged_params)
        redirect_url = f"{base_redirect_uri}?{query_string}"
        logger.info(
            f"Redirecting OAuth user to provided redirect_uri with {len(existing_params)} existing params: {base_redirect_uri}"
        )
    elif OAUTH_FRONTEND_URL:
        # Use configured frontend URL
        redirect_url = f"{OAUTH_FRONTEND_URL}{OAUTH_FRONTEND_PATH}?{query_string}"
        logger.info(f"Redirecting OAuth user to configured frontend: {OAUTH_FRONTEND_URL}{OAUTH_FRONTEND_PATH}")
    else:
        # Backward compatibility: relative path
        gui_callback_url = f"/oauth/{AGENT_ID}/{provider}/callback"
        redirect_url = f"{gui_callback_url}?{query_string}"
        # Do NOT log the full redirect_url with sensitive credentials (access_token, api_key)
        logger.warning(
            f"No redirect_uri or OAUTH_FRONTEND_URL configured, using relative path: {gui_callback_url} "
            "(query params redacted for security)"
        )

    return RedirectResponse(url=redirect_url, status_code=302)


async def _trigger_billing_credit_check_if_enabled(
    request: Request,
    oauth_user: OAuthUser,
    user_email: Optional[str] = None,
    marketing_opt_in: Optional[bool] = None,
) -> None:
    """
    Trigger billing credit check if billing is enabled.

    This ensures the billing user is created on first OAuth login so the frontend
    can display available credits immediately. Only runs if resource_monitor with
    credit_provider is configured.

    Args:
        request: FastAPI request object
        oauth_user: OAuth user object with provider, external_id, user_id, role
        user_email: User email from OAuth provider (REQUIRED for billing backend)
        marketing_opt_in: Marketing opt-in preference (REQUIRED for billing backend)
    """
    # Check if resource_monitor exists (billing may not be enabled)
    if not hasattr(request.app.state, "resource_monitor"):
        logger.debug("No resource_monitor configured - skipping billing credit check")
        return

    resource_monitor = request.app.state.resource_monitor

    # Check if credit provider is configured
    if not hasattr(resource_monitor, "credit_provider") or resource_monitor.credit_provider is None:
        logger.debug("No credit_provider configured - skipping billing credit check")
        return

    # Perform credit check to ensure billing user is created
    try:
        from ciris_engine.schemas.services.credit_gate import CreditAccount, CreditContext

        # Extract provider and external_id from oauth_user.user_id (format: "provider:external_id")
        oauth_provider = oauth_user.provider
        external_id = oauth_user.external_id

        account = CreditAccount(
            provider=f"oauth:{oauth_provider}",
            account_id=external_id,
            authority_id=oauth_user.user_id,
            tenant_id=None,
            customer_email=user_email,  # Pass email to billing backend
            marketing_opt_in=marketing_opt_in,  # Pass marketing preference to billing backend
        )

        context = CreditContext(
            agent_id=AGENT_ID,
            channel_id="oauth:callback",
            request_id=None,
            user_role=oauth_user.role.value.lower(),  # Pass user role to billing backend
        )

        result = await resource_monitor.check_credit(account, context)

        logger.info(
            f"Billing credit check for {oauth_user.user_id}: has_credit={result.has_credit}, "
            f"email={user_email}, marketing_opt_in={marketing_opt_in}, role={oauth_user.role.value}, "
            f"provider={resource_monitor.credit_provider.__class__.__name__}"
        )

    except Exception as e:
        # Don't fail OAuth login if billing check fails
        logger.warning(f"Billing credit check failed for {oauth_user.user_id}: {e}")


@router.get("/auth/oauth/{provider}/callback")
async def oauth_callback(
    provider: str,
    code: str,
    state: str,
    request: Request,
    auth_service: AuthServiceDep,
    marketing_opt_in: bool = False,
) -> RedirectResponse:
    """
    Handle OAuth callback.

    Exchanges authorization code for tokens and creates/updates user.
    Extracts marketing_opt_in from redirect_uri if present.
    """
    try:
        # Decode state parameter to extract redirect_uri
        import base64
        import json

        redirect_uri = None
        marketing_opt_in_from_uri = None

        try:
            state_json = base64.urlsafe_b64decode(state.encode()).decode()
            state_data = json.loads(state_json)
            redirect_uri = state_data.get("redirect_uri")

            # Defense-in-depth: Re-validate redirect_uri even from state
            # (state could theoretically be tampered with)
            redirect_uri = validate_redirect_uri(redirect_uri)

            # Extract marketing_opt_in from redirect_uri query parameters
            if redirect_uri:
                uri_params = extract_query_params(redirect_uri)
                marketing_opt_in_str = uri_params.get("marketing_opt_in", "").lower()
                if marketing_opt_in_str in ("true", "1", "yes"):
                    marketing_opt_in_from_uri = True
                elif marketing_opt_in_str in ("false", "0", "no"):
                    marketing_opt_in_from_uri = False

            logger.debug(f"Decoded state: redirect_uri={redirect_uri}, marketing_opt_in={marketing_opt_in_from_uri}")
        except Exception as e:
            # If state decode fails, log but continue (backward compatibility)
            logger.warning(f"Failed to decode state parameter: {e}. Using default redirect.")

        # Use marketing_opt_in from redirect_uri if available, otherwise use query param
        final_marketing_opt_in = (
            marketing_opt_in_from_uri if marketing_opt_in_from_uri is not None else marketing_opt_in
        )

        # Load OAuth configuration
        provider_config = _load_oauth_config(provider)
        client_id = provider_config["client_id"]
        client_secret = provider_config["client_secret"]

        # Handle provider-specific OAuth flow
        if provider == "google":
            user_data = await _handle_google_oauth(code, client_id, client_secret)
        elif provider == "github":
            user_data = await _handle_github_oauth(code, client_id, client_secret)
        elif provider == "discord":
            user_data = await _handle_discord_oauth(code, client_id, client_secret)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported OAuth provider: {provider}"
            )

        # Validate required fields first (need external_id for role determination)
        external_id = user_data["external_id"]
        if not external_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="OAuth provider did not return user ID")

        # Ensure users are loaded from DB before role determination (fixes role demotion bug)
        await auth_service._ensure_users_loaded()
        # Determine user role (preserves existing role if user already exists)
        user_email = user_data["email"]
        user_role = _determine_user_role(user_email, auth_service, external_id=external_id, provider=provider)

        # Block observer logins on personal (desktop/mobile) installs
        _reject_observer_on_personal_install(user_role, user_email)

        oauth_user = auth_service.create_oauth_user(
            provider=provider,
            external_id=external_id,
            email=user_email,
            name=user_data["name"],
            role=user_role,
            marketing_opt_in=final_marketing_opt_in,
        )

        # Store OAuth profile data
        name = user_data["name"] or "Unknown"
        _store_oauth_profile(auth_service, oauth_user.user_id, name, user_data["picture"])

        # Generate API key and store it
        api_key = _generate_api_key_and_store(auth_service, oauth_user, provider)

        logger.info(f"OAuth user {oauth_user.user_id} logged in successfully via {provider}")

        # Trigger billing credit check if billing is enabled
        # This ensures billing user is created and credits are initialized
        # so the frontend can display available credits immediately
        await _trigger_billing_credit_check_if_enabled(
            request, oauth_user, user_email=user_email, marketing_opt_in=final_marketing_opt_in
        )

        # Build and return redirect response with email and marketing preference
        return _build_redirect_response(
            api_key=api_key,
            oauth_user=oauth_user,
            provider=provider,
            redirect_uri=redirect_uri,
            email=user_email,
            marketing_opt_in=final_marketing_opt_in,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"OAuth callback error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"OAuth callback failed: {str(e)}"
        )


# ========== Native App Token Exchange Endpoints ==========


class NativeTokenRequest(BaseModel):
    """Request model for native app token exchange."""

    id_token: str = Field(..., description="Google ID token from native Sign-In")
    provider: str = Field(default="google", description="OAuth provider (currently only 'google' supported)")


class NativeTokenResponse(BaseModel):
    """Response model for native app token exchange."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user_id: str
    role: str
    email: Optional[str] = None
    name: Optional[str] = None


# =============================================================================
# TOKEN VERIFICATION HELPER FUNCTIONS (extracted for cognitive complexity reduction)
# =============================================================================

# Valid Google issuers - constant
VALID_GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}


def _get_allowed_audiences_from_config() -> Optional[Set[str]]:
    """Load allowed audiences from OAuth config.

    Returns None if OAuth is not configured (on-device mode).
    On-device mode skips audience validation since the Android app
    has its own client ID and we can't know it ahead of time.
    """
    try:
        provider_config = _load_oauth_config("google")
        expected_client_id = provider_config.get("client_id")
        android_client_id = provider_config.get("android_client_id")
        allowed_audiences: Set[str] = set()
        if expected_client_id:
            allowed_audiences.add(expected_client_id)
        if android_client_id:
            allowed_audiences.add(android_client_id)
        logger.debug("[NativeAuth] Configured allowed audiences count: %d", len(allowed_audiences))
        return allowed_audiences if allowed_audiences else None
    except HTTPException:
        # On-device mode: OAuth not configured, skip audience validation
        logger.debug("[NativeAuth] No OAuth config found - running in on-device mode")
        return None


def _validate_token_audience(token_aud: Optional[str], allowed_audiences: Optional[Set[str]]) -> None:
    """Validate token audience matches our configured client ID.

    If allowed_audiences is None (on-device mode), validation is skipped.
    Raises HTTPException if validation fails.
    """
    if allowed_audiences is None:
        # On-device mode: skip audience validation
        logger.debug("[NativeAuth] On-device mode: skipping audience validation")
        return

    if not token_aud or token_aud not in allowed_audiences:
        logger.error(  # NOSONAR - security audit logging, client IDs are public config
            f"[NativeAuth] SECURITY: Token audience mismatch! "
            f"Got: {token_aud}, Expected one of: {allowed_audiences}"
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token was not issued for this application (audience mismatch).",
        )


def _validate_token_issuer(token_iss: Optional[str]) -> None:
    """Validate token issuer is Google.

    Raises HTTPException if validation fails.
    """
    if not token_iss or token_iss not in VALID_GOOGLE_ISSUERS:
        logger.error(f"[NativeAuth] SECURITY: Invalid issuer! Got: {token_iss}, Expected: {VALID_GOOGLE_ISSUERS}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token was not issued by Google (issuer mismatch).",
        )


def _validate_token_expiry(token_exp: Optional[str]) -> None:
    """Validate token is not expired.

    Raises HTTPException if validation fails.
    """
    import time

    if not token_exp:
        return

    try:
        exp_timestamp = int(token_exp)
        current_time = int(time.time())
        if exp_timestamp < current_time:
            logger.error(f"[NativeAuth] SECURITY: Token expired! exp: {exp_timestamp}, now: {current_time}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google ID token has expired. Please sign in again.",
            )
    except (ValueError, TypeError):
        logger.error(f"[NativeAuth] Invalid exp claim format: {token_exp}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has invalid expiry format.",
        )


def _validate_token_sub_claim(sub: Optional[str]) -> None:
    """Validate that the sub (user ID) claim exists.

    Raises HTTPException if validation fails.
    """
    if not sub:
        logger.error("[NativeAuth] Token missing required 'sub' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google ID token missing user ID (sub claim).",
        )


def _log_email_verification_warning(token_info: Dict[str, Any]) -> None:
    """Log a warning if email is not verified."""
    email_verified = token_info.get("email_verified")
    if email_verified is not None and str(email_verified).lower() not in ("true", "1"):
        logger.warning(f"[NativeAuth] Email not verified for user {token_info.get('sub')}")


def _decode_google_jwt_locally(id_token: str) -> Dict[str, Optional[str]]:
    """
    Decode a Google ID token locally without calling Google's API.

    This is a fallback for on-device mode when the Google tokeninfo API
    is unreachable. The token is trusted because it came from Google Sign-In
    SDK running on the device, which already verified it cryptographically.

    WARNING: This does NOT verify the token signature. Only use this as a
    fallback when the token is known to come from the native Google SDK.
    """
    import base64
    import json
    import time

    logger.debug("[NativeAuth] Decoding Google JWT locally (fallback mode)...")

    try:
        # JWT has 3 parts: header.payload.signature
        parts = id_token.split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid JWT format: expected 3 parts, got {len(parts)}")

        # Decode the payload (second part) - use URL-safe base64
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        logger.debug("[NativeAuth] Local decode successful")

        # Basic validation
        exp = payload.get("exp")
        if exp and int(exp) < time.time():
            raise ValueError("Token has expired")

        iss = payload.get("iss")
        if iss not in ("accounts.google.com", "https://accounts.google.com"):
            raise ValueError(f"Invalid issuer: {iss}")

        # Extract user info
        return {
            "external_id": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name"),
            "picture": payload.get("picture"),
        }

    except Exception as e:
        logger.error(f"[NativeAuth] Local JWT decode failed: {type(e).__name__}: {e}")
        raise


async def _call_google_tokeninfo_api(id_token: str) -> Dict[str, Any]:
    """Call Google's tokeninfo API and return the response JSON."""
    import aiohttp

    logger.debug("[NativeAuth] Calling Google tokeninfo API...")

    client_timeout = aiohttp.ClientTimeout(total=10.0)
    async with aiohttp.ClientSession(timeout=client_timeout) as session:
        # Use params dict for proper URL encoding of the token
        async with session.get("https://oauth2.googleapis.com/tokeninfo", params={"id_token": id_token}) as response:
            logger.debug("[NativeAuth] Google tokeninfo response: %d", response.status)

            if response.status != 200:
                error_text = await response.text()
                logger.error(f"[NativeAuth] Google API rejected token: {response.status} - {error_text}")
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Google could not verify this ID token. It may be expired, malformed, or invalid.",
                )

            token_info: Dict[str, Any] = await response.json()
            return token_info


def _validate_all_token_claims(token_info: Dict[str, Any], allowed_audiences: Optional[Set[str]]) -> None:
    """Validate all required token claims (audience, issuer, expiry, sub)."""
    # SECURITY: Validate all token claims
    _validate_token_audience(token_info.get("aud"), allowed_audiences)
    _validate_token_issuer(token_info.get("iss"))
    _validate_token_expiry(token_info.get("exp"))
    _log_email_verification_warning(token_info)
    _validate_token_sub_claim(token_info.get("sub"))


def _extract_user_info_from_token(token_info: Dict[str, Any]) -> Dict[str, Optional[str]]:
    """Extract user information from validated token."""
    sub = token_info.get("sub")
    logger.debug("[NativeAuth] Token verified successfully")

    return {
        "external_id": sub,
        "email": token_info.get("email"),
        "name": token_info.get("name"),
        "picture": token_info.get("picture"),
    }


async def _verify_google_id_token(id_token: str) -> Dict[str, Optional[str]]:
    """
    Verify a Google ID token and extract user info.

    This verifies tokens from native Android/iOS Google Sign-In using
    Google's tokeninfo API with full security validation:
    - Validates audience (aud) matches our configured client ID
    - Validates issuer (iss) is accounts.google.com
    - Validates token is not expired (exp)
    - Validates email is verified

    SECURITY: No fallback path exists. Tokens MUST be verified by Google
    with proper audience/issuer/expiry validation before user creation.
    """
    import asyncio

    import aiohttp

    logger.debug("[NativeAuth] Verifying Google ID token")

    # Load our expected client ID from OAuth config
    allowed_audiences = _get_allowed_audiences_from_config()

    # Verify with Google's tokeninfo endpoint
    try:
        token_info = await _call_google_tokeninfo_api(id_token)

        logger.debug("[NativeAuth] Token info received from Google")

        # Validate all token claims
        _validate_all_token_claims(token_info, allowed_audiences)

        # Extract and return user info
        return _extract_user_info_from_token(token_info)

    except HTTPException:
        raise
    except asyncio.TimeoutError:
        logger.warning("[NativeAuth] Google tokeninfo API timed out")
        # On-device fallback: if we can't reach Google, decode the JWT locally
        # This is safe because the token came from Google Sign-In SDK on the device
        # which already verified it cryptographically
        logger.debug("[NativeAuth] Attempting local JWT decode fallback for on-device mode...")
        try:
            return _decode_google_jwt_locally(id_token)
        except Exception as fallback_error:
            logger.error(f"[NativeAuth] Local JWT fallback also failed: {fallback_error}")
            raise HTTPException(
                status_code=status.HTTP_504_GATEWAY_TIMEOUT,
                detail="Google verification service timed out. Please try again.",
            )
    except aiohttp.ClientError as e:
        logger.error(f"[NativeAuth] Network error calling Google API: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Could not reach Google verification service. Please check your connection.",
        )
    except Exception as e:
        logger.error(f"[NativeAuth] Unexpected error during token verification: {type(e).__name__}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Token verification failed due to an internal error.",
        )


@router.post("/auth/native/google")
async def native_google_token_exchange(
    native_request: NativeTokenRequest,
    fastapi_request: Request,
    auth_service: AuthServiceDep,
) -> NativeTokenResponse:
    """
    Exchange a native Google ID token for a CIRIS API token.

    This endpoint is used by native Android/iOS apps that perform Google Sign-In
    directly and need to exchange their Google ID token for a CIRIS API token.

    Unlike the web OAuth flow (which uses authorization codes), native apps get
    ID tokens directly from Google Sign-In SDK and send them here.
    """
    logger.debug("[NativeAuth] Native Google token exchange request")

    if native_request.provider != "google":
        logger.warning("[NativeAuth] Unsupported provider requested")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 'google' provider is currently supported for native token exchange",
        )

    try:
        # Verify the Google ID token and get user info
        logger.debug("[NativeAuth] Starting token verification...")
        user_data = await _verify_google_id_token(native_request.id_token)
        logger.debug("[NativeAuth] Token verification complete")

        external_id = user_data.get("external_id")
        if not external_id:
            logger.error("[NativeAuth] No external_id in user_data")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Google ID token did not contain user ID"
            )

        user_email = user_data.get("email")
        # Ensure users are loaded from DB before role determination (fixes role demotion bug)
        await auth_service._ensure_users_loaded()
        # Pass external_id to preserve existing user's role (don't demote on re-auth!)
        user_role = _determine_user_role(user_email, auth_service, external_id=external_id, provider="google")
        logger.debug("[NativeAuth] Determined role: %s", user_role)

        # Block observer logins on personal (desktop/mobile) installs
        _reject_observer_on_personal_install(user_role, user_email)

        # Create or get OAuth user
        oauth_user = auth_service.create_oauth_user(
            provider="google",
            external_id=external_id,
            email=user_email,
            name=user_data.get("name"),
            role=user_role,
            marketing_opt_in=False,
        )
        logger.debug("[NativeAuth] OAuth user created/retrieved")

        # Store OAuth profile data
        name = user_data.get("name") or "Unknown"
        _store_oauth_profile(auth_service, oauth_user.user_id, name, user_data.get("picture"))

        # Auto-mint SYSTEM_ADMIN users as WA with ROOT role so they can handle deferrals
        logger.debug("[NativeAuth] Checking auto-mint for role %s", oauth_user.role)
        await _auto_mint_system_admin_if_needed(oauth_user, auth_service, "NativeAuth")

        # Generate API key
        api_key = _generate_api_key_and_store(auth_service, oauth_user, "google")

        # Update billing provider with the Google ID token for credit checks
        # This ensures billing is available immediately after login
        _update_billing_provider_token(native_request.id_token)

        # Trigger billing credit check to create billing user (same as webview OAuth flow)
        # This ensures the billing user record is created so getBalance() returns correct credits
        await _trigger_billing_credit_check_if_enabled(
            fastapi_request, oauth_user, user_email=user_email, marketing_opt_in=False
        )

        logger.info("[NativeAuth] Native Google login successful")

        return NativeTokenResponse(
            access_token=api_key,
            token_type="bearer",
            expires_in=2592000,  # 30 days in seconds
            user_id=oauth_user.user_id,
            role=oauth_user.role.value,
            email=user_email,
            name=user_data.get("name"),
        )

    except HTTPException as e:
        logger.error(f"[NativeAuth] HTTP error: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        logger.error(f"[NativeAuth] Unexpected error: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Native token exchange failed: {str(e)}"
        )


# ========== Apple Native Auth ==========


class AppleNativeTokenRequest(BaseModel):
    """Request model for Apple native app token exchange."""

    id_token: str = Field(..., description="Apple ID token (JWT) from native Sign-In")
    provider: str = Field(default="apple", description="OAuth provider (always 'apple')")


def _decode_apple_jwt_locally(id_token: str) -> Dict[str, Optional[str]]:
    """
    Decode an Apple ID token locally without calling Apple's API.

    Apple ID tokens are JWTs signed with RS256. For on-device mode,
    we trust the token because it came from Apple Sign-In SDK running
    on the device, which already verified it cryptographically.

    In production, you would verify the signature against Apple's public keys.
    """
    import base64
    import json
    import time

    logger.info("[AppleNativeAuth] Decoding Apple JWT locally...")

    try:
        # JWT has 3 parts: header.payload.signature
        parts = id_token.split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid JWT format: expected 3 parts, got {len(parts)}")

        # Decode the payload (second part) - use URL-safe base64
        payload_b64 = parts[1]
        # Add padding if needed
        padding = 4 - len(payload_b64) % 4
        if padding != 4:
            payload_b64 += "=" * padding

        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        logger.info(f"[AppleNativeAuth] Local decode - sub: {payload.get('sub')}, email: {payload.get('email')}")

        # Basic validation
        exp = payload.get("exp")
        if exp and int(exp) < time.time():
            raise ValueError("Token has expired")

        iss = payload.get("iss")
        if iss != "https://appleid.apple.com":
            raise ValueError(f"Invalid issuer: {iss}")

        # Extract user info
        return {
            "external_id": payload.get("sub"),
            "email": payload.get("email"),
            "name": payload.get("name"),  # Apple doesn't include name in JWT after first auth
            "picture": None,  # Apple doesn't provide picture URLs
        }

    except Exception as e:
        logger.error(f"[AppleNativeAuth] Local JWT decode failed: {type(e).__name__}: {e}")
        raise


async def _verify_apple_id_token(id_token: str) -> Dict[str, Optional[str]]:
    """
    Verify an Apple ID token and extract user info.

    For on-device mode, we decode the JWT locally since it came from
    the Apple Sign-In SDK which already verified it cryptographically.

    In production with network access, you could optionally verify
    the signature against Apple's public keys at:
    https://appleid.apple.com/auth/keys
    """
    logger.info(f"[AppleNativeAuth] Verifying Apple ID token (length: {len(id_token)})")

    # For on-device mode, decode locally
    # The token is trusted because it came from Apple Sign-In SDK
    return _decode_apple_jwt_locally(id_token)


async def _auto_mint_system_admin_if_needed(
    oauth_user: OAuthUser, auth_service: APIAuthService, log_prefix: str
) -> None:
    """Auto-mint SYSTEM_ADMIN users as WA with ROOT role for handling deferrals.

    Args:
        oauth_user: The OAuth user to potentially mint
        auth_service: The auth service for minting
        log_prefix: Logging prefix for trace context
    """
    if oauth_user.role != UserRole.SYSTEM_ADMIN:
        logger.info(f"CIRIS_USER_CREATE: [{log_prefix}] Not SYSTEM_ADMIN, skipping auto-mint")
        return

    existing_user = auth_service.get_user(oauth_user.user_id)
    logger.info(f"CIRIS_USER_CREATE: [{log_prefix}] existing_user lookup: {existing_user}")

    if existing_user:
        logger.info(f"CIRIS_USER_CREATE: [{log_prefix}]   wa_id={existing_user.wa_id}, wa_role={existing_user.wa_role}")

    needs_minting = not existing_user or not existing_user.wa_id or existing_user.wa_id == oauth_user.user_id

    if not needs_minting:
        logger.info(f"CIRIS_USER_CREATE: [{log_prefix}] User {oauth_user.user_id} already minted as WA - skipping")
        return

    logger.info(
        f"CIRIS_USER_CREATE: [{log_prefix}] Auto-minting SYSTEM_ADMIN user {oauth_user.user_id} as WA with ROOT role"
    )
    try:
        from ciris_engine.schemas.services.authority_core import WARole

        await auth_service.mint_wise_authority(
            user_id=oauth_user.user_id,
            wa_role=WARole.ROOT,
            minted_by="system_auto_mint",
        )
        logger.info(f"CIRIS_USER_CREATE: [{log_prefix}] ✅ Successfully auto-minted {oauth_user.user_id} as ROOT WA")
    except Exception as mint_error:
        logger.warning(f"CIRIS_USER_CREATE: [{log_prefix}] Auto-mint failed (user can mint manually): {mint_error}")


@router.post("/auth/native/apple")
async def native_apple_token_exchange(
    native_request: AppleNativeTokenRequest,
    fastapi_request: Request,
    auth_service: AuthServiceDep,
) -> NativeTokenResponse:
    """
    Exchange a native Apple ID token for a CIRIS API token.

    This endpoint is used by native iOS apps that perform Apple Sign-In
    directly and need to exchange their Apple ID token for a CIRIS API token.

    Unlike the web OAuth flow (which uses authorization codes), native apps get
    ID tokens directly from Apple Sign-In SDK and send them here.
    """
    logger.info("[AppleNativeAuth] Native Apple token exchange request")

    if native_request.provider != "apple":
        logger.warning(f"[AppleNativeAuth] Unsupported provider: {native_request.provider}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 'apple' provider is supported for this endpoint",
        )

    try:
        # Verify the Apple ID token and get user info
        logger.info("[AppleNativeAuth] Starting token verification...")
        user_data = await _verify_apple_id_token(native_request.id_token)
        logger.info(f"[AppleNativeAuth] Token verification complete - external_id: {user_data.get('external_id')}")

        external_id = user_data.get("external_id")
        if not external_id:
            logger.error("[AppleNativeAuth] No external_id in user_data")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Apple ID token did not contain user ID"
            )

        user_email = user_data.get("email")
        # Ensure users are loaded from DB before role determination (fixes role demotion bug)
        await auth_service._ensure_users_loaded()
        # Pass external_id to preserve existing user's role (don't demote on re-auth!)
        user_role = _determine_user_role(user_email, auth_service, external_id=external_id, provider="apple")
        logger.info(f"[AppleNativeAuth] Determined role for {user_email}: {user_role}")

        # Block observer logins on personal (desktop/mobile) installs
        _reject_observer_on_personal_install(user_role, user_email)

        # Create or get OAuth user
        logger.info(f"[AppleNativeAuth] Creating/getting OAuth user - external_id: {external_id}, email: {user_email}")
        oauth_user = auth_service.create_oauth_user(
            provider="apple",
            external_id=external_id,
            email=user_email,
            name=user_data.get("name"),
            role=user_role,
            marketing_opt_in=False,
        )
        logger.info(f"[AppleNativeAuth] OAuth user created/retrieved - user_id: {oauth_user.user_id}")

        # Auto-mint SYSTEM_ADMIN users as WA with ROOT role so they can handle deferrals
        logger.info(
            f"CIRIS_USER_CREATE: [AppleNativeAuth] Checking auto-mint for {oauth_user.user_id} with role {oauth_user.role}"
        )
        await _auto_mint_system_admin_if_needed(oauth_user, auth_service, "AppleNativeAuth")

        # Generate API key
        logger.info(f"[AppleNativeAuth] Generating API key for user {oauth_user.user_id}")
        api_key = _generate_api_key_and_store(auth_service, oauth_user, "apple")

        # Update billing provider with the Apple ID token for credit checks
        # The billing backend accepts Apple tokens (same as Google flow)
        _update_billing_provider_token(native_request.id_token)

        # Trigger billing credit check to create billing user
        logger.info(f"[AppleNativeAuth] Triggering billing credit check for user {oauth_user.user_id}")
        await _trigger_billing_credit_check_if_enabled(
            fastapi_request, oauth_user, user_email=user_email, marketing_opt_in=False
        )

        logger.info(f"[AppleNativeAuth] SUCCESS - Native Apple user {oauth_user.user_id} logged in, token generated")

        return NativeTokenResponse(
            access_token=api_key,
            token_type="bearer",
            expires_in=2592000,  # 30 days in seconds
            user_id=oauth_user.user_id,
            role=oauth_user.role.value,
            email=user_email,
            name=user_data.get("name"),
        )

    except HTTPException as e:
        logger.error(f"[AppleNativeAuth] HTTP error: {e.status_code} - {e.detail}")
        raise
    except Exception as e:
        logger.error(f"[AppleNativeAuth] Unexpected error: {type(e).__name__}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Apple native token exchange failed: {str(e)}"
        )


# ========== API Key Management Endpoints ==========


@router.post("/auth/api-keys")
async def create_api_key(
    request: APIKeyCreateRequest,
    auth: AuthDep,
    auth_service: AuthServiceDep,
) -> APIKeyResponse:
    """
    Create a new API key for the authenticated user.

    Users can create API keys for their OAuth identity with configurable expiry (30min - 7 days).
    The key is only shown once and cannot be retrieved later.
    """
    # Calculate expiration based on minutes
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=request.expires_in_minutes)

    # Generate API key with user's current role
    api_key = f"ciris_{auth.role.value.lower()}_{secrets.token_urlsafe(32)}"

    # Store API key
    auth_service.store_api_key(
        key=api_key,
        user_id=auth.user_id,
        role=auth.role,
        expires_at=expires_at,
        description=request.description,
        created_by=auth.user_id,
    )

    logger.info(f"User {auth.user_id} created API key with {request.expires_in_minutes}min expiry")

    return APIKeyResponse(
        api_key=api_key,
        role=auth.role,
        expires_at=expires_at,
        description=request.description,
        created_at=datetime.now(timezone.utc),
        created_by=auth.user_id,
    )


@router.get("/auth/api-keys")
async def list_api_keys(auth: AuthDep, auth_service: AuthServiceDep) -> APIKeyListResponse:
    """
    List all API keys for the authenticated user.

    Returns information about all API keys created by the user (excluding the actual key values).
    """
    # Get all keys for this user
    stored_keys = auth_service.list_user_api_keys(auth.user_id)

    # Convert to response format
    api_keys = [
        APIKeyInfo(
            key_id=key.key_id,
            role=key.role,
            expires_at=key.expires_at,
            description=key.description,
            created_at=key.created_at,
            created_by=key.created_by,
            last_used=key.last_used,
            is_active=key.is_active,
        )
        for key in stored_keys
    ]

    return APIKeyListResponse(api_keys=api_keys, total=len(api_keys))


@router.delete("/auth/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_api_key(
    key_id: str,
    auth: AuthDep,
    auth_service: AuthServiceDep,
) -> None:
    """
    Delete an API key.

    Users can only delete their own API keys.
    """
    # Get the key to verify ownership
    all_keys = auth_service.list_user_api_keys(auth.user_id)
    key_to_delete = next((k for k in all_keys if k.key_id == key_id), None)

    if not key_to_delete:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="API key not found")

    # Revoke the key
    auth_service.revoke_api_key(key_id)

    logger.info(f"User {auth.user_id} deleted API key {key_id}")

    return None


# ========== Service Token Management Endpoints ==========


@router.post("/auth/service-token/revoke")
async def revoke_service_token(
    request: Request,
    revoke_request: "ServiceTokenRevokeRequest",
    auth: AuthDep,
    auth_service: AuthServiceDep,
) -> "ServiceTokenRevokeResponse":
    """
    Revoke a service token.

    This endpoint allows SYSTEM_ADMIN users to revoke service tokens for security purposes.
    Once revoked, the token cannot be used for authentication.

    Requires SYSTEM_ADMIN role for security reasons.
    """
    from ciris_engine.schemas.api.auth import ServiceTokenRevokeRequest, ServiceTokenRevokeResponse

    # Check permissions - only SYSTEM_ADMIN can revoke service tokens
    if auth.role != UserRole.SYSTEM_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only SYSTEM_ADMIN users can revoke service tokens",
        )

    # Revoke the token
    success = await auth_service.revoke_service_token(
        token=revoke_request.token,
        reason=revoke_request.reason,
        revoked_by=auth.user_id,
    )

    # Generate partial hash for response
    import hashlib

    token_hash = hashlib.sha256(revoke_request.token.encode("utf-8")).hexdigest()[:16] + "..."

    if success:
        logger.info(f"[AUTH] SYSTEM_ADMIN {auth.user_id} revoked service token {token_hash}: {revoke_request.reason}")
        return ServiceTokenRevokeResponse(
            success=True,
            message="Service token revoked successfully",
            token_hash=token_hash,
        )
    else:
        return ServiceTokenRevokeResponse(
            success=False,
            message="Service token was already revoked",
            token_hash=token_hash,
        )


# ========== Attestation Helpers ==========


def _build_attestation_response(
    status: str,
    *,
    loaded: bool = True,
    error: Optional[str] = None,
    max_level: int = 0,
    level_pending: bool = True,
) -> Dict[str, Any]:
    """Build a standardized attestation response."""
    return {
        "data": {
            "loaded": loaded,
            "attestation_status": status,
            "level_pending": level_pending,
            "max_level": max_level,
            "error": error,
        }
    }


def _get_infra_auth_service(request: Request) -> tuple[Any, Optional[Dict[str, Any]]]:
    """Get infrastructure auth service from request, returning (service, error_response)."""
    api_auth_service = getattr(request.app.state, "auth_service", None)
    if not api_auth_service:
        logger.warning("[attestation] API Auth service not available")
        return None, _build_attestation_response(
            "not_attempted", loaded=False, error="Authentication service not available"
        )

    infra_auth_service = getattr(api_auth_service, "_auth_service", None)
    if not infra_auth_service:
        logger.warning("[attestation] Infrastructure auth service not available")
        return None, _build_attestation_response(
            "not_attempted", loaded=False, error="Infrastructure authentication service not available"
        )

    if not hasattr(infra_auth_service, "get_cached_attestation"):
        logger.warning("[attestation] Auth service does not support attestation caching")
        return None, _build_attestation_response(
            "not_attempted", loaded=False, error="Attestation caching not supported"
        )

    return infra_auth_service, None


def _trigger_background_attestation(infra_auth_service: Any, force_refresh: bool = False) -> bool:
    """Trigger attestation in background. Returns True if triggered successfully."""
    import asyncio

    if not hasattr(infra_auth_service, "run_attestation"):
        return False

    try:
        if force_refresh:
            infra_auth_service.invalidate_attestation_cache()
        task = asyncio.create_task(infra_auth_service.run_attestation(mode="full", force_refresh=force_refresh))
        if hasattr(infra_auth_service, "_background_tasks"):
            infra_auth_service._background_tasks.add(task)
            task.add_done_callback(infra_auth_service._background_tasks.discard)
        return True
    except Exception as e:
        logger.warning(f"[attestation] Failed to trigger attestation: {e}")
        return False


def _handle_no_cached_attestation(infra_auth_service: Any) -> Dict[str, Any]:
    """Handle case when no cached attestation is available."""
    global _attestation_triggered_from_endpoint

    # Check if attestation is currently in progress
    in_progress = (
        hasattr(infra_auth_service, "is_attestation_in_progress") and infra_auth_service.is_attestation_in_progress()
    )
    logger.debug("[attestation] Cache empty. in_progress=%s", in_progress)

    if in_progress:
        logger.debug("[attestation] Returning in_progress status")
        return _build_attestation_response("in_progress")

    # Try to trigger attestation if not already triggered
    if not _attestation_triggered_from_endpoint:
        logger.debug("[attestation] No cached attestation - triggering now")
        if _trigger_background_attestation(infra_auth_service):
            _attestation_triggered_from_endpoint = True
            return _build_attestation_response("in_progress")
        # Trigger failed, reset flag handled in helper

    # Already triggered or trigger not possible
    if _attestation_triggered_from_endpoint:
        logger.debug("[attestation] Attestation already triggered")
        return _build_attestation_response("in_progress")

    logger.debug("[attestation] No cached attestation and could not trigger")
    return _build_attestation_response(
        "not_attempted",
        error="No cached attestation - startup attestation may not have completed",
    )


# ========== Attestation Endpoint ==========


@router.get("/auth/attestation")
async def get_attestation(request: Request, refresh: bool = False) -> Dict[str, Any]:
    """Get CIRISVerify attestation from AuthenticationService.

    By default returns the cached attestation result from startup.
    Pass ?refresh=true to invalidate the cache and trigger a fresh
    attestation run (used by the Trust page refresh button).

    Returns:
        Attestation result in the same format as /v1/setup/verify-status
    """
    global _attestation_triggered_from_endpoint

    # Get infrastructure auth service (handles service chain validation)
    infra_auth_service, error_response = _get_infra_auth_service(request)
    if error_response:
        return error_response

    # Handle refresh request
    if refresh:
        logger.debug("[attestation] Refresh requested")
        _trigger_background_attestation(infra_auth_service, force_refresh=True)
        return _build_attestation_response("in_progress")

    def _detect_platform_os() -> str:
        """Fallback platform detection when verify doesn't provide platform_os."""
        import sys

        return sys.platform  # 'darwin', 'linux', 'win32', etc.

    # Check for cached attestation (allow stale data while refresh runs in background)
    cached = infra_auth_service.get_cached_attestation(allow_stale=True)

    if not cached:
        return _handle_no_cached_attestation(infra_auth_service)

    # Convert cached AttestationResult to response format
    # This matches the format returned by /v1/setup/verify-status
    logger.debug(
        "[attestation] Returning cached attestation: max_level=%s, python_modules_passed=%s/%s",
        cached.max_level,
        cached.python_modules_passed,
        cached.python_modules_checked,
    )

    return {
        "data": {
            "loaded": cached.loaded,
            "version": cached.version,
            "agent_version": cached.agent_version,
            "hardware_type": cached.hardware_type,
            "platform_os": cached.platform_os or _detect_platform_os(),
            "key_status": cached.key_status,
            "key_id": cached.key_id,
            "attestation_status": cached.attestation_status,
            "error": cached.error,
            "diagnostic_info": cached.diagnostic_info,
            # Attestation level checks
            "dns_us_ok": cached.dns_us_ok,
            "dns_eu_ok": cached.dns_eu_ok,
            "https_us_ok": cached.https_us_ok,
            "https_eu_ok": cached.https_eu_ok,
            "binary_ok": cached.binary_ok,
            "file_integrity_ok": cached.file_integrity_ok,
            "registry_ok": cached.registry_ok,
            "audit_ok": cached.audit_ok,
            "env_ok": cached.env_ok,
            "play_integrity_ok": cached.play_integrity_ok,
            "play_integrity_verdict": cached.play_integrity_verdict,
            "max_level": cached.max_level,
            "level_pending": cached.level_pending,  # True when waiting for device attestation
            # Key attestation
            "ed25519_fingerprint": cached.ed25519_fingerprint,
            "key_storage_mode": cached.key_storage_mode,
            "hardware_backed": cached.hardware_backed,
            # Registry key status
            "registry_key_status": cached.registry_key_status,
            # Sources agreement
            "sources_agreeing": cached.sources_agreeing,
            # Attestation mode
            "attestation_mode": cached.attestation_mode,
            # File integrity details
            "total_files": cached.total_files,
            "files_checked": cached.files_checked,
            "files_passed": cached.files_passed,
            "files_failed": cached.files_failed,
            # Function integrity
            "function_integrity": cached.function_integrity,
            "functions_checked": cached.functions_checked,
            "functions_passed": cached.functions_passed,
            # Binary self-check details
            "binary_self_check": cached.binary_self_check,
            "binary_hash": cached.binary_hash,
            "function_self_check": cached.function_self_check,
            "target_triple": cached.target_triple,
            # Python integrity
            "python_integrity_ok": cached.python_integrity_ok,
            "python_modules_checked": cached.python_modules_checked,
            "python_modules_passed": cached.python_modules_passed,
            "python_modules_failed": cached.python_modules_failed,
            "python_total_hash": cached.python_total_hash,
            "python_hash_valid": cached.python_hash_valid,
            "python_failed_modules": cached.python_failed_modules,
            # v0.9.7: Unified module integrity (cross-validation)
            "module_integrity_ok": cached.module_integrity_ok,
            "module_integrity_summary": cached.module_integrity_summary,
            "cross_validated_files": cached.cross_validated_files,
            "filesystem_verified_files": cached.filesystem_verified_files,
            "agent_verified_files": cached.agent_verified_files,
            "disk_agent_mismatch": cached.disk_agent_mismatch,
            "registry_mismatch_files": cached.registry_mismatch_files,
            # L4 detail lists (v0.8.4+)
            "per_file_results": cached.per_file_results,
            "files_missing_count": cached.files_missing_count,
            "files_missing_list": cached.files_missing_list,
            "files_failed_list": cached.files_failed_list,
            "files_unexpected_list": cached.files_unexpected_list,
            "functions_failed_list": cached.functions_failed_list,
            # Mobile exclusions (v0.8.6+)
            "mobile_excluded_count": cached.mobile_excluded_count,
            "mobile_excluded_list": cached.mobile_excluded_list,
            # Cache metadata
            "cached_at": cached.cached_at.isoformat() if cached.cached_at else None,
        }
    }
