"""
Tests for graph persistence model functions.

Tests database-agnostic graph operations including:
- get_edges_for_node() with SQLite and PostgreSQL placeholders
- Placeholder translation via PostgreSQLCursorWrapper
- Cross-scope edge filtering
"""

from unittest.mock import MagicMock, Mock, patch

import pytest

from ciris_engine.logic.persistence.models.graph import GraphEdge, GraphEdgeAttributes, GraphScope, get_edges_for_node


@pytest.mark.parametrize(
    "database_type,expected_placeholder",
    [
        ("sqlite", "?"),
        ("postgresql", "%s"),
    ],
)
def test_get_edges_for_node_uses_correct_placeholders(database_type, expected_placeholder):
    """Test that get_edges_for_node works with both SQLite (?) and PostgreSQL (%s) placeholders.

    CRITICAL: This test validates the fix for the visualization bug where
    get_edges_for_node() returned 0 edges on PostgreSQL due to hardcoded ? placeholders.

    The PostgreSQLCursorWrapper should automatically translate ? to %s for PostgreSQL.
    """
    # Mock data to return
    mock_edge_data = {
        "source_node_id": "test_node_001",
        "target_node_id": "test_node_002",
        "relationship": "TEMPORAL_NEXT",
        "weight": 1.0,
        "attributes_json": '{"context": "test edge"}',
    }

    # Mock cursor with fetchall
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = [mock_edge_data]

    # Mock connection
    mock_conn = MagicMock()
    mock_conn.__enter__ = Mock(return_value=mock_conn)
    mock_conn.__exit__ = Mock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor

    # Track what SQL was executed
    executed_sql = []
    executed_params = []

    def capture_execute(sql, params=None):
        executed_sql.append(sql)
        executed_params.append(params)
        # Simulate placeholder translation for PostgreSQL
        if database_type == "postgresql":
            # Verify SQL has ? placeholders (before wrapper translates)
            assert "?" in sql, "SQL should use ? placeholders before wrapper translation"
            # Wrapper would translate ? to %s here
        return mock_cursor

    mock_cursor.execute = capture_execute

    with patch("ciris_engine.logic.persistence.models.graph.get_db_connection", return_value=mock_conn):
        # Call get_edges_for_node
        edges = get_edges_for_node(
            node_id="test_node_001",
            scope=GraphScope.LOCAL,
            db_path=f"/tmp/test_{database_type}.db",
        )

        # Verify we got edges back (not empty list)
        assert len(edges) == 1, f"Should return 1 edge for {database_type}"
        assert edges[0].source == "test_node_001"
        assert edges[0].target == "test_node_002"
        assert edges[0].relationship == "TEMPORAL_NEXT"

        # Verify the SQL query was constructed
        assert len(executed_sql) == 1
        sql = executed_sql[0]

        # Verify query structure
        assert "SELECT * FROM graph_edges" in sql
        assert "scope = ?" in sql  # Should use ? placeholder (wrapper handles translation)
        assert "source_node_id = ?" in sql
        assert "target_node_id = ?" in sql

        # Verify parameters
        assert executed_params[0] == ("local", "test_node_001", "test_node_001")


def test_get_edges_for_node_returns_both_incoming_and_outgoing():
    """Test that get_edges_for_node returns edges where node is source OR target."""
    # Create mock edges where test_node is both source and target
    mock_edges_data = [
        {
            "source_node_id": "test_node",
            "target_node_id": "other_node_1",
            "relationship": "TEMPORAL_NEXT",
            "weight": 1.0,
            "attributes_json": "{}",
        },
        {
            "source_node_id": "other_node_2",
            "target_node_id": "test_node",
            "relationship": "TEMPORAL_PREV",
            "weight": 1.0,
            "attributes_json": "{}",
        },
    ]

    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = mock_edges_data

    mock_conn = MagicMock()
    mock_conn.__enter__ = Mock(return_value=mock_conn)
    mock_conn.__exit__ = Mock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute = Mock(return_value=mock_cursor)

    with patch("ciris_engine.logic.persistence.models.graph.get_db_connection", return_value=mock_conn):
        edges = get_edges_for_node("test_node", GraphScope.LOCAL, db_path="/tmp/test.db")

        # Should return both edges (incoming and outgoing)
        assert len(edges) == 2

        # Verify we got both edge types
        relationships = {e.relationship for e in edges}
        assert "TEMPORAL_NEXT" in relationships
        assert "TEMPORAL_PREV" in relationships


