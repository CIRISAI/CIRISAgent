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
   ``prompts.language_guidance``. #997 split this one IN THE CORPUS for the
   five locales whose prose is line-for-line parallel to English (en, es, fr,
   it, pt): 29 consecutive slices, joined with ``""`` and stripped once, so the
   composed message is byte-identical to the pre-split scalar. At ``en`` that
   moves 9,505 of 13,694 B (69.4%) from unmeasurable to dispositionable and
   makes 429 B of axiotic content VARY that a values arm would previously have
   held. The other 24 locales keep the scalar, because partitioning them would
   mean re-segmenting the target-language prose — which is how word-salad has
   entered this corpus before — so ``language_guidance`` stays parked, now
   scoped to those 24.

Plus two blocks composed in Python with no render seam at all
(``action_selection_pdma.system_message`` and the ASPDMA user template's slot
payload, whose slots are other prompt fields).

TWO REGISTERS, and the distinction is load-bearing:

- ``EXPECTED_MIXED`` — blocks awaiting a split. A ratchet: it may shrink, never
  grow, and growing it to make this file pass is the one failure mode this file
  exists to prevent.
- ``IRREDUCIBLE_EXEMPLARS`` — blocks the FSD itself declares unsplittable
  (§10.2.1 [T-5a]: "verdict, register and schema in the same tokens — the
  co-occurrence *is* the demonstration ... hold-verbatim or replace-whole-
  exemplar, never split"). These are not parked pending work; splitting them is
  forbidden, and the FSD sanctions ``hold`` + ``confound_accepted: axiotic`` for
  exactly this shape (§10.3's ``pdma_worked_examples``) while explicitly
  refusing that opt-out for ``language_guidance`` as a whole. Bounded and
  FSD-cited so it cannot become a second parking lot.

The number that cannot be argued with is bytes, not entry count:
``test_language_guidance_split_997.py`` measures the real corpus and fails if
the mixed share of ``language_guidance`` at ``en`` ever grows.
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
    "system.head": (
        "CIRISAgent#997 — the DSDMA identity+norms preamble: CORE IDENTITY (ontological), "
        "the domain header rendered by a bare .format() (procedural), and CROSS-DOMAIN NORMS "
        "carrying both categorical duties (deontic) and outcome rankings (axiotic). Splitting "
        "needs the norms block cut out of the Python-side render, not a boundary the composer "
        "already knows"
    ),
    "language_guidance": (
        "CIRISAgent#997 — the UNSPLIT scalar, now scoped to the 24 locales whose prose "
        "does not partition on the English boundaries (am ar bn de fa ha hi id ja ko mr "
        "my pa ru sw ta te th tr uk ur vi yo zh). en/es/fr/it/pt are split and never "
        "resolve here. Retiring this entry means segmenting the remaining 24 in their "
        "own prose — a native-language pass, not a script"
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

#: Blocks the FSD declares UNSPLITTABLE — not parked work, forbidden work.
#:
#: §10.2.1 [T-5a]: "Few-shot worked examples: verdict, register and schema in
#: the same tokens — the co-occurrence *is* the demonstration. ``mixed``,
#: explicit disposition required; the honest options are hold-verbatim or
#: replace-whole-exemplar, never split."
#:
#: This is a DIFFERENT category from EXPECTED_MIXED, and the FSD draws the line
#: itself: §10.3's example manifest gives ``pdma_worked_examples`` ``hold`` +
#: ``confound_accepted: axiotic``, and in the same breath refuses that opt-out
#: for ``language_guidance`` as a whole because "an example manifest is a
#: template people copy, and it must not teach the opt-out as the default". An
#: exemplar has a sanctioned disposition path; an undivided 13 KB scalar does
#: not.
#:
#: Bounded, FSD-cited, and disjoint from EXPECTED_MIXED — three tests below —
#: so it cannot become a second parking lot for blocks that simply were not
#: split.
IRREDUCIBLE_EXEMPLARS: Dict[str, str] = {
    "language_guidance.13_exemplar_speak_response": (
        "FSD §10.2.1 [T-5a] — the SPEAK demonstration: canonical disclaimer, crisis "
        "numbers, warm formal register and 'those symptoms together deserve attention' "
        "in the same tokens"
    ),
    "language_guidance.14_exemplar_register_pressure": (
        "FSD §10.2.1 [T-5a] — 7a: correct and wrong responses shown verbatim; the "
        "axiotic clause cannot be lifted out of the demonstration"
    ),
    "language_guidance.16_exemplar_false_reassurance": (
        "FSD §10.2.1 [T-5a] — 7b: the refusal-to-confirm demonstrated, not described"
    ),
    "language_guidance.23_ratification_templates": (
        "FSD §10.2.1 [T-5a] — two verbatim INVOCABLE TEMPLATE model outputs"
    ),
    "language_guidance.25_exemplar_cross_cluster": (
        "FSD §10.2.1 [T-5a] — 7c: the cluster answer and the Q4 HARD-FAIL U6 "
        "counter-example, both shown verbatim"
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
    """THE gate. Every `mixed` block must be a known, tracked split — or an
    FSD-declared irreducible, which is a different claim and is registered
    separately."""
    mixed: Set[str] = {bid for bid, ann in BLOCK_ANNOTATIONS.items() if ann.block_class == BlockClass.MIXED}
    unexpected = sorted(mixed - set(EXPECTED_MIXED) - set(IRREDUCIBLE_EXEMPLARS))
    assert not unexpected, (
        f"new mixed blocks: {unexpected}. `mixed` is the absence of a class, not a class — it "
        f"defaults to refuse, so the block cannot be held or varied and the ablation cannot "
        f"measure it. Split on the field boundary the composer already knows, or add an entry "
        f"to EXPECTED_MIXED with the issue that will."
    )


#: The TOTAL mixed surface, across BOTH registers. This is the number a reader
#: should carry away, and the one an adversarial review corrected us on.
#:
#: "48 -> 7" was the headline first reported and it is wrong: five blocks moved
#: into IRREDUCIBLE_EXEMPLARS rather than being split, so the live dump carries
#: TWELVE distinct mixed keys, every one disposition=refuse. Splitting the
#: register was right — "the FSD forbids splitting this" and "we have not split
#: this yet" are different claims. Reporting only the smaller half was not.
#:
#: Bounding the SUM is what makes the split honest: a block cannot be quietly
#: relabelled from one register to the other to make a bound look better,
#: because moving it changes neither this number nor the disposition the gate
#: applies.
TOTAL_MIXED_CEILING = 13

#: What the surface measured BEFORE the per-field split, recorded so the ratchet
#: has a baseline the repository can witness.
#:
#: It could not, before. `git log --diff-filter=A` on this file returns exactly
#: one commit — the change the gate scores — with the bound already set to the
#: number that change achieved. The stated "EXPECTED_MIXED 11 -> 7" described a
#: shrink from a state no commit contains. A ratchet whose starting notch is not
#: in version control is an assertion, not a ratchet.
MIXED_BEFORE_THE_SPLIT = 48

#: A CORRECTION IS NOT A REGRESSION, and the ratchet must not punish one.
#:
#: 12 -> 13 because `system.head` was relabelled DEONTIC -> MIXED. It was
#: single-class on a merge-up argument ("deontic is the strictest class
#: present") that is invalid when the classes DISAGREE about disposition: the
#: block states both "informed consent required" (deontic, hold) and "client
#: interest over personal gain" / "patient welfare paramount" (axiotic, VARY).
#: Holding it as deontic held the independent variable inside a block the
#: campaign believed it was holding for safety reasons.
#:
#: A ratchet that only ever shrinks makes fixing a mislabel look like a
#: regression, which is an incentive to keep the mislabel. So the ceiling moves
#: for a CORRECTION and never for new debt — and the distinction has to be
#: stated in the same commit, because nothing mechanical can tell them apart.
MIXED_CEILING_CORRECTIONS = {
    "system.head": "#997 — DEONTIC -> MIXED; merge-up merged the varied class into a held one",
}


def test_the_mixed_ratchet_only_turns_one_way() -> None:
    """Bound the SUM, not each register — see TOTAL_MIXED_CEILING."""
    total = len(EXPECTED_MIXED) + len(IRREDUCIBLE_EXEMPLARS)
    assert total <= TOTAL_MIXED_CEILING, (
        f"total mixed surface grew to {total} (EXPECTED_MIXED={len(EXPECTED_MIXED)}, "
        f"IRREDUCIBLE_EXEMPLARS={len(IRREDUCIBLE_EXEMPLARS)}) — split it, don't move it "
        f"between registers"
    )
    assert len(EXPECTED_MIXED) <= 7 + len(MIXED_CEILING_CORRECTIONS), (
        f"EXPECTED_MIXED grew to {len(EXPECTED_MIXED)} — split it, don't park it "
        f"(corrections allowed: {sorted(MIXED_CEILING_CORRECTIONS)})"
    )
    assert all(v.startswith("CIRISAgent#") for v in EXPECTED_MIXED.values())


def test_the_ratchet_records_where_it_started() -> None:
    """The baseline, committed, so a future reader can check the direction of
    travel against something other than a commit message."""
    assert MIXED_BEFORE_THE_SPLIT == 48
    # every ceiling raise is accounted for by a named correction
    assert TOTAL_MIXED_CEILING == 12 + len(MIXED_CEILING_CORRECTIONS), (
        "the mixed ceiling moved without a named correction — new debt must shrink the "
        "surface or stay out of it, only a mislabel fix may raise the bound"
    )
    total = len(EXPECTED_MIXED) + len(IRREDUCIBLE_EXEMPLARS)
    assert total < MIXED_BEFORE_THE_SPLIT, "the split did not reduce the mixed surface"


def test_the_irreducible_set_is_bounded_and_cites_the_fsd() -> None:
    """The escape hatch, nailed shut.

    An FSD-declared irreducible is a claim about the ARTEFACT — splitting it
    destroys the demonstration — not an admission that nobody got round to
    splitting it. Every entry must cite the clause that says so, and the set is
    bounded at the five worked exemplars that exist, so 'irreducible' cannot
    become a place to file a block that is merely hard.
    """
    assert len(IRREDUCIBLE_EXEMPLARS) <= 5, (
        f"IRREDUCIBLE_EXEMPLARS grew to {len(IRREDUCIBLE_EXEMPLARS)} — 'the FSD forbids "
        f"splitting this' is a narrow claim about few-shot demonstrations, not a second "
        f"parking lot. If a new block belongs here, argue it in the FSD first."
    )
    uncited = sorted(k for k, v in IRREDUCIBLE_EXEMPLARS.items() if not v.startswith("FSD §10.2.1 [T-5a]"))
    assert not uncited, f"irreducible entries with no FSD citation: {uncited}"


def test_the_two_registers_are_disjoint() -> None:
    """A block is awaiting a split OR forbidden from being split. Both at once
    is a contradiction, and it would let one entry satisfy two bounds."""
    both = sorted(set(EXPECTED_MIXED) & set(IRREDUCIBLE_EXEMPLARS))
    assert not both, f"blocks in BOTH registers: {both}"


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
        for bid in (*EXPECTED_MIXED, *IRREDUCIBLE_EXEMPLARS)
        if bid in BLOCK_ANNOTATIONS and BLOCK_ANNOTATIONS[bid].block_class != BlockClass.MIXED
    )
    assert not stale, f"no longer mixed — remove from EXPECTED_MIXED/IRREDUCIBLE_EXEMPLARS: {stale}"


@pytest.mark.parametrize("block_id", sorted({*EXPECTED_MIXED, *IRREDUCIBLE_EXEMPLARS}))
def test_every_parked_block_is_actually_annotated(block_id: str) -> None:
    """The ratchet must reference real blocks, or it silently protects nothing."""
    assert block_id in BLOCK_ANNOTATIONS, f"{block_id} is registered but has no annotation"
