import logging
import sqlite3
import time
import types
from datetime import datetime
from typing import Any, Dict, Optional, TypedDict, Union

from ciris_engine.logic.config.db_paths import get_sqlite_db_full_path
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
    # Default to SQLite for backward compatibility
    if db_path is None:
        # Check for test override first
        if _test_db_path is not None:
            db_path = _test_db_path
        else:
            db_path = get_sqlite_db_full_path()

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
    _ensure_adapters_registered()

    conn = sqlite3.connect(db_path, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row

    # Apply SQLite PRAGMA directives
    pragma_statements = [
        "PRAGMA foreign_keys = ON;",
        "PRAGMA journal_mode=WAL;",
        f"PRAGMA busy_timeout = {busy_timeout if busy_timeout is not None else 5000};",
    ]

    for pragma in pragma_statements:
        result = adapter.pragma(pragma)
        if result:  # Only execute if dialect returns a statement
            conn.execute(result)

    # Return wrapped connection with retry logic by default
    if enable_retry:
        return RetryConnection(conn)

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
