"""When to hedge a slow LLM-backed attempt (2.18.0).

A slow attempt is not cancelled for its retry: once it runs past the recent
p95 latency of its kind, the next attempt starts beside it and the first
answer wins (Dean & Barroso, "The Tail at Scale"). About 5% of calls are
hedged, which is the extra provider load this spends to cut tail latency.

One book for every retry loop that hedges (the DMA executor and the
consciences), keyed by the loop's own name for the call (``run_pdma``,
``coherence_conscience``, ...).
"""

from __future__ import annotations

from collections import deque
from typing import Deque, Dict

#: The percentile an attempt must exceed before it is hedged.
HEDGE_PERCENTILE = 0.95
#: Answers needed before the percentile is trusted; until then half the HTTP
#: timeout stands in.
HEDGE_MIN_SAMPLES = 20
#: Never hedge sooner than this: an honest call answers in 2-14 s, and a hedge
#: inside that is just a doubled request (matches MIN_USEFUL_ATTEMPT_S).
HEDGE_FLOOR_S = 10.0
_WINDOW = 50

_latencies: Dict[str, Deque[float]] = {}


def record_latency(name: str, seconds: float) -> None:
    """An attempt of this kind answered after ``seconds``."""
    _latencies.setdefault(name, deque(maxlen=_WINDOW)).append(seconds)


def hedge_after_s(name: str, http_timeout_s: float) -> float:
    """Seconds to wait on an attempt before starting the next one beside it."""
    samples = sorted(_latencies.get(name, ()))
    if len(samples) >= HEDGE_MIN_SAMPLES:
        base = samples[min(len(samples) - 1, int(HEDGE_PERCENTILE * len(samples)))]
    else:
        base = http_timeout_s / 2
    return max(HEDGE_FLOOR_S, base)


def reset() -> None:
    """Forget every recorded latency (tests)."""
    _latencies.clear()
