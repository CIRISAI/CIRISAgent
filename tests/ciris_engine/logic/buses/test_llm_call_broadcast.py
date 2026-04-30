"""Tests for the v2.7.8 per-LLM-call broadcast machinery in llm_bus.

Covers the three broadcast helpers added to LLMBus + the broadcast
wiring inside _execute_llm_call (success path) and _try_service
(failure path). These are the lines that produce ReasoningEvent.LLM_CALL
events shipped to the lens — see FSD/TRACE_EVENT_LOG_PERSISTENCE.md §5.2.
"""

import asyncio
import json

import pytest
from pydantic import BaseModel

from ciris_engine.logic.buses.llm_bus import (
    _broadcast_llm_call_event,
    _classify_error,
    _safe_messages_to_text,
)
from ciris_engine.schemas.runtime.resources import ResourceUsage


class _Result(BaseModel):
    """Stand-in response model for broadcast-helper tests."""

    selected_action: str = "speak"
    reasoning: str = "test"


class TestClassifyError:
    """_classify_error maps exception class to LLMCallEvent.status enum.

    The status enum is the lens's primary failure-mode column. New
    exception classes the agent encounters need to land in one of the
    documented buckets, otherwise they pollute 'other_error'."""

    def test_timeout_classes(self):
        class ReadTimeout(Exception):
            pass

        class CustomTimeoutError(Exception):
            pass

        assert _classify_error(ReadTimeout()) == "timeout"
        assert _classify_error(asyncio.TimeoutError()) == "timeout"
        assert _classify_error(CustomTimeoutError()) == "timeout"

    def test_rate_limited_class_name(self):
        class RateLimitError(Exception):
            pass

        assert _classify_error(RateLimitError()) == "rate_limited"

    def test_rate_limited_via_message(self):
        """Some libraries raise generic exceptions with HTTP 429 in the message;
        match on '429' in the first 32 chars of the message."""
        assert _classify_error(Exception("429 Too Many Requests")) == "rate_limited"

    def test_model_not_available(self):
        class ModelNotFoundError(Exception):
            pass

        assert _classify_error(ModelNotFoundError()) == "model_not_available"
        # Substring match on message
        assert _classify_error(Exception("model_not_available: gemma-99")) == "model_not_available"

    def test_instructor_retry(self):
        class InstructorRetryException(Exception):
            pass

        assert _classify_error(InstructorRetryException()) == "instructor_retry"

    def test_unknown_exception_falls_to_other_error(self):
        """Unknown classes go to 'other_error' — but error_class on the event
        preserves the actual class name for forensics."""
        assert _classify_error(ValueError("anything")) == "other_error"
        assert _classify_error(RuntimeError("else")) == "other_error"


class TestSafeMessagesToText:
    """Serializer must round-trip JSON-able dicts and degrade gracefully on
    non-JSON-able objects rather than raising — broadcast must never break
    the LLM call path."""

    def test_json_round_trip(self):
        msgs = [{"role": "user", "content": "hello"}, {"role": "system", "content": "be nice"}]
        out = _safe_messages_to_text(msgs)
        # Must round-trip
        assert json.loads(out) == msgs

    def test_unicode_preserved(self):
        msgs = [{"role": "user", "content": "你好 нет हाँ"}]
        out = _safe_messages_to_text(msgs)
        # ensure_ascii=False keeps the actual characters in the wire-format
        assert "你好" in out
        assert "нет" in out

    def test_non_json_able_falls_back_to_repr(self):
        """Object isn't JSON-serializable; serializer must not raise."""

        class _Opaque:
            def __repr__(self):
                return "<Opaque>"

        msgs = [{"role": "user", "content": _Opaque()}]
        out = _safe_messages_to_text(msgs)
        # Either repr-encoded or some safe stringification — just must not raise
        assert isinstance(out, str)
        assert len(out) > 0


