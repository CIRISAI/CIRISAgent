"""Tests for the v2.7.8 reasoning event additions.

Pins the wire shape of LLMCallEvent and VerbSecondPassResultEvent — the
two schema additions from FSD/TRACE_EVENT_LOG_PERSISTENCE.md phase 0.
Both events are persisted to the lens, so changes to required fields
or to the dispatcher are observable from outside the agent.
"""

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.services.runtime_control import (
    LLMCallEvent,
    ReasoningEvent,
    VerbSecondPassResultEvent,
)
from ciris_engine.schemas.streaming.reasoning_stream import (
    ReasoningEventUnion,
    create_reasoning_event,
)


class TestLLMCallEventSchema:
    """Wire shape for per-LLM-call observation events.

    These rows feed the lens trace_llm_calls table — the schema needs to
    be stable across agent versions or the lens write logic breaks.
    """

    def test_minimum_required_fields(self):
        """timestamp, handler_name, service_name, duration_ms, status,
        parent_event_type, parent_attempt_index are required.

        parent_event_type + parent_attempt_index pinned as required as of
        2.7.9 per TRACE_WIRE_FORMAT.md §5.10 (item #5 of #712). Lens-side
        persistence enforces presence; the agent's wire-format emission
        is non-optional once trace_schema_version="2.7.9".
        """
        ev = LLMCallEvent(
            timestamp="2026-04-30T15:00:00Z",
            handler_name="EthicalPDMA",
            service_name="MockLLMService",
            duration_ms=42.0,
            status="ok",
            parent_event_type="DMA_RESULTS",
            parent_attempt_index=0,
        )
        assert ev.event_type == ReasoningEvent.LLM_CALL
        assert ev.duration_ms == 42.0
        assert ev.status == "ok"
        assert ev.parent_event_type == "DMA_RESULTS"
        assert ev.parent_attempt_index == 0
        # Optional fields default to None / 1 / 0
        assert ev.thought_id is None
        assert ev.attempt_count == 1
        assert ev.retry_count == 0

    def test_required_parent_event_type(self):
        """parent_event_type is REQUIRED as of 2.7.9 — drop it and validation fails."""
        with pytest.raises(ValidationError) as exc_info:
            LLMCallEvent(
                timestamp="2026-04-30T15:00:00Z",
                handler_name="EthicalPDMA",
                service_name="MockLLMService",
                duration_ms=42.0,
                status="ok",
                parent_attempt_index=0,
            )
        assert "parent_event_type" in str(exc_info.value)

    def test_required_parent_attempt_index(self):
        """parent_attempt_index is REQUIRED as of 2.7.9."""
        with pytest.raises(ValidationError) as exc_info:
            LLMCallEvent(
                timestamp="2026-04-30T15:00:00Z",
                handler_name="EthicalPDMA",
                service_name="MockLLMService",
                duration_ms=42.0,
                status="ok",
                parent_event_type="DMA_RESULTS",
            )
        assert "parent_attempt_index" in str(exc_info.value)

    def test_parent_attempt_index_non_negative(self):
        """ge=0 constraint blocks negative parent index."""
        with pytest.raises(ValidationError):
            LLMCallEvent(
                timestamp="2026-04-30T15:00:00Z",
                handler_name="EthicalPDMA",
                service_name="MockLLMService",
                duration_ms=42.0,
                status="ok",
                parent_event_type="DMA_RESULTS",
                parent_attempt_index=-1,
            )

    def test_required_field_handler_name(self):
        """handler_name is required — drop it and validation fails."""
        with pytest.raises(ValidationError) as exc_info:
            LLMCallEvent(
                timestamp="2026-04-30T15:00:00Z",
                service_name="MockLLMService",
                duration_ms=42.0,
                status="ok",
            )
        assert "handler_name" in str(exc_info.value)

    def test_required_field_duration_ms(self):
        with pytest.raises(ValidationError) as exc_info:
            LLMCallEvent(
                timestamp="2026-04-30T15:00:00Z",
                handler_name="EthicalPDMA",
                service_name="MockLLMService",
                status="ok",
            )
        assert "duration_ms" in str(exc_info.value)

    def test_duration_ms_non_negative(self):
        """ge=0.0 constraint blocks negative latency."""
        with pytest.raises(ValidationError):
            LLMCallEvent(
                timestamp="2026-04-30T15:00:00Z",
                handler_name="EthicalPDMA",
                service_name="MockLLMService",
                duration_ms=-5.0,
                status="ok",
            )

    def test_full_payload_with_failure_fields(self):
        """Failure events carry error_class, status enum, and broken sizes."""
        ev = LLMCallEvent(
            timestamp="2026-04-30T15:00:00Z",
            thought_id="th_test",
            task_id="task_test",
            handler_name="EthicalPDMA",
            service_name="OpenAICompatibleLLM",
            model="google/gemma-4-31B-it",
            base_url="https://api.together.xyz/v1",
            response_model="EthicalDMAResult",
            prompt_tokens=8192,
            completion_tokens=0,
            prompt_bytes=32666,
            completion_bytes=None,
            duration_ms=90000.0,
            status="timeout",
            error_class="ReadTimeout",
            attempt_count=1,
            retry_count=2,
            prompt_hash="0" * 64,
            parent_event_type="DMA_RESULTS",
            parent_attempt_index=0,
        )
        # All status enum values from the schema docstring should round-trip
        assert ev.status == "timeout"
        assert ev.error_class == "ReadTimeout"
        assert ev.completion_bytes is None  # Optional[int] — None is valid for failures

    def test_extra_fields_allowed_for_forward_compat(self):
        """Pydantic v2 default is to ignore extras; older lens shouldn't break
        when the agent ships a newer schema with more fields."""
        ev = LLMCallEvent(
            timestamp="2026-04-30T15:00:00Z",
            handler_name="EthicalPDMA",
            service_name="MockLLMService",
            duration_ms=10.0,
            status="ok",
            parent_event_type="DMA_RESULTS",
            parent_attempt_index=0,
            future_field="ignored",  # not in schema; should not raise
        )
        # extras drop silently; the model_dump won't include the extra
        assert "future_field" not in ev.model_dump()


