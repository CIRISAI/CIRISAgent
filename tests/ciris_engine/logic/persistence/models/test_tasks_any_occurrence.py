"""Unit tests for get_task_by_id_any_occurrence and get_task_occurrence_id_for_update."""

from unittest.mock import Mock, patch

import pytest

from ciris_engine.logic.persistence.models.tasks import get_task_by_id_any_occurrence, get_task_occurrence_id_for_update
from ciris_engine.schemas.runtime.enums import TaskStatus
from ciris_engine.schemas.runtime.models import Task


class TestGetTaskByIdAnyOccurrence:
    """Tests for get_task_by_id_any_occurrence function."""

    def test_returns_task_with_default_occurrence(self):
        """Should return task with default occurrence_id."""
        mock_task = Task(
            task_id="task_123",
            agent_occurrence_id="default",
            channel_id="test_channel",
            description="Test task",
            status=TaskStatus.PENDING,
            created_at="2025-10-31T00:00:00+00:00",
            updated_at="2025-10-31T00:00:00+00:00",
        )

        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn, patch(
            "ciris_engine.logic.persistence.models.tasks.map_row_to_task", return_value=mock_task
        ):
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {"task_id": "task_123"}  # Minimal row
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_by_id_any_occurrence("task_123")

            # Verify SQL doesn't filter by occurrence_id
            sql = mock_cursor.execute.call_args[0][0]
            assert "WHERE task_id = ?" in sql
            assert "agent_occurrence_id" not in sql
            assert "LIMIT 1" in sql

            # Verify params only include task_id
            params = mock_cursor.execute.call_args[0][1]
            assert params == ("task_123",)

            # Verify returns task
            assert result is not None
            assert isinstance(result, Task)
            assert result.agent_occurrence_id == "default"

    def test_returns_task_with_shared_occurrence(self):
        """Should return task with __shared__ occurrence_id."""
        mock_task = Task(
            task_id="SHUTDOWN_SHARED_20251031",
            agent_occurrence_id="__shared__",
            channel_id="system",
            description="Shared shutdown task",
            status=TaskStatus.ACTIVE,
            created_at="2025-10-31T00:00:00+00:00",
            updated_at="2025-10-31T00:00:00+00:00",
        )

        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn, patch(
            "ciris_engine.logic.persistence.models.tasks.map_row_to_task", return_value=mock_task
        ):
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {"task_id": "SHUTDOWN_SHARED_20251031"}
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_by_id_any_occurrence("SHUTDOWN_SHARED_20251031")

            assert result is not None
            assert result.agent_occurrence_id == "__shared__"

    def test_returns_task_with_transferred_occurrence(self):
        """Should return task that was transferred to specific occurrence (e.g., occurrence-a)."""
        mock_task = Task(
            task_id="WAKEUP_SHARED_20251031",
            agent_occurrence_id="occurrence-a",
            channel_id="system",
            description="Claimed wakeup task",
            status=TaskStatus.ACTIVE,
            created_at="2025-10-31T00:00:00+00:00",
            updated_at="2025-10-31T00:00:00+00:00",
        )

        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn, patch(
            "ciris_engine.logic.persistence.models.tasks.map_row_to_task", return_value=mock_task
        ):
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {"task_id": "WAKEUP_SHARED_20251031"}
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_by_id_any_occurrence("WAKEUP_SHARED_20251031")

            assert result is not None
            assert result.agent_occurrence_id == "occurrence-a"

    def test_returns_none_when_task_not_found(self):
        """Should return None when task doesn't exist."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None  # No task found
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_by_id_any_occurrence("nonexistent_task")

            assert result is None

    def test_handles_database_exception(self):
        """Should handle database exceptions gracefully and return None."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_conn.side_effect = Exception("Database connection failed")

            result = get_task_by_id_any_occurrence("task_123")

            assert result is None

    def test_accepts_custom_db_path(self):
        """Should accept and use custom database path."""
        mock_task = Task(
            task_id="task_123",
            agent_occurrence_id="default",
            channel_id="test_channel",
            description="Test",
            status=TaskStatus.PENDING,
            created_at="2025-10-31T00:00:00+00:00",
            updated_at="2025-10-31T00:00:00+00:00",
        )

        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn, patch(
            "ciris_engine.logic.persistence.models.tasks.map_row_to_task", return_value=mock_task
        ):
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {"task_id": "task_123"}
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_by_id_any_occurrence("task_123", db_path="/custom/path/db.sqlite")

            # Verify custom db_path was passed
            mock_conn.assert_called_once_with("/custom/path/db.sqlite")
            assert result is not None

    def test_sql_query_structure(self):
        """Should generate correct SQL query structure."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            get_task_by_id_any_occurrence("test_task")

            sql = mock_cursor.execute.call_args[0][0]

            # Verify SQL structure
            assert "SELECT * FROM tasks" in sql
            assert "WHERE task_id = ?" in sql
            assert "LIMIT 1" in sql
            # Should NOT filter by occurrence_id
            assert "agent_occurrence_id = ?" not in sql


class TestGetTaskOccurrenceIdForUpdate:
    """Tests for get_task_occurrence_id_for_update function."""

    def test_returns_default_occurrence_id(self):
        """Should return 'default' occurrence_id for single-occurrence task."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = ("default",)  # Row with occurrence_id
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_occurrence_id_for_update("task_123")

            # Verify SQL queries only agent_occurrence_id
            sql = mock_cursor.execute.call_args[0][0]
            assert "SELECT agent_occurrence_id FROM tasks" in sql
            assert "WHERE task_id = ?" in sql
            assert "LIMIT 1" in sql

            # Verify params
            params = mock_cursor.execute.call_args[0][1]
            assert params == ("task_123",)

            # Verify result
            assert result == "default"

    def test_returns_shared_occurrence_id(self):
        """Should return '__shared__' occurrence_id for unclaimed shared task."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = ("__shared__",)
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_occurrence_id_for_update("SHUTDOWN_SHARED_20251031")

            assert result == "__shared__"

    def test_returns_transferred_occurrence_id(self):
        """Should return specific occurrence_id for transferred/claimed task."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = ("occurrence-b",)  # After transfer
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_occurrence_id_for_update("WAKEUP_SHARED_20251031")

            assert result == "occurrence-b"

    def test_returns_none_when_task_not_found(self):
        """Should return None when task doesn't exist."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None  # No task found
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_occurrence_id_for_update("nonexistent_task")

            assert result is None

    def test_handles_database_exception(self):
        """Should handle database exceptions gracefully and return None."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_conn.side_effect = Exception("Database error")

            result = get_task_occurrence_id_for_update("task_123")

            assert result is None

    def test_accepts_custom_db_path(self):
        """Should accept and use custom database path."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = ("default",)
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_occurrence_id_for_update("task_123", db_path="/custom/db.sqlite")

            # Verify custom db_path was passed
            mock_conn.assert_called_once_with("/custom/db.sqlite")
            assert result == "default"

    def test_returns_str_type(self):
        """Should return string type for mypy type safety (no Any return)."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = ("occurrence-xyz",)
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_occurrence_id_for_update("task_123")

            # Verify explicit string type (not Any)
            assert isinstance(result, str)
            assert result == "occurrence-xyz"

    def test_sql_only_selects_occurrence_id(self):
        """Should select only agent_occurrence_id column for efficiency."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = ("default",)
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            get_task_occurrence_id_for_update("task_123")

            sql = mock_cursor.execute.call_args[0][0]

            # Should select only occurrence_id column, not SELECT *
            assert "SELECT agent_occurrence_id FROM tasks" in sql
            assert "SELECT *" not in sql


class TestMultiOccurrenceScenarios:
    """Integration-style tests covering all multi-occurrence scenarios."""

    @pytest.mark.parametrize(
        "task_id,occurrence_id,description",
        [
            ("regular_task", "default", "Single-occurrence task"),
            ("SHUTDOWN_SHARED_20251031", "__shared__", "Unclaimed shared task"),
            ("WAKEUP_SHARED_20251031", "occurrence-a", "Claimed/transferred task"),
            ("api_task_456", "occurrence-c", "Multi-occurrence claimed task"),
        ],
    )
    def test_get_task_by_id_any_occurrence_handles_all_scenarios(self, task_id, occurrence_id, description):
        """Should handle all occurrence scenarios without filtering."""
        mock_task = Task(
            task_id=task_id,
            agent_occurrence_id=occurrence_id,
            channel_id="system",
            description=description,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-31T00:00:00+00:00",
            updated_at="2025-10-31T00:00:00+00:00",
        )

        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn, patch(
            "ciris_engine.logic.persistence.models.tasks.map_row_to_task", return_value=mock_task
        ):
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = {"task_id": task_id}
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

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
    def test_get_task_occurrence_id_for_update_handles_all_scenarios(self, task_id, occurrence_id):
        """Should return correct occurrence_id for all scenarios."""
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = (occurrence_id,)
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            result = get_task_occurrence_id_for_update(task_id)

            assert result == occurrence_id
