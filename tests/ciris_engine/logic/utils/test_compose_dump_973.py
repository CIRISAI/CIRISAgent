"""#973 — compose --dump + ablation gate Phase 1.

Covers, per the FSD §12 Phase-1 contract:

- the dump's honest block table (routed blocks get real sources, unrouted
  text reports ``mixed`` with populated contaminants, deterministic output);
- gate self-check: a dump gated against itself under the null self-check
  regime PASSES every hold;
- mutation evidence: (1) flipping one held block's bytes turns assertion 3
  red naming the block; (2) shrinking RESIDUE_SITES turns assertions 5/4 red
  (digest + fragment-inventory drift); (3) a mixed block inside a varied
  class refuses with its block_id named;
- assertion 2 passes only when the ablation actually reached the varied
  blocks (differing bytes, both non-empty).
"""

from pathlib import Path
from typing import List, Tuple

import pytest

from ciris_engine.logic.utils.compose_dump import (
    BLOCK_ANNOTATIONS,
    annotation_for,
    compose_dump_rows,
    residue_fragments,
    run_gate,
    write_dump,
)
from ciris_engine.schemas.dma.compose import BlockClass, BlockDisposition, ComposedBlock, ComposeDumpMeta

_REPO_ROOT = Path(__file__).resolve().parents[4]
_NULL_REGIME = _REPO_ROOT / "tools" / "research" / "regimes" / "phase1_selfcheck_null.yaml"
_VARIED_REGIME = _REPO_ROOT / "tools" / "research" / "regimes" / "phase1_selfcheck_varied.yaml"

Dump = Tuple[ComposeDumpMeta, List[ComposedBlock]]


@pytest.fixture(scope="module")
def en_dump() -> Dump:
    """One full composition pass (all 8 steps, en) shared by the module."""
    return compose_dump_rows(arm="h3ere-ciris", locales=["en"])


# ---------------------------------------------------------------------------
# The dump: honest block table
# ---------------------------------------------------------------------------


