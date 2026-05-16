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


class TestConscienceResultIsRecursive:
    """Regression: pre-2.7.8 captured traces validated against
    FSD/TRACE_WIRE_FORMAT.md §5.8 surfaced that the CONSCIENCE_RESULT
    builder was missing `is_recursive` (the boolean flag distinguishing
    initial conscience pass from recursive re-validation post-override).
    ASPDMA_RESULT had it; CONSCIENCE_RESULT didn't, leaving the lens with
    only attempt_index>0 to infer recursive-ness.

    The lens uses the bool flag for direct queries and attempt_index for
    ordering — both are needed. Pin the bool's presence at GENERIC level
    so it stays in the wire shape lens dashboards depend on.
    """

    def test_is_recursive_present_at_generic_level(self):
        service = _make_service(TraceDetailLevel.GENERIC)
        event = {
            "event_type": "CONSCIENCE_RESULT",
            "thought_id": "th_test",
            "task_id": "task_test",
            "timestamp": "2026-04-30T15:00:00Z",
            "conscience_passed": True,
            "action_was_overridden": False,
            "is_recursive": False,
        }
        data = service._extract_component_data("CONSCIENCE_RESULT", event)
        assert "is_recursive" in data
        assert data["is_recursive"] is False

    def test_is_recursive_true_for_recursive_pass(self):
        """A recursive_conscience emission MUST carry is_recursive=True
        so the lens can distinguish from the initial pass without
        inference."""
        service = _make_service(TraceDetailLevel.GENERIC)
        event = {
            "event_type": "CONSCIENCE_RESULT",
            "thought_id": "th_test",
            "task_id": "task_test",
            "timestamp": "2026-04-30T15:00:00Z",
            "conscience_passed": False,
            "action_was_overridden": True,
            "is_recursive": True,
        }
        data = service._extract_component_data("CONSCIENCE_RESULT", event)
        assert data["is_recursive"] is True
        assert data["action_was_overridden"] is True

    def test_is_recursive_defaults_to_false_when_missing(self):
        """If the broadcast event omits is_recursive (older paths),
        builder defaults to False so downstream code never sees None."""
        service = _make_service(TraceDetailLevel.GENERIC)
        event = {
            "event_type": "CONSCIENCE_RESULT",
            "thought_id": "th_test",
            "task_id": "task_test",
            "timestamp": "2026-04-30T15:00:00Z",
            "conscience_passed": True,
        }
        data = service._extract_component_data("CONSCIENCE_RESULT", event)
        assert data.get("is_recursive") is False


