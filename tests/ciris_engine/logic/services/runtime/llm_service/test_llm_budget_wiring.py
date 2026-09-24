"""LLM service side of the time budgets (CIRISAgent#1186).

One retry layer per failure kind: instructor reasks ONLY on schema failures;
transport failures (timeout, connection, 5xx, 429) surface on their first
occurrence so the enclosing DMA / conscience per-try is the one layer that
retries them. These tests drive the real instructor over a fake HTTP
transport, so "called once" means one HTTP request actually went out.
"""

from __future__ import annotations

import json
import os
from typing import Callable, List
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import instructor
import pytest
from openai import APITimeoutError, AsyncOpenAI, InternalServerError
from pydantic import BaseModel

from ciris_engine.logic.config import llm_budget as lb
from ciris_engine.logic.services.runtime.llm_service.service import (
    OpenAICompatibleClient,
    OpenAIConfig,
    runtime_provider_config,
)
from ciris_engine.schemas.config.llm_budget import LOCAL_PROFILE, REMOTE_PROFILE

BASE_URL = "https://llm.example.com/v1"


class Verdict(BaseModel):
    answer: str


def _completion(content: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 3, "total_tokens": 6},
        },
    )


@pytest.fixture
def os_env_only(monkeypatch):
    """Budget resolution reads only os.environ here, never the host's .env."""
    monkeypatch.setattr(lb, "get_env_var", lambda name, default=None: os.environ.get(name, default))
    for name in ("CIRIS_LLM_TIMEOUT", "CIRIS_LLM_BUDGET_PROFILE", "CIRIS_LLM_PROVIDER", "LLM_PROVIDER"):
        monkeypatch.delenv(name, raising=False)


