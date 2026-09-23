"""Monte-Carlo model of one H3ERE interact against an ELASTIC (cloud) provider.

Pipeline shape, from the code rather than guessed:

  stage 1  EthicalPDMA | CSDMA | BaseDSDMA   concurrent  -> slowest member
  stage 2  IDMA                              sequential
  stage 3  ActionSelectionPDMA               sequential
  stage 4  four conscience shards            concurrent  -> needs ALL four
  plus     fixed per-interact overhead       (measured: task-created -> verdict,
                                              minus the four stage costs)

A conscience shard that exhausts its attempts fails CLOSED (check_ran=False),
the thought becomes PONDER, and the user gets no reply however long they wait.
That is why ``ceiling()`` exists: it is the success rate with an infinite
deadline, and no deadline can beat it.

THE CENSORED TAIL. A call past the conscience budget never logs a duration,
only a timeout, so the data is right-censored at that budget. The body is
measured; the MASS past the budget is measured; the SHAPE past it is not.
``tail`` chooses that shape. Answers near 99% are driven by the measured mass
(attempt count), and barely move with ``tail``; answers near 99.9% live
entirely in the unmeasured region and should not be trusted.

A retry here is an INDEPENDENT draw. That holds for an elastic provider and is
false for a capacity-bound box -- see local_provider.py.
"""
from __future__ import annotations

import math
import random
import statistics as st
from dataclasses import dataclass, replace
from typing import Dict, List, Optional, Sequence, Tuple

INITIAL = ("EthicalPDMAEvaluator", "CSDMAEvaluator", "BaseDSDMA")
SHARDS = (
    "coherence_conscience",
    "entropy_conscience",
    "epistemic_humility_conscience",
    "optimization_veto_conscience",
)
STAGES: Tuple[Tuple[str, Sequence[str], bool], ...] = (
    ("initial_dmas", INITIAL, True),
    ("idma", ("IDMAEvaluator",), False),
    ("action_sel", ("ActionSelectionPDMAEvaluator",), False),
    ("conscience", SHARDS, True),
)


@dataclass(frozen=True)
class Config:
    """Every budget the interact path has. Defaults = main @ 2.11.5, desktop."""

    deadline: float = 110.0  # api/routes/agent.py _get_interaction_timeout
    consc_per_try: float = 45.0  # ConscienceConfig.llm_call_timeout_seconds
    consc_attempts: int = 2  # ConscienceConfig.llm_call_retries = 1
    consc_quorum: int = 4  # shards that must answer (4 today; lowering it is a SAFETY call)
    dma_per_try: float = 90.0  # dma_orchestrator DMA_TIMEOUT_SECONDS
    dma_attempts: int = 1
    propagate: bool = False  # SRE deadline propagation: each call gets the REMAINDER
    overhead: bool = True  # add the measured per-interact overhead


class Sampler:
    """Empirical body + modelled tail past the censoring point."""

    def __init__(self, data: dict, tail: str = "lognormal", censor: float = 45.0, seed: int = 7):
        self.body: Dict[str, List[float]] = data["body"]
        self.overhead: List[float] = data.get("overhead") or [0.0]
        self.tail = tail
        self.censor = censor
        self.rng = random.Random(seed)
        tos = data.get("timeouts", {})
        self.p_over = {
            k: tos.get(k, 0) / (len(v) + tos.get(k, 0)) if (len(v) + tos.get(k, 0)) else 0.0
            for k, v in self.body.items()
        }

    def draw(self, name: str) -> float:
        v = self.body[name]
        if self.rng.random() < self.p_over.get(name, 0.0):
            return self._tail(v)
        return self.rng.choice(v)

    def draw_overhead(self) -> float:
        return max(0.0, self.rng.choice(self.overhead))

    def _tail(self, v: List[float]) -> float:
        c = self.censor
        if self.tail == "optimistic":  # most censored calls land just past the wall
            return c + abs(self.rng.gauss(0, 6))
        if self.tail == "pareto":  # heavy: P(X > c*k) = k^-1.6
            return c * self.rng.paretovariate(1.6)
        logs = [math.log(x) for x in v if x > 0]  # lognormal fit to the body, conditioned > c
        mu, sig = st.mean(logs), (st.pstdev(logs) or 0.5)
        for _ in range(200):
            x = math.exp(self.rng.gauss(mu, sig))
            if x > c:
                return x
        return c * 1.5


def _stage(names: Sequence[str], concurrent: bool, cfg: Config, s: Sampler,
           per_try: float, attempts: int, remaining: float, quorum: int) -> Tuple[float, bool]:
    costs = []
    for n in names:
        spent, ok = 0.0, False
        for _ in range(attempts):
            budget = per_try
            if cfg.propagate:
                budget = min(budget, max(remaining - spent, 0.0))
            if budget <= 0:
                break
            d = s.draw(n)
            if d <= budget:
                spent += d
                ok = True
                break
            spent += budget  # burned the whole try, learned nothing
        costs.append((spent, ok))
    need = min(quorum, len(names))
    if concurrent:
        answered = sorted(c for c, o in costs if o)
        elapsed = answered[need - 1] if len(answered) >= need else max(c for c, _ in costs)
    else:
        elapsed = sum(c for c, _ in costs)
    return elapsed, sum(1 for _, o in costs if o) >= need


def run_once(cfg: Config, s: Sampler) -> Tuple[float, bool]:
    t = s.draw_overhead() if cfg.overhead else 0.0
    for name, members, conc in STAGES:
        consc = name == "conscience"
        el, ok = _stage(
            members, conc, cfg, s,
            cfg.consc_per_try if consc else cfg.dma_per_try,
            cfg.consc_attempts if consc else cfg.dma_attempts,
            cfg.deadline - t,
            cfg.consc_quorum if consc else len(members),
        )
        t += el
        if not ok or t > cfg.deadline:
            return t, False
    return t, True


def simulate(cfg: Config, s: Sampler, n: int = 20000) -> dict:
    """Success rate plus percentiles of the replies users actually RECEIVED."""
    got: List[float] = []
    for _ in range(n):
        t, ok = run_once(cfg, s)
        if ok:
            got.append(t)
    got.sort()

    def q(p: float) -> float:
        return got[min(len(got) - 1, int(round(p * (len(got) - 1))))] if got else float("nan")

    return {"success": len(got) / n, "p50": q(0.5), "p75": q(0.75), "p90": q(0.9), "p99": q(0.99)}


def ceiling(cfg: Config, s: Sampler, n: int = 20000) -> float:
    """Success with an infinite deadline: the part no timeout can buy back."""
    return simulate(replace(cfg, deadline=1e9), s, n)["success"]


def solve_deadline(cfg: Config, s: Sampler, target: float, n: int = 30000) -> Optional[float]:
    """Smallest deadline reaching ``target``; None if the ceiling is below it."""
    if ceiling(cfg, s, n) < target:
        return None
    lo, hi, best = 10.0, 1200.0, None
    for _ in range(20):
        mid = (lo + hi) / 2
        if simulate(replace(cfg, deadline=mid), s, n)["success"] >= target:
            best, hi = mid, mid
        else:
            lo = mid
    return best