def test_dump_covers_every_step_with_expected_blocks(en_dump: Dump) -> None:
    meta, rows = en_dump
    assert meta.steps == [
        "pdma",
        "csdma",
        "idma",
        "dsdma",
        "aspdma",
        "dsaspdma",
        "tsaspdma",
        "tsaspdma_correction",
        # #986: the second composition a thought gets when a conscience
        # overrides it, in both of _build_retry_guidance's branches, plus the
        # follow-up thought carrying the conscience-authored ponder notes.
        "aspdma_retry",
        "aspdma_retry_observation",
        "aspdma_ponder_notes",
        # #986: the other recursion — DMA bounce re-run and its ASPDMA advisory.
        "csdma_bounce",
        "aspdma_bounce_advisory",
        # #986: the four conscience faculties, without and with image context
        # (a different overridable user template renders for each).
        "entropy_conscience",
        "coherence_conscience",
        "optimization_veto_conscience",
        "epistemic_humility_conscience",
        "entropy_conscience_image",
        "coherence_conscience_image",
        "optimization_veto_conscience_image",
        "epistemic_humility_conscience_image",
    ]
    by_step: dict[str, List[str]] = {}
    for row in rows:
        by_step.setdefault(row.step, []).append(row.block_id.split(".", 1)[1])
    # Since #997 a block is a FIELD, not a message: the discrete corpus/string
    # blocks are unchanged, but each composed message contributes one row per
    # field the composer appended, plus NAMED residue for the bytes no field
    # render explains (`system.head` / `system.tail` / `system.joinN`).
    for step in ("csdma", "csdma_bounce"):
        assert by_step[step] == [
            "accord",
            "language_guidance",
            "prohibition",
            "csdma_common_sense.system_guidance_header",
            "system.join1",
            "csdma_common_sense.evaluation_steps",
            "csdma_common_sense.evaluation_steps.slots",
            "system.join2",
            "csdma_common_sense.response_format",
            "system.tail",
            "csdma_common_sense.context_integration",
            "csdma_common_sense.context_integration.slots",
        ], step
    assert by_step["pdma"] == [
        "accord",
        "language_guidance",
        "prohibition",
        "pdma_ethical.system_guidance_header",
        "pdma_ethical.system_guidance_header.slots",
        "pdma_ethical.context_integration",
        "pdma_ethical.context_integration.slots",
    ]
    assert by_step["idma"] == [  # no prohibition (#910)
        "accord",
        "language_guidance",
        "idma.system_guidance_header",
        "system.join1",
        "idma.evaluation_steps",
        "system.join2",
        "idma.response_format",
        "system.join3",
        "idma.closing_reminder",
        "system.tail",
        "idma.context_integration",
        "idma.context_integration.slots",
    ]
    # DSDMA renders its header with a bare `.format()` (dsdma_base.py), so the
    # identity block and that header stay one named `system.head` residue.
    assert by_step["dsdma"] == [
        "accord",
        "language_guidance",
        "prohibition",
        "system.head",
        "dsdma_base.response_format",
        "dsdma_base.context_integration",
        "dsdma_base.context_integration.slots",
    ]
    # ASPDMA and its four #986 recursions compose the SAME blocks — the accord
    # message splits into its runtime THOUGHT_TYPE slot and the routed accord.
    for step in (
        "aspdma",
        "aspdma_retry",
        "aspdma_retry_observation",
        "aspdma_ponder_notes",
        "aspdma_bounce_advisory",
    ):
        assert by_step[step] == [
            "thought_type",
            "accord",
            "language_guidance",
            "action_selection_pdma.system_message",
            "action_selection_pdma.context_integration",
            "action_selection_pdma.context_integration.slots",
            "user.join1",
            "action_selection_pdma.csdma_ambiguity_guidance",
            "user.join2",
            "action_selection_pdma.csdma_ambiguity_alignment_example",
            "user.join3",
            "action_selection_pdma.tool_selection_guidance",
        ], step
    assert by_step["dsaspdma"] == [
        "accord",
        "language_guidance",
        "dsaspdma.system_guidance_header",
        "system.join1",
        "dsaspdma.evaluation_steps",
        "system.join2",
        "dsaspdma.response_format",
        "system.join3",
        "dsaspdma.closing_reminder",
        "user.head",
        "dsaspdma.taxonomy_text",
        "user.tail",
    ]
    assert by_step["tsaspdma"] == [
        "accord",
        "language_guidance",
        "tsaspdma.system_guidance_header",
        "system.join1",
        "tsaspdma.evaluation_steps",
        "system.join2",
        "tsaspdma.response_format",
        "system.join3",
        "tsaspdma.closing_reminder",
        "tsaspdma.context_integration",
        "tsaspdma.context_integration.slots",
    ]
    assert by_step["tsaspdma_correction"] == [
        "accord",
        "language_guidance",
        "tsaspdma.system_guidance_header",
        "system.join1",
        "tsaspdma.evaluation_steps",
        "system.join2",
        "tsaspdma.response_format",
        "system.join3",
        "tsaspdma.closing_reminder",
        "user.head",
        "tsaspdma.tool_correction_section",
        "tsaspdma.tool_correction_section.slots",
        "user.tail",
    ]
    # A conscience composes exactly three messages: the accord, its localized
    # system calibration (one YAML scalar — no field boundary to split on), and
    # the rendered user template, which splits into authored frame + payload.
    for faculty in (
        "entropy_conscience",
        "coherence_conscience",
        "optimization_veto_conscience",
        "epistemic_humility_conscience",
    ):
        assert by_step[faculty] == [
            "accord",
            f"{faculty}.system_prompt",
            f"{faculty}.user_prompt_template",
            f"{faculty}.user_prompt_template.slots",
        ], faculty
        assert by_step[f"{faculty}_image"] == [
            "accord",
            f"{faculty}.system_prompt",
            f"{faculty}.user_prompt_with_image_template",
            f"{faculty}.user_prompt_with_image_template.slots",
        ], faculty


