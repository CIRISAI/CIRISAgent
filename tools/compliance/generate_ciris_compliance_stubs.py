#!/usr/bin/env python3
"""Generate CIRIS Agent per-dimension compliance stub markdown files.

Reads SEED_DIMENSIONS.yaml and produces one stub per dimension under
the target directory (default: ../CIRISAgent/compliance/). Each stub
has two regions:

  (1) Auto-rendered structural fields — regulatory attestations, wire
      primitives, convergence note, conflicts, T-3 candidates. These
      regenerate on every script run; humans MUST NOT hand-edit.

  (2) Human-authored sections — CIRIS-side compliance implementation,
      observability hooks, known gaps. These are TODO blocks; humans
      fill them in per-dimension. The script preserves these on
      regeneration via fenced markers.

Usage:
  python3 tools/compliance/generate_ciris_compliance_stubs.py [seed_path] [output_dir]

The script is idempotent: re-running preserves human-authored content
between `<!-- BEGIN HUMAN -->` / `<!-- END HUMAN -->` fences while
refreshing the auto-rendered sections.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent
DEFAULT_SEED = REPO_ROOT / "SEED_DIMENSIONS.yaml"
DEFAULT_OUTPUT = REPO_ROOT.parent / "CIRISAgent" / "compliance"

HUMAN_BEGIN = "<!-- BEGIN HUMAN -->"
HUMAN_END = "<!-- END HUMAN -->"


def load_seed(path: Path) -> dict:
    with path.open() as f:
        return yaml.safe_load(f)


def slugify_prefix(prefix: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", prefix.lower())
    return s.strip("_")


def conflicts_for_dimension(seed: dict, dim_id: str) -> list[dict]:
    return [c for c in seed["aggregate_indices"]["conflicts_surfaced"] if dim_id in c.get("dimensions", [])]


def t3_for_dimension(seed: dict, dim_id: str) -> list[dict]:
    return [t for t in seed["aggregate_indices"]["t3_candidates_v1_5"] if t.get("affects_dimension") == dim_id]


HUMAN_TEMPLATE = """\
## CIRIS-side compliance implementation

TODO — Fill in the code/policy/test surface that implements CIRIS Agent compliance with this dimension. Suggested fields:

- **Code references**: modules / handlers / services / DMAs / conscience faculties implementing this
- **Policy text**: relevant text in `MISSION_CIRISAgent.md`, `prohibitions.py`, `pdma_*.yml`, `language_guidance/*`
- **Test coverage**: pointer to test files exercising this dimension
- **Configuration surface**: relevant schemas / config blocks

Proposed pointer (from seed): `{proposed_compliance_pointer}`

## Observability hooks

TODO — Fill in monitoring / observability surface:

- **LensCore detectors**: which F-3 / Coherence Ratchet detectors observe this?
- **RATCHET calibration**: which calibration packages apply?
- **Audit chain queries**: how would a downstream consumer verify compliance?
- **Federation evidence_refs**: emitted Contributions with `dimensions: [\"{dim_id}\"]`

Proposed pointer (from seed): `{proposed_monitors_pointer}`

## Known gaps / not-yet-implemented

