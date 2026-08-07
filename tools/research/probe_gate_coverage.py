"""Which override keys can the compose gate actually SEE? (#986)

The ablation gate (`compose_dump gate`, #973) compares two dumps block-by-block
and reports ``GATE: PASS`` when every held block is byte-identical. That check is
only as strong as the dump's reach: **a key that moves no block cannot be
verified by the gate**, so a regime could vary it and still get ``GATE: PASS``.

This module measures that reach directly, and it is deliberately a committed,
re-runnable tool rather than a one-off script — the number it produces is a
regression target (see ``tests/ciris_engine/logic/utils/test_gate_coverage_986.py``).

Method
------
1. Dump once with no manifest: the baseline.
2. For each *probe unit* (normally one override key), write an ``additive``
   manifest that replaces exactly that unit with a visible ``PROBE::<key>``
   marker, dump again, and diff ``sha256`` per ``(locale, block_id)``.
3. A unit whose replacement moves >= 1 block is **gated** — the gate can see it.
   A unit that moves 0 blocks is **dark**: the dump never composes it, so no
   assertion in ``run_gate`` can ever constrain it.

Probe units are single keys except ``accord.*``, which R5 (`_validate_manifest`,
"no partial covenant") forbids naming individually — all three accord corpus
keys move as one unit or the manifest is refused. That is a property of the
facility, not of this probe, and the report records it.

Composition caches are process-global singletons ([I-V3], see
``compose_dump``'s module docstring), so every unit runs in its own subprocess.
Units are independent, hence ``--jobs`` fans them out.

Usage::

    python3 -m tools.research.probe_gate_coverage                  # full sweep, en
    python3 -m tools.research.probe_gate_coverage --namespace template
    python3 -m tools.research.probe_gate_coverage --locales en,am --jobs 8
    python3 -m tools.research.probe_gate_coverage --json out.json  # machine-readable
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from pydantic import BaseModel, ConfigDict, Field

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:  # pragma: no cover - script entry convenience
    sys.path.insert(0, str(_REPO_ROOT))

from ciris_engine.logic.utils.compose_dump import load_dump  # noqa: E402
from ciris_engine.logic.utils.research_overrides import (  # noqa: E402
    _ACCORD_CORPUS_KEYS,
    _TEMPLATE_TEXT_FIELDS,
    _required_conscience_prompt_keys,
    _schema_present_dma_prompt_keys,
    _valid_corpus_keys,
    compute_residue_digest,
    scan_reachable_string_keys,
)

#: The five namespaces, in the order the coverage table reports them.
NAMESPACES: Tuple[str, ...] = ("corpus", "dma_prompt", "string", "conscience_prompt", "template")

#: Sub-namespace splits worth reporting separately: the coverage story is not
#: uniform inside `string` (the `conscience.*` retry envelope behaves nothing
#: like `prompts.*`), and a single 46-key row hides that.
SUBSPLITS: Tuple[Tuple[str, str], ...] = (
    ("string:conscience.*", "conscience."),
    ("string:prompts.*", "prompts."),
)

# --------------------------------------------------------------------------
# The regression lock (#986)
# --------------------------------------------------------------------------

#: Keys per namespace, as the facility defines them. Checked for EQUALITY: if
#: the reachable key space moves, the floors below are being compared against a
#: different denominator and must be re-derived, not silently passed.
#:
#: ``dma_prompt`` 36 -> 40 in 2.9.10: four live YAML fields joined the key space
#: (``tool_selection_guidance`` and ``csdma_ambiguity_alignment_example`` became
#: composable in #993; ``taxonomy_text`` and ``tool_correction_section`` were
#: live all along but sat outside the inventory, so R1 rejected any manifest
#: naming them — #995 P1-6). The denominator moved, so the floor below is
#: re-derived rather than silently passed.
#:
#: ``string`` 46 -> 75 in 2.9.10: #997 split ``prompts.language_guidance`` into
#: 29 single-class parts in the corpus. The parent key stays (it is what the 24
#: unsplit locales resolve through, and a manifest naming it still replaces the
#: whole block), so the 29 parts are net-new addressable surface. Same rule as
#: above — the denominator moved, so the floors are re-derived.
EXPECTED_KEY_COUNTS: Dict[str, int] = {
    "corpus": 4,
    "dma_prompt": 40,
    "string": 133,
    "conscience_prompt": 12,
    "template": 3,
}

#: Minimum gated keys per namespace, measured at #986 on locale `en`.
#:
#: A RATCHET, not an equality. Coverage going up is the point and must never
#: fail a build; coverage going down means a composition the gate used to see
#: has stopped being composed — the regression this exists to catch. Raise a
#: floor in the same commit that earns it.
#:
#: Where the remainder is dark, and why — each is a reported finding:
#:
#: * ``dma_prompt`` 31/36 — 23/36 at #986 (``BaseDMA._load_prompts`` read the
#:   prompt YAML with ``yaml.safe_load`` and kept a plain dict while the
#:   override layer ``setattr``'d a ``PromptCollection`` — a container
#:   mismatch), 30/36 once #989 fixed that, 31/36 at #990.
#:
#:   #990 gained ``action_selection_pdma.action_parameter_schemas``. Its composed
#:   value is GENERATED from the live action enum by
#:   ``ActionSelectionContextBuilder._get_dynamic_action_schemas``, so an
#:   override applied at YAML load was set on the ``PromptCollection`` and then
#:   passed over — the #989 failure shape in a different place, and invisible to
#:   the gate for the same reason. It was NOT declared unoverridable: the
#:   override now applies at the COMPOSITION boundary
#:   (``_composed_action_parameter_schemas``), after generation, where a manifest
#:   value wins. Every field that enters a composed prompt is overridable.
#:
#:   The five still dark are NOT probe gaps — the probe is doing its job and
#:   naming composer defects:
#:     - ``action_selection_pdma.final_ponder_advisory`` renders ONLY on a
#:       thought's last permitted round (``current_thought_depth >= max_rounds
#:       - 1``); the fixture drives depth 0-2 of 5, so no composition reaches it.
#:       A fixture gap, closable by composing a final-attempt variant.
#:     - ``action_selection_pdma.csdma_ambiguity_guidance`` is built into
#:       ``_build_guidance_sections`` as ``action_alignment_csdma_guidance`` and
#:       then never extracted; ``context_integration`` has no slot for it.
#:     - ``dsdma_base.response_format``, ``idma.closing_reminder``,
#:       ``tsaspdma.closing_reminder``: no composer read them. DEADNESS IS
#:       PER-TEMPLATE, NOT PER-FIELD — the ``dsaspdma``/``idma``/``tsaspdma``/
#:       ``csdma_common_sense`` copies of ``response_format`` and the
#:       ``action_selection_pdma``/``dsaspdma`` copies of ``closing_reminder``
#:       are all read and all gated. These were latent production defects, not
#:       dead text; #990 composed them and they are gated now.
#:
#:   2.9.10 raises the floor 31 -> 39. Four keys joined the denominator (see
#:   EXPECTED_KEY_COUNTS above) and all four are gated; #990's composed fields
#:   and #993's appended ASPDMA guidance blocks are gated; and #997's per-field
#:   block emission means a replacement that used to move one 23 KB `mixed`
#:   message now moves the named field it actually reached. ONE key is still
#:   dark: ``action_selection_pdma.final_ponder_advisory`` (a fixture gap — it
#:   renders only on a thought's last permitted round).
#: * ``string`` 71/75 — the four remaining ``conscience.*`` keys land on
#:   ``ActionSelectionDMAResult.rationale`` / ``override_reason``, which no
#:   composition renders, or on override-fold branches needing the live
#:   conscience registry. The ``prompts.*`` sub-namespace is now 58/58, with
#:   nothing dark: #997's corpus split made all 29 ``language_guidance`` parts
#:   individually addressable, and the parent key became probe-PERFORMABLE
#:   again once R1 stopped reading a split block as an absent one
#:   (``research_overrides._bundle_has``).
#: * ``template`` 2/3 — ``domain`` is severed before the only factory that reads
#:   it: ``component_builder`` rebuilds the AgentTemplate from the graph without
#:   a ``domain``, so the field reaches no prompt at runtime.
GATED_FLOOR: Dict[str, int] = {
    "corpus": 4,
    "dma_prompt": 39,
    # 71/75 -> 76/132 in 2.9.10. The count went UP and the FRACTION went down,
    # and that is the honest number: #991 wired 57 `prompts.formatters.*` keys
    # that had 1,653 translations and no reader, and the probe fixture cannot
    # exercise most of them. They render into system-snapshot / identity /
    # user-profile blocks, and the compose fixture carries no populated snapshot
    # or profile — so they are FIXTURE-dark, not WIRING-dark. The distinction is
    # evidenced: #991 verified translated labels rendering end to end at
    # es/ja/am/ar, and en output byte-identical via the 12 goldens plus a
    # 17-render differential. Raising this floor by asserting they are covered
    # would be the exact move this check exists to prevent.
    # 76 -> 77 (#1010). The §7e directional guard
    # `prompts.language_guidance.26b_user_symptom_direction` joined the key
    # space and composes, so both the denominator and the gated count moved by
    # one. (#1012's `agent.still_processing` / `agent.processor_paused` are
    # NOT here and should not be: they are API replies to a user, they reach no
    # LLM prompt, and the probe measures the prompt key space.)
    "string": 77,
    "conscience_prompt": 12,
    "template": 2,
}

#: Sub-namespace floors. ``string`` is not uniform: the ``conscience.*`` retry
#: envelope was wholly dark before #986 and a single 46-key row would hide it
#: regressing back there.
SUBSPLIT_GATED_FLOOR: Dict[str, int] = {
    "string:conscience.*": 13,
    # 29 -> 58 in 2.9.10: the #997 language_guidance split, plus the parent key
    # becoming performable again. Nothing in this sub-namespace is dark.
    # 58 -> 63 of 115. Same story: the denominator grew by the 57 formatter keys.
    # 63 -> 64: the same single key, counted in its subsplit.
    "string:prompts.*": 64,
}


class ProbeUnit(BaseModel):
    """One atomic replacement: the keys swapped together in a single dump."""

    model_config = ConfigDict(extra="forbid")

    unit_id: str = Field(..., description="Stable identity, '<namespace>:<key>' (or ':accord.*' for the R5 group)")
    namespace: str = Field(..., description="Override namespace the keys belong to")
    keys: List[str] = Field(..., min_length=1, description="Keys replaced together in this unit")


class ProbeOutcome(BaseModel):
    """What one probe unit did to the dump."""

    model_config = ConfigDict(extra="forbid")

    unit_id: str
    namespace: str
    keys: List[str]
    blocks_moved: int = Field(..., ge=0, description="Blocks whose sha256 changed, appeared, or vanished")
    moved_block_ids: List[str] = Field(default_factory=list, description="'<locale>:<block_id>', sorted")
    error: Optional[str] = Field(default=None, description="Set when the probe could not be PERFORMED")

    @property
    def gated(self) -> bool:
        """A unit is gated iff its replacement provably reached the dump."""
        return self.error is None and self.blocks_moved > 0


class NamespaceCoverage(BaseModel):
    """One row of the coverage table."""

    model_config = ConfigDict(extra="forbid")

    namespace: str
    keys_total: int = Field(..., ge=0)
    keys_gated: int = Field(..., ge=0)
    blocks_moved: int = Field(..., ge=0, description="Distinct blocks moved by any unit in this namespace")
    errors: int = Field(default=0, ge=0, description="Units whose probe could not be performed")

    @property
    def keys_dark(self) -> int:
        return self.keys_total - self.keys_gated


class GateCoverageReport(BaseModel):
    """The measurement. ``keys_dark`` is the number this whole exercise exists for."""

    model_config = ConfigDict(extra="forbid")

    kind: str = Field(default="gate_coverage_report")
    locales: List[str]
    steps: Optional[List[str]] = Field(default=None, description="None = every step the fixture drives")
    residue_digest: str
    baseline_blocks: int = Field(..., ge=0, description="Blocks in the un-overridden dump")
    keys_total: int = Field(..., ge=0)
    keys_gated: int = Field(..., ge=0)
    keys_dark: int = Field(..., ge=0)
    namespaces: List[NamespaceCoverage]
    subsplits: List[NamespaceCoverage] = Field(default_factory=list)
    outcomes: List[ProbeOutcome] = Field(default_factory=list)


# --------------------------------------------------------------------------
# Key enumeration — same source of truth the facility validates against
# --------------------------------------------------------------------------


def namespace_keys() -> Dict[str, Tuple[str, ...]]:
    """Every override key, per namespace, straight from ``research_overrides``.

    Never hardcoded: if the reachable surface moves, this moves with it, and the
    regression test notices instead of comparing against a stale constant.
    """
    return {
        "corpus": tuple(sorted(_valid_corpus_keys())),
        # Schema-present, NOT R2-required: the immune keys (#989) are excluded from
        # R2 totality but must stay in the probe — measuring which keys are dark
        # is its purpose, and skipping them would blind it to #989 being fixed.
        "dma_prompt": tuple(sorted(_schema_present_dma_prompt_keys())),
        "string": tuple(sorted(scan_reachable_string_keys())),
        "conscience_prompt": tuple(sorted(_required_conscience_prompt_keys())),
        "template": tuple(sorted(_TEMPLATE_TEXT_FIELDS)),
    }


def probe_units(namespaces: Optional[Sequence[str]] = None) -> List[ProbeUnit]:
    """Split the key space into independently-replaceable units.

    One unit per key, except the accord corpus keys: R5 ("no partial covenant")
    refuses a manifest naming some accord keys and not others, so they can only
    be probed together. A unit is the FINEST granularity the facility permits.
    """
    wanted = tuple(namespaces) if namespaces else NAMESPACES
    units: List[ProbeUnit] = []
    all_keys = namespace_keys()
    for namespace in wanted:
        keys = all_keys[namespace]
        if namespace == "corpus":
            accord = sorted(_ACCORD_CORPUS_KEYS)
            if accord:
                units.append(ProbeUnit(unit_id="corpus:accord.*", namespace="corpus", keys=accord))
            for key in keys:
                if key in _ACCORD_CORPUS_KEYS:
                    continue
                units.append(ProbeUnit(unit_id=f"corpus:{key}", namespace="corpus", keys=[key]))
            continue
        for key in keys:
            units.append(ProbeUnit(unit_id=f"{namespace}:{key}", namespace=namespace, keys=[key]))
    return units


def _manifest_for(unit: ProbeUnit, residue_digest: str) -> str:
    """An ``additive`` manifest replacing exactly this unit with markers.

    ``additive`` (not ``strict``) because the probe deliberately changes ONE
    thing: strict mode demands totality, which would move every block at once
    and measure nothing. The marker is visible on purpose — if it ever surfaces
    in a real prompt it reads as a probe artefact, not as content.
    """
    overrides: Dict[str, Dict[str, str]] = {ns: {} for ns in NAMESPACES}
    for key in unit.keys:
        overrides[unit.namespace][key] = f"PROBE::{key}"
    manifest = {
        "manifest_version": "1",
        "experiment_id": f"gate-coverage-probe-{unit.unit_id}",
        "condition": "c",
        "base_locale": "en",
        "mode": "additive",
        "residue_digest": residue_digest,
        "overrides": overrides,
        "research_hashes": {},
    }
    return json.dumps(manifest, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------
# Running one probe
# --------------------------------------------------------------------------


def _dump(out_path: Path, locales: str, steps: Optional[str], manifest: Optional[Path], arm: str) -> Optional[str]:
    """Shell out to ``compose_dump dump``. Returns None on success, else the failure."""
    cmd = [
        sys.executable,
        "-m",
        "ciris_engine.logic.utils.compose_dump",
        "dump",
        "--arm",
        arm,
        "--locales",
        locales,
        "--out",
        str(out_path),
    ]
    if steps:
        cmd += ["--steps", steps]
    if manifest is not None:
        cmd += ["--manifest", str(manifest)]
    env = dict(os.environ)
    env["CIRIS_TESTING_MODE"] = "true"
    env.pop("CIRIS_RESEARCH_PROMPT_OVERRIDES", None)
    result = subprocess.run(cmd, cwd=_REPO_ROOT, env=env, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "").strip().splitlines()
        return " / ".join(tail[-3:]) if tail else f"exit {result.returncode}"
    return None


def _block_index(path: Path) -> Dict[str, str]:
    """``'<locale>:<block_id>' -> sha256`` for one dump."""
    _meta, rows = load_dump(str(path))
    return {f"{row.locale}:{row.block_id}": row.sha256 for row in rows}


def run_unit(
    unit: ProbeUnit,
    *,
    baseline: Dict[str, str],
    locales: str,
    steps: Optional[str],
    residue_digest: str,
) -> ProbeOutcome:
    """Replace one unit, re-dump, and report which blocks moved."""
    with tempfile.TemporaryDirectory(prefix="gate-probe-") as tmp:
        tmpdir = Path(tmp)
        manifest_path = tmpdir / "manifest.json"
        manifest_path.write_text(_manifest_for(unit, residue_digest), encoding="utf-8")
        dump_path = tmpdir / "probe.jsonl"
        failure = _dump(dump_path, locales, steps, manifest_path, arm=f"probe-{unit.namespace}")
        if failure is not None:
            return ProbeOutcome(
                unit_id=unit.unit_id, namespace=unit.namespace, keys=list(unit.keys), blocks_moved=0, error=failure
            )
        probed = _block_index(dump_path)

    # A block "moves" if its bytes changed, or if it appeared/vanished — a
    # replacement that changes the BLOCK SPACE is also visible to the gate
    # (assertion 1 reports block-space mismatch), so it counts as gated.
    moved = sorted(
        key
        for key in set(baseline) | set(probed)
        if baseline.get(key) != probed.get(key)
    )
    return ProbeOutcome(
        unit_id=unit.unit_id,
        namespace=unit.namespace,
        keys=list(unit.keys),
        blocks_moved=len(moved),
        moved_block_ids=moved,
    )


def probe(
    *,
    locales: Sequence[str] = ("en",),
    steps: Optional[Sequence[str]] = None,
    namespaces: Optional[Sequence[str]] = None,
    jobs: int = 4,
) -> GateCoverageReport:
    """Run the full sweep and return the coverage report."""
    locales_arg = ",".join(locales)
    steps_arg = ",".join(steps) if steps else None
    residue_digest = compute_residue_digest()

    with tempfile.TemporaryDirectory(prefix="gate-probe-base-") as tmp:
        base_path = Path(tmp) / "baseline.jsonl"
        failure = _dump(base_path, locales_arg, steps_arg, None, arm="baseline")
        if failure is not None:
            raise SystemExit(f"baseline dump FAILED — nothing can be measured against it: {failure}")
        baseline = _block_index(base_path)

    units = probe_units(namespaces)
    outcomes: List[ProbeOutcome] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        futures = {
            pool.submit(
                run_unit, unit, baseline=baseline, locales=locales_arg, steps=steps_arg, residue_digest=residue_digest
            ): unit
            for unit in units
        }
        for future in concurrent.futures.as_completed(futures):
            outcomes.append(future.result())
    outcomes.sort(key=lambda o: (NAMESPACES.index(o.namespace), o.unit_id))

    all_keys = namespace_keys()
    wanted = tuple(namespaces) if namespaces else NAMESPACES
    rows: List[NamespaceCoverage] = []
    for namespace in wanted:
        subset = [o for o in outcomes if o.namespace == namespace]
        rows.append(
            NamespaceCoverage(
                namespace=namespace,
                keys_total=len(all_keys[namespace]),
                keys_gated=sum(len(o.keys) for o in subset if o.gated),
                blocks_moved=len({b for o in subset for b in o.moved_block_ids}),
                errors=sum(1 for o in subset if o.error is not None),
            )
        )

    subsplits: List[NamespaceCoverage] = []
    for label, prefix in SUBSPLITS:
        namespace = label.split(":", 1)[0]
        if namespace not in wanted:
            continue
        subset = [o for o in outcomes if o.namespace == namespace and all(k.startswith(prefix) for k in o.keys)]
        if not subset:
            continue
        subsplits.append(
            NamespaceCoverage(
                namespace=label,
                keys_total=sum(1 for k in all_keys[namespace] if k.startswith(prefix)),
                keys_gated=sum(len(o.keys) for o in subset if o.gated),
                blocks_moved=len({b for o in subset for b in o.moved_block_ids}),
                errors=sum(1 for o in subset if o.error is not None),
            )
        )

    keys_total = sum(r.keys_total for r in rows)
    keys_gated = sum(r.keys_gated for r in rows)
    return GateCoverageReport(
        locales=list(locales),
        steps=list(steps) if steps else None,
        residue_digest=residue_digest,
        baseline_blocks=len(baseline),
        keys_total=keys_total,
        keys_gated=keys_gated,
        keys_dark=keys_total - keys_gated,
        namespaces=rows,
        subsplits=subsplits,
        outcomes=outcomes,
    )


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------


def format_report(report: GateCoverageReport) -> str:
    """The coverage table, in the shape the #986 finding is stated in."""
    lines: List[str] = []
    lines.append(f"gate coverage: locales={','.join(report.locales)} baseline_blocks={report.baseline_blocks}")
    lines.append(f"residue_digest: {report.residue_digest}")
    lines.append("")
    lines.append("| namespace | keys | gated | dark | blocks moved |")
    lines.append("|---|---|---|---|---|")
    for row in list(report.namespaces) + list(report.subsplits):
        marker = "" if row.keys_dark == 0 else "  <- DARK" if row.keys_gated == 0 else "  <- partial"
        lines.append(
            f"| {row.namespace} | {row.keys_total} | {row.keys_gated} | {row.keys_dark} | {row.blocks_moved} |{marker}"
        )
    lines.append("")
    lines.append(
        f"{report.keys_dark} of {report.keys_total} keys are INVISIBLE to the gate "
        f"(a regime could vary them and still get GATE: PASS)."
    )
    errors = [o for o in report.outcomes if o.error is not None]
    if errors:
        lines.append("")
        lines.append(f"{len(errors)} probe(s) could not be PERFORMED (not the same as 'dark'):")
        for outcome in errors:
            lines.append(f"  {outcome.unit_id}: {outcome.error}")
    dark = [o for o in report.outcomes if not o.gated and o.error is None]
    if dark:
        lines.append("")
        lines.append("dark units:")
        for outcome in dark:
            lines.append(f"  {outcome.unit_id}")
    return "\n".join(lines)


