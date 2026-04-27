"""Tests for thought-batch parallelism (`thought_batch_size` config + the
batching loop in `AgentProcessor._process_pending_thoughts_async`).

Why the cap matters: each thought processed in parallel fans out to ~4
conscience LLM calls running concurrently (entropy/coherence/opt-veto/
epistemic-humility). A batch of N thoughts therefore creates ~4N parallel
structured-output requests in burst. On rate-limited backends (e.g.
Together gemma-4-31B-it under per-account throttling) bursts above ~12
parallel requests queue past the conscience timeout and the agent
gets stuck in WAKEUP.

These tests pin:
  1. Default `thought_batch_size = 3` (12 parallel calls) — the cap that
     keeps WAKEUP within the typical structured-output throughput of
     mid-tier hosted backends.
  2. Override via `EssentialConfig.workflow.thought_batch_size` works.
  3. The processor honors the configured value: 9 thoughts at batch=3
     produces 3 batches of 3.
  4. Backward-compat fallback: if `app_config.workflow` is None or the
     field is missing, the processor uses 3 (does NOT regress to the
     hardcoded 5 from before).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.schemas.config.essential import OperationalLimitsConfig


# ────────────────────────────── config schema ────────────────────────────


def test_thought_batch_size_default_is_3() -> None:
    """The default cap is 3 thoughts in flight (12 concurrent conscience
    calls). Any change to this default needs to be a deliberate decision
    coordinated with backend throughput planning."""
    cfg = OperationalLimitsConfig()
    assert cfg.thought_batch_size == 3


def test_thought_batch_size_can_be_overridden() -> None:
    """Operators raising the cap (faster backend) or lowering it
    (extreme rate limit) should be able to without code changes."""
    cfg = OperationalLimitsConfig(thought_batch_size=5)
    assert cfg.thought_batch_size == 5

    cfg = OperationalLimitsConfig(thought_batch_size=1)
    assert cfg.thought_batch_size == 1


def test_thought_batch_size_validates_int() -> None:
    """Field is typed as int — anything else raises validation error."""
    with pytest.raises(Exception):
        OperationalLimitsConfig(thought_batch_size="three")  # type: ignore[arg-type]


# ────────────────────────────── batching loop ────────────────────────────


def _make_thought(thought_id: str, task_id: str = "task_1") -> Any:
    """Minimal thought stub with the fields the processor reads."""
    return SimpleNamespace(thought_id=thought_id, source_task_id=task_id)


@pytest.fixture
def patch_persistence(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Patch persistence calls so the batching loop runs against an
    in-memory thought list. Returns the mock objects so tests can read
    counts."""
    pending_thoughts: List[Any] = []
    prefetched: dict[str, Any] = {}

    async def _async_get_thoughts_by_ids(ids: list[str], _occurrence_id: str) -> dict[str, Any]:
        return {tid: prefetched.get(tid, _make_thought(tid)) for tid in ids}

    def _get_pending(_occurrence_id: str) -> list[Any]:
        return list(pending_thoughts)

    def _update_status(**_kwargs: Any) -> None:
        pass

    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.main_processor.persistence.get_pending_thoughts_for_active_tasks",
        _get_pending,
    )
    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.main_processor.persistence.async_get_thoughts_by_ids",
        _async_get_thoughts_by_ids,
    )
    monkeypatch.setattr(
        "ciris_engine.logic.processors.core.main_processor.persistence.update_thought_status",
        _update_status,
    )
    # Stub the batch-context prefetch
    async def _prefetch(*_args: Any, **_kwargs: Any) -> Any:
        return None

    # `prefetch_batch_context` is imported lazily inside the method body
    # rather than at module top — patch it on its source module so the
    # local import inside `_process_pending_thoughts_async` picks it up.
    monkeypatch.setattr(
        "ciris_engine.logic.context.batch_context.prefetch_batch_context",
        _prefetch,
    )
    return {"pending_thoughts": pending_thoughts, "prefetched": prefetched}


def _make_processor(batch_size: int | None, *, workflow_present: bool = True) -> Any:
    """Construct a minimal AgentProcessor stub with the fields the batch
    method touches. We instantiate via __new__ to bypass the heavyweight
    init."""
    from ciris_engine.logic.processors.core.main_processor import AgentProcessor

    proc = AgentProcessor.__new__(AgentProcessor)
    proc.agent_occurrence_id = "test_occurrence"

    # Build app_config with optional workflow.thought_batch_size
    if workflow_present:
        if batch_size is None:
            workflow = SimpleNamespace(max_active_thoughts=100)  # field absent
        else:
            workflow = SimpleNamespace(
                max_active_thoughts=100,
                thought_batch_size=batch_size,
            )
        proc.app_config = SimpleNamespace(workflow=workflow)
    else:
        proc.app_config = SimpleNamespace(workflow=None)

    # state_manager.get_state() — return WAKEUP so no SHUTDOWN filtering
    state_mgr = MagicMock()
    state_mgr.get_state.return_value = MagicMock(name="WAKEUP-state")
    proc.state_manager = state_mgr

    # _process_single_thought is the unit of work — mock as instant no-op
    proc._process_single_thought = AsyncMock(return_value={"action": "speak"})

    # `_process_pending_thoughts_async` calls `self._get_service(...)` and
    # `self.runtime` to build prefetch arguments; we stub them but don't
    # exercise the prefetch path itself (it's no-op'd via patch_persistence).
    proc._get_service = lambda _name: None
    proc.services = MagicMock()
    proc.runtime = MagicMock()

    return proc


