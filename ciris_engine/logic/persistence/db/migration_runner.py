import logging
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def _ensure_tracking_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            filename TEXT PRIMARY KEY,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def run_migrations(db_path: str | None = None) -> None:
    """Apply pending migrations located in the migrations directory."""
    from .core import get_db_connection

    with get_db_connection(db_path) as conn:
        _ensure_tracking_table(conn)  # type: ignore[arg-type]
        conn.commit()

        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        for file in migration_files:
            name = file.name
            cur = conn.execute("SELECT 1 FROM schema_migrations WHERE filename = ?", (name,))
            if cur.fetchone():
                continue
            logger.info(f"Applying migration {name}")
            sql = file.read_text()
            try:
                conn.executescript(sql)
                conn.execute("INSERT INTO schema_migrations (filename) VALUES (?)", (name,))
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Migration {name} failed: {e}")
                raise
