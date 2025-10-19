"""
Unit tests for the database query builder.

Tests dialect-aware SQL generation for SQLite and PostgreSQL.
"""

import pytest

from ciris_engine.logic.persistence.db.dialect import Dialect, DialectAdapter
from ciris_engine.logic.persistence.db.query_builder import (
    ConflictResolution,
    InsertQuery,
    QueryBuilder,
    SelectQuery,
)


class TestInsertQuery:
    """Test InsertQuery SQL generation."""

    def test_insert_simple_sqlite(self):
        """Test simple INSERT for SQLite."""
        adapter = DialectAdapter("sqlite:///test.db")
        query = InsertQuery(
            table="users",
            columns=["id", "name", "email"],
        )
        sql = query.to_sql(adapter)

        assert "INSERT INTO users" in sql
        assert "(id, name, email)" in sql
        assert "VALUES (?, ?, ?)" in sql
        assert "OR IGNORE" not in sql
        assert "ON CONFLICT" not in sql

    def test_insert_simple_postgresql(self):
        """Test simple INSERT for PostgreSQL."""
        adapter = DialectAdapter("postgresql://localhost/test")
        query = InsertQuery(
            table="users",
            columns=["id", "name", "email"],
        )
        sql = query.to_sql(adapter)

        assert "INSERT INTO users" in sql
        assert "(id, name, email)" in sql
        assert "VALUES (?, ?, ?)" in sql
        assert "OR IGNORE" not in sql
        assert "ON CONFLICT" not in sql

    def test_insert_ignore_sqlite(self):
        """Test INSERT OR IGNORE for SQLite."""
        adapter = DialectAdapter("sqlite:///test.db")
        query = InsertQuery(
            table="users",
            columns=["id", "name", "email"],
            conflict_resolution=ConflictResolution.IGNORE,
            conflict_columns=["id"],
        )
        sql = query.to_sql(adapter)

        assert "INSERT OR IGNORE INTO users" in sql
        assert "(id, name, email)" in sql
        assert "VALUES (?, ?, ?)" in sql
        assert "ON CONFLICT" not in sql

    def test_insert_ignore_postgresql(self):
        """Test INSERT ... ON CONFLICT DO NOTHING for PostgreSQL."""
        adapter = DialectAdapter("postgresql://localhost/test")
        query = InsertQuery(
            table="users",
            columns=["id", "name", "email"],
            conflict_resolution=ConflictResolution.IGNORE,
            conflict_columns=["id"],
        )
        sql = query.to_sql(adapter)

        assert "INSERT INTO users" in sql
        assert "(id, name, email)" in sql
        assert "VALUES (?, ?, ?)" in sql
        assert "ON CONFLICT (id) DO NOTHING" in sql

    def test_insert_ignore_postgresql_composite_key(self):
        """Test INSERT with composite primary key for PostgreSQL."""
        adapter = DialectAdapter("postgresql://localhost/test")
        query = InsertQuery(
            table="graph_nodes",
            columns=["node_id", "scope", "node_type", "attributes_json"],
            conflict_resolution=ConflictResolution.IGNORE,
            conflict_columns=["node_id", "scope"],
        )
        sql = query.to_sql(adapter)

        assert "INSERT INTO graph_nodes" in sql
        assert "ON CONFLICT (node_id, scope) DO NOTHING" in sql

    def test_insert_replace_sqlite(self):
        """Test INSERT OR REPLACE for SQLite."""
        adapter = DialectAdapter("sqlite:///test.db")
        query = InsertQuery(
            table="users",
            columns=["id", "name", "email", "updated_at"],
            conflict_resolution=ConflictResolution.REPLACE,
            conflict_columns=["id"],
            update_columns=["name", "email", "updated_at"],
        )
        sql = query.to_sql(adapter)

        assert "INSERT OR REPLACE INTO users" in sql
        assert "(id, name, email, updated_at)" in sql
        assert "VALUES (?, ?, ?, ?)" in sql

    def test_insert_replace_postgresql(self):
        """Test INSERT ... ON CONFLICT DO UPDATE for PostgreSQL."""
        adapter = DialectAdapter("postgresql://localhost/test")
        query = InsertQuery(
            table="users",
            columns=["id", "name", "email", "updated_at"],
            conflict_resolution=ConflictResolution.REPLACE,
            conflict_columns=["id"],
            update_columns=["name", "email", "updated_at"],
        )
        sql = query.to_sql(adapter)

        assert "INSERT INTO users" in sql
        assert "ON CONFLICT (id) DO UPDATE SET" in sql
        assert "name = EXCLUDED.name" in sql
        assert "email = EXCLUDED.email" in sql
        assert "updated_at = EXCLUDED.updated_at" in sql


