#!/usr/bin/env python3
"""Review-only pass: the pipeline's own MQM judge over one language's live
corpus, with NO repair and NO write. A diagnostic, not a lane.

Why it exists: run the hardest language first and let it back-inform the
English. Yoruba on ciris.ai did exactly that: where the judge cannot make sense of the Yoruba,
the English is usually the ambiguous party. The evaluate lane repairs as it
goes and drops the initial findings of anything it fixed, so to READ the
findings you need a pass that only reads. This is that pass. It costs one
review call per chunk (cheap) and moves no money up the ladder.

Usage:
  LOCALIZE_BUNDLE=dictionaries python3 localization/review_only.py --lang yo \
      [--keys 'pat.*' ...] [--chunk 150] [--out localization/hard-cases/review-yo]
Writes <out>.json (findings with English + translation) and <out>.md (triage
by section, worst first, with the judge's notes) and prints the spend.
"""
from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

if not os.environ.get("OPENROUTER_API_KEY"):
    kf = Path.home() / ".openrouter_key"
    if kf.exists():
        os.environ["OPENROUTER_API_KEY"] = kf.read_text().strip()

import localize as L  # noqa: E402  (verbatim upstream module; used read-only here)

# Comma-separated key prefixes to leave out (dead or retired copy), e.g.
# REVIEW_SKIP_PREFIXES="oldLanding.,retiredPage." Nothing is skipped by default.
SKIP = tuple(p for p in os.environ.get("REVIEW_SKIP_PREFIXES", "").split(",") if p)
SOURCE_HINT = re.compile(
    r"ambigu|idiom|metaphor|source (is|text|phrase|wording)|in English|the English|"
    r"unclear|two readings|could mean|pun|wordplay|colloquial|figurative|literal rendering|"
    r"fragment|incomplete|elliptical|dangling|referent", re.I)


def live_keys(en_flat: dict, patterns: list[str]) -> list[str]:
    keys = []
    for k in sorted(en_flat):
        if patterns and not any(fnmatch.fnmatch(k, p) for p in patterns):
            continue
        if SKIP and k.startswith(SKIP):
            continue
        if not isinstance(en_flat[k], str) or not en_flat[k].strip():
            continue
        keys.append(k)
    return keys


def chunks(keys: list[str], size: int) -> list[list[str]]:
    by_sec: dict[str, list[str]] = defaultdict(list)
    for k in keys:
        by_sec[k.split(".")[0]].append(k)
    out: list[list[str]] = []
    for sec in by_sec:
        ks = by_sec[sec]
        for i in range(0, len(ks), size):
            out.append(ks[i:i + size])
    return out


def unreviewed(errs: list[dict]) -> bool:
    return any(str(e.get("note", "")).startswith(("reviewer unreachable", "review reply unparseable",
                                                   "no valid review")) for e in errs)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--lang", required=True)
    ap.add_argument("--keys", action="append", default=[])
    ap.add_argument("--chunk", type=int, default=150)
    ap.add_argument("--out", default=None)
    ap.add_argument("--retries", type=int, default=3)
    args = ap.parse_args()

    L.REVIEW_MODEL = L._review_model()
    bundle = L.CANONICAL.name
    en_flat = L.guard.flat_values(L.load(L.CANONICAL / "en.json"))
    lang_flat = L.guard.flat_values(L.load(L.CANONICAL / f"{args.lang}.json"))
    keys = live_keys(en_flat, args.keys)
    present = [k for k in keys if isinstance(lang_flat.get(k), str) and lang_flat[k].strip()]
    missing = [k for k in keys if k not in present]
    out = Path(args.out or (HERE / "hard-cases" / f"review-{args.lang}-{bundle}"))
    out.parent.mkdir(exist_ok=True)
    print(f"[review-only] {args.lang} / {bundle}: {len(present)} live key(s) to judge, "
          f"{len(missing)} missing in this language, reviewer={L.REVIEW_MODEL}", flush=True)

    spend = L.Spend()
    findings: dict[str, list[dict]] = {}
    for i, ch in enumerate(chunks(present, args.chunk), 1):
        values = {k: lang_flat[k] for k in ch}
        for attempt in range(1, args.retries + 1):
            got = L.evaluate_lane(args.lang, values, en_flat, spend, log=lambda m: print(m, flush=True))
            bad = [k for k, e in got.items() if unreviewed(e)]
            if not bad:
                break
            print(f"[review-only] chunk {i}: {len(bad)} unreviewed (provider); retry {attempt}/{args.retries} in 120s", flush=True)
            time.sleep(120)
            values = {k: lang_flat[k] for k in bad}
            got = {**{k: e for k, e in got.items() if not unreviewed(e)}, **got}
        findings.update(got)
        flagged = sum(1 for e in got.values() if e)
        print(f"[review-only] chunk {i}/{len(chunks(present, args.chunk))} {ch[0].split('.')[0]}: "
              f"{flagged}/{len(ch)} flagged", flush=True)

    # ── report ──────────────────────────────────────────────────────────────
    doc = {"lang": args.lang, "bundle": bundle, "keys": len(present), "missing": missing,
           "findings": {k: {"en": en_flat[k], args.lang: lang_flat[k], "errors": e}
                        for k, e in findings.items() if e}}
    out.with_suffix(".json").write_text(json.dumps(doc, indent=2, ensure_ascii=False))

    sev = Counter(); cat = Counter(); repairable = 0; source_side = []
    for k, e in findings.items():
        if not e:
            continue
        if L.needs_repair(e):
            repairable += 1
        for x in e:
            sev[x.get("severity")] += 1; cat[x.get("category")] += 1
            if SOURCE_HINT.search(str(x.get("note", ""))):
                source_side.append(k)
    lines = [f"# Review-only: {args.lang} / {bundle}", "",
             f"{len(present)} keys judged; {sum(1 for e in findings.values() if e)} with findings; "
             f"{repairable} would trigger repair (critical/major or terminology).", "",
             f"Severity: {dict(sev)}  Category: {dict(cat)}", "",
             f"Notes that point at the ENGLISH ({len(set(source_side))} keys): "
             + ", ".join(sorted(set(source_side))[:60]), ""]
    by_sec: dict[str, list[str]] = defaultdict(list)
    for k, e in findings.items():
        if e:
            by_sec[k.split(".")[0]].append(k)
    order = {"critical": 0, "major": 1, "minor": 2}
    for sec in sorted(by_sec, key=lambda s: -len(by_sec[s])):
        lines.append(f"## {sec} ({len(by_sec[sec])} flagged)")
        for k in sorted(by_sec[sec], key=lambda k: min(order.get(x.get("severity"), 3) for x in findings[k])):
            lines.append(f"- **{k}**  EN: {en_flat[k][:160]!r}")
            lines.append(f"  {args.lang}: {lang_flat[k][:160]!r}")
            for x in findings[k]:
                lines.append(f"  - {x.get('severity')}/{x.get('category')}: {str(x.get('note',''))[:260]}"
                             + (f"  → {x.get('suggestion')[:120]!r}" if x.get("suggestion") else ""))
        lines.append("")
    out.with_suffix(".md").write_text("\n".join(lines))
    print("\nspend (estimate):"); print(spend.report())
    print(f"[review-only] wrote {out.with_suffix('.json').name} and {out.with_suffix('.md').name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
