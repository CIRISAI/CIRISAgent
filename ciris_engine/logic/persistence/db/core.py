import logging
import sqlite3
import time
from datetime import datetime
from typing import Any, Optional, Union

from ciris_engine.logic.config.db_paths import get_sqlite_db_full_path
from ciris_engine.schemas.persistence.tables import AUDIT_LOG_TABLE_V1 as audit_log_table_v1
from ciris_engine.schemas.persistence.tables import AUDIT_ROOTS_TABLE_V1 as audit_roots_table_v1
from ciris_engine.schemas.persistence.tables import AUDIT_SIGNING_KEYS_TABLE_V1 as audit_signing_keys_table_v1
from ciris_engine.schemas.persistence.tables import FEEDBACK_MAPPINGS_TABLE_V1 as feedback_mappings_table_v1
from ciris_engine.schemas.persistence.tables import GRAPH_EDGES_TABLE_V1 as graph_edges_table_v1
from ciris_engine.schemas.persistence.tables import GRAPH_NODES_TABLE_V1 as graph_nodes_table_v1
from ciris_engine.schemas.persistence.tables import SERVICE_CORRELATIONS_TABLE_V1 as service_correlations_table_v1
from ciris_engine.schemas.persistence.tables import TASKS_TABLE_V1 as tasks_table_v1
from ciris_engine.schemas.persistence.tables import THOUGHTS_TABLE_V1 as thoughts_table_v1
from ciris_engine.schemas.persistence.tables import WA_CERT_TABLE_V1 as wa_cert_table_v1

from .migration_runner import run_migrations
from .retry import DEFAULT_BASE_DELAY, DEFAULT_MAX_DELAY, DEFAULT_MAX_RETRIES, is_retryable_error

logger = logging.getLogger(__name__)


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
            return self._conn.executescript(*args, **kwargs)  # type: ignore[no-any-return]
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
) -> Union[sqlite3.Connection, RetryConnection]:
    """Establishes a connection to the SQLite database with foreign key support.

    Args:
        db_path: Optional path to database file
        busy_timeout: Optional busy timeout in milliseconds (e.g., 5000 for 5 seconds)
        enable_retry: Enable automatic retry for write operations (default: True)

    Returns:
        SQLite connection with row factory and foreign keys enabled.
        By default, returns a RetryConnection that automatically retries write operations.
    """
    # Ensure adapters are registered before creating connection
    _ensure_adapters_registered()

    if db_path is None:
        db_path = get_sqlite_db_full_path()
    conn = sqlite3.connect(db_path, check_same_thread=False, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")

    # Enable WAL mode for better concurrency
    conn.execute("PRAGMA journal_mode=WAL;")

    # Set busy timeout if specified (also used as a fallback)
    if busy_timeout is not None:
        conn.execute(f"PRAGMA busy_timeout = {busy_timeout};")
    else:
        # Default 5 second busy timeout as a fallback
        conn.execute("PRAGMA busy_timeout = 5000;")

    # Return wrapped connection with retry logic by default
    if enable_retry:
        return RetryConnection(conn)

    return conn


# Removed unused schema getter functions - only graph schemas are used


def get_graph_nodes_table_schema_sql() -> str:
    return graph_nodes_table_v1


def get_graph_edges_table_schema_sql() -> str:
    return graph_edges_table_v1


def get_service_correlations_table_schema_sql() -> str:
    return service_correlations_table_v1


def initialize_database(db_path: Optional[str] = None) -> None:
    """Initialize the database with base schema and apply migrations."""
    try:
        with get_db_connection(db_path) as conn:
            base_tables = [
                tasks_table_v1,
                thoughts_table_v1,
                feedback_mappings_table_v1,
                graph_nodes_table_v1,
                graph_edges_table_v1,
                service_correlations_table_v1,
                audit_log_table_v1,
                audit_roots_table_v1,
                audit_signing_keys_table_v1,
                wa_cert_table_v1,
            ]

            for table_sql in base_tables:
                conn.executescript(table_sql)

            conn.commit()

        run_migrations(db_path)

        logger.info(f"Database initialized at {db_path or get_sqlite_db_full_path()}")
    except sqlite3.Error as e:
        logger.exception(f"Database error during initialization: {e}")
        raise
