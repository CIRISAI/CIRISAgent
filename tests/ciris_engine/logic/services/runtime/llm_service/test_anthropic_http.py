"""Claude over HTTPS when the anthropic SDK is absent (iOS, CIRISAgent#1298).

Every anthropic release requires jiter (native Rust, no iOS wheel), so the iOS
bundle has no SDK. The agent used to fall back to an OpenAI client pointed at
openrouter.ai carrying the user's ANTHROPIC key. These tests pin the direct path:
the request it sends, how it reads replies, how errors map onto the exception
types the LLM service already handles, and that the key only ever goes to
api.anthropic.com.
"""

from __future__ import annotations

import builtins
import json
from typing import Any, Dict, List

import httpx
import openai
import pytest
from pydantic import BaseModel

from ciris_engine.logic.services.runtime.llm_service import anthropic_http as ah


class Verdict(BaseModel):
    action: str
    confidence: float


def _reply(text: str, *, stop: str = "end_turn", thinking: bool = True, usage=(12, 7)) -> Dict[str, Any]:
    content: List[Dict[str, Any]] = [{"type": "thinking", "thinking": ""}] if thinking else []
    content.append({"type": "text", "text": text})
    return {
        "id": "msg_1",
        "model": "claude-opus-5-5",
        "stop_reason": stop,
        "content": content,
        "usage": {"input_tokens": usage[0], "output_tokens": usage[1]},
    }


def _client(responses: List[httpx.Response], seen: List[httpx.Request]) -> ah.AnthropicHTTPClient:
    queue = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return queue.pop(0)

    return ah.AnthropicHTTPClient("sk-ant-test", transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_structured_call_sends_a_native_request_and_parses_the_reply():
    seen: List[httpx.Request] = []
    client = _client([httpx.Response(200, json=_reply('```json\n{"action": "speak", "confidence": 0.9}\n```'))], seen)
    instructor = ah.AnthropicHTTPInstructor(client)

    result, completion = await instructor.chat.completions.create_with_completion(
        model="claude-opus-5-5",
        messages=[
            {"role": "system", "content": "You are CIRIS."},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "What now?"},
                    {"type": "image_url", "image_url": {"url": "data:image/png;base64,iVBORw0KGgo="}},
                ],
            },
        ],
        response_model=Verdict,
        max_tokens=2048,
        temperature=0.0,
        extra_body={"provider": {"order": ["x"]}},
    )

    assert result == Verdict(action="speak", confidence=0.9)
    assert (completion.usage.prompt_tokens, completion.usage.completion_tokens) == (12, 7)
    (request,) = seen
    assert str(request.url) == "https://api.anthropic.com/v1/messages"
    assert request.headers["x-api-key"] == "sk-ant-test"
    assert request.headers["anthropic-version"] == ah.ANTHROPIC_API_VERSION
    body = json.loads(request.content)
    assert set(body) == {"model", "max_tokens", "system", "messages"}, "no temperature / extra_body / seed"
    assert body["system"].startswith("You are CIRIS.") and '"action"' in body["system"]
    assert body["messages"][0]["content"][1] == {
        "type": "image",
        "source": {"type": "base64", "media_type": "image/png", "data": "iVBORw0KGgo="},
    }


@pytest.mark.asyncio
async def test_a_schema_mismatch_is_reasked_with_the_error():
    seen: List[httpx.Request] = []
    client = _client(
        [
            httpx.Response(200, json=_reply('{"action": "speak"}')),
            httpx.Response(200, json=_reply('{"action": "speak", "confidence": 0.5}')),
        ],
        seen,
    )
    result, completion = await ah.AnthropicHTTPInstructor(client).chat.completions.create_with_completion(
        model="m", messages=[{"role": "user", "content": "hi"}], response_model=Verdict
    )
    assert result.confidence == 0.5
    assert completion.usage.prompt_tokens == 24, "usage sums across the re-ask"
    reask = json.loads(seen[1].content)["messages"]
    assert reask[-2]["role"] == "assistant" and "did not validate" in reask[-1]["content"]


