"""Unit tests for LLM provider persistence CRUD helpers."""

import json
import pytest
from pathlib import Path
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from ciris_engine.logic.persistence.llm_providers import (
    CIRIS_SERVICES_DISABLED_VAR,
    LLMProviderConfig,
    PersistenceResult,
    RUNTIME_PROVIDERS_CONFIG_KEY,
    RUNTIME_PROVIDERS_ENV_VAR,
    clear_all_providers,
    create_provider,
    delete_provider,
    get_ciris_services_disabled,
    get_provider,
    list_providers,
    read_providers_from_env,
    read_providers_from_graph,
    set_ciris_services_disabled,
    update_provider,
    upsert_provider,
    write_providers_to_env,
    write_providers_to_graph,
)


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_provider_config() -> LLMProviderConfig:
    """Create a sample provider config."""
    return LLMProviderConfig(
        provider_id="local",
        base_url="http://localhost:8080/v1",
        model="llama3",
        api_key="local",
        priority="normal",
    )


@pytest.fixture
def sample_provider_dict() -> dict[str, Any]:
    """Create a sample provider config as dict."""
    return {
        "provider_id": "local",
        "base_url": "http://localhost:8080/v1",
        "model": "llama3",
        "api_key": "local",
        "priority": "normal",
    }


@pytest.fixture
def mock_config_service() -> MagicMock:
    """Create a mock GraphConfigService."""
    service = MagicMock()
    service.get_config = AsyncMock(return_value=None)
    service.set_config = AsyncMock()
    return service


@pytest.fixture
def temp_env_file(tmp_path: Path) -> Path:
    """Create a temporary .env file."""
    env_file = tmp_path / ".env"
    env_file.write_text("# Test env file\nSOME_VAR=value\n")
    return env_file


# =============================================================================
# LLMProviderConfig Tests
# =============================================================================


class TestLLMProviderConfig:
    """Tests for LLMProviderConfig model."""

    def test_create_with_defaults(self):
        """Test creating config with minimal required fields."""
        config = LLMProviderConfig(
            provider_id="local",
            base_url="http://localhost:8080",
        )
        assert config.provider_id == "local"
        assert config.base_url == "http://localhost:8080"
        assert config.model == "default"
        assert config.api_key == ""
        assert config.priority == "fallback"

    def test_create_with_all_fields(self, sample_provider_config: LLMProviderConfig):
        """Test creating config with all fields."""
        assert sample_provider_config.provider_id == "local"
        assert sample_provider_config.base_url == "http://localhost:8080/v1"
        assert sample_provider_config.model == "llama3"
        assert sample_provider_config.api_key == "local"
        assert sample_provider_config.priority == "normal"

    def test_to_dict(self, sample_provider_config: LLMProviderConfig):
        """Test converting to dict."""
        result = sample_provider_config.to_dict()
        assert result == {
            "provider_id": "local",
            "base_url": "http://localhost:8080/v1",
            "model": "llama3",
            "api_key": "local",
            "priority": "normal",
            "enabled": True,
        }

    def test_from_dict(self, sample_provider_dict: dict[str, Any]):
        """Test creating from dict."""
        config = LLMProviderConfig.from_dict(sample_provider_dict)
        assert config.provider_id == "local"
        assert config.base_url == "http://localhost:8080/v1"
        assert config.model == "llama3"

    def test_roundtrip(self, sample_provider_config: LLMProviderConfig):
        """Test dict roundtrip."""
        d = sample_provider_config.to_dict()
        config2 = LLMProviderConfig.from_dict(d)
        assert config2 == sample_provider_config


# =============================================================================
# .env File Operations Tests
# =============================================================================


