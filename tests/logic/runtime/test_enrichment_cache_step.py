"""The context-enrichment cache is warmed at boot.

Shipped in 2.4.2 (#669), the "Populate Context Enrichment Cache" step was only
ever registered by ``initialization_steps.register_all_initialization_steps`` —
a dead duplicate registrar with no callers. The live registrar,
``CIRISRuntime._register_initialization_steps``, registered 14 steps and left
this one out, so ``populate_enrichment_cache_at_startup`` never ran at boot and
every first thought paid the full per-tool enrichment latency.

These tests lock the step into the live registrar with the properties that make
it safe to run there: SERVICES phase, non-critical, and ordered after the
adapters that provide the tools.
"""

from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.runtime.ciris_runtime import CIRISRuntime
from ciris_engine.schemas.services.operations import InitializationPhase

STEP_NAME = "Populate Context Enrichment Cache"


def _registered_steps() -> List[Tuple[InitializationPhase, str, bool, Optional[float]]]:
    """Drive the live registrar and capture what it registers.

    ``object.__new__`` avoids the full runtime dependency graph — the registrar
    only binds methods off the class, it reads no instance state.
    """
    runtime = object.__new__(CIRISRuntime)
    manager = MagicMock()
    captured: List[Tuple[InitializationPhase, str, bool, Optional[float]]] = []

    def capture(phase: InitializationPhase, name: str, handler: Any, **kwargs: Any) -> None:
        assert callable(handler), f"step {name} registered a non-callable handler"
        captured.append((phase, name, bool(kwargs.get("critical", True)), kwargs.get("timeout")))

    manager.register_step.side_effect = capture
    CIRISRuntime._register_initialization_steps(runtime, manager)
    return captured


def test_enrichment_cache_step_is_registered() -> None:
    names = [name for _, name, _, _ in _registered_steps()]
    assert STEP_NAME in names, f"boot never warms the enrichment cache; registered steps: {names}"


def test_enrichment_cache_step_is_non_critical_in_services_phase() -> None:
    step = next(s for s in _registered_steps() if s[1] == STEP_NAME)
    phase, _, critical, timeout = step

    assert phase == InitializationPhase.SERVICES
    # Non-critical by construction: a cold cache must never block boot, because
    # enrichment falls back to running lazily on the first thought.
    assert critical is False
    assert timeout is not None and timeout > 0


def test_enrichment_cache_step_runs_after_the_adapters_that_provide_tools() -> None:
    names = [name for _, name, _, _ in _registered_steps()]
    assert names.index("Register Adapter Services") < names.index(STEP_NAME)
    assert names.index("Load Saved Adapters") < names.index(STEP_NAME)
    assert names.index(STEP_NAME) < names.index("Initialize Maintenance Service")


@pytest.mark.asyncio
async def test_handler_delegates_to_the_startup_population_helper() -> None:
    """The registered handler reaches ``populate_enrichment_cache_at_startup``."""
    runtime = object.__new__(CIRISRuntime)
    tools: Dict[str, Any] = {"api": ["tool"]}

    with (
        patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False),
        patch(
            "ciris_engine.logic.context.system_snapshot_helpers._collect_available_tools",
            new=AsyncMock(return_value=tools),
        ),
        patch(
            "ciris_engine.logic.context.system_snapshot_helpers.populate_enrichment_cache_at_startup",
            new=AsyncMock(),
        ) as populate,
    ):
        await CIRISRuntime._populate_context_enrichment_cache(runtime)

    populate.assert_awaited_once()
    assert populate.await_args is not None
    assert populate.await_args.args[1] == tools


@pytest.mark.asyncio
async def test_handler_swallows_failures() -> None:
    """A failed warm-up must not surface as a boot error."""
    runtime = object.__new__(CIRISRuntime)

    with (
        patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False),
        patch(
            "ciris_engine.logic.context.system_snapshot_helpers._collect_available_tools",
            new=AsyncMock(side_effect=RuntimeError("adapter exploded")),
        ),
    ):
        await CIRISRuntime._populate_context_enrichment_cache(runtime)
