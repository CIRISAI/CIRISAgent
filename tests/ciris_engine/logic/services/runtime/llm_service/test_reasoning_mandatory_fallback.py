"""A model whose reasoning cannot be turned off gets the least reasoning it accepts.

CIRISClient run 43445421167: anthropic/claude-sonnet-5.5 through OpenRouter
answered every DMA call with `400 Reasoning is mandatory for this endpoint and
cannot be disabled`, and the agent raised without retrying, so the person got
"I encountered an issue processing your request" for every message. Eric,
2026-11-13: suppress reasoning "as much as possible". Measured on that model:
`enabled=false` and `effort=none` are refused; `effort=minimal` with `exclude`
is accepted at 0 reasoning tokens.
"""

from __future__ import annotations

from typing import Any, List
from unittest.mock import MagicMock

import pytest
from openai import APIConnectionError, AuthenticationError, BadRequestError, RateLimitError
from pydantic import BaseModel

from ciris_engine.logic.services.runtime.llm_service import service as svc
from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

OR = "https://openrouter.ai/api/v1"
MODEL = "anthropic/claude-sonnet-5.5"
MANDATORY = "Error code: 400 - {'error': {'message': 'Reasoning is mandatory for this endpoint and cannot be disabled.'}}"


@pytest.fixture(autouse=True)
def _fresh_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_REASONING_MANDATORY_MODELS", set())


def _bad_request(message: str) -> BadRequestError:
    response = MagicMock()
    response.status_code = 400
    response.headers = {}
    response.request = MagicMock()
    return BadRequestError(message=message, response=response, body={"error": {"message": message}})


def _client() -> OpenAICompatibleClient:
    c = OpenAICompatibleClient.__new__(OpenAICompatibleClient)
    c.max_retries = 3
    c.base_delay = 0.001
    c.max_delay = 0.01
    c.retryable_exceptions = (APIConnectionError, RateLimitError, BadRequestError)
    c.non_retryable_exceptions = (AuthenticationError,)
    c.model_name = MODEL
    return c


class _R(BaseModel):
    ok: bool = True


def test_reasoning_stays_off_for_a_model_not_known_to_refuse() -> None:
    assert svc.build_request_extra_body(OR, MODEL)["reasoning"] == {"enabled": False}


def test_after_a_refusal_the_model_gets_minimal_reasoning_not_off() -> None:
    assert svc.note_reasoning_mandatory(MODEL) is True
    assert svc.build_request_extra_body(OR, MODEL)["reasoning"] == {"effort": "minimal", "exclude": True}
    assert svc.build_request_extra_body(OR, "qwen/qwen3.6-35b-a3b")["reasoning"] == {"enabled": False}


def test_the_refusal_is_recognised_and_learned_once() -> None:
    assert svc.is_reasoning_mandatory_error(_bad_request(MANDATORY))
    assert not svc.is_reasoning_mandatory_error(_bad_request("invalid model"))
    assert svc.note_reasoning_mandatory(MODEL) is True
    assert svc.note_reasoning_mandatory(MODEL.upper()) is False


@pytest.mark.asyncio
async def test_the_pipeline_retries_with_the_fallback_and_succeeds() -> None:
    client = _client()
    sent: List[Any] = []

    async def call(messages, response_model, max_tokens, temperature):
        body = svc.build_request_extra_body(OR, MODEL)
        sent.append(body["reasoning"])
        if body["reasoning"] == {"enabled": False}:
            raise _bad_request(MANDATORY)
        return _R()

    result = await client._retry_with_backoff(call, [{"role": "user", "content": "x"}], _R, 100, 0.0)
    assert isinstance(result, _R)
    assert sent == [{"enabled": False}, {"effort": "minimal", "exclude": True}]


@pytest.mark.asyncio
async def test_a_second_refusal_after_the_fallback_is_not_retried_forever() -> None:
    client = _client()
    calls = 0

    async def call(messages, response_model, max_tokens, temperature):
        nonlocal calls
        calls += 1
        raise _bad_request(MANDATORY)

    with pytest.raises(BadRequestError):
        await client._retry_with_backoff(call, [{"role": "user", "content": "x"}], _R, 100, 0.0)
    assert calls == 2


@pytest.mark.asyncio
async def test_test_connection_makes_the_same_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wizard said "Connection successful" for this model while the agent could not answer."""
    import openai

    from ciris_engine.logic.adapters.api.routes.setup import llm_validation

    sent: List[Any] = []

    class _Completions:
        async def create(self, **kw: Any) -> Any:
            sent.append(kw["extra_body"]["reasoning"])
            if kw["extra_body"]["reasoning"] == {"enabled": False}:
                raise _bad_request(MANDATORY)
            return MagicMock()

    class _Fake:
        def __init__(self, **kw: Any) -> None:
            self.chat = MagicMock()
            self.chat.completions = _Completions()

    monkeypatch.setattr(openai, "AsyncOpenAI", _Fake)
    req = llm_validation.LLMValidationRequest(provider="openrouter", api_key="k", base_url=OR, model=MODEL)
    out = await llm_validation._validate_openai_compatible(req)
    assert out.valid is True
    assert sent == [{"enabled": False}, {"effort": "minimal", "exclude": True}]
