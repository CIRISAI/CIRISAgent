"""
Authentication resource for CIRIS v1 API (Pre-Beta).

**WARNING**: This SDK is for the v1 API which is in pre-beta stage.
The API interfaces may change without notice.

Provides clean session management with the 4-role model:
- OBSERVER: Read-only access to system state
- ADMIN: Operational control
- AUTHORITY: Strategic decisions and guidance
- ROOT: Full system access
"""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..transport import Transport


class LoginRequest:
    """Request to authenticate with username/password."""

    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password


class LoginResponse:
    """Response after successful login."""

    def __init__(self, data: Dict[str, Any]):
        self.access_token: str = data["access_token"]
        self.token_type: str = data["token_type"]
        self.expires_in: int = data["expires_in"]
        self.user_id: str = data["user_id"]
        self.role: str = data["role"]


class TokenRefreshRequest:
    """Request to refresh access token."""

    def __init__(self, refresh_token: str):
        self.refresh_token = refresh_token


class UserInfo:
    """Current user information with permissions."""

    def __init__(self, data: Dict[str, Any]):
        self.user_id: str = data["user_id"]
        self.username: str = data["username"]
        self.role: str = data["role"]
        self.permissions: List[str] = data["permissions"]
        self.created_at: datetime = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
        self.last_login: Optional[datetime] = None
        if data.get("last_login"):
            self.last_login = datetime.fromisoformat(data["last_login"].replace("Z", "+00:00"))


class AuthResource:
    """
    Authentication resource for managing API sessions.

    Provides endpoints for:
    - Login with username/password
    - Logout to end session
    - Get current user info with permissions
    - Refresh authentication token
    """

    def __init__(self, transport: Transport):
        self._transport = transport

    async def login(self, username: str, password: str) -> LoginResponse:
        """
        Authenticate with username and password.

        Currently supports ROOT user only. In production, this would
        integrate with a proper user database.

        Args:
            username: User's username
            password: User's password

        Returns:
            LoginResponse with access token and user details

        Raises:
            HTTPException: If credentials are invalid
        """
        request_data = {"username": username, "password": password}

        response = await self._transport.request("POST", "/v1/auth/login", json=request_data)
        assert response is not None

        return LoginResponse(response)

    async def logout(self) -> None:
        """
        End the current session by revoking the API key.

        This invalidates the current authentication token,
        effectively logging out the user.

        Raises:
            HTTPException: If not authenticated
        """
        await self._transport.request("POST", "/v1/auth/logout")

    async def get_current_user(self) -> UserInfo:
        """
        Get current authenticated user information.

        Returns details about the currently authenticated user including
        their role and all permissions based on that role.

        Returns:
            UserInfo with user details and permissions

        Raises:
            HTTPException: If not authenticated
        """
        response = await self._transport.request("GET", "/v1/auth/me")
        assert response is not None

        return UserInfo(response)

    async def refresh_token(self, refresh_token: Optional[str] = None) -> LoginResponse:
        """
        Refresh the current access token.

        Creates a new access token and revokes the old one. The user must
        be authenticated to refresh their token.

        Args:
            refresh_token: Optional refresh token (not currently used,
                         authentication is required)

        Returns:
            LoginResponse with new access token

        Raises:
            HTTPException: If not authenticated
        """
        request_data = {"refresh_token": refresh_token or "current_token"}

        response = await self._transport.request("POST", "/v1/auth/refresh", json=request_data)
        assert response is not None

        return LoginResponse(response)

    # Convenience methods for session management

    async def is_authenticated(self) -> bool:
        """
        Check if the client is currently authenticated.

        Returns:
            True if authenticated, False otherwise
        """
        try:
            await self.get_current_user()
            return True
        except Exception:
            return False

    async def has_permission(self, permission: str) -> bool:
        """
        Check if the current user has a specific permission.

        Args:
            permission: Permission to check (e.g., "view_messages")

        Returns:
            True if user has permission, False otherwise
        """
        try:
            user = await self.get_current_user()
            return permission in user.permissions
        except Exception:
            return False

    async def get_role(self) -> Optional[str]:
        """
        Get the current user's role.

        Returns:
            Role name (OBSERVER, ADMIN, AUTHORITY, ROOT) or None if not authenticated
        """
        try:
            user = await self.get_current_user()
            return user.role
        except Exception:
            return None
