"""When to hedge a slow LLM-backed attempt (2.18.0).

A slow attempt is not cancelled for its retry: once it runs past the recent
p95 latency of its kind, the next attempt starts beside it and the first
answer wins (Dean & Barroso, "The Tail at Scale").

A hedge is for a TAIL outlier, and it costs the provider a whole request even
when we cancel it (cancelling our side does not stop its prefill). Against a
provider that is slow across the board, hedging every slow call doubles the
load on the thing that is slow: the 2.18.0 bn battery hedged 111 times on a
DeepInfra p50 of 45 s and tripped the breaker. So hedging is load-aware:
- no hedge without history: a kind hedges only once its own p95 exists;
- a budget: hedges are at most HEDGE_BUDGET of recent attempts, process-wide.
  When most calls are slow together, the budget runs out and hedging stops.

One book for every retry loop that hedges (the DMA executor and the
consciences), keyed by the loop's own name for the call (``run_pdma``,
``coherence_conscience``, ...).
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict, Optional

#: The percentile an attempt must exceed before it is hedged.
HEDGE_PERCENTILE = 0.95
#: Answers needed before the percentile is trusted. Until then: no hedging.
HEDGE_MIN_SAMPLES = 20
#: Hedges allowed per recent attempt, process-wide.
HEDGE_BUDGET = 0.05
#: Attempts (hedged or not) the budget is reckoned over.
_BUDGET_WINDOW = 200
#: Never hedge sooner than this: an honest call answers in 2-14 s, and a hedge
#: inside that is just a doubled request (matches MIN_USEFUL_ATTEMPT_S).
HEDGE_FLOOR_S = 10.0
_WINDOW = 50

_latencies: Dict[str, Deque[float]] = {}
#: One entry per attempt started: True when it was a hedge.
_attempts: Deque[bool] = deque(maxlen=_BUDGET_WINDOW)


def record_latency(name: str, seconds: float) -> None:
    """An attempt of this kind answered after ``seconds``."""
    _latencies.setdefault(name, deque(maxlen=_WINDOW)).append(seconds)


def hedge_after_s(name: str) -> Optional[float]:
    """Seconds to wait on an attempt before hedging it, or None: no history yet."""
    samples = sorted(_latencies.get(name, ()))
    if len(samples) < HEDGE_MIN_SAMPLES:
        return None
    return max(HEDGE_FLOOR_S, samples[min(len(samples) - 1, int(HEDGE_PERCENTILE * len(samples)))])


def note_attempt() -> None:
    """A first (unhedged) attempt started."""
    _attempts.append(False)


def try_hedge() -> bool:
    """Spend one hedge from the budget, if the recent attempts afford it."""
    if sum(_attempts) + 1 > HEDGE_BUDGET * max(len(_attempts), HEDGE_MIN_SAMPLES):
        return False
    _attempts.append(True)
    return True


def reset() -> None:
    """Forget every recorded latency and attempt (tests)."""
    _latencies.clear()
    _attempts.clear()
