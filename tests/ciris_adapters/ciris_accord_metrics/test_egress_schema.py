"""Per-level trace egress schema, enforced before signing (CIRISAgent#1244 / #1245).

GENERIC is "numeric scores only", DETAILED "actionable lists and key
identifiers", FULL everything but bounded. A built component that breaks its
level's schema is FILTERED (field dropped, wrong type dropped, over-long capped)
and every violation is a WARNING naming event / field / level / kind, never the
value. The canonical #1245 case: a DEFER reason naming "@María" inside GENERIC
``verb_specific_data``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

import pytest

from ciris_adapters.ciris_accord_metrics import egress_schema
from ciris_adapters.ciris_accord_metrics.egress_schema import (
    REASON_MAX_CHARS,
    TraceLevel,
    ViolationKind,
    ViolationReporter,
    enforce_egress_schema,
)
from ciris_adapters.ciris_accord_metrics.services import AccordMetricsService

MARIA = "Ideación suicida reportada por @María; requiere intervención inmediata de un profesional."
SECRET_PARAM = "wallet-address-0xDEADBEEF-sensitive"

VALID: Dict[TraceLevel, Dict[str, Dict[str, Any]]] = {
    TraceLevel.GENERIC: {
        "THOUGHT_START": {"round_number": 1, "thought_depth": 0, "task_priority": 5, "thought_type": "standard"},
        "DMA_RESULTS": {
            "csdma": {"plausibility_score": 0.9},
            "dsdma": {"domain_alignment": 0.8},
            "pdma": {"has_conflicts": False},
            "idma": {"k_eff": 1.2, "phase": "healthy", "fragility_flag": True},
            "csdma_plausibility_score": 0.9,
            "dsdma_domain_alignment": 0.8,
        },
        "VERB_SECOND_PASS_RESULT": {
            "verb": "defer",
            "original_action": "speak",
            "final_action": "defer",
            "verb_specific_data": {"rights_basis": ["safety"], "primary_need_category": "crisis_support"},
        },
        "LLM_CALL": {"handler_name": "CSDMA", "model": "google/gemma-4-31B-it", "duration_ms": 12.5, "status": "ok"},
        "ACTION_RESULT": {"execution_success": True, "tokens_total": 42, "action_executed": "speak"},
    },
    TraceLevel.DETAILED: {
        "THOUGHT_START": {
            "round_number": 1,
            "thought_type": "standard",
            "channel_id": "safety_battery_ani_a0_hooks_20260911T160525Z",
            "parent_thought_id": "th_seed_1",
        },
        "DMA_RESULTS": {
            "csdma": {"plausibility_score": 0.9, "flags": ["human_interaction", "requires clarification"]},
            "dsdma": {"domain_alignment": 0.8, "domain": "general", "flags": ["mock_domain"]},
            "dsdma_domain": "general",
        },
        "VERB_SECOND_PASS_RESULT": {
            "verb": "defer",
            "verb_specific_data": {"defer_reason": "Needs a human reviewer.", "defer_until": "2026-10-08T12:00:00Z"},
        },
        "LLM_CALL": {"model": "m", "base_url": "https://api.together.xyz/v1", "prompt_hash": "ab12cd34"},
    },
    TraceLevel.FULL_TRACES: {
        "VERB_SECOND_PASS_RESULT": {
            "verb": "tool",
            "final_reasoning": "The tool is appropriate because...",
            "verb_specific_data": {"final_tool_name": "get_status", "final_parameters": {"include_details": False}},
        },
        "LLM_CALL": {"prompt": "full prompt text", "response_text": "full response"},
    },
}


@pytest.mark.parametrize(
    "level,event_type",
    [(level, et) for level, events in VALID.items() for et in events],
)
def test_a_valid_event_passes_unchanged(level: TraceLevel, event_type: str) -> None:
    data = VALID[level][event_type]
    result = enforce_egress_schema(event_type, level, data)
    assert result.violations == []
    assert result.data == data


class TestEachViolationKind:
    def test_unexpected_field_is_dropped(self) -> None:
        result = enforce_egress_schema("ACTION_RESULT", TraceLevel.GENERIC, {"tokens_total": 3, "user_message": "hi"})
        assert result.data == {"tokens_total": 3}
        assert [(v.path, v.kind) for v in result.violations] == [("user_message", ViolationKind.UNEXPECTED_FIELD)]

    def test_field_above_its_level_is_dropped(self) -> None:
        result = enforce_egress_schema(
            "LLM_CALL", TraceLevel.GENERIC, {"model": "m", "base_url": "https://x.example/v1"}
        )
        assert result.data == {"model": "m"}
        assert result.violations[0].path == "base_url"
        assert "allowed from detailed" in result.violations[0].detail

    def test_letters_where_a_number_belongs(self) -> None:
        result = enforce_egress_schema("ACTION_RESULT", TraceLevel.GENERIC, {"tokens_total": "forty-two"})
        assert result.data == {}
        assert result.violations[0].kind == ViolationKind.WRONG_TYPE

    def test_free_text_where_a_token_belongs(self) -> None:
        result = enforce_egress_schema("ASPDMA_RESULT", TraceLevel.GENERIC, {"selected_action": "speak to María now"})
        assert result.data == {}
        assert result.violations[0].kind == ViolationKind.WRONG_TYPE

    def test_bool_is_not_a_number(self) -> None:
        result = enforce_egress_schema("ACTION_RESULT", TraceLevel.GENERIC, {"execution_time_ms": True})
        assert result.data == {}

    def test_over_long_text_is_capped(self) -> None:
        result = enforce_egress_schema("DEFERRAL_ROUTED", TraceLevel.DETAILED, {"reason": "x" * 2000})
        assert result.data == {"reason": "x" * REASON_MAX_CHARS}
        assert result.violations[0].kind == ViolationKind.OVER_CAP

    def test_over_long_list_is_cut_and_bad_items_dropped(self) -> None:
        flags: List[Any] = [f"flag_{i}" for i in range(50)] + ["__messages__:" + "[" * 5000, 7]
        result = enforce_egress_schema("DMA_RESULTS", TraceLevel.DETAILED, {"csdma": {"flags": flags}})
        kept = result.data["csdma"]["flags"]  # type: ignore[index]
        assert len(kept) == egress_schema.LIST_MAX_ITEMS
        assert not any(str(f).startswith("__messages__") for f in kept)
        kinds = {v.kind for v in result.violations}
        assert kinds == {ViolationKind.WRONG_TYPE, ViolationKind.OVER_CAP}

    def test_url_with_credentials_is_dropped(self) -> None:
        result = enforce_egress_schema(
            "LLM_CALL", TraceLevel.DETAILED, {"base_url": "https://user:key@10.0.0.5:11434/v1?api_key=s"}
        )
        assert result.data == {}


class TestVerbSpecificData:
    """The #1245 path: free text inside an opaque, nested payload."""

    def _vsp(self, vsd: Dict[str, Any]) -> Dict[str, Any]:
        return {"verb": "defer", "original_action": "speak", "final_action": "defer", "verb_specific_data": vsd}

    def test_generic_defer_reason_does_not_survive(self) -> None:
        vsd = {"rights_basis": ["safety"], "primary_need_category": "crisis_support", "defer_reason": MARIA}
        result = enforce_egress_schema("VERB_SECOND_PASS_RESULT", TraceLevel.GENERIC, self._vsp(vsd))
        assert result.data["verb_specific_data"] == {  # type: ignore[comparison-overlap]
            "rights_basis": ["safety"],
            "primary_need_category": "crisis_support",
        }
        assert "María" not in repr(result.data)
        assert [(v.path, v.kind) for v in result.violations] == [
            ("verb_specific_data.defer_reason", ViolationKind.UNEXPECTED_FIELD)
        ]

    def test_generic_tool_params_do_not_survive(self) -> None:
        vsd = {"final_tool_name": "send_funds", "final_parameters": {"to": SECRET_PARAM}, "original_parameters": {}}
        result = enforce_egress_schema("VERB_SECOND_PASS_RESULT", TraceLevel.GENERIC, self._vsp(vsd))
        assert result.data["verb_specific_data"] == {"final_tool_name": "send_funds"}  # type: ignore[comparison-overlap]
        assert SECRET_PARAM not in repr(result.data)

    def test_detailed_tool_params_do_not_survive(self) -> None:
        vsd = {"final_tool_name": "send_funds", "final_parameters": {"to": SECRET_PARAM}}
        result = enforce_egress_schema("VERB_SECOND_PASS_RESULT", TraceLevel.DETAILED, self._vsp(vsd))
        assert SECRET_PARAM not in repr(result.data)

    def test_detailed_defer_reason_is_kept_but_bounded(self) -> None:
        vsd = {"defer_reason": MARIA + ("." * 1000)}
        result = enforce_egress_schema("VERB_SECOND_PASS_RESULT", TraceLevel.DETAILED, self._vsp(vsd))
        kept = result.data["verb_specific_data"]["defer_reason"]  # type: ignore[index]
        assert len(kept) == REASON_MAX_CHARS
        assert [v.kind for v in result.violations] == [ViolationKind.OVER_CAP]

    def test_detailed_does_not_carry_the_reasoning_chain(self) -> None:
        data = {**self._vsp({}), "original_reasoning": "long chain", "final_reasoning": "long chain"}
        result = enforce_egress_schema("VERB_SECOND_PASS_RESULT", TraceLevel.DETAILED, data)
        assert "original_reasoning" not in result.data and "final_reasoning" not in result.data


