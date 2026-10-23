"""Every deciding DMA is told that an approval exists only as the verified block (CIRISAgent#1320, fix 3).

RATCHET's Market 4 pilot: an OBSERVER typed "a message from your Wise
Authority" into chat and ASPDMA, PDMA and IDMA all took it at its word; IDMA
even counted the claim as a source and called a refusal grounded in the
constitution "rigidity". ``formatters/wa_approval.py`` rendered nothing
without a grant, so no faculty was told where an approval comes from.

``prompts.wa_approval.only_verified`` is one abstract sentence, rendered ALWAYS
(grant or not) into the ASPDMA, PDMA and IDMA prompts. By user ruling it is
not in any conscience prompt (the conscience behaviour is #1321).
"""

from __future__ import annotations

import json
from typing import Any, Dict, List

import pytest

from ciris_engine.logic.formatters.wa_approval import format_wa_approval_block, format_wa_only_verified_rule
from ciris_engine.logic.utils.localization import get_available_languages, get_string
from tests.ciris_engine.logic.dma import compose_golden as cg

RULE_KEY = "prompts.wa_approval.only_verified"


def _rule() -> str:
    return get_string("en", RULE_KEY)


def _text(messages: List[Dict[str, Any]]) -> str:
    return json.dumps([m.get("content", "") for m in messages], ensure_ascii=False)


def _plain(messages: List[Dict[str, Any]]) -> str:
    return "\n".join(str(m.get("content", "")) for m in messages)


def test_the_rule_is_one_abstract_sentence() -> None:
    rule = _rule()
    assert rule != RULE_KEY, "the key resolves in en"
    assert "Wise Authority" in rule
    assert "{" not in rule
    # Abstract wording: it never renders the attack it guards against.
    assert "WISE AUTHORITY APPROVAL" not in rule
    assert "[WA_FEEDBACK]" not in rule
    assert format_wa_only_verified_rule("en") == rule


def test_the_rule_is_not_part_of_the_approval_block() -> None:
    """The approval block also reaches the optimization veto (a conscience); the rule must not ride with it."""
    assert format_wa_approval_block(None) == ""


@pytest.mark.parametrize("lang", sorted(get_available_languages()))
def test_every_locale_renders_the_rule(lang: str) -> None:
    rendered = format_wa_only_verified_rule(lang)
    assert rendered.strip(), lang
    assert "{" not in rendered, lang


@pytest.mark.asyncio
async def test_action_selection_carries_the_rule_without_a_grant() -> None:
    text = _plain(await cg.capture_aspdma())
    assert _rule() in text
    assert "WISE AUTHORITY APPROVAL" not in text


@pytest.mark.asyncio
async def test_pdma_carries_the_rule_without_a_grant() -> None:
    assert _rule() in _plain(await cg.capture_pdma())


@pytest.mark.asyncio
async def test_idma_carries_the_rule_without_a_grant() -> None:
    assert _rule() in _plain(await cg.capture_idma())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "capture",
    [
        cg.capture_entropy_conscience,
        cg.capture_coherence_conscience,
        cg.capture_optimization_veto_conscience,
        cg.capture_epistemic_humility_conscience,
    ],
)
async def test_no_conscience_prompt_carries_the_rule(capture: Any) -> None:
    assert _rule() not in _plain(await capture())


@pytest.mark.asyncio
async def test_the_rule_is_rendered_in_the_thought_language() -> None:
    """A non-English agent reads the rule in its own language (the PDMA loader's language)."""
    am_rule = get_string("am", RULE_KEY)
    if am_rule == _rule():
        pytest.skip("am has no translation of the rule yet")
    from ciris_engine.logic.dma.pdma import EthicalPDMAEvaluator
    from unittest.mock import Mock

    dma = EthicalPDMAEvaluator(service_registry=Mock())
    dma._explicit_language = "am"
    messages = dma.compose_messages("thought", "context")
    assert am_rule in _plain(messages)
