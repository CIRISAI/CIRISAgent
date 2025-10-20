"""Unit tests for database execution helpers."""

import sqlite3
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, call, patch

import pytest

from ciris_engine.logic.persistence.db.execution_helpers import (
    execute_sql_statements,
    get_applied_migrations,
    get_pending_migrations,
    mask_password_in_url,
    record_migration,
    split_sql_statements,
)


class TestExecuteSQLStatements:
    """Tests for execute_sql_statements()."""

    def test_execute_statements_postgresql(self):
        """Test PostgreSQL execution uses cursor.execute() for each statement."""
        # Setup
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_adapter = MagicMock()
        mock_adapter.is_postgresql.return_value = True

        statements = ["CREATE TABLE test1", "CREATE TABLE test2"]

        # Execute
        execute_sql_statements(mock_conn, statements, mock_adapter)

        # Verify
        assert mock_cursor.execute.call_count == 2
        mock_cursor.execute.assert_any_call("CREATE TABLE test1")
        mock_cursor.execute.assert_any_call("CREATE TABLE test2")
        mock_cursor.close.assert_called_once()

    def test_execute_statements_sqlite(self):
        """Test SQLite execution uses executescript()."""
        # Setup
        mock_conn = MagicMock()
        mock_adapter = MagicMock()
        mock_adapter.is_postgresql.return_value = False

        statements = ["CREATE TABLE test1", "CREATE TABLE test2"]

        # Execute
        execute_sql_statements(mock_conn, statements, mock_adapter)

        # Verify
        mock_conn.executescript.assert_called_once()
        executed_sql = mock_conn.executescript.call_args[0][0]
        assert "CREATE TABLE test1" in executed_sql
        assert "CREATE TABLE test2" in executed_sql

    def test_execute_statements_empty_filtered(self):
        """Test empty statements are filtered out."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_adapter = MagicMock()
        mock_adapter.is_postgresql.return_value = True

        statements = ["CREATE TABLE test", "", "  ", "INSERT INTO test VALUES (1)"]

        execute_sql_statements(mock_conn, statements, mock_adapter)

        # Should only execute 2 non-empty statements
        assert mock_cursor.execute.call_count == 2
        mock_cursor.execute.assert_any_call("CREATE TABLE test")
        mock_cursor.execute.assert_any_call("INSERT INTO test VALUES (1)")

    def test_execute_statements_cursor_closed_on_error(self):
        """Test cursor is closed even if execution fails."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.execute.side_effect = Exception("SQL error")
        mock_conn.cursor.return_value = mock_cursor
        mock_adapter = MagicMock()
        mock_adapter.is_postgresql.return_value = True

        statements = ["BAD SQL"]

        with pytest.raises(Exception, match="SQL error"):
            execute_sql_statements(mock_conn, statements, mock_adapter)

        # Cursor should still be closed
        mock_cursor.close.assert_called_once()


