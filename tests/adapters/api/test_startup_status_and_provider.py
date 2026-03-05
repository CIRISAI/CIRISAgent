"""
Tests for startup-status endpoint, LLM provider detection, and MockLLM logging.

Covers new code from v2.0.11:
- GET /system/startup-status endpoint (health.py)
- StartupStatusResponse schema (schemas.py)
- _detect_llm_provider() and extracted helpers (config.py)
- _detect_api_key_set() for provider-aware key detection (config.py)
- MockLLM _log_service_started calls in adapter_loader.py and module_loader.py
"""

import os
from unittest.mock import Mock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.setup.config import (
    _detect_api_key_set,
    _detect_from_api_keys,
    _detect_from_base_url,
    _detect_from_explicit_env,
    _detect_llm_provider,
    _is_mock_llm,
)
from ciris_engine.logic.adapters.api.routes.system.schemas import StartupStatusResponse


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(mock_llm: bool = False) -> Mock:
    """Create a mock FastAPI Request with optional mock_llm runtime."""
    request = Mock()
    request.app = Mock()
    request.app.state = Mock()
    if mock_llm:
        runtime = Mock()
        runtime.modules_to_load = ["mock_llm"]
        request.app.state.runtime = runtime
    else:
        request.app.state.runtime = None
    return request


# ---------------------------------------------------------------------------
# _is_mock_llm tests
# ---------------------------------------------------------------------------

