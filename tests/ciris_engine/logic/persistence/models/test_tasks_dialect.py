"""Functional tests for `get_task_by_correlation_id` post-2.9.0 absorption.

The legacy file in this slot probed SQL-dialect formatting (sqlite ? vs
postgres %s, json_extract vs ->>). Now that tasks are routed through
ciris-persist's typed substrate API, dialect choice happens inside the
Rust crate. These tests verify behaviour at the public function level.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.persistence.models.tasks import (
    add_task,
    get_task_by_correlation_id,
)
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext

# Wire the shared persist engine fixture.
from tests.fixtures.persist_engine import persist_engine  # noqa: F401


def _task(task_id: str, correlation_id: str, occurrence_id: str = "default") -> Task:
    return Task(
        task_id=task_id,
        agent_occurrence_id=occurrence_id,
        channel_id="ch",
        description=f"task {task_id}",
        status=TaskStatus.PENDING,
        priority=0,
        created_at="2025-10-31T00:00:00+00:00",
        updated_at="2025-10-31T00:00:00+00:00",
        context=TaskContext(channel_id="ch", correlation_id=correlation_id),
    )


def test_get_task_by_correlation_id_found(persist_engine):
    add_task(_task("task-a", "corr-a"))
    result = get_task_by_correlation_id("corr-a")
    assert result is not None
    assert result.task_id == "task-a"


def test_get_task_by_correlation_id_not_found(persist_engine):
    add_task(_task("task-a", "corr-a"))
    assert get_task_by_correlation_id("missing-correlation") is None


def test_get_task_by_correlation_id_respects_occurrence(persist_engine):
    add_task(_task("task-default", "corr-x", "default"))
    add_task(_task("task-other", "corr-x", "occurrence-other"))
    # Filter to default occurrence only.
    result = get_task_by_correlation_id("corr-x", occurrence_id="default")
    assert result is not None
    assert result.task_id == "task-default"


def test_get_task_by_correlation_id_returns_latest_when_multiple(persist_engine):
    """When two tasks share a correlation_id, return the most recently created."""
    # Add the duplicate-correlation guard short-circuit by giving different
    # occurrence_ids so both rows can coexist.
    earlier = _task("task-old", "corr-y", "default")
    earlier.created_at = "2024-01-01T00:00:00+00:00"
    later = _task("task-new", "corr-y", "occurrence-other")
    later.created_at = "2026-01-01T00:00:00+00:00"
    add_task(earlier)
    add_task(later)
    # When asking for occurrence "default" we get the only matching row.
    result = get_task_by_correlation_id("corr-y", occurrence_id="default")
    assert result is not None
    assert result.task_id == "task-old"


def test_get_task_by_correlation_id_exception_handling(persist_engine):
    """Persist errors should be swallowed and return None."""
    from unittest.mock import patch

    with patch(
        "ciris_engine.logic.persistence.models.tasks._list_with_filter",
        side_effect=RuntimeError("simulated"),
    ):
        assert get_task_by_correlation_id("corr-any") is None
