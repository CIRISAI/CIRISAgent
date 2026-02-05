"""Additional tests for setup routes to increase coverage.

Covers uncovered helper functions:
- _validate_api_key_for_provider
- _classify_llm_connection_error
- _validate_setup_passwords
- _log_oauth_linking_skip
- _get_llm_providers
- _get_available_adapters
- _should_skip_manifest
- _create_adapter_from_manifest
"""

from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.setup import (
    AdapterConfig,
    LLMValidationRequest,
    SetupCompleteRequest,
    _classify_llm_connection_error,
    _create_adapter_from_manifest,
    _get_available_adapters,
    _get_llm_providers,
    _log_oauth_linking_skip,
    _should_skip_manifest,
    _validate_api_key_for_provider,
    _validate_setup_passwords,
)


class TestValidateApiKeyForProvider:
    """Tests for _validate_api_key_for_provider helper."""

    def test_openai_invalid_placeholder_key(self):
        """OpenAI provider with placeholder API key returns error."""
        config = LLMValidationRequest(
            provider="openai",
            api_key="your_openai_api_key_here",
        )
        result = _validate_api_key_for_provider(config)
        assert result is not None
        assert result.valid is False
        assert "Invalid API key" in result.message

    def test_openai_empty_api_key(self):
        """OpenAI provider with empty API key returns error."""
        config = LLMValidationRequest(
            provider="openai",
            api_key="",
        )
        result = _validate_api_key_for_provider(config)
        assert result is not None
        assert result.valid is False

    def test_openai_valid_api_key(self):
        """OpenAI provider with valid API key returns None (valid)."""
        config = LLMValidationRequest(
            provider="openai",
            api_key="sk-test-key-12345",
        )
        result = _validate_api_key_for_provider(config)
        assert result is None  # None means valid

    def test_local_provider_no_api_key_required(self):
        """Local provider doesn't require API key."""
        config = LLMValidationRequest(
            provider="local",
            api_key="",
            base_url="http://localhost:11434",
        )
        result = _validate_api_key_for_provider(config)
        assert result is None  # Valid

    def test_other_provider_missing_api_key(self):
        """Other providers require API key."""
        config = LLMValidationRequest(
            provider="other",
            api_key="",
            base_url="https://api.example.com",
        )
        result = _validate_api_key_for_provider(config)
        assert result is not None
        assert result.valid is False
        assert "API key required" in result.message

    def test_other_provider_with_api_key(self):
        """Other provider with API key is valid."""
        config = LLMValidationRequest(
            provider="other",
            api_key="test-api-key",
            base_url="https://api.example.com",
        )
        result = _validate_api_key_for_provider(config)
        assert result is None  # Valid


class TestClassifyLLMConnectionError:
    """Tests for _classify_llm_connection_error helper."""

    def test_unauthorized_401_error(self):
        """401 error is classified as authentication failed."""
        error = Exception("Error: 401 Unauthorized")
        result = _classify_llm_connection_error(error, "https://api.openai.com")
        assert result.valid is False
        assert "Authentication failed" in result.message
        assert "Invalid API key" in result.error

    def test_unauthorized_text_error(self):
        """Unauthorized text is classified as authentication failed."""
        error = Exception("Unauthorized access")
        result = _classify_llm_connection_error(error, "https://api.openai.com")
        assert result.valid is False
        assert "Authentication failed" in result.message

    def test_not_found_404_error(self):
        """404 error is classified as endpoint not found."""
        error = Exception("Error: 404 Not Found")
        result = _classify_llm_connection_error(error, "https://api.example.com/v1")
        assert result.valid is False
        assert "Endpoint not found" in result.message
        assert "api.example.com/v1" in result.error

    def test_not_found_text_error(self):
        """Not Found text is classified as endpoint not found."""
        error = Exception("Not Found: page does not exist")
        result = _classify_llm_connection_error(error, "https://api.openai.com")
        assert result.valid is False
        assert "Endpoint not found" in result.message

    def test_timeout_error(self):
        """Timeout error is classified appropriately."""
        error = Exception("Connection timeout while waiting for response")
        result = _classify_llm_connection_error(error, "http://localhost:11434")
        assert result.valid is False
        assert "Connection timeout" in result.message
        assert "Could not connect" in result.error

    def test_generic_error(self):
        """Generic error is classified as connection failed."""
        error = Exception("Some other network error")
        result = _classify_llm_connection_error(error, "https://api.openai.com")
        assert result.valid is False
        assert "Connection failed" in result.message
        assert "Some other network error" in result.error