class TestSnapshotAndContextCirisVerifyFields:
    """Pin the CIRISVerify attestation field set on SNAPSHOT_AND_CONTEXT.

    The lens uses these for hardware-integrity scoring as part of k_eff
    analysis (see FSD/TRACE_WIRE_FORMAT.md §5.2.1). Each `*_ok` boolean
    is independently meaningful — collapsing them or dropping any from
    GENERIC silently breaks per-check k_eff dimensions in the lens.

    Source of truth for the field set: VerifyAttestationContext in
    ciris_engine/schemas/services/attestation.py.
    """

    def _snapshot_event_with_attestation(self) -> Dict[str, Any]:
        return {
            "event_type": "SNAPSHOT_AND_CONTEXT",
            "thought_id": "th_test",
            "task_id": "task_test",
            "timestamp": "2026-04-30T15:00:00Z",
            "system_snapshot": {
                "cognitive_state": "work",
                "verify_attestation": {
                    "attestation_level": 3,
                    "attestation_status": "verified",
                    "attestation_summary": "Level 3/5 | ✓Binary ✓Environment ✓Registry",
                    "disclosure_severity": "info",
                    "disclosure_text": "",
                    "binary_ok": True,
                    "env_ok": True,
                    "registry_ok": True,
                    "file_integrity_ok": False,
                    "audit_ok": False,
                    "play_integrity_ok": False,
                    "hardware_backed": True,
                    "key_status": "local",
                    "key_id": "agent-test",
                    "ed25519_fingerprint": "0123abcd" * 8,  # 64 hex chars
                    "key_storage_mode": "TPM",
                    "hardware_type": "TpmFirmware",
                    "verify_version": "1.6.3",
                },
            },
        }

    def test_generic_carries_full_per_check_boolean_set(self):
        """All six per-check booleans + hardware_backed must land at GENERIC.
        Each is near-zero-correlation with the reasoning stack and powers
        an independent k_eff dimension."""
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data(
            "SNAPSHOT_AND_CONTEXT", self._snapshot_event_with_attestation()
        )
        # Each check is a separate k_eff dimension — losing any silently
        # collapses the lens's hardware-integrity scoring
        for field in (
            "binary_ok",
            "env_ok",
            "registry_ok",
            "file_integrity_ok",
            "audit_ok",
            "play_integrity_ok",
            "hardware_backed",
        ):
            assert field in data, f"GENERIC missing CIRISVerify check field: {field}"
        # Per-check values pass through verbatim
        assert data["binary_ok"] is True
        assert data["registry_ok"] is True
        assert data["file_integrity_ok"] is False

    def test_generic_carries_attestation_summary_fields(self):
        """attestation_level + attestation_status + attestation_context +
        disclosure_severity must all land at GENERIC. They drive UI banner
        severity and lens-side level-stratified queries."""
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data(
            "SNAPSHOT_AND_CONTEXT", self._snapshot_event_with_attestation()
        )
        for field in (
            "attestation_level",
            "attestation_status",
            "attestation_context",
            "disclosure_severity",
        ):
            assert field in data, f"GENERIC missing attestation summary field: {field}"
        assert data["attestation_level"] == 3
        assert data["attestation_status"] == "verified"
        # Pre-rendered summary string is human-readable — not authoritative
        # but lens may show it in detail dashboards
        assert "Level 3/5" in data["attestation_context"]

    def test_detailed_adds_key_identifying_fields(self):
        """Key identity fields are gated behind DETAILED because they
        identify the agent instance — keep them out of GENERIC for
        deployments that share GENERIC traces with non-operators."""
        service = _make_service(TraceDetailLevel.DETAILED)
        data = service._extract_component_data(
            "SNAPSHOT_AND_CONTEXT", self._snapshot_event_with_attestation()
        )
        for field in (
            "key_status",
            "key_id",
            "ed25519_fingerprint",
            "key_storage_mode",
            "hardware_type",
            "verify_version",
        ):
            assert field in data, f"DETAILED missing key/version field: {field}"
        assert data["ed25519_fingerprint"] == "0123abcd" * 8
        assert data["hardware_type"] == "TpmFirmware"

    def test_generic_does_not_leak_key_identity(self):
        """Key fingerprint and key_id MUST NOT appear at GENERIC — they're
        identifying and gated behind DETAILED. Pin this so a future
        well-meaning refactor doesn't promote them."""
        service = _make_service(TraceDetailLevel.GENERIC)
        data = service._extract_component_data(
            "SNAPSHOT_AND_CONTEXT", self._snapshot_event_with_attestation()
        )
        for field in ("ed25519_fingerprint", "key_id", "key_status"):
            assert field not in data, f"GENERIC unexpectedly leaks identifying field: {field}"

    def test_attestation_absent_when_verify_not_run(self):
        """When CIRISVerify hasn't run (verify_attestation absent),
        builder emits attestation_level=0, attestation_status='not_attempted',
        and the per-check booleans default to None (not False — preserving
        the distinction between 'check failed' and 'check not run')."""
        service = _make_service(TraceDetailLevel.GENERIC)
        event = {
            "event_type": "SNAPSHOT_AND_CONTEXT",
            "thought_id": "th_test",
            "task_id": "task_test",
            "timestamp": "2026-04-30T15:00:00Z",
            "system_snapshot": {"cognitive_state": "work"},  # no verify_attestation
        }
        data = service._extract_component_data("SNAPSHOT_AND_CONTEXT", event)
        assert data["attestation_level"] == 0
        assert data["attestation_status"] == "not_attempted"
        # Per-check booleans default to None when verify wasn't run — distinct
        # from False which means "check ran and failed"
        assert data["binary_ok"] is None
        assert data["env_ok"] is None


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


# Property-based contract fuzz (CIRISAgent#757 / CIRISLens#13).
from hypothesis import given, settings  # noqa: E402
from hypothesis import strategies as st  # noqa: E402