class TestSelectQuery:
    """Test SelectQuery SQL generation."""

    def test_select_simple(self):
        """Test simple SELECT."""
        adapter = DialectAdapter("sqlite:///test.db")
        query = SelectQuery(
            table="users",
            columns=["id", "name", "email"],
        )
        sql = query.to_sql(adapter)

        assert "SELECT id, name, email FROM users" in sql
        assert "WHERE" not in sql
        assert "ORDER BY" not in sql
        assert "LIMIT" not in sql

    def test_select_with_where(self):
        """Test SELECT with WHERE clause."""
        adapter = DialectAdapter("sqlite:///test.db")
        query = SelectQuery(
            table="users",
            columns=["id", "name"],
            where_conditions=["active = ?", "created_at > ?"],
        )
        sql = query.to_sql(adapter)

        assert "SELECT id, name FROM users" in sql
        assert "WHERE active = ? AND created_at > ?" in sql

    def test_select_with_order(self):
        """Test SELECT with ORDER BY."""
        adapter = DialectAdapter("sqlite:///test.db")
        query = SelectQuery(
            table="users",
            columns=["id", "name"],
            order_by="created_at DESC",
        )
        sql = query.to_sql(adapter)

        assert "SELECT id, name FROM users" in sql
        assert "ORDER BY created_at DESC" in sql

    def test_select_with_limit(self):
        """Test SELECT with LIMIT."""
        adapter = DialectAdapter("sqlite:///test.db")
        query = SelectQuery(
            table="users",
            columns=["id", "name"],
            limit=10,
        )
        sql = query.to_sql(adapter)

        assert "SELECT id, name FROM users" in sql
        assert "LIMIT 10" in sql

    def test_select_complete(self):
        """Test SELECT with all clauses."""
        adapter = DialectAdapter("sqlite:///test.db")
        query = SelectQuery(
            table="users",
            columns=["id", "name", "email"],
            where_conditions=["active = ?"],
            order_by="created_at DESC",
            limit=5,
        )
        sql = query.to_sql(adapter)

        assert "SELECT id, name, email FROM users" in sql
        assert "WHERE active = ?" in sql
        assert "ORDER BY created_at DESC" in sql
        assert "LIMIT 5" in sql


class TestQueryBuilder:
    """Test QueryBuilder factory methods."""

    def test_insert_ignore_node_sqlite(self):
        """Test graph_nodes INSERT OR IGNORE for SQLite."""
        adapter = DialectAdapter("sqlite:///test.db")
        builder = QueryBuilder(adapter)
        sql = builder.insert_ignore_node()

        assert "INSERT OR IGNORE INTO graph_nodes" in sql
        assert "(node_id, scope, node_type, attributes_json, version, updated_by, updated_at, created_at)" in sql
        assert "VALUES (?, ?, ?, ?, ?, ?, ?, ?)" in sql

    def test_insert_ignore_node_postgresql(self):
        """Test graph_nodes INSERT for PostgreSQL."""
        adapter = DialectAdapter("postgresql://localhost/test")
        builder = QueryBuilder(adapter)
        sql = builder.insert_ignore_node()

        assert "INSERT INTO graph_nodes" in sql
        assert "ON CONFLICT (node_id, scope) DO NOTHING" in sql
        assert "(node_id, scope, node_type, attributes_json, version, updated_by, updated_at, created_at)" in sql

    def test_insert_ignore_edge_sqlite(self):
        """Test graph_edges INSERT OR IGNORE for SQLite."""
        adapter = DialectAdapter("sqlite:///test.db")
        builder = QueryBuilder(adapter)
        sql = builder.insert_ignore_edge()

        assert "INSERT OR IGNORE INTO graph_edges" in sql
        assert "(edge_id, source_node_id, target_node_id, scope, relationship, weight, attributes_json, created_at)" in sql
        assert "VALUES (?, ?, ?, ?, ?, ?, ?, ?)" in sql

    def test_insert_ignore_edge_postgresql(self):
        """Test graph_edges INSERT for PostgreSQL."""
        adapter = DialectAdapter("postgresql://localhost/test")
        builder = QueryBuilder(adapter)
        sql = builder.insert_ignore_edge()

        assert "INSERT INTO graph_edges" in sql
        assert "ON CONFLICT (edge_id) DO NOTHING" in sql
        assert "(edge_id, source_node_id, target_node_id, scope, relationship, weight, attributes_json, created_at)" in sql

    def test_builder_uses_adapter_dialect(self):
        """Test that builder respects adapter dialect."""
        sqlite_adapter = DialectAdapter("sqlite:///test.db")
        postgres_adapter = DialectAdapter("postgresql://localhost/test")

        sqlite_builder = QueryBuilder(sqlite_adapter)
        postgres_builder = QueryBuilder(postgres_adapter)

        sqlite_sql = sqlite_builder.insert_ignore_node()
        postgres_sql = postgres_builder.insert_ignore_node()

        assert "INSERT OR IGNORE" in sqlite_sql
        assert "ON CONFLICT" in postgres_sql


