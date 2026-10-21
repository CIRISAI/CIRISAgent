#!/usr/bin/env python3
"""Play with interact-budget assumptions on measured latencies.

  python -m tools.analysis.interact_budget.explore calibrate
  python -m tools.analysis.interact_budget.explore scenarios [--target 0.99]
  python -m tools.analysis.interact_budget.explore experience
  python -m tools.analysis.interact_budget.explore tails
  python -m tools.analysis.interact_budget.explore ceiling
  python -m tools.analysis.interact_budget.explore local [--speed 3] [--slots 1]
  python -m tools.analysis.interact_budget.explore local-sweep [--speed 1]

Default dataset: the dated snapshot in this directory. Rebuild one from any
set of runs with extract_latency.py and pass it with --latency.
"""
from __future__ import annotations

import argparse
import json
import statistics as st
from dataclasses import replace
from pathlib import Path

from .local_provider import conscience_stage
from .pipeline import SHARDS, Config, Sampler, ceiling, simulate, solve_deadline

HERE = Path(__file__).parent
DEFAULT = sorted(HERE.glob("latency.*.json"))[-1] if list(HERE.glob("latency.*.json")) else None

SCENARIOS = [
    ("today: 45s x2 @110s", Config()),
    ("no conscience retry (45s x1)", Config(consc_attempts=1)),
    ("deadline propagation", Config(propagate=True)),
    ("45s x3", Config(consc_attempts=3)),
    ("45s x4", Config(consc_attempts=4)),
    ("60s x3", Config(consc_per_try=60.0, consc_attempts=3)),
    ("fail-fast 30s x4", Config(consc_per_try=30.0, consc_attempts=4)),
    ("fail-fast 20s x6", Config(consc_per_try=20.0, consc_attempts=6)),
]


def _fmt(d):
    return f"{d:.0f}s" if d else "unreachable"


def cmd_calibrate(data, a):
    s = Sampler(data, a.tail, a.censor, a.seed)
    r = simulate(replace(Config(), deadline=1e9), s, a.n)
    e = sorted(data.get("end_to_end", []))
    print("model vs observed, task-created -> first conscience verdict (current config, no deadline)")
    if e:
        n = len(e)
        print(f"  observed  n={n:4}  p50 {st.median(e):5.1f}s  p90 {e[int(0.9 * (n - 1))]:5.1f}s")
    print(f"  model     n={a.n:4}  p50 {r['p50']:5.1f}s  p90 {r['p90']:5.1f}s   ceiling {100 * r['success']:.1f}%")
    b = data["body"]
    ok = sum(len(b[x]) for x in SHARDS)
    to = sum(data["timeouts"].values())
    at = data.get("attempts", {})
    print(f"  conscience calls ok={ok} timed out={to}  per-call timeout rate {100 * to / (ok + to):.1f}%")
    if at.get("1"):
        print(f"  P(retry also times out) = {at.get('2', 0)}/{at['1']} = {100 * at.get('2', 0) / at['1']:.0f}%  "
              "(independent draws would give roughly the per-call rate)")


def cmd_ceiling(data, a):
    b = data["body"]
    ok = sum(len(b[x]) for x in SHARDS)
    p = sum(data["timeouts"].values()) / (ok + sum(data["timeouts"].values()))
    print(f"per-call timeout rate p = {100 * p:.1f}%   stage needs all {len(SHARDS)} shards\n")
    for k in range(1, 6):
        shard = p ** k
        stage = 1 - (1 - shard) ** len(SHARDS)
        print(f"  attempts={k}:  P(shard unavailable) {100 * shard:7.3f}%   ceiling {100 * (1 - stage):6.2f}%")


def cmd_scenarios(data, a):
    print(f"tail={a.tail}  target={100 * a.target:.1f}%  n={a.n}\n")
    print(f"{'scenario':32} {'ok@110s':>8} {'ceiling':>8} {'p50':>6} {'p99':>6} {'deadline for target':>20}")
    for label, cfg in SCENARIOS:
        s = Sampler(data, a.tail, a.censor, a.seed)
        r = simulate(cfg, s, a.n)
        c = ceiling(cfg, s, a.n)
        d = solve_deadline(cfg, s, a.target, a.n)
        print(f"{label:32} {100 * r['success']:7.1f}% {100 * c:7.1f}% {r['p50']:5.0f}s {r['p99']:5.0f}s {_fmt(d):>20}")


