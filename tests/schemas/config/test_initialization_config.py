"""
Tests for root initialization configuration model.
"""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.schemas.config.governance_config import GovernanceConfig
from ciris_engine.schemas.config.infrastructure_config import InfrastructureConfig
from ciris_engine.schemas.config.initialization_config import InitializationConfig
from ciris_engine.schemas.config.llm_config import LLMConfig
from ciris_engine.schemas.config.memory_config import MemoryConfig
from ciris_engine.schemas.config.observability_config import ObservabilityConfig


class TestInitializationConfig:
    """Tests for complete InitializationConfig."""

    def test_from_essential_config_creates_complete_config(self):
        """InitializationConfig.from_essential_config() creates all sub-configs."""
        # Mock essential config
        essential_config = MagicMock()
        essential_config.security.secrets_key_path = Path(".ciris_keys")
        essential_config.audit.audit_log_path = Path("audit.jsonl")
        essential_config.security.signing_key_path = Path(".keys/signing.pem")
        essential_config.services.llm_endpoint = "https://api.openai.com/v1"
        essential_config.services.llm_model = "gpt-4o-mini"
        essential_config.services.llm_timeout = 30
        essential_config.services.llm_max_retries = 3

        env = {"OPENAI_API_KEY": "test-key", "CIRIS_SIMPLE_FREE_USES": "10"}

        # Mock all db path helpers
        with (
            patch.dict(os.environ, env, clear=True),
            patch("ciris_engine.logic.config.db_paths.get_secrets_db_full_path", return_value="/data/secrets.db"),
            patch("ciris_engine.logic.config.db_paths.get_sqlite_db_full_path", return_value="/data/memory.db"),
            patch("ciris_engine.logic.config.db_paths.get_audit_db_full_path", return_value="/data/audit.db"),
        ):
            config = InitializationConfig.from_essential_config(essential_config, skip_llm_init=False)

        # Verify all sub-configs created
        assert isinstance(config.infrastructure, InfrastructureConfig)
        assert isinstance(config.memory, MemoryConfig)
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.observability, ObservabilityConfig)
        assert isinstance(config.governance, GovernanceConfig)

        # Spot-check values
        assert config.infrastructure.resource_monitor.simple.free_uses == 10
        assert config.llm.primary.api_key == "test-key"
        assert config.llm.skip_initialization is False
        assert config.memory.memory_db_path == Path("/data/memory.db")
        assert config.observability.audit.db_path == Path("/data/audit.db")
        assert config.governance.visibility.db_path == Path("/data/memory.db")  # Uses main db

    def test_from_essential_config_respects_skip_llm_init(self):
        """InitializationConfig.from_essential_config() passes skip_llm_init to LLMConfig."""
        essential_config = MagicMock()
        essential_config.security.secrets_key_path = Path(".ciris_keys")
        essential_config.audit.audit_log_path = Path("audit.jsonl")
        essential_config.security.signing_key_path = Path(".keys/signing.pem")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("ciris_engine.logic.config.db_paths.get_secrets_db_full_path", return_value="/data/secrets.db"),
            patch("ciris_engine.logic.config.db_paths.get_sqlite_db_full_path", return_value="/data/memory.db"),
            patch("ciris_engine.logic.config.db_paths.get_audit_db_full_path", return_value="/data/audit.db"),
        ):
            config = InitializationConfig.from_essential_config(essential_config, skip_llm_init=True)

        assert config.llm.skip_initialization is True
        assert config.llm.primary is None
        assert config.llm.secondary is None

    def test_model_structure(self):
        """InitializationConfig can be constructed with all sub-configs."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("ciris_engine.logic.config.db_paths.get_sqlite_db_full_path", return_value="/data/memory.db"),
            patch("ciris_engine.logic.config.db_paths.get_audit_db_full_path", return_value="/data/audit.db"),
        ):
            essential_mock = MagicMock()
            essential_mock.audit.audit_log_path = Path("audit.jsonl")
            essential_mock.security.signing_key_path = Path(".keys/signing.pem")

            config = InitializationConfig(
                infrastructure=InfrastructureConfig.from_env(),
                memory=MemoryConfig(
                    secrets_key_path=Path(".keys"), secrets_db_path=Path("/data/secrets.db"), memory_db_path=Path("/data/memory.db")
                ),
                llm=LLMConfig(skip_initialization=True),
                observability=ObservabilityConfig.from_essential_config(essential_mock),
                governance=GovernanceConfig.from_essential_config(essential_mock),
            )

        assert config is not None
        assert isinstance(config.infrastructure, InfrastructureConfig)
        assert isinstance(config.memory, MemoryConfig)
        assert isinstance(config.llm, LLMConfig)
        assert isinstance(config.observability, ObservabilityConfig)
        assert isinstance(config.governance, GovernanceConfig)