class TestVerbSecondPassResultEventSchema:
    """Wire shape for the generic verb-second-pass event (replaces TSASPDMA_RESULT)."""

    def test_minimum_required_fields(self):
        ev = VerbSecondPassResultEvent(
            thought_id="th_test",
            timestamp="2026-04-30T15:00:00Z",
            verb="tool",
            original_action="tool",
            original_reasoning="ASPDMA selected curl",
            final_action="tool",
            final_reasoning="TSASPDMA confirmed",
        )
        assert ev.event_type == ReasoningEvent.VERB_SECOND_PASS_RESULT
        assert ev.verb == "tool"
        assert ev.verb_specific_data == {}  # default_factory=dict
        assert ev.task_id is None
        assert ev.second_pass_prompt is None

    def test_verb_required(self):
        """verb discriminator is required — without it the lens can't decode
        verb_specific_data."""
        with pytest.raises(ValidationError) as exc_info:
            VerbSecondPassResultEvent(
                thought_id="th_test",
                timestamp="2026-04-30T15:00:00Z",
                original_action="tool",
                original_reasoning="x",
                final_action="tool",
                final_reasoning="y",
            )
        assert "verb" in str(exc_info.value)

    def test_verb_specific_data_is_opaque_jsondict(self):
        """Schema treats verb_specific_data as JSONDict — any dict shape passes."""
        # TOOL shape
        tool_ev = VerbSecondPassResultEvent(
            thought_id="th_test",
            timestamp="2026-04-30T15:00:00Z",
            verb="tool",
            original_action="tool",
            original_reasoning="x",
            final_action="speak",
            final_reasoning="y",
            verb_specific_data={
                "original_tool_name": "curl",
                "final_tool_name": None,
                "original_parameters": {},
                "final_parameters": {"content": "clarify"},
            },
        )
        assert tool_ev.verb_specific_data["original_tool_name"] == "curl"

        # DEFER shape — entirely different fields
        defer_ev = VerbSecondPassResultEvent(
            thought_id="th_test",
            timestamp="2026-04-30T15:00:00Z",
            verb="defer",
            original_action="defer",
            original_reasoning="x",
            final_action="defer",
            final_reasoning="y",
            verb_specific_data={
                "rights_basis": ["fair_trial"],
                "primary_need_category": "justice_and_legal_agency",
                "domain_hint": "legal",
            },
        )
        assert defer_ev.verb_specific_data["rights_basis"] == ["fair_trial"]
        # Schema shouldn't care that the keys are completely different per verb
        assert "original_tool_name" not in defer_ev.verb_specific_data


