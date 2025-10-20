import logging
import sqlite3
from pathlib import Path
from typing import Any, Union

logger = logging.getLogger(__name__)

MIGRATIONS_BASE_DIR = Path(__file__).resolve().parent.parent / "migrations"
# For backward compatibility with tests - points to SQLite migrations
MIGRATIONS_DIR = MIGRATIONS_BASE_DIR / "sqlite"


def _ensure_tracking_table(conn: Union[sqlite3.Connection, Any]) -> None:
    """Create schema_migrations tracking table if it doesn't exist.

    Works with both SQLite and PostgreSQL connections.
    """
    from .dialect import get_adapter

    adapter = get_adapter()

    # PostgreSQL needs a cursor, SQLite can execute directly
    if adapter.is_postgresql():
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.close()
    else:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename TEXT PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _is_all_comments(stmt: str) -> bool:
    """Check if a statement contains only SQL comments.

    Args:
        stmt: SQL statement to check

    Returns:
        True if all non-empty lines start with --
    """
    for line in stmt.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return False
    return True


def _filter_comment_only_statements(statements: list[str]) -> list[str]:
    """Filter out statements that are ONLY comments.

    Args:
        statements: List of SQL statements

    Returns:
        List of statements with comment-only statements removed
    """
    return [s for s in statements if s and not _is_all_comments(s)]


def _get_applied_migration_names(conn: Any) -> set[str]:
    """Get set of already-applied migration filenames.

    Args:
        conn: Database connection

    Returns:
        Set of migration filenames that have been applied
    """
    cursor = conn.cursor()
    cursor.execute("SELECT filename FROM schema_migrations")
    return {row["filename"] if hasattr(row, "keys") else row[0] for row in cursor.fetchall()}


def _execute_postgresql_migration(conn: Any, statements: list[str], name: str, adapter: Any) -> None:
    """Execute migration statements for PostgreSQL with individual commits.

    Args:
        conn: Database connection
        statements: List of SQL statements to execute
        name: Migration filename
        adapter: Database adapter
    """
    cursor = conn.cursor()
    try:
        # Execute each statement with individual commits for PostgreSQL DDL
        # This ensures ALTER TABLE changes are visible to subsequent CREATE INDEX
        for statement in statements:
            cursor.execute(statement)
            conn.commit()

        # Mark migration as applied
        cursor.execute(
            f"INSERT INTO schema_migrations (filename) VALUES ({adapter.placeholder()})",
            (name,),
        )
        conn.commit()
    finally:
        cursor.close()


def _execute_sqlite_migration(conn: Any, sql: str, name: str) -> None:
    """Execute migration SQL for SQLite.

    Args:
        conn: Database connection
        sql: Raw SQL text
        name: Migration filename
    """
    conn.executescript(sql)
    conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (name,))
    conn.commit()


def _apply_migration(conn: Any, migration_file: Path, adapter: Any) -> None:
    """Apply a single migration file.

    Args:
        conn: Database connection
        migration_file: Path to migration file
        adapter: Database adapter
    """
    from .execution_helpers import split_sql_statements

    name = migration_file.name
    logger.info(f"Applying migration {name}")
    sql = migration_file.read_text()

    try:
        statements = split_sql_statements(sql)
        statements = _filter_comment_only_statements(statements)

        if adapter.is_postgresql():
            _execute_postgresql_migration(conn, statements, name, adapter)
        else:
            _execute_sqlite_migration(conn, sql, name)

        logger.info(f"Migration {name} applied successfully")
    except Exception as e:
        conn.rollback()
        logger.error(f"Migration {name} failed: {e}")
        raise


def run_migrations(db_path: str | None = None) -> None:
    """Apply pending migrations located in the migrations directory.

    Works with both SQLite and PostgreSQL databases.
    Selects migrations from migrations/sqlite/ or migrations/postgres/ based on dialect.
    """
    from .core import get_db_connection
    from .dialect import get_adapter
    from .execution_helpers import get_pending_migrations

    adapter = get_adapter()

    # Select correct migration directory based on dialect
    migrations_dir = MIGRATIONS_BASE_DIR / ("postgres" if adapter.is_postgresql() else "sqlite")

    if not migrations_dir.exists():
        logger.info(f"No migrations directory found at {migrations_dir}")
        return

    with get_db_connection(db_path) as conn:
        _ensure_tracking_table(conn)
        conn.commit()

        # Get migrations that haven't been applied yet
        applied = _get_applied_migration_names(conn)
        pending = get_pending_migrations(migrations_dir, applied)

        if not pending:
            logger.info("No pending migrations")
            return

        logger.info(f"Running {len(pending)} pending migrations")

        for migration_file in pending:
            _apply_migration(conn, migration_file, adapter)