@pytest.mark.asyncio
async def test_batch_size_3_splits_9_thoughts_into_3_batches(
    patch_persistence: dict[str, Any],
) -> None:
    """9 thoughts × batch_size=3 → 3 batches of 3. Verify by counting
    `_process_single_thought` invocations and that asyncio.gather sees
    batches of size 3."""
    patch_persistence["pending_thoughts"][:] = [_make_thought(f"th_{i}") for i in range(9)]

    proc = _make_processor(batch_size=3)

    gather_call_sizes: list[int] = []
    real_gather = __import__("asyncio").gather

    async def _spy_gather(*tasks, return_exceptions=False):
        gather_call_sizes.append(len(tasks))
        return await real_gather(*tasks, return_exceptions=return_exceptions)

    with patch("ciris_engine.logic.processors.core.main_processor.asyncio.gather", _spy_gather):
        n_processed = await proc._process_pending_thoughts_async()

    assert n_processed == 9
    assert proc._process_single_thought.await_count == 9
    assert gather_call_sizes == [3, 3, 3], (
        f"expected 3 batches of 3, got batch sizes {gather_call_sizes}"
    )


@pytest.mark.asyncio
async def test_batch_size_5_splits_9_into_5_4(
    patch_persistence: dict[str, Any],
) -> None:
    """Operator override to 5: 9 thoughts → batches of 5 + 4."""
    patch_persistence["pending_thoughts"][:] = [_make_thought(f"th_{i}") for i in range(9)]

    proc = _make_processor(batch_size=5)

    gather_call_sizes: list[int] = []
    real_gather = __import__("asyncio").gather

    async def _spy_gather(*tasks, return_exceptions=False):
        gather_call_sizes.append(len(tasks))
        return await real_gather(*tasks, return_exceptions=return_exceptions)

    with patch("ciris_engine.logic.processors.core.main_processor.asyncio.gather", _spy_gather):
        await proc._process_pending_thoughts_async()

    assert gather_call_sizes == [5, 4]


@pytest.mark.asyncio
async def test_batch_size_1_serializes_calls(
    patch_persistence: dict[str, Any],
) -> None:
    """batch=1 forces fully serial processing — for extreme-throttle
    backends or single-occupancy tests."""
    patch_persistence["pending_thoughts"][:] = [_make_thought(f"th_{i}") for i in range(4)]

    proc = _make_processor(batch_size=1)

    gather_call_sizes: list[int] = []
    real_gather = __import__("asyncio").gather

    async def _spy_gather(*tasks, return_exceptions=False):
        gather_call_sizes.append(len(tasks))
        return await real_gather(*tasks, return_exceptions=return_exceptions)

    with patch("ciris_engine.logic.processors.core.main_processor.asyncio.gather", _spy_gather):
        await proc._process_pending_thoughts_async()

    assert gather_call_sizes == [1, 1, 1, 1]


@pytest.mark.asyncio
async def test_workflow_none_falls_back_to_default_3(
    patch_persistence: dict[str, Any],
) -> None:
    """`app_config.workflow` is None (legacy / minimal config) → the
    processor uses the default 3, NOT the previous hardcoded 5."""
    patch_persistence["pending_thoughts"][:] = [_make_thought(f"th_{i}") for i in range(7)]

    proc = _make_processor(batch_size=None, workflow_present=False)

    gather_call_sizes: list[int] = []
    real_gather = __import__("asyncio").gather

    async def _spy_gather(*tasks, return_exceptions=False):
        gather_call_sizes.append(len(tasks))
        return await real_gather(*tasks, return_exceptions=return_exceptions)

    with patch("ciris_engine.logic.processors.core.main_processor.asyncio.gather", _spy_gather):
        await proc._process_pending_thoughts_async()

    # 7 thoughts at default 3 → batches of 3, 3, 1
    assert gather_call_sizes == [3, 3, 1]


@pytest.mark.asyncio
async def test_workflow_present_but_field_missing_falls_back_to_3(
    patch_persistence: dict[str, Any],
) -> None:
    """`app_config.workflow.thought_batch_size` field missing (older config
    objects) → still 3, not the hardcoded 5 from before."""
    patch_persistence["pending_thoughts"][:] = [_make_thought(f"th_{i}") for i in range(7)]

    proc = _make_processor(batch_size=None, workflow_present=True)

    gather_call_sizes: list[int] = []
    real_gather = __import__("asyncio").gather

    async def _spy_gather(*tasks, return_exceptions=False):
        gather_call_sizes.append(len(tasks))
        return await real_gather(*tasks, return_exceptions=return_exceptions)

    with patch("ciris_engine.logic.processors.core.main_processor.asyncio.gather", _spy_gather):
        await proc._process_pending_thoughts_async()

    assert gather_call_sizes == [3, 3, 1]


@pytest.mark.asyncio
async def test_batch_size_does_not_change_total_processed(
    patch_persistence: dict[str, Any],
) -> None:
    """Different batch sizes still process every thought — they only
    change how many run in parallel per gather call."""
    for bs, n_thoughts in [(1, 5), (2, 5), (3, 5), (5, 5), (10, 5)]:
        patch_persistence["pending_thoughts"][:] = [_make_thought(f"th_{bs}_{i}") for i in range(n_thoughts)]
        proc = _make_processor(batch_size=bs)
        n_processed = await proc._process_pending_thoughts_async()
        assert n_processed == n_thoughts, f"batch_size={bs}: processed {n_processed}/{n_thoughts}"