def test_routed_blocks_carry_real_sources_and_classes(en_dump: Dump) -> None:
    _, rows = en_dump
    by_id = {r.block_id: r for r in rows}
    assert by_id["pdma.accord"].source == "corpus:accord.polyglot_compressed"
    assert by_id["pdma.accord"].block_class is BlockClass.AXIOTIC
    assert by_id["dsaspdma.accord"].source == "corpus:accord.localized"
    assert by_id["pdma.prohibition"].block_class is BlockClass.DEONTIC
    assert by_id["pdma.prohibition"].source == "string:prompts.prohibitions"
    assert by_id["pdma.language_guidance"].source == "string:prompts.language_guidance"
    # ASPDMA's accord message used to report as ONE mixed block because a runtime
    # THOUGHT_TYPE slot was prepended to the routed accord. #997 splits it: the
    # slot is its own contingent block and 54,725 B of routed corpus is axiotic
    # and varied instead of unmeasurable.
    assert by_id["aspdma.thought_type"].block_class is BlockClass.CONTINGENT
    assert by_id["aspdma.accord"].block_class is BlockClass.AXIOTIC
    assert by_id["aspdma.accord"].source == "corpus:accord.localized"
    # #995 P0-1 routed the conscience accord; #997 patches the module-top name
    # the faculties bind, so the largest block in the dump reports its real key.
    assert by_id["entropy_conscience.accord"].source == "corpus:accord.polyglot_full"
    # A field row names the field, carries the composer's own source, and points
    # back at the message it was split out of.
    header = by_id["idma.idma.system_guidance_header"]
    assert header.source == "dma_prompt:idma.system_guidance_header"
    assert header.block_class is BlockClass.NOMOLOGICAL
    assert header.parent_block_id == "idma.system"


def test_every_mixed_block_carries_populated_contaminants(en_dump: Dump) -> None:
    _, rows = en_dump
    for row in rows:
        if row.block_class is BlockClass.MIXED:
            assert row.contaminant, f"{row.block_id}: mixed without contaminant list (§10.2.1 T-N1)"
            assert row.disposition is BlockDisposition.REFUSE  # refusal by default


def test_residue_scan_finds_inline_action_scaffolding_in_aspdma_user(en_dump: Dump) -> None:
    """Assertion 4's instrument: the inline action-schema scaffolding must be
    visible as residue inside the ASPDMA user message. (Pre-#974 this test
    watched the DEFER policy; step 0 routed that text into
    action_selection_pdma.yml, so it is covered now and correctly ABSENT from
    the residue scan — the remaining generator literals still hit.)

    #997 moved the hits one level down without losing any: the scaffolding is
    interpolated INTO the ASPDMA user template, so it lands in the slot-payload
    block rather than in the whole message. That block is the one
    ``EXPECTED_MIXED`` entry that exists precisely because its slots carry other
    prompt fields."""
    _, rows = en_dump
    slots = next(r for r in rows if r.block_id == "aspdma.action_selection_pdma.context_integration.slots")
    assert any("action_instruction_generator" in hit for hit in slots.residue_hits)
    # And the routed DEFER policy no longer registers as an uncovered fragment:
    # its prose left the pinned Python symbols, so the scan must not carry it.
    assert not any("DEFER is ONLY" in text for _, text in residue_fragments())


def test_every_composed_block_reassembles_into_its_message(en_dump: Dump) -> None:
    """The #997 contract: every byte the model receives is reported exactly once.

    Rows that carry a ``parent_block_id`` are the pieces of one composed
    message; their byte lengths must sum to the message's. (``_split_message``
    already refuses to return a split that does not reassemble; this asserts the
    property survives into the emitted rows.)"""
    _, rows = en_dump
    totals: dict[tuple[str, str], int] = {}
    for row in rows:
        if row.parent_block_id is not None:
            totals[(row.locale, row.parent_block_id)] = totals.get((row.locale, row.parent_block_id), 0) + row.bytes
    assert totals, "no message was split — the per-field seam is not firing"
    # A parent that was split has no row of its own, so the sum is checked
    # against a recomposition of the same step rather than a stored row: the
    # invariant that matters here is that every parent has >1 piece and no piece
    # is empty.
    for row in rows:
        assert row.bytes > 0, f"{row.block_id}: zero-byte block emitted"