class TestLlmCallParentEventTypeWireContract:
    """Persist's `BatchEvent.parent_event_type` is
    `Option<ReasoningEventType>` (CIRISPersist/src/schema/events.rs:268-275):
    legal values are `None` (field omitted via `skip_serializing_if`) or a
    member of the closed `ReasoningEventType` enum. Any other string lands
    a non-enum value in `trace_llm_calls.parent_event_type` and persist
    HTTP-422s the whole batch (40% reject rate driver per CIRISLens#13).

    The agent's `llm_call_context.UNKNOWN_PARENT_EVENT_TYPE = "UNKNOWN_PARENT"`
    sentinel is for agent-side WARN only — `llm_bus.py:183-189` logs the
    unwired call site so it can be fixed; the sentinel must NOT reach the
    wire. This contract is enforced in `_extract_component_data` for the
    LLM_CALL event.
    """

    # Closed taxonomy mirrored from the agent's ReasoningEvent enum
    # (ciris_engine/schemas/streaming/reasoning_stream.py). Keep in sync if
    # the enum gains members. If a member is added in the agent but not
    # here, this fuzz silently under-covers; if a member here is removed
    # from the agent, the test_unknown_parent_normalized_to_none case
    # still pins the load-bearing invariant.
    VALID_PARENT_EVENT_TYPES = (
        "THOUGHT_START",
        "SNAPSHOT_AND_CONTEXT",
        "DMA_RESULTS",
        "IDMA_RESULT",
        "ASPDMA_RESULT",
        "CONSCIENCE_RESULT",
        "ACTION_RESULT",
    )

    def test_unknown_parent_normalized_to_none(self):
        """The sentinel never reaches the wire — it normalizes to None.

        This is the load-bearing invariant. Without it, persist HTTP-422s
        every batch built by an LLM call made outside a streaming_step
        context (which is exactly the failure mode that drove CIRISLens#13
        and the 22-hour bridge diagnostic cycle).
        """
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _llm_call_event_dict(parent_event_type="UNKNOWN_PARENT")
        data = service._extract_component_data("LLM_CALL", event)
        assert data["parent_event_type"] is None, (
            "Sentinel 'UNKNOWN_PARENT' must normalize to None on the wire — "
            "persist's Option<ReasoningEventType> with skip_serializing_if "
            "omits the field entirely, which is legal. The literal string "
            "lands a non-enum value and persist 422s the batch "
            "(see CIRISLens#13)."
        )

    @given(parent_event_type=st.sampled_from(VALID_PARENT_EVENT_TYPES))
    @settings(max_examples=20)
    def test_valid_enum_values_pass_through_unchanged(self, parent_event_type: str):
        """Every member of ReasoningEventType passes through unchanged.

        Property: for any valid enum value, the wire value matches the
        input. Catches the regression where a future "be defensive" patch
        could unintentionally normalize valid values too.
        """
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _llm_call_event_dict(parent_event_type=parent_event_type)
        data = service._extract_component_data("LLM_CALL", event)
        assert data["parent_event_type"] == parent_event_type

    @given(
        parent_event_type=st.one_of(
            st.none(),
            st.just("UNKNOWN_PARENT"),
            st.sampled_from(VALID_PARENT_EVENT_TYPES),
        )
    )
    @settings(max_examples=30)
    def test_wire_value_is_either_none_or_valid_enum(self, parent_event_type):
        """Wire invariant: for ANY input, the emitted value is either None
        or a legal `ReasoningEventType` member.

        This is the contract persist enforces. If a future change adds a
        new code path that smuggles a different non-enum string into the
        event dict, this fuzz catches it before persist 422s a real run.
        """
        service = _make_service(TraceDetailLevel.GENERIC)
        event = _llm_call_event_dict(parent_event_type=parent_event_type)
        data = service._extract_component_data("LLM_CALL", event)
        wire_value = data["parent_event_type"]
        assert wire_value is None or wire_value in self.VALID_PARENT_EVENT_TYPES, (
            f"Wire value {wire_value!r} is neither None nor a member of "
            f"ReasoningEventType — persist will 422 the batch."
        )