class TestEnvFileOperations:
    """Tests for .env file read/write operations."""

    def test_read_providers_from_env_empty(self, temp_env_file: Path):
        """Test reading from .env with no providers."""
        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = read_providers_from_env()
            assert result == {}

    def test_read_providers_from_env_with_providers(self, temp_env_file: Path):
        """Test reading providers from .env."""
        providers_data = {
            "jetson_local": {
                "provider_id": "local",
                "base_url": "http://jetson.local:8080/v1",
                "model": "gemma",
                "api_key": "",
                "priority": "high",
            }
        }
        content = temp_env_file.read_text()
        content += f"\n{RUNTIME_PROVIDERS_ENV_VAR}='{json.dumps(providers_data)}'\n"
        temp_env_file.write_text(content)

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = read_providers_from_env()
            assert "jetson_local" in result
            assert result["jetson_local"].provider_id == "local"
            assert result["jetson_local"].base_url == "http://jetson.local:8080/v1"

    def test_read_providers_from_env_double_quoted(self, temp_env_file: Path):
        """Test reading providers with double-quoted JSON."""
        providers_data = {"test": {"provider_id": "x", "base_url": "http://x", "model": "m", "api_key": "", "priority": "low"}}
        content = temp_env_file.read_text()
        content += f'\n{RUNTIME_PROVIDERS_ENV_VAR}="{json.dumps(providers_data)}"\n'
        temp_env_file.write_text(content)

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = read_providers_from_env()
            assert "test" in result

    def test_write_providers_to_env(
        self, temp_env_file: Path, sample_provider_config: LLMProviderConfig
    ):
        """Test writing providers to .env."""
        providers = {"my_provider": sample_provider_config}

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = write_providers_to_env(providers)
            assert result is True

            # Verify written content
            content = temp_env_file.read_text()
            assert RUNTIME_PROVIDERS_ENV_VAR in content
            assert "my_provider" in content

    def test_write_providers_to_env_overwrites_existing(
        self, temp_env_file: Path, sample_provider_config: LLMProviderConfig
    ):
        """Test that writing overwrites existing provider line."""
        # Write initial providers
        initial_data = {"old_provider": {"provider_id": "old", "base_url": "http://old", "model": "m", "api_key": "", "priority": "low"}}
        content = temp_env_file.read_text()
        content += f"\n{RUNTIME_PROVIDERS_ENV_VAR}='{json.dumps(initial_data)}'\n"
        temp_env_file.write_text(content)

        # Write new providers
        providers = {"new_provider": sample_provider_config}

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = write_providers_to_env(providers)
            assert result is True

            # Verify only new provider exists
            content = temp_env_file.read_text()
            assert "new_provider" in content
            assert "old_provider" not in content
            # Should only have one RUNTIME_PROVIDERS line
            assert content.count(RUNTIME_PROVIDERS_ENV_VAR) == 1

    def test_write_empty_providers_removes_line(self, temp_env_file: Path):
        """Test that writing empty dict removes the provider line."""
        # Add existing provider line
        content = temp_env_file.read_text()
        content += f"\n{RUNTIME_PROVIDERS_ENV_VAR}='{{\"test\": {{}}}}'\n"
        temp_env_file.write_text(content)

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = write_providers_to_env({})
            assert result is True

            content = temp_env_file.read_text()
            assert RUNTIME_PROVIDERS_ENV_VAR not in content

    def test_write_providers_no_env_file(self, tmp_path: Path):
        """Test writing when .env doesn't exist."""
        nonexistent = tmp_path / "nonexistent.env"

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=nonexistent,
        ):
            result = write_providers_to_env({"test": LLMProviderConfig(provider_id="x", base_url="http://x")})
            assert result is False


# =============================================================================
# Graph Config Operations Tests
# =============================================================================


