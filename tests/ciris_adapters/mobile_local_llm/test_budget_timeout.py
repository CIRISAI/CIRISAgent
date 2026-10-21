"""On-device inference uses the LOCAL budget profile and no hidden SDK retries (CIRISAgent#1186)."""

from __future__ import annotations

import os
from unittest import mock

import pytest
from pydantic import BaseModel

from ciris_adapters.mobile_local_llm.config import ENV_REQUEST_TIMEOUT, MobileLocalLLMConfig, load_config_from_env
from ciris_adapters.mobile_local_llm.service import MobileLocalLLMService
from ciris_engine.logic.config import llm_budget as lb
from ciris_engine.schemas.config.llm_budget import LOCAL_PROFILE


@pytest.fixture
def os_env_only(monkeypatch):
    monkeypatch.setattr(lb, "get_env_var", lambda name, default=None: os.environ.get(name, default))


def test_default_request_timeout_is_the_local_profile(os_env_only):
    with mock.patch.dict(os.environ, {}, clear=True):
        assert load_config_from_env().request_timeout_seconds == LOCAL_PROFILE.llm_http_timeout_s
    assert MobileLocalLLMConfig().request_timeout_seconds == LOCAL_PROFILE.llm_http_timeout_s


def test_the_global_llm_timeout_override_applies(os_env_only):
    with mock.patch.dict(os.environ, {"CIRIS_LLM_TIMEOUT": "120"}, clear=True):
        assert load_config_from_env().request_timeout_seconds == 120.0


def test_the_adapter_override_wins(os_env_only):
    with mock.patch.dict(os.environ, {"CIRIS_LLM_TIMEOUT": "120", ENV_REQUEST_TIMEOUT: "33"}, clear=True):
        assert load_config_from_env().request_timeout_seconds == 33.0


class _Answer(BaseModel):
    text: str


@pytest.mark.asyncio
async def test_the_sdk_client_is_built_without_retries():
    svc = MobileLocalLLMService(MobileLocalLLMConfig(), server_manager=mock.MagicMock())
    with mock.patch("openai.AsyncOpenAI") as client_cls, mock.patch("instructor.patch") as patch_fn:
        patch_fn.return_value.chat.completions.create = mock.AsyncMock(return_value=_Answer(text="ok"))
        await svc._dispatch_structured(
            messages=[{"role": "user", "content": "hi"}], response_model=_Answer, max_tokens=8, temperature=0.0
        )
    kwargs = client_cls.call_args.kwargs
    assert kwargs["max_retries"] == 0
    assert kwargs["timeout"] == LOCAL_PROFILE.llm_http_timeout_s
