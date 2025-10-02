"""
Unit tests for memory route helper functions.

Tests the extracted helper functions that reduce complexity in memory.py:
- get_user_filter_ids_for_observer
- calculate_time_buckets
- query_edges_for_visualization
- generate_html_wrapper
"""

import html
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.memory import (
    calculate_time_buckets,
    generate_html_wrapper,
    get_user_filter_ids_for_observer,
    query_edges_for_visualization,
)
from ciris_engine.schemas.api.auth import AuthContext, Permission, UserRole
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphNode, GraphScope, NodeType


class TestGetUserFilterIdsForObserver:
    """Tests for get_user_filter_ids_for_observer helper."""

    @pytest.mark.asyncio
    async def test_admin_no_filtering(self):
        """ADMIN users should not have filtering applied."""
        request = Mock()
        auth = AuthContext(
            user_id="admin",
            role=UserRole.ADMIN,
            permissions=set(),
            authenticated_at=datetime.now(timezone.utc),
        )

        result = await get_user_filter_ids_for_observer(request, auth)

        assert result is None

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory.get_user_allowed_ids")
    async def test_observer_with_allowed_ids(self, mock_get_allowed_ids):
        """OBSERVER users should get filtered IDs."""
        request = Mock()
        auth = AuthContext(
            user_id="user123",
            role=UserRole.OBSERVER,
            permissions=set(),
            authenticated_at=datetime.now(timezone.utc),
        )

        # Mock authentication service
        mock_auth_service = Mock()
        request.app.state.authentication_service = mock_auth_service

        # Mock get_user_allowed_ids to return a set of IDs
        mock_get_allowed_ids.return_value = {"user123", "discord:discord_123", "google:google_456"}

        result = await get_user_filter_ids_for_observer(request, auth)

        assert result is not None
        assert isinstance(result, list)
        assert "user123" in result
        assert "discord:discord_123" in result
        assert "google:google_456" in result

        # Verify get_user_allowed_ids was called correctly
        mock_get_allowed_ids.assert_called_once_with(mock_auth_service, "user123")

    @pytest.mark.asyncio
    async def test_observer_auth_service_not_available(self):
        """Should raise 503 if auth service not available."""
        request = Mock()
        request.app.state.authentication_service = None
        auth = AuthContext(
            user_id="user123",
            role=UserRole.OBSERVER,
            permissions=set(),
            authenticated_at=datetime.now(timezone.utc),
        )

        with pytest.raises(HTTPException) as exc_info:
            await get_user_filter_ids_for_observer(request, auth)

        assert exc_info.value.status_code == 503
        assert "Authentication service not available" in str(exc_info.value.detail)