class TestGraphConfigOperations:
    """Tests for GraphConfigService read/write operations."""

    @pytest.mark.asyncio
    async def test_read_providers_from_graph_empty(
        self, mock_config_service: MagicMock
    ):
        """Test reading from graph with no providers."""
        mock_config_service.get_config.return_value = None

        result = await read_providers_from_graph(mock_config_service)
        assert result == {}
        mock_config_service.get_config.assert_called_once_with(RUNTIME_PROVIDERS_CONFIG_KEY)

    @pytest.mark.asyncio
    async def test_read_providers_from_graph_with_providers(
        self, mock_config_service: MagicMock
    ):
        """Test reading providers from graph."""
        mock_config = MagicMock()
        mock_config.value.dict_value = {
            "test_provider": {
                "provider_id": "local",
                "base_url": "http://test:8080",
                "model": "llama",
                "api_key": "",
                "priority": "high",
            }
        }
        mock_config_service.get_config.return_value = mock_config

        result = await read_providers_from_graph(mock_config_service)
        assert "test_provider" in result
        assert result["test_provider"].provider_id == "local"

    @pytest.mark.asyncio
    async def test_read_providers_from_graph_no_service(self):
        """Test reading with no config service."""
        result = await read_providers_from_graph(None)
        assert result == {}

    @pytest.mark.asyncio
    async def test_write_providers_to_graph(
        self,
        mock_config_service: MagicMock,
        sample_provider_config: LLMProviderConfig,
    ):
        """Test writing providers to graph."""
        providers = {"my_provider": sample_provider_config}

        result = await write_providers_to_graph(mock_config_service, providers)
        assert result is True

        mock_config_service.set_config.assert_called_once()
        call_kwargs = mock_config_service.set_config.call_args
        assert call_kwargs.kwargs["key"] == RUNTIME_PROVIDERS_CONFIG_KEY
        assert "my_provider" in call_kwargs.kwargs["value"]

    @pytest.mark.asyncio
    async def test_write_providers_to_graph_no_service(
        self, sample_provider_config: LLMProviderConfig
    ):
        """Test writing with no config service."""
        result = await write_providers_to_graph(None, {"test": sample_provider_config})
        assert result is False


# =============================================================================
# CRUD Operations Tests
# =============================================================================