@pytest.mark.asyncio
async def test_exhausted_reasks_raise():
    seen: List[httpx.Request] = []
    client = _client([httpx.Response(200, json=_reply("not json")) for _ in range(3)], seen)
    with pytest.raises(ah.AnthropicStructuredOutputError):
        await ah.AnthropicHTTPInstructor(client).chat.completions.create_with_completion(
            model="m", messages=[{"role": "user", "content": "hi"}], response_model=Verdict, max_retries=2
        )
    assert len(seen) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,exc",
    [
        (400, openai.BadRequestError),
        (401, openai.AuthenticationError),
        (403, openai.PermissionDeniedError),
        (404, openai.NotFoundError),
        (429, openai.RateLimitError),
        (529, openai.InternalServerError),
    ],
)
async def test_http_errors_map_onto_the_exceptions_the_service_handles(status, exc):
    client = _client([httpx.Response(status, json={"error": {"message": "nope"}})], [])
    with pytest.raises(exc):
        await client.create_message({"model": "m", "max_tokens": 1, "messages": []})


@pytest.mark.asyncio
async def test_a_refusal_is_raised_not_parsed():
    client = _client([httpx.Response(200, json={**_reply(""), "stop_reason": "refusal", "stop_details": {"category": "cyber"}})], [])
    with pytest.raises(ah.AnthropicRefusalError, match="cyber"):
        await ah.AnthropicHTTPInstructor(client).chat.completions.create_with_completion(
            model="m", messages=[{"role": "user", "content": "hi"}], response_model=Verdict
        )


@pytest.mark.asyncio
async def test_model_listing_follows_pagination():
    seen: List[httpx.Request] = []
    client = _client(
        [
            httpx.Response(200, json={"data": [{"id": "claude-opus-5-5"}], "has_more": True, "last_id": "claude-opus-5-5"}),
            httpx.Response(200, json={"data": [{"id": "claude-sonnet-5-5"}], "has_more": False, "last_id": None}),
        ],
        seen,
    )
    assert await client.list_model_ids() == ["claude-opus-5-5", "claude-sonnet-5-5"]
    assert seen[1].url.params["after_id"] == "claude-opus-5-5"


@pytest.fixture
def no_anthropic_sdk(monkeypatch):
    """Make `import anthropic` fail, as it does on iOS."""
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "anthropic" or name.startswith("anthropic."):
            raise ImportError("No module named 'anthropic' (simulated iOS bundle)")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)


def test_without_the_sdk_the_service_talks_to_anthropic_never_openrouter(no_anthropic_sdk):
    from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

    service = object.__new__(OpenAICompatibleClient)
    service._init_anthropic_client("sk-ant-secret", "claude-opus-5-5", 45)
    assert isinstance(service.instruct_client, ah.AnthropicHTTPInstructor)
    assert isinstance(service.client, ah.AnthropicHTTPClient)
    assert "anthropic.com" in str(service.client.base_url)
    assert "openrouter" not in str(service.client.base_url)
    assert service.client.timeout == 45


@pytest.mark.asyncio
async def test_without_the_sdk_model_listing_uses_https(no_anthropic_sdk, monkeypatch):
    from ciris_engine.logic.services.runtime.llm_service import model_listing

    async def fake_list(self):
        return ["claude-opus-5-5"]

    monkeypatch.setattr(ah.AnthropicHTTPClient, "list_model_ids", fake_list)
    assert await model_listing.list_model_ids(model_listing.SDK_ANTHROPIC, "sk-ant-test") == ["claude-opus-5-5"]


@pytest.mark.asyncio
async def test_without_the_sdk_setup_validation_checks_the_model_over_https(no_anthropic_sdk, monkeypatch):
    from ciris_engine.logic.adapters.api.routes.setup import llm_validation

    asked: List[str] = []

    async def fake_retrieve(self, model):
        asked.append(model)
        return {"id": model}

    monkeypatch.setattr(ah.AnthropicHTTPClient, "retrieve_model", fake_retrieve)
    config = llm_validation.LLMValidationRequest(provider="anthropic", api_key="sk-ant-test", model="claude-opus-5-5")
    result = await llm_validation._validate_anthropic_connection(config)
    assert result.valid is True and asked == ["claude-opus-5-5"]