class TestCreateReasoningEventDispatcher:
    """The dispatcher is the only sanctioned way to construct events from the
    enum + kwargs. Adding a new ReasoningEvent without wiring the dispatcher
    leaves the event unreachable from outside the schema module."""

    def test_dispatcher_constructs_llm_call(self):
        ev = create_reasoning_event(
            event_type=ReasoningEvent.LLM_CALL,
            thought_id="th_test",
            task_id="task_test",
            timestamp="2026-04-30T15:00:00Z",
            handler_name="EthicalPDMA",
            service_name="MockLLMService",
            duration_ms=10.0,
            status="ok",
            parent_event_type="DMA_RESULTS",
            parent_attempt_index=0,
        )
        assert isinstance(ev, LLMCallEvent)
        assert ev.handler_name == "EthicalPDMA"
        assert ev.parent_event_type == "DMA_RESULTS"
        # And it satisfies the union (so reasoning_event_stream can broadcast it)
        assert isinstance(ev, ReasoningEventUnion.__args__)

    def test_dispatcher_constructs_verb_second_pass(self):
        ev = create_reasoning_event(
            event_type=ReasoningEvent.VERB_SECOND_PASS_RESULT,
            thought_id="th_test",
            task_id="task_test",
            timestamp="2026-04-30T15:00:00Z",
            verb="defer",
            original_action="defer",
            original_reasoning="initial defer",
            final_action="defer",
            final_reasoning="DSASPDMA refined",
            verb_specific_data={"rights_basis": ["x"]},
        )
        assert isinstance(ev, VerbSecondPassResultEvent)
        assert ev.verb == "defer"

    def test_dispatcher_llm_call_allows_none_thought_id(self):
        """LLM_CALL events may originate from contexts where thought_id is None
        (future dream-state introspection, system probes). The dispatcher
        and schema both have to permit it — pin that contract.

        Such out-of-pipeline calls report parent_event_type="UNKNOWN_PARENT"
        from the ContextVar default — the broadcast helper logs a warning so
        we can wire them as we find them.
        """
        ev = create_reasoning_event(
            event_type=ReasoningEvent.LLM_CALL,
            thought_id=None,
            task_id=None,
            timestamp="2026-04-30T15:00:00Z",
            handler_name="SystemProbe",
            service_name="MockLLMService",
            duration_ms=5.0,
            status="ok",
            parent_event_type="UNKNOWN_PARENT",
            parent_attempt_index=0,
        )
        assert ev.thought_id is None
        assert ev.parent_event_type == "UNKNOWN_PARENT"

    def test_dispatcher_unknown_event_raises(self):
        """Defensive — dispatcher should still reject unknown types so a future
        rename surfaces loudly."""
        with pytest.raises(ValueError, match="Unknown reasoning event type"):
            create_reasoning_event(
                event_type="not_an_event",  # type: ignore[arg-type]
                thought_id="th",
                task_id=None,
                timestamp="t",
            )


class TestReasoningEventEnum:
    """Pin the wire-format string of the new enum values — these are
    serialized to the lens and changing them is a breaking change."""

    def test_llm_call_string(self):
        assert ReasoningEvent.LLM_CALL.value == "llm_call"

    def test_verb_second_pass_result_string(self):
        assert ReasoningEvent.VERB_SECOND_PASS_RESULT.value == "verb_second_pass_result"

    def test_legacy_tsaspdma_result_still_present(self):
        """TSASPDMA_RESULT is DEPRECATED but still emitted alongside the new
        event during the FSD §10 phase 0 transition window. Removing it now
        would break older lens versions that haven't switched over yet."""
        assert ReasoningEvent.TSASPDMA_RESULT.value == "tsaspdma_result"
