"""
Database-agnostic query builder with dialect support.

Provides a fluent interface for building SQL queries that automatically
adapt to the target dialect (SQLite, PostgreSQL, MySQL, etc.).

This module centralizes all SQL generation logic, making it easy to:
1. Add support for new database backends
2. Test SQL generation without a database
3. Keep business logic free of SQL dialect knowledge
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from ciris_engine.logic.persistence.db.dialect import DialectAdapter


class ConflictResolution(str, Enum):
    """How to handle conflicts during INSERT operations."""

    IGNORE = "ignore"  # INSERT OR IGNORE / ON CONFLICT DO NOTHING
    REPLACE = "replace"  # INSERT OR REPLACE / ON CONFLICT DO UPDATE
    ERROR = "error"  # Let database raise error (default behavior)


@dataclass
class InsertQuery:
    """Builder for INSERT statements with dialect awareness.

    Examples:
        >>> query = InsertQuery(
        ...     table="users",
        ...     columns=["id", "name", "email"],
        ...     conflict_resolution=ConflictResolution.IGNORE,
        ...     conflict_columns=["id"]
        ... )
        >>> sql = query.to_sql(adapter)
    """

    table: str
    columns: List[str]
    values_placeholder: bool = True  # Use ? placeholders
    conflict_resolution: ConflictResolution = ConflictResolution.ERROR
    conflict_columns: Optional[List[str]] = None  # For ON CONFLICT
    update_columns: Optional[List[str]] = None  # For ON CONFLICT DO UPDATE

    def to_sql(self, adapter: "DialectAdapter") -> str:
        """Generate SQL for the target dialect.

        Args:
            adapter: Dialect adapter to use for SQL generation

        Returns:
            SQL string with ? placeholders (will be translated by cursor wrapper)
        """
        from ciris_engine.logic.persistence.db.dialect import Dialect

        placeholders = ", ".join(["?"] * len(self.columns))
        columns_str = ", ".join(self.columns)

        if self.conflict_resolution == ConflictResolution.IGNORE:
            if adapter.dialect == Dialect.SQLITE:
                return f"INSERT OR IGNORE INTO {self.table} ({columns_str}) VALUES ({placeholders})"
            else:  # PostgreSQL
                conflict_cols = ", ".join(self.conflict_columns or self.columns)
                return f"INSERT INTO {self.table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT ({conflict_cols}) DO NOTHING"

        elif self.conflict_resolution == ConflictResolution.REPLACE:
            if adapter.dialect == Dialect.SQLITE:
                return f"INSERT OR REPLACE INTO {self.table} ({columns_str}) VALUES ({placeholders})"
            else:  # PostgreSQL
                conflict_cols = ", ".join(self.conflict_columns or self.columns)
                update_cols = self.update_columns or [c for c in self.columns if c not in (self.conflict_columns or [])]
                updates = ", ".join([f"{col} = EXCLUDED.{col}" for col in update_cols])
                return f"INSERT INTO {self.table} ({columns_str}) VALUES ({placeholders}) ON CONFLICT ({conflict_cols}) DO UPDATE SET {updates}"

        # ERROR (default)
        return f"INSERT INTO {self.table} ({columns_str}) VALUES ({placeholders})"


@dataclass
class SelectQuery:
    """Builder for SELECT statements with dialect awareness.

    Examples:
        >>> query = SelectQuery(
        ...     table="users",
        ...     columns=["id", "name"],
        ...     where_conditions=["active = ?"],
        ...     order_by="created_at DESC",
        ...     limit=10
        ... )
        >>> sql = query.to_sql(adapter)
    """

    table: str
    columns: List[str]
    where_conditions: List[str] = field(default_factory=list)
    order_by: Optional[str] = None
    limit: Optional[int] = None

    def to_sql(self, adapter: "DialectAdapter") -> str:
        """Generate SQL for the target dialect.

        Args:
            adapter: Dialect adapter to use for SQL generation

        Returns:
            SQL string with ? placeholders (will be translated by cursor wrapper)
        """
        cols = ", ".join(self.columns)
        sql = f"SELECT {cols} FROM {self.table}"

        if self.where_conditions:
            sql += " WHERE " + " AND ".join(self.where_conditions)

        if self.order_by:
            sql += f" ORDER BY {self.order_by}"

        if self.limit:
            sql += f" LIMIT {self.limit}"

        return sql


class QueryBuilder:
    """Factory for creating dialect-aware queries.

    This class provides high-level methods for common query patterns,
    automatically handling dialect-specific SQL generation.

    Examples:
        >>> from ciris_engine.logic.persistence.db.dialect import get_adapter
        >>> adapter = get_adapter()
        >>> builder = QueryBuilder(adapter)
        >>> sql = builder.insert_ignore_node()
    """

    def __init__(self, adapter: "DialectAdapter"):
        """Initialize query builder with dialect adapter.

        Args:
            adapter: Dialect adapter for SQL generation
        """
        self.adapter = adapter

    def insert(
        self,
        table: str,
        columns: List[str],
        conflict_resolution: ConflictResolution = ConflictResolution.ERROR,
        conflict_columns: Optional[List[str]] = None,
    ) -> InsertQuery:
        """Create an INSERT query builder.

        Args:
            table: Table name
            columns: List of column names
            conflict_resolution: How to handle conflicts
            conflict_columns: Columns that define uniqueness constraint

        Returns:
            InsertQuery builder
        """
        return InsertQuery(
            table=table, columns=columns, conflict_resolution=conflict_resolution, conflict_columns=conflict_columns
        )

    def select(self, table: str, columns: List[str]) -> SelectQuery:
        """Create a SELECT query builder.

        Args:
            table: Table name
            columns: List of column names to select

        Returns:
            SelectQuery builder
        """
        return SelectQuery(table=table, columns=columns)

    def insert_ignore_node(self) -> str:
        """Create INSERT OR IGNORE for graph_nodes with proper conflict handling.

        Handles the PRIMARY KEY constraint (node_id, scope) correctly for both dialects.

        Returns:
            SQL string ready for execution (with ? placeholders)
        """
        query = self.insert(
            table="graph_nodes",
            columns=[
                "node_id",
                "scope",
                "node_type",
                "attributes_json",
                "version",
                "updated_by",
                "updated_at",
                "created_at",
            ],
            conflict_resolution=ConflictResolution.IGNORE,
            conflict_columns=["node_id", "scope"],  # PRIMARY KEY
        )
        return query.to_sql(self.adapter)

    def insert_ignore_edge(self) -> str:
        """Create INSERT OR IGNORE for graph_edges with proper conflict handling.

        Handles the PRIMARY KEY constraint (edge_id) correctly for both dialects.

        Returns:
            SQL string ready for execution (with ? placeholders)
        """
        query = self.insert(
            table="graph_edges",
            columns=[
                "edge_id",
                "source_node_id",
                "target_node_id",
                "scope",
                "relationship",
                "weight",
                "attributes_json",
                "created_at",
            ],
            conflict_resolution=ConflictResolution.IGNORE,
            conflict_columns=["edge_id"],  # PRIMARY KEY
        )
        return query.to_sql(self.adapter)
