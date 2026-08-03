"""The taxonomy gate — every block is tagged, and no block is ``mixed``.

Two assertions, and they are the precondition for instrumenting the ablation at
all:

1. **Every composed block carries a class.** An untagged block is a block the
   gate cannot disposition, so it is neither held nor varied — it just rides
   along.
2. **No block is ``mixed``.** ``mixed`` is not a class; it is the absence of
   one. It defaults to refuse, which is the honest behaviour, but a refusal is
   not a measurement.

Why this matters more than the class vocabulary: eleven well-chosen classes are
currently collapsing onto ``mixed`` for most of the surface, so the ceiling on
the ablation is **routing, not vocabulary**. A class earns its place only if it
implies a different disposition or kill condition — and a block that cannot be
dispositioned at all defeats every one of them at once.

``mixed`` arose from block GRANULARITY, not from prose. ``_rows_for_messages``
emitted one row per *message*, while ``get_system_message`` composes a message
from up to seven fields, each with its own ``source=<component>.<field>[<lang>]``
tag and, in almost every case, its own single class. A system message that is
``procedural + axiotic + contingent`` is three clean blocks the dump reported as
one dirty one. #997 split on the field boundary the composer already knows —
no prose rewriting, no re-localization, and production composition byte-identical
(the recording hook lives in the dump's patch set and does not exist at runtime).

What survives is the genuinely mixed residue, and it is of exactly two kinds:

1. **one YAML scalar that carries values and method together** —
   ``pdma_ethical.system_guidance_header`` and the three conscience system
   prompts. Splitting these means cutting the corpus into fields, not moving a
   boundary the composer already knows.
2. **prose whose classes interleave sentence by sentence** —
   ``prompts.language_guidance`` (13,694 B at ``en``), a text split followed by
   a re-localization pass across all 29 locales.

Plus two blocks composed in Python with no render seam at all
(``action_selection_pdma.system_message`` and the ASPDMA user template's slot
payload, whose slots are other prompt fields).

``EXPECTED_MIXED`` is a ratchet. It may shrink, never grow — and growing it to
make this file pass is the one failure mode this file exists to prevent.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Dict, Set

import pytest

from ciris_engine.logic.utils.compose_dump import BLOCK_ANNOTATIONS
from ciris_engine.schemas.dma.compose import BlockClass

#: Blocks still awaiting a split, each with what it must become. A ratchet.
#: Entries leave as composition is split; nothing may join without an issue.
EXPECTED_MIXED: Dict[str, str] = {
    "language_guidance": (
        "CIRISAgent#997 — 13,694 B of prose carrying register doctrine, categorical "
        "prohibitions, crisis-line world-facts and value claims sentence by sentence; "
        "needs a text split + re-localization across 29 locales"
    ),
    "pdma_ethical.system_guidance_header": (
        "CIRISAgent#997 — one YAML field walking the PDMA stages while naming and "
        "ranking the Six Principles and M-1; needs the field cut in 29 locales"
    ),
    "action_selection_pdma.system_message": (
        "CIRISAgent#997 — assembled from Python literals (DEFAULT_TEMPLATE + the "
        "conscience-retry block), so there is no render seam to split it on; "
        "'Recall CIRIS principles override personal preference' is why it cannot merge up"
    ),
    "action_selection_pdma.context_integration.slots": (
        "CIRISAgent#997 — the ASPDMA user template delivers other PROMPT FIELDS "
        "(action_parameter_schemas, final_ponder_advisory, conscience_guidance) through "
        "slots; recording those renders as blocks retires this entry"
    ),
    "coherence_conscience.system_prompt": (
        "CIRISAgent#997 — one YAML scalar; the CIRIS CORE PRINCIPLES section (562 B) "
        "needs cutting out into its own field"
    ),
    "epistemic_humility_conscience.system_prompt": (
        "CIRISAgent#997 — one YAML scalar; ALIGNED GRACE and the closing grace premise "
        "(415 B) need cutting out into their own fields"
    ),
    "optimization_veto_conscience.system_prompt": (
        "CIRISAgent#997 — one YAML scalar; ~11.7 KB of cross-tradition value doctrine "
        "(torque, the four capture patterns, the locale covenant) needs cutting into fields"
    ),
}


def test_every_annotated_block_carries_a_class() -> None:
    """No entry may be tagless. A block with no class cannot be dispositioned,
    so it is silently exempt from both hold and vary."""
    tagless = sorted(bid for bid, ann in BLOCK_ANNOTATIONS.items() if ann.block_class is None)
    assert not tagless, f"blocks with no taxonomy tag: {tagless}"


def test_every_mixed_block_names_its_contaminants() -> None:
    """`mixed` without a contaminant list is unactionable: it says "we could not
    split this" without saying into what. The split plan lives in that list."""
    naked = sorted(
        bid
        for bid, ann in BLOCK_ANNOTATIONS.items()
        if ann.block_class == BlockClass.MIXED and not ann.contaminant
    )
    assert not naked, f"mixed blocks with no contaminant list: {naked}"


