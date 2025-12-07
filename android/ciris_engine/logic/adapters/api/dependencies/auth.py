"""
Authentication dependencies for FastAPI routes.

Provides role-based access control through dependency injection.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Optional, Set

from fastapi import Depends, Header, HTTPException, Request, status

from ciris_engine.schemas.api.auth import ROLE_PERMISSIONS, APIKeyInfo, AuthContext, UserInfo, UserRole

from ..services.auth_service import APIAuthService

__all__ = [
    "AuthContext",
    "get_auth_service",
    "require_admin",
    "require_observer",
    "require_authenticated",
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
    service_user = auth_service.validate_service_token(service_token)
    if not service_user:
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


async def get_auth_context(  # NOSONAR: FastAPI requires async for dependency injection
    request: Request,
    authorization: Optional[str] = Header(None),
    auth_service: APIAuthService = Depends(get_auth_service),
) -> AuthContext:
    """Extract and validate authentication from request."""
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
    """Optional authentication - returns None if no auth provided."""
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

    async def check(  # NOSONAR: FastAPI requires async for dependency injection
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
