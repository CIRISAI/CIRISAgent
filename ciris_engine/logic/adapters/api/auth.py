"""
Authentication utilities for API routes.
"""

from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer

from .models import TokenData

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(request: Request, token: Optional[str] = Depends(security)) -> TokenData:
    """
    Get the current authenticated user from the token.

    Validates both API keys and JWT tokens.
    """
    import logging

    logger = logging.getLogger(__name__)

    logger.debug(f"[AUTH] get_current_user called, token present: {token is not None}")

    if not token:
        logger.warning("[AUTH] No token provided")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Extract token string from HTTPBearer object
    token_str = token.credentials if hasattr(token, "credentials") else str(token)
    logger.debug(
        f"[AUTH] Token extracted, type: {type(token)}, first 20 chars: {token_str[:20] if token_str else 'None'}..."
    )

    # Get authentication services from app state
    wa_auth_service = getattr(request.app.state, "authentication_service", None)  # WA AuthenticationService for JWTs
    api_auth_service = getattr(request.app.state, "auth_service", None)  # APIAuthService for API keys
    logger.debug(
        f"[AUTH] WA auth service available: {wa_auth_service is not None}, API auth service available: {api_auth_service is not None}"
    )

    if not wa_auth_service and not api_auth_service:
        # Fallback to development mode for backward compatibility
        return TokenData(username="admin", email="admin@ciris.ai", role="SYSTEM_ADMIN")

    try:
        # First, check if it's an API key (starts with "ciris_")
        if token_str.startswith("ciris_"):
            logger.debug("[AUTH] Detected API key format - attempting API key validation")
            if api_auth_service:
                stored_key = api_auth_service.validate_api_key(token_str)
                logger.debug(f"[AUTH] API key validation result: {stored_key is not None}")
                if stored_key:
                    # Get user from API auth service
                    user = api_auth_service.get_user(stored_key.user_id)
                    if user and user.is_active:
                        logger.debug(f"[AUTH] API key validated for user: {user.name}, role: {user.api_role.value}")
                        return TokenData(
                            username=user.name,
                            email=user.oauth_email,
                            role=user.api_role.value,
                            exp=stored_key.expires_at,
                        )
                logger.warning("[AUTH] API key validation failed - invalid or expired")
            else:
                logger.warning("[AUTH] API auth service not available for API key validation")

        # If not an API key or API key validation failed, try JWT verification
        logger.debug("[AUTH] Attempting JWT token verification")
        if wa_auth_service:
            verification = await wa_auth_service.verify_token(token_str)
            logger.debug(
                f"[AUTH] JWT verification result: valid={verification.valid if verification else None}, role={verification.role if verification else None}"
            )
            if verification and verification.valid:
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
