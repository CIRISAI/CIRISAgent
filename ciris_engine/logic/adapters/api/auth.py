"""
Authentication utilities for API routes.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer

from .models import TokenData

# HTTP Bearer token security scheme
security = HTTPBearer(auto_error=False)


async def get_current_user(token: Optional[str] = Depends(security)) -> TokenData:
    """
    Get the current authenticated user from the token.

    For now, returns a mock admin user for development.
    TODO: Implement proper JWT token validation.
    """
    # For development, always return admin user
    # In production, this would validate the JWT token
    return TokenData(username="admin", email="admin@ciris.ai", role="SYSTEM_ADMIN")
