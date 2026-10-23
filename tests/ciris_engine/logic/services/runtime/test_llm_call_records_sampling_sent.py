"""An LLM_CALL records the sampling actually sent, and who served it.

RATCHET's repeatability rested on env pins plus a log line
("[OPENROUTER] SUCCESS - Provider: X"). The trace now carries them: the client
path that writes the wire request reports what it sent, so a parameter that
path drops is None, never the value the caller asked for.

Lives in this directory for the `llm_service` fixture (conftest.py).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from ciris_adapters.ciris_accord_metrics.egress_schema import TraceLevel, enforce_egress_schema
from ciris_engine.logic.buses.llm_bus import LLMCallEventContext, _broadcast_llm_call_event
from ciris_engine.schemas.runtime.resources import LLMCallSampling, ResourceUsage


class _Reply(BaseModel):
    answer: str = "ok"


def _completion(provider: object = None, model: object = None) -> MagicMock:
    completion = MagicMock()
    completion.usage = MagicMock(prompt_tokens=3, completion_tokens=2)
    completion.provider = provider
    completion.model = model
    return completion


async def _call(llm_service, completion: MagicMock, temperature: float = 0.0) -> ResourceUsage:
    with patch.object(
        llm_service.instruct_client.chat.completions,
        "create_with_completion",
        AsyncMock(return_value=(_Reply(), completion)),
    ):
        _, usage = await llm_service.call_llm_structured(
            messages=[{"role": "user", "content": "x"}],
            response_model=_Reply,
            max_tokens=96,
            temperature=temperature,
        )
    return usage


@pytest.mark.asyncio
async def test_openai_path_records_temperature_seed_cap_and_router_provider(llm_service, monkeypatch) -> None:
    monkeypatch.setenv("CIRIS_LLM_SEED", "20261022")
    usage = await _call(llm_service, _completion("DeepInfra", "meta-llama/llama-4-scout"), temperature=0.3)
    assert usage.sampling == LLMCallSampling(
        temperature=0.3,
        seed=20261022,
        max_tokens=96,
        served_by="DeepInfra",
        served_model="meta-llama/llama-4-scout",
    )


@pytest.mark.asyncio
async def test_an_unset_seed_is_recorded_as_not_sent(llm_service, monkeypatch) -> None:
    monkeypatch.delenv("CIRIS_LLM_SEED", raising=False)
    usage = await _call(llm_service, _completion())
    assert usage.sampling is not None
    assert usage.sampling.seed is None
    assert usage.sampling.temperature == 0.0
    # A MagicMock attribute is not a provider name: never recorded as one.
    assert usage.sampling.served_by is None


@pytest.mark.asyncio
async def test_claude_over_https_records_no_temperature_or_seed(llm_service, monkeypatch) -> None:
    """That path sends neither, so the trace must not claim it did."""
    from ciris_engine.logic.services.runtime.llm_service.anthropic_http import (
        AnthropicHTTPClient,
        AnthropicHTTPInstructor,
    )

    monkeypatch.setenv("CIRIS_LLM_SEED", "7")
    llm_service.instruct_client = AnthropicHTTPInstructor(AnthropicHTTPClient(api_key="test-key"))
    usage = await _call(llm_service, _completion(model="claude-sonnet-5-5"), temperature=0.7)
    assert usage.sampling == LLMCallSampling(
        temperature=None, seed=None, max_tokens=96, served_model="claude-sonnet-5-5"
    )


class _Stream:
    _subscribers = ["dummy"]
    _recent_events: list = []

    def __init__(self) -> None:
        self.events: list = []

    async def broadcast_reasoning_event(self, ev) -> None:
        self.events.append(ev)


def _ctx(usage) -> LLMCallEventContext:
    service = type("S", (), {"model_name": "meta-llama/llama-4-scout"})()
    return LLMCallEventContext(
        success=usage is not None,
        handler_name="EthicalPDMA",
        service_name="OpenAICompatibleLLM",
        selected_service=service,
        api_base="https://openrouter.ai/api/v1",
        response_model=_Reply,
        messages=[{"role": "user", "content": "hi"}],
        result=_Reply() if usage is not None else None,
        usage=usage,
        duration_ms=10.0,
        thought_id="th_1",
        task_id="task_1",
        retry_count=0,
        error=None if usage is not None else TimeoutError("timed out"),
    )


@pytest.mark.asyncio
async def test_the_llm_call_event_carries_what_was_sent(monkeypatch) -> None:
    from ciris_engine.logic.infrastructure import step_streaming

    stream = _Stream()
    monkeypatch.setattr(step_streaming, "reasoning_event_stream", stream)
    sampling = LLMCallSampling(
        temperature=0.0, seed=42, max_tokens=512, served_by="Google AI Studio", served_model="google/gemma-4-31b-it"
    )
    await _broadcast_llm_call_event(_ctx(ResourceUsage(tokens_input=1, tokens_output=1, sampling=sampling)))
    await _broadcast_llm_call_event(_ctx(None))

    ok, failed = stream.events
    assert (ok.sent_temperature, ok.sent_seed, ok.sent_max_tokens) == (0.0, 42, 512)
    assert (ok.served_by, ok.served_model) == ("Google AI Studio", "google/gemma-4-31b-it")
    # A failed call got no reply: nothing is claimed about what served it.
    assert (failed.sent_temperature, failed.served_by) == (None, None)


def test_the_sampling_fields_ship_at_generic() -> None:
    data = {
        "handler_name": "CSDMA",
        "sent_temperature": 0.0,
        "sent_seed": 42,
        "sent_max_tokens": 512,
        "served_by": "Google AI Studio",
        "served_model": "google/gemma-4-31b-it",
        "status": "ok",
    }
    result = enforce_egress_schema("LLM_CALL", TraceLevel.GENERIC, data)
    assert result.violations == []
    assert result.data == data