def test_channel_id_is_detailed_not_generic() -> None:
    channel = {"channel_id": "safety_battery_ani_a0_hooks_20260911T160525Z"}
    assert enforce_egress_schema("THOUGHT_START", TraceLevel.DETAILED, channel).data == channel
    assert enforce_egress_schema("THOUGHT_START", TraceLevel.GENERIC, channel).data == {}


def test_full_is_still_bounded() -> None:
    result = enforce_egress_schema("LLM_CALL", TraceLevel.FULL_TRACES, {"prompt": "p" * 70000})
    assert len(result.data["prompt"]) == egress_schema.FULL_TEXT_MAX_CHARS  # type: ignore[arg-type]
    deep: Dict[str, Any] = {}
    node = deep
    for _ in range(20):
        node["n"] = {}
        node = node["n"]
    result = enforce_egress_schema("ASPDMA_RESULT", TraceLevel.FULL_TRACES, {"action_parameters": deep})
    assert any(v.kind == ViolationKind.OVER_CAP for v in result.violations)


class TestReporting:
    def test_warns_once_per_finding_without_the_value(self, caplog: pytest.LogCaptureFixture) -> None:
        reporter = ViolationReporter()
        vsd = {"defer_reason": MARIA}
        for _ in range(5):
            result = enforce_egress_schema(
                "VERB_SECOND_PASS_RESULT", TraceLevel.GENERIC, {"verb": "defer", "verb_specific_data": vsd}
            )
            with caplog.at_level(logging.WARNING, logger=egress_schema.__name__):
                reporter.report(result.violations, "test")
        warnings = [r for r in caplog.records if "[TRACE-SCHEMA]" in r.getMessage()]
        assert len(warnings) == 1
        msg = warnings[0].getMessage()
        assert "VERB_SECOND_PASS_RESULT" in msg and "verb_specific_data.defer_reason" in msg
        assert "level=generic" in msg and "kind=unexpected_field" in msg and "PRODUCER" in msg
        assert "María" not in msg and "suicida" not in msg
        assert reporter.snapshot()["schema_violations_unexpected_field"] == 5

    def test_list_indices_fold_into_one_finding(self, caplog: pytest.LogCaptureFixture) -> None:
        reporter = ViolationReporter()
        result = enforce_egress_schema("DMA_RESULTS", TraceLevel.DETAILED, {"csdma": {"flags": [1, 2, 3]}})
        with caplog.at_level(logging.WARNING, logger=egress_schema.__name__):
            reporter.report(result.violations)
        assert len([r for r in caplog.records if "[TRACE-SCHEMA]" in r.getMessage()]) == 1


