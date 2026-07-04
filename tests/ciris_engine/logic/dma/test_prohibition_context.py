"""Round-1 DMA prohibition-context injection (CIRISAgent#910).

The prohibited-capabilities list is surfaced in the system context of the
round-1 parallel DMAs (PDMA/CSDMA/DSDMA) — and ONLY those — so prohibited
trajectories are named in reasoning content before they reach the WiseBus gate.
The block is generated from PROHIBITED_CAPABILITIES at assembly time (single
source of truth) with a short, localizable what/why per category.
"""

from __future__ import annotations

import pathlib

from ciris_engine.logic.buses.prohibitions import (
    CATEGORY_GUIDANCE,
    PROHIBITED_CAPABILITIES,
    ProhibitionSeverity,
    get_prohibition_severity,
)
from ciris_engine.logic.utils.localization import get_prohibition_guidance

_DMA_DIR = pathlib.Path(__file__).resolve().parents[4] / "ciris_engine" / "logic" / "dma"


def test_every_gate_category_has_guidance() -> None:
    """Drift guard: the reasoning block can never silently drop a gate category."""
    missing = [c for c in PROHIBITED_CAPABILITIES if c not in CATEGORY_GUIDANCE]
    assert missing == [], f"PROHIBITED_CAPABILITIES categories without CATEGORY_GUIDANCE: {missing}"


def test_block_covers_every_category_and_severity() -> None:
    block = get_prohibition_guidance("en")
    # every category's what/why is present
    for category, desc in CATEGORY_GUIDANCE.items():
        assert desc in block, f"{category} description missing from block"
    # both severity tiers rendered
    assert "Never permitted" in block
    assert "separate licensed" in block
    # never-allowed items land in the NEVER section (order: header, never, module)
    never_section = block.split("Never permitted")[1].split("Only via")[0]
    for category in PROHIBITED_CAPABILITIES:
        if get_prohibition_severity(category) == ProhibitionSeverity.NEVER_ALLOWED:
            assert CATEGORY_GUIDANCE[category] in never_section


def test_new_category_without_description_still_surfaces(monkeypatch) -> None:
    """A gate category with no description must not vanish — generic fallback."""
    import ciris_engine.logic.buses.prohibitions as P

    patched = dict(P.PROHIBITED_CAPABILITIES)
    patched["FUTURE_UNKNOWN"] = {"some_cap"}
    monkeypatch.setattr(P, "PROHIBITED_CAPABILITIES", patched)
    block = get_prohibition_guidance("en")
    assert "Outside this agent's scope." in block


def test_localized_override_is_used(monkeypatch) -> None:
    """A {lang}.json prompts.prohibitions.<CATEGORY> override replaces the English base."""
    import ciris_engine.logic.utils.localization as L

    real = L.get_string

    def fake(lang, key, default=""):
        if key == "prompts.prohibitions.MEDICAL":
            return "LOCALIZED-MEDICAL-WHY"
        return real(lang, key, default=default)

    monkeypatch.setattr(L, "get_string", fake)
    block = get_prohibition_guidance("xx")
    assert "LOCALIZED-MEDICAL-WHY" in block
    assert CATEGORY_GUIDANCE["MEDICAL"] not in block  # English base overridden


def test_round1_dmas_inject_but_aspdma_does_not() -> None:
    """Round-1 DMAs inject the block via the shared helper; ASPDMA must not (#910).

    The accord + language-guidance + prohibition append is centralized in
    formatters.append_round1_accord_blocks (de-duplicated). Round-1 DMAs call it;
    the prohibition injection lives inside it; ASPDMA/recursive passes deliberately
    do NOT call it (they keep accord + language guidance, no prohibitions).
    """
    helper_src = (_DMA_DIR.parent / "formatters" / "prompt_blocks.py").read_text()
    assert "get_prohibition_guidance" in helper_src, "helper must inject the prohibition block"

    for fn in ("pdma.py", "csdma.py", "dsdma_base.py"):
        src = (_DMA_DIR / fn).read_text()
        assert "append_round1_accord_blocks" in src, f"round-1 {fn} should call the round-1 helper"
    for fn in ("dsaspdma.py", "tsaspdma.py"):
        src = (_DMA_DIR / fn).read_text()
        assert "append_round1_accord_blocks" not in src, f"ASPDMA {fn} must NOT use the round-1 helper"
        assert "get_prohibition_guidance" not in src, f"ASPDMA {fn} must NOT inject prohibitions"
