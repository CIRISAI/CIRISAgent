"""OpenRouter spending-limit refusals and the per-call output budget (CIRISAgent#1366 item 20).

Every 402 used to read as ``insufficient_quota`` and fail with no retry, so one
transient in-flight-budget refusal ruined a RATCHET Market 4 episode. OpenRouter
names the situation in ``error.metadata.limit_source`` (and ``reason``); these
tests pin that each one is classified from that structure, never from the prose,
and that only the in-flight budget is treated as transient.

The service tests drive the real instructor over a fake HTTP transport, so
"sent once" means one HTTP request actually went out.
"""

from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional
from unittest.mock import patch

import httpx
import instructor
import openai
import pytest
from openai import AsyncOpenAI
from pydantic import BaseModel

from ciris_engine.logic.services.runtime.llm_service.provider_limits import (
    IN_FLIGHT_BACKOFF_CAP_S,
    LENGTH_ESCALATION_MAX_TOKENS,
    ProviderLimitError,
    ProviderLimitFaultCode,
    in_flight_backoff_s,
    parse_retry_after,
    provider_limit_fault,
)
from ciris_engine.logic.services.runtime.llm_service.service import (
    OpenAICompatibleClient,
    OpenAIConfig,
    _root_provider_fault,
)

BASE_URL = "https://openrouter.ai/api/v1"

IN_FLIGHT = {"reason": "in_flight_budget_exhausted", "limit_source": "openrouter_in_flight_budget"}
WEIGHT = {"reason": "weight_exceeds_budget", "limit_source": "openrouter_credits"}
CREDITS = {"limit_source": "openrouter_credits"}
KEY_LIMIT = {"limit_source": "openrouter_key_limit", "limit_reset": "monthly"}


def _body(metadata: Optional[dict], message: str = "This request would exceed your available credits.") -> dict:
    err: dict = {"code": 402, "message": message}
    if metadata is not None:
        err["metadata"] = dict(metadata, remedy_hint="hint text we must never branch on")
    return {"error": err}


def _api_error(status: int, metadata: Optional[dict], retry_after: Optional[str] = None) -> openai.APIStatusError:
    """The error the openai SDK raises: body UNWRAPPED to the inner object, headers on .response."""
    headers = {"Retry-After": retry_after} if retry_after is not None else {}
    req = httpx.Request("POST", f"{BASE_URL}/chat/completions")
    body = _body(metadata)
    resp = httpx.Response(status, request=req, headers=headers, json=body)
    return openai.APIStatusError("Error code", response=resp, body=body["error"])


class TestClassification:
    def test_in_flight_budget_with_retry_after(self):
        fault = provider_limit_fault(_api_error(402, IN_FLIGHT, retry_after="7"))
        assert fault is not None
        assert fault.code is ProviderLimitFaultCode.IN_FLIGHT_BUDGET
        assert fault.retryable
        assert fault.retry_after_s == 7.0
        assert _root_provider_fault(_api_error(402, IN_FLIGHT)) == "in_flight_budget"

    def test_in_flight_budget_without_retry_after(self):
        fault = provider_limit_fault(_api_error(402, IN_FLIGHT))
        assert fault is not None and fault.retryable and fault.retry_after_s is None

    def test_weight_exceeds_budget_is_request_too_large_not_retryable(self):
        fault = provider_limit_fault(_api_error(402, WEIGHT, retry_after="3"))
        assert fault is not None
        assert fault.code is ProviderLimitFaultCode.REQUEST_TOO_LARGE
        assert not fault.retryable
        assert _root_provider_fault(_api_error(402, WEIGHT)) == "request_too_large"

    def test_credits_balance_is_insufficient_quota(self):
        fault = provider_limit_fault(_api_error(402, CREDITS))
        assert fault is not None and fault.code is ProviderLimitFaultCode.INSUFFICIENT_QUOTA
        assert not fault.retryable
        assert _root_provider_fault(_api_error(402, CREDITS)) == "insufficient_quota"

    @pytest.mark.parametrize("status", [402, 403])
    def test_key_limit_as_402_or_403(self, status):
        fault = provider_limit_fault(_api_error(status, KEY_LIMIT))
        assert fault is not None and fault.code is ProviderLimitFaultCode.KEY_LIMIT
        assert not fault.retryable
        assert fault.limit_reset == "monthly"
        assert _root_provider_fault(_api_error(status, KEY_LIMIT)) == "key_limit"
        text = fault.describe()
        assert "key limit" in text.lower()
        assert "add credits" not in text.lower()
        assert "monthly" in text

    def test_a_402_without_limit_source_keeps_todays_answer(self):
        e = _api_error(402, None)
        assert provider_limit_fault(e) is None
        assert _root_provider_fault(e) == "insufficient_quota"

    def test_the_hint_text_is_never_read(self):
        # Prose that SAYS "in-flight" but a limit_source that says credits:
        # the structure wins.
        req = httpx.Request("POST", f"{BASE_URL}/chat/completions")
        body = _body(CREDITS, message="retry after in-flight requests settle")
        e = openai.APIStatusError("x", response=httpx.Response(402, request=req, json=body), body=body["error"])
        fault = provider_limit_fault(e)
        assert fault is not None and fault.code is ProviderLimitFaultCode.INSUFFICIENT_QUOTA

    def test_retry_after_http_date_and_garbage(self):
        assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT") == 0.0
        assert parse_retry_after("soon") is None
        assert parse_retry_after(None) is None

    def test_backoff_floors_at_retry_after_and_caps(self):
        for attempt in range(6):
            assert in_flight_backoff_s(attempt, 5.0) >= 5.0
            assert in_flight_backoff_s(attempt, 500.0) == IN_FLIGHT_BACKOFF_CAP_S
            assert 0.0 <= in_flight_backoff_s(attempt, None) <= IN_FLIGHT_BACKOFF_CAP_S


