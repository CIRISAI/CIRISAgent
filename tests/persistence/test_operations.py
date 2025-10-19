"""
Unit tests for high-level database operations.

Tests the operations layer that wraps query builder and provides
a clean API for business logic.
"""

import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from ciris_engine.logic.persistence.db.core import get_db_connection, initialize_database
from ciris_engine.logic.persistence.db.dialect import init_dialect
from ciris_engine.logic.persistence.db.operations import (
    batch_insert_edges_if_not_exist,
    batch_insert_nodes_if_not_exist,
    insert_edge_if_not_exists,
    insert_node_if_not_exists,
)


@pytest.fixture
def temp_db():
    """Create a temporary SQLite database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = str(Path(tmpdir) / "test.db")

        # Initialize dialect and database
        init_dialect(f"sqlite:///{db_path}")
        initialize_database(db_path=db_path)

        yield db_path


@pytest.fixture
def postgres_db():
    """PostgreSQL database for testing (requires running PostgreSQL)."""
    db_url = "postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db"

    # Initialize dialect
    init_dialect(db_url)

    # Clean up test data
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM graph_edges")
        cursor.execute("DELETE FROM graph_nodes")
        conn.commit()

    yield db_url

    # Clean up after test
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM graph_edges")
        cursor.execute("DELETE FROM graph_nodes")
        conn.commit()


class TestInsertNodeIfNotExists:
    """Test insert_node_if_not_exists() function."""

    def test_insert_new_node_sqlite(self, temp_db):
        """Test inserting a new node in SQLite."""
        result = insert_node_if_not_exists(
            node_id="test_node_1",
            scope="local",
            node_type="test",
            attributes={"key": "value", "count": 42},
            version=1,
            updated_by="test",
            db_path=temp_db,
        )

        assert result is True

        # Verify node was created
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT node_id, node_type, attributes_json FROM graph_nodes WHERE node_id = ?",
                ("test_node_1",),
            )
            row = cursor.fetchone()

            assert row is not None
            assert row["node_id"] == "test_node_1"
            assert row["node_type"] == "test"

            attrs = json.loads(row["attributes_json"])
            assert attrs["key"] == "value"
            assert attrs["count"] == 42

    def test_insert_duplicate_node_ignored_sqlite(self, temp_db):
        """Test inserting duplicate node is ignored in SQLite."""
        # Insert first time
        result1 = insert_node_if_not_exists(
            node_id="test_node_2",
            scope="local",
            node_type="test",
            attributes={"version": 1},
            db_path=temp_db,
        )
        assert result1 is True

        # Insert again - should be ignored
        result2 = insert_node_if_not_exists(
            node_id="test_node_2",
            scope="local",
            node_type="test",
            attributes={"version": 2},  # Different attributes
            db_path=temp_db,
        )
        assert result2 is True  # Node exists

        # Verify original attributes are unchanged
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT attributes_json FROM graph_nodes WHERE node_id = ?",
                ("test_node_2",),
            )
            row = cursor.fetchone()
            attrs = json.loads(row["attributes_json"])
            assert attrs["version"] == 1  # Original value

    @pytest.mark.skipif(
        not Path("/tmp/.postgres_available").exists(),
        reason="PostgreSQL not available"
    )
    def test_insert_new_node_postgresql(self, postgres_db):
        """Test inserting a new node in PostgreSQL."""
        result = insert_node_if_not_exists(
            node_id="pg_test_node_1",
            scope="local",
            node_type="test",
            attributes={"pg_key": "pg_value"},
            version=1,
            updated_by="test",
        )

        assert result is True

        # Verify node was created
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT node_id, attributes_json FROM graph_nodes WHERE node_id = %s",
                ("pg_test_node_1",),
            )
            row = cursor.fetchone()

            assert row is not None
            # PostgreSQL returns JSONB as dict
            attrs = row["attributes_json"] if isinstance(row["attributes_json"], dict) else json.loads(row["attributes_json"])
            assert attrs["pg_key"] == "pg_value"


class TestBatchInsertNodesIfNotExist:
    """Test batch_insert_nodes_if_not_exist() function."""

    def test_batch_insert_nodes_sqlite(self, temp_db):
        """Test batch inserting nodes in SQLite."""
        now = datetime.now(timezone.utc).isoformat()

        nodes = [
            ("batch_node_1", "local", "test", {"batch": 1}, 1, "test", now, now),
            ("batch_node_2", "local", "test", {"batch": 2}, 1, "test", now, now),
            ("batch_node_3", "local", "test", {"batch": 3}, 1, "test", now, now),
        ]

        count = batch_insert_nodes_if_not_exist(nodes, db_path=temp_db)
        assert count == 3

        # Verify all nodes were created
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM graph_nodes WHERE node_id LIKE 'batch_node_%'"
            )
            assert cursor.fetchone()["count"] == 3

    def test_batch_insert_with_duplicates_sqlite(self, temp_db):
        """Test batch insert with duplicates in SQLite."""
        now = datetime.now(timezone.utc).isoformat()

        # Insert first batch
        nodes1 = [
            ("dup_node_1", "local", "test", {"version": 1}, 1, "test", now, now),
            ("dup_node_2", "local", "test", {"version": 1}, 1, "test", now, now),
        ]
        count1 = batch_insert_nodes_if_not_exist(nodes1, db_path=temp_db)
        assert count1 == 2

        # Insert second batch with some duplicates
        nodes2 = [
            ("dup_node_2", "local", "test", {"version": 2}, 1, "test", now, now),  # Duplicate
            ("dup_node_3", "local", "test", {"version": 1}, 1, "test", now, now),  # New
        ]
        count2 = batch_insert_nodes_if_not_exist(nodes2, db_path=temp_db)
        assert count2 == 2  # Returns batch size, not inserted count

        # Verify total count is 3 (not 4)
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM graph_nodes WHERE node_id LIKE 'dup_node_%'"
            )
            assert cursor.fetchone()["count"] == 3


class TestInsertEdgeIfNotExists:
    """Test insert_edge_if_not_exists() function."""

    def test_insert_new_edge_sqlite(self, temp_db):
        """Test inserting a new edge in SQLite."""
        # First create nodes
        insert_node_if_not_exists(
            node_id="source_1", scope="local", node_type="test", attributes={}, db_path=temp_db
        )
        insert_node_if_not_exists(
            node_id="target_1", scope="local", node_type="test", attributes={}, db_path=temp_db
        )

        # Insert edge
        result = insert_edge_if_not_exists(
            edge_id="edge_1",
            source_node_id="source_1",
            target_node_id="target_1",
            scope="local",
            relationship="TEST_RELATIONSHIP",
            weight=0.75,
            attributes={"edge_attr": "value"},
            db_path=temp_db,
        )

        assert result is True

        # Verify edge was created
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT edge_id, relationship, weight, attributes_json FROM graph_edges WHERE edge_id = ?",
                ("edge_1",),
            )
            row = cursor.fetchone()

            assert row is not None
            assert row["relationship"] == "TEST_RELATIONSHIP"
            assert row["weight"] == 0.75

            attrs = json.loads(row["attributes_json"])
            assert attrs["edge_attr"] == "value"

    def test_insert_duplicate_edge_ignored_sqlite(self, temp_db):
        """Test inserting duplicate edge is ignored in SQLite."""
        # Create nodes
        insert_node_if_not_exists(
            node_id="source_2", scope="local", node_type="test", attributes={}, db_path=temp_db
        )
        insert_node_if_not_exists(
            node_id="target_2", scope="local", node_type="test", attributes={}, db_path=temp_db
        )

        # Insert edge first time
        result1 = insert_edge_if_not_exists(
            edge_id="edge_2",
            source_node_id="source_2",
            target_node_id="target_2",
            scope="local",
            relationship="REL1",
            weight=1.0,
            db_path=temp_db,
        )
        assert result1 is True

        # Insert again - should be ignored
        result2 = insert_edge_if_not_exists(
            edge_id="edge_2",
            source_node_id="source_2",
            target_node_id="target_2",
            scope="local",
            relationship="REL2",  # Different relationship
            weight=0.5,
            db_path=temp_db,
        )
        assert result2 is True  # Edge exists

        # Verify original relationship is unchanged
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT relationship FROM graph_edges WHERE edge_id = ?",
                ("edge_2",),
            )
            row = cursor.fetchone()
            assert row["relationship"] == "REL1"  # Original value


class TestBatchInsertEdgesIfNotExist:
    """Test batch_insert_edges_if_not_exist() function."""

    def test_batch_insert_edges_sqlite(self, temp_db):
        """Test batch inserting edges in SQLite."""
        # Create source and target nodes
        for i in range(1, 4):
            insert_node_if_not_exists(
                node_id=f"batch_source_{i}",
                scope="local",
                node_type="test",
                attributes={},
                db_path=temp_db,
            )
            insert_node_if_not_exists(
                node_id=f"batch_target_{i}",
                scope="local",
                node_type="test",
                attributes={},
                db_path=temp_db,
            )

        now = datetime.now(timezone.utc).isoformat()

        edges = [
            ("batch_edge_1", "batch_source_1", "batch_target_1", "local", "REL", 1.0, "{}", now),
            ("batch_edge_2", "batch_source_2", "batch_target_2", "local", "REL", 1.0, "{}", now),
            ("batch_edge_3", "batch_source_3", "batch_target_3", "local", "REL", 1.0, "{}", now),
        ]

        count = batch_insert_edges_if_not_exist(edges, db_path=temp_db)
        assert count == 3

        # Verify all edges were created
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM graph_edges WHERE edge_id LIKE 'batch_edge_%'"
            )
            assert cursor.fetchone()["count"] == 3

    def test_batch_insert_edges_with_duplicates_sqlite(self, temp_db):
        """Test batch insert edges with duplicates in SQLite."""
        # Create nodes
        insert_node_if_not_exists(
            node_id="dup_source", scope="local", node_type="test", attributes={}, db_path=temp_db
        )
        insert_node_if_not_exists(
            node_id="dup_target", scope="local", node_type="test", attributes={}, db_path=temp_db
        )

        now = datetime.now(timezone.utc).isoformat()

        # Insert first batch
        edges1 = [
            ("dup_edge_1", "dup_source", "dup_target", "local", "REL", 1.0, "{}", now),
        ]
        count1 = batch_insert_edges_if_not_exist(edges1, db_path=temp_db)
        assert count1 == 1

        # Insert second batch with duplicate
        edges2 = [
            ("dup_edge_1", "dup_source", "dup_target", "local", "REL", 1.0, "{}", now),  # Duplicate
            ("dup_edge_2", "dup_source", "dup_target", "local", "REL", 1.0, "{}", now),  # New
        ]
        count2 = batch_insert_edges_if_not_exist(edges2, db_path=temp_db)
        assert count2 == 2  # Returns batch size

        # Verify total count is 2 (not 3)
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as count FROM graph_edges WHERE edge_id LIKE 'dup_edge_%'"
            )
            assert cursor.fetchone()["count"] == 2


class TestCrossDatabaseCompatibility:
    """Test that operations work consistently across SQLite and PostgreSQL."""

    def test_node_attributes_json_handling_sqlite(self, temp_db):
        """Test that dict attributes are properly JSON serialized in SQLite."""
        attrs = {
            "string": "value",
            "number": 42,
            "float": 3.14,
            "bool": True,
            "list": [1, 2, 3],
            "nested": {"key": "value"},
        }

        insert_node_if_not_exists(
            node_id="json_test",
            scope="local",
            node_type="test",
            attributes=attrs,
            db_path=temp_db,
        )

        # Verify JSON round-trip
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT attributes_json FROM graph_nodes WHERE node_id = ?",
                ("json_test",),
            )
            row = cursor.fetchone()

            # SQLite returns TEXT, need to parse
            loaded_attrs = json.loads(row["attributes_json"])
            assert loaded_attrs == attrs

    def test_edge_attributes_json_string_handling_sqlite(self, temp_db):
        """Test that edge attributes JSON string is properly handled in SQLite."""
        # Create nodes
        insert_node_if_not_exists(
            node_id="edge_source", scope="local", node_type="test", attributes={}, db_path=temp_db
        )
        insert_node_if_not_exists(
            node_id="edge_target", scope="local", node_type="test", attributes={}, db_path=temp_db
        )

        # Insert edge with complex attributes
        attrs = {"metadata": {"count": 10, "tags": ["a", "b"]}}
        insert_edge_if_not_exists(
            edge_id="json_edge",
            source_node_id="edge_source",
            target_node_id="edge_target",
            scope="local",
            relationship="TEST",
            weight=1.0,
            attributes=attrs,
            db_path=temp_db,
        )

        # Verify JSON round-trip
        with get_db_connection(db_path=temp_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT attributes_json FROM graph_edges WHERE edge_id = ?",
                ("json_edge",),
            )
            row = cursor.fetchone()

            loaded_attrs = json.loads(row["attributes_json"])
            assert loaded_attrs == attrs
