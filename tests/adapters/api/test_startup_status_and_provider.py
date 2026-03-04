"""
Tests for startup-status endpoint, _detect_llm_provider(), and MockLLM logging.

Covers new code from v2.0.11:
- GET /system/startup-status endpoint (health.py)
- StartupStatusResponse schema (schemas.py)
- _detect_llm_provider() function (config.py)
- MockLLM _log_service_started calls in adapter_loader.py and module_loader.py
"""

import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.setup.config import _detect_llm_provider
from ciris_engine.logic.adapters.api.routes.system.schemas import StartupStatusResponse


# ---------------------------------------------------------------------------
# _detect_llm_provider tests
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


class TestDetectLlmProvider:
    """Test _detect_llm_provider() covers all detection branches."""

    def _call(self, request=None, env=None):
        env = env or {}
        request = request or _make_request()
        with patch.dict(os.environ, env, clear=True):
            return _detect_llm_provider(request)

    # -- Mock LLM detection --

    def test_mock_llm_from_runtime(self):
        request = _make_request(mock_llm=True)
        assert self._call(request) == "mockllm"

    def test_mock_llm_from_env_true(self):
        assert self._call(env={"CIRIS_MOCK_LLM": "true"}) == "mockllm"

    def test_mock_llm_from_env_1(self):
        assert self._call(env={"CIRIS_MOCK_LLM": "1"}) == "mockllm"

    def test_mock_llm_from_env_yes(self):
        assert self._call(env={"CIRIS_MOCK_LLM": "yes"}) == "mockllm"

    def test_mock_llm_from_env_on(self):
        assert self._call(env={"CIRIS_MOCK_LLM": "on"}) == "mockllm"

    # -- Explicit provider env vars --

    def test_explicit_anthropic(self):
        assert self._call(env={"CIRIS_LLM_PROVIDER": "anthropic"}) == "anthropic"

    def test_explicit_claude(self):
        assert self._call(env={"CIRIS_LLM_PROVIDER": "claude"}) == "anthropic"

    def test_explicit_google(self):
        assert self._call(env={"CIRIS_LLM_PROVIDER": "google"}) == "google"

    def test_explicit_gemini(self):
        assert self._call(env={"CIRIS_LLM_PROVIDER": "gemini"}) == "google"

    def test_explicit_openai(self):
        assert self._call(env={"CIRIS_LLM_PROVIDER": "openai"}) == "openai"

    def test_explicit_openrouter(self):
        assert self._call(env={"CIRIS_LLM_PROVIDER": "openrouter"}) == "openrouter"

    def test_explicit_groq(self):
        assert self._call(env={"CIRIS_LLM_PROVIDER": "groq"}) == "groq"

    def test_explicit_together(self):
        assert self._call(env={"CIRIS_LLM_PROVIDER": "together"}) == "together"

    def test_explicit_openai_compatible(self):
        assert self._call(env={"CIRIS_LLM_PROVIDER": "openai_compatible"}) == "other"

    def test_explicit_unknown_passthrough(self):
        assert self._call(env={"CIRIS_LLM_PROVIDER": "custom_provider"}) == "custom_provider"

    def test_llm_provider_fallback_env(self):
        """LLM_PROVIDER used when CIRIS_LLM_PROVIDER absent."""
        assert self._call(env={"LLM_PROVIDER": "anthropic"}) == "anthropic"

    # -- Auto-detect from API keys --

    def test_anthropic_api_key(self):
        assert self._call(env={"ANTHROPIC_API_KEY": "sk-ant-123"}) == "anthropic"

    def test_google_api_key(self):
        assert self._call(env={"GOOGLE_API_KEY": "AIza123"}) == "google"

    def test_gemini_api_key(self):
        assert self._call(env={"GEMINI_API_KEY": "AIza456"}) == "google"

    # -- Base URL detection --

    def test_base_url_openrouter(self):
        assert self._call(env={"OPENAI_API_BASE": "https://openrouter.ai/v1"}) == "openrouter"

    def test_base_url_groq(self):
        assert self._call(env={"OPENAI_API_BASE": "https://api.groq.com/v1"}) == "groq"

    def test_base_url_together_xyz(self):
        assert self._call(env={"OPENAI_API_BASE": "https://api.together.xyz/v1"}) == "together"

    def test_base_url_together_ai(self):
        assert self._call(env={"OPENAI_API_BASE": "https://api.together.ai/v1"}) == "together"

    def test_base_url_mistral(self):
        assert self._call(env={"OPENAI_API_BASE": "https://api.mistral.ai/v1"}) == "mistral"

    def test_base_url_deepseek(self):
        assert self._call(env={"OPENAI_API_BASE": "https://api.deepseek.com/v1"}) == "deepseek"

    def test_base_url_cohere(self):
        assert self._call(env={"OPENAI_API_BASE": "https://api.cohere.com/v1"}) == "cohere"

    def test_base_url_localhost(self):
        assert self._call(env={"OPENAI_API_BASE": "http://localhost:11434"}) == "local"

    def test_base_url_127(self):
        assert self._call(env={"OPENAI_API_BASE": "http://127.0.0.1:11434"}) == "local"

    def test_base_url_unknown(self):
        assert self._call(env={"OPENAI_API_BASE": "https://custom.example.com"}) == "other"

    # -- CIRIS Proxy --

    def test_ciris_proxy_url(self):
        assert self._call(env={"CIRIS_PROXY_URL": "https://proxy.ciris.ai"}) == "ciris_proxy"

    def test_ciris_proxy_enabled(self):
        assert self._call(env={"CIRIS_PROXY_ENABLED": "true"}) == "ciris_proxy"

    def test_ciris_proxy_enabled_1(self):
        assert self._call(env={"CIRIS_PROXY_ENABLED": "1"}) == "ciris_proxy"

    # -- Default --

    def test_default_openai(self):
        assert self._call(env={}) == "openai"

    # -- Priority: mock > explicit > key > url > proxy > default --

    def test_mock_overrides_explicit(self):
        assert self._call(
            request=_make_request(mock_llm=True),
            env={"CIRIS_LLM_PROVIDER": "anthropic"},
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

        with patch("ciris_engine.logic.adapters.api.routes.system.health.get_startup_status.__module__"):
            pass  # just ensure importable

        # Patch the module-level globals that get_startup_status imports
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
