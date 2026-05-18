"""
Database retry mechanism for handling SQLite busy errors.

After 2.9.0 absorption (CIRISAgent#763), the public retry helpers
(`with_retry`, `get_db_connection_with_retry`, `execute_with_retry`)
were removed — they had no production callers, and persist v1.5+ owns
busy-handling internally via sqlx's connection pool.

What remains is the small retry primitive surface used by
`RetryConnection` in `core.py` for the legacy `get_db_connection` path
that still wraps the agent's pre-persist tables (tasks, thoughts,
correlations, etc. — those substrates will absorb into persist on the
T-lane work pending in release/2.9.0).

When those last callers disappear, this whole module goes too.
"""

import logging
import sqlite3

logger = logging.getLogger(__name__)


# Default retry configuration (used by core.RetryConnection).
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 0.1  # 100ms
DEFAULT_MAX_DELAY = 1.0  # 1 second


def is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable (database busy/locked)."""
    if isinstance(error, sqlite3.OperationalError):
        error_msg = str(error).lower()
        return "database is locked" in error_msg or "database table is locked" in error_msg
    return False
