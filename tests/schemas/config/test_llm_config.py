"""
Tests for LLM service configuration models.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.schemas.config.llm_config import InstructorMode, LLMConfig, LLMProviderConfig


class TestLLMProviderConfig:
    """Tests for LLMProviderConfig model."""

    def test_default_values(self):
        """LLMProviderConfig uses sensible defaults."""
        config = LLMProviderConfig(api_key="test-key")

        assert config.api_key == "test-key"
        assert config.base_url == "https://api.openai.com/v1"
        assert config.model_name == "gpt-4o-mini"
        assert config.instructor_mode == InstructorMode.JSON
        assert config.timeout_seconds == 30
        assert config.max_retries == 3

    def test_custom_values(self):
        """LLMProviderConfig accepts custom values."""
        config = LLMProviderConfig(
            api_key="custom-key",
            base_url="https://custom.api.com/v1",
            model_name="gpt-4o",
            instructor_mode=InstructorMode.TOOLS,
            timeout_seconds=60,
            max_retries=5,
        )

        assert config.api_key == "custom-key"
        assert config.base_url == "https://custom.api.com/v1"
        assert config.model_name == "gpt-4o"
        assert config.instructor_mode == InstructorMode.TOOLS
        assert config.timeout_seconds == 60
        assert config.max_retries == 5


class TestLLMConfig:
    """Tests for LLMConfig model."""

    def test_from_env_loads_primary_llm(self):
        """LLMConfig.from_env_and_essential() loads primary LLM from OPENAI_API_KEY."""
        essential_config = MagicMock()
        essential_config.services.llm_endpoint = "https://api.openai.com/v1"
        essential_config.services.llm_model = "gpt-4o-mini"
        essential_config.services.llm_timeout = 30
        essential_config.services.llm_max_retries = 3

        env = {"OPENAI_API_KEY": "primary-key", "INSTRUCTOR_MODE": "JSON"}

        with patch.dict(os.environ, env, clear=True):
            config = LLMConfig.from_env_and_essential(essential_config)

        assert config.primary is not None
        assert config.primary.api_key == "primary-key"
        assert config.primary.instructor_mode == InstructorMode.JSON
        assert config.secondary is None
        assert config.skip_initialization is False

    def test_from_env_loads_secondary_llm(self):
        """LLMConfig.from_env_and_essential() loads secondary LLM when key provided."""
        essential_config = MagicMock()
        essential_config.services.llm_endpoint = "https://api.openai.com/v1"
        essential_config.services.llm_model = "gpt-4o-mini"
        essential_config.services.llm_timeout = 30
        essential_config.services.llm_max_retries = 3

        env = {
            "OPENAI_API_KEY": "primary-key",
            "CIRIS_OPENAI_API_KEY_2": "secondary-key",
            "CIRIS_OPENAI_API_BASE_2": "https://secondary.api.com/v1",
            "CIRIS_OPENAI_MODEL_NAME_2": "gpt-4o",
        }

        with patch.dict(os.environ, env, clear=True):
            config = LLMConfig.from_env_and_essential(essential_config)

        assert config.primary is not None
        assert config.primary.api_key == "primary-key"
        assert config.secondary is not None
        assert config.secondary.api_key == "secondary-key"
        assert config.secondary.base_url == "https://secondary.api.com/v1"
        assert config.secondary.model_name == "gpt-4o"

    def test_skip_initialization_true_when_requested(self):
        """LLMConfig.from_env_and_essential() sets skip_initialization=True for mock mode."""
        essential_config = MagicMock()

        config = LLMConfig.from_env_and_essential(essential_config, skip_llm_init=True)

        assert config.skip_initialization is True
        assert config.primary is None
        assert config.secondary is None

    def test_secondary_none_when_no_key_provided(self):
        """LLMConfig.from_env_and_essential() sets secondary=None when no key."""
        essential_config = MagicMock()
        essential_config.services.llm_endpoint = "https://api.openai.com/v1"
        essential_config.services.llm_model = "gpt-4o-mini"
        essential_config.services.llm_timeout = 30
        essential_config.services.llm_max_retries = 3

        env = {"OPENAI_API_KEY": "primary-key"}

        with patch.dict(os.environ, env, clear=True):
            config = LLMConfig.from_env_and_essential(essential_config)

        assert config.primary is not None
        assert config.secondary is None