def _service_over(handler: Callable[[httpx.Request], httpx.Response], monkeypatch) -> OpenAICompatibleClient:
    """A real OpenAICompatibleClient whose HTTP goes to `handler`."""
    monkeypatch.delenv("MOCK_LLM", raising=False)
    with patch("sys.argv", ["pytest"]):
        service = OpenAICompatibleClient(
            config=OpenAIConfig(api_key="test-key-12345", model_name="test-model", base_url=BASE_URL, max_retries=2)
        )
    client = AsyncOpenAI(
        api_key="test-key-12345",
        base_url=BASE_URL,
        max_retries=0,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    service.client = client
    service.instruct_client = instructor.from_openai(client, mode=instructor.Mode.JSON)
    return service


async def _call(service: OpenAICompatibleClient) -> BaseModel:
    result, _usage = await service.call_llm_structured(
        messages=[{"role": "user", "content": "hi"}], response_model=Verdict, max_tokens=64, temperature=0.0
    )
    return result


class TestOneRetryLayerPerFailure:
    @pytest.mark.asyncio
    async def test_a_timeout_is_sent_once_and_reported_as_a_timeout(self, monkeypatch):
        requests: List[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            raise httpx.ReadTimeout("timed out", request=request)

        service = _service_over(handler, monkeypatch)
        with pytest.raises(TimeoutError) as exc_info:
            await _call(service)

        assert len(requests) == 1, "a timed-out request must not be re-sent inside the service"
        # The conscience fail-closed path keys on this category.
        assert OpenAICompatibleClient._categorize_llm_error(exc_info.value) == "TIMEOUT"
        assert isinstance(exc_info.value.__cause__, APITimeoutError)

    @pytest.mark.asyncio
    async def test_a_5xx_is_sent_once(self, monkeypatch):
        requests: List[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return httpx.Response(503, json={"error": {"message": "overloaded"}})

        service = _service_over(handler, monkeypatch)
        with pytest.raises(RuntimeError) as exc_info:
            await _call(service)

        assert len(requests) == 1
        # The cause chain keeps the status for the LLM bus's 5xx backoff.
        assert isinstance(exc_info.value.__cause__, InternalServerError)

    @pytest.mark.asyncio
    async def test_an_answer_that_does_not_fit_the_schema_is_reasked_once(self, monkeypatch):
        replies = iter(["this is not json", json.dumps({"answer": "ok"})])
        requests: List[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return _completion(next(replies))

        service = _service_over(handler, monkeypatch)
        result = await _call(service)

        assert isinstance(result, Verdict) and result.answer == "ok"
        assert len(requests) == 2, "one schema failure earns exactly one reask"

    @pytest.mark.asyncio
    async def test_the_reask_budget_is_two_attempts(self, monkeypatch):
        requests: List[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return _completion("still not json")

        service = _service_over(handler, monkeypatch)
        with pytest.raises(RuntimeError):
            await _call(service)
        assert len(requests) == 2

    @pytest.mark.asyncio
    async def test_retry_with_backoff_does_not_retry_transport_errors(self, monkeypatch):
        service = _service_over(lambda r: _completion("{}"), monkeypatch)
        calls = 0

        async def func(*_args: object) -> tuple:
            nonlocal calls
            calls += 1
            raise APITimeoutError(request=httpx.Request("POST", BASE_URL))

        with patch("asyncio.sleep") as sleep:
            with pytest.raises(APITimeoutError):
                await service._retry_with_backoff(func, [], Verdict, 64, 0.0)
        assert calls == 1
        sleep.assert_not_called()


class TestNativeSdkTimeouts:
    """Native Anthropic / Google clients raise their own timeout types; they surface as TimeoutError too."""

    @pytest.mark.asyncio
    async def test_a_bare_httpx_timeout_is_a_timeout(self, monkeypatch):
        service = _service_over(lambda r: _completion("{}"), monkeypatch)
        create = AsyncMock(side_effect=httpx.ReadTimeout(""))  # genai lets these through, message empty
        service.instruct_client = MagicMock()
        service.instruct_client.chat.completions.create_with_completion = create
        with pytest.raises(TimeoutError) as exc_info:
            await _call(service)
        assert create.await_count == 1
        assert OpenAICompatibleClient._categorize_llm_error(exc_info.value) == "TIMEOUT"

    @pytest.mark.asyncio
    async def test_an_anthropic_timeout_is_a_timeout(self, monkeypatch):
        anthropic = pytest.importorskip("anthropic")
        service = _service_over(lambda r: _completion("{}"), monkeypatch)
        create = AsyncMock(side_effect=anthropic.APITimeoutError(request=httpx.Request("POST", BASE_URL)))
        service.instruct_client = MagicMock()
        service.instruct_client.chat.completions.create_with_completion = create
        with pytest.raises(TimeoutError):
            await _call(service)
        assert create.await_count == 1


class TestSdkRetriesOff:
    def test_anthropic_native_client_has_no_sdk_retries(self):
        pytest.importorskip("anthropic")
        service = object.__new__(OpenAICompatibleClient)
        service._init_anthropic_client("sk-ant-test", "claude-sonnet-4-20250514", 45)
        assert service.client.max_retries == 0
        assert service.client.timeout == 45

    def test_google_native_client_is_given_the_timeout(self):
        pytest.importorskip("google.genai")
        service = object.__new__(OpenAICompatibleClient)
        with patch("ciris_engine.logic.services.runtime.llm_service.service.instructor.from_provider") as from_provider:
            service._init_google_client("g-key", "gemini-2.0-flash", 45)
        http_options = from_provider.call_args.kwargs["http_options"]
        assert http_options.timeout == 45_000  # milliseconds
        assert http_options.retry_options is None  # genai retries nothing without these


class TestLocalMeansOneThing:
    @pytest.mark.parametrize(
        "url",
        ["http://jetson.local:8080/v1", "http://100.101.102.103:11434/v1", "http://172.20.0.5:8000/v1", "http://gpu-box:11434"],
    )
    def test_local_endpoints_get_reasoning_off(self, url):
        assert OpenAICompatibleClient._is_local_url(url)
        assert OpenAICompatibleClient._build_reasoning_off_extras(url, "gemma-4") == {
            "chat_template_kwargs": {"enable_thinking": False}
        }

    def test_a_cloud_host_on_a_local_server_port_is_not_local(self):
        assert not OpenAICompatibleClient._is_local_url("https://vllm.example.com:8000/v1")


class TestRuntimeProviderConfig:
    @pytest.mark.parametrize("provider_id", ["local", "local_inference", "ollama"])
    def test_a_declared_local_provider_is_keyless_and_gets_the_local_timeout(self, os_env_only, provider_id):
        cfg = runtime_provider_config(provider_id, "https://tunnel.example.com/v1", "gemma", None)
        assert cfg.api_key == "local"
        assert cfg.timeout_seconds == int(LOCAL_PROFILE.llm_http_timeout_s)

    def test_a_cloud_provider_keeps_its_key_and_gets_the_remote_timeout(self, os_env_only):
        cfg = runtime_provider_config("groq", "https://api.groq.com/openai/v1", "llama", "gsk-123")
        assert cfg.api_key == "gsk-123"
        assert cfg.timeout_seconds == int(REMOTE_PROFILE.llm_http_timeout_s)

    def test_an_explicit_override_wins(self, os_env_only, monkeypatch):
        monkeypatch.setenv("CIRIS_LLM_TIMEOUT", "77")
        assert runtime_provider_config("local", "http://jetson.local:8080/v1", "m", "").timeout_seconds == 77
