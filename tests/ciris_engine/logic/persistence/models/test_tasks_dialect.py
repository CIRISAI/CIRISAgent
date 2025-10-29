"""Unit tests for tasks.py dialect adapter usage in get_task_by_correlation_id."""

from unittest.mock import Mock, patch

import pytest

from ciris_engine.logic.persistence.models.tasks import get_task_by_correlation_id


@pytest.mark.parametrize(
    "database_type,placeholder,json_extract_fn",
    [
        ("sqlite", "?", "json_extract"),
        ("postgres", "%s", "->>'"),
    ],
)
def test_get_task_by_correlation_id_uses_dialect_adapter(database_type, placeholder, json_extract_fn):
    """Test that get_task_by_correlation_id uses correct dialect adapter for SQL generation."""
    # Mock the dialect adapter
    mock_adapter = Mock()
    mock_adapter.placeholder.return_value = placeholder

    if database_type == "sqlite":
        mock_adapter.json_extract.return_value = "json_extract(context_json, '$.correlation_id')"
    else:  # postgres
        mock_adapter.json_extract.return_value = "(context_json->>'correlation_id')"

    with patch("ciris_engine.logic.persistence.db.dialect.get_adapter", return_value=mock_adapter):
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            # Mock database connection and cursor
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None  # No task found
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            # Call function
            result = get_task_by_correlation_id(
                correlation_id="test_correlation_id",
                occurrence_id="default",
                db_path="/tmp/test.db",
            )

            # Verify result
            assert result is None  # No task found

            # Verify dialect adapter methods were called
            mock_adapter.placeholder.assert_called()
            mock_adapter.json_extract.assert_called_once_with("context_json", "$.correlation_id")

            # Verify SQL was executed with correct params
            mock_cursor.execute.assert_called_once()
            sql, params = mock_cursor.execute.call_args[0]

            # Verify SQL contains dialect-specific elements
            assert json_extract_fn in sql
            assert placeholder in sql

            # Verify params are correct (occurrence_id, correlation_id)
            assert params == ("default", "test_correlation_id")


def test_get_task_by_correlation_id_sqlite_specific():
    """Test SQLite-specific JSON extraction in SQL query."""
    mock_adapter = Mock()
    mock_adapter.placeholder.return_value = "?"
    mock_adapter.json_extract.return_value = "json_extract(context_json, '$.correlation_id')"

    with patch("ciris_engine.logic.persistence.db.dialect.get_adapter", return_value=mock_adapter):
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            get_task_by_correlation_id("test_id", "default", "/tmp/test.db")

            sql = mock_cursor.execute.call_args[0][0]

            # Verify SQLite-specific syntax
            assert "json_extract(context_json, '$.correlation_id')" in sql
            assert "?" in sql  # SQLite placeholder


def test_get_task_by_correlation_id_postgres_specific():
    """Test PostgreSQL-specific JSON extraction in SQL query."""
    mock_adapter = Mock()
    mock_adapter.placeholder.return_value = "%s"
    mock_adapter.json_extract.return_value = "(context_json->>'correlation_id')"

    with patch("ciris_engine.logic.persistence.db.dialect.get_adapter", return_value=mock_adapter):
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            get_task_by_correlation_id("test_id", "default", "/tmp/test.db")

            sql = mock_cursor.execute.call_args[0][0]

            # Verify PostgreSQL-specific syntax
            assert "(context_json->>'correlation_id')" in sql
            assert "%s" in sql  # PostgreSQL placeholder


def test_get_task_by_correlation_id_exception_handling():
    """Test that get_task_by_correlation_id handles database exceptions gracefully."""
    with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
        mock_conn.side_effect = Exception("Database connection failed")

        # Call should handle exception and return None
        result = get_task_by_correlation_id(correlation_id="test_id", occurrence_id="default", db_path="/tmp/test.db")

        assert result is None


def test_get_task_by_correlation_id_correct_parameter_order():
    """Test that parameters are passed in correct order to SQL query."""
    mock_adapter = Mock()
    mock_adapter.placeholder.return_value = "?"
    mock_adapter.json_extract.return_value = "json_extract(context_json, '$.correlation_id')"

    with patch("ciris_engine.logic.persistence.db.dialect.get_adapter", return_value=mock_adapter):
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            get_task_by_correlation_id(
                correlation_id="my_correlation_123", occurrence_id="occurrence_2", db_path="/tmp/test.db"
            )

            # Verify parameters are in correct order: (occurrence_id, correlation_id)
            params = mock_cursor.execute.call_args[0][1]
            assert params == ("occurrence_2", "my_correlation_123")


def test_get_task_by_correlation_id_sql_structure():
    """Test that generated SQL has correct structure with ORDER BY and LIMIT."""
    mock_adapter = Mock()
    mock_adapter.placeholder.return_value = "?"
    mock_adapter.json_extract.return_value = "json_extract(context_json, '$.correlation_id')"

    with patch("ciris_engine.logic.persistence.db.dialect.get_adapter", return_value=mock_adapter):
        with patch("ciris_engine.logic.persistence.models.tasks.get_db_connection") as mock_conn:
            mock_cursor = Mock()
            mock_cursor.fetchone.return_value = None
            mock_context = Mock()
            mock_context.__enter__ = Mock(return_value=mock_context)
            mock_context.__exit__ = Mock(return_value=False)
            mock_context.cursor.return_value = mock_cursor
            mock_conn.return_value = mock_context

            get_task_by_correlation_id("test_id", "default", "/tmp/test.db")

            sql = mock_cursor.execute.call_args[0][0]

            # Verify SQL structure
            assert "SELECT * FROM tasks" in sql
            assert "WHERE agent_occurrence_id" in sql
            assert "ORDER BY created_at DESC" in sql
            assert "LIMIT 1" in sql
