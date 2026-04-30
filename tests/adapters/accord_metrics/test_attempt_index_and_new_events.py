"""Tests for the v2.7.8 accord_metrics adapter additions.

Covers three areas in `ciris_adapters/ciris_accord_metrics/services.py`:

1. _extract_component_data for the LLM_CALL event — trace-level-gated
   field selection (GENERIC / DETAILED / FULL_TRACES).
2. _extract_component_data for the VERB_SECOND_PASS_RESULT event —
   verb discriminator + opaque verb_specific_data + trace-level gating.
3. attempt_index counter — injected into the event dict at receive time
   in _process_single_event, propagated to component_data, and cleaned
   up when the trace completes.

The autouse `mock_unified_signing_key` fixture from conftest.py covers
the Ed25519 vault load so the service constructs without crypto deps.
"""

import asyncio
from typing import Any, Dict

import pytest

from ciris_adapters.ciris_accord_metrics.services import (
    AccordMetricsService,
    TraceDetailLevel,
)


def _make_service(trace_level: TraceDetailLevel = TraceDetailLevel.GENERIC) -> AccordMetricsService:
    """Construct a consented service at the given trace level."""
    return AccordMetricsService(
        config={
            "consent_given": True,
            "consent_timestamp": "2026-01-01T00:00:00Z",
            "trace_level": trace_level.value,
        }
    )


def _llm_call_event_dict(**overrides: Any) -> Dict[str, Any]:
    """Reasoning event dict shaped like what reasoning_event_stream ships."""
    base = {
        "event_type": "LLM_CALL",
        "thought_id": "th_test",
        "task_id": "task_test",
        "timestamp": "2026-04-30T15:00:00Z",
        "handler_name": "EthicalPDMA",
        "service_name": "OpenAICompatibleLLM",
        "model": "google/gemma-4-31B-it",
        "base_url": "https://api.together.xyz/v1",
        "response_model": "EthicalDMAResult",
        "duration_ms": 90000.0,
        "prompt_tokens": 8192,
        "completion_tokens": 512,
        "prompt_bytes": 32666,
        "completion_bytes": 1024,
        "cost_usd": 0.0123,
        "status": "ok",
        "error_class": None,
        "attempt_count": 1,
        "retry_count": 0,
        "prompt_hash": "0" * 64,
        "prompt": "<full prompt text here>",
        "response_text": "<full completion here>",
    }
    base.update(overrides)
    return base


def _verb_second_pass_event_dict(**overrides: Any) -> Dict[str, Any]:
    base = {
        "event_type": "VERB_SECOND_PASS_RESULT",
        "thought_id": "th_test",
        "task_id": "task_test",
        "timestamp": "2026-04-30T15:00:00Z",
        "verb": "tool",
        "original_action": "tool",
        "original_reasoning": "ASPDMA selected curl",
        "final_action": "speak",
        "final_reasoning": "TSASPDMA wants clarification",
        "verb_specific_data": {
            "original_tool_name": "curl",
            "final_tool_name": None,
            "original_parameters": {},
            "final_parameters": {"content": "clarify"},
        },
        "second_pass_prompt": "<full TSASPDMA prompt>",
    }
    base.update(overrides)
    return base


