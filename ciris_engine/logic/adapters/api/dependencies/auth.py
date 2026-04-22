"""
Authentication dependencies for FastAPI routes.

Provides role-based access control through dependency injection.

Supports:
- Bearer token authentication (API keys, service tokens, username:password)
- Ingress authentication via registered providers (e.g., HA Supervisor, CIRISMedical)
"""

import logging
from datetime import datetime, timezone
from typing import Any, Callable, List, Optional, Set

from fastapi import Depends, Header, HTTPException, Request, status

from ciris_engine.protocols.services.infrastructure.ingress_auth import IngressAuthProviderProtocol, IngressUser
from ciris_engine.schemas.api.auth import ROLE_PERMISSIONS, APIKeyInfo, AuthContext, UserInfo, UserRole

from ..services.auth_service import APIAuthService

logger = logging.getLogger(__name__)


# =============================================================================
# Ingress Auth Provider Registry
# =============================================================================
# Adapters can register themselves as ingress auth providers to handle
# authentication via their proxy systems (e.g., HA Supervisor, medical proxies).
#
# Design: Chain of Responsibility Pattern (Sequential with Short-Circuit)
# ---------
# Providers are checked in priority order (highest first). The first provider
# that can_handle_request() AND successfully authenticate_request() wins.
# If no ingress provider handles the request, we fall back to Bearer auth.
#
# Why Sequential (not Parallel):
# 1. Authentication should be deterministic - same request, same provider handles it
# 2. First match wins avoids ambiguity when multiple providers could handle
# 3. Short-circuit on success improves performance
# 4. Order matters for security - more trusted providers should be checked first
#
# References:
# - Chain of Responsibility: https://refactoring.guru/design-patterns/chain-of-responsibility
# - Auth Middleware Pattern: https://medium.com/@mehar.chand.cloud/chain-of-responsibility-design-pattern-use-case-authentication-and-authorization-middleware-a96f17a9ebe3

from dataclasses import dataclass, field


@dataclass
class RegisteredProvider:
    """Wrapper for registered ingress auth providers with priority."""

    provider: IngressAuthProviderProtocol
    priority: int = 100  # Higher priority = checked first (default: 100)


_ingress_auth_providers: List[RegisteredProvider] = []


def register_ingress_auth_provider(
    provider: IngressAuthProviderProtocol,
    priority: int = 100,
) -> None:
    """Register an ingress auth provider with priority.

    Adapters call this when they provide ingress authentication.
    Providers are checked in priority order (highest first).

    Args:
        provider: The ingress auth provider to register
        priority: Check order priority (higher = checked first). Defaults:
            - home_assistant: 100 (standard priority)
            - ciris_medical: 200 (higher priority in medical environments)
            - enterprise_sso: 50 (lower priority, fallback)

    Example:
        ```python
        # Register HA provider with standard priority
        register_ingress_auth_provider(ha_provider, priority=100)

        # Register medical provider with higher priority
        register_ingress_auth_provider(medical_provider, priority=200)
        ```
    """
    # Check if already registered (by provider identity)
    for registered in _ingress_auth_providers:
        if registered.provider is provider:
            logger.debug(f"[AUTH] Provider {provider.provider_name} already registered, skipping")
            return

    _ingress_auth_providers.append(RegisteredProvider(provider=provider, priority=priority))
    # Sort by priority (highest first) for Chain of Responsibility order
    _ingress_auth_providers.sort(key=lambda r: r.priority, reverse=True)
    logger.info(f"[AUTH] Registered ingress auth provider: {provider.provider_name} (priority: {priority})")


def unregister_ingress_auth_provider(provider: IngressAuthProviderProtocol) -> None:
    """Unregister an ingress auth provider.

    Args:
        provider: The provider to unregister
    """
    for i, registered in enumerate(_ingress_auth_providers):
        if registered.provider is provider:
            _ingress_auth_providers.pop(i)
            logger.info(f"[AUTH] Unregistered ingress auth provider: {provider.provider_name}")
            return


