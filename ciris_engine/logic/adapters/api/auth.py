"""
Authentication utilities for API routes.
"""

from typing import Any, Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from .models import TokenData

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


def _extract_token_string(token: Optional[str]) -> str:
    """Extract token string from HTTPBearer object or raw string."""
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return token.credentials if hasattr(token, "credentials") else str(token)


def _get_auth_services(request: Request) -> tuple[Optional[Any], Optional[Any]]:
    """Get authentication services from app state."""
    wa_auth_service = getattr(request.app.state, "authentication_service", None)
    api_auth_service = getattr(request.app.state, "auth_service", None)
    return wa_auth_service, api_auth_service


def _create_fallback_token_data() -> TokenData:
    """Create fallback token data for development mode."""
    return TokenData(username="admin", email="admin@ciris.ai", role="SYSTEM_ADMIN")


def _try_api_key_validation(token_str: str, api_auth_service: Optional[Any], logger: Any) -> Optional[TokenData]:
    """Try to validate token as an API key. Returns TokenData if valid, None otherwise."""
    if not token_str.startswith("ciris_"):
        return None

    logger.debug("[AUTH] Detected API key format - attempting API key validation")

    if not api_auth_service:
        logger.warning("[AUTH] API auth service not available for API key validation")
        return None

    stored_key = api_auth_service.validate_api_key(token_str)
    logger.debug(f"[AUTH] API key validation result: {stored_key is not None}")

    if not stored_key:
        logger.warning("[AUTH] API key validation failed - invalid or expired")
        return None

    # Get user from API auth service
    user = api_auth_service.get_user(stored_key.user_id)
    if not user or not user.is_active:
        return None

    logger.debug(f"[AUTH] API key validated for user: {user.name}, role: {user.api_role.value}")
    return TokenData(
        username=user.name,
        email=user.oauth_email,
        role=user.api_role.value,
        exp=stored_key.expires_at,
    )


async def _try_jwt_validation(token_str: str, wa_auth_service: Optional[Any], logger: Any) -> Optional[TokenData]:
    """Try to validate token as a JWT. Returns TokenData if valid, None otherwise."""
    if not wa_auth_service:
        return None

    logger.debug("[AUTH] Attempting JWT token verification")

    verification = await wa_auth_service.verify_token(token_str)
    logger.debug(
        f"[AUTH] JWT verification result: valid={verification.valid if verification else None}, role={verification.role if verification else None}"
    )

    if not verification or not verification.valid:
        return None

    # Convert WA role to API role format
    role_mapping = {
        "OBSERVER": "OBSERVER",
        "ADMIN": "ADMIN",
        "AUTHORITY": "AUTHORITY",
        "SYSTEM_ADMIN": "SYSTEM_ADMIN",
    }

    api_role = role_mapping.get(verification.role, "OBSERVER")

    return TokenData(
        username=verification.name or verification.wa_id,
        email=None,  # WA tokens don't include email
        role=api_role,
        exp=verification.expires_at,
    )


async def get_current_user(request: Request, token: Optional[str] = Depends(security)) -> TokenData:
    """
    Get the current authenticated user from the token.

    Validates both API keys and JWT tokens.
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.debug(f"[AUTH] get_current_user called, token present: {token is not None}")

    # Extract and validate token
    token_str = _extract_token_string(token)
    logger.debug(
        f"[AUTH] Token extracted, type: {type(token)}, first 20 chars: {token_str[:20] if token_str else 'None'}..."
    )

    # Get authentication services
    wa_auth_service, api_auth_service = _get_auth_services(request)
    logger.debug(
        f"[AUTH] WA auth service available: {wa_auth_service is not None}, API auth service available: {api_auth_service is not None}"
    )

    # Fallback to development mode if no services available
    if not wa_auth_service and not api_auth_service:
        return _create_fallback_token_data()

    try:
        # Try API key validation first
        api_key_result = _try_api_key_validation(token_str, api_auth_service, logger)
        if api_key_result:
            return api_key_result

        # Try JWT validation as fallback
        jwt_result = await _try_jwt_validation(token_str, wa_auth_service, logger)
        if jwt_result:
            return jwt_result

        # Both validation methods failed
        logger.warning("[AUTH] Both API key and JWT validation failed")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.debug(f"[AUTH] Exception during token validation: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
