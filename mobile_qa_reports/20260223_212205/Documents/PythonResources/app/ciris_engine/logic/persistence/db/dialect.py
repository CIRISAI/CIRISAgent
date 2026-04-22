"""
Database dialect adapter for SQLite and PostgreSQL compatibility.

Provides lightweight SQL translation to support both SQLite and PostgreSQL
backends with a single connection string configuration.
"""

from enum import Enum
from typing import TYPE_CHECKING, Any, Optional
from urllib.parse import unquote, urlparse

if TYPE_CHECKING:
    from ciris_engine.logic.persistence.db.query_builder import QueryBuilder


class Dialect(str, Enum):
    """Supported database dialects."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


def parse_postgres_url(url: str) -> tuple[str, str, str, int, str, str, str]:
    """Parse PostgreSQL URL handling special characters in password.

    Handles passwords with special characters (@, }, ], {, etc.) that break urlparse.

    Args:
        url: PostgreSQL connection string

    Returns:
        Tuple of (scheme, username, password, port, host, database, params)

    Raises:
        ValueError: If URL format is invalid
    """
    import re

    # Pattern: postgresql://username:password@host:port/database?params
    # Password may contain special chars INCLUDING @, so we need to parse carefully
    # The password is everything after the first : and before the LAST @
    # Use non-greedy match for scheme/user, greedy for password (can contain @ or be empty)
    pattern = r"^(postgres(?:ql)?):\/\/([^:]+):(.*)@([^:\/\?]+):(\d+)\/([^?]+)(\?.*)?$"
    match = re.match(pattern, url)

    if not match:
        raise ValueError(f"Invalid PostgreSQL URL format: {url}")

    scheme, username, password_and_host, host, port, database, params = match.groups()

    # Now we need to split password from host at the LAST @
    # Find the last @ that's followed by host:port pattern
    # The host part should not contain @ (it's the part after the last @)
    last_at_idx = password_and_host.rfind("@")
    if last_at_idx == -1:
        # No @ found - this means password_and_host is just the password (empty host captured)
        password = password_and_host
    else:
        # Split at the last @
        password = password_and_host[:last_at_idx]
        # The part after @ should match our captured host
        rest = password_and_host[last_at_idx + 1 :]
        if rest != host:
            # Host mismatch - means our regex didn't capture correctly
            # Fall back to treating everything as password
            password = password_and_host

    # URL-decode the password component (handles %XX encoding)
    password = unquote(password) if password else ""
    params = params or ""

    return scheme, username, password, int(port), host, database, params


class DialectAdapter:
    """Translates SQL between SQLite and PostgreSQL dialects.

    This lightweight adapter enables the CIRIS persistence layer to work
    with both SQLite (development/small deployments) and PostgreSQL
    (production/scale) without code changes.

    Design Philosophy:
    - Minimal abstraction (no ORM overhead)
    - Strategic translation of 5 key patterns
    - Backward compatible (SQLite default)
    - Connection string determines dialect
    """

    def __init__(self, connection_string: str):
        """Initialize adapter from connection string.

        Args:
            connection_string: Database URL (sqlite://path or postgresql://...)
        """
        # Quick check for PostgreSQL scheme
        if connection_string.startswith(("postgresql://", "postgres://")):
            # Use robust parser that handles special characters in passwords
            try:
                _scheme, _user, _password, _port, _host, _database, _params = parse_postgres_url(connection_string)
                self.dialect = Dialect.POSTGRESQL
                self.db_url = connection_string
                self.db_path = ""  # Empty string for PostgreSQL (not a file path)
            except ValueError as e:
                # Fall back to urlparse if custom parser fails
                import logging

                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to parse PostgreSQL URL with custom parser: {e}")
                logger.warning("Falling back to standard urlparse - may fail with special chars in password")

                parsed = urlparse(connection_string)
                self.dialect = Dialect.POSTGRESQL
                self.db_url = connection_string
                self.db_path = ""
        else:
            # Use standard urlparse for SQLite and other schemes
            parsed = urlparse(connection_string)

            if parsed.scheme in ("sqlite", "sqlite3", ""):
                self.dialect = Dialect.SQLITE
                # For SQLite, store the path (with or without leading //)
                self.db_path = parsed.path or connection_string
                self.db_url = connection_string
            else:
                # Default to SQLite for backward compatibility
                self.dialect = Dialect.SQLITE
                self.db_path = connection_string
                self.db_url = connection_string

    def upsert(
        self,
        table: str,
        columns: list[str],
        conflict_columns: list[str],
        update_columns: Optional[list[str]] = None,
    ) -> str:
        """Generate UPSERT statement for the target dialect.

        Translates INSERT OR REPLACE (SQLite) to INSERT ... ON CONFLICT (Postgres).

        Args:
            table: Table name
            columns: All column names to insert
            conflict_columns: Columns that define uniqueness constraint
            update_columns: Columns to update on conflict (defaults to all non-conflict columns)

        Returns:
            Dialect-specific UPSERT SQL statement
        """
        if update_columns is None:
            # Update all columns except conflict columns
            update_columns = [col for col in columns if col not in conflict_columns]

        placeholders = ", ".join([self.placeholder()] * len(columns))
        columns_str = ", ".join(columns)

        if self.dialect == Dialect.SQLITE:
            # SQLite: INSERT OR REPLACE
            return f"""
INSERT OR REPLACE INTO {table}
({columns_str})
VALUES ({placeholders})
"""

        # PostgreSQL: INSERT ... ON CONFLICT ... DO UPDATE
        conflict_str = ", ".join(conflict_columns)
        updates = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_columns])

        return f"""
INSERT INTO {table}
({columns_str})
VALUES ({placeholders})
ON CONFLICT ({conflict_str})
DO UPDATE SET {updates}
"""

    def json_extract(self, column: str, json_path: str) -> str:
        """Generate JSON field extraction for the target dialect.

        Translates json_extract() (SQLite) to JSONB operators (Postgres).

        Args:
            column: Column name containing JSON
            json_path: JSON path ($.field.subfield)

        Returns:
            Dialect-specific JSON extraction expression
        """
        if self.dialect == Dialect.SQLITE:
            # SQLite: json_extract(column, '$.path')
            return f"json_extract({column}, '{json_path}')"

        # PostgreSQL: column->'field'->>'subfield' or column->>'field'
        # Convert $.field.subfield to JSONB path
        path_parts = json_path.lstrip("$").strip(".").split(".")

        if not path_parts or not path_parts[0]:
            return f"{column}"

        # Build JSONB accessor chain
        # All intermediate paths use -> (returns JSONB)
        # Final path uses ->> (returns text)
        expr = column
        for i, part in enumerate(path_parts):
            if i == len(path_parts) - 1:
                # Last element: extract as text
                expr = f"{expr}->>'{part}'"
            else:
                # Intermediate: keep as JSONB
                expr = f"{expr}->'{part}'"

        return expr

    def insert_or_ignore(self, table: str, columns: list[str], conflict_columns: Optional[list[str]] = None) -> str:
        """Generate INSERT OR IGNORE statement for the target dialect.

        Args:
            table: Table name
            columns: Column names to insert
            conflict_columns: Columns that define uniqueness (required for PostgreSQL)

        Returns:
            Dialect-specific INSERT OR IGNORE SQL statement
        """
        placeholders = ", ".join(["?"] * len(columns))
        columns_str = ", ".join(columns)

        if self.dialect == Dialect.SQLITE:
            # SQLite: INSERT OR IGNORE
            return f"INSERT OR IGNORE INTO {table} ({columns_str}) VALUES ({placeholders})"

        # PostgreSQL: INSERT ... ON CONFLICT DO NOTHING
        # Requires conflict columns to be specified
        if not conflict_columns:
            # If no conflict columns specified, use all columns
            conflict_columns = columns

        conflict_str = ", ".join(conflict_columns)
        return f"INSERT INTO {table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT ({conflict_str}) DO NOTHING"

    def pragma(self, statement: str) -> Optional[str]:
        """Handle PRAGMA statements (SQLite-specific).

        Args:
            statement: PRAGMA statement

        Returns:
            Statement for SQLite, None for PostgreSQL
        """
        if self.dialect == Dialect.SQLITE:
            return statement
        # PostgreSQL doesn't use PRAGMA - return None to skip
        return None

    def placeholder(self) -> str:
        """Return parameter placeholder for the target dialect.

        Returns:
            '?' for SQLite, '%s' for PostgreSQL
        """
        if self.dialect == Dialect.SQLITE:
            return "?"
        return "%s"

    def is_sqlite(self) -> bool:
        """Check if using SQLite dialect."""
        return self.dialect == Dialect.SQLITE

    def is_postgresql(self) -> bool:
        """Check if using PostgreSQL dialect."""
        return self.dialect == Dialect.POSTGRESQL

    def translate_placeholders(self, sql: str) -> str:
        """Translate SQLite '?' placeholders to PostgreSQL '%s' placeholders."""
        if not self.is_postgresql():
            return sql
        # Replace ? with %s for PostgreSQL
        translated = sql.replace("?", "%s")
        if "?" in sql:
            import logging

            logger = logging.getLogger(__name__)
            logger.debug(f"DEBUG translate_placeholders: {sql[:100]}... -> {translated[:100]}...")
        return translated

    def extract_scalar(self, row: Optional[Any]) -> Optional[Any]:
        """Extract scalar value from cursor fetchone() result.

        Handles differences between SQLite and PostgreSQL row objects.

        Args:
            row: Result from cursor.fetchone()

        Returns:
            First column value from the row, or None if row is None

        Note:
            - SQLite: Row objects support both integer and dict-like indexing
            - PostgreSQL: Row objects may only support dict-like indexing
        """
        if row is None:
            return None

        # Try integer indexing first (works for SQLite and some PostgreSQL drivers)
        try:
            return row[0]
        except (KeyError, TypeError):
            # Fall back to dict-like access for PostgreSQL
            # Get first column name and access by key
            if hasattr(row, "keys"):
                keys = row.keys()
                if keys:
                    # Convert keys to list since dict_keys/odict_keys don't support indexing
                    return row[list(keys)[0]]
            return None

    def get_query_builder(self) -> "QueryBuilder":
        """Get a query builder for this dialect.

        Returns:
            QueryBuilder instance configured for this dialect
        """
        from ciris_engine.logic.persistence.db.query_builder import QueryBuilder

        return QueryBuilder(self)

    def insert_ignore_node_sql(self) -> str:
        """Get INSERT OR IGNORE SQL for graph_nodes.

        Handles dialect-specific conflict resolution for the graph_nodes table.
        Uses PRIMARY KEY constraint (node_id, scope).

        Returns:
            SQL string with ? placeholders (will be translated by cursor wrapper)
        """
        return self.get_query_builder().insert_ignore_node()

    def insert_ignore_edge_sql(self) -> str:
        """Get INSERT OR IGNORE SQL for graph_edges.

        Handles dialect-specific conflict resolution for the graph_edges table.
        Uses PRIMARY KEY constraint (edge_id).

        Returns:
            SQL string with ? placeholders (will be translated by cursor wrapper)
        """
        return self.get_query_builder().insert_ignore_edge()


# Global adapter instance
_adapter: Optional[DialectAdapter] = None


def init_dialect(connection_string: str = "data/ciris.db") -> DialectAdapter:
    """Initialize global dialect adapter.

    Args:
        connection_string: Database URL (defaults to SQLite for backward compatibility)

    Returns:
        Initialized DialectAdapter instance
    """
    global _adapter
    _adapter = DialectAdapter(connection_string)
    return _adapter


def get_adapter() -> DialectAdapter:
    """Get global dialect adapter instance.

    Returns:
        Global DialectAdapter instance

    Raises:
        RuntimeError: If adapter not initialized
    """
    if _adapter is None:
        # Auto-initialize with SQLite default for backward compatibility
        return init_dialect()
    return _adapter