def test_no_non_mixed_block_declares_contaminants() -> None:
    """A single-class block with a contaminant list is a mislabel — either it is
    mixed, or the list is wrong. Both are worth failing on."""
    confused = sorted(
        bid
        for bid, ann in BLOCK_ANNOTATIONS.items()
        if ann.block_class != BlockClass.MIXED and ann.contaminant
    )
    assert not confused, f"single-class blocks carrying contaminants: {confused}"


def test_no_mixed_blocks_beyond_the_ratchet() -> None:
    """THE gate. Every `mixed` block must be a known, tracked split."""
    mixed: Set[str] = {bid for bid, ann in BLOCK_ANNOTATIONS.items() if ann.block_class == BlockClass.MIXED}
    unexpected = sorted(mixed - set(EXPECTED_MIXED))
    assert not unexpected, (
        f"new mixed blocks: {unexpected}. `mixed` is the absence of a class, not a class — it "
        f"defaults to refuse, so the block cannot be held or varied and the ablation cannot "
        f"measure it. Split on the field boundary the composer already knows, or add an entry "
        f"to EXPECTED_MIXED with the issue that will."
    )


def test_the_mixed_ratchet_only_turns_one_way() -> None:
    assert len(EXPECTED_MIXED) <= 7, f"EXPECTED_MIXED grew to {len(EXPECTED_MIXED)} — split it, don't park it"
    assert all(v.startswith("CIRISAgent#") for v in EXPECTED_MIXED.values())


def test_only_axiotic_contamination_survives_as_mixed() -> None:
    """The merge rule, asserted.

    Classes that all imply hold-or-n/a are merged up to the strictest one, so a
    block is only ``mixed`` when its classes DISAGREE about disposition — which
    means ``axiotic`` (the sole varied class) sitting next to something that
    must hold. A ``mixed`` block without an axiotic contaminant is a block that
    was left mixed for no decision-bearing reason.
    """
    for block_id, annotation in BLOCK_ANNOTATIONS.items():
        if annotation.block_class is not BlockClass.MIXED:
            continue
        assert BlockClass.AXIOTIC in (annotation.contaminant or ()), (
            f"{block_id} is mixed but names no axiotic contaminant — every class it does name "
            f"holds or is n/a, so the strictest one is a decision-equivalent label. Merge it up."
        )


def test_the_safe_format_patch_set_covers_every_module_top_binding() -> None:
    """A module that binds ``safe_format`` at import time escapes the dump's
    per-field split SILENTLY — the fields just revert to unnamed residue and
    the dump stays green. Every such module must be in the patch list."""
    from tests.ciris_engine.logic.dma.compose_golden import SAFE_FORMAT_PATCH_TARGETS

    engine_root = Path(__file__).resolve().parents[4] / "ciris_engine"
    binding = re.compile(r"^from [.\w]*prompt_loader import [^\n]*\bsafe_format\b", re.MULTILINE)
    missing = []
    for path in sorted(engine_root.rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if not binding.search(source):
            continue
        module = str(path.relative_to(engine_root.parent).with_suffix("")).replace("/", ".")
        if f"{module}.safe_format" not in SAFE_FORMAT_PATCH_TARGETS:
            missing.append(module)
    assert not missing, (
        f"modules binding safe_format at import time but absent from "
        f"SAFE_FORMAT_PATCH_TARGETS: {missing}"
    )


def test_the_ratchet_carries_no_stale_entries() -> None:
    """A parked block that is no longer mixed must leave, or the ratchet can
    hide a NEW mixed block behind a stale key."""
    stale = sorted(
        bid
        for bid in EXPECTED_MIXED
        if bid in BLOCK_ANNOTATIONS and BLOCK_ANNOTATIONS[bid].block_class != BlockClass.MIXED
    )
    assert not stale, f"no longer mixed — remove from EXPECTED_MIXED: {stale}"


@pytest.mark.parametrize("block_id", sorted(EXPECTED_MIXED))
def test_every_parked_block_is_actually_annotated(block_id: str) -> None:
    """The ratchet must reference real blocks, or it silently protects nothing."""
    assert block_id in BLOCK_ANNOTATIONS, f"{block_id} is parked in EXPECTED_MIXED but has no annotation"
