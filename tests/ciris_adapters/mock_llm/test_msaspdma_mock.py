"""The mock LLM answers MSASPDMA (the memorize second pass) instead of crashing it.

It had no handler for MSASPDMALLMResult, so every mock MEMORIZE logged
"MSASPDMA: Failed ... no attribute 'final_action'" and the QA incidents gate
failed runs whose tests all passed (run 39664086947, 38/38).
"""

import yaml

from ciris_adapters.mock_llm.responses import create_response
from ciris_engine.logic.dma.msaspdma import MSASPDMALLMResult


def _prompt(thought: str, node_id: str, node_type: str, scope: str) -> list:
    template = yaml.safe_load(open("ciris_engine/logic/dma/prompts/msaspdma.yml"))["context_integration"]
    user = template.format(
        original_thought_content=thought,
        aspdma_reasoning="[MOCK LLM] Memorizing",
        proposed_node_id=node_id,
        proposed_node_type=node_type,
        proposed_node_scope=scope,
        proposed_attributes="(none)",
        candidate_nodes="(none)",
        system_owned_attributes="(none)",
    )
    return [{"role": "system", "content": "memorize second pass"}, {"role": "user", "content": user}]


def test_affirms_the_proposed_node_with_the_same_content():
    messages = _prompt(
        "@qa (ID: wa-root-x): $memorize qa_wa_identity_ok CONCEPT IDENTITY",
        "19b2535b-f92b-436b-86eb-2ee2fda88f08",
        "concept",
        "identity",
    )
    result = create_response(MSASPDMALLMResult, messages=messages)
    assert isinstance(result, MSASPDMALLMResult)
    assert result.final_action == "MEMORIZE"
    assert result.node_id == "19b2535b-f92b-436b-86eb-2ee2fda88f08"
    assert (result.node_type, result.node_scope) == ("concept", "identity")
    # An IDENTITY write comes back without `content`, the way a live second pass
    # names its attributes (RATCHET run 39788730490), so wa_identity_approval
    # exercises that shape; the text is the same the action-selection pass stored.
    assert result.attributes == {"created_by": "agent", "statement": "qa_wa_identity_ok_concept_identity"}


def test_other_scopes_keep_content_for_the_memory_modules():
    messages = _prompt("@qa: $memorize qa_local_fact CONCEPT LOCAL", "n-local", "concept", "local")
    result = create_response(MSASPDMALLMResult, messages=messages)
    assert result.attributes == {"created_by": "agent", "content": "qa_local_fact_concept_local"}


def test_an_unreadable_prompt_ponders_rather_than_writes():
    result = create_response(MSASPDMALLMResult, messages=[{"role": "user", "content": "nothing useful"}])
    assert result.final_action == "PONDER"
