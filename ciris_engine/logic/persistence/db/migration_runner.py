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


def run_migrations(db_path: str | None = None) -> None:
    """Apply pending migrations located in the migrations directory.

    Works with both SQLite and PostgreSQL databases.
    Selects migrations from migrations/sqlite/ or migrations/postgres/ based on dialect.
    """
    from .core import get_db_connection
    from .dialect import get_adapter
    from .execution_helpers import get_applied_migrations, get_pending_migrations, record_migration, split_sql_statements

    adapter = get_adapter()

    # Select correct migration directory based on dialect
    if adapter.is_postgresql():
        migrations_dir = MIGRATIONS_BASE_DIR / "postgres"
    else:
        migrations_dir = MIGRATIONS_BASE_DIR / "sqlite"

    if not migrations_dir.exists():
        logger.info(f"No migrations directory found at {migrations_dir}")
        return

    with get_db_connection(db_path) as conn:
        _ensure_tracking_table(conn)
        conn.commit()

        # Get migrations that haven't been applied yet
        # Note: schema_migrations uses 'filename' column, not 'migration_name'
        cursor = conn.cursor()
        cursor.execute("SELECT filename FROM schema_migrations")
        applied = {row["filename"] if hasattr(row, "keys") else row[0] for row in cursor.fetchall()}
        pending = get_pending_migrations(migrations_dir, applied)

        if not pending:
            logger.info("No pending migrations")
            return

        logger.info(f"Running {len(pending)} pending migrations")

        for migration_file in pending:
            name = migration_file.name
            logger.info(f"Applying migration {name}")
            sql = migration_file.read_text()

            try:
                statements = split_sql_statements(sql)
                # Filter out SQL comments
                statements = [s for s in statements if s and not s.startswith("--")]

                if adapter.is_postgresql():
                    cursor = conn.cursor()
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
                    cursor.close()
                    conn.commit()
                else:
                    conn.executescript(sql)
                    conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (name,))
                    conn.commit()

                logger.info(f"Migration {name} applied successfully")
            except Exception as e:
                conn.rollback()
                logger.error(f"Migration {name} failed: {e}")
                raise