class Verdict(BaseModel):
    answer: str


def _completion(content: str, finish_reason: str = "stop") -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "created": 0,
            "model": "test-model",
            "choices": [
                {"index": 0, "message": {"role": "assistant", "content": content}, "finish_reason": finish_reason}
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 3, "total_tokens": 6},
        },
    )


def _service_over(handler: Callable[[httpx.Request], httpx.Response], monkeypatch) -> OpenAICompatibleClient:
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


def _refusal(metadata: dict, status: int = 402, retry_after: Optional[str] = None) -> httpx.Response:
    headers: Dict[str, str] = {"Retry-After": retry_after} if retry_after else {}
    return httpx.Response(status, headers=headers, json=_body(metadata))


async def _call(service: OpenAICompatibleClient, max_tokens: int = 2048) -> BaseModel:
    result, _ = await service.call_llm_structured(
        messages=[{"role": "user", "content": "hi"}], response_model=Verdict, max_tokens=max_tokens
    )
    return result


class TestServiceRaisesTheCategorizedRefusal:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("retry_after", [None, "4"])
    async def test_in_flight_is_transient_and_never_trips_the_breaker(self, monkeypatch, retry_after):
        sent: List[httpx.Request] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(request)
            return _refusal(IN_FLIGHT, retry_after=retry_after)

        service = _service_over(handler, monkeypatch)
        for _ in range(6):  # more than the breaker's failure threshold (5)
            with pytest.raises(ProviderLimitError) as exc_info:
                await _call(service)
        assert exc_info.value.fault.code is ProviderLimitFaultCode.IN_FLIGHT_BUDGET
        assert exc_info.value.fault.retry_after_s == (float(retry_after) if retry_after else None)
        assert len(sent) == 6, "the service sends once; waiting is the bus's job"
        assert service.circuit_breaker.consecutive_failures == 0
        assert service.circuit_breaker.is_available()
        assert service.last_fault_code == "in_flight_budget"
        # The DMA/conscience retry rule must still give it another attempt.
        from ciris_engine.logic.conscience.transport import is_worth_another_attempt

        assert is_worth_another_attempt(RuntimeError(f"All LLM services failed for X. Last error: {exc_info.value}"))

    @pytest.mark.asyncio
    async def test_weight_exceeds_budget_is_surfaced_without_retry_or_smaller_budget(self, monkeypatch):
        sent: List[dict] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content))
            return _refusal(WEIGHT)

        service = _service_over(handler, monkeypatch)
        with pytest.raises(ProviderLimitError) as exc_info:
            await _call(service, max_tokens=4096)
        assert exc_info.value.fault.code is ProviderLimitFaultCode.REQUEST_TOO_LARGE
        assert len(sent) == 1, "retrying this request unchanged cannot succeed"
        assert sent[0]["max_tokens"] == 4096, "max_tokens is never shrunk"
        assert service.last_fault_code == "request_too_large"
        from ciris_engine.logic.conscience.transport import is_worth_another_attempt

        assert not is_worth_another_attempt(
            RuntimeError(f"All LLM services failed for X. Last error: {exc_info.value}")
        )

    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", [402, 403])
    async def test_key_limit_names_the_key_limit(self, monkeypatch, status):
        service = _service_over(lambda r: _refusal(KEY_LIMIT, status=status), monkeypatch)
        with pytest.raises(ProviderLimitError):
            await _call(service)
        assert service.last_fault_code == "key_limit"
        assert "key limit" in service.last_error.lower()
        assert "add credits" not in service.last_error.lower()

    @pytest.mark.asyncio
    async def test_empty_balance_is_billing(self, monkeypatch):
        service = _service_over(lambda r: _refusal(CREDITS), monkeypatch)
        with pytest.raises(ProviderLimitError):
            await _call(service)
        assert service.last_fault_code == "insufficient_quota"


class TestLengthEscalation:
    @pytest.mark.asyncio
    async def test_a_reply_cut_off_at_max_tokens_is_retried_once_at_the_larger_budget(self, monkeypatch):
        sent: List[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content)["max_tokens"])
            if len(sent) == 1:
                return _completion('{"answer": "trunc', finish_reason="length")
            return _completion('{"answer": "whole"}')

        service = _service_over(handler, monkeypatch)
        result = await _call(service, max_tokens=2048)
        assert result.answer == "whole"
        assert sent == [2048, LENGTH_ESCALATION_MAX_TOKENS]

    @pytest.mark.asyncio
    async def test_no_escalation_past_the_ceiling(self, monkeypatch):
        sent: List[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content)["max_tokens"])
            return _completion('{"answer": "trunc', finish_reason="length")

        service = _service_over(handler, monkeypatch)
        with pytest.raises(RuntimeError):
            await _call(service, max_tokens=LENGTH_ESCALATION_MAX_TOKENS)
        assert sent == [LENGTH_ESCALATION_MAX_TOKENS]

    @pytest.mark.asyncio
    async def test_escalation_happens_once_and_only_upward(self, monkeypatch):
        sent: List[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            sent.append(json.loads(request.content)["max_tokens"])
            return _completion('{"answer": "trunc', finish_reason="length")

        service = _service_over(handler, monkeypatch)
        with pytest.raises(RuntimeError):
            await _call(service, max_tokens=2048)
        assert sent == [2048, LENGTH_ESCALATION_MAX_TOKENS]