def clear_ingress_auth_providers() -> None:
    """Clear all registered ingress auth providers (for testing)."""
    _ingress_auth_providers.clear()
    logger.debug("[AUTH] Cleared all ingress auth providers")


def get_ingress_auth_providers() -> List[IngressAuthProviderProtocol]:
    """Get all registered ingress auth providers (in priority order)."""
    return [r.provider for r in _ingress_auth_providers]


def has_ingress_auth_providers() -> bool:
    """Check if any ingress auth providers are registered."""
    return len(_ingress_auth_providers) > 0


def should_skip_setup_wizard_user_step() -> bool:
    """Check if any registered provider wants to skip setup wizard user step."""
    return any(r.provider.skip_setup_wizard_user_step() for r in _ingress_auth_providers)


def get_active_ingress_provider_names() -> List[str]:
    """Get names of all active ingress auth providers (for status/debugging)."""
    return [r.provider.provider_name for r in _ingress_auth_providers]


__all__ = [
    # Auth context and service
    "AuthContext",
    "get_auth_service",
    # Role requirements
    "require_admin",
    "require_observer",
    "require_authenticated",
    # Ingress auth provider registry
    "register_ingress_auth_provider",
    "unregister_ingress_auth_provider",
    "clear_ingress_auth_providers",
    "get_ingress_auth_providers",
    "has_ingress_auth_providers",
    "should_skip_setup_wizard_user_step",
    "get_active_ingress_provider_names",
]


def get_auth_service(request: Request) -> APIAuthService:
    """Get auth service from app state."""
    if not hasattr(request.app.state, "auth_service"):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Auth service not initialized")
    auth_service = request.app.state.auth_service
    if not isinstance(auth_service, APIAuthService):
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Invalid auth service type")
    return auth_service


def _extract_bearer_token(authorization: Optional[str]) -> str:
    """Extract and validate bearer token from authorization header."""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authorization format",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return authorization[7:]  # Remove "Bearer " prefix