class TestValidateSetupPasswords:
    """Tests for _validate_setup_passwords helper."""

    def test_oauth_user_without_password_generates_random(self):
        """OAuth user without password gets a generated one."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password=None,
            oauth_provider="google",
        )
        result = _validate_setup_passwords(setup, is_oauth_user=True)
        assert len(result) > 8  # Generated password should be long

    def test_oauth_user_with_empty_password_generates_random(self):
        """OAuth user with empty password gets a generated one."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="",
            oauth_provider="google",
        )
        result = _validate_setup_passwords(setup, is_oauth_user=True)
        assert len(result) > 8

    def test_non_oauth_user_without_password_raises_error(self):
        """Non-OAuth user without password raises HTTPException."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password=None,
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_setup_passwords(setup, is_oauth_user=False)
        assert exc_info.value.status_code == 400
        assert "at least 8 characters" in exc_info.value.detail

    def test_password_too_short_raises_error(self):
        """Password shorter than 8 characters raises HTTPException."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="short",
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_setup_passwords(setup, is_oauth_user=False)
        assert exc_info.value.status_code == 400
        assert "at least 8 characters" in exc_info.value.detail

    def test_valid_password_returns_same(self):
        """Valid password is returned unchanged."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="validpassword123",
        )
        result = _validate_setup_passwords(setup, is_oauth_user=False)
        assert result == "validpassword123"

    def test_system_admin_password_too_short_raises_error(self):
        """System admin password too short raises HTTPException."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="validpassword123",
            system_admin_password="short",
        )
        with pytest.raises(HTTPException) as exc_info:
            _validate_setup_passwords(setup, is_oauth_user=False)
        assert exc_info.value.status_code == 400
        assert "System admin password" in exc_info.value.detail


