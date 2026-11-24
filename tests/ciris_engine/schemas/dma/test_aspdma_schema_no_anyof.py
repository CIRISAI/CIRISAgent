"""Unit tests for union-free ASPDMALLMResult JSON schema (CIRISAgent#893)."""

from __future__ import annotations

from typing import Any

import pytest

from ciris_engine.schemas.dma.results import ASPDMALLMResult, convert_llm_result_to_action_result
from ciris_engine.schemas.runtime.enums import HandlerActionType


def _contains_key(obj: Any, target: str) -> bool:
    if isinstance(obj, dict):
        if target in obj:
            return True
        return any(_contains_key(v, target) for v in obj.values())
    if isinstance(obj, list):
        return any(_contains_key(item, target) for item in obj)
    return False


class TestASPDMALLMResultNoAnyOf:
    def test_json_schema_has_zero_anyof(self) -> None:
        schema = ASPDMALLMResult.model_json_schema()
        assert not _contains_key(schema, "anyOf"), f"Found anyOf in ASPDMALLMResult schema: {schema}"

    def test_explicit_null_fields_coerce_to_empty_defaults(self) -> None:
        res = ASPDMALLMResult.model_validate(
            {
                "selected_action": "speak",
                "reasoning": "Greeting the user.",
                "speak_content": None,
                "ponder_questions": None,
                "reject_reason": None,
                "tool_name": None,
                "memorize_scope": None,
                "completion_reason": None,
            }
        )
        assert res.speak_content == ""
        assert res.ponder_questions == []
        assert res.reject_reason == ""
        assert res.tool_name == ""
        assert res.memorize_scope == ""
        assert res.completion_reason == ""

    @pytest.mark.parametrize("action", list(HandlerActionType))
    def test_all_ten_actions_convert_cleanly(self, action: HandlerActionType) -> None:
        llm_result = ASPDMALLMResult(
            selected_action=action,
            reasoning="Test reasoning.",
            speak_content="hello" if action == HandlerActionType.SPEAK else "",
            ponder_questions=["q1"] if action == HandlerActionType.PONDER else [],
            reject_reason="nope" if action == HandlerActionType.REJECT else "",
            tool_name="lookup" if action == HandlerActionType.TOOL else "",
            memorize_scope="local" if action == HandlerActionType.MEMORIZE else "",
            completion_reason="done" if action == HandlerActionType.TASK_COMPLETE else "",
        )
        converted = convert_llm_result_to_action_result(llm_result, channel_id="api_123")
        assert converted.selected_action == action
        assert converted.rationale == "Test reasoning."
