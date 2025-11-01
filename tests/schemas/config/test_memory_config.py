"""
Tests for memory service configuration models.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.schemas.config.memory_config import MemoryConfig


class TestMemoryConfig:
    """Tests for MemoryConfig model."""

    def test_from_essential_config_uses_helper_functions(self):
        """MemoryConfig.from_essential_config() uses db path helper functions."""
        # Mock essential config
        essential_config = MagicMock()
        essential_config.security.secrets_key_path = Path(".ciris_keys")

        # Mock helper functions (patch where they're imported, not where they're defined)
        with patch("ciris_engine.logic.config.db_paths.get_secrets_db_full_path") as mock_secrets_path, patch(
            "ciris_engine.logic.config.db_paths.get_sqlite_db_full_path"
        ) as mock_memory_path:
            mock_secrets_path.return_value = "/app/data/secrets.db"
            mock_memory_path.return_value = "/app/data/ciris_engine.db"

            config = MemoryConfig.from_essential_config(essential_config)

        # Verify helper functions were called
        mock_secrets_path.assert_called_once_with(essential_config)
        mock_memory_path.assert_called_once_with(essential_config)

        # Verify config created correctly (paths are returned as strings from helpers)
        assert config.secrets_key_path == Path(".ciris_keys")
        assert config.secrets_db_path == "/app/data/secrets.db"
        assert config.memory_db_path == "/app/data/ciris_engine.db"

    def test_paths_accept_strings_for_postgres_urls(self):
        """MemoryConfig accepts string paths for PostgreSQL connection strings."""
        # Test with PostgreSQL connection strings (must stay as strings, not Path objects)
        postgres_url = "postgresql://user:pass@host:5432/ciris_db?sslmode=require"
        postgres_secrets_url = "postgresql://user:pass@host:5432/ciris_db_secrets?sslmode=require"

        config = MemoryConfig(
            secrets_key_path=Path(".ciris_keys"),
            secrets_db_path=postgres_secrets_url,
            memory_db_path=postgres_url,
        )

        # Verify URLs are preserved as strings (not mangled by Path conversion)
        assert isinstance(config.secrets_key_path, Path)
        assert isinstance(config.secrets_db_path, str)
        assert isinstance(config.memory_db_path, str)
        assert config.secrets_db_path == postgres_secrets_url
        assert config.memory_db_path == postgres_url

    def test_paths_accept_path_objects_for_sqlite(self):
        """MemoryConfig accepts Path objects for SQLite file paths."""
        config = MemoryConfig(
            secrets_key_path=".ciris_keys",
            secrets_db_path=Path("/data/secrets.db"),
            memory_db_path=Path("/data/memory.db"),
        )

        assert isinstance(config.secrets_key_path, Path)
        # Pydantic may convert Path to str or keep as Path - both are valid
        assert config.secrets_db_path in ("/data/secrets.db", Path("/data/secrets.db"))
        assert config.memory_db_path in ("/data/memory.db", Path("/data/memory.db"))
