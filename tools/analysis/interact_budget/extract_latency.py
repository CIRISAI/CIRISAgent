#!/usr/bin/env python3
"""Build a latency dataset from agent logs, so every number in the toys is reproducible.

Reads ``ciris_agent_*.log`` / ``latest.log`` files under the given directories
(typically five-platform ``live-qa-*`` artifacts), de-duplicates them by content
(the gate ships the same file under two paths), and writes one JSON file:

  body            {evaluator: [seconds, ...]}  successful calls ([LLM-TIMING])
  timeouts        {shard: n}                   conscience attempts that hit the budget
  attempts        {"1": n, "2": n}              which attempt timed out
  recovered       [[shard, seconds], ...]       "answered on attempt 2 after Xs"
  gave_up         {shard: n}                   both attempts lost (transport TIMEOUT)
  overhead        [seconds, ...]               task-created -> verdict, minus the
                                               stage costs the toy models
  end_to_end      [seconds, ...]               task-created -> first conscience verdict
  meta            provenance: files, providers, budget in force

Fetch artifacts with, e.g.:

  for r in <run ids>; do for a in live-qa-windows live-qa-linux-android live-qa-macos-ios; do
    gh run download $r -n $a -D runs/$r/$a; done; done
  python -m tools.analysis.interact_budget.extract_latency runs/ -o latency.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

TS = r"(\d{4}-\d\d-\d\d \d\d:\d\d:\d\d\.\d+)"
INITIAL = ("EthicalPDMAEvaluator", "CSDMAEvaluator", "BaseDSDMA")
SHARDS = (
    "coherence_conscience",
    "entropy_conscience",
    "epistemic_humility_conscience",
    "optimization_veto_conscience",
)


def _ts(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        return None


def unique_logs(roots: List[Path]) -> List[Path]:
    seen: Dict[str, Path] = {}
    for root in roots:
        for p in sorted(root.rglob("*.log")):
            if not (p.name.startswith("ciris_agent_") or p.name == "latest.log"):
                continue
            h = hashlib.md5(p.read_bytes()).hexdigest()
            seen.setdefault(h, p)
    return list(seen.values())


def extract(paths: List[Path]) -> dict:
    body: Dict[str, List[float]] = defaultdict(list)
    timeouts: Counter = Counter()
    attempts: Counter = Counter()
    gave_up: Counter = Counter()
    recovered: List[list] = []
    overhead: List[float] = []
    end_to_end: List[float] = []
    providers: Counter = Counter()
    budgets: Counter = Counter()

    for p in paths:
        text = p.read_text(errors="ignore")
        for m in re.finditer(r"\[LLM-TIMING\] (\S+) (th_\S+): (\d+)ms", text):
            body[m.group(1)].append(int(m.group(3)) / 1000)
        for m in re.finditer(
            r"\[CONSCIENCE\] ([a-z_]+conscience): no answer within the facility budget \((\d+)s\) on attempt (\d)/", text
        ):
            timeouts[m.group(1)] += 1
            attempts[m.group(3)] += 1
            budgets[f"conscience_per_try={m.group(2)}s"] += 1
        for m in re.finditer(r"\[CONSCIENCE\] ([a-z_]+conscience): answered on attempt 2 after ([\d.]+)s", text):
            recovered.append([m.group(1), float(m.group(2))])
        for m in re.finditer(r"([A-Za-z]+)Conscience: transport failure \(TIMEOUT\)", text):
            gave_up[m.group(1)] += 1
        for m in re.finditer(r"\[LLM_REQUEST\] model=([^,]+), base_url=([^,]+), timeout=(\d+)", text):
            providers[f"{m.group(1)} @ {m.group(2)}"] += 1
            budgets[f"http_timeout={m.group(3)}s"] += 1

        # Per-thought: end-to-end, and the overhead the stage model does not see.
        created: Dict[str, datetime] = {}
        stage: Dict[str, Dict[str, float]] = defaultdict(dict)
        for line in text.splitlines():
            m = re.match(TS + r".*PASSIVE TASK CREATED: (\S+)", line)
            if m and _ts(m.group(1)):
                created[m.group(2)] = _ts(m.group(1))  # type: ignore[assignment]
                continue
            m = re.search(r"\[LLM-TIMING\] (\S+) (th_seed_\S+): (\d+)ms", line)
            if m:
                stage[m.group(2)][m.group(1)] = int(m.group(3)) / 1000
                continue
            m = re.match(TS + r".*conscience result for (th_seed_(\S+?)_\S+): final_action=", line)
            if not m:
                continue
            thought, task_prefix = m.group(2), m.group(3)
            start = next((v for k, v in created.items() if k.startswith(task_prefix)), None)
            end = _ts(m.group(1))
            if not (start and end):
                continue
            e2e = (end - start).total_seconds()
            end_to_end.append(e2e)
            t = stage.get(thought, {})
            if all(k in t for k in INITIAL + ("IDMAEvaluator", "ActionSelectionPDMAEvaluator") + SHARDS):
                modelled = (
                    max(t[k] for k in INITIAL)
                    + t["IDMAEvaluator"]
                    + t["ActionSelectionPDMAEvaluator"]
                    + max(t[k] for k in SHARDS)
                )
                overhead.append(round(e2e - modelled, 3))

    return {
        "body": {k: sorted(v) for k, v in sorted(body.items())},
        "timeouts": dict(timeouts),
        "attempts": dict(attempts),
        "recovered": recovered,
        "gave_up": dict(gave_up),
        "overhead": sorted(overhead),
        "end_to_end": sorted(end_to_end),
        "meta": {
            "files": len(paths),
            "providers": dict(providers),
            "budgets_seen": dict(budgets),
            "extracted": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
    }


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("roots", nargs="+", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    ap.add_argument("--runs", default="", help="comma-separated run ids, recorded as provenance")
    a = ap.parse_args(argv)
    data = extract(unique_logs(a.roots))
    if a.runs:
        data["meta"]["runs"] = [r for r in a.runs.split(",") if r]
    out = json.dumps(data, indent=1)
    if a.out:
        a.out.write_text(out + "\n")
    else:
        sys.stdout.write(out + "\n")
    b = data["body"]
    ok = sum(len(b[s]) for s in SHARDS if s in b)
    to = sum(data["timeouts"].values())
    print(
        f"files={data['meta']['files']} conscience ok={ok} timeouts={to} "
        f"({100 * to / max(ok + to, 1):.1f}%) e2e samples={len(data['end_to_end'])}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
