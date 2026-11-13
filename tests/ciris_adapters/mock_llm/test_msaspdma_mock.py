"""The mock LLM answers MSASPDMA (the memorize second pass) instead of crashing it.

It had no handler for MSASPDMALLMResult, so every mock MEMORIZE logged
"MSASPDMA: Failed ... no attribute 'final_action'" and the QA incidents gate
failed runs whose tests all passed (run 39664086947, 38/38).
"""

import yaml

from ciris_adapters.mock_llm.responses import create_response
from ciris_adapters.mock_llm.responses_action_selection import _with_mock_params
from ciris_engine.logic.dma.dsaspdma import DSASPDMALLMResult
from ciris_engine.logic.dma.fsaspdma import FSASPDMALLMResult
from ciris_engine.logic.dma.msaspdma import MSASPDMALLMResult
from ciris_engine.logic.dma.rsaspdma import RSASPDMALLMResult


def _prompt(thought: str, node_type: str, scope: str) -> list:
    """The memorize second-pass prompt as the engine composes it after #1027.

    Action selection names no node, so the proposal lines carry a placeholder;
    what the mock action selection parsed from ``$memorize`` rides in its
    reasoning (``_with_mock_params``), which the prompt quotes.
    """
    template = yaml.safe_load(open("ciris_engine/logic/dma/prompts/msaspdma.yml"))["context_integration"]
    user = template.format(
        original_thought_content=thought,
        aspdma_reasoning=_with_mock_params(
            "[MOCK LLM] Memorizing", {"node_type": node_type, "scope": scope, "content": "from_action_selection"}
        ),
        proposed_node_id="(not chosen yet — choose below)",
        proposed_node_type="(not chosen yet — choose below)",
        proposed_node_scope=scope,
        proposed_attributes="(none)",
        candidate_nodes="(none)",
        system_owned_attributes="(none)",
    )
    return [{"role": "system", "content": "memorize second pass"}, {"role": "user", "content": user}]


def test_addresses_the_requested_memorize_with_the_same_content():
    messages = _prompt("@qa (ID: wa-root-x): $memorize qa_wa_identity_ok CONCEPT IDENTITY", "concept", "identity")
    result = create_response(MSASPDMALLMResult, messages=messages)
    assert isinstance(result, MSASPDMALLMResult)
    assert result.final_action == "MEMORIZE"
    assert result.node_id and "not chosen" not in result.node_id
    assert (result.node_type, result.node_scope) == ("concept", "identity")
    # An IDENTITY write comes back without `content`, the way a live second pass
    # names its attributes (RATCHET run 39788730490), so wa_identity_approval
    # exercises that shape; the text is the same the action-selection pass stored.
    assert result.attributes == {"created_by": "agent", "statement": "qa_wa_identity_ok_concept_identity"}


def test_other_scopes_keep_content_for_the_memory_modules():
    messages = _prompt("@qa: $memorize qa_local_fact CONCEPT LOCAL", "concept", "local")
    result = create_response(MSASPDMALLMResult, messages=messages)
    assert result.attributes == {"created_by": "agent", "content": "qa_local_fact_concept_local"}


def test_an_unreadable_prompt_ponders_rather_than_writes():
    result = create_response(MSASPDMALLMResult, messages=[{"role": "user", "content": "nothing useful"}])
    assert result.final_action == "PONDER"


def _second_pass_prompt(reasoning: str) -> list:
    return [
        {"role": "user", "content": f"Original thought:\nx\n\nYour reasoning:\n{reasoning}\n\n=== CANDIDATE NODES ==="}
    ]


def test_the_mock_action_selection_hands_recall_and_forget_to_their_second_passes():
    """End to end through the mock: `$recall` / `$forget` survive ASPDMA carrying no fields."""
    recall = create_response(
        RSASPDMALLMResult,
        messages=_second_pass_prompt(_with_mock_params("[MOCK LLM] Recalling", {"query": "qa_fact", "limit": 5})),
    )
    assert (recall.final_action, recall.query, recall.limit) == ("RECALL", "qa_fact", 5)

    forget = create_response(
        FSASPDMALLMResult,
        messages=_second_pass_prompt(
            _with_mock_params("[MOCK LLM] Forgetting", {"node_id": "qa_node", "scope": "local", "reason": "cleanup"})
        ),
    )
    assert (forget.final_action, forget.node_id, forget.reason) == ("FORGET", "qa_node", "cleanup")


def test_recall_and_forget_ponder_when_nothing_was_handed_over():
    assert create_response(RSASPDMALLMResult, messages=_second_pass_prompt("no payload")).final_action == "PONDER"
    assert create_response(FSASPDMALLMResult, messages=_second_pass_prompt("no payload")).final_action == "PONDER"


def test_a_timed_deferral_reaches_the_defer_second_pass():
    """`$defer +30s` used to travel in ASPDMA's defer_until field; DSASPDMA sets it now."""
    template = yaml.safe_load(open("ciris_engine/logic/dma/prompts/dsaspdma.yml"))["context_integration"]
    reasoning = _with_mock_params(
        "[MOCK LLM] Deferring: needs review", {"reason": "needs review", "defer_until": "2030-01-01T00:00:00+00:00"}
    )
    user = template.format(
        original_thought_content="$defer +30s needs review",
        aspdma_reasoning=reasoning,
        current_reason=reasoning,
        current_context="(none)",
        current_defer_until="none",
        current_domain_hint="none",
        taxonomy_text="",
        domain_hint_options="",
    )
    result = create_response(DSASPDMALLMResult, messages=[{"role": "user", "content": user}])
    assert result.reason_summary == "needs review"
    assert result.defer_until == "2030-01-01T00:00:00+00:00"