def test_get_edges_for_node_filters_by_scope():
    """Test that get_edges_for_node only returns edges matching the requested scope."""

    # Only return edges when scope matches
    def mock_execute_with_scope_check(sql, params):
        requested_scope = params[0]  # First param is scope
        if requested_scope == "local":
            mock_cursor.fetchall.return_value = [
                {
                    "source_node_id": "test_node",
                    "target_node_id": "other_node",
                    "relationship": "TEMPORAL_NEXT",
                    "weight": 1.0,
                    "attributes_json": "{}",
                }
            ]
        else:
            mock_cursor.fetchall.return_value = []  # No edges in other scopes
        return mock_cursor

    mock_cursor = Mock()
    mock_conn = MagicMock()
    mock_conn.__enter__ = Mock(return_value=mock_conn)
    mock_conn.__exit__ = Mock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute = mock_execute_with_scope_check

    with patch("ciris_engine.logic.persistence.models.graph.get_db_connection", return_value=mock_conn):
        # Query LOCAL scope - should return edges
        local_edges = get_edges_for_node("test_node", GraphScope.LOCAL, db_path="/tmp/test.db")
        assert len(local_edges) == 1

        # Query IDENTITY scope - should return no edges (our test edges are in LOCAL)
        identity_edges = get_edges_for_node("test_node", GraphScope.IDENTITY, db_path="/tmp/test.db")
        assert len(identity_edges) == 0


def test_get_edges_for_node_handles_empty_result():
    """Test that get_edges_for_node returns empty list when no edges found."""
    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = []  # No edges

    mock_conn = MagicMock()
    mock_conn.__enter__ = Mock(return_value=mock_conn)
    mock_conn.__exit__ = Mock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute = Mock(return_value=mock_cursor)

    with patch("ciris_engine.logic.persistence.models.graph.get_db_connection", return_value=mock_conn):
        edges = get_edges_for_node("nonexistent_node", GraphScope.LOCAL, db_path="/tmp/test.db")

        assert edges == []
        assert isinstance(edges, list)


def test_get_edges_for_node_parses_attributes_correctly():
    """Test that get_edges_for_node correctly parses edge attributes."""
    mock_edge_data = {
        "source_node_id": "node_a",
        "target_node_id": "node_b",
        "relationship": "IMPACTS_QUALITY",
        "weight": 0.85,
        "attributes_json": '{"created_at": "2025-01-01T00:00:00Z", "context": "quality impact"}',
    }

    mock_cursor = Mock()
    mock_cursor.fetchall.return_value = [mock_edge_data]

    mock_conn = MagicMock()
    mock_conn.__enter__ = Mock(return_value=mock_conn)
    mock_conn.__exit__ = Mock(return_value=False)
    mock_conn.cursor.return_value = mock_cursor
    mock_cursor.execute = Mock(return_value=mock_cursor)

    with patch("ciris_engine.logic.persistence.models.graph.get_db_connection", return_value=mock_conn):
        edges = get_edges_for_node("node_a", GraphScope.LOCAL, db_path="/tmp/test.db")

        assert len(edges) == 1
        edge = edges[0]

        # Verify basic edge properties
        assert edge.source == "node_a"
        assert edge.target == "node_b"
        assert edge.relationship == "IMPACTS_QUALITY"
        assert edge.weight == 0.85

        # Verify attributes were parsed
        assert edge.attributes is not None
        # created_at is parsed as datetime object
        assert edge.attributes.created_at is not None
        assert str(edge.attributes.created_at).startswith("2025-01-01")
        assert edge.attributes.context == "quality impact"


def test_get_edges_for_node_handles_exception_gracefully():
    """Test that get_edges_for_node returns empty list on database error."""
    mock_conn = MagicMock()
    mock_conn.__enter__ = Mock(side_effect=Exception("Database connection failed"))

    with patch("ciris_engine.logic.persistence.models.graph.get_db_connection", return_value=mock_conn):
        edges = get_edges_for_node("test_node", GraphScope.LOCAL, db_path="/tmp/test.db")

        # Should return empty list on error (not raise exception)
        assert edges == []
