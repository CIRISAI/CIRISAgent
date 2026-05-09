"""Regression guards for LLM_CALL parent_event_type wiring (CIRISAgent#717).

Background
----------
Every ``ReasoningEvent.LLM_CALL`` carries ``parent_event_type`` +
``parent_attempt_index``. Persistence (CIRISPersist v0.3.3+) joins
``trace_llm_calls`` to ``trace_events`` on the dedup tuple
``(agent_id_hash, trace_id, thought_id, parent_event_type, parent_attempt_index)``,
so a wrong/missing ``parent_event_type`` produces un-joinable rows.

The parent context is set by ``set_parent_event_context()`` (an asyncio
``ContextVar``), typically via the ``@streaming_step`` decorator that wraps
each H3ERE pipeline handler. If a handler skips ``@streaming_step`` OR a
new LLM-issuing ``StepPoint`` is added without a mapping in
``_resolve_parent_event_for_step()``, every LLM call from that path falls
back to the sentinel ``"UNKNOWN_PARENT"`` and lands as a valid-but-wrong
row in lens.

The sentinel WARN-on-fire design surfaces this in logs but doesn't fail
the build. CIRISAgent#715 (e714ff3c4) closed all known unwired sites;
**this module guards against re-introducing the gap.**

Three layers:
1. ``test_step_point_mapping_coverage`` — every documented LLM-issuing
   StepPoint maps to a non-None parent. Catches: someone adds a new
   ``StepPoint.X`` that issues LLM calls but forgets the mapping.
2. ``test_known_emission_sites_unchanged`` — snapshot of the small set
   of ``_broadcast_llm_call_event`` callsites in the codebase. Forces
   any new emission site to be reviewed.
3. ``test_*_set_parent_event_context_*`` — direct unit tests of the
   ContextVar machinery that the wider system relies on.

The dynamic end-to-end check (drive a real thought through the pipeline
in mock-LLM mode, capture LLM_CALL events, assert no UNKNOWN_PARENT) lives
in ``tools/qa_runner/modules/streaming_verification.py`` and is exercised
by the ``streaming`` QA module — that catches the runtime-coverage case
the static tests can't.
"""
from __future__ import annotations

import ast
import asyncio
from pathlib import Path
from typing import Set

import pytest

from ciris_engine.logic.buses.llm_call_context import (
    UNKNOWN_PARENT_ATTEMPT_INDEX,
    UNKNOWN_PARENT_EVENT_TYPE,
    get_parent_event_context,
    set_parent_event_context,
)
from ciris_engine.logic.processors.core.step_decorators import (
    _resolve_parent_event_for_step,
)
from ciris_engine.schemas.services.runtime_control import StepPoint


# ---------------------------------------------------------------------------
# StepPoint coverage


# StepPoints that issue LLM calls in the canonical H3ERE pipeline.
# Adding a new LLM-issuing StepPoint? Add it here AND to
# `_resolve_parent_event_for_step()`. The two MUST agree or this test fails.
LLM_ISSUING_STEP_POINTS: Set[StepPoint] = {
    StepPoint.PERFORM_DMAS,
    StepPoint.PERFORM_ASPDMA,
    StepPoint.RECURSIVE_ASPDMA,
    StepPoint.CONSCIENCE_EXECUTION,
    StepPoint.RECURSIVE_CONSCIENCE,
    StepPoint.FINALIZE_ACTION,
}

# StepPoints that DO NOT issue LLM calls — listed here so adding a new
# StepPoint forces a deliberate categorization. If a new value lands in
# the enum without appearing in either set, `test_step_point_categorization`
# fails and the developer must decide which side it belongs on.
NON_LLM_STEP_POINTS: Set[StepPoint] = {
    StepPoint.START_ROUND,
    StepPoint.GATHER_CONTEXT,
    StepPoint.PERFORM_ACTION,
    StepPoint.ACTION_COMPLETE,
    StepPoint.ROUND_COMPLETE,
}


