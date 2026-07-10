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
    """A {lang}.json prompts.prohibitions.<CATEGORY> override is used verbatim, and
    the block is looked up in the target language ONLY (no English fallback leak)."""
    import ciris_engine.logic.utils.localization as L

    # The block resolves against the language's OWN bundle (no cross-language
    # English fallback). Simulate a language 'xx' whose bundle localizes only
    # MEDICAL — the localized value must appear, and the un-localized categories
    # must be omitted (not English-filled), so no English base leaks in.
    monkeypatch.setattr(
        L,
        "_get_language_data",
        lambda lang: {"prompts": {"prohibitions": {"MEDICAL": "LOCALIZED-MEDICAL-WHY"}}},
    )
    block = get_prohibition_guidance("xx")
    assert "LOCALIZED-MEDICAL-WHY" in block
    assert CATEGORY_GUIDANCE["MEDICAL"] not in block  # English base overridden
    # No English fallback for the other (un-localized) categories on a non-en lang.
    assert CATEGORY_GUIDANCE["FINANCIAL"] not in block


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


# --- CI-red guard: every supported language must FULLY localize the block -----
#
# CIRISAgent#916 / the #912 regression: an un-localized prompts.prohibitions.*
# key used to fall back to English and silently pollute a non-English DMA prompt
# (Staged QA all_1 caught it at runtime, but only for `am`). These tests make an
# incomplete or English-leaking prohibition localization a HARD CI FAILURE for
# EVERY supported language — so this class of gap can never ship silently again.
#
# The key-parity half is already enforced by test_localization_completeness
# (adding prompts.prohibitions.* to en.json requires every {lang}.json to carry
# them). These add the SEMANTIC half: the rendered block must contain all
# categories and must not be English for a non-English language.
import json as _json
from pathlib import Path as _Path

_LOCALIZED_DIR = _Path(__file__).resolve().parents[4] / "ciris_engine" / "data" / "localized"


def _supported_languages() -> list[str]:
    manifest = _json.loads((_LOCALIZED_DIR / "manifest.json").read_text(encoding="utf-8"))
    return sorted(manifest.get("languages", {}).keys())


# Latin-script languages can't be script-checked; parity + non-identity still apply.
_NON_LATIN_SCRIPT = {
    "am": "ሀ-፿", "ar": "؀-ۿ", "bn": "ঀ-৿",
    "fa": "؀-ۿ", "hi": "ऀ-ॿ", "ja": "぀-ヿ一-鿿",
    "ko": "가-힯", "mr": "ऀ-ॿ", "my": "က-႟",
    "pa": "਀-੿", "ru": "Ѐ-ӿ", "ta": "஀-௿",
    "te": "ఀ-౿", "th": "฀-๿", "uk": "Ѐ-ӿ",
    "ur": "؀-ۿ", "zh": "一-鿿",
}


def test_prohibition_block_fully_localized_every_language() -> None:
    """Each supported language must render ALL categories — none omitted for a
    missing translation (the #912 omit-path must never trigger in shipped code)."""
    import re

    expected = len(PROHIBITED_CAPABILITIES)
    en_block = get_prohibition_guidance("en")
    failures: list[str] = []
    for lang in _supported_languages():
        block = get_prohibition_guidance(lang)
        if not block.strip():
            failures.append(f"{lang}: prohibition block EMPTY (no prompts.prohibitions.* localized)")
            continue
        n = len([ln for ln in block.splitlines() if ln.startswith("- ")])
        if n != expected:
            failures.append(f"{lang}: {n}/{expected} categories rendered — un-localized categories omitted")
        if lang != "en":
            if block == en_block:
                failures.append(f"{lang}: block byte-identical to English (not translated)")
            script = _NON_LATIN_SCRIPT.get(lang)
            if script and not re.search(f"[{script}]", block):
                failures.append(f"{lang}: no {lang}-script characters in block (English placeholder?)")
    assert not failures, "prohibition localization incomplete:\n  " + "\n  ".join(failures)
