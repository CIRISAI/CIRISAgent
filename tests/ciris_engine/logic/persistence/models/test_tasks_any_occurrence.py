"""Unit tests for `get_task_by_id_any_occurrence` and `get_task_occurrence_id_for_update`.

Post-2.9.0 absorption these functions route through ciris-persist's substrate
API rather than raw sqlite3. Tests use the shared `persist_engine` fixture to
wire a real Engine and exercise the public functions end-to-end.
"""

from __future__ import annotations

import pytest

from ciris_engine.logic.persistence.models.tasks import (
    add_task,
    get_task_by_id_any_occurrence,
    get_task_occurrence_id_for_update,
)
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext


# Pull in the shared `persist_engine` fixture so the engine is wired
# before each test (and unwired on teardown for test ordering safety).
from tests.fixtures.persist_engine import persist_engine  # noqa: F401


def _make_task(task_id: str, occurrence_id: str = "default") -> Task:
    return Task(
        task_id=task_id,
        agent_occurrence_id=occurrence_id,
        channel_id="ch",
        description=f"task {task_id}",
        status=TaskStatus.PENDING,
        priority=0,
        created_at="2025-10-31T00:00:00+00:00",
        updated_at="2025-10-31T00:00:00+00:00",
        context=TaskContext(channel_id="ch", correlation_id=f"corr-{task_id}"),
    )


class TestGetTaskByIdAnyOccurrence:
    def test_returns_task_with_default_occurrence(self, persist_engine):
        add_task(_make_task("task_123", "default"))
        result = get_task_by_id_any_occurrence("task_123")
        assert result is not None
        assert isinstance(result, Task)
        assert result.task_id == "task_123"
        assert result.agent_occurrence_id == "default"

    def test_returns_task_with_shared_occurrence(self, persist_engine):
        add_task(_make_task("SHUTDOWN_SHARED_20251031", "__shared__"))
        result = get_task_by_id_any_occurrence("SHUTDOWN_SHARED_20251031")
        assert result is not None
        assert result.agent_occurrence_id == "__shared__"

    def test_returns_task_with_transferred_occurrence(self, persist_engine):
        add_task(_make_task("WAKEUP_SHARED_20251031", "occurrence-a"))
        result = get_task_by_id_any_occurrence("WAKEUP_SHARED_20251031")
        assert result is not None
        assert result.agent_occurrence_id == "occurrence-a"

    def test_returns_none_when_task_not_found(self, persist_engine):
        assert get_task_by_id_any_occurrence("missing-task") is None

    def test_handles_database_exception(self, persist_engine):
        """Should swallow persist errors and return None."""
        from unittest.mock import patch

        with patch(
            "ciris_engine.logic.persistence.models.tasks._get_engine"
        ) as mock_engine:
            mock_engine.return_value.task_get.side_effect = RuntimeError("simulated")
            assert get_task_by_id_any_occurrence("anything") is None

    def test_accepts_custom_db_path(self, persist_engine):
        """db_path is preserved for back-compat but unused; should still work."""
        add_task(_make_task("task_x", "default"))
        result = get_task_by_id_any_occurrence("task_x")
        assert result is not None
        assert result.task_id == "task_x"


class TestGetTaskOccurrenceIdForUpdate:
    def test_returns_default_occurrence_id(self, persist_engine):
        add_task(_make_task("task_123", "default"))
        assert get_task_occurrence_id_for_update("task_123") == "default"

    def test_returns_shared_occurrence_id(self, persist_engine):
        add_task(_make_task("SHUTDOWN_SHARED_20251031", "__shared__"))
        assert get_task_occurrence_id_for_update("SHUTDOWN_SHARED_20251031") == "__shared__"

    def test_returns_transferred_occurrence_id(self, persist_engine):
        add_task(_make_task("WAKEUP_SHARED_20251031", "occurrence-a"))
        assert get_task_occurrence_id_for_update("WAKEUP_SHARED_20251031") == "occurrence-a"

    def test_returns_none_when_task_not_found(self, persist_engine):
        assert get_task_occurrence_id_for_update("missing") is None

    def test_handles_database_exception(self, persist_engine):
        from unittest.mock import patch

        with patch(
            "ciris_engine.logic.persistence.models.tasks._get_engine"
        ) as mock_engine:
            mock_engine.return_value.task_get.side_effect = RuntimeError("simulated")
            assert get_task_occurrence_id_for_update("any") is None

    def test_accepts_custom_db_path(self, persist_engine):
        add_task(_make_task("task_y", "default"))
        assert get_task_occurrence_id_for_update("task_y") == "default"

    def test_returns_str_type(self, persist_engine):
        add_task(_make_task("task_z", "default"))
        assert isinstance(get_task_occurrence_id_for_update("task_z"), str)


class TestMultiOccurrenceScenarios:
    @pytest.mark.parametrize(
        "task_id,occurrence_id,description",
        [
            ("regular_task", "default", "Single-occurrence task"),
            ("SHUTDOWN_SHARED_20251031", "__shared__", "Unclaimed shared task"),
            ("WAKEUP_SHARED_20251031", "occurrence-a", "Claimed/transferred task"),
            ("api_task_456", "occurrence-c", "Multi-occurrence claimed task"),
        ],
    )
    def test_get_task_by_id_any_occurrence_handles_all_scenarios(
        self, persist_engine, task_id, occurrence_id, description
    ):
        add_task(_make_task(task_id, occurrence_id))
        result = get_task_by_id_any_occurrence(task_id)
        assert result is not None
        assert result.task_id == task_id
        assert result.agent_occurrence_id == occurrence_id

    @pytest.mark.parametrize(
        "task_id,occurrence_id",
        [
            ("regular_task", "default"),
            ("SHUTDOWN_SHARED_20251031", "__shared__"),
            ("WAKEUP_SHARED_20251031", "occurrence-a"),
        ],
    )
    def test_get_task_occurrence_id_for_update_handles_all_scenarios(
        self, persist_engine, task_id, occurrence_id
    ):
        add_task(_make_task(task_id, occurrence_id))
        assert get_task_occurrence_id_for_update(task_id) == occurrence_id