class TestLogOAuthLinkingSkip:
    """Tests for _log_oauth_linking_skip helper."""

    def test_logs_missing_provider(self):
        """Logs reason when oauth_provider is missing."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="password123",
            oauth_provider=None,
            oauth_external_id="12345",
        )
        # Should not raise, just logs
        _log_oauth_linking_skip(setup)

    def test_logs_missing_external_id(self):
        """Logs reason when oauth_external_id is missing."""
        setup = SetupCompleteRequest(
            llm_provider="openai",
            llm_api_key="sk-test",
            admin_username="testuser",
            admin_password="password123",
            oauth_provider="google",
            oauth_external_id=None,
        )
        # Should not raise, just logs
        _log_oauth_linking_skip(setup)


class TestGetLLMProviders:
    """Tests for _get_llm_providers helper."""

    def test_returns_list_of_providers(self):
        """Returns a list of LLM providers."""
        providers = _get_llm_providers()
        assert isinstance(providers, list)
        assert len(providers) >= 3  # At least openai, local, other

    def test_provider_ids(self):
        """Providers have expected IDs."""
        providers = _get_llm_providers()
        provider_ids = {p.id for p in providers}
        assert "openai" in provider_ids
        assert "local" in provider_ids
        assert "other" in provider_ids

    def test_openai_provider_config(self):
        """OpenAI provider has correct configuration."""
        providers = _get_llm_providers()
        openai = next(p for p in providers if p.id == "openai")
        assert openai.requires_api_key is True
        assert openai.requires_base_url is False
        assert openai.default_model == "gpt-5.2"

    def test_local_provider_config(self):
        """Local provider has correct configuration."""
        providers = _get_llm_providers()
        local = next(p for p in providers if p.id == "local")
        assert local.requires_api_key is False
        assert local.requires_base_url is True
        assert local.requires_model is True
        assert "11434" in local.default_base_url


class TestGetAvailableAdapters:
    """Tests for _get_available_adapters helper."""

    def test_returns_list_of_adapters(self):
        """Returns a list of adapters."""
        adapters = _get_available_adapters()
        assert isinstance(adapters, list)
        assert len(adapters) >= 2  # At least api, cli

    def test_adapter_ids(self):
        """Adapters have expected IDs."""
        adapters = _get_available_adapters()
        adapter_ids = {a.id for a in adapters}
        # API adapter is always required
        assert "api" in adapter_ids
        # Should have multiple adapters from discovery
        assert len(adapter_ids) >= 4

    def test_api_adapter_enabled_by_default(self):
        """API adapter is enabled by default."""
        adapters = _get_available_adapters()
        api = next(a for a in adapters if a.id == "api")
        assert api.enabled_by_default is True

    def test_discord_adapter_requires_env_vars(self):
        """Discord adapter requires DISCORD_BOT_TOKEN."""
        adapters = _get_available_adapters()
        discord = next((a for a in adapters if a.id == "discord"), None)
        if discord:
            assert "DISCORD_BOT_TOKEN" in discord.required_env_vars


class TestShouldSkipManifest:
    """Tests for _should_skip_manifest helper."""

    def _create_mock_manifest(
        self,
        name: str = "test_adapter",
        is_mock: bool = False,
        reference: bool = False,
        for_qa: bool = False,
        services: list = None,
        metadata: dict = None,
    ) -> Mock:
        """Create a mock manifest for testing."""
        manifest = Mock()
        manifest.module = Mock()
        manifest.module.name = name
        manifest.module.is_mock = is_mock
        manifest.module.reference = reference
        manifest.module.for_qa = for_qa
        manifest.services = services if services is not None else [Mock()]
        manifest.metadata = metadata
        return manifest

    def test_skip_already_seen(self):
        """Skip manifest if module_id already in seen_ids."""
        manifest = self._create_mock_manifest(name="already_seen")
        seen_ids = {"already_seen"}
        assert _should_skip_manifest(manifest, "already_seen", seen_ids) is True

    def test_skip_covenant_metrics(self):
        """Skip ciris_covenant_metrics (handled separately)."""
        manifest = self._create_mock_manifest(name="ciris_covenant_metrics")
        seen_ids = set()
        assert _should_skip_manifest(manifest, "ciris_covenant_metrics", seen_ids) is True

    def test_skip_mock_modules(self):
        """Skip mock modules."""
        manifest = self._create_mock_manifest(is_mock=True)
        seen_ids = set()
        assert _should_skip_manifest(manifest, "test_adapter", seen_ids) is True

    def test_skip_reference_modules(self):
        """Skip reference modules."""
        manifest = self._create_mock_manifest(reference=True)
        seen_ids = set()
        assert _should_skip_manifest(manifest, "test_adapter", seen_ids) is True

    def test_skip_qa_modules(self):
        """Skip QA modules."""
        manifest = self._create_mock_manifest(for_qa=True)
        seen_ids = set()
        assert _should_skip_manifest(manifest, "test_adapter", seen_ids) is True

    def test_skip_no_services(self):
        """Skip modules with no services."""
        manifest = self._create_mock_manifest(services=[])
        seen_ids = set()
        assert _should_skip_manifest(manifest, "test_adapter", seen_ids) is True

    def test_skip_library_type(self):
        """Skip modules with metadata type = library."""
        manifest = self._create_mock_manifest(metadata={"type": "library"})
        seen_ids = set()
        assert _should_skip_manifest(manifest, "test_adapter", seen_ids) is True

    def test_skip_common_suffix(self):
        """Skip modules ending with _common."""
        manifest = self._create_mock_manifest(name="ciris_common")
        seen_ids = set()
        assert _should_skip_manifest(manifest, "ciris_common", seen_ids) is True

    def test_skip_common_infix(self):
        """Skip modules with _common_ in name."""
        manifest = self._create_mock_manifest(name="ciris_common_utils")
        seen_ids = set()
        assert _should_skip_manifest(manifest, "ciris_common_utils", seen_ids) is True

    def test_do_not_skip_valid_adapter(self):
        """Do not skip valid adapter."""
        manifest = self._create_mock_manifest(name="valid_adapter")
        seen_ids = set()
        assert _should_skip_manifest(manifest, "valid_adapter", seen_ids) is False


class TestCreateAdapterFromManifest:
    """Tests for _create_adapter_from_manifest helper."""

    def _create_mock_manifest(
        self,
        name: str = "test_adapter",
        description: str = "Test adapter description",
        capabilities: list = None,
        metadata: dict = None,
        platform_requirements: list = None,
    ) -> Mock:
        """Create a mock manifest for testing."""
        manifest = Mock()
        manifest.module = Mock()
        manifest.module.name = name
        manifest.module.description = description
        manifest.capabilities = capabilities
        manifest.metadata = metadata
        manifest.platform_requirements = platform_requirements
        return manifest

    def test_creates_adapter_config(self):
        """Creates AdapterConfig from manifest."""
        manifest = self._create_mock_manifest()
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert isinstance(result, AdapterConfig)
        assert result.id == "test_adapter"

    def test_name_formatting(self):
        """Name is formatted with title case and spaces."""
        manifest = self._create_mock_manifest(name="my_test_adapter")
        result = _create_adapter_from_manifest(manifest, "my_test_adapter")
        assert result.name == "My Test Adapter"

    def test_description_from_manifest(self):
        """Uses description from manifest."""
        manifest = self._create_mock_manifest(description="Custom description")
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert result.description == "Custom description"

    def test_description_fallback(self):
        """Uses fallback description when manifest has none."""
        manifest = self._create_mock_manifest(description=None)
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert result.description == "test_adapter adapter"

    def test_requires_binaries_true(self):
        """Detects requires:binaries capability."""
        manifest = self._create_mock_manifest(capabilities=["requires:binaries", "other"])
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert result.requires_binaries is True

    def test_requires_binaries_false(self):
        """No requires:binaries means requires_binaries is False."""
        manifest = self._create_mock_manifest(capabilities=["other"])
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert result.requires_binaries is False

    def test_supported_platforms_from_metadata(self):
        """Extracts supported_platforms from metadata."""
        manifest = self._create_mock_manifest(metadata={"supported_platforms": ["linux", "darwin"]})
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert result.supported_platforms == ["linux", "darwin"]

    def test_supported_platforms_empty_when_missing(self):
        """Empty supported_platforms when not in metadata."""
        manifest = self._create_mock_manifest(metadata={})
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert result.supported_platforms == []

    def test_supported_platforms_empty_when_invalid_type(self):
        """Empty supported_platforms when metadata value is not a list."""
        manifest = self._create_mock_manifest(metadata={"supported_platforms": "linux"})  # String, not list
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert result.supported_platforms == []

    def test_ciris_services_adapter_enabled_by_default(self):
        """ciris_hosted_tools is enabled by default."""
        manifest = self._create_mock_manifest(name="ciris_hosted_tools")
        result = _create_adapter_from_manifest(manifest, "ciris_hosted_tools")
        assert result.enabled_by_default is True
        assert result.requires_ciris_services is True

    def test_regular_adapter_not_enabled_by_default(self):
        """Regular adapters are not enabled by default."""
        manifest = self._create_mock_manifest()
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert result.enabled_by_default is False
        assert result.requires_ciris_services is False

    def test_platform_requirements_from_manifest(self):
        """Uses platform_requirements from manifest."""
        manifest = self._create_mock_manifest(platform_requirements=["gpu", "cuda"])
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert result.platform_requirements == ["gpu", "cuda"]

    def test_platform_requirements_empty_when_none(self):
        """Empty platform_requirements when manifest has None."""
        manifest = self._create_mock_manifest(platform_requirements=None)
        result = _create_adapter_from_manifest(manifest, "test_adapter")
        assert result.platform_requirements == []


# ============================================================================
# Live Model Listing Helper Tests
# ============================================================================


class TestDetectOllama:
    """Tests for _detect_ollama helper."""

    def test_standard_ollama_port(self):
        from ciris_engine.logic.adapters.api.routes.setup import _detect_ollama

        assert _detect_ollama("http://localhost:11434") is True

    def test_ollama_port_with_path(self):
        from ciris_engine.logic.adapters.api.routes.setup import _detect_ollama

        assert _detect_ollama("http://myserver:11434/v1") is True

    def test_non_ollama_port(self):
        from ciris_engine.logic.adapters.api.routes.setup import _detect_ollama

        assert _detect_ollama("http://localhost:8080") is False

    def test_none_url(self):
        from ciris_engine.logic.adapters.api.routes.setup import _detect_ollama

        assert _detect_ollama(None) is False

    def test_empty_string(self):
        from ciris_engine.logic.adapters.api.routes.setup import _detect_ollama

        assert _detect_ollama("") is False


class TestGetProviderBaseUrl:
    """Tests for _get_provider_base_url helper."""

    def test_known_provider_groq(self):
        from ciris_engine.logic.adapters.api.routes.setup import _get_provider_base_url

        assert _get_provider_base_url("groq", None) == "https://api.groq.com/openai/v1"

    def test_known_provider_together(self):
        from ciris_engine.logic.adapters.api.routes.setup import _get_provider_base_url

        assert _get_provider_base_url("together", None) == "https://api.together.xyz/v1"

    def test_known_provider_openrouter(self):
        from ciris_engine.logic.adapters.api.routes.setup import _get_provider_base_url

        assert _get_provider_base_url("openrouter", None) == "https://openrouter.ai/api/v1"

    def test_custom_url_overrides_default(self):
        from ciris_engine.logic.adapters.api.routes.setup import _get_provider_base_url

        assert _get_provider_base_url("groq", "https://custom.url/v1") == "https://custom.url/v1"

    def test_unknown_provider_no_url(self):
        from ciris_engine.logic.adapters.api.routes.setup import _get_provider_base_url

        assert _get_provider_base_url("openai", None) is None

    def test_unknown_provider_with_url(self):
        from ciris_engine.logic.adapters.api.routes.setup import _get_provider_base_url

        assert _get_provider_base_url("other", "https://my-api.com/v1") == "https://my-api.com/v1"


class TestAnnotateModelsWithCapabilities:
    """Tests for _annotate_models_with_capabilities helper."""

    def test_known_model_annotated(self):
        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, _annotate_models_with_capabilities

        models = [LiveModelInfo(id="gpt-4o", display_name="gpt-4o")]
        result = _annotate_models_with_capabilities(models, "openai")
        assert result[0].display_name == "GPT-4o"
        assert result[0].ciris_compatible is True
        assert result[0].source == "both"

    def test_unknown_model_left_as_is(self):
        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, _annotate_models_with_capabilities

        models = [LiveModelInfo(id="ft:custom-model-2025", display_name="ft:custom-model-2025")]
        result = _annotate_models_with_capabilities(models, "openai")
        assert result[0].ciris_compatible is None
        assert result[0].source == "live"

    def test_unknown_provider(self):
        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, _annotate_models_with_capabilities

        models = [LiveModelInfo(id="my-model", display_name="my-model")]
        result = _annotate_models_with_capabilities(models, "nonexistent_provider")
        assert result[0].ciris_compatible is None

    def test_empty_models_list(self):
        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, _annotate_models_with_capabilities

        result = _annotate_models_with_capabilities([], "openai")
        assert result == []


class TestSortModels:
    """Tests for _sort_models helper."""

    def test_sorting_order(self):
        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, _sort_models

        models = [
            LiveModelInfo(id="a", display_name="A", ciris_compatible=False),
            LiveModelInfo(id="b", display_name="B", ciris_compatible=True, ciris_recommended=True),
            LiveModelInfo(id="c", display_name="C", ciris_compatible=None),
            LiveModelInfo(id="d", display_name="D", ciris_compatible=True),
        ]
        sorted_models = _sort_models(models)
        assert sorted_models[0].id == "b"  # recommended
        assert sorted_models[1].id == "d"  # compatible
        assert sorted_models[2].id == "c"  # unknown
        assert sorted_models[3].id == "a"  # incompatible

    def test_alphabetical_within_group(self):
        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, _sort_models

        models = [
            LiveModelInfo(id="z", display_name="Zebra", ciris_compatible=True),
            LiveModelInfo(id="a", display_name="Alpha", ciris_compatible=True),
        ]
        sorted_models = _sort_models(models)
        assert sorted_models[0].id == "a"
        assert sorted_models[1].id == "z"

    def test_empty_list(self):
        from ciris_engine.logic.adapters.api.routes.setup import _sort_models

        assert _sort_models([]) == []


class TestGetStaticFallbackModels:
    """Tests for _get_static_fallback_models helper."""

    def test_known_provider(self):
        from ciris_engine.logic.adapters.api.routes.setup import _get_static_fallback_models

        models = _get_static_fallback_models("openai")
        assert len(models) > 0
        assert all(m.source == "static" for m in models)

    def test_unknown_provider_empty(self):
        from ciris_engine.logic.adapters.api.routes.setup import _get_static_fallback_models

        models = _get_static_fallback_models("nonexistent_provider")
        assert len(models) == 0


class TestBuildFallbackResponse:
    """Tests for _build_fallback_response helper."""

    def test_includes_error_message(self):
        from ciris_engine.logic.adapters.api.routes.setup import _build_fallback_response

        resp = _build_fallback_response("openai", "Connection timed out")
        assert resp.source == "static"
        assert resp.error is not None
        assert "Connection timed out" in resp.error
        assert resp.total_count > 0
        assert resp.provider == "openai"

    def test_unknown_provider_empty_models(self):
        from ciris_engine.logic.adapters.api.routes.setup import _build_fallback_response

        resp = _build_fallback_response("nonexistent", "No such provider")
        assert resp.source == "static"
        assert resp.total_count == 0
        assert resp.error is not None


class TestListModelsForProvider:
    """Tests for _list_models_for_provider orchestrator."""

    @pytest.mark.asyncio
    async def test_invalid_api_key_returns_static(self):
        """Invalid API key triggers static fallback."""
        from ciris_engine.logic.adapters.api.routes.setup import LLMValidationRequest, _list_models_for_provider

        config = LLMValidationRequest(
            provider="openai",
            api_key="your_openai_api_key_here",  # Placeholder key triggers validation error
        )
        result = await _list_models_for_provider(config)
        assert result.source == "static"
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_live_query_exception_falls_back(self):
        """Exception during live query triggers static fallback."""
        from unittest.mock import patch as async_patch

        from ciris_engine.logic.adapters.api.routes.setup import LLMValidationRequest, _list_models_for_provider

        config = LLMValidationRequest(
            provider="openai",
            api_key="sk-valid-key-12345",
        )

        with async_patch(
            "ciris_engine.logic.adapters.api.routes.setup._fetch_live_models",
            side_effect=TimeoutError("Connection timed out"),
        ):
            result = await _list_models_for_provider(config)
            assert result.source == "static"
            assert result.error is not None

    @pytest.mark.asyncio
    async def test_successful_live_query(self):
        """Successful live query returns annotated models."""
        from unittest.mock import patch as async_patch

        from ciris_engine.logic.adapters.api.routes.setup import (
            LiveModelInfo,
            LLMValidationRequest,
            _list_models_for_provider,
        )

        config = LLMValidationRequest(
            provider="openai",
            api_key="sk-valid-key-12345",
        )

        mock_models = [
            LiveModelInfo(id="gpt-4o", display_name="gpt-4o", source="live"),
            LiveModelInfo(id="gpt-3.5-turbo", display_name="gpt-3.5-turbo", source="live"),
        ]

        with async_patch(
            "ciris_engine.logic.adapters.api.routes.setup._fetch_live_models",
            return_value=mock_models,
        ):
            result = await _list_models_for_provider(config)
            assert result.source == "live"
            assert result.error is None
            assert result.total_count == 2

    @pytest.mark.asyncio
    async def test_local_provider_skips_api_key_validation(self):
        """Local provider does not require API key validation."""
        from unittest.mock import patch as async_patch

        from ciris_engine.logic.adapters.api.routes.setup import (
            LiveModelInfo,
            LLMValidationRequest,
            _list_models_for_provider,
        )

        config = LLMValidationRequest(
            provider="local",
            api_key="",
            base_url="http://localhost:11434",
        )

        mock_models = [LiveModelInfo(id="llama3", display_name="llama3", source="live")]

        with async_patch(
            "ciris_engine.logic.adapters.api.routes.setup._fetch_live_models",
            return_value=mock_models,
        ):
            result = await _list_models_for_provider(config)
            assert result.source == "live"


class TestFetchLiveModels:
    """Tests for _fetch_live_models dispatch function."""

    @pytest.mark.asyncio
    async def test_dispatches_to_anthropic(self):
        """Anthropic provider dispatches to _list_models_anthropic."""
        from unittest.mock import patch as async_patch

        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, LLMValidationRequest, _fetch_live_models

        config = LLMValidationRequest(provider="anthropic", api_key="sk-ant-test123")

        with async_patch(
            "ciris_engine.logic.adapters.api.routes.setup._list_models_anthropic",
            return_value=[LiveModelInfo(id="claude-3-opus", display_name="Claude 3 Opus", source="live")],
        ) as mock_anthropic:
            result = await _fetch_live_models(config)
            mock_anthropic.assert_called_once_with("sk-ant-test123")
            assert len(result) == 1
            assert result[0].id == "claude-3-opus"

    @pytest.mark.asyncio
    async def test_dispatches_to_google(self):
        """Google provider dispatches to _list_models_google."""
        from unittest.mock import patch as async_patch

        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, LLMValidationRequest, _fetch_live_models

        config = LLMValidationRequest(provider="google", api_key="AIza-test123")

        with async_patch(
            "ciris_engine.logic.adapters.api.routes.setup._list_models_google",
            return_value=[LiveModelInfo(id="gemini-2.0-flash-exp", display_name="Gemini 2.0 Flash", source="live")],
        ) as mock_google:
            result = await _fetch_live_models(config)
            mock_google.assert_called_once_with("AIza-test123")
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_dispatches_to_ollama(self):
        """Local provider with Ollama URL dispatches to _list_models_ollama."""
        from unittest.mock import patch as async_patch

        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, LLMValidationRequest, _fetch_live_models

        config = LLMValidationRequest(provider="local", api_key="", base_url="http://localhost:11434")

        with async_patch(
            "ciris_engine.logic.adapters.api.routes.setup._list_models_ollama",
            return_value=[LiveModelInfo(id="llama3:latest", display_name="llama3:latest", source="live")],
        ) as mock_ollama:
            result = await _fetch_live_models(config)
            mock_ollama.assert_called_once_with("http://localhost:11434")
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_dispatches_to_openai_compatible(self):
        """OpenAI provider dispatches to _list_models_openai_compatible."""
        from unittest.mock import patch as async_patch

        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, LLMValidationRequest, _fetch_live_models

        config = LLMValidationRequest(provider="openai", api_key="sk-test123")

        with async_patch(
            "ciris_engine.logic.adapters.api.routes.setup._list_models_openai_compatible",
            return_value=[LiveModelInfo(id="gpt-4o", display_name="gpt-4o", source="live")],
        ) as mock_openai:
            result = await _fetch_live_models(config)
            mock_openai.assert_called_once_with("sk-test123", None, "openai")
            assert len(result) == 1

    @pytest.mark.asyncio
    async def test_groq_resolves_base_url(self):
        """Groq provider resolves to correct base URL."""
        from unittest.mock import patch as async_patch

        from ciris_engine.logic.adapters.api.routes.setup import LiveModelInfo, LLMValidationRequest, _fetch_live_models

        config = LLMValidationRequest(provider="groq", api_key="gsk_test123")

        with async_patch(
            "ciris_engine.logic.adapters.api.routes.setup._list_models_openai_compatible",
            return_value=[],
        ) as mock_openai:
            await _fetch_live_models(config)
            mock_openai.assert_called_once_with("gsk_test123", "https://api.groq.com/openai/v1", "groq")
