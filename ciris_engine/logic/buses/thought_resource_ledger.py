"""Per-thought LLM resource totals, kept where the calls are recorded.

The ACTION_COMPLETE reasoning event carries what one thought cost (tokens,
cost, carbon, energy, call count, models). It used to be rebuilt per thought
by six telemetry queries, each of which paged up to 1000 of the newest
tsdb_data graph nodes out of the substrate, JSON-decoded every one and then
filtered them by metric name and thought tag in Python. Every LLM call writes
several such nodes, so the cost of each thought's lookup grew with the run
(14,000 nodes after ~300 thoughts in the memory benchmark) -- the six
executor-thread scans per thought were what made work rounds slow down -- and
past 1000 nodes in the window the answer was silently truncated.

LLMBus._record_resource_telemetry is the single point every completed call's
usage passes through, so it records the totals here as well. Reading them is a
dict lookup. Bounded: the oldest thoughts are evicted past MAX_THOUGHTS, long
after their ACTION_COMPLETE has been emitted.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Optional, Set

from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.types import JSONDict

#: Thoughts whose totals are retained (oldest evicted first).
MAX_THOUGHTS = 4096


@dataclass
class _ThoughtTotals:
    tokens_total: int = 0
    tokens_input: int = 0
    tokens_output: int = 0
    cost_cents: float = 0.0
    carbon_grams: float = 0.0
    energy_kwh: float = 0.0
    llm_calls: int = 0
    models: Set[str] = field(default_factory=set)
    api_bases: Set[str] = field(default_factory=set)


def empty_resource_summary() -> JSONDict:
    """The ACTION_COMPLETE resource fields for a thought that made no LLM call."""
    return {
        "tokens_total": 0,
        "tokens_input": 0,
        "tokens_output": 0,
        "cost_cents": 0.0,
        "carbon_grams": 0.0,
        "energy_mwh": 0.0,
        "llm_calls": 0,
        "models_used": [],
        "api_bases_used": [],
    }


class ThoughtResourceLedger:
    """Running per-thought totals of LLM usage."""

    def __init__(self, max_thoughts: int = MAX_THOUGHTS) -> None:
        self._max = max_thoughts
        self._lock = threading.Lock()
        self._totals: "OrderedDict[str, _ThoughtTotals]" = OrderedDict()

    def record(self, thought_id: str, usage: ResourceUsage, api_base: Optional[str] = None) -> None:
        """Add one completed LLM call's usage to its thought."""
        if not thought_id:
            return
        with self._lock:
            totals = self._totals.get(thought_id)
            if totals is None:
                totals = self._totals[thought_id] = _ThoughtTotals()
                while len(self._totals) > self._max:
                    self._totals.popitem(last=False)
            totals.tokens_total += usage.tokens_used
            totals.tokens_input += usage.tokens_input
            totals.tokens_output += usage.tokens_output
            totals.cost_cents += usage.cost_cents
            totals.carbon_grams += usage.carbon_grams
            totals.energy_kwh += usage.energy_kwh
            totals.llm_calls += 1
            totals.models.add(usage.model_used or "unknown")
            totals.api_bases.add(api_base or "default")

    def summary(self, thought_id: str) -> JSONDict:
        """The thought's totals in the ACTION_COMPLETE resource shape (zeros if none)."""
        with self._lock:
            totals = self._totals.get(thought_id)
            if totals is None:
                return empty_resource_summary()
            return {
                "tokens_total": totals.tokens_total,
                "tokens_input": totals.tokens_input,
                "tokens_output": totals.tokens_output,
                "cost_cents": float(totals.cost_cents),
                "carbon_grams": float(totals.carbon_grams),
                # kWh -> mWh (1 kWh = 1,000,000 mWh)
                "energy_mwh": float(totals.energy_kwh) * 1_000_000,
                "llm_calls": totals.llm_calls,
                "models_used": sorted(totals.models),
                "api_bases_used": sorted(totals.api_bases),
            }

    def __len__(self) -> int:
        return len(self._totals)


#: The process-wide ledger LLMBus writes and the ACTION_COMPLETE step reads.
thought_resource_ledger = ThoughtResourceLedger()
