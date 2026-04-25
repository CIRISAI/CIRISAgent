"""Targeted tests for helper functions in the mock LLM action-selection adapter."""

from ciris_adapters.mock_llm.responses_action_selection import (
    _extract_music_play_request,
    _infer_dsaspdma_result,
    _parse_key_value_tokens,
    _parse_tool_params_string,
)
from ciris_engine.schemas.services.agent_credits import DomainCategory
from ciris_engine.schemas.services.deferral_taxonomy import (
    DeferralNeedCategory,
    DeferralOperationalReason,
)


def test_infer_dsaspdma_result_detects_licensed_domain() -> None:
    result = _infer_dsaspdma_result(
        prompt_text="The user is asking for legal advice about a contract dispute.",
        current_reason="",
    )

    assert result.domain_hint == DomainCategory.LEGAL
    assert result.primary_need_category == DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY
    assert result.operational_reason == DeferralOperationalReason.LICENSED_DOMAIN_REQUIRED
    assert "licensed legal review" in result.reason_summary.lower()


def test_infer_dsaspdma_result_uses_general_operational_reason() -> None:
    result = _infer_dsaspdma_result(
        prompt_text="The request is ambiguous and there is insufficient context to proceed safely.",
        current_reason="",
    )

    assert result.domain_hint is None
    assert result.primary_need_category == DeferralNeedCategory.GENERAL_HUMAN_OVERSIGHT
    assert result.operational_reason == DeferralOperationalReason.INSUFFICIENT_CONTEXT
    assert "more context is required" in result.reason_summary.lower()


def test_infer_dsaspdma_result_collects_secondary_need_categories() -> None:
    result = _infer_dsaspdma_result(
        prompt_text="There are legal, financial debt, privacy, and surveillance implications here.",
        current_reason="Need review.",
    )

    assert result.primary_need_category == DeferralNeedCategory.JUSTICE_AND_LEGAL_AGENCY
    assert result.secondary_need_categories == [
        DeferralNeedCategory.LIVELIHOOD_AND_FINANCIAL_SECURITY,
        DeferralNeedCategory.PRIVACY_AUTONOMY_AND_DIGNITY,
    ]
    assert result.reason_summary == "Need review."


def test_extract_music_play_request_strips_media_prefixes() -> None:
    result = _extract_music_play_request("Please play the song Dreams by Fleetwood Mac in the bedroom")

    assert result is not None
    assert result["media_id"] == "Dreams Fleetwood Mac"
    assert result["media_type"] == "track"


def test_parse_tool_params_string_accepts_json_object() -> None:
    assert _parse_tool_params_string('{"path": "/tmp/test.txt", "mode": "read"}') == {
        "path": "/tmp/test.txt",
        "mode": "read",
    }


def test_parse_tool_params_string_accepts_shell_style_pairs() -> None:
    assert _parse_tool_params_string('path="/tmp/test file.txt" mode=read retries=2') == {
        "path": "/tmp/test file.txt",
        "mode": "read",
        "retries": "2",
    }


def test_parse_key_value_tokens_ignores_non_pairs() -> None:
    assert _parse_key_value_tokens('justtext mode=read flag') == {"mode": "read"}
