import logging
import sqlite3
from pathlib import Path
from typing import Any, Union

logger = logging.getLogger(__name__)

MIGRATIONS_BASE_DIR = Path(__file__).resolve().parent.parent / "migrations"


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

    adapter = get_adapter()

    # Select correct migration directory based on dialect
    if adapter.is_postgresql():
        migrations_dir = MIGRATIONS_BASE_DIR / "postgres"
    else:
        migrations_dir = MIGRATIONS_BASE_DIR / "sqlite"

    with get_db_connection(db_path) as conn:
        _ensure_tracking_table(conn)  # type: ignore[arg-type]
        conn.commit()

        migration_files = sorted(migrations_dir.glob("*.sql"))
        for file in migration_files:
            name = file.name

            # Check if migration already applied
            if adapter.is_postgresql():
                cursor = conn.cursor()
                cursor.execute(
                    f"SELECT 1 FROM schema_migrations WHERE filename = {adapter.placeholder()}",
                    (name,),
                )
                already_applied = cursor.fetchone() is not None
                cursor.close()
            else:
                cur = conn.execute("SELECT 1 FROM schema_migrations WHERE filename = ?", (name,))
                already_applied = cur.fetchone() is not None

            if already_applied:
                continue

            logger.info(f"Applying migration {name}")
            sql = file.read_text()
            try:
                # PostgreSQL doesn't support executescript
                if adapter.is_postgresql():
                    cursor = conn.cursor()
                    statements = [s.strip() for s in sql.split(";") if s.strip()]
                    # Filter out SQL comments and empty lines
                    statements = [s for s in statements if s and not s.startswith("--") and s.strip()]

                    # Execute non-empty statements with individual commits for DDL
                    for statement in statements:
                        cursor.execute(statement)
                        # Commit after each DDL statement for PostgreSQL
                        # This ensures ALTER TABLE changes are visible to subsequent CREATE INDEX
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