class TestFuzzLocationToRegionPrecision:
    """`_fuzz_location_to_region` rounds lat/lng to PII-safe region
    resolution (~11 km grid) before they hit the wire (CIRISAgent#757).

    The string field `user_location` is already coarsened to
    city/state/country. Two emitted fields cannot disagree on privacy
    posture without leaking precision through the loose one. The fuzz
    here pins the invariant: for ANY input float in the valid lat/lng
    range, the wire string parses back to a value within
    floating-point epsilon of `round(input, 1)` — equivalently, the
    wire never carries more than 1 decimal place of precision.

    Reference resolution (CIRISAgent#757 analysis):
      4 decimals = ~11 m   = a specific house  (the leak we fixed)
      1 decimal  = ~11 km  = a city / region   (target resolution)

    `_PII_LOCATION_FUZZ_DECIMALS = 1` enforces this.
    """

    def test_schaumburg_example_from_pii_analysis(self):
        """The exact captured-prod-body example: lat=42.0334, lng=-88.0834.

        These resolve to a specific house in Schaumburg, Illinois at 4
        decimals. After fuzzing, they must resolve to the city/region
        grid (matching the `user_location` string at the same field).
        """
        from ciris_adapters.ciris_accord_metrics.services import _fuzz_location_to_region

        assert _fuzz_location_to_region(42.0334) == "42.0"
        assert _fuzz_location_to_region(-88.0834) == "-88.1"

    @given(value=st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_wire_precision_never_exceeds_one_decimal(self, value: float):
        """Property: for ANY lat/lng input, the wire value is within
        floating-point epsilon of `round(value, 1)`.

        This is the load-bearing PII invariant. If any future code path
        regresses to emitting raw float precision (the bug this fuzz
        prevents), hypothesis will find an input where the wire value
        differs from the 1-decimal rounding and fail loudly here —
        before a real federation peer's home address ships on a trace.
        """
        from ciris_adapters.ciris_accord_metrics.services import _fuzz_location_to_region

        wire_str = _fuzz_location_to_region(value)
        wire_value = float(wire_str)
        expected = round(value, 1)
        # Floating-point epsilon tolerance — round() of any normal float
        # produces a representable value within 1 ULP of the true tenths.
        assert abs(wire_value - expected) < 1e-9, (
            f"Fuzzed wire value {wire_str!r} (parsed: {wire_value}) does "
            f"not match round({value}, 1) = {expected}. This means the "
            f"emit path is carrying more than 1 decimal of precision — "
            f"region resolution is broken, residence may leak."
        )

    @given(value=st.floats(min_value=-180.0, max_value=180.0, allow_nan=False, allow_infinity=False))
    @settings(max_examples=200)
    def test_wire_string_format_invariant(self, value: float):
        """Property: the wire string is parseable as a float and has
        no more than 1 digit after the decimal point.

        Catches a different regression class than the precision check
        above: if someone changes the helper to use a format string that
        adds spurious precision (e.g., `f"{value:.4f}"` zero-padded),
        the parsed value would still match but the wire bytes would carry
        4-decimal-shaped precision. Asserting the literal string shape
        guards the wire form.
        """
        from ciris_adapters.ciris_accord_metrics.services import _fuzz_location_to_region

        wire_str = _fuzz_location_to_region(value)
        # Must be parseable
        parsed = float(wire_str)
        assert isinstance(parsed, float)
        # Decimal-place count: split on '.', fractional part is at most 1 char.
        # An integer-valued result like "42" (no dot) is also acceptable —
        # the precision contract is satisfied either way.
        if "." in wire_str:
            integer_part, fractional_part = wire_str.split(".", 1)
            # Strip negative sign for digit-counting if present
            assert len(fractional_part) <= 1, (
                f"Wire string {wire_str!r} has fractional part {fractional_part!r} "
                f"(len={len(fractional_part)}) — exceeds 1-decimal precision contract."
            )


class TestBuildCorrelationMetadata:
    """Direct coverage for `_build_correlation_metadata` — the shared
    helper extracted from `_send_events_batch` + `_send_connected_event`
    to eliminate the duplicated populate-PII blocks (which tripped
    SonarCloud's duplicated-lines gate AND doubled the surface where
    the PII fuzz could be missed).

    Closes the SonarCloud coverage gap on the populate-PII branch.
    A single direct test of the helper covers BOTH former call sites
    because both now delegate here.
    """

    def _make_bare_adapter(self):
        """Build an AccordMetricsService skeleton with just the attributes
        `_build_correlation_metadata` reads — no HTTP, no signing key,
        no consent state. Lets us directly call the helper as a unit.
        """
        from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

        obj = AccordMetricsService.__new__(AccordMetricsService)
        # Agent-meta fields — default empty so we can assert each
        # individually triggers an entry when set.
        obj._deployment_region = ""
        obj._deployment_type = ""
        obj._agent_role = ""
        obj._agent_template = ""
        # Location-sharing state — default consent off.
        obj._share_location_in_traces = False
        obj._user_location = ""
        obj._user_timezone = ""
        obj._user_latitude = None
        obj._user_longitude = None
        return obj

    def test_empty_state_yields_empty_dict(self):
        """No agent-meta + no location-sharing → empty correlation_metadata."""
        adapter = self._make_bare_adapter()
        assert adapter._build_correlation_metadata() == {}

    def test_agent_meta_fields_populated_when_set(self):
        """deployment_region / type / agent_role / agent_template each
        contribute an entry when their backing attr is truthy."""
        adapter = self._make_bare_adapter()
        adapter._deployment_region = "us-west-2"
        adapter._deployment_type = "production"
        adapter._agent_role = "moderator"
        adapter._agent_template = "datum"
        assert adapter._build_correlation_metadata() == {
            "deployment_region": "us-west-2",
            "deployment_type": "production",
            "agent_role": "moderator",
            "agent_template": "datum",
        }

    def test_consent_off_omits_all_pii_even_when_lat_lng_set(self):
        """Consent gate is load-bearing — even with lat/lng set, if
        `_share_location_in_traces=False` no PII fields appear."""
        adapter = self._make_bare_adapter()
        adapter._user_location = "Schaumburg, Illinois, USA"
        adapter._user_timezone = "America/Chicago"
        adapter._user_latitude = 42.0334
        adapter._user_longitude = -88.0834
        adapter._share_location_in_traces = False
        result = adapter._build_correlation_metadata()
        for pii_field in ("user_location", "user_timezone", "user_latitude", "user_longitude"):
            assert pii_field not in result, (
                f"Consent off → {pii_field!r} must NOT appear. Got: {result}"
            )

    def test_consent_on_emits_fuzzed_lat_lng(self):
        """Load-bearing case: consent flipped on, lat/lng set → region-fuzz
        applied at the populate site. Schaumburg example from
        CIRISAgent#757 PII analysis."""
        adapter = self._make_bare_adapter()
        adapter._share_location_in_traces = True
        adapter._user_location = "Schaumburg, Illinois, USA"
        adapter._user_timezone = "America/Chicago"
        adapter._user_latitude = 42.0334
        adapter._user_longitude = -88.0834
        result = adapter._build_correlation_metadata()
        # Raw strings pass through (already coarse city/region)
        assert result["user_location"] == "Schaumburg, Illinois, USA"
        assert result["user_timezone"] == "America/Chicago"
        # PII fuzz invariant: 4-decimal source → 1-decimal wire
        assert result["user_latitude"] == "42.0", (
            f"populate path must call _fuzz_location_to_region — got "
            f"{result['user_latitude']!r}, expected '42.0'"
        )
        assert result["user_longitude"] == "-88.1", (
            f"populate path must call _fuzz_location_to_region — got "
            f"{result['user_longitude']!r}, expected '-88.1'"
        )

    def test_consent_on_omits_individual_unset_pii_fields(self):
        """Consent on but individual PII field empty/None → that one
        field stays out (per-field guard, not all-or-nothing)."""
        adapter = self._make_bare_adapter()
        adapter._share_location_in_traces = True
        adapter._user_location = "Berlin, Germany"
        # _user_timezone left "", _user_latitude/longitude left None
        assert adapter._build_correlation_metadata() == {"user_location": "Berlin, Germany"}

    def test_consent_on_with_only_latitude_set(self):
        """Per-field gate: only lat set, only lat emitted (fuzzed).
        Pins the `is not None` discriminator for the numeric fields."""
        adapter = self._make_bare_adapter()
        adapter._share_location_in_traces = True
        adapter._user_latitude = 52.5200  # Berlin
        # longitude left None
        assert adapter._build_correlation_metadata() == {"user_latitude": "52.5"}

    def test_zero_latitude_is_emitted_not_treated_as_missing(self):
        """Edge case: lat=0.0 is valid (equator) and `is not None`
        correctly admits it. Guards against `if self._user_latitude:`
        regression."""
        adapter = self._make_bare_adapter()
        adapter._share_location_in_traces = True
        adapter._user_latitude = 0.0
        adapter._user_longitude = 0.0
        result = adapter._build_correlation_metadata()
        assert result["user_latitude"] == "0.0"
        assert result["user_longitude"] == "0.0"

    def test_send_events_batch_and_send_connected_event_both_call_helper(self):
        """Pin the delegation invariant — both former populate sites now
        route through `_build_correlation_metadata`. If a future refactor
        re-inlines either call site, this test fails."""
        import inspect
        from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

        seb_source = inspect.getsource(AccordMetricsService._send_events_batch)
        sce_source = inspect.getsource(AccordMetricsService._send_connected_event)
        assert "_build_correlation_metadata()" in seb_source, (
            "_send_events_batch must delegate populate-PII to "
            "_build_correlation_metadata — re-inlining defeats both the "
            "duplicated-lines fix AND the single-test coverage gain."
        )
        assert "_build_correlation_metadata()" in sce_source, (
            "_send_connected_event must delegate populate-PII to "
            "_build_correlation_metadata — same reasoning as above."
        )
