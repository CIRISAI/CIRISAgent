"""Round-1 DMA prohibition-context injection (CIRISAgent#910).

The prohibited-capabilities list is surfaced in the system context of the
round-1 parallel DMAs (PDMA/CSDMA/DSDMA) — and ONLY those — so prohibited
trajectories are named in reasoning content before they reach the WiseBus gate.
The block is generated from PROHIBITED_CAPABILITIES at assembly time (single
source of truth) with a short, localizable what/why per category.
"""

from __future__ import annotations

import pathlib

import pytest

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


# --- #910 test plan, part 1 (behavioral half): the block is ON THE WIRE -------
#
# test_round1_dmas_inject_but_aspdma_does_not (above) proves the call-graph at
# the source level; this proves the BEHAVIOR — the round-1 helper actually
# appends the generated prohibition block as a system message in the message
# list the DMAs ship to the LLM.


def test_round1_helper_appends_prohibition_block_to_wire_messages() -> None:
    from ciris_engine.logic.buses.prohibitions import PROHIBITION_HEADER_EN, PROHIBITION_TIER_NEVER_EN
    from ciris_engine.logic.formatters.prompt_blocks import append_round1_accord_blocks

    messages: list[dict[str, str]] = []
    append_round1_accord_blocks(messages, language="en", accord_mode="default")

    assert messages, "round-1 helper appended nothing"
    assert all(m["role"] == "system" for m in messages)
    prohibition_msgs = [m for m in messages if PROHIBITION_HEADER_EN in m["content"]]
    assert len(prohibition_msgs) == 1, "exactly one system message must carry the prohibition block"
    block = prohibition_msgs[0]["content"]
    assert PROHIBITION_TIER_NEVER_EN in block
    # The wire block is the same generated-at-assembly-time block (single source).
    assert get_prohibition_guidance("en") in block


# --- #910 test plan, part 3: flow-forward into ASPDMA context ----------------
#
# A prohibition-trending thought gets its category NAMED in a round-1 DMA
# output field (PDMA rationale; CSDMA/DSDMA flags + reasoning), and those exact
# fields are plumbed into ASPDMA's context by the context builder — so the
# category reaches ASPDMA in reasoning content WITHOUT the block being restated
# there. Mock-LLM level per the issue: we assert on the plumbing (what ASPDMA's
# LLM call actually receives), not on live model output.


