"""Build the static data the results page renders from.

Reads the committed evidence — `qa_reports/safety_battery/` (question + answer)
and `qa_reports/safety_interpret/` (per-criterion verdict) — joins them, and
writes `docs/results/data/`:

    index.json          one row per interpret run; what the sortable table shows
    runs/<bundle>.json  the drill-down: every question, the agent's answer, and
                        each criterion's verdict with the span it cited
    rubrics/<id>.json   criterion id -> summary, severity, rationale, query

The join is `capture.agent_task_id == verdict.response_id`. A verdict whose
response is missing is REPORTED, never dropped: a page that silently shows 62 of
63 verdicts is the same defect class this repo keeps finding, so an unjoinable
verdict renders with its answer marked absent instead of vanishing.

Per-run files rather than one ledger, for two reasons that agree: the 250 KB
pre-commit cap, and the page only needs one run's detail at a time — so the
index stays small and the detail loads on click.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sys
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
CAP = ROOT / "qa_reports/safety_battery"
INT = ROOT / "qa_reports/safety_interpret"
RUBRICS = ROOT / "tests/safety"
OUT = ROOT / "docs/results/data"

BUNDLE = re.compile(r"^([a-z]{2})_([a-z_]+)_(\d{8}T\d{6}Z)(?:_(\d{8}T\d{6}Z))?$")


def read_jsonl(p: pathlib.Path) -> list[dict]:
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def captures_by_ts() -> dict[str, dict]:
    """capture timestamp -> {response_id: capture row}."""
    out: dict[str, dict] = {}
    for d in sorted(CAP.iterdir()) if CAP.exists() else []:
        m = BUNDLE.match(d.name)
        if not m:
            continue
        rows = read_jsonl(d / "results.jsonl")
        if rows:
            out[m.group(3)] = {r.get("agent_task_id"): r for r in rows}
    return out


def rubrics() -> dict[str, dict]:
    """rubric_id -> {criterion_id: {...}} from the in-repo rubric files."""
    out: dict[str, dict] = {}
    for f in sorted(RUBRICS.rglob("*canonical_universal_criteria.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        rid = d.get("rubric_id")
        if not rid:
            continue
        out[rid] = {
            "rubric_id": rid,
            "rubric_version": d.get("rubric_version"),
            "cell": d.get("cell"),
            "criteria": {
                c["id"]: {
                    "id": c.get("id"),
                    "summary": c.get("summary"),
                    "severity": c.get("severity"),
                    "rationale": c.get("rationale"),
                    "query": (c.get("args") or {}).get("query"),
                }
                for c in d.get("universal", [])
                if c.get("id")
            },
        }
    return out


def batteries() -> dict[str, dict]:
    """language -> the 9-question arc, so the page can SHOW the questions.

    The page previously published rubrics but not questions, so a reader could
    see how an answer was judged and never see what was asked — the criteria
    without the stimulus. Both halves are needed to understand a verdict, and
    neither should require reading the repo.

    Question text is per-language and lives in `translations`; a language whose
    arc has not been translated yet falls back to English so the page shows the
    question rather than a blank.
    """
    out: dict[str, dict] = {}
    for f in sorted(RUBRICS.rglob("*_mental_health_arc.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        lang = (d.get("cell") or {}).get("language")
        if not lang:
            continue
        qs = []
        for q in d.get("questions", []):
            tr = q.get("translations") or {}
            qs.append(
                {
                    "id": q.get("question_id"),
                    "stage": q.get("stage"),
                    "evaluates": q.get("evaluates"),
                    "text": tr.get(lang) or tr.get("en") or "",
                    "translated": bool(tr.get(lang)),
                    "hard_fail_triggers": q.get("hard_fail_triggers"),
                }
            )
        out[lang] = {
            "language": lang,
            "battery_id": d.get("battery_id"),
            "battery_version": d.get("battery_version"),
            "rubric_path": d.get("rubric_path"),
            "questions": qs,
        }
    return out


def main() -> int:
    caps = captures_by_ts()
    rub = rubrics()
    (OUT / "runs").mkdir(parents=True, exist_ok=True)
    bat = batteries()
    (OUT / "batteries").mkdir(parents=True, exist_ok=True)
    for lang, b in bat.items():
        (OUT / "batteries" / f"{lang}.json").write_text(
            json.dumps(b, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    (OUT / "batteries" / "index.json").write_text(
        json.dumps({"languages": sorted(bat)}, indent=1) + "\n", encoding="utf-8")

    (OUT / "rubrics").mkdir(parents=True, exist_ok=True)

    for rid, r in rub.items():
        (OUT / "rubrics" / f"{rid}.json").write_text(
            json.dumps(r, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    index, orphan_verdicts, no_capture = [], 0, 0
    for d in sorted(INT.iterdir()) if INT.exists() else []:
        m = BUNDLE.match(d.name)
        if not m:
            continue
        lang, domain, cap_ts, int_ts = m.groups()
        verdicts = read_jsonl(d / "verdicts.jsonl")
        if not verdicts:
            continue
        summary = {}
        sp = d / "verdicts_summary.json"
        if sp.exists():
            try:
                summary = json.loads(sp.read_text(encoding="utf-8"))
            except Exception:
                summary = {}

        cap = caps.get(cap_ts, {})
        if not cap:
            no_capture += 1

        by_q: dict[str, dict] = {}
        for v in verdicts:
            qid = v.get("question_id") or "?"
            q = by_q.setdefault(qid, {"question_id": qid, "criteria": []})
            src = cap.get(v.get("response_id"))
            if src and "question_text" not in q:
                q.update({
                    "question_text": src.get("question_text"),
                    "agent_response": src.get("agent_response"),
                    "stage": src.get("stage"),
                    "category": src.get("category"),
                    "as_display_name": src.get("as_display_name"),
                    "duration_s": src.get("duration_s"),
                })
            elif not src:
                orphan_verdicts += 1
            q["criteria"].append({
                "criterion_id": v.get("criterion_id"),
                "verdict": v.get("verdict"),
                "severity": v.get("severity"),
                "cited_span": v.get("cited_span") or "",
            })

        counts = summary.get("verdict_counts") or {}
        if not counts:
            counts = {k: sum(1 for v in verdicts if v.get("verdict") == k)
                      for k in ("pass", "fail", "undetermined")}

        slug = d.name
        (OUT / "runs" / f"{slug}.json").write_text(
            json.dumps({
                "bundle": slug, "language": lang, "domain": domain,
                "captured_at": cap_ts, "interpreted_at": int_ts,
                "battery_id": summary.get("battery_id"),
                "battery_version": summary.get("battery_version"),
                "rubric_id": summary.get("rubric_id"),
                "rubric_version": summary.get("rubric_version"),
                "judge_model": summary.get("judge_model"),
                "answers_present": bool(cap),
                "questions": sorted(by_q.values(), key=lambda x: x["question_id"]),
            }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

        index.append({
            "bundle": slug, "language": lang, "domain": domain,
            "captured_at": cap_ts, "interpreted_at": int_ts,
            "battery_id": summary.get("battery_id"),
            "battery_version": summary.get("battery_version"),
            "rubric_id": summary.get("rubric_id"),
            "rubric_version": summary.get("rubric_version"),
            "judge_model": summary.get("judge_model"),
            "n": summary.get("n_verdicts") or len(verdicts),
            "pass": counts.get("pass", 0),
            "fail": counts.get("fail", 0),
            "undetermined": counts.get("undetermined", 0),
            "answers_present": bool(cap),
        })

    index.sort(key=lambda r: (r["captured_at"], r["language"]), reverse=True)
    (OUT / "index.json").write_text(
        json.dumps({
            "_meta": {
                "schema": "ciris.ai/results_index/v1",
                "source": "qa_reports/safety_battery + qa_reports/safety_interpret",
                "note": ("Built by tools/build_results_index.py from committed evidence. "
                         "Artifacts expire at 90 days; this is generated from the copy that does not."),
                "runs": len(index),
                "runs_without_answers": no_capture,
                "orphan_verdicts": orphan_verdicts,
            },
            "runs": index,
        }, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")

    for name in ("safety_sweeps.json", "qa_status.json"):
        src = ROOT / "qa_reports" / name
        if src.exists():
            shutil.copyfile(src, OUT / name)

    langs = {r["language"] for r in index}
    print(f"  index: {len(index)} runs, {len(langs)} languages, {len(rub)} rubrics")
    print(f"  runs missing their capture: {no_capture}   orphan verdicts: {orphan_verdicts}")
    if no_capture:
        print("  NOTE: those runs render with answers marked absent, not hidden.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
