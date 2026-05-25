import logging
import sqlite3
import sys
import threading
import time
import types
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Tuple, TypedDict, Union, cast

from ciris_engine.logic.config.db_paths import get_audit_db_full_path, get_sqlite_db_full_path

# iOS-specific: Global lock for SQLite operations to avoid iOS's SQLiteDatabaseTracking assertions
# iOS's debug SQLite has stricter thread checking that triggers assertions with check_same_thread=False
_ios_sqlite_lock: Optional[threading.RLock] = None
_is_ios_platform: Optional[bool] = None

# iOS thread-local connection cache: Apple's SQLiteDatabaseTracking (iOS 26+) asserts if a
# sqlite3* handle is used from a different thread than the one that called sqlite3_open().
# Python-level locks don't help — the check is in Apple's C interposer. The fix: reuse
# the same connection per (thread, db_path) pair so the opening thread always matches.
_ios_thread_local = threading.local()


def _check_ios_platform() -> bool:
    """Check if running on iOS."""
    global _is_ios_platform
    if _is_ios_platform is None:
        _is_ios_platform = sys.platform == "ios" or (
            sys.platform == "darwin"
            and hasattr(sys, "implementation")
            and "iphoneos" in getattr(sys.implementation, "_multiarch", "").lower()
        )
    return _is_ios_platform


def _get_ios_lock() -> threading.RLock:
    """Get the iOS SQLite lock (created lazily)."""
    global _ios_sqlite_lock
    if _ios_sqlite_lock is None:
        _ios_sqlite_lock = threading.RLock()
    return _ios_sqlite_lock


from .dialect import init_dialect
from .retry import DEFAULT_BASE_DELAY, DEFAULT_MAX_DELAY, DEFAULT_MAX_RETRIES, is_retryable_error

logger = logging.getLogger(__name__)


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


class IOSDictRow(dict[str, Any]):
    """A dict subclass that supports both string key and integer index access.

    This mimics sqlite3.Row behavior for iOS compatibility:
    - row["column_name"] works (string key access)
    - row[0], row[1] works (integer index access)
    - dict(row) and **row only yield string keys (for Pydantic model unpacking)

    The integer index access is provided via __getitem__ override, but integers
    are NOT stored as dict keys. This ensures Task(**row) works correctly.
    """

    def __init__(self, string_dict: dict[str, Any], column_order: list[str]):
        """Initialize with string-keyed dict and column order for integer access.

        Args:
            string_dict: Dict with string keys only
            column_order: List of column names in order, for integer indexing
        """
        super().__init__(string_dict)
        self._column_order = column_order

    def __getitem__(self, key: str | int) -> Any:
        """Support both string and integer key access."""
        if isinstance(key, int):
            # Integer access - look up column name by index
            if 0 <= key < len(self._column_order):
                col_name = self._column_order[key]
                return super().__getitem__(col_name)
            raise IndexError(f"Index {key} out of range (columns: {len(self._column_order)})")
        # String access - normal dict behavior
        return super().__getitem__(key)

    def get(self, key: str | int, default: Any = None) -> Any:
        """Support both string and integer key access with default."""
        try:
            return self.__getitem__(key)
        except (KeyError, IndexError):
            return default


