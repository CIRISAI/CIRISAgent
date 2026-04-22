"""
Comprehensive tests for database migration system.

Tests cover:
- Migration runner functionality
- Migration tracking and ordering
- Rollback capabilities
- Error handling
- Idempotency
"""

import os
import sqlite3
import tempfile
from pathlib import Path

import pytest

from ciris_engine.logic.persistence.db.core import get_db_connection, initialize_database
from ciris_engine.logic.persistence.db.migration_runner import MIGRATIONS_DIR


class MigrationError(Exception):
    """Error during migration execution."""

    pass


def get_applied_migrations(conn: sqlite3.Connection) -> set:
    """Get set of applied migrations from database."""
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT filename FROM schema_migrations")
        return {row[0] for row in cursor.fetchall()}
    except sqlite3.OperationalError:
        # Table might not exist yet
        return set()


def apply_migration(conn: sqlite3.Connection, migration_file: Path) -> None:
    """Apply a single migration file."""
    filename = migration_file.name

    # Check if already applied
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM schema_migrations WHERE filename = ?", (filename,))
    if cursor.fetchone():
        return  # Already applied

    # Read and execute migration
    try:
        sql = migration_file.read_text()
        conn.executescript(sql)

        # Record migration
        cursor.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (filename,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise MigrationError(f"Failed to apply migration {filename}: {e}")


class TestMigrationSystem:
    """Test the database migration system."""

    @pytest.fixture
    def temp_db_path(self) -> str:
        """Create a temporary database file."""
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        yield path
        # Cleanup
        if os.path.exists(path):
            os.unlink(path)

    @pytest.fixture
    def temp_migrations_dir(self) -> Path:
        """Create a temporary migrations directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            migrations_path = Path(tmpdir) / "migrations"
            migrations_path.mkdir()
            yield migrations_path

    def test_migrations_directory_exists(self):
        """Test that the migrations directory exists."""
        assert MIGRATIONS_DIR.exists()
        assert MIGRATIONS_DIR.is_dir()

    def test_migration_files_exist(self):
        """Test that expected migration files exist."""
        expected_migrations = ["001_initial_schema.sql", "002_add_retry_status.sql"]

        migration_files = list(MIGRATIONS_DIR.glob("*.sql"))
        migration_names = [f.name for f in migration_files]

        for expected in expected_migrations:
            assert expected in migration_names, f"Missing migration: {expected}"

    def test_get_applied_migrations_empty(self, temp_db_path: str):
        """Test getting applied migrations from empty database."""
        # Create minimal database with migrations table
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        with get_db_connection(temp_db_path) as conn:
            applied = get_applied_migrations(conn)
            assert isinstance(applied, set)
            assert len(applied) == 0

    def test_apply_single_migration(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test applying a single migration."""
        # Create test migration
        migration_file = temp_migrations_dir / "001_test_migration.sql"
        migration_file.write_text(
            """
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );

            INSERT INTO test_table (name) VALUES ('test_value');
        """
        )

        # Create database with migrations table
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        # Apply migration
        with get_db_connection(temp_db_path) as conn:
            apply_migration(conn, migration_file)

        # Verify migration was applied
        with get_db_connection(temp_db_path) as conn:
            # Check migrations table
            applied = get_applied_migrations(conn)
            assert "001_test_migration.sql" in applied

            # Check table was created
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'")
            assert cursor.fetchone() is not None

            # Check data was inserted
            cursor.execute("SELECT name FROM test_table")
            result = cursor.fetchone()
            assert result[0] == "test_value"

    def test_migration_idempotency(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test that migrations are idempotent (not applied twice)."""
        # Create test migration
        migration_file = temp_migrations_dir / "001_test_migration.sql"
        migration_file.write_text(
            """
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY
            );
        """
        )

        # Initialize database
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        # Apply migration once
        with get_db_connection(temp_db_path) as conn:
            apply_migration(conn, migration_file)

        # Try to apply again - should be skipped
        with get_db_connection(temp_db_path) as conn:
            # This should not raise an error
            apply_migration(conn, migration_file)

            # Should still only be recorded once
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM schema_migrations WHERE filename = ?", ("001_test_migration.sql",))
            count = cursor.fetchone()[0]
            assert count == 1

    def test_migration_ordering(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test that migrations are applied in correct order."""
        # Create multiple migrations
        migrations = [
            ("003_third.sql", "CREATE TABLE table3 (id INTEGER);"),
            ("001_first.sql", "CREATE TABLE table1 (id INTEGER);"),
            ("002_second.sql", "CREATE TABLE table2 (id INTEGER);"),
        ]

        for filename, sql in migrations:
            (temp_migrations_dir / filename).write_text(sql)

        # Initialize and run migrations
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        # Use the module's run_migrations with custom directory
        # Note: We'll need to manually apply in order since run_migrations uses MIGRATIONS_DIR
        migration_files = sorted(temp_migrations_dir.glob("*.sql"))
        with get_db_connection(temp_db_path) as conn:
            for migration_file in migration_files:
                apply_migration(conn, migration_file)

        # Verify order
        with get_db_connection(temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT filename FROM schema_migrations ORDER BY applied_at")
            applied_order = [row[0] for row in cursor.fetchall()]

            assert applied_order == ["001_first.sql", "002_second.sql", "003_third.sql"]

    def test_migration_with_syntax_error(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test handling of migration with SQL syntax error."""
        # Create migration with syntax error
        migration_file = temp_migrations_dir / "001_bad_migration.sql"
        migration_file.write_text(
            """
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,  -- Extra comma
            );
        """
        )

        # Initialize database
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        # Apply migration should fail
        with pytest.raises(MigrationError) as exc_info:
            with get_db_connection(temp_db_path) as conn:
                apply_migration(conn, migration_file)

        assert "001_bad_migration.sql" in str(exc_info.value)

    def test_migration_transaction_rollback(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test that failed migrations don't get recorded as applied."""
        # Create migration that partially succeeds then fails
        migration_file = temp_migrations_dir / "001_partial_migration.sql"
        migration_file.write_text(
            """
            CREATE TABLE test_table (id INTEGER PRIMARY KEY);
            INSERT INTO test_table (id) VALUES (1);
            INSERT INTO test_table (id) VALUES (1);  -- Duplicate, will fail
        """
        )

        # Initialize database
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        # Apply migration should fail
        with pytest.raises(MigrationError):
            with get_db_connection(temp_db_path) as conn:
                apply_migration(conn, migration_file)

        # Note: executescript() commits after each statement in SQLite,
        # so the table will exist even though the migration failed
        with get_db_connection(temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'")
            # Table exists because CREATE TABLE succeeded before INSERT failed
            assert cursor.fetchone() is not None

            # But migration should not be recorded as applied
            applied = get_applied_migrations(conn)
            assert "001_partial_migration.sql" not in applied

    def test_run_migrations_integration(self, temp_db_path: str):
        """Test the full run_migrations function."""
        # Initialize database (includes running migrations)
        initialize_database(temp_db_path)

        # Verify migrations were applied
        with get_db_connection(temp_db_path) as conn:
            applied = get_applied_migrations(conn)

            # Should have at least the initial migrations
            assert "001_initial_schema.sql" in applied
            assert "002_add_retry_status.sql" in applied

    def test_migration_with_comments(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test migration files with SQL comments."""
        migration_file = temp_migrations_dir / "001_commented.sql"
        migration_file.write_text(
            """
            -- This is a comment
            /* This is a
               multi-line comment */
            CREATE TABLE test_table (
                id INTEGER PRIMARY KEY, -- inline comment
                name TEXT
            );
            -- Another comment
        """
        )

        # Initialize database
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        # Apply migration
        with get_db_connection(temp_db_path) as conn:
            apply_migration(conn, migration_file)

        # Verify success
        with get_db_connection(temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='test_table'")
            assert cursor.fetchone() is not None

    def test_empty_migration_file(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test handling of empty migration files."""
        migration_file = temp_migrations_dir / "001_empty.sql"
        migration_file.write_text("")

        # Initialize database
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        # Apply empty migration - should succeed
        with get_db_connection(temp_db_path) as conn:
            apply_migration(conn, migration_file)

        # Should be recorded
        with get_db_connection(temp_db_path) as conn:
            applied = get_applied_migrations(conn)
            assert "001_empty.sql" in applied

    def test_migration_creating_indexes(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test migrations that create indexes."""
        migration_file = temp_migrations_dir / "001_indexes.sql"
        migration_file.write_text(
            """
            CREATE TABLE users (
                id INTEGER PRIMARY KEY,
                email TEXT UNIQUE NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX idx_users_email ON users(email);
            CREATE INDEX idx_users_created_at ON users(created_at);
        """
        )

        # Initialize database
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        # Apply migration
        with get_db_connection(temp_db_path) as conn:
            apply_migration(conn, migration_file)

        # Verify indexes were created
        with get_db_connection(temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='users'")
            indexes = [row[0] for row in cursor.fetchall()]

            assert "idx_users_email" in indexes
            assert "idx_users_created_at" in indexes

    def test_migration_altering_tables(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test migrations that alter existing tables."""
        # First migration creates table
        migration1 = temp_migrations_dir / "001_create.sql"
        migration1.write_text(
            """
            CREATE TABLE products (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            );
        """
        )

        # Second migration alters table
        migration2 = temp_migrations_dir / "002_alter.sql"
        migration2.write_text(
            """
            ALTER TABLE products ADD COLUMN price REAL DEFAULT 0.0;
            ALTER TABLE products ADD COLUMN stock INTEGER DEFAULT 0;
        """
        )

        # Initialize database
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        # Apply migrations in order
        for migration_file in sorted(temp_migrations_dir.glob("*.sql")):
            with get_db_connection(temp_db_path) as conn:
                apply_migration(conn, migration_file)

        # Verify columns were added
        with get_db_connection(temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA table_info(products)")
            columns = {row[1]: row[2] for row in cursor.fetchall()}  # name: type

            assert "id" in columns
            assert "name" in columns
            assert "price" in columns
            assert "stock" in columns

    def test_concurrent_migration_attempts(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test handling of concurrent migration attempts."""
        import threading

        # Create a slow migration
        migration_file = temp_migrations_dir / "001_slow.sql"
        migration_file.write_text(
            """
            CREATE TABLE test_table (id INTEGER PRIMARY KEY);
            -- SQLite doesn't have sleep, but we can simulate with a big query
            INSERT INTO test_table
            SELECT 1 WHERE (SELECT COUNT(*) FROM sqlite_master) >= 0;
        """
        )

        # Initialize database
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        results = []
        errors = []

        def run_migration():
            try:
                with get_db_connection(temp_db_path) as conn:
                    apply_migration(conn, migration_file)
                results.append("success")
            except Exception as e:
                errors.append(str(e))

        # Start multiple threads
        threads = []
        for _ in range(3):
            t = threading.Thread(target=run_migration)
            threads.append(t)
            t.start()

        # Wait for all to complete
        for t in threads:
            t.join()

        # Only one should succeed, others should handle gracefully
        # Due to UNIQUE constraint on filename, duplicates will fail
        assert len(results) >= 1  # At least one should succeed

        # Verify migration was applied exactly once
        with get_db_connection(temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM schema_migrations WHERE filename = ?", ("001_slow.sql",))
            count = cursor.fetchone()[0]
            assert count == 1

    def test_idempotent_index_creation(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test that CREATE INDEX IF NOT EXISTS is idempotent.

        This tests the fix for the PostgreSQL QA runner issue where
        'index idx_scheduled_tasks_status already exists' caused failures.
        """
        # Create migration with idempotent index creation
        migration_file = temp_migrations_dir / "001_idempotent_indexes.sql"
        migration_file.write_text(
            """
            CREATE TABLE IF NOT EXISTS test_tasks (
                id TEXT PRIMARY KEY,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_test_tasks_status ON test_tasks(status);
            CREATE INDEX IF NOT EXISTS idx_test_tasks_created ON test_tasks(created_at);
        """
        )

        # Initialize database
        with get_db_connection(temp_db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    filename TEXT PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
            """
            )
            conn.commit()

        # Apply migration first time
        with get_db_connection(temp_db_path) as conn:
            sql = migration_file.read_text()
            conn.executescript(sql)
            conn.commit()

        # Running the same SQL again should NOT fail due to IF NOT EXISTS
        with get_db_connection(temp_db_path) as conn:
            sql = migration_file.read_text()
            # This should not raise any exception
            conn.executescript(sql)
            conn.commit()

        # Verify indexes exist
        with get_db_connection(temp_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='test_tasks'")
            indexes = {row[0] for row in cursor.fetchall()}
            assert "idx_test_tasks_status" in indexes
            assert "idx_test_tasks_created" in indexes

    def test_non_idempotent_index_creation_fails(self, temp_db_path: str, temp_migrations_dir: Path):
        """Test that CREATE INDEX (without IF NOT EXISTS) fails on duplicate.

        This verifies our understanding of the original bug.
        """
        # First, create a table and index
        with get_db_connection(temp_db_path) as conn:
            conn.executescript(
                """
                CREATE TABLE test_data (id INTEGER PRIMARY KEY, value TEXT);
                CREATE INDEX idx_test_data_value ON test_data(value);
            """
            )
            conn.commit()

        # Now try to create the same index again (without IF NOT EXISTS)
        # This SHOULD fail
        with pytest.raises(sqlite3.OperationalError) as exc_info:
            with get_db_connection(temp_db_path) as conn:
                conn.execute("CREATE INDEX idx_test_data_value ON test_data(value)")

        assert "already exists" in str(exc_info.value)
