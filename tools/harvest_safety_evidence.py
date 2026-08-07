"""Backfill safety-battery evidence out of expiring Actions artifacts into the repo.

DESTINATION — settled by what already writes there, not invented here:

    qa_reports/safety_battery/<lang>_<domain>_<capTS>/      results.jsonl, summary.json, manifest_signed.json
    qa_reports/safety_interpret/<lang>_<domain>_<capTS>_<intTS>/  verdicts.jsonl, verdicts_summary.json, manifest_signed.json

That is where `tools/qa_runner` writes on a local run, what `safety-battery.yml`
globs for (`ls -td qa_reports/safety_battery/${LANG}_${DOMAIN}_*`), and — the
part that makes this replicable — it is the artifact's OWN internal layout. A
capture zip contains `safety_battery/<bundle>/…`; an interpret zip contains
`safety_interpret/<bundle>/…`. So restoring is `unzip -d qa_reports/` with no
rename and no mapping table to drift out of date.

TRACES ARE EXCLUDED, deliberately. A capture artifact averages 4.6 MB and is
99.9% `traces/` — 19 MB of lens batches against 15 KB of questions and answers.
The reasoning stream is a different artifact class with a different retention
question; it belongs in a Release, not in git. What is taken here is the
evidence a reader needs to check a verdict: the question, the answer, the
per-criterion judgement, and the signed manifest that says the pair was not
edited afterwards.

Why this exists: artifacts expire at 90 days. When this was written, 20,894 of
the repo's 24,109 artifacts were already gone and the oldest live battery
evidence was dated 2026-05-11 — inside days of the cliff. A ledger that says
"q08 failed U2" without the answer that failed it is an assertion, not evidence.

Run by `.github/workflows/safety-evidence-sync.yml` on a schedule against main,
rather than from the battery workflow itself. Three reasons, in order of weight:

  1. Batteries run on pull_request branches. Committing evidence there lands it
     on a branch that may never merge, and evidence that depends on a merge is
     evidence that can be lost by a decision unrelated to it.
  2. A commit step inside the battery makes the battery fail when the commit
     fails. The artifact is the source of truth at run time; the repo is the
     durable copy. Coupling them means a git error can lose a run's verdict.
  3. It self-heals. This is idempotent — it writes only bytes that differ — so a
     sync missed to an outage, a runner failure or a red main is picked up by
     the next one with no operator action. That is not hypothetical: the day
     this was written, GitHub Actions was in a major outage for hours and
     several battery runs were cancelled mid-flight.

IDEMPOTENT BY CONSTRUCTION: a file already present with identical bytes is
skipped, so re-running produces an empty diff. That is what makes "catch up
everything still alive" a safe default instead of a churn machine.
"""

from __future__ import annotations

import io
import json
import pathlib
import subprocess
import sys
import zipfile

REPO = "CIRISAI/CIRISAgent"
DEST = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "qa_reports")

#: Everything except the reasoning traces. Names are matched on the basename so
#: the artifact's directory structure is preserved exactly as-is.
KEEP = {"results.jsonl", "summary.json", "manifest_signed.json",
        "verdicts.jsonl", "verdicts_summary.json"}


def live_artifacts() -> list[dict]:
    raw = subprocess.run(
        ["gh", "api", f"repos/{REPO}/actions/artifacts?per_page=100", "--paginate",
         "--jq", ".artifacts[] | select(.expired == false) | {id, name, created_at, size: .size_in_bytes}"],
        capture_output=True, text=True, check=False).stdout
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            a = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "safety-battery-capture" in a["name"] or "safety-battery-interpret" in a["name"]:
            out.append(a)
    return out


def extract(art_id: int) -> list[pathlib.Path]:
    """Pull the small evidence files out of one artifact zip, preserving paths."""
    proc = subprocess.run(["gh", "api", f"repos/{REPO}/actions/artifacts/{art_id}/zip"],
                          capture_output=True, check=False)
    if proc.returncode != 0 or not proc.stdout:
        return []
    try:
        zf = zipfile.ZipFile(io.BytesIO(proc.stdout))
    except zipfile.BadZipFile:
        return []
    written = []
    for name in zf.namelist():
        base = name.rsplit("/", 1)[-1]
        if base not in KEEP:
            continue                      # traces/ and anything else stays out
        if "/traces/" in name:
            continue
        target = DEST / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data = zf.read(name)
        if target.exists() and target.read_bytes() == data:
            continue
        target.write_bytes(data)
        written.append(target)
    return written


def main() -> int:
    arts = live_artifacts()
    caps = [a for a in arts if "capture" in a["name"]]
    ints = [a for a in arts if "interpret" in a["name"]]
    print(f"  live: {len(caps)} capture + {len(ints)} interpret", flush=True)

    total, failed = 0, 0
    for i, a in enumerate(arts, 1):
        w = extract(a["id"])
        if not w and "interpret" in a["name"]:
            failed += 1
        total += len(w)
        if i % 25 == 0:
            print(f"    {i}/{len(arts)} … {total} files written", flush=True)

    bundles_b = len(list((DEST / "safety_battery").glob("*"))) if (DEST / "safety_battery").exists() else 0
    bundles_i = len(list((DEST / "safety_interpret").glob("*"))) if (DEST / "safety_interpret").exists() else 0
    size = sum(p.stat().st_size for p in DEST.rglob("*") if p.is_file())
    print(f"  wrote {total} files, {failed} artifacts yielded nothing")
    print(f"  bundles now: safety_battery={bundles_b}  safety_interpret={bundles_i}")
    print(f"  qa_reports total: {size/1048576:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
