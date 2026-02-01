"""Unit tests for authentication_store helper functions."""

import sqlite3
import sys
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.persistence.stores.authentication_store import (
    _apply_column_migrations,
    _detect_ios_platform,
    _execute_table_creation,
    _get_existing_columns,
)


class TestDetectIOSPlatform:
    """Tests for _detect_ios_platform()."""

    def test_detect_ios_platform_on_ios(self):
        """Test detection on actual iOS platform."""
        with patch.object(sys, "platform", "ios"):
            assert _detect_ios_platform() is True

    def test_detect_ios_platform_on_darwin_with_iphoneos(self):
        """Test detection on darwin with iphoneos multiarch."""
        mock_impl = MagicMock()
        mock_impl._multiarch = "arm64-apple-iphoneos"

        with patch.object(sys, "platform", "darwin"):
            with patch.object(sys, "implementation", mock_impl, create=True):
                assert _detect_ios_platform() is True

    def test_detect_ios_platform_on_darwin_without_iphoneos(self):
        """Test detection on macOS (not iOS)."""
        mock_impl = MagicMock()
        mock_impl._multiarch = "x86_64-apple-macosx"

        with patch.object(sys, "platform", "darwin"):
            with patch.object(sys, "implementation", mock_impl, create=True):
                assert _detect_ios_platform() is False

    def test_detect_ios_platform_on_linux(self):
        """Test detection on Linux platform."""
        with patch.object(sys, "platform", "linux"):
            assert _detect_ios_platform() is False

    def test_detect_ios_platform_on_windows(self):
        """Test detection on Windows platform."""
        with patch.object(sys, "platform", "win32"):
            assert _detect_ios_platform() is False

    def test_detect_ios_platform_darwin_no_multiarch(self):
        """Test detection on darwin without _multiarch attribute."""
        mock_impl = MagicMock(spec=[])  # No _multiarch attribute

        with patch.object(sys, "platform", "darwin"):
            with patch.object(sys, "implementation", mock_impl, create=True):
                assert _detect_ios_platform() is False


