"""
Test dual LLM service initialization with CIRIS_OPENAI_API_KEY_2.
"""

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.registries.base import Priority
from ciris_engine.logic.runtime.service_initializer import ServiceInitializer
from ciris_engine.schemas.runtime.enums import ServiceType


@pytest.fixture
def mock_config():
    """Create mock config with LLM settings."""
    config = Mock()
    config.services = Mock()
    config.services.llm_endpoint = "https://api.openai.com/v1"
    config.services.llm_model = "gpt-4o-mini"
    config.services.llm_timeout = 30
    config.services.llm_max_retries = 3
    config.security = Mock()
    config.security.audit_key_path = ".ciris_keys"
    config.security.audit_retention_days = 90
    config.security.signing_key_path = ".ciris_keys"
    config.security.secrets_key_path = ".ciris_keys"
    config.database = Mock()
    config.database.graph_db = ":memory:"
    config.database.audit_db = ":memory:"
    config.database.runtime_db = ":memory:"
    config.database.database_url = "sqlite://:memory:"  # Add database_url for Phase 3B
    config.database.main_db = ":memory:"
    config.database.secrets_db = ":memory:"
    config.audit = Mock()
    config.audit.audit_log_path = "audit_logs.jsonl"
    config.mock_llm = False  # Explicitly disable mock LLM
    return config


@pytest.fixture
def mock_service_registry():
    """Create mock service registry."""
    registry = Mock()
    registry.register_global = Mock()
    registry.register_service = Mock()
    registry.get_service = Mock(return_value=None)
    return registry


@pytest.fixture
def mock_time_service():
    """Create mock time service."""
    time_service = Mock()
    time_service.now = Mock()
    return time_service


@pytest.fixture
def service_initializer(mock_config, mock_service_registry, mock_time_service):
    """Create service initializer with mocks."""
    initializer = ServiceInitializer(essential_config=mock_config)
    initializer.service_registry = mock_service_registry
    initializer.time_service = mock_time_service
    initializer.telemetry_service = Mock()
    initializer.config = mock_config  # Store config for _initialize_llm_services
    initializer._skip_llm_init = False  # Ensure LLM initialization is not skipped
    initializer._modules_to_load = []  # Ensure no mock_llm module is in the list
    return initializer


