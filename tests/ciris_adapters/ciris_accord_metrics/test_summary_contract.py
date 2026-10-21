"""The trace-summary WIRE CONTRACT test (CIRISServer#315 seam class).

The capacity scorer — the ONLY path that ships traces to the canonical —
reads persist's trace-summary projection, which extracts FLAT top-level
JSON paths from sealed trace_events payloads via `json_extract`
(ciris-persist `SQLITE_TRACE_SUMMARY_SELECT` / postgres
`TRACE_SUMMARY_SELECT`). The accord adapter authors those payloads. The
two repos held this contract only as an unwritten assumption, and it
drifted silently: `json_extract` on a missing path returns NULL, SQL
aggregates skip NULLs, the feature matrix emptied, `emitted=0`, and no
trace ever reached Node A — with every transport layer green. Three
event families were wrong at once (nested-vs-flat DMA, unprefixed IDMA,
tier-stripped ACTION/THOUGHT keys).

This test pins the producing side of the contract: every (event_type,
flat_path) pair that persist's summary SQL extracts MUST be present in
the payload `_extract_component_data` emits at GENERIC level (the lowest
tier every deployment ships). If persist adds an extraction path, add it
here; if this test fails after a persist bump, the seam moved again —
fix the emitter, never bypass.

Upstream ask (CIRISServer#315): export the extraction-path list on the
conformance surface (alongside wire_vocabulary_sha256) so this list is
asserted against the substrate instead of mirrored by hand.

`task_description` (THOUGHT_START) is deliberately ABSENT from the
GENERIC contract: it is free text and stays FULL-tier by design —
persist reading it level-blind is flagged upstream as a wrong-tier read.
"""

from typing import Any, Dict, List, Tuple

import pytest

from ciris_adapters.ciris_accord_metrics.services import (
    AccordMetricsService,
    TraceDetailLevel,
)

# Mirror of ciris-persist SQLITE_TRACE_SUMMARY_SELECT's json_extract paths
# (store/sqlite.rs; postgres TRACE_SUMMARY_SELECT matches 1:1), minus the
# FULL-tier-only task_description (see module docstring). The paired dict is a
# representative SOURCE event carrying every field the emitter derives from —
# shaped like the real reasoning events observed on-device (2026-07-24 fold DB).
CONTRACT: List[Tuple[str, Dict[str, Any], List[str]]] = [
    (
        "THOUGHT_START",
        {"thought_type": "seed", "thought_depth": 1, "round_number": 0, "task_priority": 0},
        ["thought_type", "thought_depth"],
    ),
    (
        "DMA_RESULTS",
        {
            "csdma": {"plausibility_score": 1.0},
            "dsdma": {"domain_alignment": 1.0, "domain": "general"},
            "pdma": {"conflicts": "none"},
        },
        ["csdma_plausibility_score", "dsdma_domain_alignment", "dsdma_domain"],
    ),
    (
        "IDMA_RESULT",
        {
            "k_eff": 1.0,
            "correlation_risk": 1.0,
            "fragility_flag": True,
            "phase": "rigidity",
            "reasoning_state": "rigidity",
        },
        ["idma_k_eff", "idma_correlation_risk", "idma_fragility_flag", "idma_phase"],
    ),
    (
        "CONSCIENCE_RESULT",
        {
            "conscience_passed": True,
            "action_was_overridden": False,
            "entropy_passed": True,
            "coherence_passed": True,
            "optimization_veto_passed": True,
            "epistemic_humility_passed": True,
            "epistemic_data": {"entropy_level": 0.1, "coherence_level": 0.9},
        },
        [
            "conscience_passed",
            "action_was_overridden",
            "entropy_passed",
            "coherence_passed",
            "optimization_veto_passed",
            "epistemic_humility_passed",
        ],
    ),
    (
        "ACTION_RESULT",
        {
            "execution_success": True,
            "action_executed": "speak",
            "execution_time_ms": 16.4,
            "tokens_total": 100,
        },
        ["success", "action_executed"],
    ),
]


def _generic_service() -> AccordMetricsService:
    """A bare service at GENERIC level — _extract_component_data is a pure
    function of (self._trace_level, event_type, event); no runtime wiring
    is needed to exercise the contract."""
    svc = object.__new__(AccordMetricsService)
    svc._trace_level = TraceDetailLevel.GENERIC
    return svc


@pytest.mark.parametrize(
    "event_type,source_event,required_paths",
    CONTRACT,
    ids=[c[0] for c in CONTRACT],
)
def test_summary_extraction_paths_present_at_generic(
    event_type: str, source_event: Dict[str, Any], required_paths: List[str]
) -> None:
    svc = _generic_service()
    payload = svc._extract_component_data(event_type, source_event)
    missing = [p for p in required_paths if payload.get(p) is None]
    assert not missing, (
        f"{event_type} payload is missing flat summary path(s) {missing} at GENERIC level — "
        f"persist's trace-summary json_extract will read NULL, the capacity scorer's "
        f"feature matrix loses these dims, and (for the essential dims) traces stop "
        f"shipping to the canonical entirely. Emitted keys: {sorted(payload.keys())}"
    )


def test_essential_feature_dims_are_the_essential_ones() -> None:
    """The scorer drops any row where BOTH essential dims are absent
    (n_eff.rs feature_matrix filter: csdma_plausibility_score OR idma_k_eff).
    Guard the two dims that decide row survival explicitly, so a contract
    edit can never silently demote them."""
    svc = _generic_service()
    dma = svc._extract_component_data("DMA_RESULTS", {"csdma": {"plausibility_score": 0.7}, "dsdma": {}, "pdma": {}})
    idma = svc._extract_component_data("IDMA_RESULT", {"k_eff": 2.0})
    assert dma.get("csdma_plausibility_score") == 0.7
    assert idma.get("idma_k_eff") == 2.0