class TestCRUDOperations:
    """Tests for combined CRUD operations."""

    @pytest.mark.asyncio
    async def test_list_providers_from_graph(
        self, mock_config_service: MagicMock
    ):
        """Test listing providers prefers graph."""
        mock_config = MagicMock()
        mock_config.value.dict_value = {
            "graph_provider": {
                "provider_id": "graph",
                "base_url": "http://graph",
                "model": "m",
                "api_key": "",
                "priority": "high",
            }
        }
        mock_config_service.get_config.return_value = mock_config

        result = await list_providers(mock_config_service)
        assert "graph_provider" in result
        assert result["graph_provider"].provider_id == "graph"

    @pytest.mark.asyncio
    async def test_list_providers_falls_back_to_env(
        self, mock_config_service: MagicMock, temp_env_file: Path
    ):
        """Test listing falls back to .env when graph empty."""
        mock_config_service.get_config.return_value = None

        # Add provider to .env
        providers_data = {"env_provider": {"provider_id": "env", "base_url": "http://env", "model": "m", "api_key": "", "priority": "low"}}
        content = temp_env_file.read_text()
        content += f"\n{RUNTIME_PROVIDERS_ENV_VAR}='{json.dumps(providers_data)}'\n"
        temp_env_file.write_text(content)

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = await list_providers(mock_config_service)
            assert "env_provider" in result

    @pytest.mark.asyncio
    async def test_get_provider_found(
        self, mock_config_service: MagicMock
    ):
        """Test getting a specific provider."""
        mock_config = MagicMock()
        mock_config.value.dict_value = {
            "my_provider": {
                "provider_id": "local",
                "base_url": "http://localhost",
                "model": "m",
                "api_key": "",
                "priority": "normal",
            }
        }
        mock_config_service.get_config.return_value = mock_config

        result = await get_provider("my_provider", mock_config_service)
        assert result is not None
        assert result.provider_id == "local"

    @pytest.mark.asyncio
    async def test_get_provider_not_found(
        self, mock_config_service: MagicMock
    ):
        """Test getting a nonexistent provider."""
        mock_config_service.get_config.return_value = None

        result = await get_provider("nonexistent", mock_config_service)
        assert result is None

    @pytest.mark.asyncio
    async def test_create_provider_success(
        self,
        mock_config_service: MagicMock,
        sample_provider_config: LLMProviderConfig,
        temp_env_file: Path,
    ):
        """Test creating a new provider."""
        mock_config_service.get_config.return_value = None

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = await create_provider(
                "new_provider", sample_provider_config, mock_config_service
            )

            assert result.success is True
            assert result.graph_persisted is True
            assert result.env_persisted is True

    @pytest.mark.asyncio
    async def test_create_provider_already_exists(
        self,
        mock_config_service: MagicMock,
        sample_provider_config: LLMProviderConfig,
    ):
        """Test creating a provider that already exists."""
        mock_config = MagicMock()
        mock_config.value.dict_value = {
            "existing": {"provider_id": "x", "base_url": "http://x", "model": "m", "api_key": "", "priority": "low"}
        }
        mock_config_service.get_config.return_value = mock_config

        result = await create_provider(
            "existing", sample_provider_config, mock_config_service
        )

        assert result.success is False
        assert "already exists" in result.error

    @pytest.mark.asyncio
    async def test_update_provider_success(
        self,
        mock_config_service: MagicMock,
        sample_provider_config: LLMProviderConfig,
        temp_env_file: Path,
    ):
        """Test updating an existing provider."""
        mock_config = MagicMock()
        mock_config.value.dict_value = {
            "existing": {"provider_id": "old", "base_url": "http://old", "model": "m", "api_key": "", "priority": "low"}
        }
        mock_config_service.get_config.return_value = mock_config

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = await update_provider(
                "existing", sample_provider_config, mock_config_service
            )

            assert result.success is True

    @pytest.mark.asyncio
    async def test_update_provider_not_found(
        self,
        mock_config_service: MagicMock,
        sample_provider_config: LLMProviderConfig,
    ):
        """Test updating a nonexistent provider."""
        mock_config_service.get_config.return_value = None

        result = await update_provider(
            "nonexistent", sample_provider_config, mock_config_service
        )

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_delete_provider_success(
        self,
        mock_config_service: MagicMock,
        temp_env_file: Path,
    ):
        """Test deleting a provider."""
        mock_config = MagicMock()
        mock_config.value.dict_value = {
            "to_delete": {"provider_id": "x", "base_url": "http://x", "model": "m", "api_key": "", "priority": "low"}
        }
        mock_config_service.get_config.return_value = mock_config

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = await delete_provider("to_delete", mock_config_service)

            assert result.success is True

    @pytest.mark.asyncio
    async def test_delete_provider_not_found(
        self, mock_config_service: MagicMock
    ):
        """Test deleting a nonexistent provider."""
        mock_config_service.get_config.return_value = None

        result = await delete_provider("nonexistent", mock_config_service)

        assert result.success is False
        assert "not found" in result.error

    @pytest.mark.asyncio
    async def test_upsert_provider_creates(
        self,
        mock_config_service: MagicMock,
        sample_provider_config: LLMProviderConfig,
        temp_env_file: Path,
    ):
        """Test upsert creates new provider."""
        mock_config_service.get_config.return_value = None

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = await upsert_provider(
                "new_provider", sample_provider_config, mock_config_service
            )

            assert result.success is True

    @pytest.mark.asyncio
    async def test_upsert_provider_updates(
        self,
        mock_config_service: MagicMock,
        sample_provider_config: LLMProviderConfig,
        temp_env_file: Path,
    ):
        """Test upsert updates existing provider."""
        mock_config = MagicMock()
        mock_config.value.dict_value = {
            "existing": {"provider_id": "old", "base_url": "http://old", "model": "m", "api_key": "", "priority": "low"}
        }
        mock_config_service.get_config.return_value = mock_config

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = await upsert_provider(
                "existing", sample_provider_config, mock_config_service
            )

            assert result.success is True

    @pytest.mark.asyncio
    async def test_clear_all_providers(
        self,
        mock_config_service: MagicMock,
        temp_env_file: Path,
    ):
        """Test clearing all providers."""
        # Add existing provider to .env
        content = temp_env_file.read_text()
        content += f"\n{RUNTIME_PROVIDERS_ENV_VAR}='{{\"test\": {{}}}}'\n"
        temp_env_file.write_text(content)

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = await clear_all_providers(mock_config_service)

            assert result.success is True

            # Verify .env is cleared
            content = temp_env_file.read_text()
            assert RUNTIME_PROVIDERS_ENV_VAR not in content


