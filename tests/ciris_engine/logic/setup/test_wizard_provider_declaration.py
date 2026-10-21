"""The setup wizard persists the declared provider id (CIRISAgent#1186).

Without it the runtime guesses local-vs-remote from the URL, and a local model
behind a tunnel or a hostname gets a cloud time budget. Writing it must never
change which SDK client is built.
"""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest
from dotenv import dotenv_values

from ciris_engine.logic.config import llm_budget as lb
from ciris_engine.logic.services.runtime.llm_service.service import LLMProvider, _detect_provider_from_env
from ciris_engine.logic.setup.wizard import create_env_file
from ciris_engine.schemas.config.llm_budget import ProviderClass

_LLM_ENV = ("CIRIS_LLM_PROVIDER", "LLM_PROVIDER", "OPENAI_API_BASE", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY")


def _write(tmp_path, mocker, provider: str, base_url: str) -> dict:
    env_file = tmp_path / ".env"
    mocker.patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=env_file)
    create_env_file(llm_provider=provider, llm_api_key="key-123", llm_base_url=base_url, llm_model="m")
    return {k: v for k, v in dotenv_values(env_file).items() if v is not None}


def _selected_sdk(env: dict) -> LLMProvider:
    scrubbed = {k: v for k, v in os.environ.items() if k not in _LLM_ENV and not k.startswith("CIRIS_")}
    with patch.dict(os.environ, {**scrubbed, **env}, clear=True):
        return _detect_provider_from_env()


@pytest.mark.parametrize(
    "provider,base_url",
    [
        ("local", "http://192.168.1.50:11434/v1"),
        ("local_inference", "https://tunnel.example.com/v1"),
        ("mobile_local", "http://127.0.0.1:8091/v1"),
        ("groq", "https://api.groq.com/openai/v1"),
        ("together", "https://api.together.xyz/v1"),
        ("openrouter", "https://openrouter.ai/api/v1"),
        ("other", "https://llm.example.com/v1"),
    ],
)
def test_the_provider_id_is_written_and_the_sdk_choice_is_unchanged(tmp_path, mocker, provider, base_url):
    env = _write(tmp_path, mocker, provider, base_url)
    assert env["LLM_PROVIDER"] == provider

    without_declaration = {k: v for k, v in env.items() if k != "LLM_PROVIDER"}
    assert _selected_sdk(env) == _selected_sdk(without_declaration) == LLMProvider.OPENAI_COMPATIBLE


@pytest.mark.parametrize("provider,expected", [("google", "google"), ("anthropic", "anthropic")])
def test_native_sdk_providers_keep_their_single_declaration(tmp_path, mocker, provider, expected):
    env_file = tmp_path / ".env"
    mocker.patch("ciris_engine.logic.setup.first_run.get_default_config_path", return_value=env_file)
    create_env_file(llm_provider=provider, llm_api_key="key-123", llm_base_url="", llm_model="m")
    text = env_file.read_text()
    assert text.count("LLM_PROVIDER=") == 1
    assert dotenv_values(env_file)["LLM_PROVIDER"] == expected


def test_openai_is_not_declared(tmp_path, mocker):
    """LLM_PROVIDER=openai would flip an openai + custom-base setup from OPENAI_COMPATIBLE to OPENAI."""
    env = _write(tmp_path, mocker, "openai", "https://openrouter.ai/api/v1")
    assert "LLM_PROVIDER" not in env
    assert _selected_sdk(env) == LLMProvider.OPENAI_COMPATIBLE


def test_a_tunnelled_local_model_gets_the_local_budget(tmp_path, mocker, monkeypatch):
    env = _write(tmp_path, mocker, "local_inference", "https://tunnel.example.com/v1")
    monkeypatch.setattr(lb, "get_env_var", lambda name, default=None: env.get(name, default))
    assert lb.active_budget().provider_class is ProviderClass.LOCAL
