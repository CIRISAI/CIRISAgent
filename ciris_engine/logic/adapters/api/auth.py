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

    Validates JWT tokens using the authentication service.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authentication token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get authentication service from app state
    auth_service = getattr(request.app.state, "authentication_service", None)
    if not auth_service:
        # Fallback to development mode for backward compatibility
        return TokenData(username="admin", email="admin@ciris.ai", role="SYSTEM_ADMIN")

    try:
        # Validate token using the authentication service
        verification = await auth_service.verify_token(token)
        if not verification or not verification.valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

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

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {str(e)}",
            headers={"WWW-Authenticate": "Bearer"},
        )