# =============================================================================
# CIRIS Services Disabled Flag Tests
# =============================================================================


class TestCirisServicesDisabledFlag:
    """Tests for CIRIS_SERVICES_DISABLED flag management.

    The CIRIS_SERVICES_DISABLED flag controls whether CIRIS hosted services
    (LLM providers and tools) are initialized on startup.

    Expected behavior:
    - set_ciris_services_disabled(True) writes CIRIS_SERVICES_DISABLED=true to .env
    - set_ciris_services_disabled(False) writes CIRIS_SERVICES_DISABLED=false to .env
    - get_ciris_services_disabled() reads from environment variable
    - Flag persists across restarts via .env file
    """

    def test_set_ciris_services_disabled_true(self, temp_env_file: Path) -> None:
        """Test setting CIRIS services as disabled.

        Expected:
        - Returns True (success)
        - Writes CIRIS_SERVICES_DISABLED=true to .env
        - Preserves existing .env content
        """
        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = set_ciris_services_disabled(True)

            assert result is True

            content = temp_env_file.read_text()
            assert f"{CIRIS_SERVICES_DISABLED_VAR}=true" in content
            # Verify existing content preserved
            assert "SOME_VAR=value" in content

    def test_set_ciris_services_disabled_false(self, temp_env_file: Path) -> None:
        """Test re-enabling CIRIS services.

        Expected:
        - Returns True (success)
        - Writes CIRIS_SERVICES_DISABLED=false to .env
        """
        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = set_ciris_services_disabled(False)

            assert result is True

            content = temp_env_file.read_text()
            assert f"{CIRIS_SERVICES_DISABLED_VAR}=false" in content

    def test_set_ciris_services_disabled_overwrites_existing(
        self, temp_env_file: Path
    ) -> None:
        """Test that setting flag overwrites existing value.

        Expected:
        - Removes old CIRIS_SERVICES_DISABLED line
        - Adds new line with updated value
        - Only one instance of the flag in file
        """
        # Add existing flag
        content = temp_env_file.read_text()
        content += f"\n{CIRIS_SERVICES_DISABLED_VAR}=false\n"
        temp_env_file.write_text(content)

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            result = set_ciris_services_disabled(True)

            assert result is True

            content = temp_env_file.read_text()
            # Should only have one instance
            assert content.count(CIRIS_SERVICES_DISABLED_VAR) == 1
            assert f"{CIRIS_SERVICES_DISABLED_VAR}=true" in content
            assert f"{CIRIS_SERVICES_DISABLED_VAR}=false" not in content

    def test_set_ciris_services_disabled_no_env_file(self, tmp_path: Path) -> None:
        """Test setting flag when .env doesn't exist.

        Expected:
        - Returns False (failure)
        - Does not create .env file
        """
        nonexistent = tmp_path / "nonexistent.env"

        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=nonexistent,
        ):
            result = set_ciris_services_disabled(True)

            assert result is False
            assert not nonexistent.exists()

    def test_set_ciris_services_disabled_no_env_path(self) -> None:
        """Test setting flag when env path cannot be determined.

        Expected:
        - Returns False (failure)
        """
        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=None,
        ):
            result = set_ciris_services_disabled(True)

            assert result is False

    def test_get_ciris_services_disabled_true(self) -> None:
        """Test reading disabled flag when set to true.

        Expected:
        - Returns True when env var is "true"
        """
        with patch.dict("os.environ", {CIRIS_SERVICES_DISABLED_VAR: "true"}):
            result = get_ciris_services_disabled()
            assert result is True

    def test_get_ciris_services_disabled_one(self) -> None:
        """Test reading disabled flag when set to "1".

        Expected:
        - Returns True when env var is "1"
        """
        with patch.dict("os.environ", {CIRIS_SERVICES_DISABLED_VAR: "1"}):
            result = get_ciris_services_disabled()
            assert result is True

    def test_get_ciris_services_disabled_yes(self) -> None:
        """Test reading disabled flag when set to "yes".

        Expected:
        - Returns True when env var is "yes"
        """
        with patch.dict("os.environ", {CIRIS_SERVICES_DISABLED_VAR: "yes"}):
            result = get_ciris_services_disabled()
            assert result is True

    def test_get_ciris_services_disabled_case_insensitive(self) -> None:
        """Test reading disabled flag is case-insensitive.

        Expected:
        - Returns True for "TRUE", "True", etc.
        """
        with patch.dict("os.environ", {CIRIS_SERVICES_DISABLED_VAR: "TRUE"}):
            result = get_ciris_services_disabled()
            assert result is True

        with patch.dict("os.environ", {CIRIS_SERVICES_DISABLED_VAR: "True"}):
            result = get_ciris_services_disabled()
            assert result is True

    def test_get_ciris_services_disabled_false(self) -> None:
        """Test reading disabled flag when set to false.

        Expected:
        - Returns False when env var is "false"
        """
        with patch.dict("os.environ", {CIRIS_SERVICES_DISABLED_VAR: "false"}):
            result = get_ciris_services_disabled()
            assert result is False

    def test_get_ciris_services_disabled_not_set(self) -> None:
        """Test reading disabled flag when not set.

        Expected:
        - Returns False when env var is not set
        """
        with patch.dict("os.environ", {}, clear=True):
            # Ensure the var is not in environment
            import os
            os.environ.pop(CIRIS_SERVICES_DISABLED_VAR, None)

            result = get_ciris_services_disabled()
            assert result is False

    def test_get_ciris_services_disabled_empty(self) -> None:
        """Test reading disabled flag when empty.

        Expected:
        - Returns False when env var is empty string
        """
        with patch.dict("os.environ", {CIRIS_SERVICES_DISABLED_VAR: ""}):
            result = get_ciris_services_disabled()
            assert result is False

    def test_get_ciris_services_disabled_invalid(self) -> None:
        """Test reading disabled flag with invalid value.

        Expected:
        - Returns False for unrecognized values
        """
        with patch.dict("os.environ", {CIRIS_SERVICES_DISABLED_VAR: "maybe"}):
            result = get_ciris_services_disabled()
            assert result is False

    def test_roundtrip_disable_enable(self, temp_env_file: Path) -> None:
        """Test full roundtrip: disable then enable.

        Expected:
        - Can disable, read as disabled
        - Can re-enable, read as enabled
        - File correctly updated at each step
        """
        with patch(
            "ciris_engine.logic.persistence.llm_providers._get_env_path",
            return_value=temp_env_file,
        ):
            # Disable
            assert set_ciris_services_disabled(True) is True
            content = temp_env_file.read_text()
            assert f"{CIRIS_SERVICES_DISABLED_VAR}=true" in content

            # Enable
            assert set_ciris_services_disabled(False) is True
            content = temp_env_file.read_text()
            assert f"{CIRIS_SERVICES_DISABLED_VAR}=false" in content
            # Old value should be gone
            assert f"{CIRIS_SERVICES_DISABLED_VAR}=true" not in content