def _handle_service_token_auth(request: Request, auth_service: APIAuthService, service_token: str) -> AuthContext:
    """Handle service token authentication."""
    import hashlib
    import logging

    logger = logging.getLogger(__name__)

    service_user = auth_service.validate_service_token(service_token)
    if not service_user:
        # Audit failed service token authentication (security monitoring)
        token_hash = hashlib.sha256(service_token.encode("utf-8")).hexdigest()[:16] + "..."
        client_ip = request.client.host if request.client else "unknown"
        # Sanitize user-agent to prevent log injection attacks
        raw_user_agent = request.headers.get("user-agent", "unknown")
        sanitized_user_agent = raw_user_agent.replace("\n", "").replace("\r", "")[:200]
        logger.warning(
            f"[AUTH SECURITY] Failed service token authentication: token_hash={token_hash}, client_ip={client_ip}, "
            f"user_agent={sanitized_user_agent}"
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid service token")

    # Service token authentication successful
    # NOTE: We do not audit successful service token auth to avoid log spam
    # Service tokens are used frequently by the manager and other services
    # Only failed attempts are audited for security monitoring

    from ciris_engine.schemas.api.auth import UserRole as AuthUserRole

    context = AuthContext(
        user_id=service_user.wa_id,
        role=AuthUserRole.SERVICE_ACCOUNT,
        permissions=ROLE_PERMISSIONS.get(AuthUserRole.SERVICE_ACCOUNT, set()),
        api_key_id=None,
        authenticated_at=datetime.now(timezone.utc),
    )
    context.request = request
    return context


async def _handle_password_auth(request: Request, auth_service: APIAuthService, api_key: str) -> AuthContext:
    """Handle username:password authentication."""
    username, password = api_key.split(":", 1)
    user = await auth_service.verify_user_password(username, password)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    from ciris_engine.schemas.api.auth import UserRole as AuthUserRole

    # Map APIRole to UserRole
    user_role = AuthUserRole[user.api_role.value]
    context = AuthContext(
        user_id=user.wa_id,
        role=user_role,
        permissions=ROLE_PERMISSIONS.get(user_role, set()),
        api_key_id=None,
        authenticated_at=datetime.now(timezone.utc),
    )
    context.request = request
    return context


def _build_permissions_set(key_info: Any, user: Any) -> Set[Any]:
    """Build permissions set from role and custom permissions."""
    permissions = set(ROLE_PERMISSIONS.get(key_info.role, set()))

    # Add any custom permissions if user exists and has them
    if user and hasattr(user, "custom_permissions") and user.custom_permissions:
        from ciris_engine.schemas.api.auth import Permission

        for perm in user.custom_permissions:
            # Convert string to Permission enum if it's a valid permission
            try:
                permissions.add(Permission(perm))
            except ValueError:
                # Skip invalid permission strings
                pass

    return permissions


def _handle_api_key_auth(request: Request, auth_service: APIAuthService, api_key: str) -> AuthContext:
    """Handle regular API key authentication."""
    key_info = auth_service.validate_api_key(api_key)
    if not key_info:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    # Get user to check for custom permissions
    user = auth_service.get_user(key_info.user_id)

    # Build permissions set
    permissions = _build_permissions_set(key_info, user)

    # Create auth context with request reference
    context = AuthContext(
        user_id=key_info.user_id,
        role=key_info.role,
        permissions=permissions,
        api_key_id=auth_service._get_key_id(api_key),
        authenticated_at=datetime.now(timezone.utc),
    )

    # Attach request to context for service access in routes
    context.request = request
    return context


async def _handle_ingress_auth(
    request: Request, auth_service: APIAuthService, ingress_user: IngressUser
) -> AuthContext:
    """Handle ingress authentication from a registered provider.

    Creates or retrieves the CIRIS user corresponding to the ingress user,
    then builds an AuthContext.
    """
    from ciris_engine.schemas.runtime.api import APIRole

    # Build a unique user ID from provider and external ID
    user_id = f"{ingress_user.provider}:{ingress_user.external_id}"

    # Check if user already exists
    existing_user = auth_service.get_user(user_id)

    if existing_user:
        # User exists - use their existing role
        role = existing_user.api_role
        user_role = UserRole[role.value] if hasattr(role, "value") else UserRole.OBSERVER
        # SECURITY: Log provider only, not full external_id
        logger.debug(f"[INGRESS_AUTH] Found existing user ({ingress_user.provider}), role: {user_role}")
    else:
        # New user - create them
        # Check if this is the FIRST user in the system - they should be SYSTEM_ADMIN
        # This is more reliable than the provider's suggested_role flag which can be
        # consumed by non-user-creating requests (health checks, etc.)
        existing_users = await auth_service.list_users()
        is_first_user = len(existing_users) == 0

        if is_first_user:
            # First user in the system gets SYSTEM_ADMIN
            user_role = UserRole.SYSTEM_ADMIN
            # SECURITY: Log provider only
            logger.info(f"[INGRESS_AUTH] First user in system - granting SYSTEM_ADMIN ({ingress_user.provider})")
        elif ingress_user.suggested_role:
            user_role = ingress_user.suggested_role
        else:
            user_role = UserRole.OBSERVER

        # Map UserRole to APIRole for user creation
        api_role_map = {
            UserRole.OBSERVER: APIRole.OBSERVER,
            UserRole.ADMIN: APIRole.ADMIN,
            UserRole.SYSTEM_ADMIN: APIRole.SYSTEM_ADMIN,
        }
        api_role = api_role_map.get(user_role, APIRole.OBSERVER)

        # Create the user
        username = ingress_user.display_name or ingress_user.username or ingress_user.external_id
        # SECURITY: Log provider only, not full external_id
        logger.info(
            f"[INGRESS_AUTH] Creating new user from ingress: {username} ({ingress_user.provider}), role: {user_role}"
        )

        # Use a placeholder password - ingress users don't use passwords
        import secrets

        placeholder_password = secrets.token_urlsafe(32)

        new_user = await auth_service.create_user(
            username=username,
            password=placeholder_password,
            api_role=api_role,
        )

        if new_user:
            logger.info(f"[INGRESS_AUTH] Created user: {new_user.wa_id}")
            # CRITICAL: Also store user under provider:external_id key for future lookups
            # The user was stored under wa_id by create_user, but ingress lookups use provider:external_id
            auth_service._users[user_id] = new_user
            # SECURITY: Don't log full user_id which contains external_id
            logger.info(f"[INGRESS_AUTH] Stored user under ingress key ({ingress_user.provider})")

            # Link OAuth identity to WA certificate so it persists across restarts
            try:
                await auth_service.link_user_oauth(
                    wa_id=new_user.wa_id,
                    provider=ingress_user.provider,
                    external_id=ingress_user.external_id,
                    account_name=username,
                    metadata={"ingress_auth": "true"},
                    primary=True,
                )
                logger.info(f"[INGRESS_AUTH] Linked ingress identity to WA: {new_user.wa_id}")
            except Exception as link_err:
                # Non-fatal - user can still authenticate this session
                logger.warning(f"[INGRESS_AUTH] Failed to link ingress identity: {link_err}")
        else:
            # User might already exist with a different key
            logger.warning(f"[INGRESS_AUTH] Could not create user {username}, checking alternate keys")
            existing_user = auth_service.get_user(user_id)
            if existing_user:
                user_role = UserRole[existing_user.api_role.value]

    # Build permissions
    permissions = set(ROLE_PERMISSIONS.get(user_role, set()))

    # Create auth context
    context = AuthContext(
        user_id=user_id,
        role=user_role,
        permissions=permissions,
        api_key_id=None,
        authenticated_at=ingress_user.authenticated_at or datetime.now(timezone.utc),
    )
    context.request = request

    return context


async def _try_ingress_auth(request: Request, auth_service: APIAuthService) -> Optional[AuthContext]:
    """Try to authenticate via registered ingress auth providers.

    Uses Chain of Responsibility pattern:
    - Providers are checked in priority order (highest first)
    - First provider that can_handle_request() attempts authentication
    - If authenticate_request() succeeds, return the context
    - If it fails, continue to next provider (allows fallback)

    Returns AuthContext if an ingress provider handled the request,
    None if no provider could handle it.
    """
    for registered in _ingress_auth_providers:
        provider = registered.provider
        try:
            if provider.can_handle_request(request):
                logger.debug(
                    f"[AUTH] Ingress provider {provider.provider_name} "
                    f"(priority: {registered.priority}) handling request"
                )
                ingress_user = await provider.authenticate_request(request)
                if ingress_user:
                    return await _handle_ingress_auth(request, auth_service, ingress_user)
                else:
                    # Provider claimed to handle but returned None - log and try next
                    logger.warning(
                        f"[AUTH] Ingress provider {provider.provider_name} "
                        "can_handle_request=True but authenticate_request returned None"
                    )
        except Exception as e:
            # Don't let one provider's failure break the chain
            logger.error(f"[AUTH] Ingress provider {provider.provider_name} error: {e}")
            continue

    return None


async def get_auth_context(  # NOSONAR - FastAPI requires async for dependency injection
    request: Request,
    authorization: Optional[str] = Header(None),
    auth_service: APIAuthService = Depends(get_auth_service),
) -> AuthContext:
    """Extract and validate authentication from request.

    Checks authentication sources in order:
    1. Registered ingress auth providers (e.g., HA Supervisor, CIRISMedical)
    2. Bearer token (API key, service token, username:password)
    """
    # First, try ingress auth providers (e.g., HA Supervisor headers)
    if _ingress_auth_providers:
        ingress_context = await _try_ingress_auth(request, auth_service)
        if ingress_context:
            return ingress_context

    # Fall back to bearer token authentication
    api_key = _extract_bearer_token(authorization)

    # Check if this is a service token
    if api_key.startswith("service:"):
        service_token = api_key[8:]  # Remove "service:" prefix
        return _handle_service_token_auth(request, auth_service, service_token)

    # Check if this is username:password format (for legacy support)
    if ":" in api_key:
        return await _handle_password_auth(request, auth_service, api_key)

    # Otherwise, validate as regular API key
    return _handle_api_key_auth(request, auth_service, api_key)


async def optional_auth(
    request: Request,
    authorization: Optional[str] = Header(None),
    auth_service: APIAuthService = Depends(get_auth_service),
) -> Optional[AuthContext]:
    """Optional authentication - returns None if no auth provided.

    Checks in order:
    1. Ingress auth providers (always checked - they use headers, not Bearer)
    2. Bearer token if provided
    """
    # First, try ingress auth providers (they don't require Authorization header)
    if _ingress_auth_providers:
        ingress_context = await _try_ingress_auth(request, auth_service)
        if ingress_context:
            return ingress_context

    # No ingress auth, check Bearer token
    if not authorization:
        return None

    try:
        return await get_auth_context(request, authorization, auth_service)
    except HTTPException:
        return None


def require_role(minimum_role: UserRole) -> Callable[..., AuthContext]:
    """
    Factory for role-based access control dependencies.

    Args:
        minimum_role: Minimum role required for access

    Returns:
        Dependency function that validates role
    """

    def check_role(auth: AuthContext = Depends(get_auth_context)) -> AuthContext:
        """Validate user has required role."""
        if not auth.role.has_permission(minimum_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Insufficient permissions. Requires {minimum_role.value} role or higher.",
            )

        return auth

    # Set function name for better error messages
    check_role.__name__ = f"require_{minimum_role.value.lower()}"
    return check_role


# Convenience dependencies for common roles
require_authenticated = get_auth_context  # Alias for basic authentication
require_observer = require_role(UserRole.OBSERVER)
require_admin = require_role(UserRole.ADMIN)
require_authority = require_role(UserRole.AUTHORITY)
require_system_admin = require_role(UserRole.SYSTEM_ADMIN)
require_service_account = require_role(UserRole.SERVICE_ACCOUNT)


def check_permissions(permissions: list[str]) -> Callable[..., Any]:
    """
    Factory for permission-based access control dependencies.

    Args:
        permissions: List of required permissions

    Returns:
        Dependency function that validates permissions
    """

    async def check(  # NOSONAR - FastAPI requires async for dependency injection
        auth: AuthContext = Depends(get_auth_context), auth_service: APIAuthService = Depends(get_auth_service)
    ) -> None:
        """Validate user has required permissions."""
        from ciris_engine.schemas.runtime.api import APIRole
        from ciris_engine.schemas.services.authority_core import WARole

        # Get the user from auth service to get their API role
        user = auth_service.get_user(auth.user_id)
        if not user:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User not found")

        # Get permissions for user's API role
        user_permissions = set(auth_service.get_permissions_for_role(user.api_role))

        # ROOT WA role inherits AUTHORITY permissions (for deferral resolution, etc.)
        # This is separate from API role - ROOT WAs get both SYSTEM_ADMIN + AUTHORITY perms
        if hasattr(user, "wa_role") and user.wa_role == WARole.ROOT:
            authority_perms = auth_service.get_permissions_for_role(APIRole.AUTHORITY)
            user_permissions.update(authority_perms)

        # Add any custom permissions
        if hasattr(user, "custom_permissions") and user.custom_permissions:
            for perm in user.custom_permissions:
                user_permissions.add(perm)

        # Check if user has all required permissions
        missing = set(permissions) - user_permissions
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Missing required permissions: {', '.join(missing)}"
            )

    return check