class TestDualLLMService:
    """Test dual LLM service initialization."""

    @pytest.mark.asyncio
    async def test_single_llm_service_without_second_key(self, service_initializer, mock_service_registry):
        """Test that only one LLM service is created when CIRIS_OPENAI_API_KEY_2 is not set."""
        # Ensure second API key is not set
        if "CIRIS_OPENAI_API_KEY_2" in os.environ:
            del os.environ["CIRIS_OPENAI_API_KEY_2"]

        # Set primary API key
        os.environ["OPENAI_API_KEY"] = "test-api-key-1"

        with patch("ciris_engine.logic.runtime.service_initializer.OpenAICompatibleClient") as MockLLMClient:
            mock_llm_instance = AsyncMock()
            MockLLMClient.return_value = mock_llm_instance

            await service_initializer._initialize_llm_services(service_initializer.config)

            # Should create only one LLM service
            assert MockLLMClient.call_count == 1

            # Should register only one service
            assert mock_service_registry.register_service.call_count == 1

            # Check registration details
            call_args = mock_service_registry.register_service.call_args
            assert call_args.kwargs["service_type"] == ServiceType.LLM
            assert call_args.kwargs["priority"] == Priority.HIGH
            assert call_args.kwargs["metadata"]["provider"] == "openai"

    @pytest.mark.asyncio
    async def test_dual_llm_service_with_second_key(self, service_initializer, mock_service_registry):
        """Test that two LLM services are created when CIRIS_OPENAI_API_KEY_2 is set."""
        # Set both API keys
        os.environ["OPENAI_API_KEY"] = "test-api-key-1"
        os.environ["CIRIS_OPENAI_API_KEY_2"] = "test-api-key-2"
        os.environ["CIRIS_OPENAI_API_BASE_2"] = "https://api.lambda.ai/v1"
        os.environ["CIRIS_OPENAI_MODEL_NAME_2"] = "llama-model"

        with patch("ciris_engine.logic.runtime.service_initializer.OpenAICompatibleClient") as MockLLMClient:
            mock_llm_instance = AsyncMock()
            MockLLMClient.return_value = mock_llm_instance

            await service_initializer._initialize_llm_services(service_initializer.config)

            # Should create two LLM services
            assert MockLLMClient.call_count == 2

            # Should register two services
            assert mock_service_registry.register_service.call_count == 2

            # Check first registration (primary)
            first_call = mock_service_registry.register_service.call_args_list[0]
            assert first_call.kwargs["service_type"] == ServiceType.LLM
            assert first_call.kwargs["priority"] == Priority.HIGH
            assert first_call.kwargs["metadata"]["provider"] == "openai"

            # Check second registration (secondary)
            second_call = mock_service_registry.register_service.call_args_list[1]
            assert second_call.kwargs["service_type"] == ServiceType.LLM
            assert second_call.kwargs["priority"] == Priority.NORMAL  # Lower priority
            assert second_call.kwargs["metadata"]["provider"] == "openai_secondary"
            assert second_call.kwargs["metadata"]["model"] == "llama-model"
            assert second_call.kwargs["metadata"]["base_url"] == "https://api.lambda.ai/v1"

    @pytest.mark.asyncio
    async def test_second_llm_config_from_env(self, service_initializer):
        """Test that second LLM configuration is correctly loaded from environment."""
        # Set environment variables
        os.environ["OPENAI_API_KEY"] = "test-api-key-1"
        os.environ["CIRIS_OPENAI_API_KEY_2"] = "test-api-key-2"
        os.environ["CIRIS_OPENAI_API_BASE_2"] = "https://custom.api.com/v1"
        os.environ["CIRIS_OPENAI_MODEL_NAME_2"] = "custom-model"

        with patch("ciris_engine.logic.runtime.service_initializer.OpenAICompatibleClient") as MockLLMClient:
            mock_llm_instance = AsyncMock()
            MockLLMClient.return_value = mock_llm_instance

            await service_initializer._initialize_llm_services(service_initializer.config)

            # Check second LLM client was created with correct config
            second_call = MockLLMClient.call_args_list[1]
            # OpenAICompatibleClient is called with keyword arguments
            second_config = second_call.kwargs["config"]

            assert second_config.api_key == "test-api-key-2"
            assert second_config.base_url == "https://custom.api.com/v1"
            assert second_config.model_name == "custom-model"
            assert second_config.timeout_seconds == 30  # From primary config
            assert second_config.max_retries == 3  # From primary config

    @pytest.mark.asyncio
    async def test_both_services_started(self, service_initializer):
        """Test that both LLM services are properly started."""
        # Set both API keys
        os.environ["OPENAI_API_KEY"] = "test-api-key-1"
        os.environ["CIRIS_OPENAI_API_KEY_2"] = "test-api-key-2"

        with patch("ciris_engine.logic.runtime.service_initializer.OpenAICompatibleClient") as MockLLMClient:
            # Create two different mock instances
            mock_primary = AsyncMock()
            mock_secondary = AsyncMock()
            MockLLMClient.side_effect = [mock_primary, mock_secondary]

            await service_initializer._initialize_llm_services(service_initializer.config)

            # Both services should be started
            mock_primary.start.assert_called_once()
            mock_secondary.start.assert_called_once()

    def teardown_method(self):
        """Clean up environment variables after each test."""
        # Remove test environment variables
        for key in ["OPENAI_API_KEY", "CIRIS_OPENAI_API_KEY_2", "CIRIS_OPENAI_API_BASE_2", "CIRIS_OPENAI_MODEL_NAME_2"]:
            if key in os.environ:
                del os.environ[key]
