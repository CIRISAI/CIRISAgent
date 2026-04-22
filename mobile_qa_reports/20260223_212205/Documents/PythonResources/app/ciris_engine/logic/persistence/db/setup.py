import logging
import sqlite3

from ciris_engine.logic.config import get_sqlite_db_full_path

from .migration_runner import run_migrations

logger = logging.getLogger(__name__)


def initialize_database(db_path: str | None = None) -> None:
    """Apply pending migrations to initialize or update the database."""
    try:
        run_migrations(db_path)
        logger.info(f"Database migrations applied at {db_path or get_sqlite_db_full_path()}")
    except sqlite3.Error as e:
        logger.exception(f"Database error during initialization: {e}")
        raise