# ---- reasoning off: CIRIS reasons in its DMA pipeline; model-side thinking is pure cost here


@pytest.mark.parametrize(
    "model,expected",
    [
        # cannot be disabled: lowest effort
        ("claude-opus-5-5", {"output_config": {"effort": "low"}}),
        ("claude-fable-5-1", {"output_config": {"effort": "low"}}),
        ("claude-fable-5", {"output_config": {"effort": "low"}}),
        ("claude-mythos-5-1", {"output_config": {"effort": "low"}}),
        # disabled is a 400; between_tools is the off mode
        ("claude-sonnet-5-5", {"thinking": {"type": "between_tools"}}),
        # disabled accepted (at their default effort)
        ("claude-opus-5", {"thinking": {"type": "disabled"}}),
        ("claude-sonnet-5", {"thinking": {"type": "disabled"}}),
        ("claude-haiku-5-5", {"thinking": {"type": "disabled"}}),
        ("claude-opus-4-8", {"thinking": {"type": "disabled"}}),
        ("claude-opus-4-7", {"thinking": {"type": "disabled"}}),
        # do not think unless asked, or unknown: send nothing
        ("claude-opus-4-6", {}),
        ("claude-sonnet-4-6", {}),
        ("claude-haiku-4-5", {}),
        ("claude-sonnet-4-20250514", {}),
        ("claude-some-future-model", {}),
        ("", {}),
    ],
)
def test_reasoning_off_per_model(model, expected):
    assert ah.claude_reasoning_off(model) == expected


def test_reasoning_off_matches_the_most_specific_prefix():
    # claude-opus-5-5 must not fall through to claude-opus-5's "disabled" (a 400 on 5.5).
    assert ah.claude_reasoning_off("claude-opus-5-5") != ah.claude_reasoning_off("claude-opus-5")
    assert ah.claude_reasoning_off("claude-sonnet-5-5") != ah.claude_reasoning_off("claude-sonnet-5")


@pytest.mark.asyncio
async def test_the_shim_forwards_only_the_reasoning_controls_from_extra_body():
    seen: List[httpx.Request] = []
    client = _client([httpx.Response(200, json=_reply('{"action": "speak", "confidence": 1}'))], seen)
    await ah.AnthropicHTTPInstructor(client).chat.completions.create_with_completion(
        model="claude-sonnet-5-5",
        messages=[{"role": "user", "content": "hi"}],
        response_model=Verdict,
        extra_body={**ah.claude_reasoning_off("claude-sonnet-5-5"), "provider": {"order": ["x"]}, "metadata": {"a": 1}},
    )
    body = json.loads(seen[0].content)
    assert body["thinking"] == {"type": "between_tools"}
    assert "provider" not in body and "metadata" not in body


def test_the_service_asks_for_reasoning_off_on_the_anthropic_provider_without_a_base_url():
    from types import SimpleNamespace

    from ciris_engine.logic.services.runtime.llm_service.service import LLMProvider, OpenAICompatibleClient

    service = object.__new__(OpenAICompatibleClient)
    service.provider = LLMProvider.ANTHROPIC
    service.model_name = "claude-opus-5-5"
    service.openai_config = SimpleNamespace(base_url=None, require_zero_data_retention=True)
    extra = service._build_extra_kwargs(None, None, "Verdict", None)
    assert extra["extra_body"]["output_config"] == {"effort": "low"}


def test_the_host_keyed_policy_agrees_for_api_anthropic_com():
    from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

    assert OpenAICompatibleClient._build_reasoning_off_extras(
        "https://api.anthropic.com/v1", "claude-sonnet-5-5"
    ) == {"thinking": {"type": "between_tools"}}