class TestExecuteTableCreation:
    """Tests for _execute_table_creation()."""

    def test_execute_table_creation_sqlite(self, tmp_path):
        """Test table creation on SQLite."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        table_sql = """
        CREATE TABLE IF NOT EXISTS test_table (
            id INTEGER PRIMARY KEY,
            name TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_test_name ON test_table(name);
        """

        _execute_table_creation(conn, table_sql, is_postgres=False, is_ios=False)
        conn.commit()

        # Verify table was created
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'")
        result = cursor.fetchone()
        assert result is not None
        cursor.close()
        conn.close()

    def test_execute_table_creation_ios_sqlite(self, tmp_path):
        """Test table creation on iOS SQLite (individual statements)."""
        db_path = tmp_path / "test_ios.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        table_sql = """
        CREATE TABLE IF NOT EXISTS ios_table (
            id INTEGER PRIMARY KEY,
            value TEXT
        );
        """

        _execute_table_creation(conn, table_sql, is_postgres=False, is_ios=True)
        conn.commit()

        # Verify table was created
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ios_table'")
        result = cursor.fetchone()
        assert result is not None
        cursor.close()
        conn.close()

    def test_execute_table_creation_postgres(self):
        """Test table creation on PostgreSQL (mocked)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        table_sql = """
        CREATE TABLE IF NOT EXISTS pg_table (
            id SERIAL PRIMARY KEY
        );
        CREATE INDEX IF NOT EXISTS idx_pg ON pg_table(id);
        """

        _execute_table_creation(mock_conn, table_sql, is_postgres=True, is_ios=False)

        # Should have executed individual statements
        assert mock_cursor.execute.call_count == 2
        mock_cursor.close.assert_called_once()


class TestGetExistingColumns:
    """Tests for _get_existing_columns()."""

    def test_get_existing_columns_sqlite(self, tmp_path):
        """Test getting existing columns from SQLite."""
        db_path = tmp_path / "test_cols.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create a table with specific columns
        conn.execute(
            """
            CREATE TABLE wa_cert (
                wa_id TEXT PRIMARY KEY,
                name TEXT,
                role TEXT,
                pubkey TEXT
            )
        """
        )
        conn.commit()

        columns = _get_existing_columns(conn, is_postgres=False)

        assert "wa_id" in columns
        assert "name" in columns
        assert "role" in columns
        assert "pubkey" in columns
        assert len(columns) == 4
        conn.close()

    def test_get_existing_columns_postgres(self):
        """Test getting existing columns from PostgreSQL (mocked)."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Mock PostgreSQL information_schema response
        mock_cursor.fetchall.return_value = [
            {"column_name": "wa_id"},
            {"column_name": "name"},
            {"column_name": "role"},
        ]

        columns = _get_existing_columns(mock_conn, is_postgres=True)

        assert "wa_id" in columns
        assert "name" in columns
        assert "role" in columns
        mock_cursor.close.assert_called_once()

    def test_get_existing_columns_postgres_tuple_rows(self):
        """Test getting columns from PostgreSQL with tuple rows."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor

        # Mock PostgreSQL returning tuples instead of dicts
        mock_cursor.fetchall.return_value = [
            ("wa_id",),
            ("name",),
            ("role",),
        ]

        columns = _get_existing_columns(mock_conn, is_postgres=True)

        assert "wa_id" in columns
        assert "name" in columns
        assert "role" in columns


class TestApplyColumnMigrations:
    """Tests for _apply_column_migrations()."""

    def test_apply_column_migrations_adds_missing(self, tmp_path):
        """Test adding missing columns."""
        db_path = tmp_path / "test_migrate.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create table without optional columns
        conn.execute(
            """
            CREATE TABLE wa_cert (
                wa_id TEXT PRIMARY KEY,
                name TEXT
            )
        """
        )
        conn.commit()

        # Apply migrations - should add missing columns
        existing_columns = {"wa_id", "name"}
        _apply_column_migrations(conn, existing_columns)
        conn.commit()

        # Verify columns were added
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(wa_cert)")
        new_columns = {row[1] for row in cursor.fetchall()}
        cursor.close()

        assert "custom_permissions_json" in new_columns
        assert "adapter_name" in new_columns
        assert "adapter_metadata_json" in new_columns
        assert "oauth_links_json" in new_columns
        conn.close()

    def test_apply_column_migrations_skips_existing(self, tmp_path):
        """Test that existing columns are not re-added."""
        db_path = tmp_path / "test_skip.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create table with all columns already present
        conn.execute(
            """
            CREATE TABLE wa_cert (
                wa_id TEXT PRIMARY KEY,
                name TEXT,
                custom_permissions_json TEXT,
                adapter_name TEXT,
                adapter_metadata_json TEXT,
                oauth_links_json TEXT
            )
        """
        )
        conn.commit()

        # All columns exist - should not execute any ALTER TABLE
        existing_columns = {
            "wa_id",
            "name",
            "custom_permissions_json",
            "adapter_name",
            "adapter_metadata_json",
            "oauth_links_json",
        }

        # This should not raise any errors
        _apply_column_migrations(conn, existing_columns)
        conn.commit()
        conn.close()

    def test_apply_column_migrations_partial(self, tmp_path):
        """Test adding only some missing columns."""
        db_path = tmp_path / "test_partial.db"
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row

        # Create table with some optional columns
        conn.execute(
            """
            CREATE TABLE wa_cert (
                wa_id TEXT PRIMARY KEY,
                custom_permissions_json TEXT
            )
        """
        )
        conn.commit()

        # Only custom_permissions_json exists
        existing_columns = {"wa_id", "custom_permissions_json"}
        _apply_column_migrations(conn, existing_columns)
        conn.commit()

        # Verify only missing columns were added
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(wa_cert)")
        new_columns = {row[1] for row in cursor.fetchall()}
        cursor.close()

        assert "adapter_name" in new_columns
        assert "adapter_metadata_json" in new_columns
        assert "oauth_links_json" in new_columns
        conn.close()
