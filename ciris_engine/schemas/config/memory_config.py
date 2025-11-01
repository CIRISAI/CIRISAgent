"""
Memory service configuration models.

This module provides typed configuration for memory-related services:
- SecretsService
- MemoryService (LocalGraphMemoryService)
"""

from pathlib import Path

from pydantic import BaseModel, Field


class MemoryConfig(BaseModel):
    """Configuration for memory service initialization."""

    # Secrets service config (memory depends on secrets)
    secrets_key_path: Path = Field(default=Path(".ciris_keys"), description="Directory containing encryption keys")
    secrets_db_path: Path = Field(description="Path to secrets database")

    # Memory service config
    memory_db_path: Path = Field(description="Path to main memory database")

    @classmethod
    def from_essential_config(cls, essential_config) -> "MemoryConfig":
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
            secrets_db_path=Path(get_secrets_db_full_path(essential_config)),
            memory_db_path=Path(get_sqlite_db_full_path(essential_config)),
        )