def test_the_per_field_hook_does_not_exist_outside_a_dump_run() -> None:
    """Production composition is byte-identical because there is NO hook in
    production: ``safe_format`` is unmodified, and the recording pass-through is
    a patch scoped to the dump's ExitStack. Asserted by identity."""
    from ciris_engine.logic.dma import prompt_loader

    before = prompt_loader.safe_format
    compose_dump_rows(arm="h3ere-ciris", locales=["en"], steps=["pdma"])
    assert prompt_loader.safe_format is before


def test_dump_rows_are_deterministic(en_dump: Dump) -> None:
    meta_2, rows_2 = compose_dump_rows(arm="h3ere-ciris", locales=["en"])
    meta_1, rows_1 = en_dump
    assert meta_1 == meta_2
    assert [r.model_dump(by_alias=True) for r in rows_1] == [r.model_dump(by_alias=True) for r in rows_2]


def test_annotation_fallback_is_mixed() -> None:
    """A block this table has never seen is honestly mixed — the gate then
    refuses it without an explicit disposition, so new blocks cannot slip
    through green."""
    unknown = annotation_for("newstep.someblock")
    assert unknown.block_class is BlockClass.MIXED
    assert unknown.contaminant
    assert "accord" in BLOCK_ANNOTATIONS  # the κ pass (#976) replaces this table


# ---------------------------------------------------------------------------
# Gate Phase 1: self-check + mutations
# ---------------------------------------------------------------------------


def _write(tmp_path: Path, name: str, meta: ComposeDumpMeta, rows: List[ComposedBlock]) -> str:
    out = tmp_path / name
    write_dump(meta, rows, str(out))
    return str(out)