def test_step_point_categorization_is_total():
    """Every StepPoint must be classified as LLM-issuing or not.

    Catches: someone adds a new StepPoint to the enum and the regression
    guard ages out silently because the new value never appears in either
    set. Force a deliberate decision at the test site.
    """
    declared = LLM_ISSUING_STEP_POINTS | NON_LLM_STEP_POINTS
    enum_members = set(StepPoint)
    missing = enum_members - declared
    extra = declared - enum_members
    assert not missing, (
        f"New StepPoint(s) without categorization: {sorted(s.value for s in missing)}. "
        f"Add each to either LLM_ISSUING_STEP_POINTS or NON_LLM_STEP_POINTS in this test."
    )
    assert not extra, (
        f"Categorization references nonexistent StepPoint(s): {sorted(s.value for s in extra)}. "
        f"Remove from LLM_ISSUING_STEP_POINTS / NON_LLM_STEP_POINTS."
    )


@pytest.mark.parametrize("step", sorted(LLM_ISSUING_STEP_POINTS, key=lambda s: s.value))
def test_llm_issuing_step_maps_to_real_parent(step: StepPoint):
    """Every LLM-issuing StepPoint resolves to a non-None parent event.

    A None mapping means LLM calls from that step's handler will hit the
    UNKNOWN_PARENT sentinel — the bug class CIRISAgent#717 guards against.
    """
    parent = _resolve_parent_event_for_step(step)
    assert parent is not None, (
        f"StepPoint.{step.name} is in LLM_ISSUING_STEP_POINTS but "
        f"_resolve_parent_event_for_step() returned None. Add the mapping in "
        f"ciris_engine/logic/processors/core/step_decorators.py."
    )
    parent_event_type, parent_attempt_index = parent
    assert parent_event_type != UNKNOWN_PARENT_EVENT_TYPE, (
        f"StepPoint.{step.name} maps to the UNKNOWN_PARENT sentinel — that's exactly "
        f"the value the sentinel exists to flag as missing."
    )
    assert parent_attempt_index >= 0, (
        f"StepPoint.{step.name} maps to a negative parent_attempt_index — persistence rejects."
    )


@pytest.mark.parametrize("step", sorted(NON_LLM_STEP_POINTS, key=lambda s: s.value))
def test_non_llm_step_maps_to_none(step: StepPoint):
    """Non-LLM-issuing StepPoints map to None — the decorator skips ContextVar setup.

    If this fails, either the StepPoint started issuing LLM calls (move it
    to LLM_ISSUING_STEP_POINTS) or the resolver gained an incorrect mapping.
    """
    assert _resolve_parent_event_for_step(step) is None, (
        f"StepPoint.{step.name} is in NON_LLM_STEP_POINTS but resolves to a parent. "
        f"Either move it to LLM_ISSUING_STEP_POINTS, or remove the spurious mapping."
    )


# ---------------------------------------------------------------------------
# Emission-site snapshot


REPO_ROOT = Path(__file__).resolve().parents[4]  # tests/ciris_engine/logic/buses/test_*.py → repo root