class TestDialectAdapterIntegration:
    """Test DialectAdapter integration with QueryBuilder."""

    def test_adapter_get_query_builder(self):
        """Test DialectAdapter.get_query_builder()."""
        adapter = DialectAdapter("sqlite:///test.db")
        builder = adapter.get_query_builder()

        assert isinstance(builder, QueryBuilder)
        assert builder.adapter is adapter

    def test_adapter_insert_ignore_node_sql(self):
        """Test DialectAdapter.insert_ignore_node_sql()."""
        sqlite_adapter = DialectAdapter("sqlite:///test.db")
        postgres_adapter = DialectAdapter("postgresql://localhost/test")

        sqlite_sql = sqlite_adapter.insert_ignore_node_sql()
        postgres_sql = postgres_adapter.insert_ignore_node_sql()

        assert "INSERT OR IGNORE" in sqlite_sql
        assert "graph_nodes" in sqlite_sql

        assert "ON CONFLICT (node_id, scope) DO NOTHING" in postgres_sql
        assert "graph_nodes" in postgres_sql

    def test_adapter_insert_ignore_edge_sql(self):
        """Test DialectAdapter.insert_ignore_edge_sql()."""
        sqlite_adapter = DialectAdapter("sqlite:///test.db")
        postgres_adapter = DialectAdapter("postgresql://localhost/test")

        sqlite_sql = sqlite_adapter.insert_ignore_edge_sql()
        postgres_sql = postgres_adapter.insert_ignore_edge_sql()

        assert "INSERT OR IGNORE" in sqlite_sql
        assert "graph_edges" in sqlite_sql

        assert "ON CONFLICT (edge_id) DO NOTHING" in postgres_sql
        assert "graph_edges" in postgres_sql


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_insert_with_no_conflict_columns_defaults_to_all(self):
        """Test INSERT IGNORE without conflict columns uses all columns."""
        adapter = DialectAdapter("postgresql://localhost/test")
        query = InsertQuery(
            table="users",
            columns=["id", "name", "email"],
            conflict_resolution=ConflictResolution.IGNORE,
            # No conflict_columns specified
        )
        sql = query.to_sql(adapter)

        # Should use all columns as conflict columns
        assert "ON CONFLICT (id, name, email) DO NOTHING" in sql

    def test_insert_replace_auto_calculates_update_columns(self):
        """Test INSERT REPLACE auto-calculates update columns."""
        adapter = DialectAdapter("postgresql://localhost/test")
        query = InsertQuery(
            table="users",
            columns=["id", "name", "email", "updated_at"],
            conflict_resolution=ConflictResolution.REPLACE,
            conflict_columns=["id"],
            # No update_columns specified - should use all except conflict
        )
        sql = query.to_sql(adapter)

        assert "name = EXCLUDED.name" in sql
        assert "email = EXCLUDED.email" in sql
        assert "updated_at = EXCLUDED.updated_at" in sql
        # Should NOT update the conflict column
        assert "id = EXCLUDED.id" not in sql

    def test_select_empty_where_conditions(self):
        """Test SELECT with empty where_conditions list."""
        adapter = DialectAdapter("sqlite:///test.db")
        query = SelectQuery(
            table="users",
            columns=["id"],
            where_conditions=[],
        )
        sql = query.to_sql(adapter)

        assert "WHERE" not in sql

    def test_placeholders_always_use_question_mark(self):
        """Test that placeholders always use ? (wrapper translates)."""
        sqlite_adapter = DialectAdapter("sqlite:///test.db")
        postgres_adapter = DialectAdapter("postgresql://localhost/test")

        sqlite_query = InsertQuery(table="test", columns=["a", "b"])
        postgres_query = InsertQuery(table="test", columns=["a", "b"])

        sqlite_sql = sqlite_query.to_sql(sqlite_adapter)
        postgres_sql = postgres_query.to_sql(postgres_adapter)

        # Both should use ? placeholders (cursor wrapper handles translation)
        assert "VALUES (?, ?)" in sqlite_sql
        assert "VALUES (?, ?)" in postgres_sql
        assert "%s" not in postgres_sql  # Wrapper translates this
