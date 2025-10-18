"""
Database dialect adapter for SQLite and PostgreSQL compatibility.

Provides lightweight SQL translation to support both SQLite and PostgreSQL
backends with a single connection string configuration.
"""

from enum import Enum
from typing import Optional
from urllib.parse import urlparse


class Dialect(str, Enum):
    """Supported database dialects."""

    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"


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
        parsed = urlparse(connection_string)

        # Detect dialect from URL scheme
        if parsed.scheme in ("sqlite", "sqlite3", ""):
            self.dialect = Dialect.SQLITE
            # For SQLite, store the path (with or without leading //)
            self.db_path = parsed.path or connection_string
            self.db_url = connection_string
        elif parsed.scheme in ("postgresql", "postgres"):
            self.dialect = Dialect.POSTGRESQL
            self.db_url = connection_string
            self.db_path = None
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
                expr = f"{expr}->>>'{part}'"
            else:
                # Intermediate: keep as JSONB
                expr = f"{expr}->'{part}'"

        return expr

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