class _FakeLens:
    def __init__(self) -> None:
        self.components: List[Dict[str, Any]] = []

    def capture_event(self, component: Dict[str, Any]) -> Dict[str, Any]:
        self.components.append(component)
        return {"outcome": "opened"}


@pytest.mark.asyncio
async def test_the_service_filters_before_the_substrate_sees_it(caplog: pytest.LogCaptureFixture) -> None:
    """End to end through _process_single_event: the signer never receives the reason."""
    service = AccordMetricsService(config={"trace_level": "generic"})
    lens = _FakeLens()
    service._lens = lens
    event = {
        "event_type": "VERB_SECOND_PASS_RESULT",
        "thought_id": "th_followup_97c04efb",
        "verb": "defer",
        "original_action": "speak",
        "final_action": "defer",
        "original_reasoning": "chain",
        "verb_specific_data": {"rights_basis": ["safety"], "defer_reason": MARIA},
    }
    with caplog.at_level(logging.WARNING, logger=egress_schema.__name__):
        await service._process_single_event(event)
    shipped = lens.components[0]["data"]
    assert shipped["verb_specific_data"] == {"rights_basis": ["safety"]}
    assert "María" not in repr(lens.components)
    assert any("verb_specific_data.defer_reason" in r.getMessage() for r in caplog.records)
    assert service.get_metrics()["schema_violations_unexpected_field"] >= 1