class TestIsMockLlm:
    def test_from_runtime(self):
        assert _is_mock_llm(_make_request(mock_llm=True)) is True

    def test_no_runtime(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _is_mock_llm(_make_request()) is False

    @pytest.mark.parametrize("val", ["true", "1", "yes", "on", "TRUE", "Yes"])
    def test_from_env_truthy(self, val):
        with patch.dict(os.environ, {"CIRIS_MOCK_LLM": val}, clear=True):
            assert _is_mock_llm(_make_request()) is True

    def test_from_env_false(self):
        with patch.dict(os.environ, {"CIRIS_MOCK_LLM": "false"}, clear=True):
            assert _is_mock_llm(_make_request()) is False


# ---------------------------------------------------------------------------
# _detect_from_explicit_env tests
# ---------------------------------------------------------------------------

class TestDetectFromExplicitEnv:
    def test_returns_none_when_unset(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _detect_from_explicit_env() is None

    @pytest.mark.parametrize("raw,expected", [
        ("anthropic", "anthropic"),
        ("claude", "anthropic"),
        ("google", "google"),
        ("gemini", "google"),
        ("openai", "openai"),
        ("openrouter", "openrouter"),
        ("groq", "groq"),
        ("together", "together"),
        ("openai_compatible", "other"),
    ])
    def test_alias_mapping(self, raw, expected):
        with patch.dict(os.environ, {"CIRIS_LLM_PROVIDER": raw}, clear=True):
            assert _detect_from_explicit_env() == expected

    def test_unknown_passthrough(self):
        with patch.dict(os.environ, {"CIRIS_LLM_PROVIDER": "custom_provider"}, clear=True):
            assert _detect_from_explicit_env() == "custom_provider"

    def test_llm_provider_fallback(self):
        with patch.dict(os.environ, {"LLM_PROVIDER": "anthropic"}, clear=True):
            assert _detect_from_explicit_env() == "anthropic"

    def test_ciris_takes_precedence(self):
        with patch.dict(os.environ, {"CIRIS_LLM_PROVIDER": "google", "LLM_PROVIDER": "openai"}, clear=True):
            assert _detect_from_explicit_env() == "google"


# ---------------------------------------------------------------------------
# _detect_from_api_keys tests
# ---------------------------------------------------------------------------

class TestDetectFromApiKeys:
    def test_no_keys(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _detect_from_api_keys() is None

    def test_anthropic_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant-123"}, clear=True):
            assert _detect_from_api_keys() == "anthropic"

    def test_google_key(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIza"}, clear=True):
            assert _detect_from_api_keys() == "google"

    def test_gemini_key(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIza"}, clear=True):
            assert _detect_from_api_keys() == "google"

    def test_anthropic_takes_precedence_over_google(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "x", "GOOGLE_API_KEY": "y"}, clear=True):
            assert _detect_from_api_keys() == "anthropic"


# ---------------------------------------------------------------------------
# _detect_from_base_url tests
# ---------------------------------------------------------------------------

class TestDetectFromBaseUrl:
    def test_no_url(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _detect_from_base_url() is None

    @pytest.mark.parametrize("url,expected", [
        ("https://openrouter.ai/v1", "openrouter"),
        ("https://api.groq.com/v1", "groq"),
        ("https://api.together.xyz/v1", "together"),
        ("https://api.together.ai/v1", "together"),
        ("https://api.mistral.ai/v1", "mistral"),
        ("https://api.deepseek.com/v1", "deepseek"),
        ("https://api.cohere.com/v1", "cohere"),
        ("http://localhost:11434", "local"),
        ("http://127.0.0.1:11434", "local"),
    ])
    def test_known_patterns(self, url, expected):
        with patch.dict(os.environ, {"OPENAI_API_BASE": url}, clear=True):
            assert _detect_from_base_url() == expected

    def test_unknown_url(self):
        with patch.dict(os.environ, {"OPENAI_API_BASE": "https://custom.example.com"}, clear=True):
            assert _detect_from_base_url() == "other"


# ---------------------------------------------------------------------------
# _detect_llm_provider (integration of all detectors)
# ---------------------------------------------------------------------------

class TestDetectLlmProvider:
    def _call(self, request=None, env=None):
        env = env or {}
        request = request or _make_request()
        with patch.dict(os.environ, env, clear=True):
            return _detect_llm_provider(request)

    def test_mock_overrides_all(self):
        assert self._call(
            request=_make_request(mock_llm=True),
            env={"CIRIS_LLM_PROVIDER": "anthropic", "ANTHROPIC_API_KEY": "x"},
        ) == "mockllm"

    def test_explicit_overrides_key(self):
        assert self._call(env={
            "CIRIS_LLM_PROVIDER": "google",
            "ANTHROPIC_API_KEY": "sk-ant-123",
        }) == "google"

    def test_key_overrides_url(self):
        assert self._call(env={
            "ANTHROPIC_API_KEY": "sk-ant-123",
            "OPENAI_API_BASE": "https://openrouter.ai/v1",
        }) == "anthropic"

    def test_url_overrides_proxy(self):
        assert self._call(env={
            "OPENAI_API_BASE": "https://api.groq.com/v1",
            "CIRIS_PROXY_URL": "https://proxy.ciris.ai",
        }) == "groq"

    def test_ciris_proxy_url(self):
        assert self._call(env={"CIRIS_PROXY_URL": "https://proxy.ciris.ai"}) == "ciris_proxy"

    def test_ciris_proxy_enabled(self):
        assert self._call(env={"CIRIS_PROXY_ENABLED": "true"}) == "ciris_proxy"

    def test_ciris_proxy_enabled_1(self):
        assert self._call(env={"CIRIS_PROXY_ENABLED": "1"}) == "ciris_proxy"

    def test_default_openai(self):
        assert self._call(env={}) == "openai"


# ---------------------------------------------------------------------------
# _detect_api_key_set tests
# ---------------------------------------------------------------------------

class TestDetectApiKeySet:
    def test_openai_key(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-123"}, clear=True):
            assert _detect_api_key_set("openai") is True

    def test_openai_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _detect_api_key_set("openai") is False

    def test_anthropic_key(self):
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "sk-ant"}, clear=True):
            assert _detect_api_key_set("anthropic") is True

    def test_anthropic_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _detect_api_key_set("anthropic") is False

    def test_google_key(self):
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "AIza"}, clear=True):
            assert _detect_api_key_set("google") is True

    def test_gemini_key_counts_for_google(self):
        with patch.dict(os.environ, {"GEMINI_API_KEY": "AIza"}, clear=True):
            assert _detect_api_key_set("google") is True

    def test_mockllm_always_false(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-123"}, clear=True):
            assert _detect_api_key_set("mockllm") is False

    def test_ciris_proxy_always_false(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-123"}, clear=True):
            assert _detect_api_key_set("ciris_proxy") is False

    def test_local_always_false(self):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-123"}, clear=True):
            assert _detect_api_key_set("local") is False

    def test_unknown_falls_back_to_openai_key(self):
        """Unknown providers fall back to OPENAI_API_KEY (OpenAI-compatible)."""
        with patch.dict(os.environ, {"OPENAI_API_KEY": "sk-123"}, clear=True):
            assert _detect_api_key_set("openrouter") is True

    def test_unknown_no_fallback_key(self):
        with patch.dict(os.environ, {}, clear=True):
            assert _detect_api_key_set("openrouter") is False


# ---------------------------------------------------------------------------
# StartupStatusResponse schema tests
# ---------------------------------------------------------------------------

class TestStartupStatusResponse:
    def test_basic_construction(self):
        r = StartupStatusResponse(
            phase="STARTUP",
            services_online=5,
            services_total=22,
            service_names=["TimeService", "ShutdownService"],
        )
        assert r.phase == "STARTUP"
        assert r.services_online == 5
        assert r.services_total == 22
        assert len(r.service_names) == 2

    def test_empty_service_names_default(self):
        r = StartupStatusResponse(phase="STARTUP", services_online=0, services_total=22)
        assert r.service_names == []


# ---------------------------------------------------------------------------
# GET /startup-status endpoint tests
# ---------------------------------------------------------------------------

class TestStartupStatusEndpoint:
    @pytest.mark.asyncio
    async def test_returns_startup_status(self):
        from ciris_engine.logic.adapters.api.routes.system.health import get_startup_status

        with patch(
            "ciris_engine.logic.runtime.service_initializer._services_started",
            new={1, 2, 3},
        ), patch(
            "ciris_engine.logic.runtime.service_initializer._current_phase",
            new="RESUME (test)",
        ):
            result = await get_startup_status()
            data = result.data
            assert data.services_online == 3
            assert data.services_total == 22
            assert data.phase == "RESUME (test)"
            assert "TimeService" in data.service_names
            assert "InitializationService" in data.service_names

    @pytest.mark.asyncio
    async def test_empty_services(self):
        from ciris_engine.logic.adapters.api.routes.system.health import get_startup_status

        with patch(
            "ciris_engine.logic.runtime.service_initializer._services_started",
            new=set(),
        ), patch(
            "ciris_engine.logic.runtime.service_initializer._current_phase",
            new="STARTUP",
        ):
            result = await get_startup_status()
            assert result.data.services_online == 0
            assert result.data.service_names == []

    @pytest.mark.asyncio
    async def test_all_services(self):
        from ciris_engine.logic.adapters.api.routes.system.health import get_startup_status

        with patch(
            "ciris_engine.logic.runtime.service_initializer._services_started",
            new=set(range(1, 23)),
        ), patch(
            "ciris_engine.logic.runtime.service_initializer._current_phase",
            new="RESUME (0 remaining services)",
        ):
            result = await get_startup_status()
            assert result.data.services_online == 22
            assert len(result.data.service_names) == 22

    @pytest.mark.asyncio
    async def test_out_of_range_service_numbers_ignored(self):
        from ciris_engine.logic.adapters.api.routes.system.health import get_startup_status

        with patch(
            "ciris_engine.logic.runtime.service_initializer._services_started",
            new={0, 1, 23, 99},  # 0 and 23/99 are out of range
        ), patch(
            "ciris_engine.logic.runtime.service_initializer._current_phase",
            new="STARTUP",
        ):
            result = await get_startup_status()
            assert result.data.services_online == 4  # count of set items
            assert result.data.service_names == ["TimeService"]  # only #1 maps


# ---------------------------------------------------------------------------
# MockLLM _log_service_started integration in loaders
# ---------------------------------------------------------------------------

class TestMockLlmLogging:
    def test_adapter_loader_calls_log_service_started(self):
        """AdapterLoader._log_mock_llm_startup calls _log_service_started for mock LLM."""
        from ciris_engine.logic.runtime.adapter_loader import AdapterLoader
        from ciris_engine.schemas.runtime.enums import ServiceType

        loader = AdapterLoader()

        manifest = Mock()
        manifest.module.is_mock = True
        service_decl = Mock()
        service_decl.type = ServiceType.LLM
        manifest.services = [service_decl]

        with patch(
            "ciris_engine.logic.runtime.service_initializer._log_service_started"
        ) as mock_log:
            loader._log_mock_llm_startup(manifest)
            mock_log.assert_called_once_with(14, "MockLLMService")

    def test_adapter_loader_skips_non_mock(self):
        """_log_mock_llm_startup skips non-mock manifests."""
        from ciris_engine.logic.runtime.adapter_loader import AdapterLoader

        loader = AdapterLoader()
        manifest = Mock()
        manifest.module.is_mock = False

        with patch(
            "ciris_engine.logic.runtime.service_initializer._log_service_started"
        ) as mock_log:
            loader._log_mock_llm_startup(manifest)
            mock_log.assert_not_called()

    def test_adapter_loader_skips_non_llm_mock(self):
        """_log_mock_llm_startup skips mock services that aren't LLM type."""
        from ciris_engine.logic.runtime.adapter_loader import AdapterLoader
        from ciris_engine.schemas.runtime.enums import ServiceType

        loader = AdapterLoader()
        manifest = Mock()
        manifest.module.is_mock = True
        service_decl = Mock()
        service_decl.type = ServiceType.COMMUNICATION
        manifest.services = [service_decl]

        with patch(
            "ciris_engine.logic.runtime.service_initializer._log_service_started"
        ) as mock_log:
            loader._log_mock_llm_startup(manifest)
            mock_log.assert_not_called()
