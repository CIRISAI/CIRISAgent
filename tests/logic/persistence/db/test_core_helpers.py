"""Unit tests for database core helper functions."""

import sqlite3
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.persistence.db.core import (
    _create_sqlite_connection_ios,
    _execute_pragmas,
    _get_pragma_statements,
    _resolve_db_path,
)


class TestResolveDbPath:
    """Tests for _resolve_db_path()."""

    def test_resolve_db_path_explicit(self, tmp_path):
        """Test resolving explicit db_path."""
        db_file = tmp_path / "explicit.db"
        result = _resolve_db_path(str(db_file))
        assert result == str(db_file)

    def test_resolve_db_path_postgres_url(self):
        """Test resolving PostgreSQL URL."""
        postgres_url = "postgresql://user:pass@localhost:5432/dbname"
        result = _resolve_db_path(postgres_url)
        assert result == postgres_url

    def test_resolve_db_path_from_test_override(self, tmp_path):
        """Test resolving from test override path."""
        db_file = tmp_path / "test_override.db"

        with patch("ciris_engine.logic.persistence.db.core._test_db_path", str(db_file)):
            result = _resolve_db_path(None)
            assert result == str(db_file)

    def test_resolve_db_path_default(self):
        """Test resolving to default path when no override."""
        with patch("ciris_engine.logic.persistence.db.core._test_db_path", None):
            with patch(
                "ciris_engine.logic.persistence.db.core.get_sqlite_db_full_path"
            ) as mock_get_path:
                mock_get_path.return_value = "/mock/data/ciris_engine.db"
                result = _resolve_db_path(None)
                assert result == "/mock/data/ciris_engine.db"


class TestGetPragmaStatements:
    """Tests for _get_pragma_statements()."""

    def test_get_pragma_statements_desktop(self):
        """Test desktop pragma statements."""
        pragmas = _get_pragma_statements(is_ios=False, busy_timeout=None)

        assert "PRAGMA foreign_keys = ON;" in pragmas
        assert "PRAGMA journal_mode=WAL;" in pragmas
        assert "PRAGMA busy_timeout = 5000;" in pragmas
        assert len(pragmas) == 3

    def test_get_pragma_statements_ios(self):
        """Test iOS pragma statements."""
        pragmas = _get_pragma_statements(is_ios=True, busy_timeout=None)

        assert "PRAGMA foreign_keys = ON;" in pragmas
        assert "PRAGMA journal_mode=WAL;" in pragmas
        assert "PRAGMA busy_timeout = 30000;" in pragmas
        assert "PRAGMA synchronous=NORMAL;" in pragmas
        assert len(pragmas) == 4

    def test_get_pragma_statements_custom_timeout(self):
        """Test pragma statements with custom busy_timeout."""
        pragmas = _get_pragma_statements(is_ios=False, busy_timeout=10000)
        assert "PRAGMA busy_timeout = 10000;" in pragmas

    def test_get_pragma_statements_ios_custom_timeout(self):
        """Test iOS pragma statements with custom busy_timeout."""
        pragmas = _get_pragma_statements(is_ios=True, busy_timeout=60000)
        assert "PRAGMA busy_timeout = 60000;" in pragmas

    def test_get_pragma_statements_returns_list(self):
        """Test that pragmas are returned as a list."""
        pragmas = _get_pragma_statements(is_ios=False, busy_timeout=None)
        assert isinstance(pragmas, list)
        assert all(isinstance(p, str) for p in pragmas)


class TestExecutePragmas:
    """Tests for _execute_pragmas()."""

    def test_execute_pragmas_calls_adapter_pragma(self):
        """Test that _execute_pragmas calls adapter.pragma for each statement."""
        mock_conn = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.pragma.side_effect = lambda p: p  # Return pragma unchanged

        pragmas = ["PRAGMA foreign_keys = ON;", "PRAGMA journal_mode=WAL;"]

        _execute_pragmas(mock_conn, mock_adapter, pragmas)

        assert mock_adapter.pragma.call_count == 2
        assert mock_conn.execute.call_count == 2

    def test_execute_pragmas_skips_none_results(self):
        """Test that _execute_pragmas skips None pragma results."""
        mock_conn = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.pragma.side_effect = [None, "PRAGMA journal_mode=WAL;", None]

        pragmas = ["PRAGMA a;", "PRAGMA journal_mode=WAL;", "PRAGMA b;"]

        _execute_pragmas(mock_conn, mock_adapter, pragmas)

        assert mock_adapter.pragma.call_count == 3
        assert mock_conn.execute.call_count == 1

    def test_execute_pragmas_raises_on_error(self):
        """Test that _execute_pragmas raises on execute error."""
        mock_conn = MagicMock()
        mock_conn.execute.side_effect = Exception("Execute failed")
        mock_adapter = MagicMock()
        mock_adapter.pragma.return_value = "PRAGMA journal_mode=WAL;"

        with pytest.raises(Exception, match="Execute failed"):
            _execute_pragmas(mock_conn, mock_adapter, ["PRAGMA journal_mode=WAL;"])


class TestCreateSQLiteConnectionIOS:
    """Tests for _create_sqlite_connection_ios()."""

    def test_create_sqlite_connection_ios_new_db(self, tmp_path):
        """Test creating iOS SQLite connection for new database."""
        db_path = tmp_path / "new_ios.db"

        conn = _create_sqlite_connection_ios(str(db_path))

        assert conn is not None
        # Verify it's a valid connection
        cursor = conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result[0] == 1
        cursor.close()
        conn.close()

    def test_create_sqlite_connection_ios_existing_db(self, tmp_path):
        """Test creating iOS SQLite connection for existing database."""
        db_path = tmp_path / "existing_ios.db"

        # Create initial database with some data
        init_conn = sqlite3.connect(str(db_path))
        init_conn.execute("CREATE TABLE test (id INTEGER)")
        init_conn.execute("INSERT INTO test VALUES (42)")
        init_conn.commit()
        init_conn.close()

        # Open with iOS connection
        conn = _create_sqlite_connection_ios(str(db_path))

        cursor = conn.cursor()
        cursor.execute("SELECT id FROM test")
        result = cursor.fetchone()
        assert result[0] == 42
        cursor.close()
        conn.close()

    def test_create_sqlite_connection_ios_autocommit_mode(self, tmp_path):
        """Test iOS connection is in autocommit mode."""
        db_path = tmp_path / "autocommit_ios.db"

        conn = _create_sqlite_connection_ios(str(db_path))

        # isolation_level=None means autocommit mode
        assert conn.isolation_level is None
        conn.close()

    def test_create_sqlite_connection_ios_check_same_thread_false(self, tmp_path):
        """Test iOS connection allows multi-thread access."""
        db_path = tmp_path / "thread_ios.db"

        conn = _create_sqlite_connection_ios(str(db_path))

        # Should be able to use from any thread without error
        conn.execute("SELECT 1")
        conn.close()

    def test_create_sqlite_connection_ios_raises_on_invalid_path(self, tmp_path):
        """Test iOS connection raises on invalid path."""
        # Non-existent nested directory
        db_path = tmp_path / "nonexistent" / "subdir" / "ios.db"

        with pytest.raises(sqlite3.OperationalError):
            _create_sqlite_connection_ios(str(db_path))