class TestSplitSQLStatements:
    """Tests for split_sql_statements()."""

    def test_split_simple_statements(self):
        """Test splitting simple semicolon-separated statements."""
        sql = "CREATE TABLE t1; CREATE TABLE t2; INSERT INTO t1 VALUES (1);"
        result = split_sql_statements(sql)

        assert len(result) == 3
        assert result[0] == "CREATE TABLE t1"
        assert result[1] == "CREATE TABLE t2"
        assert result[2] == "INSERT INTO t1 VALUES (1)"

    def test_split_with_whitespace(self):
        """Test splitting handles leading/trailing whitespace."""
        sql = "  CREATE TABLE t1  ;   CREATE TABLE t2  ;  "
        result = split_sql_statements(sql)

        assert len(result) == 2
        assert result[0] == "CREATE TABLE t1"
        assert result[1] == "CREATE TABLE t2"

    def test_split_empty_statements_filtered(self):
        """Test empty statements are filtered out."""
        sql = "CREATE TABLE t1;; ; ;;CREATE TABLE t2;"
        result = split_sql_statements(sql)

        assert len(result) == 2
        assert result[0] == "CREATE TABLE t1"
        assert result[1] == "CREATE TABLE t2"

    def test_split_single_statement(self):
        """Test single statement without semicolon."""
        sql = "CREATE TABLE test"
        result = split_sql_statements(sql)

        assert len(result) == 1
        assert result[0] == "CREATE TABLE test"

    def test_split_multiline_statement(self):
        """Test multiline SQL statement."""
        sql = """
            CREATE TABLE test (
                id INTEGER PRIMARY KEY,
                name TEXT
            );
            INSERT INTO test VALUES (1, 'test');
        """
        result = split_sql_statements(sql)

        assert len(result) == 2
        assert "CREATE TABLE test" in result[0]
        assert "INSERT INTO test" in result[1]

    def test_split_postgresql_dollar_quoted_block(self):
        """Test PostgreSQL DO $$ ... END $$; blocks are not split internally."""
        sql = """
            ALTER TABLE tasks ADD COLUMN test TEXT;

            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'scheduled_tasks') THEN
                    ALTER TABLE scheduled_tasks ADD COLUMN test TEXT;
                END IF;
            END $$;

            CREATE INDEX idx_test ON tasks(test);
        """
        result = split_sql_statements(sql)

        # Should be 3 statements: ALTER TABLE, DO block, CREATE INDEX
        assert len(result) == 3
        assert "ALTER TABLE tasks" in result[0]
        assert "DO $$" in result[1]
        assert "END $$;" in result[1]
        assert "CREATE INDEX" in result[2]
        # Verify DO block is intact with internal semicolons
        assert "END IF;" in result[1]

    def test_split_postgresql_multiple_dollar_blocks(self):
        """Test multiple PostgreSQL DO $$ blocks in same migration."""
        sql = """
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'table1') THEN
                    ALTER TABLE table1 ADD COLUMN col1 TEXT;
                END IF;
            END $$;

            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'table2') THEN
                    ALTER TABLE table2 ADD COLUMN col2 TEXT;
                END IF;
            END $$;
        """
        result = split_sql_statements(sql)

        # Should be 2 separate DO blocks
        assert len(result) == 2
        assert "table1" in result[0]
        assert "table2" in result[1]
        assert "END IF;" in result[0]
        assert "END IF;" in result[1]

    def test_split_postgresql_tagged_dollar_quotes(self):
        """Test PostgreSQL tagged dollar quotes ($func$, $BODY$, etc.)."""
        sql = """
            CREATE FUNCTION test_func() RETURNS void AS $func$
            BEGIN
                INSERT INTO test VALUES (1);
                UPDATE test SET value = 2;
            END;
            $func$ LANGUAGE plpgsql;

            CREATE FUNCTION another_func() RETURNS void AS $BODY$
            DECLARE
                v_count INTEGER;
            BEGIN
                SELECT COUNT(*) INTO v_count FROM users;
            END;
            $BODY$ LANGUAGE plpgsql;
        """
        result = split_sql_statements(sql)

        # Should be 2 separate function definitions
        assert len(result) == 2
        assert "test_func" in result[0]
        assert "$func$" in result[0]
        assert "INSERT INTO test" in result[0]
        assert "UPDATE test" in result[0]
        assert "another_func" in result[1]
        assert "$BODY$" in result[1]
        assert "v_count" in result[1]

    def test_split_postgresql_mixed_dollar_quotes(self):
        """Test mixing simple $$ and tagged $identifier$ quotes."""
        sql = """
            DO $$
            BEGIN
                EXECUTE 'SELECT 1;';
            END $$;

            CREATE FUNCTION get_count() RETURNS INTEGER AS $body$
            BEGIN
                RETURN (SELECT COUNT(*) FROM items);
            END;
            $body$ LANGUAGE plpgsql;

            ALTER TABLE items ADD COLUMN status TEXT;
        """
        result = split_sql_statements(sql)

        # Should be 3 statements: DO block, function, ALTER TABLE
        assert len(result) == 3
        assert "DO $$" in result[0]
        assert "EXECUTE" in result[0]
        assert "CREATE FUNCTION" in result[1]
        assert "$body$" in result[1]
        assert "ALTER TABLE" in result[2]

    def test_split_postgresql_nested_semicolons_in_tagged_quotes(self):
        """Test that semicolons inside tagged dollar quotes are preserved."""
        sql = """
            CREATE FUNCTION complex_func() RETURNS void AS $function$
            DECLARE
                rec RECORD;
            BEGIN
                FOR rec IN SELECT * FROM users LOOP
                    INSERT INTO log (user_id) VALUES (rec.id);
                    UPDATE stats SET count = count + 1;
                END LOOP;
            END;
            $function$ LANGUAGE plpgsql;
        """
        result = split_sql_statements(sql)

        # Should be 1 statement with all internal semicolons preserved
        assert len(result) == 1
        assert "INSERT INTO log" in result[0]
        assert "UPDATE stats" in result[0]
        assert "END LOOP;" in result[0]
        assert "$function$" in result[0]


