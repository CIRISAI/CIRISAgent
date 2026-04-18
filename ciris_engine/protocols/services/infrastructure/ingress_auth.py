"""Ingress Authentication Provider Protocol.

Allows adapters to provide authentication for requests coming through
external proxies (e.g., Home Assistant Supervisor, nginx auth_request).

This enables:
- Home Assistant addon mode: Trust X-Remote-User-* headers from Supervisor
- Medical environments: Trust authentication from CIRISMedical proxy
- Enterprise deployments: Trust headers from corporate SSO proxies
"""

from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Protocol

from fastapi import Request

from ciris_engine.schemas.api.auth import AuthContext, UserRole


@dataclass
class IngressUser:
    """User information extracted from ingress headers.

    Adapters populate this from their proxy's headers, then the
    auth system creates/finds the corresponding CIRIS user.
    """

    # Required: Unique identifier from the external system
    external_id: str

    # Required: Provider identifier (e.g., "home_assistant", "ciris_medical")
    provider: str

    # Optional: User details from external system
    username: Optional[str] = None
    display_name: Optional[str] = None
    email: Optional[str] = None

    # Role mapping: External role maps to CIRIS role
    # If None, defaults to OBSERVER for new users, preserves existing for known users
    suggested_role: Optional[UserRole] = None

    # Additional metadata from the proxy
    metadata: Optional[Dict[str, Any]] = None

    # Timestamp when auth was validated
    authenticated_at: Optional[datetime] = None


class IngressAuthProviderProtocol(Protocol):
    """Protocol for adapters that provide ingress authentication.

    Adapters implementing this protocol can authenticate requests
    that come through their proxy system (e.g., HA Supervisor ingress).

    The auth flow is:
    1. Request arrives with proxy headers
    2. Auth system calls can_handle_request() on registered providers
    3. First provider that returns True handles the request
    4. Provider's authenticate_request() extracts user info from headers
    5. Auth system creates/finds CIRIS user and builds AuthContext

    Example implementation (Home Assistant):
    ```python
    class HAIngressAuthProvider:
        def can_handle_request(self, request: Request) -> bool:
            # Only handle if we're in supervisor mode AND headers present
            return (
                os.getenv("SUPERVISOR_TOKEN") and
                request.headers.get("X-Remote-User-Id")
            )

        async def authenticate_request(self, request: Request) -> IngressUser:
            return IngressUser(
                external_id=request.headers["X-Remote-User-Id"],
                provider="home_assistant",
                username=request.headers.get("X-Remote-User-Name"),
                display_name=request.headers.get("X-Remote-User-Display-Name"),
            )
    ```
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Unique identifier for this auth provider (e.g., 'home_assistant')."""
        ...

    @abstractmethod
    def can_handle_request(self, request: Request) -> bool:
        """Check if this provider can authenticate the given request.

        This should be a fast check (no I/O) that examines request headers
        to determine if this provider's authentication is applicable.

        Args:
            request: The FastAPI request to check

        Returns:
            True if this provider should handle authentication for this request
        """
        ...

    @abstractmethod
    async def authenticate_request(self, request: Request) -> Optional[IngressUser]:
        """Extract user information from request headers.

        Called only if can_handle_request() returned True.

        Args:
            request: The FastAPI request with proxy headers

        Returns:
            IngressUser with extracted user info, or None if auth failed
        """
        ...

    @abstractmethod
    def is_first_user_admin(self) -> bool:
        """Whether the first user from this provider should be admin.

        For HA addon mode, the first HA user to access CIRIS should
        become the admin (owner of the HA instance).

        Returns:
            True if first user should be granted admin role
        """
        ...

    @abstractmethod
    def skip_setup_wizard_user_step(self) -> bool:
        """Whether to skip the user creation step in setup wizard.

        When True, the setup wizard will not prompt for username/password
        since authentication is handled by the external proxy.

        Returns:
            True if user creation step should be skipped
        """
        ...

    @abstractmethod
    def get_provider_metadata(self) -> Dict[str, Any]:
        """Get metadata about this auth provider for display.

        Returns:
            Dict with provider info like:
            {
                "name": "Home Assistant",
                "description": "Authenticated via Home Assistant",
                "icon": "mdi:home-assistant",
                "trusted_headers": ["X-Remote-User-Id", ...],
            }
        """
        ...