def _find_broadcast_llm_call_emission_sites() -> Set[str]:
    """Walk ciris_engine + ciris_adapters for `_broadcast_llm_call_event(` callsites.

    Returns set of "<relpath>:<line>" strings — sortable, snapshot-stable.
    Ignores definition site + accord_metrics taxonomy comments.
    """
    sites: Set[str] = set()
    target_name = "_broadcast_llm_call_event"
    for root_name in ("ciris_engine", "ciris_adapters"):
        root = REPO_ROOT / root_name
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            if "__pycache__" in py.parts:
                continue
            try:
                tree = ast.parse(py.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue
            for node in ast.walk(tree):
                # Function call: `_broadcast_llm_call_event(...)`
                if isinstance(node, ast.Call):
                    func = node.func
                    if isinstance(func, ast.Name) and func.id == target_name:
                        rel = py.relative_to(REPO_ROOT)
                        sites.add(f"{rel}:{node.lineno}")
    return sites


# Known LLM_CALL emission sites in the agent codebase. Adding a new emitter
# requires updating this set — and that update is your prompt to verify
# the new site is reached only from a `@streaming_step`-decorated handler
# OR explicitly inside a `set_parent_event_context()` `with` block.
EXPECTED_BROADCAST_SITES: Set[str] = {
    "ciris_engine/logic/buses/llm_bus.py:833",  # _execute_llm_call success path
    "ciris_engine/logic/buses/llm_bus.py:953",  # _execute_llm_call error path
}


def test_emission_site_snapshot():
    """Snapshot of every `_broadcast_llm_call_event(` callsite in the codebase.

    If this fails because a NEW site was added, the developer must (a) confirm
    the new site is reached only from a parent-context-aware path (decorator
    or explicit ``with set_parent_event_context(...)``), then (b) add the
    site to ``EXPECTED_BROADCAST_SITES``. This forces deliberate review at
    every new emission, matching the design intent in CIRISAgent#717.

    If it fails because a site MOVED, just update the line number — same
    review-on-touch principle still applies.
    """
    actual = _find_broadcast_llm_call_emission_sites()
    extra = actual - EXPECTED_BROADCAST_SITES
    missing = EXPECTED_BROADCAST_SITES - actual
    assert not extra, (
        f"New _broadcast_llm_call_event() callsite(s) detected: {sorted(extra)}. "
        f"Verify each is reached only from a @streaming_step handler OR an explicit "
        f"`with set_parent_event_context(...):` block, then add to EXPECTED_BROADCAST_SITES."
    )
    assert not missing, (
        f"Removed/moved _broadcast_llm_call_event() callsite(s): {sorted(missing)}. "
        f"Update EXPECTED_BROADCAST_SITES to match current line numbers."
    )


# ---------------------------------------------------------------------------
# ContextVar machinery — defense-in-depth unit tests


def test_default_context_returns_unknown_parent_sentinel():
    """No prior context set → sentinel. The wire-format contract holds."""
    parent_event_type, parent_attempt_index = get_parent_event_context()
    assert parent_event_type == UNKNOWN_PARENT_EVENT_TYPE
    assert parent_attempt_index == UNKNOWN_PARENT_ATTEMPT_INDEX


def test_set_parent_event_context_propagates():
    """`with set_parent_event_context(...)` sets the ContextVar inside the block."""
    with set_parent_event_context("ASPDMA_RESULT", 2):
        assert get_parent_event_context() == ("ASPDMA_RESULT", 2)
    # And resets on exit.
    assert get_parent_event_context() == (UNKNOWN_PARENT_EVENT_TYPE, UNKNOWN_PARENT_ATTEMPT_INDEX)


def test_set_parent_event_context_clamps_negative_index():
    """Negative parent_attempt_index → clamped to 0 with WARN log (persistence rejects negatives)."""
    with set_parent_event_context("DMA_RESULTS", -1):
        parent_event_type, parent_attempt_index = get_parent_event_context()
    assert parent_event_type == "DMA_RESULTS"
    assert parent_attempt_index == 0


def test_set_parent_event_context_isolates_across_async_tasks():
    """ContextVar isolation — concurrent thoughts each see their own parent context."""

    async def task(name: str, parent_event_type: str, parent_attempt_index: int) -> tuple:
        with set_parent_event_context(parent_event_type, parent_attempt_index):
            await asyncio.sleep(0)  # yield to other tasks
            return (name, *get_parent_event_context())

    async def driver() -> list:
        results = await asyncio.gather(
            task("a", "DMA_RESULTS", 0),
            task("b", "ASPDMA_RESULT", 1),
            task("c", "CONSCIENCE_RESULT", 2),
        )
        return results

    results = asyncio.run(driver())
    assert results == [
        ("a", "DMA_RESULTS", 0),
        ("b", "ASPDMA_RESULT", 1),
        ("c", "CONSCIENCE_RESULT", 2),
    ]
