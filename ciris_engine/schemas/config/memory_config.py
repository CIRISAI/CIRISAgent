"""
Memory service configuration models.

This module provides typed configuration for memory-related services:
- SecretsService
- MemoryService (LocalGraphMemoryService)
"""

from pathlib import Path
from typing import TYPE_CHECKING, Union

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ciris_engine.schemas.config.essential import EssentialConfig


class MemoryConfig(BaseModel):
    """Configuration for memory service initialization."""

    # Secrets service config (memory depends on secrets)
    secrets_key_path: Path = Field(default=Path(".ciris_keys"), description="Directory containing encryption keys")
    secrets_db_path: Union[str, Path] = Field(
        description="Path to secrets database (SQLite path or PostgreSQL connection string)"
    )

    # Memory service config
    memory_db_path: Union[str, Path] = Field(
        description="Path to main memory database (SQLite path or PostgreSQL connection string)"
    )

    @classmethod
    def from_essential_config(cls, essential_config: "EssentialConfig") -> "MemoryConfig":
        """Create from EssentialConfig using helper functions.

        This maintains backward compatibility with existing path resolution.

        Args:
            essential_config: EssentialConfig instance

        Returns:
            MemoryConfig with resolved paths
        """
        from ciris_engine.logic.config.db_paths import get_secrets_db_full_path, get_sqlite_db_full_path

        return cls(
            secrets_key_path=essential_config.security.secrets_key_path,
            secrets_db_path=get_secrets_db_full_path(essential_config),  # str (SQLite path or Postgres URL)
            memory_db_path=get_sqlite_db_full_path(essential_config),  # str (SQLite path or Postgres URL)
        )
