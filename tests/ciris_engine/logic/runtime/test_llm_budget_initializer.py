"""ServiceInitializer takes every LLM timeout from the budget profile (CIRISAgent#1186).

Before: a substring scan picked 300s for "local" (via a config key that did not
exist), `services.llm_timeout` otherwise — 60s on desktop, which loads
essential.yaml, and the schema default 30s on phones, which do not. Persisted
providers got 120/60 from a third heuristic.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.config import llm_budget as lb
from ciris_engine.logic.persistence.llm_providers import LLMProviderConfig
from ciris_engine.logic.runtime.service_initializer import ServiceInitializer, _is_loopback_or_lan
from ciris_engine.schemas.config.essential import EssentialConfig, ServiceEndpointsConfig
from ciris_engine.schemas.config.llm_budget import LOCAL_PROFILE, REMOTE_PROFILE

REMOTE_S = int(REMOTE_PROFILE.llm_http_timeout_s)
LOCAL_S = int(LOCAL_PROFILE.llm_http_timeout_s)


@pytest.fixture(autouse=True)
def os_env_only(monkeypatch):
    """Budget resolution reads only os.environ here, never the host's .env."""
    monkeypatch.setattr(lb, "get_env_var", lambda name, default=None: os.environ.get(name, default))
    for name in (
        "CIRIS_LLM_TIMEOUT",
        "CIRIS_LLM_BUDGET_PROFILE",
        "CIRIS_LLM_PROVIDER",
        "LLM_PROVIDER",
        "OPENAI_API_BASE",
        "CIRIS_OPENAI_API_BASE",
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GEMINI_API_KEY",
        "CIRIS_OPENAI_API_KEY_2",
        "CIRIS_BILLING_GOOGLE_ID_TOKEN",
        "CIRIS_BILLING_APPLE_ID_TOKEN",
        "CIRIS_LLM_REPLICAS",
        "CIRIS_SERVICES_DISABLED",
        "MOCK_LLM",
    ):
        monkeypatch.delenv(name, raising=False)


class TestResolveLLMTimeout:
    @pytest.mark.parametrize(
        "base_url,provider_id,expected",
        [
            ("https://api.openai.com/v1", None, REMOTE_S),
            ("https://openrouter.ai/api/v1", "openrouter", REMOTE_S),
            (None, None, REMOTE_S),  # SDK default URL is a hosted API
            ("http://jetson.local:8080/v1", None, LOCAL_S),
            ("http://localhost:11434/v1", None, LOCAL_S),
            ("http://172.20.0.5:8000/v1", None, LOCAL_S),  # the old scan only knew 172.16.
            ("https://tunnel.example.com/v1", "local", LOCAL_S),  # a declaration beats the URL
            ("https://api.v10.example.com/v1", None, REMOTE_S),  # "10." inside a hostname
        ],
    )
    def test_profile_decides(self, base_url, provider_id, expected):
        assert ServiceInitializer._resolve_llm_timeout(base_url, provider_id) == expected

    def test_explicit_override_wins(self, monkeypatch):
        monkeypatch.setenv("CIRIS_LLM_TIMEOUT", "77")
        assert ServiceInitializer._resolve_llm_timeout("http://jetson.local:8080/v1") == 77
        assert ServiceInitializer._resolve_llm_timeout("https://api.openai.com/v1") == 77


class TestLoopbackOrLan:
    def test_delegates_to_the_one_classifier(self):
        assert _is_loopback_or_lan("http://100.101.102.103:11434/v1")  # Tailscale
        assert _is_loopback_or_lan("https://tunnel.example.com/v1", "local_inference")
        assert not _is_loopback_or_lan("https://api.groq.com/openai/v1")
        assert not _is_loopback_or_lan("")


def _initializer(config: object) -> ServiceInitializer:
    initializer = ServiceInitializer(essential_config=config)  # type: ignore[arg-type]
    initializer.service_registry = Mock()
    initializer.time_service = Mock()
    initializer.telemetry_service = Mock()
    initializer._skip_llm_init = False
    return initializer


async def _primary_timeout(config: object) -> int:
    initializer = _initializer(config)
    with patch("ciris_engine.logic.runtime.service_initializer.OpenAICompatibleClient") as client_cls:
        client_cls.return_value = AsyncMock()
        await initializer._initialize_llm_services(config)
    return int(client_cls.call_args_list[0].kwargs["config"].timeout_seconds)


class TestMobileEqualsDesktop:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "base_url,expected",
        [("https://llm01.ciris.ai/v1", REMOTE_S), ("http://jetson.local:8080/v1", LOCAL_S)],
    )
    async def test_timeout_does_not_depend_on_essential_yaml(self, monkeypatch, base_url, expected):
        """Desktop loads essential.yaml (llm_timeout: 60); phones build EssentialConfig in code (30)."""
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-key-that-is-long-enough-1234567890")
        monkeypatch.setenv("OPENAI_API_BASE", base_url)

        mobile = EssentialConfig()
        desktop = EssentialConfig(services=ServiceEndpointsConfig(llm_timeout=60))
        assert mobile.services.llm_timeout != desktop.services.llm_timeout

        assert await _primary_timeout(mobile) == expected
        assert await _primary_timeout(desktop) == expected


class TestPersistedProviders:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "provider_id,base_url,expected_timeout,expected_key",
        [
            ("local_inference", "http://jetson.local:8080/v1", LOCAL_S, "local"),
            ("local", "https://tunnel.example.com/v1", LOCAL_S, "local"),
            ("groq", "https://api.groq.com/openai/v1", REMOTE_S, "gsk-real"),
        ],
    )
    async def test_restored_provider_uses_the_profile(self, provider_id, base_url, expected_timeout, expected_key):
        initializer = _initializer(EssentialConfig())
        initializer.config_service = Mock()
        initializer.service_registry.get_provider_by_name = Mock(return_value=None)
        stored = LLMProviderConfig(
            provider_id=provider_id,
            base_url=base_url,
            model="m",
            api_key="" if expected_key == "local" else expected_key,
            priority="high",
        )
        with patch(
            "ciris_engine.logic.persistence.llm_providers.list_providers", AsyncMock(return_value={"p": stored})
        ), patch("ciris_engine.logic.runtime.service_initializer.OpenAICompatibleClient") as client_cls:
            client_cls.return_value = AsyncMock()
            await initializer._load_persisted_runtime_llm_providers()

        cfg = client_cls.call_args.kwargs["config"]
        assert cfg.timeout_seconds == expected_timeout
        assert cfg.api_key == expected_key
