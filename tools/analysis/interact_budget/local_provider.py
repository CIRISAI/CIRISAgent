"""The conscience stage against a CAPACITY-BOUND local provider (e.g. a Jetson).

pipeline.py treats a retry as an independent draw. On a box with a fixed number
of inference slots that is false, twice over:

1. QUEUEING -- four shards fired at once against fewer than four slots
   serialise, and a retry joins the back of the queue.
2. ZOMBIES -- cancelling the HTTP request does not reliably stop generation:
   llama.cpp never checks ``is_connection_closed`` (ggml-org/llama.cpp#24496);
   llama-server/llama-swap leave "a zombie request occupying the single slot";
   Ollama fixed hang-on-disconnect only in v0.33.0. So a retry queues BEHIND
   the call it abandoned and cannot start until that call finishes anyway.

``frees_slot`` selects between the two server behaviours. ``speed`` scales the
measured cloud service times -- it is a GUESS until a local box is measured
with extract_latency.py.
"""
from __future__ import annotations

import statistics as st
from typing import Tuple

from .pipeline import SHARDS, Sampler


def conscience_stage(s: Sampler, slots: int, per_try: float, attempts: int, frees_slot: bool,
                     zombie_extra: float, speed: float, n: int = 8000) -> Tuple[float, float, float, float, float]:
    """Returns (success, p50, p90, p99, mean slot-seconds spent on abandoned calls)."""
    ok_n, times, burned_all = 0, [], []
    for _ in range(n):
        free_at = [0.0] * slots
        finished, burned = [], 0.0
        for sh in SHARDS:
            t, answered = 0.0, False
            for _a in range(attempts):
                svc = s.draw(sh) * speed
                i = min(range(slots), key=lambda k: free_at[k])
                start = max(t, free_at[i])
                if svc <= per_try:
                    free_at[i] = start + svc
                    t, answered = start + svc, True
                    break
                hold = per_try if frees_slot else svc + zombie_extra
                free_at[i] = start + hold
                burned += hold
                t = start + per_try
            finished.append((t, answered))
        if all(a for _, a in finished):
            ok_n += 1
            times.append(max(t for t, _ in finished))
        burned_all.append(burned)
    times.sort()

    def q(p: float) -> float:
        return times[min(len(times) - 1, int(round(p * (len(times) - 1))))] if times else float("nan")

    return ok_n / n, q(0.5), q(0.9), q(0.99), st.mean(burned_all)