@pytest.mark.asyncio
class TestBroadcastLlmCallEventSuccess:
    """Success-path broadcast — fields populated from the result and usage."""

    async def test_emits_event_with_size_and_duration(self, monkeypatch):
        captured = []

        async def fake_broadcast(event):
            captured.append(event)

        # Patch the global stream with a fake whose subscribers list is non-empty
        # so the broadcast guard inside the helper doesn't no-op.
        from ciris_engine.logic.infrastructure import step_streaming

        class _FakeStream:
            _subscribers = ["dummy"]
            _recent_events = []  # conftest teardown clears this; needs to exist

            async def broadcast_reasoning_event(self, ev):
                await fake_broadcast(ev)

        monkeypatch.setattr(step_streaming, "reasoning_event_stream", _FakeStream())

        # Mock service with an openai_config carrying model_name
        service = type("S", (), {})()
        service.openai_config = type("C", (), {"model_name": "google/gemma-4-31B-it"})()

        await _broadcast_llm_call_event(
            success=True,
            handler_name="EthicalPDMA",
            service_name="OpenAICompatibleLLM",
            selected_service=service,
            api_base="https://api.together.xyz/v1",
            response_model=_Result,
            messages=[{"role": "user", "content": "hi"}],
            result=_Result(),
            usage=ResourceUsage(
                tokens_used=15, tokens_input=10, tokens_output=5, model_used="gemma-4"
            ),
            latency_ms=42.5,
            thought_id="th_test",
            task_id="task_test",
            retry_count=0,
        )

        assert len(captured) == 1
        ev = captured[0]
        # Schema-validated payload — these are all the lens-facing fields
        assert ev.handler_name == "EthicalPDMA"
        assert ev.service_name == "OpenAICompatibleLLM"
        assert ev.model == "google/gemma-4-31B-it"
        assert ev.base_url == "https://api.together.xyz/v1"
        assert ev.response_model == "_Result"
        assert ev.duration_ms == 42.5
        assert ev.status == "ok"
        assert ev.error_class is None
        assert ev.prompt_tokens == 10
        assert ev.completion_tokens == 5
        assert ev.prompt_bytes is not None and ev.prompt_bytes > 0
        assert ev.completion_bytes is not None and ev.completion_bytes > 0
        # Hash is SHA-256 hex (64 chars)
        assert ev.prompt_hash is not None and len(ev.prompt_hash) == 64

    async def test_no_subscribers_skips_broadcast(self, monkeypatch):
        """Best-effort: if there's no one listening, don't pay serialization cost."""
        from ciris_engine.logic.infrastructure import step_streaming

        broadcast_called = False

        async def fake_broadcast(_):
            nonlocal broadcast_called
            broadcast_called = True

        class _EmptyStream:
            _subscribers = []  # empty list — broadcast should still work
            _recent_events = []

            async def broadcast_reasoning_event(self, ev):
                await fake_broadcast(ev)

        monkeypatch.setattr(step_streaming, "reasoning_event_stream", _EmptyStream())

        service = type("S", (), {"openai_config": type("C", (), {"model_name": "x"})()})()

        # Helper IS willing to call broadcast even with empty subscribers — the
        # stream itself decides not to deliver. We're pinning that the helper
        # doesn't pre-empt that decision (otherwise the trace adapter, which
        # may subscribe AFTER the call, would miss events).
        await _broadcast_llm_call_event(
            success=True,
            handler_name="EthicalPDMA",
            service_name="MockLLMService",
            selected_service=service,
            api_base=None,
            response_model=_Result,
            messages=[{"role": "user", "content": "hi"}],
            result=_Result(),
            usage=None,
            latency_ms=1.0,
            thought_id="th_test",
            task_id=None,
            retry_count=0,
        )
        assert broadcast_called is True


@pytest.mark.asyncio
class TestBroadcastLlmCallEventFailure:
    """Failure-path broadcast — status, error_class, no result, no usage."""

    async def test_emits_timeout_status_with_error_class(self, monkeypatch):
        captured = []

        from ciris_engine.logic.infrastructure import step_streaming

        class _FakeStream:
            _subscribers = ["dummy"]
            _recent_events = []

            async def broadcast_reasoning_event(self, ev):
                captured.append(ev)

        monkeypatch.setattr(step_streaming, "reasoning_event_stream", _FakeStream())

        class ReadTimeout(Exception):
            pass

        service = type("S", (), {"openai_config": type("C", (), {"model_name": "x"})()})()

        await _broadcast_llm_call_event(
            success=False,
            handler_name="EthicalPDMA",
            service_name="MockLLMService",
            selected_service=service,
            api_base=None,
            response_model=_Result,
            messages=[{"role": "user", "content": "hi"}],
            result=None,
            usage=None,
            latency_ms=90000.0,
            thought_id="th_test",
            task_id="task_test",
            retry_count=0,
            error=ReadTimeout("connection hung"),
        )

        assert len(captured) == 1
        ev = captured[0]
        assert ev.status == "timeout"
        assert ev.error_class == "ReadTimeout"
        assert ev.duration_ms == 90000.0
        # Result-derived fields are None on failure
        assert ev.prompt_tokens is None
        assert ev.completion_tokens is None
        assert ev.completion_bytes is None
        # But prompt-derived fields populate even on failure (the prompt was sent)
        assert ev.prompt_bytes is not None and ev.prompt_bytes > 0
        assert ev.prompt_hash is not None

    async def test_broadcast_failure_does_not_raise(self, monkeypatch):
        """Trace plumbing failure must never break the LLM call path. If the
        downstream stream raises during broadcast_reasoning_event, the helper
        swallows + logs."""
        from ciris_engine.logic.infrastructure import step_streaming

        class _BrokenStream:
            _subscribers = ["dummy"]
            _recent_events = []

            async def broadcast_reasoning_event(self, ev):
                raise RuntimeError("stream is on fire")

        monkeypatch.setattr(step_streaming, "reasoning_event_stream", _BrokenStream())

        service = type("S", (), {"openai_config": type("C", (), {"model_name": "x"})()})()

        # MUST NOT RAISE — even though the underlying stream raised
        await _broadcast_llm_call_event(
            success=True,
            handler_name="EthicalPDMA",
            service_name="MockLLMService",
            selected_service=service,
            api_base=None,
            response_model=_Result,
            messages=[{"role": "user", "content": "hi"}],
            result=_Result(),
            usage=None,
            latency_ms=1.0,
            thought_id="th_test",
            task_id=None,
            retry_count=0,
        )
