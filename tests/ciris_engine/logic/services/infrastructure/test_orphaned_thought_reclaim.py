"""Thoughts left PROCESSING by a dead process are reclaimed at startup (#1018).

The defect: nothing reset them, so the parent task stayed ACTIVE forever. Worse,
`get_tasks_needing_recovery_thought` only recovers tasks with NO
pending/processing thoughts — so the stuck row **suppressed the recovery that
would have fixed it**. A permanently-stuck thought is indistinguishable from a
healthy in-flight one, and the longer it sits the healthier it looks.

In the reporting database, exactly one shutdown seed thought had ever reached
`completed`; every interrupted shutdown since January left a permanent artifact.

The safety property that matters for multi-occurrence: a booting process may
reclaim only ITS OWN rows. A peer's PROCESSING thought may be genuinely in
flight, and aborting it would kill live work on another node.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import List

import pytest

from ciris_engine.logic.services.infrastructure.database_maintenance.service import (
    DatabaseMaintenanceService,
)
from ciris_engine.schemas.runtime.enums import ThoughtStatus

MODULE = "ciris_engine.logic.services.infrastructure.database_maintenance.service"
THOUGHTS = "ciris_engine.logic.persistence.models.thoughts"
OCC = "ciris_engine.logic.utils.occurrence_utils"


def _thought(tid: str, task_id: str, occ: str) -> SimpleNamespace:
    return SimpleNamespace(thought_id=tid, source_task_id=task_id, agent_occurrence_id=occ)


def _service() -> DatabaseMaintenanceService:
    return DatabaseMaintenanceService.__new__(DatabaseMaintenanceService)


@pytest.mark.asyncio
async def test_stranded_processing_thoughts_are_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    stranded = [
        _thought("th_seed_SHUTDOWN_3c7b47c5-b52", "SHUTDOWN_SHARED_20260809", "default"),
        _thought("th_followup_x", "TASK_A", "default"),
    ]
    updates: List[tuple] = []

    monkeypatch.setattr(f"{OCC}.get_current_occurrence_id", lambda: "default")
    monkeypatch.setattr(f"{THOUGHTS}.get_thoughts_by_status", lambda s, o=None, **k: stranded)
    monkeypatch.setattr(
        f"{THOUGHTS}.update_thought_status",
        lambda tid, status, occ=None, **k: (updates.append((tid, status, occ)), True)[1],
    )

    await _service()._reclaim_orphaned_processing_thoughts()

    assert len(updates) == 2
    assert {u[0] for u in updates} == {"th_seed_SHUTDOWN_3c7b47c5-b52", "th_followup_x"}
    assert all(u[1] is ThoughtStatus.FAILED for u in updates), (
        "must FAIL, not re-PEND: the thought died at an unknown point with unknown "
        "side effects, and re-running a SHUTDOWN seed re-executes a days-old shutdown"
    )


@pytest.mark.asyncio
async def test_only_this_occurrence_is_reclaimed(monkeypatch: pytest.MonkeyPatch) -> None:
    """The multi-occurrence safety property.

    A peer's PROCESSING thought may be genuinely in flight. The query must be
    scoped to this occurrence, or booting one node aborts live work on another.
    """
    seen_scope: List[str] = []

    def _by_status(status, occurrence_id="default", **kwargs):
        seen_scope.append(occurrence_id)
        return []

    monkeypatch.setattr(f"{OCC}.get_current_occurrence_id", lambda: "002")
    monkeypatch.setattr(f"{THOUGHTS}.get_thoughts_by_status", _by_status)

    await _service()._reclaim_orphaned_processing_thoughts()

    assert seen_scope == ["002"], (
        f"reclaim queried scope {seen_scope}; it must ask only about its own "
        "occurrence, never globally"
    )


@pytest.mark.asyncio
async def test_a_failed_row_does_not_stop_the_sweep(monkeypatch: pytest.MonkeyPatch) -> None:
    """One bad row must not block boot, nor silently truncate the sweep."""
    stranded = [_thought("bad", "T", "default"), _thought("good", "T", "default")]
    done: List[str] = []

    def _update(tid, status, occ=None, **kwargs):
        if tid == "bad":
            raise RuntimeError("row is wedged")
        done.append(tid)
        return True

    monkeypatch.setattr(f"{OCC}.get_current_occurrence_id", lambda: "default")
    monkeypatch.setattr(f"{THOUGHTS}.get_thoughts_by_status", lambda s, o=None, **k: stranded)
    monkeypatch.setattr(f"{THOUGHTS}.update_thought_status", _update)

    await _service()._reclaim_orphaned_processing_thoughts()

    assert done == ["good"], "the sweep must continue past a row it cannot fail"


@pytest.mark.asyncio
async def test_reclaim_runs_before_anything_reads_thought_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ordering is load-bearing, not cosmetic.

    Every later cleanup step reads thought status; a stranded PROCESSING row is
    what makes those reads wrong. If the reclaim drifts later in the sequence the
    bug returns silently, so the order is asserted on the source.
    """
    import inspect

    src = inspect.getsource(DatabaseMaintenanceService.perform_startup_cleanup)
    reclaim = src.find("_reclaim_orphaned_processing_thoughts")
    invalid = src.find("_cleanup_invalid_thoughts")
    stale = src.find("_cleanup_stale_wakeup_tasks")

    assert reclaim != -1, "the reclaim is no longer called at startup"
    assert reclaim < invalid, "reclaim must precede _cleanup_invalid_thoughts"
    assert reclaim < stale, "reclaim must precede _cleanup_stale_wakeup_tasks"


@pytest.mark.asyncio
async def test_never_raises_out_of_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    """Boot must survive a broken reclaim; the agent starting matters more."""
    monkeypatch.setattr(f"{OCC}.get_current_occurrence_id", lambda: "default")

    def _boom(*a, **k):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(f"{THOUGHTS}.get_thoughts_by_status", _boom)
    await _service()._reclaim_orphaned_processing_thoughts()  # must not raise
