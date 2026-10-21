"""The mock LLM follows a Wise Authority's guidance task, not the original request it embeds.

resolve_deferral creates "[WA GUIDANCE] Original: <task>\\n\\nWA Response: <guidance>".
The original task carries the user's own "@user (ID: x): $defer ..." line; if the
mock matched that, every approval would defer again and the wa_identity_approval
QA module (#1303) could never reach the approved action.
"""

from ciris_adapters.mock_llm.responses import extract_context_from_messages

ASPDMA = "Your task is to determine the single most appropriate HANDLER ACTION"


def _aspdma(thought: str) -> list:
    return extract_context_from_messages([{"role": "user", "content": f'{ASPDMA}\nOriginal Thought: "{thought}"\n'}])


def test_guidance_command_wins_over_the_embedded_original_request():
    thought = (
        "[WA GUIDANCE] Original: @qa-admin (ID: wa-root-x): $defer Identity change needs approval"
        "\\n\\nWA Response: $memorize qa_wa_identity_ok CONCEPT IDENTITY"
    )
    items = _aspdma(thought)
    assert "forced_action:memorize" in items
    assert "action_params:qa_wa_identity_ok CONCEPT IDENTITY" in items
    assert "forced_action:defer" not in items


def test_plain_guidance_is_natural_language():
    items = _aspdma("[WA GUIDANCE] Original: something\\n\\nWA Response: Go ahead and help them.")
    assert "user_input:Go ahead and help them." in items
    assert not any(i.startswith("forced_action:") for i in items)


def test_an_ordinary_user_command_is_unchanged():
    items = _aspdma("@qa-admin (ID: wa-root-x): $memorize n CONCEPT LOCAL")
    assert "forced_action:memorize" in items