class TestCalculateTimeBuckets:
    """Tests for calculate_time_buckets helper."""

    def test_empty_nodes(self):
        """Should return empty dict for empty nodes list."""
        result = calculate_time_buckets([], hours=24)

        assert result == {}

    def test_hourly_bucketing(self):
        """Should use hourly buckets for <= 48 hours."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={},
                updated_at=datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc),
            ),
            GraphNode(
                id="node2",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={},
                updated_at=datetime(2025, 1, 15, 10, 45, tzinfo=timezone.utc),
            ),
            GraphNode(
                id="node3",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={},
                updated_at=datetime(2025, 1, 15, 11, 15, tzinfo=timezone.utc),
            ),
        ]

        result = calculate_time_buckets(nodes, hours=24)

        assert result == {
            "2025-01-15 10:00": 2,
            "2025-01-15 11:00": 1,
        }

    def test_daily_bucketing(self):
        """Should use daily buckets for > 48 hours."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={},
                updated_at=datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc),
            ),
            GraphNode(
                id="node2",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={},
                updated_at=datetime(2025, 1, 16, 14, 45, tzinfo=timezone.utc),
            ),
            GraphNode(
                id="node3",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={},
                updated_at=datetime(2025, 1, 16, 18, 15, tzinfo=timezone.utc),
            ),
        ]

        result = calculate_time_buckets(nodes, hours=72)

        assert result == {
            "2025-01-15": 1,
            "2025-01-16": 2,
        }

    def test_nodes_without_updated_at(self):
        """Should skip nodes without updated_at timestamp."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={},
                updated_at=datetime(2025, 1, 15, 10, 30, tzinfo=timezone.utc),
            ),
            GraphNode(
                id="node2",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={},
                updated_at=None,
            ),
        ]

        result = calculate_time_buckets(nodes, hours=24)

        assert result == {"2025-01-15 10:00": 1}


class TestQueryEdgesForVisualization:
    """Tests for query_edges_for_visualization helper."""

    def test_empty_nodes(self):
        """Should return empty list for empty nodes."""
        result = query_edges_for_visualization([])

        assert result == []

    @patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node")
    def test_query_edges_success(self, mock_get_edges):
        """Should query and return edges between nodes."""
        nodes = [
            GraphNode(id="node1", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={}),
            GraphNode(id="node2", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={}),
        ]

        # Mock edges
        mock_get_edges.return_value = [
            GraphEdge(source="node1", target="node2", relationship="relates_to", scope=GraphScope.LOCAL),
        ]

        result = query_edges_for_visualization(nodes, max_edges=500)

        assert len(result) == 1
        assert result[0].source == "node1"
        assert result[0].target == "node2"

    @patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node")
    def test_exclude_edges_to_missing_nodes(self, mock_get_edges):
        """Should exclude edges where target is not in node list."""
        nodes = [
            GraphNode(id="node1", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={}),
            GraphNode(id="node2", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={}),
        ]

        # Mock edges (one to external node)
        mock_get_edges.return_value = [
            GraphEdge(source="node1", target="node2", relationship="relates_to", scope=GraphScope.LOCAL),
            GraphEdge(source="node1", target="external_node", relationship="relates_to", scope=GraphScope.LOCAL),
        ]

        result = query_edges_for_visualization(nodes, max_edges=500)

        assert len(result) == 1
        assert result[0].target == "node2"

    @patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node")
    def test_avoid_duplicate_edges(self, mock_get_edges):
        """Should avoid duplicate edges (bidirectional)."""
        nodes = [
            GraphNode(id="node1", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={}),
            GraphNode(id="node2", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={}),
        ]

        # Mock edges (same edge in both directions)
        def mock_edges(node_id, scope):
            if node_id == "node1":
                return [GraphEdge(source="node1", target="node2", relationship="relates_to", scope=GraphScope.LOCAL)]
            elif node_id == "node2":
                return [GraphEdge(source="node2", target="node1", relationship="relates_to", scope=GraphScope.LOCAL)]
            return []

        mock_get_edges.side_effect = mock_edges

        result = query_edges_for_visualization(nodes, max_edges=500)

        # Should only have one edge (avoid reverse duplicate)
        assert len(result) == 1

    @patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node")
    def test_max_edges_limit(self, mock_get_edges):
        """Should respect max_edges limit."""
        nodes = [
            GraphNode(id=f"node{i}", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={}) for i in range(10)
        ]

        # Mock many edges
        def mock_edges(node_id, scope):
            idx = int(node_id.replace("node", ""))
            return [
                GraphEdge(source=node_id, target=f"node{j}", relationship="relates_to", scope=GraphScope.LOCAL)
                for j in range(10)
                if j != idx
            ]

        mock_get_edges.side_effect = mock_edges

        result = query_edges_for_visualization(nodes, max_edges=5)

        assert len(result) <= 5

    @patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node")
    def test_exception_handling(self, mock_get_edges):
        """Should handle exceptions gracefully and return empty edges."""
        nodes = [
            GraphNode(id="node1", type=NodeType.CONCEPT, scope=GraphScope.LOCAL, attributes={}),
        ]

        mock_get_edges.side_effect = Exception("Database error")

        result = query_edges_for_visualization(nodes, max_edges=500)

        assert result == []


class TestGenerateHtmlWrapper:
    """Tests for generate_html_wrapper helper."""

    def test_basic_html_generation(self):
        """Should generate valid HTML with embedded SVG."""
        svg = '<svg><circle cx="50" cy="50" r="40"/></svg>'
        hours = 24
        layout = "hierarchy"
        node_count = 10
        width = 800

        result = generate_html_wrapper(svg, hours, layout, node_count, width)

        assert "<!DOCTYPE html>" in result
        assert "<html>" in result
        assert svg in result
        assert "Memory Graph Visualization" in result

    def test_xss_protection(self):
        """Should escape user-controlled values to prevent XSS."""
        svg = '<svg><circle cx="50" cy="50" r="40"/></svg>'
        hours = 24
        layout = '<script>alert("xss")</script>'
        node_count = 10
        width = 800

        result = generate_html_wrapper(svg, hours, layout, node_count, width)

        # Should escape the script tag
        assert '<script>alert("xss")</script>' not in result
        assert html.escape('<script>alert("xss")</script>') in result

    def test_stats_display(self):
        """Should display stats correctly."""
        svg = '<svg><circle cx="50" cy="50" r="40"/></svg>'
        hours = 48
        layout = "timeline"
        node_count = 25
        width = 1200

        result = generate_html_wrapper(svg, hours, layout, node_count, width)

        assert "Last 48 hours" in result
        assert "25" in result
        assert "timeline" in result

    def test_width_calculation(self):
        """Should calculate container width correctly."""
        svg = '<svg><circle cx="50" cy="50" r="40"/></svg>'
        hours = 24
        layout = "hierarchy"
        node_count = 10
        width = 800

        result = generate_html_wrapper(svg, hours, layout, node_count, width)

        # Should add 40px padding to width
        assert "max-width: 840px" in result
