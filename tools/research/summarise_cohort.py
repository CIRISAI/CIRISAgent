#!/usr/bin/env python3
"""Summarise a captured CEG cohort into a markdown block.

Extracted from the workflow rather than inlined as a heredoc so it can be tested
and run by hand against a downloaded artifact.

It reports three things the campaign has been bitten by:

1. AN EMPTY COHORT, loudly. A run that evaluates cleanly and captures nothing
   once reported "Success Rate 100.0%" while writing zero trace files, and
   anything scoring it computed over an empty set and called the result clean.

2. CONSTANT SCALARS. A feature with no variance is dropped at the retention
   gate, so a cohort can report a sixteen-feature projection while measuring
   fewer, with nothing in the output saying so. Constancy is usually either an
   unmeasured upstream field or a corpus too small to vary — both worth knowing
   before a number is quoted.

3. A DECLARED CONDITION CONTRADICTED BY RUNTIME STATE — the sealed
   `condition_attestation`. A run labelled (c) whose faculties were skipped is
   not a (c) run, and scoring it under that label produces a confident wrong
   answer rather than a noisy one.
"""

from __future__ import annotations

import collections
import glob
import json
import re
import sys

SCALARS = ("entropy_score", "coherence_score", "entropy_level", "coherence_level")


def main(root: str) -> int:
    files = sorted(glob.glob(f"{root}/**/ceg-seal-*.json", recursive=True))
    print("\n### Cohort\n")
    if not files:
        print("**No traces captured.** Anything scoring this cohort would compute over an empty set.")
        print("\nCheck the adapter log for `Local-copy` / `CEG seal` lines — every path logs its verdict,")
        print("including why it wrote nothing.")
        return 0

    signed = 0
    with_attestation = 0
    contradictions = []
    values: dict[str, set[str]] = collections.defaultdict(set)

    for f in files:
        try:
            d = json.load(open(f))
        except Exception:  # noqa: BLE001 — a malformed file should not hide the rest
            continue
        signed += int(d.get("signed_rows") or 0)
        ca = d.get("condition_attestation")
        if ca:
            with_attestation += 1
            if ca.get("contradicts_declaration"):
                contradictions.append((d.get("trace_id"), ca.get("declared_condition"), ca.get("implied_condition")))
        blob = json.dumps(d.get("ceg_rows") or [])
        for key in SCALARS:
            for m in re.finditer(rf'"{key}"\s*:\s*([0-9.]+)', blob):
                values[key].add(m.group(1))

    print(f"- documents: **{len(files)}** · PQC-signed rows: **{signed}**")
    print(f"- carrying `condition_attestation`: **{with_attestation}/{len(files)}**")
    if with_attestation == 0:
        print("  - ⚠️ none carry it — this capture predates the attestation, so a")
        print("    consistency gate over it would return zero contradictions and read as a pass.")
        print("    **An absent gate is not a satisfied gate.**")

    print("\n**Scalars**\n")
    for key in SCALARS:
        vals = sorted(values.get(key, set()))
        if not vals:
            continue
        if len(vals) == 1:
            print(f"- `{key}`: {vals} ⚠️ **CONSTANT** — no variance, dropped at the retention gate")
        else:
            print(f"- `{key}`: {vals}")

    if contradictions:
        print("\n**DECLARED CONDITION CONTRADICTED BY RUNTIME STATE**\n")
        for trace_id, declared, implied in contradictions:
            print(f"- `{trace_id}`: declared `{declared}`, runtime implies `{implied}`")
        print("\nThis cohort must not be scored under the declared arm.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "research-traces"))