class TestMaskPasswordInURL:
    """Tests for mask_password_in_url()."""

    def test_mask_postgresql_url(self):
        """Test masking password in PostgreSQL URL."""
        url = "postgresql://user:secret123@localhost:5432/db"
        masked = mask_password_in_url(url)

        assert masked == "postgresql://user:****@localhost:5432/db"
        assert "secret123" not in masked

    def test_mask_mysql_url(self):
        """Test masking password in MySQL URL."""
        url = "mysql://admin:p@ssw0rd@db.example.com:3306/mydb"
        masked = mask_password_in_url(url)

        assert masked == "mysql://admin:****@db.example.com:3306/mydb"
        assert "p@ssw0rd" not in masked

    def test_mask_complex_password(self):
        """Test masking complex password with special characters."""
        url = "postgresql://user:p@ss!w#rd$123@host/db"
        masked = mask_password_in_url(url)

        assert masked == "postgresql://user:****@host/db"
        assert "p@ss!w#rd$123" not in masked

    def test_no_mask_sqlite_url(self):
        """Test SQLite URL is returned unchanged."""
        url = "sqlite:///path/to/database.db"
        masked = mask_password_in_url(url)

        assert masked == url

    def test_no_mask_no_password(self):
        """Test URL without password returns unchanged."""
        url = "postgresql://localhost:5432/db"
        masked = mask_password_in_url(url)

        assert masked == url

    def test_no_mask_no_credentials(self):
        """Test URL without credentials returns unchanged."""
        url = "postgresql://localhost/db"
        masked = mask_password_in_url(url)

        assert masked == url


