import logging
import sqlite3
import sys
import threading
import time
import types
from datetime import datetime
from typing import Any, Dict, Optional, TypedDict, Union

from ciris_engine.logic.config.db_paths import get_sqlite_db_full_path

# iOS-specific: Global lock for SQLite operations to avoid iOS's SQLiteDatabaseTracking assertions
# iOS's debug SQLite has stricter thread checking that triggers assertions with check_same_thread=False
_ios_sqlite_lock: Optional[threading.RLock] = None
_is_ios_platform: Optional[bool] = None


def _check_ios_platform() -> bool:
    """Check if running on iOS."""
    global _is_ios_platform
    if _is_ios_platform is None:
        _is_ios_platform = sys.platform == "ios" or (
            sys.platform == "darwin" and hasattr(sys, "implementation")
            and "iphoneos" in getattr(sys.implementation, "_multiarch", "").lower()
        )
    return _is_ios_platform


def _get_ios_lock() -> threading.RLock:
    """Get the iOS SQLite lock (created lazily)."""
    global _ios_sqlite_lock
    if _ios_sqlite_lock is None:
        _ios_sqlite_lock = threading.RLock()
    return _ios_sqlite_lock
from ciris_engine.schemas.persistence.postgres import tables as postgres_tables
from ciris_engine.schemas.persistence.sqlite import tables as sqlite_tables

from .dialect import init_dialect
from .migration_runner import run_migrations
from .retry import DEFAULT_BASE_DELAY, DEFAULT_MAX_DELAY, DEFAULT_MAX_RETRIES, is_retryable_error

logger = logging.getLogger(__name__)

# Try to import psycopg2 for PostgreSQL support
try:
    import psycopg2
    import psycopg2.extras

    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    logger.debug("psycopg2 not available - PostgreSQL support disabled")


# Test database path override - set by test fixtures
_test_db_path: Optional[str] = None


# Custom datetime adapter and converter for SQLite
def adapt_datetime(ts: datetime) -> str:
    """Convert datetime to ISO 8601 string."""
    return ts.isoformat()


def convert_datetime(val: bytes) -> datetime:
    """Convert ISO 8601 string back to datetime."""
    return datetime.fromisoformat(val.decode())


# Track if adapters have been registered
_adapters_registered = False


def _ensure_adapters_registered() -> None:
    """Register SQLite adapters if not already done."""
    global _adapters_registered
    if not _adapters_registered:
        sqlite3.register_adapter(datetime, adapt_datetime)
        sqlite3.register_converter("timestamp", convert_datetime)
        _adapters_registered = True


