"""Per-round phase timing: where a work round's time went, logged once per round.

A work round runs its batch of thoughts concurrently, so a round's wall time
says nothing about which stage of the pipeline is slow. Each stage records the
time one thought spent in it here; the work processor drains the totals at the
end of the round and logs a single line (see WorkProcessor._log_round).

Totals are thought-seconds: fifty thoughts that each spend 2 s in their DMAs
record 100 s of DMA time in a round whose wall time may be 10 s. Comparing a
phase's share across rounds is the point -- a phase whose per-thought time
climbs while the batch size stays fixed is the one that grows with
accumulated state.

`loop_lag` is the longest the event loop was late for a scheduled wakeup
during the round (the resource monitor samples it every tick). A large value
means something ran synchronously on the loop for that long, freezing HTTP
intake along with everything else.

Bounded by construction: one dict entry per phase, no per-event retention.
Thread-safe, because some phases (trace capture, audit) finish on workers.
"""

from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Dict, Iterator, Tuple


class RoundPhase(str, Enum):
    """Pipeline stages a work round's time is attributed to."""

    CONTEXT = "context"  # context gathering / system snapshot
    DMA = "dma"  # DMA round 1 (ethical, common-sense, domain, identity)
    ASPDMA = "aspdma"  # action selection (+ the verb-specific second pass)
    CONSCIENCE = "conscience"  # conscience faculties (+ the retry pass)
    DISPATCH = "dispatch"  # action dispatch and handlers (includes the audit entry)
    AUDIT = "audit"  # audit entries (hash chain, signing, persistence)
    TRACE_CAPTURE = "trace"  # reasoning-event capture into the substrate LensClient


@dataclass
class PhaseTotals:
    """Thought-seconds spent in one phase during one round."""

    seconds: float = 0.0
    count: int = 0
    max_seconds: float = 0.0


class RoundPhaseTimer:
    """Accumulates phase totals until the work processor drains them."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._totals: Dict[RoundPhase, PhaseTotals] = {}
        self._loop_lag_max = 0.0

    def record(self, phase: RoundPhase, seconds: float) -> None:
        with self._lock:
            totals = self._totals.get(phase)
            if totals is None:
                totals = self._totals[phase] = PhaseTotals()
            totals.seconds += seconds
            totals.count += 1
            if seconds > totals.max_seconds:
                totals.max_seconds = seconds

    def note_loop_lag(self, seconds: float) -> None:
        with self._lock:
            if seconds > self._loop_lag_max:
                self._loop_lag_max = seconds

    def drain(self) -> Tuple[Dict[RoundPhase, PhaseTotals], float]:
        """The totals since the last drain, and the worst loop lag; then reset."""
        with self._lock:
            totals, lag = self._totals, self._loop_lag_max
            self._totals, self._loop_lag_max = {}, 0.0
        return totals, lag


#: The process-wide timer (one work loop per process).
round_phase_timer = RoundPhaseTimer()


def record_round_phase(phase: RoundPhase, seconds: float) -> None:
    round_phase_timer.record(phase, seconds)


@contextmanager
def timed_phase(phase: RoundPhase) -> Iterator[None]:
    """Record the time spent inside the block against ``phase`` (also on error)."""
    started = time.monotonic()
    try:
        yield
    finally:
        round_phase_timer.record(phase, time.monotonic() - started)


def format_phase_totals(totals: Dict[RoundPhase, PhaseTotals]) -> str:
    """`dma 120.4s/50 (max 4.1s), ...` in pipeline order; phases with no samples are left out."""
    parts = []
    for phase in RoundPhase:
        t = totals.get(phase)
        if t is None or t.count == 0:
            continue
        parts.append(f"{phase.value} {t.seconds:.1f}s/{t.count} (max {t.max_seconds:.1f}s)")
    return ", ".join(parts) or "none"
