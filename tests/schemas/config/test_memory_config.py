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

        # Verify config created correctly
        assert config.secrets_key_path == Path(".ciris_keys")
        assert config.secrets_db_path == Path("/app/data/secrets.db")
        assert config.memory_db_path == Path("/app/data/ciris_engine.db")

    def test_paths_are_path_objects(self):
        """MemoryConfig converts paths to Path objects."""
        config = MemoryConfig(
            secrets_key_path=".ciris_keys", secrets_db_path="/data/secrets.db", memory_db_path="/data/memory.db"
        )

        assert isinstance(config.secrets_key_path, Path)
        assert isinstance(config.secrets_db_path, Path)
        assert isinstance(config.memory_db_path, Path)