class IOSSerializedCursor:
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
        logger.debug(f"[iOS_CURSOR] Created wrapper for {cursor}")

    def _ensure_cursor(self) -> None:
        """Recreate cursor if it was closed (iOS pattern)."""
        if self._closed and _check_ios_platform():
            with self._lock:
                self._cursor = self._conn.cursor()
                self._closed = False
                logger.debug("[iOS_CURSOR] Recreated cursor after close")

    def execute(self, sql: str, parameters: Any = None) -> "IOSSerializedCursor":
        self._ensure_cursor()  # Recreate if needed on iOS
        logger.debug(f"[iOS_CURSOR] execute: {sql[:80]}...")
        with self._lock:
            try:
                if parameters is not None:
                    self._cursor.execute(sql, parameters)
                else:
                    self._cursor.execute(sql)
                logger.debug("[iOS_CURSOR] execute succeeded")
                return self
            except Exception as e:
                logger.error(f"[iOS_CURSOR] execute FAILED: {e}")
                raise

    def executemany(self, sql: str, seq_of_parameters: Any) -> "IOSSerializedCursor":
        logger.debug(f"[iOS_CURSOR] executemany: {sql[:80]}...")
        with self._lock:
            self._cursor.executemany(sql, seq_of_parameters)
            return self

    def _row_to_dict(self, row: Any) -> dict[str, Any] | None:
        """Convert sqlite3.Row to IOSDictRow for iOS compatibility.

        Returns an IOSDictRow that:
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
            # Return IOSDictRow that supports both string and integer access
            return IOSDictRow(string_dict, columns)
        # Fallback: try to get keys from the row itself if it's dict-like
        if hasattr(row, "keys"):
            return dict(row)
        # Last resort: log warning and return empty dict
        logger.warning("[iOS_CURSOR] _row_to_dict: no description and row has no keys()")
        return {}

    def fetchone(self) -> Any:
        if self._closed:
            logger.warning("[iOS_CURSOR] fetchone() called on closed cursor, returning None")
            return None
        logger.debug("[iOS_CURSOR] fetchone() called...")
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
                    logger.debug(f"[iOS_CURSOR] fetchone() result={result}, cursor closed")
                else:
                    logger.debug(f"[iOS_CURSOR] fetchone() succeeded: {result}")
                return result
            except Exception as e:
                logger.error(f"[iOS_CURSOR] fetchone() FAILED: {e}")
                raise

    def fetchall(self) -> Any:
        if self._closed:
            logger.warning("[iOS_CURSOR] fetchall() called on closed cursor, returning []")
            return []
        logger.debug("[iOS_CURSOR] fetchall() called...")
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
                    logger.debug(f"[iOS_CURSOR] fetchall() rows={len(result) if result else 0}, cursor closed")
                else:
                    logger.debug(f"[iOS_CURSOR] fetchall() succeeded: {len(result) if result else 0} rows")
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


class IOSSerializedConnection:
    """SQLite connection wrapper that serializes all access for iOS compatibility.

    iOS's debug SQLite has strict thread checking that causes assertion failures
    when connections are used from multiple threads, even with check_same_thread=False.
    This wrapper uses a global lock to serialize all database access.

    CRITICAL: cursor() returns a wrapped cursor so cursor.execute() also goes through lock.
    """

    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn
        self._lock = _get_ios_lock()
        logger.debug("[iOS_CONN] IOSSerializedConnection created")

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

    def cursor(self) -> IOSSerializedCursor:
        """Return a WRAPPED cursor that serializes all operations."""
        logger.debug("[iOS_CONN] cursor() called - creating wrapped cursor...")
        with self._lock:
            try:
                raw_cursor = self._conn.cursor()
                # Pass connection reference so cursor can be recreated on iOS
                wrapped = IOSSerializedCursor(raw_cursor, self._lock, self._conn)
                logger.debug("[iOS_CONN] cursor() succeeded, returning wrapped cursor")
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
        logger.debug("[iOS_CONN] close() called")
        with self._lock:
            self._conn.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __enter__(self) -> "IOSSerializedConnection":
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


def _resolve_db_path(db_path: Optional[str]) -> str:
    """Resolve the database path, checking test overrides and defaults."""
    if db_path is not None:
        return db_path

    logger.debug("[DB_CONNECT] db_path is None, resolving...")
    if _test_db_path is not None:
        logger.debug(f"[DB_CONNECT] Using test override path: {_test_db_path}")
        return _test_db_path

    logger.debug("[DB_CONNECT] Calling get_sqlite_db_full_path()...")
    resolved = get_sqlite_db_full_path()
    logger.debug(f"[DB_CONNECT] Resolved path: {resolved}")
    return resolved


class _IOSCursorProxy:
    """Proxy that prevents sqlite3_finalize() from running on the wrong thread.

    When Python GCs a sqlite3.Cursor, it calls sqlite3_finalize() which triggers
    Apple's libRPAC isBulkReadStatement assertion if the GC thread differs from
    the thread that called sqlite3_prepare(). This proxy suppresses __del__() and
    close() — the cursor's prepared statements get cleaned up when the connection
    itself is finalized (which only happens on the owning thread via thread-local).
    """

    __slots__ = ("_cursor",)

    def __init__(self, cursor: sqlite3.Cursor):
        object.__setattr__(self, "_cursor", cursor)

    def close(self) -> None:
        pass  # Suppress — let connection cleanup handle it

    def __del__(self) -> None:
        pass  # Suppress — prevents cross-thread sqlite3_finalize

    def __iter__(self) -> Any:
        return iter(object.__getattribute__(self, "_cursor"))

    def __next__(self) -> Any:
        return next(object.__getattribute__(self, "_cursor"))

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_cursor"), name)

    def execute(self, *args: Any, **kwargs: Any) -> "_IOSCursorProxy":
        object.__getattribute__(self, "_cursor").execute(*args, **kwargs)
        return self

    def executemany(self, *args: Any, **kwargs: Any) -> "_IOSCursorProxy":
        object.__getattribute__(self, "_cursor").executemany(*args, **kwargs)
        return self

    def fetchone(self) -> Any:
        return object.__getattribute__(self, "_cursor").fetchone()

    def fetchall(self) -> list[Any]:
        cursor = cast(sqlite3.Cursor, object.__getattribute__(self, "_cursor"))
        return cursor.fetchall()

    def fetchmany(self, size: int = -1) -> list[Any]:
        cursor = cast(sqlite3.Cursor, object.__getattribute__(self, "_cursor"))
        return cursor.fetchmany(size)

    @property
    def description(self) -> Any:
        return object.__getattribute__(self, "_cursor").description

    @property
    def rowcount(self) -> int:
        cursor = cast(sqlite3.Cursor, object.__getattribute__(self, "_cursor"))
        return cursor.rowcount

    @property
    def lastrowid(self) -> Any:
        return object.__getattribute__(self, "_cursor").lastrowid


class _IOSConnectionProxy:
    """Proxy that prevents callers from closing/finalizing connections AND cursors.

    Apple's libRPAC.dylib (SQLiteDatabaseTracking) asserts if sqlite3_finalize()
    is called from a different thread than sqlite3_open()/sqlite3_prepare().
    Python's GC can finalize Connection and Cursor objects on any thread.

    This proxy:
    - Suppresses Connection.close() and __del__()
    - Wraps all returned cursors in _IOSCursorProxy (suppresses Cursor.__del__())
    - Real objects live in thread-local storage, finalized only on owning thread
    """

    def __init__(self, conn: sqlite3.Connection):
        object.__setattr__(self, "_conn", conn)

    def close(self) -> None:
        pass

    def __del__(self) -> None:
        pass

    def __enter__(self) -> "_IOSConnectionProxy":
        return self

    def __exit__(self, *args: Any) -> None:
        pass

    def __getattr__(self, name: str) -> Any:
        return getattr(object.__getattribute__(self, "_conn"), name)

    def execute(self, *args: Any, **kwargs: Any) -> _IOSCursorProxy:
        conn = cast(sqlite3.Connection, object.__getattribute__(self, "_conn"))
        return _IOSCursorProxy(conn.execute(*args, **kwargs))

    def executemany(self, *args: Any, **kwargs: Any) -> _IOSCursorProxy:
        conn = cast(sqlite3.Connection, object.__getattribute__(self, "_conn"))
        return _IOSCursorProxy(conn.executemany(*args, **kwargs))

    def executescript(self, *args: Any, **kwargs: Any) -> _IOSCursorProxy:
        conn = cast(sqlite3.Connection, object.__getattribute__(self, "_conn"))
        return _IOSCursorProxy(conn.executescript(*args, **kwargs))

    def cursor(self) -> _IOSCursorProxy:
        conn = cast(sqlite3.Connection, object.__getattribute__(self, "_conn"))
        return _IOSCursorProxy(conn.cursor())

    def commit(self) -> None:
        object.__getattribute__(self, "_conn").commit()

    def rollback(self) -> None:
        object.__getattribute__(self, "_conn").rollback()

    @property
    def row_factory(self) -> Any:
        return object.__getattribute__(self, "_conn").row_factory

    @row_factory.setter
    def row_factory(self, value: Any) -> None:
        object.__getattribute__(self, "_conn").row_factory = value


def _create_sqlite_connection_ios(db_path: str) -> "_IOSConnectionProxy":
    """Create or reuse SQLite connection with iOS-specific settings.

    Returns a proxy that prevents callers from closing/finalizing the connection.
    The real connection lives in thread-local storage, ensuring sqlite3_finalize()
    only ever runs on the thread that called sqlite3_open() — satisfying Apple's
    libRPAC.dylib SQLiteDatabaseTracking assertions.
    """
    cache_attr = f"_sqlite_conn_{hash(db_path)}"
    cached: sqlite3.Connection | None = getattr(_ios_thread_local, cache_attr, None)

    if cached is not None:
        try:
            cached.execute("SELECT 1")
            logger.debug(f"[DB_CONNECT] iOS: reusing thread-local connection for {db_path}")
            return _IOSConnectionProxy(cached)
        except Exception:
            logger.debug("[DB_CONNECT] iOS: cached connection invalid, creating new one")
            # Don't close here — let it die with the thread

    logger.debug(f"[DB_CONNECT] iOS: creating new thread-local connection for {db_path}")
    try:
        conn = sqlite3.connect(
            db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
            isolation_level=None,
            timeout=30.0,
        )
        setattr(_ios_thread_local, cache_attr, conn)
        logger.debug(f"[DB_CONNECT] iOS: thread-local connection created and cached")
        return _IOSConnectionProxy(conn)
    except Exception as e:
        logger.error(f"[DB_CONNECT] sqlite3.connect FAILED: {e}")
        raise


def _get_pragma_statements(is_ios: bool, busy_timeout: Optional[int]) -> list[str]:
    """Get the appropriate PRAGMA statements for the platform."""
    if is_ios:
        return [
            "PRAGMA foreign_keys = ON;",
            "PRAGMA journal_mode=WAL;",
            f"PRAGMA busy_timeout = {busy_timeout if busy_timeout is not None else 30000};",
            "PRAGMA synchronous=NORMAL;",
        ]
    return [
        "PRAGMA foreign_keys = ON;",
        "PRAGMA journal_mode=WAL;",
        f"PRAGMA busy_timeout = {busy_timeout if busy_timeout is not None else 5000};",
    ]


def _execute_pragmas(conn: Any, adapter: Any, pragma_statements: list[str]) -> None:
    """Execute PRAGMA statements on the connection."""
    logger.debug(f"[DB_CONNECT] Executing {len(pragma_statements)} PRAGMA statements...")
    for pragma in pragma_statements:
        result = adapter.pragma(pragma)
        if result:
            logger.debug(f"[DB_CONNECT] Executing: {result}")
            try:
                conn.execute(result)
                logger.debug(f"[DB_CONNECT] PRAGMA succeeded: {result}")
            except Exception as e:
                logger.error(f"[DB_CONNECT] PRAGMA FAILED: {result} - {e}")
                raise


def get_db_connection(
    db_path: Optional[str] = None, busy_timeout: Optional[int] = None, enable_retry: bool = True
) -> Union[sqlite3.Connection, RetryConnection, Any]:
    """Open a stdlib sqlite3 connection for the bootstrap-layer schema init.

    Post-2.9.0 absorption: this function is consumed only by the bootstrap
    layer (initialize_database, run_migrations, retry.get_db_connection_with_retry,
    db.operations). PostgreSQL deployments route schema management through
    persist's Engine — this function rejects postgres:// DSNs.
    """
    db_path = _resolve_db_path(db_path)
    adapter = init_dialect(db_path)

    # PostgreSQL no longer wires through psycopg2 — persist's sqlx backend
    # owns the connection pool. The bootstrap layer's legacy schema is a
    # SQLite-only concern (a 2.8.x upgrade-path concept); fresh Postgres
    # deployments skip legacy CREATE TABLE entirely (see initialize_database).
    if adapter.is_postgresql():
        raise RuntimeError(
            "get_db_connection() does not support PostgreSQL after 2.9.0. "
            "Route through persist's Engine substrate instead."
        )

    _ensure_adapters_registered()
    is_ios = _check_ios_platform()
    conn: Union[_IOSConnectionProxy, sqlite3.Connection]
    if is_ios:
        conn = _create_sqlite_connection_ios(db_path)
    else:
        conn = sqlite3.connect(db_path, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)

    conn.row_factory = sqlite3.Row

    pragma_statements = _get_pragma_statements(is_ios, busy_timeout)
    _execute_pragmas(conn, adapter, pragma_statements)

    if enable_retry and not is_ios:
        return RetryConnection(cast(sqlite3.Connection, conn))
    return conn


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
    """Bootstrap the database for 2.9.0.

    Both SQLite and PostgreSQL deployments are owned end-to-end by
    ciris-persist's Engine: `_bootstrap_persist_engine` constructs the
    Engine (which runs persist's own sqlx migrations to create the
    `cirislens.*` / `cirisgraph.*` schema), then runs the A0a legacy
    graph migration once. There is no agent-side CREATE TABLE — persist's
    `run_legacy_graph_migration` (v1.6.4, CIRISPersist#70) reads any
    legacy 2.8.x `graph_nodes` / `graph_edges` over its own connection,
    and no-ops gracefully when those tables are absent (fresh install).
    """
    import traceback

    caller_info = "".join(traceback.format_stack()[-4:-1])
    logger.info(f"[DB_INIT] initialize_database called from:\n{caller_info}")

    try:
        if db_path is None:
            db_path = get_sqlite_db_full_path()
        logger.info(f"Initializing database via persist Engine: {db_path}")
        _bootstrap_persist_engine(db_path)
    except Exception as e:
        logger.exception(f"Database error during initialization: {e}")
        raise


def _persist_dsn_and_sentinel(db_path: str) -> Tuple[str, Optional[Path]]:
    """Resolve a db_path / database_url to (persist DSN, sentinel directory).

    Three supported forms — and crucially, a SQLite *URL* must never be run
    through Path().resolve(): that mangles the URL into a bogus filesystem
    path and silently bootstraps persist against the wrong (empty) database.

      - Postgres URL            -> used verbatim; sentinels in the data dir
      - SQLite URL (sqlite://)  -> used verbatim — the config schema
                                   documents sqlite://... as a valid
                                   database_url; sentinels anchored next to
                                   the db file
      - bare filesystem path    -> wrapped as sqlite:///<abs>; sentinels
                                   anchored beside the file
    """
    if db_path.startswith(("postgres://", "postgresql://")):
        from ciris_engine.logic.utils.path_resolution import get_data_dir

        return db_path, Path(get_data_dir())
    if db_path.startswith("sqlite:"):
        # SQLAlchemy form: sqlite:///rel/path (3 slashes -> relative) or
        # sqlite:////abs/path (4 slashes -> absolute). Splitting on
        # 'sqlite:///' keeps the right leading-slash count for Path().
        path_part = db_path.split("sqlite:///", 1)[-1] if "sqlite:///" in db_path else ""
        sentinel = Path(path_part).resolve().parent if path_part and path_part != ":memory:" else None
        return db_path, sentinel
    abs_path = Path(db_path).resolve()
    # `sqlite:///{abs_path}` where abs_path begins with '/' yields
    # 'sqlite:////absolute/path' — 4 slashes, absolute as required.
    return f"sqlite:///{abs_path}", abs_path.parent


def _bootstrap_persist_engine(db_path: Optional[str]) -> None:
    """Construct the ciris-persist Engine, run A0a migration if needed,
    and wire the engine into `persistence.models.graph` (2.9.0).

    Idempotent per-process: if an Engine is already wired, this is a
    no-op. Persist's Engine holds the tokio runtime + connection pool
    and is designed for one instance per process — tests that need
    multiple isolated DBs must explicitly call set_persist_engine()
    with their own Engine instance.

    Tolerant: if persist is unavailable or migration fails, logs the
    error but does not block startup. The agent will then hit the
    "engine not initialized" RuntimeError on the first persistence call,
    surfacing the problem loud rather than silently.
    """
    import os
    from pathlib import Path

    # Compute the expected DSN up front so we can decide whether to
    # re-wire. Production calls initialize_database() once per process
    # with the same db_path — second/third calls are no-ops. Tests
    # call it with a fresh temp_db each time — those re-wire.
    from ciris_engine.logic.persistence.models import graph as graph_persistence

    if db_path is None:
        _resolved_db_path = get_sqlite_db_full_path()
    else:
        _resolved_db_path = db_path
    if not isinstance(_resolved_db_path, str):
        _resolved_db_path = str(_resolved_db_path)
    # Same resolution the bootstrap below uses — so a sqlite:// URL produces
    # an _expected_dsn that actually matches and the idempotent-skip works.
    _expected_dsn = _persist_dsn_and_sentinel(_resolved_db_path)[0]

    if graph_persistence._engine is not None and graph_persistence._engine_dsn == _expected_dsn:
        logger.debug("persist engine already wired to %s, skipping re-bootstrap", _expected_dsn)
        return

    # Resolve the DSN. Postgres takes its own URL; SQLite uses
    # SQLAlchemy-style sqlite:// + (3 or 4 slashes).
    if db_path is None:
        db_path = get_sqlite_db_full_path()

    if not isinstance(db_path, str):
        db_path = str(db_path)

    # Postgres URL verbatim, sqlite:// URL verbatim, bare path -> sqlite:///.
    # See _persist_dsn_and_sentinel — a sqlite:// URL must not be resolved
    # as a filesystem path.
    dsn, sentinel_dir = _persist_dsn_and_sentinel(db_path)

    signing_key_id = os.environ.get("CIRIS_AGENT_ID", "ciris-agent-bootstrap")

    try:
        from ciris_persist import Engine  # type: ignore[import-untyped]
    except ImportError:
        logger.warning(
            "ciris-persist not importable; 2.9.0 absorption disabled. Pin ciris-persist>=1.6.4 in requirements.txt."
        )
        return

    # Test isolation only: under pytest, fixtures routinely bootstrap a
    # fresh per-test engine, and a single test may invoke more than one
    # engine-wiring fixture. ciris-persist's process-singleton rejects a
    # second construction with a different config — so un-pin the current
    # engine first via reset_engine() (handle-free; CIRISPersist#88). We
    # only reach here when the idempotent-skip above did NOT fire, i.e. a
    # genuinely different config is being bootstrapped. Gated strictly on
    # PYTEST_CURRENT_TEST: in production a second differing config is a
    # real bug and persist's EngineConfigMismatch guardrail must still
    # fire untouched.
    if os.environ.get("PYTEST_CURRENT_TEST"):
        try:
            from ciris_persist import reset_engine

            reset_engine()
        except Exception:  # noqa: BLE001 - best-effort test teardown
            pass
        graph_persistence._engine = None
        graph_persistence._engine_dsn = None

    try:
        engine = Engine(dsn, signing_key_id)
    except Exception as e:
        # iOS: flock() returns EPERM in the sandbox. Single-process mobile app
        # has no multi-agent risk. Delete any stale lock file and retry once.
        if "operation not permitted" in str(e).lower() or "lock" in str(e).lower():
            is_ios = sys.platform == "ios" or (
                sys.platform == "darwin"
                and hasattr(sys, "implementation")
                and "iphoneos" in getattr(sys.implementation, "_multiarch", "").lower()
            )
            if is_ios:
                logger.warning("iOS: Engine bootstrap lock failed (%s) — clearing stale locks and retrying", e)
                # Remove any stale lock/WAL files that may be blocking
                import glob

                for pattern in [f"{db_path}*-lock", f"{db_path}-journal"]:
                    for lock_file in glob.glob(pattern):
                        try:
                            Path(lock_file).unlink()
                            logger.info("Removed stale lock: %s", lock_file)
                        except OSError as unlink_err:
                            logger.debug("Could not remove stale lock %s: %s", lock_file, unlink_err)
                # Retry with fresh state
                try:
                    from ciris_persist import reset_engine

                    reset_engine()
                except Exception as reset_err:
                    logger.debug("reset_engine() before retry failed (non-fatal): %s", reset_err)
                engine = Engine(dsn, signing_key_id)
            else:
                raise
        else:
            raise
    logger.info("ciris-persist Engine constructed (dsn=%s)", dsn)

    # A0a graph migration + A0b audit bridge. Both run once, sentinel-gated.
    if sentinel_dir is not None:
        # A0a: copy legacy graph_nodes/graph_edges → cirisgraph.* . Persist
        # owns the whole operation since v1.6.4 (CIRISPersist#70) — it reads
        # the legacy schema over its own connection (SQLite *and* Postgres),
        # so the agent ships zero raw SQL for the upgrade path. Idempotent
        # and tolerant of legacy-tables-absent on fresh installs.
        sentinel = sentinel_dir / ".persist_migrated"
        if not sentinel.exists():
            try:
                import json as _json

                logger.info("A0a migration sentinel absent — running legacy graph migration")
                raw = engine.run_legacy_graph_migration(_json.dumps({"dry_run": False}))
                stats = _json.loads(raw) if isinstance(raw, (bytes, str)) else raw
                if stats.get("outcome") in ("ok", "partial") and stats.get("errors", 0) == 0:
                    sentinel.write_text(
                        f'{{"nodes_written":{stats.get("nodes_written", 0)},'
                        f'"edges_written":{stats.get("edges_written", 0)}}}'
                    )
                    logger.info(
                        "A0a migration complete: %d nodes, %d edges "
                        "(skipped: %d already-present, %d too-large; "
                        "%d dangling-FK edges)",
                        stats.get("nodes_written", 0),
                        stats.get("edges_written", 0),
                        stats.get("nodes_skipped_already_present", 0),
                        stats.get("nodes_skipped_too_large", 0),
                        stats.get("edges_skipped_dangling_fk", 0),
                    )
                else:
                    logger.error(
                        "A0a migration outcome=%s errors=%d; sentinel NOT written",
                        stats.get("outcome"),
                        stats.get("errors", 0),
                    )
            except Exception:
                logger.exception("A0a migration failed; persist engine wired anyway")

        # 2.9.0 A0b: bridge the legacy audit chain into persist's
        # cirislens_audit_log. Sentinel-gated like A0a; runs once on
        # first 2.9.0 boot. Tolerant: if CIRISVerify isn't ready yet
        # (early-boot ordering) or if the legacy audit DB is absent
        # (fresh deployment with no legacy chain), log + skip.
        audit_sentinel = sentinel_dir / ".audit_bridged"
        # Resolve the legacy audit DB from config (database.audit_db) so a
        # deployment that customised audit_db still bridges its chain —
        # don't assume the default sentinel_dir/ciris_audit.db location.
        try:
            legacy_audit_db = Path(get_audit_db_full_path())
        except Exception:  # pragma: no cover - defensive
            legacy_audit_db = sentinel_dir / "ciris_audit.db"
        if not audit_sentinel.exists() and legacy_audit_db.exists():
            try:
                # Bundled under ciris_engine/ so the in-place upgrade path is
                # reachable from Chaquopy on Android too — tools/ isn't in
                # the mobile extractPackages list (CIRISAgent#780).
                from ciris_engine.logic.audit.chain_bridge import run as run_bridge

                logger.info("A0b audit-bridge sentinel absent — running chain bridge")
                result = run_bridge(
                    engine_db=Path(db_path),
                    audit_db=legacy_audit_db,
                    dry_run=False,
                    engine=engine,
                )
                audit_sentinel.write_text(
                    f'{{"bridge_id":"{result.bridge_id}",'
                    f'"legacy_terminal_seq":{result.legacy_terminal_seq},'
                    f'"legacy_db_sha256":"{result.legacy_db_sha256}"}}'
                )
                logger.info(
                    "A0b audit bridge complete: legacy_seq=%d bridge_id=%s",
                    result.legacy_terminal_seq,
                    result.bridge_id,
                )
            except Exception:
                # CIRISVerify availability + signing-key access are
                # ordering-sensitive at boot; we don't block startup on
                # bridge failure. Next boot retries (sentinel absent).
                logger.exception("A0b audit bridge failed; persist engine wired anyway")
        elif not legacy_audit_db.exists():
            logger.debug(
                "no legacy audit DB at %s — fresh deployment, no chain to bridge",
                legacy_audit_db,
            )

    # Wire the engine into persistence.models.graph.
    from ciris_engine.logic.persistence.models import graph as graph_persistence

    graph_persistence.set_persist_engine(engine, dsn)