def check_floors(report: GateCoverageReport) -> List[str]:
    """Every way the measured coverage falls short of the #986 lock. Empty = ok."""
    problems: List[str] = []

    counts = {namespace: len(keys) for namespace, keys in namespace_keys().items()}
    if counts != EXPECTED_KEY_COUNTS:
        problems.append(
            f"key space moved: {counts} != {EXPECTED_KEY_COUNTS} — the floors below are stated "
            f"against the old denominator and must be re-derived, not silently passed"
        )

    for outcome in report.outcomes:
        if outcome.error is not None:
            problems.append(
                f"{outcome.unit_id}: probe could not be PERFORMED ({outcome.error}) — "
                f"an unperformable probe is not a dark key and must not be scored as one"
            )

    measured = {row.namespace: row for row in report.namespaces}
    measured.update({row.namespace: row for row in report.subsplits})
    for label, floor in list(GATED_FLOOR.items()) + list(SUBSPLIT_GATED_FLOOR.items()):
        row = measured.get(label)
        if row is None:
            continue
        if row.keys_gated < floor:
            problems.append(
                f"{label}: {row.keys_gated} gated keys, floor is {floor} — the gate can see FEWER "
                f"override keys than at #986. A key the dump no longer composes is a key a regime "
                f"could vary while the gate still reports GATE: PASS"
            )
    return problems


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python3 -m tools.research.probe_gate_coverage",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--locales", default="en", help="comma-separated locales to compose")
    parser.add_argument("--steps", default=None, help="comma-separated steps (default: every step)")
    parser.add_argument(
        "--namespace", action="append", default=None, choices=list(NAMESPACES), help="restrict to namespace(s)"
    )
    parser.add_argument("--jobs", type=int, default=4, help="parallel probe subprocesses")
    parser.add_argument("--json", default=None, help="also write the machine-readable report here")
    parser.add_argument(
        "--assert-floors",
        action="store_true",
        help="exit non-zero if any namespace's gated-key count fell below its #986 floor. This is "
        "the regression lock — it runs in the compose-gate CI job, where a full sweep has a "
        "budget it does not have inside the sharded unit-test run.",
    )
    args = parser.parse_args(argv)

    # Refuse BEFORE the sweep, not after: the sweep is ~100 compositions and an
    # operator should not pay for it to be told the invocation was invalid.
    if args.assert_floors and (args.namespace or args.steps):
        raise SystemExit(
            "--assert-floors measures the WHOLE key space against the whole composed surface; "
            "it cannot be combined with --namespace or --steps (a partial sweep would compare a "
            "subset against floors derived from the full one, and pass for the wrong reason)"
        )

    report = probe(
        locales=[loc.strip() for loc in args.locales.split(",") if loc.strip()],
        steps=[s.strip() for s in args.steps.split(",") if s.strip()] if args.steps else None,
        namespaces=args.namespace,
        jobs=args.jobs,
    )
    print(format_report(report))
    if args.json:
        Path(args.json).write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.json}", file=sys.stderr)

    if args.assert_floors:
        problems = check_floors(report)
        if problems:
            print("")
            for problem in problems:
                print(f"FAIL {problem}")
            print(f"COVERAGE: FAIL — {len(problems)} regression(s)")
            return 1
        print("\nCOVERAGE: PASS — no namespace lost gated keys")
    return 0


if __name__ == "__main__":
    sys.exit(main())