def cmd_experience(data, a):
    print("what users RECEIVE (percentiles are over replies actually delivered)\n")
    print(f"{'config':30} {'reply rate':>10} {'p50':>6} {'p75':>6} {'p90':>6} {'p99':>6}")
    for label, cfg in [
        ("today: 45s x2 @110s", Config()),
        ("45s x4 @110s", Config(consc_attempts=4)),
        ("45s x4 @175s", Config(consc_attempts=4, deadline=175.0)),
        ("45s x4 @175s + propagation", Config(consc_attempts=4, deadline=175.0, propagate=True)),
    ]:
        r = simulate(cfg, Sampler(data, a.tail, a.censor, a.seed), a.n)
        print(f"{label:30} {100 * r['success']:9.1f}% {r['p50']:5.0f}s {r['p75']:5.0f}s {r['p90']:5.0f}s {r['p99']:5.0f}s")


def cmd_tails(data, a):
    print(f"sensitivity to the UNMEASURED tail shape (target {100 * a.target:.1f}%)\n")
    for tail in ("optimistic", "lognormal", "pareto"):
        for label, cfg in [("45s x2", Config()), ("45s x4", Config(consc_attempts=4)),
                           ("60s x3", Config(consc_per_try=60.0, consc_attempts=3))]:
            s = Sampler(data, tail, a.censor, a.seed)
            print(f"  {tail:11} {label:8} ceiling {100 * ceiling(cfg, s, a.n):5.1f}%   "
                  f"deadline {_fmt(solve_deadline(cfg, s, a.target, a.n))}")


def cmd_local(data, a):
    print(f"capacity-bound box: speed {a.speed}x, zombie residual {a.zombie:.0f}s\n")
    print(f"{'slots':>5} {'cancel frees slot':>18} {'att':>4} {'ok':>7} {'p50':>6} {'p90':>6} {'p99':>6} {'slot-s wasted':>14}")
    for slots in (a.slots,) if a.slots else (1, 2, 4):
        for frees in (True, False):
            for att in (1, 2, 4):
                r = conscience_stage(Sampler(data, a.tail, a.censor, a.seed), slots, 45.0, att, frees,
                                     a.zombie, a.speed, a.n // 3)
                tag = "yes (vLLM/Ollama>=0.33)" if frees else "NO (llama.cpp)"
                print(f"{slots:5} {tag:>18} {att:4} {100 * r[0]:6.1f}% {r[1]:5.0f}s {r[2]:5.0f}s {r[3]:5.0f}s {r[4]:13.0f}s")


def cmd_local_sweep(data, a):
    print(f"one slot, cancel does NOT free it, speed {a.speed}x: long single try vs retries\n")
    print(f"{'per_try':>8} {'att':>4} {'ok':>7} {'p90':>6} {'slot-s wasted':>14}")
    for per_try in (45, 60, 90, 120, 180, 240):
        for att in (1, 2):
            r = conscience_stage(Sampler(data, a.tail, a.censor, a.seed), a.slots or 1, per_try, att, False,
                                 a.zombie, a.speed, a.n // 3)
            print(f"{per_try:8} {att:4} {100 * r[0]:6.1f}% {r[2]:5.0f}s {r[4]:13.0f}s")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["calibrate", "ceiling", "scenarios", "experience", "tails", "local", "local-sweep"])
    ap.add_argument("--latency", type=Path, default=DEFAULT)
    ap.add_argument("-n", type=int, default=20000)
    ap.add_argument("--target", type=float, default=0.99)
    ap.add_argument("--tail", choices=["lognormal", "optimistic", "pareto"], default="lognormal")
    ap.add_argument("--censor", type=float, default=45.0)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--speed", type=float, default=1.0, help="local service-time multiplier (a GUESS until measured)")
    ap.add_argument("--slots", type=int, default=0)
    ap.add_argument("--zombie", type=float, default=30.0, help="seconds an abandoned generation keeps its slot")
    a = ap.parse_args(argv)
    data = json.loads(a.latency.read_text())
    {"calibrate": cmd_calibrate, "ceiling": cmd_ceiling, "scenarios": cmd_scenarios, "experience": cmd_experience,
     "tails": cmd_tails, "local": cmd_local, "local-sweep": cmd_local_sweep}[a.command](data, a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