class TestGetAppliedMigrations:
    """Tests for get_applied_migrations()."""

    def test_get_applied_migrations_success(self):
        """Test retrieving applied migrations."""
        # Setup
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            {"migration_name": "001_initial.sql"},
            {"migration_name": "002_add_users.sql"},
            {"migration_name": "003_add_indexes.sql"},
        ]

        # Execute
        result = get_applied_migrations(mock_conn)

        # Verify
        assert result == {"001_initial.sql", "002_add_users.sql", "003_add_indexes.sql"}
        mock_cursor.execute.assert_called_once_with("SELECT migration_name FROM migrations")

    def test_get_applied_migrations_empty(self):
        """Test when no migrations have been applied."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        result = get_applied_migrations(mock_conn)

        assert result == set()


class TestGetPendingMigrations:
    """Tests for get_pending_migrations()."""

    def test_get_pending_migrations(self, tmp_path):
        """Test retrieving pending migration files."""
        # Create test migration files
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        (migrations_dir / "001_initial.sql").write_text("CREATE TABLE test;")
        (migrations_dir / "002_add_users.sql").write_text("CREATE TABLE users;")
        (migrations_dir / "003_add_indexes.sql").write_text("CREATE INDEX test_idx ON test(id);")

        applied_migrations = {"001_initial.sql"}

        # Execute
        result = get_pending_migrations(migrations_dir, applied_migrations)

        # Verify
        assert len(result) == 2
        assert result[0].name == "002_add_users.sql"
        assert result[1].name == "003_add_indexes.sql"

    def test_get_pending_migrations_all_applied(self, tmp_path):
        """Test when all migrations are already applied."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        (migrations_dir / "001_initial.sql").write_text("CREATE TABLE test;")
        (migrations_dir / "002_add_users.sql").write_text("CREATE TABLE users;")

        applied_migrations = {"001_initial.sql", "002_add_users.sql"}

        result = get_pending_migrations(migrations_dir, applied_migrations)

        assert len(result) == 0

    def test_get_pending_migrations_none_applied(self, tmp_path):
        """Test when no migrations have been applied."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        (migrations_dir / "001_initial.sql").write_text("CREATE TABLE test;")
        (migrations_dir / "002_add_users.sql").write_text("CREATE TABLE users;")

        applied_migrations = set()

        result = get_pending_migrations(migrations_dir, applied_migrations)

        assert len(result) == 2

    def test_get_pending_migrations_sorted(self, tmp_path):
        """Test migrations are returned in sorted order."""
        migrations_dir = tmp_path / "migrations"
        migrations_dir.mkdir()

        # Create out of order
        (migrations_dir / "003_add_indexes.sql").write_text("CREATE INDEX;")
        (migrations_dir / "001_initial.sql").write_text("CREATE TABLE;")
        (migrations_dir / "002_add_users.sql").write_text("CREATE TABLE users;")

        result = get_pending_migrations(migrations_dir, set())

        assert result[0].name == "001_initial.sql"
        assert result[1].name == "002_add_users.sql"
        assert result[2].name == "003_add_indexes.sql"


class TestHelperFunctions:
    """Tests for internal helper functions."""

    def test_update_dollar_quote_state_opening(self):
        """Test opening a dollar-quoted block."""
        from ciris_engine.logic.persistence.db.execution_helpers import _update_dollar_quote_state

        in_quote, tag = _update_dollar_quote_state("$$", False, None)
        assert in_quote is True
        assert tag == "$$"

    def test_update_dollar_quote_state_closing(self):
        """Test closing a dollar-quoted block."""
        from ciris_engine.logic.persistence.db.execution_helpers import _update_dollar_quote_state

        in_quote, tag = _update_dollar_quote_state("$$", True, "$$")
        assert in_quote is False
        assert tag is None

    def test_update_dollar_quote_state_mismatched_tag(self):
        """Test encountering different tag while in dollar-quoted block."""
        from ciris_engine.logic.persistence.db.execution_helpers import _update_dollar_quote_state

        in_quote, tag = _update_dollar_quote_state("$func$", True, "$$")
        assert in_quote is True
        assert tag == "$$"

    def test_should_finalize_statement_with_semicolon(self):
        """Test should finalize when semicolon at end and not in dollar quote."""
        from ciris_engine.logic.persistence.db.execution_helpers import _should_finalize_statement

        assert _should_finalize_statement("CREATE TABLE test;", False) is True

    def test_should_finalize_statement_in_dollar_quote(self):
        """Test should not finalize when in dollar quote."""
        from ciris_engine.logic.persistence.db.execution_helpers import _should_finalize_statement

        assert _should_finalize_statement("INSERT INTO test;", True) is False

    def test_should_finalize_statement_no_semicolon_at_end(self):
        """Test should not finalize when semicolon not at end."""
        from ciris_engine.logic.persistence.db.execution_helpers import _should_finalize_statement

        assert _should_finalize_statement("SELECT * FROM test; WHERE id = 1", False) is False

    def test_finalize_statement_with_content(self):
        """Test finalizing statement with content."""
        from ciris_engine.logic.persistence.db.execution_helpers import _finalize_statement

        result = _finalize_statement(["  CREATE TABLE test  ", "  (id INTEGER)  "])
        # Note: _finalize_statement joins with \n and strips outer whitespace only
        assert result == "CREATE TABLE test  \n  (id INTEGER)"

    def test_finalize_statement_empty(self):
        """Test finalizing empty statement."""
        from ciris_engine.logic.persistence.db.execution_helpers import _finalize_statement

        result = _finalize_statement(["  ", ""])
        assert result is None


class TestRecordMigration:
    """Tests for record_migration()."""

    def test_record_migration_postgresql(self):
        """Test recording migration with PostgreSQL adapter."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_adapter = MagicMock()
        mock_adapter.is_postgresql.return_value = True

        with patch("ciris_engine.logic.persistence.db.execution_helpers.datetime") as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2025-01-01T12:00:00"
            record_migration(mock_conn, "001_initial.sql", mock_adapter)

        # Verify PostgreSQL placeholder (%s) used
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "%s" in call_args[0][0]
        assert call_args[0][1] == ("001_initial.sql", "2025-01-01T12:00:00")

    def test_record_migration_sqlite(self):
        """Test recording migration with SQLite adapter."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_adapter = MagicMock()
        mock_adapter.is_postgresql.return_value = False

        with patch("ciris_engine.logic.persistence.db.execution_helpers.datetime") as mock_datetime:
            mock_datetime.now.return_value.isoformat.return_value = "2025-01-01T12:00:00"
            record_migration(mock_conn, "001_initial.sql", mock_adapter)

        # Verify SQLite placeholder (?) used
        mock_cursor.execute.assert_called_once()
        call_args = mock_cursor.execute.call_args
        assert "?" in call_args[0][0]
        assert call_args[0][1] == ("001_initial.sql", "2025-01-01T12:00:00")

    def test_record_migration_inserts_correct_data(self):
        """Test migration record contains correct data."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_adapter = MagicMock()
        mock_adapter.is_postgresql.return_value = False

        record_migration(mock_conn, "002_add_users.sql", mock_adapter)

        call_args = mock_cursor.execute.call_args
        assert "002_add_users.sql" in call_args[0][1]
        # Verify timestamp is ISO format
        timestamp = call_args[0][1][1]
        assert "T" in timestamp  # ISO format contains 'T' separator