class PostgreSQLCursorWrapper:
    """Wrapper for PostgreSQL cursor to translate SQL placeholders.

    This wrapper ensures that ? placeholders are translated to %s
    even when code directly uses cursor.execute().
    """

    def __init__(self, cursor: Any):
        """Initialize wrapper with psycopg2 cursor."""
        self._cursor = cursor

    def execute(self, sql: str, parameters: Any = None) -> Any:
        """Execute SQL with placeholder translation.

        Translates:
        - ? -> %s (for positional parameters with tuple/list)
        - :name -> %(name)s (for named parameters with dict)
        """
        import re

        # If using named parameters (dict), convert :name to %(name)s
        if parameters and isinstance(parameters, dict):
            # Replace :param_name with %(param_name)s
            translated_sql = re.sub(r":(\w+)", r"%(\1)s", sql)
        else:
            # Using positional parameters, convert ? to %s
            translated_sql = sql.replace("?", "%s")

        if parameters:
            return self._cursor.execute(translated_sql, parameters)
        else:
            return self._cursor.execute(translated_sql)

    def executemany(self, sql: str, seq_of_parameters: Any) -> Any:
        """Execute many SQL statements with placeholder translation."""
        translated_sql = sql.replace("?", "%s")
        return self._cursor.executemany(translated_sql, seq_of_parameters)

    def fetchone(self) -> Any:
        """Fetch one row."""
        return self._cursor.fetchone()

    def fetchall(self) -> Any:
        """Fetch all rows."""
        return self._cursor.fetchall()

    def fetchmany(self, size: Optional[int] = None) -> Any:
        """Fetch many rows."""
        if size is None:
            return self._cursor.fetchmany()
        return self._cursor.fetchmany(size)

    def close(self) -> None:
        """Close cursor."""
        self._cursor.close()

    @property
    def rowcount(self) -> Any:
        """Get row count."""
        return self._cursor.rowcount

    @property
    def description(self) -> Any:
        """Get description."""
        return self._cursor.description

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to the underlying cursor."""
        return getattr(self._cursor, name)

    def __iter__(self) -> Any:
        """Make cursor iterable."""
        return iter(self._cursor)


class PostgreSQLConnectionWrapper:
    """Wrapper for PostgreSQL connection to provide SQLite-like interface.

    This wrapper allows code written for SQLite (which supports conn.execute())
    to work with PostgreSQL (which requires cursor.execute()).
    """

    def __init__(self, conn: Any):
        """Initialize wrapper with psycopg2 connection."""
        self._conn = conn

    def execute(self, sql: str, parameters: Any = None) -> Any:
        """Execute SQL statement using a cursor.

        CRITICAL: Translates SQL placeholders for PostgreSQL compatibility:
        - ? -> %s (for positional parameters)
        - :name -> %(name)s (for named parameters)
        """
        import re

        # Translate placeholders based on parameter type
        if parameters and isinstance(parameters, dict):
            # Named parameters: :name -> %(name)s
            translated_sql = re.sub(r":(\w+)", r"%(\1)s", sql)
        else:
            # Positional parameters: ? -> %s
            translated_sql = sql.replace("?", "%s")

        cursor = self._conn.cursor()
        logger.debug("PostgreSQLConnectionWrapper.execute: Placeholder translation")
        logger.debug(f"  original: {sql[:150]}...")
        logger.debug(f"  translated: {translated_sql[:150]}...")
        logger.debug(f"  param type: {type(parameters).__name__}, value: {parameters}")

        if parameters:
            cursor.execute(translated_sql, parameters)
        else:
            cursor.execute(translated_sql)

        logger.debug(f"PostgreSQLConnectionWrapper.execute: SUCCESS, rowcount={cursor.rowcount}")
        return cursor

    def executemany(self, sql: str, seq_of_parameters: Any) -> Any:
        """Execute SQL statement multiple times.

        CRITICAL: Translates ? placeholders to %s for PostgreSQL compatibility.
        """
        # CRITICAL: Translate placeholders for PostgreSQL
        translated_sql = sql.replace("?", "%s")

        cursor = self._conn.cursor()
        cursor.executemany(translated_sql, seq_of_parameters)
        return cursor

    def cursor(self) -> Any:
        """Create and return a new cursor wrapped for PostgreSQL compatibility."""
        # Return a wrapped cursor that translates placeholders
        return PostgreSQLCursorWrapper(self._conn.cursor())

    def commit(self) -> None:
        """Commit the current transaction."""
        self._conn.commit()

    def rollback(self) -> None:
        """Rollback the current transaction."""
        self._conn.rollback()

    def close(self) -> None:
        """Close the connection."""
        self._conn.close()

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to the underlying connection."""
        return getattr(self._conn, name)

    def __enter__(self) -> "PostgreSQLConnectionWrapper":
        """Context manager entry."""
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Context manager exit - commit if no exception, rollback otherwise."""
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        self._conn.close()


class iOSDictRow(dict):
    """A dict subclass that supports both string key and integer index access.

    This mimics sqlite3.Row behavior for iOS compatibility:
    - row["column_name"] works (string key access)
    - row[0], row[1] works (integer index access)
    - dict(row) and **row only yield string keys (for Pydantic model unpacking)

    The integer index access is provided via __getitem__ override, but integers
    are NOT stored as dict keys. This ensures Task(**row) works correctly.
    """

    def __init__(self, string_dict: dict, column_order: list):
        """Initialize with string-keyed dict and column order for integer access.

        Args:
            string_dict: Dict with string keys only
            column_order: List of column names in order, for integer indexing
        """
        super().__init__(string_dict)
        self._column_order = column_order

    def __getitem__(self, key):
        """Support both string and integer key access."""
        if isinstance(key, int):
            # Integer access - look up column name by index
            if 0 <= key < len(self._column_order):
                col_name = self._column_order[key]
                return super().__getitem__(col_name)
            raise IndexError(f"Index {key} out of range (columns: {len(self._column_order)})")
        # String access - normal dict behavior
        return super().__getitem__(key)

    def get(self, key, default=None):
        """Support both string and integer key access with default."""
        try:
            return self.__getitem__(key)
        except (KeyError, IndexError):
            return default


class iOSSerializedCursor:
    """Cursor wrapper that serializes all access for iOS compatibility.

    This ensures cursor.execute() and other cursor methods go through the global lock.
    On iOS, cursors are closed after fetch to prevent SQLiteDatabaseTracking assertions,
    and automatically recreated on the next execute().
    """

    def __init__(self, cursor: sqlite3.Cursor, lock: threading.RLock, conn: sqlite3.Connection):
        self._cursor = cursor
        self._lock = lock
        self._conn = conn  # Keep reference to recreate cursor if needed
        self._closed = False
        logger.info(f"[iOS_CURSOR] Created wrapper for {cursor}")

    def _ensure_cursor(self) -> None:
        """Recreate cursor if it was closed (iOS pattern)."""
        if self._closed and _check_ios_platform():
            with self._lock:
                self._cursor = self._conn.cursor()
                self._closed = False
                logger.info("[iOS_CURSOR] Recreated cursor after close")

    def execute(self, sql: str, parameters: Any = None) -> "iOSSerializedCursor":
        self._ensure_cursor()  # Recreate if needed on iOS
        logger.info(f"[iOS_CURSOR] execute: {sql[:80]}...")
        with self._lock:
            try:
                if parameters is not None:
                    self._cursor.execute(sql, parameters)
                else:
                    self._cursor.execute(sql)
                logger.info("[iOS_CURSOR] execute succeeded")
                return self
            except Exception as e:
                logger.error(f"[iOS_CURSOR] execute FAILED: {e}")
                raise

    def executemany(self, sql: str, seq_of_parameters: Any) -> "iOSSerializedCursor":
        logger.info(f"[iOS_CURSOR] executemany: {sql[:80]}...")
        with self._lock:
            self._cursor.executemany(sql, seq_of_parameters)
            return self

    def _row_to_dict(self, row: Any) -> dict:
        """Convert sqlite3.Row to iOSDictRow for iOS compatibility.

        Returns an iOSDictRow that:
        - Supports string key access: row["column_name"]
        - Supports integer index access: row[0], row[1]
        - Only yields string keys for dict() and ** unpacking

        This ensures both `row[0]` and `Task(**row)` work correctly.
        """
        if row is None:
            return None
        # Get column names from cursor description
        if self._cursor.description:
            columns = [col[0] for col in self._cursor.description]
            string_dict = {}
            for col_name, value in zip(columns, row):
                string_dict[col_name] = value
            # Return iOSDictRow that supports both string and integer access
            return iOSDictRow(string_dict, columns)
        # Fallback: try to get keys from the row itself if it's dict-like
        if hasattr(row, 'keys'):
            return dict(row)
        # Last resort: log warning and return empty dict
        logger.warning("[iOS_CURSOR] _row_to_dict: no description and row has no keys()")
        return {}

    def fetchone(self) -> Any:
        if self._closed:
            logger.warning("[iOS_CURSOR] fetchone() called on closed cursor, returning None")
            return None
        logger.info("[iOS_CURSOR] fetchone() called...")
        with self._lock:
            try:
                result = self._cursor.fetchone()
                # On iOS, convert Row to dict and close cursor immediately
                if _check_ios_platform():
                    if result is not None:
                        result = self._row_to_dict(result)
                    # Close cursor immediately to prevent iOS tracking assertions
                    self._cursor.close()
                    self._closed = True
                    logger.info(f"[iOS_CURSOR] fetchone() result={result}, cursor closed")
                else:
                    logger.info(f"[iOS_CURSOR] fetchone() succeeded: {result}")
                return result
            except Exception as e:
                logger.error(f"[iOS_CURSOR] fetchone() FAILED: {e}")
                raise

    def fetchall(self) -> Any:
        if self._closed:
            logger.warning("[iOS_CURSOR] fetchall() called on closed cursor, returning []")
            return []
        logger.info("[iOS_CURSOR] fetchall() called...")
        with self._lock:
            try:
                result = self._cursor.fetchall()
                # On iOS, convert Rows to dicts and close cursor immediately
                if _check_ios_platform():
                    if result:
                        result = [self._row_to_dict(row) for row in result]
                    # Close cursor immediately to prevent iOS tracking assertions
                    self._cursor.close()
                    self._closed = True
                    logger.info(f"[iOS_CURSOR] fetchall() rows={len(result) if result else 0}, cursor closed")
                else:
                    logger.info(f"[iOS_CURSOR] fetchall() succeeded: {len(result) if result else 0} rows")
                return result
            except Exception as e:
                logger.error(f"[iOS_CURSOR] fetchall() FAILED: {e}")
                raise

    def fetchmany(self, size: Optional[int] = None) -> Any:
        with self._lock:
            if size is None:
                return self._cursor.fetchmany()
            return self._cursor.fetchmany(size)

    def close(self) -> None:
        with self._lock:
            self._cursor.close()

    @property
    def rowcount(self) -> int:
        return self._cursor.rowcount

    @property
    def lastrowid(self) -> Optional[int]:
        return self._cursor.lastrowid

    @property
    def description(self) -> Any:
        return self._cursor.description

    def __iter__(self) -> Any:
        return iter(self._cursor)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._cursor, name)


class iOSSerializedConnection:
    """SQLite connection wrapper that serializes all access for iOS compatibility.

    iOS's debug SQLite has strict thread checking that causes assertion failures
    when connections are used from multiple threads, even with check_same_thread=False.
    This wrapper uses a global lock to serialize all database access.

    CRITICAL: cursor() returns a wrapped cursor so cursor.execute() also goes through lock.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = _get_ios_lock()
        logger.info("[iOS_CONN] iOSSerializedConnection created")

    def execute(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        sql = args[0] if args else "unknown"
        logger.debug(f"[iOS_CONN] execute: {sql[:100]}...")
        with self._lock:
            try:
                result = self._conn.execute(*args, **kwargs)
                logger.debug("[iOS_CONN] execute succeeded")
                return result
            except Exception as e:
                logger.error(f"[iOS_CONN] execute FAILED: {e}")
                raise

    def executemany(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        sql = args[0] if args else "unknown"
        logger.debug(f"[iOS_CONN] executemany: {sql[:100]}...")
        with self._lock:
            return self._conn.executemany(*args, **kwargs)

    def executescript(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        logger.debug("[iOS_CONN] executescript called")
        with self._lock:
            return self._conn.executescript(*args, **kwargs)

    def cursor(self) -> iOSSerializedCursor:
        """Return a WRAPPED cursor that serializes all operations."""
        logger.info("[iOS_CONN] cursor() called - creating wrapped cursor...")
        with self._lock:
            try:
                raw_cursor = self._conn.cursor()
                # Pass connection reference so cursor can be recreated on iOS
                wrapped = iOSSerializedCursor(raw_cursor, self._lock, self._conn)
                logger.info("[iOS_CONN] cursor() succeeded, returning wrapped cursor")
                return wrapped
            except Exception as e:
                logger.error(f"[iOS_CONN] cursor() FAILED: {e}")
                raise

    def commit(self) -> None:
        logger.debug("[iOS_CONN] commit() called")
        with self._lock:
            self._conn.commit()

    def rollback(self) -> None:
        logger.debug("[iOS_CONN] rollback() called")
        with self._lock:
            self._conn.rollback()

    def close(self) -> None:
        logger.info("[iOS_CONN] close() called")
        with self._lock:
            self._conn.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __enter__(self) -> "iOSSerializedConnection":
        logger.debug("[iOS_CONN] __enter__ called")
        self._lock.acquire()
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        logger.debug(f"[iOS_CONN] __exit__ called, exc_type={exc_type}")
        try:
            return self._conn.__exit__(exc_type, exc_val, exc_tb)
        finally:
            self._lock.release()


class RetryConnection:
    """SQLite connection wrapper with automatic retry on write operations."""

    # SQL commands that modify data
    WRITE_COMMANDS = {"INSERT", "UPDATE", "DELETE", "CREATE", "DROP", "ALTER", "REPLACE"}

    def __init__(
        self,
        conn: sqlite3.Connection,
        max_retries: int = DEFAULT_MAX_RETRIES,
        base_delay: float = DEFAULT_BASE_DELAY,
        max_delay: float = DEFAULT_MAX_DELAY,
        enable_retry: bool = True,
    ):
        self._conn = conn
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._enable_retry = enable_retry

    def _is_write_operation(self, sql: str) -> bool:
        """Check if SQL command is a write operation."""
        if not sql:
            return False
        # Get first word of SQL command
        first_word = sql.strip().split()[0].upper()
        return first_word in self.WRITE_COMMANDS

    def _retry_execute(self, method_name: str, *args: Any, **kwargs: Any) -> Any:
        """Execute with retry logic for write operations."""
        # Check if this is a write operation
        sql = args[0] if args else kwargs.get("sql", "")
        is_write = self._is_write_operation(sql)

        # If retry is disabled or this is not a write operation, execute directly
        if not self._enable_retry or not is_write:
            method = getattr(self._conn, method_name)
            return method(*args, **kwargs)

        # Retry logic for write operations
        last_error = None
        for attempt in range(self._max_retries + 1):
            try:
                method = getattr(self._conn, method_name)
                return method(*args, **kwargs)
            except Exception as e:
                if not is_retryable_error(e) or attempt == self._max_retries:
                    raise

                last_error = e
                delay = min(self._base_delay * (2**attempt), self._max_delay)

                logger.debug(
                    f"Database busy on write operation (attempt {attempt + 1}/{self._max_retries + 1}), "
                    f"retrying in {delay:.2f}s: {e}"
                )

                time.sleep(delay)

        # Should not reach here
        raise last_error if last_error else RuntimeError("Unexpected retry loop exit")

    def execute(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        """Execute SQL with retry for write operations."""
        return self._retry_execute("execute", *args, **kwargs)  # type: ignore[no-any-return]

    def executemany(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        """Execute many SQL statements with retry for write operations."""
        return self._retry_execute("executemany", *args, **kwargs)  # type: ignore[no-any-return]

    def executescript(self, *args: Any, **kwargs: Any) -> sqlite3.Cursor:
        """Execute SQL script with retry."""
        # Scripts may contain multiple operations, so always retry
        if not self._enable_retry:
            return self._conn.executescript(*args, **kwargs)
        return self._retry_execute("executescript", *args, **kwargs)  # type: ignore[no-any-return]

    def __getattr__(self, name: str) -> Any:
        """Delegate all other attributes to the underlying connection."""
        return getattr(self._conn, name)

    def __enter__(self) -> "RetryConnection":
        """Context manager entry."""
        self._conn.__enter__()
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> Any:
        """Context manager exit."""
        return self._conn.__exit__(exc_type, exc_val, exc_tb)


def get_db_connection(
    db_path: Optional[str] = None, busy_timeout: Optional[int] = None, enable_retry: bool = True
) -> Union[sqlite3.Connection, RetryConnection, Any]:
    """Establishes a connection to the database (SQLite or PostgreSQL).

    Supports both SQLite and PostgreSQL backends via connection string detection.
    Connection string format:
    - SQLite: "sqlite://path/to/db.db" or just "path/to/db.db"
    - PostgreSQL: "postgresql://user:pass@host:port/dbname"

    Args:
        db_path: Optional database connection string (defaults to SQLite data/ciris.db)
        busy_timeout: Optional busy timeout in milliseconds (SQLite only)
        enable_retry: Enable automatic retry for write operations (SQLite only)

    Returns:
        Database connection:
        - SQLite: RetryConnection wrapper (if enable_retry=True) or raw Connection
        - PostgreSQL: psycopg2 connection with dict cursor factory
    """
    import traceback
    caller_info = ''.join(traceback.format_stack()[-4:-1])
    logger.info(f"[DB_CONNECT] get_db_connection called from:\n{caller_info}")

    # Default to SQLite for backward compatibility
    if db_path is None:
        logger.info("[DB_CONNECT] db_path is None, resolving...")
        # Check for test override first
        if _test_db_path is not None:
            db_path = _test_db_path
            logger.info(f"[DB_CONNECT] Using test override path: {db_path}")
        else:
            logger.info("[DB_CONNECT] Calling get_sqlite_db_full_path()...")
            db_path = get_sqlite_db_full_path()
            logger.info(f"[DB_CONNECT] Resolved path: {db_path}")

    # Initialize dialect adapter based on connection string
    adapter = init_dialect(db_path)

    # PostgreSQL connection
    if adapter.is_postgresql():
        if not POSTGRES_AVAILABLE:
            raise RuntimeError(
                "PostgreSQL connection requested but psycopg2 not installed. "
                "Install with: pip install psycopg2-binary"
            )

        conn = psycopg2.connect(adapter.db_url)
        # Use dict cursor for compatibility with SQLite Row factory
        conn.cursor_factory = psycopg2.extras.RealDictCursor
        # Wrap connection to provide SQLite-like execute() interface
        return PostgreSQLConnectionWrapper(conn)

    # SQLite connection (default)
    logger.info(f"[DB_CONNECT] Creating SQLite connection to: {db_path}")
    _ensure_adapters_registered()

    # Detect iOS platform for special handling
    is_ios = _check_ios_platform()
    logger.info(f"[DB_CONNECT] Platform detection: is_ios={is_ios}")

    # iOS-specific connection settings to avoid SQLiteDatabaseTracking assertions
    if is_ios:
        logger.info("[DB_CONNECT] iOS mode: using serialized connection settings")
        # On iOS, use serialized mode and autocommit to avoid threading issues
        # with iOS's internal SQLite debugging infrastructure
        try:
            logger.info(f"[DB_CONNECT] Calling sqlite3.connect({db_path})...")
            conn = sqlite3.connect(
                db_path,
                check_same_thread=False,
                detect_types=sqlite3.PARSE_DECLTYPES,
                isolation_level=None,  # Autocommit mode - avoids transaction state issues
                timeout=30.0,  # Longer timeout for iOS
            )
            logger.info(f"[DB_CONNECT] sqlite3.connect succeeded, conn={conn}")
        except Exception as e:
            logger.error(f"[DB_CONNECT] sqlite3.connect FAILED: {e}")
            raise
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)

    logger.info("[DB_CONNECT] Setting row_factory...")
    conn.row_factory = sqlite3.Row

    # Apply SQLite PRAGMA directives
    # On iOS, skip WAL mode as it can cause issues with iOS's SQLite debugging
    if is_ios:
        pragma_statements = [
            "PRAGMA foreign_keys = ON;",
            "PRAGMA journal_mode=WAL;",  # WAL mode for better concurrent access on iOS
            f"PRAGMA busy_timeout = {busy_timeout if busy_timeout is not None else 30000};",  # 30s timeout for iOS
            "PRAGMA synchronous=NORMAL;",  # Less strict sync for better iOS compatibility
        ]
    else:
        pragma_statements = [
            "PRAGMA foreign_keys = ON;",
            "PRAGMA journal_mode=WAL;",
            f"PRAGMA busy_timeout = {busy_timeout if busy_timeout is not None else 5000};",
        ]

    # On iOS, wrap with serialized connection BEFORE executing PRAGMAs
    # This ensures all database access goes through the lock from the start
    if is_ios:
        logger.info("[DB_CONNECT] Wrapping connection with iOSSerializedConnection BEFORE PRAGMAs...")
        conn = iOSSerializedConnection(conn)
        logger.info("[DB_CONNECT] iOS wrapper created, now executing PRAGMAs through wrapper")

    logger.info(f"[DB_CONNECT] Executing {len(pragma_statements)} PRAGMA statements...")
    for pragma in pragma_statements:
        result = adapter.pragma(pragma)
        if result:  # Only execute if dialect returns a statement
            logger.info(f"[DB_CONNECT] Executing: {result}")
            try:
                conn.execute(result)
                logger.info(f"[DB_CONNECT] PRAGMA succeeded: {result}")
            except Exception as e:
                logger.error(f"[DB_CONNECT] PRAGMA FAILED: {result} - {e}")
                raise

    # Return wrapped connection with retry logic by default
    if enable_retry and not is_ios:  # iOS already has serialization, skip retry wrapper
        logger.info("[DB_CONNECT] Returning RetryConnection wrapper")
        return RetryConnection(conn)

    logger.info(f"[DB_CONNECT] Returning connection: {type(conn).__name__}")
    return conn


# Removed unused schema getter functions - only graph schemas are used


def get_graph_nodes_table_schema_sql() -> str:
    return sqlite_tables.GRAPH_NODES_TABLE_V1


def get_graph_edges_table_schema_sql() -> str:
    return sqlite_tables.GRAPH_EDGES_TABLE_V1


def get_service_correlations_table_schema_sql() -> str:
    return sqlite_tables.SERVICE_CORRELATIONS_TABLE_V1


class ConnectionDiagnostics(TypedDict, total=False):
    """Typed structure for database connection diagnostic information."""

    dialect: str
    connection_string: str
    is_postgresql: bool
    is_sqlite: bool
    active_connections: int  # PostgreSQL only
    connection_error: str  # If connection diagnostics failed
    connectivity: str  # "OK" or "FAILED: {error}"


def get_connection_diagnostics(db_path: Optional[str] = None) -> ConnectionDiagnostics:
    """Get diagnostic information about database connections.

    Useful for debugging connection issues in production, especially PostgreSQL.

    Args:
        db_path: Optional database connection string

    Returns:
        Dictionary with connection diagnostic information
    """
    if db_path is None:
        db_path = get_sqlite_db_full_path()

    adapter = init_dialect(db_path)
    diagnostics: ConnectionDiagnostics = {
        "dialect": adapter.dialect.value,
        "connection_string": adapter.db_url if adapter.is_postgresql() else adapter.db_path,
        "is_postgresql": adapter.is_postgresql(),
        "is_sqlite": adapter.is_sqlite(),
    }

    # Try to get active connection count for PostgreSQL
    if adapter.is_postgresql():
        try:
            with get_db_connection(db_path=db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT count(*) as connection_count
                    FROM pg_stat_activity
                    WHERE datname = current_database()
                    """
                )
                result = cursor.fetchone()
                if result:
                    diagnostics["active_connections"] = (
                        result[0] if isinstance(result, tuple) else result["connection_count"]
                    )
                cursor.close()
        except Exception as e:
            diagnostics["connection_error"] = str(e)
            logger.warning(f"Failed to get PostgreSQL connection diagnostics: {e}")

    # Test basic connectivity
    try:
        with get_db_connection(db_path=db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            diagnostics["connectivity"] = "OK"
    except Exception as e:
        diagnostics["connectivity"] = f"FAILED: {e}"
        logger.error(f"Database connectivity test failed for {db_path}: {e}")

    return diagnostics


def initialize_database(db_path: Optional[str] = None) -> None:
    """Initialize the database with base schema and apply migrations.

    Note: Each deployment uses either SQLite or PostgreSQL exclusively.
    No migration between database backends is supported.
    """
    import traceback
    caller_info = ''.join(traceback.format_stack()[-4:-1])
    logger.info(f"[DB_INIT] initialize_database called from:\n{caller_info}")

    from ciris_engine.logic.persistence.db.execution_helpers import (
        execute_sql_statements,
        mask_password_in_url,
        split_sql_statements,
    )

    try:
        # Determine if we're using PostgreSQL or SQLite
        if db_path is None:
            db_path = get_sqlite_db_full_path()

        adapter = init_dialect(db_path)

        # Log which database type we're initializing
        tables_module: types.ModuleType
        if adapter.is_postgresql():
            safe_url = mask_password_in_url(adapter.db_url)
            logger.info(f"Initializing PostgreSQL database: {safe_url}")
            tables_module = postgres_tables
        else:
            logger.info(f"Initializing SQLite database: {db_path}")
            tables_module = sqlite_tables

        with get_db_connection(db_path) as conn:
            base_tables = [
                tables_module.TASKS_TABLE_V1,
                tables_module.THOUGHTS_TABLE_V1,
                tables_module.FEEDBACK_MAPPINGS_TABLE_V1,
                tables_module.GRAPH_NODES_TABLE_V1,
                tables_module.GRAPH_EDGES_TABLE_V1,
                tables_module.SERVICE_CORRELATIONS_TABLE_V1,
                tables_module.AUDIT_LOG_TABLE_V1,
                tables_module.AUDIT_ROOTS_TABLE_V1,
                tables_module.AUDIT_SIGNING_KEYS_TABLE_V1,
                tables_module.WA_CERT_TABLE_V1,
            ]

            for table_sql in base_tables:
                statements = split_sql_statements(table_sql)
                execute_sql_statements(conn, statements, adapter)

            conn.commit()

        run_migrations(db_path)

        logger.info(f"Database initialized at {db_path or get_sqlite_db_full_path()}")
    except Exception as e:
        logger.exception(f"Database error during initialization: {e}")
        raise