class TestLlmCallExtractComponentData:
    """Per-LLM-call event builder. The trace-level gating is the privacy
    contract — full prompt/response text is FULL only, hash is DETAILED+,
    nothing content-bearing at GENERIC."""

    def test_generic_excludes_prompt_hash_and_text(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _llm_call_event_dict()
        data = service._extract_component_data("LLM_CALL", event)

        # Cheap fields always present — needed for cost/latency monitoring
        assert data["handler_name"] == "EthicalPDMA"
        assert data["service_name"] == "OpenAICompatibleLLM"
        assert data["model"] == "google/gemma-4-31B-it"
        assert data["duration_ms"] == 90000.0
        assert data["prompt_tokens"] == 8192
        assert data["completion_tokens"] == 512
        assert data["prompt_bytes"] == 32666
        assert data["status"] == "ok"
        # GENERIC privacy contract: no content-bearing fields
        assert "prompt_hash" not in data
        assert "prompt" not in data
        assert "response_text" not in data

    def test_detailed_adds_prompt_hash(self):
        service = _make_service(TraceDetailLevel.DETAILED)
        event = _llm_call_event_dict()
        data = service._extract_component_data("LLM_CALL", event)

        assert data["prompt_hash"] == "0" * 64
        # DETAILED still excludes the actual content
        assert "prompt" not in data
        assert "response_text" not in data

    def test_full_traces_adds_prompt_and_response(self):
        service = _make_service(TraceDetailLevel.FULL_TRACES)
        event = _llm_call_event_dict()
        data = service._extract_component_data("LLM_CALL", event)

        assert data["prompt"] == "<full prompt text here>"
        assert data["response_text"] == "<full completion here>"
        assert data["prompt_hash"] == "0" * 64  # DETAILED includes still apply

    def test_failure_event_carries_error_class(self):
        """status=timeout + error_class lands in GENERIC, not gated. This is
        the field that makes the Spanish-MH-style three-consecutive-timeouts
        diagnosis a one-query lookup."""
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _llm_call_event_dict(
            status="timeout",
            error_class="ReadTimeout",
            completion_tokens=None,
            completion_bytes=None,
        )
        data = service._extract_component_data("LLM_CALL", event)

        assert data["status"] == "timeout"
        assert data["error_class"] == "ReadTimeout"
        assert data["completion_tokens"] is None


class TestVerbSecondPassExtractComponentData:
    """Generic verb-second-pass event builder — verb discriminator must be
    in GENERIC so the lens can route by verb, verb_specific_data is opaque
    serialized payload also in GENERIC, reasoning text is DETAILED+, the
    prompt is FULL only."""

    def test_generic_carries_verb_and_action_and_payload(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _verb_second_pass_event_dict()
        data = service._extract_component_data("VERB_SECOND_PASS_RESULT", event)

        assert data["verb"] == "tool"
        assert data["original_action"] == "tool"
        assert data["final_action"] == "speak"
        # verb_specific_data is opaque at GENERIC — serialized as-is so the
        # lens can decode by verb at query time
        assert data["verb_specific_data"]["original_tool_name"] == "curl"
        assert data["verb_specific_data"]["final_parameters"] == {"content": "clarify"}
        # GENERIC excludes reasoning text + prompt
        assert "original_reasoning" not in data
        assert "final_reasoning" not in data
        assert "second_pass_prompt" not in data

    def test_detailed_adds_reasoning_text(self):
        service = _make_service(TraceDetailLevel.DETAILED)
        event = _verb_second_pass_event_dict()
        data = service._extract_component_data("VERB_SECOND_PASS_RESULT", event)

        assert data["original_reasoning"] == "ASPDMA selected curl"
        assert data["final_reasoning"] == "TSASPDMA wants clarification"
        # Prompt still excluded at DETAILED
        assert "second_pass_prompt" not in data

    def test_full_adds_second_pass_prompt(self):
        service = _make_service(TraceDetailLevel.FULL_TRACES)
        event = _verb_second_pass_event_dict()
        data = service._extract_component_data("VERB_SECOND_PASS_RESULT", event)

        assert data["second_pass_prompt"] == "<full TSASPDMA prompt>"

    def test_defer_verb_specific_data_passes_through(self):
        """verb_specific_data is per-verb — the same builder must handle
        completely different shapes without losing fields."""
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _verb_second_pass_event_dict(
            verb="defer",
            original_action="defer",
            final_action="defer",
            verb_specific_data={
                "rights_basis": ["fair_trial"],
                "primary_need_category": "justice_and_legal_agency",
                "domain_hint": "legal",
                "operational_reason": "licensed_domain_required",
            },
        )
        data = service._extract_component_data("VERB_SECOND_PASS_RESULT", event)

        assert data["verb"] == "defer"
        # Schema-agnostic passthrough — keys are completely different from TOOL
        assert data["verb_specific_data"]["rights_basis"] == ["fair_trial"]
        assert data["verb_specific_data"]["domain_hint"] == "legal"
        assert "original_tool_name" not in data["verb_specific_data"]


class TestEventToComponentMapping:
    """The EVENT_TO_COMPONENT mapping routes events to trace component_type.
    Pin the new entries — these decide the lens column the event lands in."""

    def test_llm_call_maps_to_llm_call_component(self):
        assert AccordMetricsService.EVENT_TO_COMPONENT["LLM_CALL"] == "llm_call"
        assert (
            AccordMetricsService.EVENT_TO_COMPONENT["ReasoningEvent.LLM_CALL"]
            == "llm_call"
        )

    def test_verb_second_pass_maps_to_verb_second_pass_component(self):
        assert (
            AccordMetricsService.EVENT_TO_COMPONENT["VERB_SECOND_PASS_RESULT"]
            == "verb_second_pass"
        )
        assert (
            AccordMetricsService.EVENT_TO_COMPONENT["ReasoningEvent.VERB_SECOND_PASS_RESULT"]
            == "verb_second_pass"
        )

    def test_legacy_tsaspdma_still_maps_to_rationale(self):
        """Transition window per FSD §10 phase 0 gate — TSASPDMA_RESULT keeps
        flowing alongside VERB_SECOND_PASS_RESULT until the lens stops
        reading it. Pin this so a future "remove the legacy" PR can't
        silently break older lens deployments."""
        assert AccordMetricsService.EVENT_TO_COMPONENT["TSASPDMA_RESULT"] == "rationale"


@pytest.mark.asyncio
class TestAttemptIndexCounter:
    """attempt_index is computed at adapter receive time and injected into
    the event dict before the component_data builder runs. Single-subscriber
    FIFO from reasoning_event_stream guarantees broadcast order, so the
    counter increments produce a stable monotonic index keyed by
    (thought_id, event_type)."""

    async def test_first_event_for_thought_gets_index_zero(self):
        service = _make_service()
        event = _llm_call_event_dict(thought_id="th_a")

        await service._process_single_event(event)

        assert event["attempt_index"] == 0
        # Counter incremented for next time
        assert service._attempt_counters[("th_a", "LLM_CALL")] == 1

    async def test_repeated_event_increments_for_same_thought(self):
        """Multiple LLM_CALL events for the same thought get 0, 1, 2, ..."""
        service = _make_service()

        for expected_index in range(5):
            event = _llm_call_event_dict(thought_id="th_a")
            await service._process_single_event(event)
            assert event["attempt_index"] == expected_index

        assert service._attempt_counters[("th_a", "LLM_CALL")] == 5

    async def test_separate_thoughts_have_independent_counters(self):
        """Per-(thought_id, event_type) — two different thoughts emitting the
        same event type each get their own 0..N sequence."""
        service = _make_service()

        # Interleave events across two thoughts
        for thought_id, expected in [("th_a", 0), ("th_b", 0), ("th_a", 1), ("th_b", 1), ("th_a", 2)]:
            event = _llm_call_event_dict(thought_id=thought_id)
            await service._process_single_event(event)
            assert event["attempt_index"] == expected

    async def test_separate_event_types_have_independent_counters(self):
        """Same thought, different event types → independent counters."""
        service = _make_service()

        ev1 = _llm_call_event_dict(thought_id="th_a")
        ev2 = _verb_second_pass_event_dict(thought_id="th_a")

        await service._process_single_event(ev1)
        await service._process_single_event(ev2)
        await service._process_single_event(ev1)

        # LLM_CALL counter: 0, then 1
        assert service._attempt_counters[("th_a", "LLM_CALL")] == 2
        # VERB_SECOND_PASS_RESULT counter: separate, sat at 0 → now 1
        assert service._attempt_counters[("th_a", "VERB_SECOND_PASS_RESULT")] == 1
        assert ev1["attempt_index"] == 1  # second LLM_CALL
        assert ev2["attempt_index"] == 0  # first VERB_SECOND_PASS_RESULT

    async def test_attempt_index_lands_in_trace_component_data(self):
        """The whole point of attempt_index is for the lens row to carry it.
        Confirm it makes it into the persisted TraceComponent.data dict
        regardless of the underlying event_type's builder."""
        service = _make_service()

        event = _llm_call_event_dict(thought_id="th_a")
        await service._process_single_event(event)

        # First time → index 0; trace must have one component with that index
        assert "th_a" in service._active_traces
        components = service._active_traces["th_a"].components
        assert len(components) == 1
        assert components[0].data["attempt_index"] == 0

        # Second event → index 1 lands on the new component
        await service._process_single_event(_llm_call_event_dict(thought_id="th_a"))
        components = service._active_traces["th_a"].components
        assert components[1].data["attempt_index"] == 1


@pytest.mark.asyncio
class TestAttemptIndexCleanup:
    """When a thought completes (ACTION_RESULT triggers _complete_trace),
    its attempt_index counter entries must be dropped — otherwise the dict
    grows unbounded across long-running agents."""

    async def test_complete_trace_drops_counters_for_thought(self):
        service = _make_service()

        # Fire several events for two thoughts
        for _ in range(3):
            await service._process_single_event(_llm_call_event_dict(thought_id="th_a"))
            await service._process_single_event(_llm_call_event_dict(thought_id="th_b"))

        # Both thoughts have counter entries
        assert ("th_a", "LLM_CALL") in service._attempt_counters
        assert ("th_b", "LLM_CALL") in service._attempt_counters

        # Complete only th_a — th_b counters must survive
        await service._complete_trace("th_a", "2026-04-30T15:30:00Z")

        assert ("th_a", "LLM_CALL") not in service._attempt_counters
        assert ("th_b", "LLM_CALL") in service._attempt_counters

    async def test_complete_trace_drops_all_event_types_for_thought(self):
        """A single thought can emit many event types — completion must drop
        all of its counter keys, not just one event type."""
        service = _make_service()

        await service._process_single_event(_llm_call_event_dict(thought_id="th_a"))
        await service._process_single_event(_verb_second_pass_event_dict(thought_id="th_a"))

        assert len([k for k in service._attempt_counters if k[0] == "th_a"]) == 2

        await service._complete_trace("th_a", "2026-04-30T15:30:00Z")

        assert [k for k in service._attempt_counters if k[0] == "th_a"] == []

    async def test_complete_trace_no_op_when_thought_unknown(self):
        """Completing a thought that was never tracked must be safe."""
        service = _make_service()
        # No exception, no state change
        await service._complete_trace("never_seen", "2026-04-30T15:30:00Z")
        assert service._attempt_counters == {}