TODO — Honestly catalog anything this dimension requires that CIRIS Agent does not yet implement. Reference relevant `GAPS.md` entries from the response repo if applicable.
"""


def render_auto_section(dim: dict, batches_by_id: dict, seed: dict, seed_version: str) -> str:
    parts: list[str] = []

    counts = dim["attestations"]
    parts.append(f"# {dim['id']} — `{dim['prefix']}` ({dim['tier']})")
    parts.append("")
    parts.append(f"> {dim['gloss']}")
    parts.append("")
    parts.append(
        f"**Seed reference**: `SEED_DIMENSIONS.yaml` v{seed_version}, dimension `{dim['id']}` "
        f"([source](https://github.com/CIRISAI/ciris-response-magnifica-humanitas/blob/main/SEED_DIMENSIONS.yaml))"
    )
    parts.append(f"**Accord principle**: {dim['accord_principle']}")
    parts.append(
        f"**Attestation density**: MH={counts['MH']} · EU={counts['EU']} · "
        f"IEEE={counts['IEEE']} · ASEAN={counts['ASEAN']} · total={counts['total']}"
    )
    parts.append("")

    absent = dim.get("absent_batch") or []
    if absent:
        for ab in absent:
            bshort = batches_by_id.get(ab["batch_id"], {}).get("short", ab["batch_id"])
            parts.append(f"**Absent from**: {bshort} — {ab['absence_note']}")
            if ab.get("functional_analogue"):
                parts.append(f"  *Functional analogue*: {ab['functional_analogue']}")
            parts.append("")

    parts.append("## Regulatory attestations")
    parts.append("")
    parts.append("*(Auto-rendered from seed; do not hand-edit. Re-run `python tools/compliance/generate_ciris_compliance_stubs.py tools/compliance/SEED_DIMENSIONS.yaml compliance/` after seed updates.)*")
    parts.append("")
    for ra in dim["regulatory_attestations"]:
        b = batches_by_id.get(ra["batch_id"], {})
        bshort = b.get("short", ra["batch_id"])
        btitle = b.get("title", ra["batch_id"])
        parts.append(f"- **{bshort}** ({btitle}) — *{ra['citation']}*")
        parts.append(f'    > "{ra["language"]}"')
        parts.append(f"    Wire form: `{ra['wire_form']}`")
    parts.append("")

    parts.append("## Wire primitives")
    parts.append("")
    for p in dim["wire_primitives"]:
        parts.append(f"- `{p}`")
    parts.append("")

    note = dim.get("convergence_note")
    if note:
        parts.append("## Convergence note")
        parts.append("")
        parts.append(note)
        parts.append("")

    conflicts = conflicts_for_dimension(seed, dim["id"])
    if conflicts:
        parts.append("## Cross-source conflicts involving this dimension")
        parts.append("")
        for c in conflicts:
            parts.append(f"- **{c['id']}** ({c['type']}, severity {c['severity']}): {c['claim']}")
            if c.get("disposition"):
                parts.append(f"    Disposition: {c['disposition']}")
        parts.append("")

    t3s = t3_for_dimension(seed, dim["id"])
    if t3s:
        parts.append("## v1.5+ T-3 candidates affecting this dimension")
        parts.append("")
        for t in t3s:
            srcs = ", ".join(t.get("source") or [])
            parts.append(f"- **{t['id']}** `{t['proposed_prefix']}` (priority {t['priority']}, source(s): {srcs})")
        parts.append("")

    return "\n".join(parts)


def extract_human(existing_text: str) -> str | None:
    if HUMAN_BEGIN not in existing_text or HUMAN_END not in existing_text:
        return None
    start = existing_text.index(HUMAN_BEGIN) + len(HUMAN_BEGIN)
    end = existing_text.index(HUMAN_END)
    return existing_text[start:end].strip("\n")


def build_stub(dim: dict, batches_by_id: dict, seed: dict, seed_version: str, existing_path: Path | None) -> str:
    auto = render_auto_section(dim, batches_by_id, seed, seed_version)

    existing_human: str | None = None
    if existing_path is not None and existing_path.exists():
        existing_human = extract_human(existing_path.read_text())

    if existing_human:
        human_body = existing_human
    else:
        proposed_compliance = (dim.get("ciris_compliance") or {}).get("proposed_pointer") or "(none specified in seed; please fill)"
        proposed_monitors = (dim.get("monitors") or {}).get("proposed_pointer") or "(none specified in seed; please fill)"
        human_body = HUMAN_TEMPLATE.format(
            proposed_compliance_pointer=proposed_compliance,
            proposed_monitors_pointer=proposed_monitors,
            dim_id=dim["id"],
        )

    return (
        auto
        + "\n---\n\n"
        + HUMAN_BEGIN
        + "\n"
        + human_body.strip("\n")
        + "\n"
        + HUMAN_END
        + "\n"
    )


def generate(seed_path: Path, output_dir: Path) -> None:
    seed = load_seed(seed_path)
    seed_version = seed["metadata"]["seed_version"]
    batches_by_id = {b["id"]: b for b in seed["batches"]}

    output_dir.mkdir(parents=True, exist_ok=True)

    written = 0
    preserved = 0
    for dim in seed["dimensions"]:
        filename = f"{dim['id']}_{slugify_prefix(dim['prefix'])}.md"
        path = output_dir / filename

        previously_existed = path.exists()
        content = build_stub(dim, batches_by_id, seed, seed_version, path if previously_existed else None)
        path.write_text(content)
        written += 1
        if previously_existed:
            preserved += 1
        print(f"  {'updated' if previously_existed else 'created'}: {filename}")

    print(f"\nWrote {written} stubs to {output_dir}")
    if preserved:
        print(f"Preserved human-authored content in {preserved} pre-existing stubs.")


if __name__ == "__main__":
    seed_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_SEED
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_OUTPUT
    generate(seed_path, output_dir)