@pytest.mark.asyncio
async def test_prohibition_category_flows_forward_into_aspdma_context() -> None:
    from datetime import datetime, timezone
    from unittest.mock import AsyncMock, Mock

    from ciris_engine.logic.buses.prohibitions import PROHIBITION_HEADER_EN, PROHIBITION_TIER_NEVER_EN
    from ciris_engine.logic.dma.action_selection_pdma import ActionSelectionPDMAEvaluator
    from ciris_engine.schemas.dma.faculty import EnhancedDMAInputs
    from ciris_engine.schemas.dma.results import ASPDMALLMResult, CSDMAResult, DSDMAResult, EthicalDMAResult
    from ciris_engine.schemas.runtime.enums import HandlerActionType, ThoughtStatus, ThoughtType
    from ciris_engine.schemas.runtime.models import Thought, ThoughtContext
    from ciris_engine.schemas.runtime.system_context import SystemSnapshot

    registry = Mock()
    registry.get_services_by_type.return_value = []

    thought = Thought(
        thought_id="prohib-thought-1",
        source_task_id="prohib-task-1",
        content="User asks which neighborhoods to exclude from loan offers",
        status=ThoughtStatus.PROCESSING,
        thought_type=ThoughtType.STANDARD,
        thought_depth=1,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        context=ThoughtContext(task_id="prohib-task-1", round_number=1, depth=1, correlation_id="prohib-corr"),
    )
    snapshot = SystemSnapshot(
        agent_identity={"agent_id": "test_agent", "description": "t", "role": "t"},
        channel_id="test_channel",
        agent_version="1.0.0",
        system_counts={"total_tasks": 1, "total_thoughts": 1},
    )
    # Round-1 outputs name the category, as the injected block instructs.
    inputs = EnhancedDMAInputs(
        original_thought=thought,
        processing_context={"system_snapshot": snapshot.model_dump()},
        ethical_pdma_result=EthicalDMAResult(
            action=HandlerActionType.DEFER,
            rationale=(
                "This request trends toward the prohibited capability category "
                "DISCRIMINATION (redlining) — naming it as out-of-scope so later "
                "stages can weigh and defer it."
            ),
            weight_alignment_score=0.4,
            ethical_alignment_score=0.1,
        ),
        csdma_result=CSDMAResult(
            plausibility_score=0.8,
            flags=["prohibition_trend:DISCRIMINATION"],
            reasoning="Request pattern-matches redlining; flagged for downstream weighing.",
        ),
        dsdma_result=DSDMAResult(
            domain="general",
            domain_alignment=0.2,
            flags=["prohibition_trend:DISCRIMINATION"],
            reasoning="Domain analysis concurs: DISCRIMINATION-trending.",
        ),
        permitted_actions=[HandlerActionType.SPEAK, HandlerActionType.DEFER, HandlerActionType.PONDER],
    )

    evaluator = ActionSelectionPDMAEvaluator(service_registry=registry)
    evaluator.call_llm_structured = AsyncMock(
        return_value=(
            ASPDMALLMResult(
                selected_action=HandlerActionType.DEFER,
                reasoning="Prohibited-capability trend named upstream; deferring.",
                defer_reason="DISCRIMINATION trend",
            ),
            None,
        )
    )

    await evaluator.evaluate(inputs)

    evaluator.call_llm_structured.assert_called_once()
    messages = evaluator.call_llm_structured.call_args.kwargs["messages"]
    joined = "\n".join(m["content"] for m in messages)

    # The category named in round-1 outputs reaches ASPDMA's context via the
    # DMA-summary plumbing (rationale + flags + reasoning are all carried).
    assert "DISCRIMINATION" in joined
    assert "redlining" in joined
    assert "prohibition_trend:DISCRIMINATION" in joined
    # ...and it arrives as flowed-forward reasoning content, NOT as a restated
    # prohibition block (round-1 scope only, by design).
    assert PROHIBITION_HEADER_EN not in joined
    assert PROHIBITION_TIER_NEVER_EN not in joined


# --- #910 test plan, part 4: the WiseBus gate is unchanged -------------------
#
# The structural gate is the enforcement point and must be indifferent to the
# reasoning-context injection: whether the prompt block renders fully, or not at
# all, _validate_capability behaves identically. (Full gate coverage lives in
# tests/logic/buses/test_wise_bus_medical_blocking.py and
# tests/test_prohibition_system.py; this pins the injection-independence seam.)


def test_wisebus_gate_unchanged_by_injection_state(monkeypatch) -> None:
    from unittest.mock import MagicMock

    from ciris_engine.logic.buses.wise_bus import WiseBus

    registry = MagicMock()
    registry.get_services_by_type.return_value = []
    bus = WiseBus(registry, MagicMock())

    def gate_behavior() -> tuple[bool, bool, bool]:
        try:
            bus._validate_capability("capability:redlining")
            never_raises = False
        except ValueError:
            never_raises = True
        module_defers = bus._validate_capability("domain:medical") is not None
        safe_allowed = bus._validate_capability("domain:weather") is None
        return (never_raises, module_defers, safe_allowed)

    baseline = gate_behavior()
    assert baseline == (True, True, True)

    # Simulate a language with NOTHING localized: the reasoning block vanishes...
    import ciris_engine.logic.utils.localization as L

    monkeypatch.setattr(L, "_get_language_data", lambda lang: {})
    assert get_prohibition_guidance("xx") == ""
    # ...and the gate does not move an inch.
    assert gate_behavior() == baseline
