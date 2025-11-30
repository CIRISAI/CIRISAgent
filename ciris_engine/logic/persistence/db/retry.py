"""
Database retry mechanism for handling SQLite busy errors.

Provides a minimal, clean retry wrapper for database operations
to handle concurrent access issues gracefully.
"""

import functools
import logging
import sqlite3
import time
from contextlib import contextmanager
from typing import Any, Callable, Iterator, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Default retry configuration
DEFAULT_MAX_RETRIES = 3
DEFAULT_BASE_DELAY = 0.1  # 100ms
DEFAULT_MAX_DELAY = 1.0  # 1 second


def is_retryable_error(error: Exception) -> bool:
    """Check if an error is retryable (database busy/locked)."""
    if isinstance(error, sqlite3.OperationalError):
        error_msg = str(error).lower()
        return "database is locked" in error_msg or "database table is locked" in error_msg
    return False


def with_retry(
    func: Callable[..., T] | None = None,
    *,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
    max_delay: float = DEFAULT_MAX_DELAY,
) -> Callable[..., T] | Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator for retrying database operations on busy errors.

    Can be used as:
        @with_retry
        def my_func(): ...

        @with_retry(max_retries=5, base_delay=0.5)
        def my_func(): ...

    Args:
        func: Function to retry (None when used with parameters)
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries (exponential backoff)
        max_delay: Maximum delay between retries

    Returns:
        Wrapped function with retry logic or decorator
    """

    def decorator(f: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            last_error = None

            for attempt in range(max_retries + 1):  # +1 for initial attempt
                try:
                    return f(*args, **kwargs)
                except Exception as e:
                    if not is_retryable_error(e) or attempt == max_retries:
                        # Not retryable or last attempt - re-raise
                        raise

                    last_error = e
                    delay = min(base_delay * (2**attempt), max_delay)

                    logger.debug(
                        f"Database busy error on attempt {attempt + 1}/{max_retries + 1}, "
                        f"retrying in {delay:.2f}s: {e}"
                    )

                    time.sleep(delay)

            # Should not reach here, but just in case
            raise last_error if last_error else RuntimeError("Unexpected retry loop exit")

        return wrapper

    # If func is provided, we're being used as @with_retry
    if func is not None:
        return decorator(func)

    # Otherwise, we're being used as @with_retry(...) and need to return decorator
    return decorator


@contextmanager
def get_db_connection_with_retry(db_path: str | None = None, busy_timeout: int = 5000) -> Iterator[sqlite3.Connection]:
    """
    Get a database connection with busy timeout configured.

    Args:
        db_path: Optional database path
        busy_timeout: Busy timeout in milliseconds (default 5 seconds)

    Yields:
        Database connection with retry configuration
    """
    from .core import get_db_connection

    conn = get_db_connection(db_path)
    try:
        # Enable WAL mode for better concurrent access
        conn.execute("PRAGMA journal_mode=WAL")
        # Set busy timeout to wait before failing
        conn.execute(f"PRAGMA busy_timeout={busy_timeout}")
        yield conn  # type: ignore[misc]
    finally:
        conn.close()


def execute_with_retry(
    operation: Callable[[sqlite3.Connection], T],
    db_path: str | None = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    base_delay: float = DEFAULT_BASE_DELAY,
) -> T:
    """
    Execute a database operation with automatic retry on busy errors.

    Args:
        operation: Function that takes a connection and performs database operations
        db_path: Optional database path
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay between retries

    Returns:
        Result of the operation

    Example:
        def insert_task(conn):
            cursor = conn.cursor()
            cursor.execute("INSERT INTO tasks ...")
            conn.commit()
            return cursor.lastrowid

        task_id = execute_with_retry(insert_task)
    """

    @with_retry(max_retries=max_retries, base_delay=base_delay)  # type: ignore
    def _execute() -> T:
        with get_db_connection_with_retry(db_path) as conn:
            return operation(conn)

    return _execute()
