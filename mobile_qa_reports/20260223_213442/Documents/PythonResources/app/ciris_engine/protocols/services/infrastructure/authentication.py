"""Authentication Service Protocol.

Handles identity verification and token management for Wise Authorities.
Authentication = "Who are you?"
"""

from abc import abstractmethod
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Protocol, Tuple, Union

from ...runtime.base import ServiceProtocol

if TYPE_CHECKING:
    from ciris_engine.schemas.runtime.models import Task
    from ciris_engine.schemas.services.authority_core import TokenType, WACertificate, WARole
else:
    from ciris_engine.schemas.services.authority_core import WACertificate, WARole, TokenType

from ciris_engine.schemas.services.authority.wise_authority import AuthenticationResult, TokenVerification, WAUpdate


class AuthenticationServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for authentication service - identity management."""

    @abstractmethod
    async def authenticate(self, token: str) -> Optional[AuthenticationResult]:
        """Authenticate a WA token and return identity info."""
        ...

    @abstractmethod
    async def create_token(self, wa_id: str, token_type: TokenType, ttl: int = 3600) -> str:
        """Create a new authentication token."""
        ...

    @abstractmethod
    async def verify_token(self, token: str) -> Optional[TokenVerification]:
        """Verify and decode a token."""
        ...

    @abstractmethod
    async def create_wa(
        self, name: str, email: str, scopes: List[str], role: WARole = WARole.OBSERVER
    ) -> WACertificate:
        """Create a new Wise Authority identity."""
        ...

    @abstractmethod
    async def revoke_wa(self, wa_id: str, reason: str) -> bool:
        """Revoke a Wise Authority identity."""
        ...

    @abstractmethod
    async def update_wa(
        self, wa_id: str, updates: Optional[WAUpdate] = None, **kwargs: Union[str, bool, datetime]
    ) -> Optional[WACertificate]:
        """Update a Wise Authority identity."""
        ...

    @abstractmethod
    async def list_was(self, active_only: bool = True) -> List[WACertificate]:
        """List Wise Authority identities."""
        ...

    @abstractmethod
    async def get_wa(self, wa_id: str) -> Optional[WACertificate]:
        """Get a specific Wise Authority by ID."""
        ...

    @abstractmethod
    async def rotate_keys(self, wa_id: str) -> bool:
        """Rotate cryptographic keys for a WA."""
        ...

    @abstractmethod
    async def bootstrap_if_needed(self) -> None:
        """Bootstrap the system with root WA if needed."""
        ...

    @abstractmethod
    async def create_channel_token(self, wa_id: str, channel_id: str, ttl: int = 3600) -> str:
        """Create a channel-specific token."""
        ...

    @abstractmethod
    def verify_token_sync(self, token: str) -> Optional[Dict[str, Any]]:
        """Synchronously verify a token (for non-async contexts)."""
        ...

    @abstractmethod
    async def update_last_login(self, wa_id: str) -> None:
        """Update the last login timestamp for a WA."""
        ...

    @abstractmethod
    def create_gateway_token(self, wa: "WACertificate", expires_hours: int = 8) -> str:
        """Create gateway-signed token (for OAuth/password auth)."""
        ...

    @abstractmethod
    async def get_wa_by_oauth(self, provider: str, external_id: str) -> Optional["WACertificate"]:
        """Get WA certificate by OAuth identity."""
        ...

    @abstractmethod
    async def link_oauth_identity(
        self,
        wa_id: str,
        provider: str,
        external_id: str,
        *,
        account_name: Optional[str] = None,
        metadata: Optional[Dict[str, str]] = None,
        primary: bool = False,
    ) -> Optional["WACertificate"]:
        """Associate an additional OAuth identity with a WA."""
        ...

    @abstractmethod
    async def unlink_oauth_identity(self, wa_id: str, provider: str, external_id: str) -> Optional["WACertificate"]:
        """Remove an associated OAuth identity from a WA."""
        ...

    @abstractmethod
    def generate_keypair(self) -> Tuple[bytes, bytes]:
        """Generate Ed25519 keypair (private, public)."""
        ...

    @abstractmethod
    def hash_password(self, password: str) -> str:
        """Hash password using PBKDF2."""
        ...

    @abstractmethod
    def sign_data(self, data: bytes, private_key: bytes) -> str:
        """Sign data with Ed25519 private key."""
        ...

    @abstractmethod
    async def sign_task(self, task: "Task", wa_id: str) -> Tuple[str, str]:
        """Sign a task with a WA's private key.

        Returns:
            Tuple of (signature, signed_at timestamp)
        """
        ...

    @abstractmethod
    async def verify_task_signature(self, task: "Task") -> bool:
        """Verify a task's signature.

        Returns:
            True if signature is valid, False otherwise
        """
        ...

    @abstractmethod
    async def get_system_wa_id(self) -> Optional[str]:
        """Get the system WA ID for signing system tasks."""
        ...