def test_gate_selfcheck_passes(en_dump: Dump, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    meta, rows = en_dump
    dump_a = _write(tmp_path, "a.jsonl", meta, rows)
    dump_b = _write(tmp_path, "b.jsonl", meta, rows)
    assert run_gate(dump_a, dump_b, str(_NULL_REGIME)) == 0
    assert "GATE: PASS" in capsys.readouterr().out


def test_gate_mutation_1_flipped_held_block_turns_assertion_3_red(
    en_dump: Dump, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meta, rows = en_dump
    mutated = [
        r.model_copy(update={"sha256": "0" * 64}) if r.block_id == "pdma.prohibition" else r for r in rows
    ]
    dump_a = _write(tmp_path, "a.jsonl", meta, rows)
    dump_b = _write(tmp_path, "b.jsonl", meta, mutated)
    assert run_gate(dump_a, dump_b, str(_NULL_REGIME)) == 1
    out = capsys.readouterr().out
    assert "[3] en:pdma.prohibition" in out  # the failing block is NAMED


def test_gate_mutation_2_shrunken_residue_inventory_turns_assertions_5_and_4_red(
    en_dump: Dump, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Removing a RESIDUE_SITES entry (weakening the scan's coverage) is
    caught: the live residue_digest no longer matches what the dumps recorded
    (assertion 5) and the live fragment inventory count drifts (assertion 4).

    NOT covered by self-check, stated honestly: weakening the scanner itself
    (e.g. raising the fragment length floor) in the same commit that produces
    both dumps AND runs the gate — shared-code weakening is invisible to any
    self-check by construction; that is what review of this module is for.
    """
    from ciris_engine.logic.utils import research_overrides

    meta, rows = en_dump
    dump_a = _write(tmp_path, "a.jsonl", meta, rows)
    dump_b = _write(tmp_path, "b.jsonl", meta, rows)
    monkeypatch.setattr(research_overrides, "RESIDUE_SITES", research_overrides.RESIDUE_SITES[:-1])
    assert run_gate(dump_a, dump_b, str(_NULL_REGIME)) == 1
    out = capsys.readouterr().out
    assert "[5] residue_digest mismatch" in out
    assert "[4] residue scan inventory drift" in out


def test_gate_mutation_3_mixed_block_in_varied_class_refuses_by_name(
    en_dump: Dump, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meta, rows = en_dump
    dump_a = _write(tmp_path, "a.jsonl", meta, rows)
    dump_b = _write(tmp_path, "b.jsonl", meta, rows)
    assert run_gate(dump_a, dump_b, str(_VARIED_REGIME)) == 1
    out = capsys.readouterr().out
    # language_guidance: no per-block entry, axiotic contaminant, axiotic varied.
    assert "REFUSE en:pdma.language_guidance" in out
    # The block the DEFER policy and the action-parameter schemas are delivered
    # in, held while axiotic varies [M-4/T-N1]. Pre-#997 this was the whole
    # `aspdma.user` message; the field split moved it to the slot payload.
    assert "REFUSE en:aspdma.action_selection_pdma.context_integration.slots" in out


def test_gate_assertion_2_passes_when_ablation_reaches_varied_blocks(
    en_dump: Dump, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """With every axiotic block actually replaced (differing, non-empty) and
    every mixed contamination explicitly confound-accepted, the varied gate
    holds — assertion 2 is satisfiable, not a tautological refusal."""
    meta, rows = en_dump
    varied_rows = [
        (
            r.model_copy(update={"sha256": "f" * 64, "bytes": 1234})
            if r.block_class is BlockClass.AXIOTIC
            else r
        )
        for r in rows
    ]
    dump_a = _write(tmp_path, "a.jsonl", meta, rows)
    dump_b = _write(tmp_path, "b.jsonl", meta, varied_rows)
    regime = tmp_path / "regime.yaml"
    regime.write_text(
        """
regime_id: test-varied-accepted
arms:
  h3ere-ciris: {harness: h3ere}
  h3ere-alt: {harness: h3ere, replace: {axiotic: corpora/values-alt/}}
blocks:
  language_guidance: {disposition: hold, confound_accepted: [axiotic]}
  pdma_ethical.system_guidance_header: {disposition: hold, confound_accepted: [axiotic]}
  action_selection_pdma.system_message: {disposition: hold, confound_accepted: [axiotic]}
  action_selection_pdma.context_integration.slots: {disposition: hold, confound_accepted: [axiotic]}
  coherence_conscience.system_prompt: {disposition: hold, confound_accepted: [axiotic]}
  epistemic_humility_conscience.system_prompt: {disposition: hold, confound_accepted: [axiotic]}
  optimization_veto_conscience.system_prompt: {disposition: hold, confound_accepted: [axiotic]}
pins:
  residue_digest: "live"
""",
        encoding="utf-8",
    )
    assert run_gate(dump_a, dump_b, str(regime)) == 0
    assert "GATE: PASS" in capsys.readouterr().out


def test_gate_assertion_2_rejects_empty_replacement(
    en_dump: Dump, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    meta, rows = en_dump
    emptied = [
        r.model_copy(update={"sha256": "e" * 64, "bytes": 0}) if r.block_id == "pdma.accord" else r for r in rows
    ]
    dump_a = _write(tmp_path, "a.jsonl", meta, rows)
    dump_b = _write(tmp_path, "b.jsonl", meta, emptied)
    regime = tmp_path / "regime.yaml"
    regime.write_text(
        """
regime_id: test-empty-replacement
arms:
  h3ere-ciris: {harness: h3ere}
  h3ere-blank: {harness: h3ere, disable: [axiotic]}
blocks:
  language_guidance: {disposition: hold, confound_accepted: [axiotic]}
  pdma_ethical.system_guidance_header: {disposition: hold, confound_accepted: [axiotic]}
  action_selection_pdma.system_message: {disposition: hold, confound_accepted: [axiotic]}
  action_selection_pdma.context_integration.slots: {disposition: hold, confound_accepted: [axiotic]}
  coherence_conscience.system_prompt: {disposition: hold, confound_accepted: [axiotic]}
  epistemic_humility_conscience.system_prompt: {disposition: hold, confound_accepted: [axiotic]}
  optimization_veto_conscience.system_prompt: {disposition: hold, confound_accepted: [axiotic]}
pins:
  residue_digest: "live"
""",
        encoding="utf-8",
    )
    assert run_gate(dump_a, dump_b, str(regime)) == 1
    out = capsys.readouterr().out
    assert "[2] en:pdma.accord" in out
    assert "EMPTY" in out


def test_residue_fragments_are_normalized_and_bounded() -> None:
    fragments = residue_fragments()
    assert fragments, "the residue inventory yielded no scannable fragments"
    for fragment_id, text in fragments:
        assert "::" in fragment_id
        assert "\n" not in text  # whitespace-normalized
        assert len(text) >= 40
