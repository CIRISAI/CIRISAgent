"""Retry primitives for the legacy SQLite bootstrap layer.

After 2.9.0, every production write path routes through ciris-persist
which has its own retry semantics. The constants and `is_retryable_error`
helper below are still consumed by the connection-pool wrapper inside
`db/core.py` for the SQLite-only bootstrap upgrade path (legacy CREATE
TABLE statements during 2.8.x → 2.9.0 migration). No new callers.
"""

import sqlite3

DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 0.1
DEFAULT_MAX_DELAY = 1.0


def is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable (SQLite database busy/locked)."""
    if isinstance(error, sqlite3.OperationalError):
        msg = str(error).lower()
        return "database is locked" in msg or "database table is locked" in msg
    return False
