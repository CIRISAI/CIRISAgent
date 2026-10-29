"""The crisis block is part of the standard system prompt at every DMA (#1248).

Production, 2026-08-30 (WhatsApp, Ethiopia): a user asking for mental-health
help was given "907 00 00 00" — 907 is the curated Ethiopia AMBULANCE number,
padded into a fake helpline. Before #1248 the curated crisis block reached only
DSDMA, and only for an identity template carrying a ``{crisis_resources_block}``
slot: ASPDMA, which writes the user-facing SPEAK text, never saw it.

User ruling (Eric): crisis blocks load into context as part of the standard
system prompt, like language guidance. So at every site that carries language
guidance, the locale's crisis block is the system message directly after it —
once, from one composer, from the locale's OWN corpus registry.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pytest

from ciris_engine.logic.formatters.crisis_resources import get_crisis_resources_system_block
from ciris_engine.schemas.resources.crisis import load_crisis_registry
from tests.ciris_engine.logic.dma import compose_golden as cg

#: Every composition step that carries per-language guidance (and so must carry
#: the crisis block right after it). The conscience faculties carry neither.
LANGUAGE_GUIDANCE_STEPS = (
    "pdma",
    "csdma",
    "idma",
    "dsdma",
    "aspdma",
    "dsaspdma",
    "msaspdma",
    "tsaspdma",
    "tsaspdma_correction",
    "aspdma_retry",
    "csdma_bounce",
)

CRISIS_HEADER = "=== Crisis Resources ==="


@pytest.fixture(autouse=True)
def _no_location(monkeypatch: pytest.MonkeyPatch) -> None:
    # The system block reads the opted-in location from the environment; pin it
    # off so these assertions are about the language path.
    for key in ("CIRIS_USER_COUNTRY", "CIRIS_USER_LOCATION"):
        monkeypatch.delenv(key, raising=False)


def _locale_environment(lang: str) -> Any:
    # Sentinel accord / guidance, REAL crisis composer (no crisis_resources
    # sentinel), so the composed bytes are the corpus block itself.
    return cg.prompt_content_environment(
        language=lang,
        accord=cg._sentinel_accord,
        localized_accord=cg._sentinel_localized_accord,
        language_guidance=cg._sentinel_language_guidance,
        prohibition_guidance=cg._sentinel_prohibition_guidance,
    )


async def _compose(step: str, lang: str) -> List[Dict[str, Any]]:
    with _locale_environment(lang):
        return await cg.capture_step(step)  # type: ignore[no-any-return]


def _crisis_positions(messages: List[Dict[str, Any]]) -> List[int]:
    return [i for i, m in enumerate(messages) if CRISIS_HEADER in str(m.get("content", ""))]


@pytest.mark.parametrize("lang", ["en", "am", "es"])
@pytest.mark.parametrize("step", LANGUAGE_GUIDANCE_STEPS)
@pytest.mark.asyncio
async def test_crisis_block_follows_language_guidance_exactly_once(step: str, lang: str) -> None:
    messages = await _compose(step, lang)
    positions = _crisis_positions(messages)
    # Exactly once: DSDMA's legacy in-template injection must not double it.
    assert len(positions) == 1, f"{step}/{lang}: crisis block appears {len(positions)} times"
    i = positions[0]
    assert messages[i] == {"role": "system", "content": get_crisis_resources_system_block(lang)}, (
        f"{step}/{lang}: crisis block is not its own system message from the shared composer"
    )
    assert str(messages[i - 1].get("content", "")).startswith("<GOLDEN-LANGUAGE-GUIDANCE"), (
        f"{step}/{lang}: crisis block is not directly after language guidance"
    )


@pytest.mark.parametrize("lang", ["en", "am"])
@pytest.mark.asyncio
async def test_aspdma_composed_messages_carry_the_locale_crisis_block(lang: str) -> None:
    """The SPEAK-writing DMA sees the curated numbers (the #1248 root cause)."""
    messages = await _compose("aspdma", lang)
    system_text = "\n".join(str(m["content"]) for m in messages if m["role"] == "system")
    assert CRISIS_HEADER in system_text
    if lang == "am":
        assert "[Ethiopia]" in system_text and "Phone: 907" in system_text
        assert "NOT mental-health or crisis helplines" in system_text
        assert "Call the emergency number listed above for your country" in system_text
    else:
        assert "Call 911 or local emergency services" in system_text


def _locales() -> List[str]:
    from ciris_engine.logic.utils.localization import get_available_languages

    return sorted(lang for lang in get_available_languages() if len(lang) == 2)


@pytest.mark.parametrize("lang", [l for l in _locales() if l != "en"])
def test_no_locale_gets_the_english_block_substituted(lang: str) -> None:
    """A supported locale is served its OWN registry, never en's (US 911 / 988)."""
    assert load_crisis_registry(lang).locale == lang
    block = get_crisis_resources_system_block(lang)
    assert block != get_crisis_resources_system_block("en"), f"{lang}: received the en crisis block"
    # en-only US helplines never leak into another locale's block.
    for marker in ("988", "741741", "Crisis Text Line", "Samaritans"):
        assert marker not in block, f"{lang}: en-only {marker} in a non-en block"


@pytest.mark.parametrize("lang", ["am", "es"])
@pytest.mark.asyncio
async def test_aspdma_composes_the_locale_block_not_en(lang: str) -> None:
    messages = await _compose("aspdma", lang)
    contents = [m["content"] for m in messages]
    assert get_crisis_resources_system_block(lang) in contents
    assert get_crisis_resources_system_block("en") not in contents


def test_dsdma_template_slot_renders_a_number_free_pointer() -> None:
    from ciris_engine.logic.dma.dsdma_base import DSDMA_CRISIS_BLOCK_POINTER

    assert CRISIS_HEADER in DSDMA_CRISIS_BLOCK_POINTER  # names the block it points to
    assert not any(ch.isdigit() for ch in DSDMA_CRISIS_BLOCK_POINTER)


@pytest.mark.asyncio
async def test_aspdma_location_country_first(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opted-in location reaches the SPEAK-writing DMA: a Spanish speaker in Germany."""
    monkeypatch.setenv("CIRIS_USER_COUNTRY", "DE")
    messages = await _compose("aspdma", "es")
    block = next(m["content"] for m in messages if CRISIS_HEADER in str(m["content"]))
    first = next(l for l in block.splitlines() if l.startswith("• ["))
    assert first.startswith("• [Germany — your location]")


@pytest.mark.parametrize("lang", ["en", "am"])
@pytest.mark.asyncio
async def test_dsdma_template_slot_does_not_double_the_block(lang: str) -> None:
    """An identity template with the legacy ``{crisis_resources_block}`` slot (echo-speculative)
    still gets the block exactly ONCE — as the system message, not also in the template."""
    from unittest.mock import AsyncMock, Mock

    from ciris_engine.logic.dma.dsdma_base import BaseDSDMA

    template = "Domain {domain_name}.\nFor Mental Health Concerns:\n{crisis_resources_block}\n"
    with _locale_environment(lang):
        dma = BaseDSDMA(
            domain_name="golden_domain",
            service_registry=Mock(),
            domain_specific_knowledge={"rules_summary": "r"},
            prompt_template=template,
        )
        dma.fetch_original_task = AsyncMock(return_value=cg.make_task())  # type: ignore[method-assign]
        captured: Dict[str, Any] = {}
        dma.call_llm_structured = cg._recording_llm(captured, cg.make_dsdma_result())  # type: ignore[method-assign]
        await dma.evaluate(cg.make_dsdma_queue_item())
    messages = captured["messages"]
    # The slot renders the number-free pointer (which names the header); the
    # block's CONTENT appears once.
    system_text = "\n".join(str(m["content"]) for m in messages if m["role"] == "system")
    assert system_text.count("Find a Helpline") == 1
