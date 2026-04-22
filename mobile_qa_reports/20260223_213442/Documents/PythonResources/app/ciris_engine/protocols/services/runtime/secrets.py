"""Secrets Service Protocol."""

from abc import abstractmethod
from typing import Any, Dict, List, Optional, Protocol, Tuple

from ciris_engine.schemas.secrets.core import SecretReference
from ciris_engine.schemas.secrets.service import (
    DecapsulationContext,
    FilterUpdateRequest,
    FilterUpdateResult,
    SecretRecallResult,
)
from ciris_engine.schemas.services.core.secrets import SecretsServiceStats
from ciris_engine.schemas.types import JSONDict

# ActionParameters and FilterConfig don't exist as concrete types - use JSONDict
ActionParameters = JSONDict
FilterConfig = JSONDict

from ...runtime.base import ServiceProtocol


class SecretsServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for secrets service."""

    @abstractmethod
    async def encrypt(self, plaintext: str) -> str:
        """Encrypt a secret."""
        ...

    @abstractmethod
    async def decrypt(self, ciphertext: str) -> str:
        """Decrypt a secret."""
        ...

    @abstractmethod
    async def store_secret(self, key: str, value: str) -> None:
        """Store an encrypted secret."""
        ...

    @abstractmethod
    async def retrieve_secret(self, key: str) -> Optional[str]:
        """Retrieve and decrypt a secret."""
        ...

    @abstractmethod
    async def process_incoming_text(self, text: str, source_message_id: str) -> Tuple[str, List[SecretReference]]:
        """Process incoming text to detect and store secrets."""
        ...

    @abstractmethod
    async def decapsulate_secrets_in_parameters(
        self, action_type: str, action_params: ActionParameters, context: DecapsulationContext
    ) -> ActionParameters:
        """Replace secret UUIDs with decrypted values in action parameters."""
        ...

    @abstractmethod
    async def list_stored_secrets(self, limit: int = 10) -> List[SecretReference]:
        """List all stored secrets (metadata only, no decryption)."""
        ...

    @abstractmethod
    async def get_filter_config(self) -> FilterConfig:
        """Get current filter configuration."""
        ...

    @abstractmethod
    async def recall_secret(
        self, secret_uuid: str, purpose: str, accessor: str = "agent", decrypt: bool = False
    ) -> Optional["SecretRecallResult"]:
        """Recall a stored secret for agent use."""
        ...

    @abstractmethod
    async def forget_secret(self, secret_uuid: str, accessor: str = "agent") -> bool:
        """Forget (delete) a stored secret."""
        ...

    @abstractmethod
    async def update_filter_config(
        self, updates: "FilterUpdateRequest", accessor: str = "agent"
    ) -> "FilterUpdateResult":
        """Update secrets filter configuration."""
        ...

    @abstractmethod
    async def get_service_stats(self) -> "SecretsServiceStats":
        """Get comprehensive service statistics."""
        ...

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if the secrets service is healthy."""
        ...

    @abstractmethod
    async def reencrypt_all(self, new_master_key: bytes) -> bool:
        """Re-encrypt all stored secrets with a new master key."""
        ...
