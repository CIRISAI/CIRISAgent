"""
Unit tests for memory_visualization module.

Tests graph visualization utilities for memory API.
"""

from datetime import datetime, timedelta
from unittest.mock import Mock

import pytest

from ciris_engine.logic.adapters.api.routes.memory_visualization import (
    _circular_layout,
    calculate_timeline_layout,
    generate_svg,
    get_edge_color,
    get_edge_style,
    get_node_color,
    get_node_size,
    hierarchy_pos,
)
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphNode, GraphNodeAttributes, NodeType


class TestGetEdgeColor:
    """Test get_edge_color function."""

    def test_known_relationships(self):
        """Test color mapping for known relationships."""
        assert get_edge_color("CREATED") == "#2563eb"
        assert get_edge_color("UPDATED") == "#10b981"
        assert get_edge_color("REFERENCED") == "#f59e0b"
        assert get_edge_color("TRIGGERED") == "#ef4444"
        assert get_edge_color("ANALYZED") == "#8b5cf6"
        assert get_edge_color("RESPONDED_TO") == "#ec4899"
        assert get_edge_color("CAUSED") == "#dc2626"
        assert get_edge_color("RESOLVED") == "#059669"
        assert get_edge_color("DEPENDS_ON") == "#7c3aed"
        assert get_edge_color("RELATES_TO") == "#6b7280"
        assert get_edge_color("DERIVED_FROM") == "#0891b2"
        assert get_edge_color("STORED") == "#4b5563"

    def test_unknown_relationship(self):
        """Test default color for unknown relationships."""
        assert get_edge_color("UNKNOWN") == "#9ca3af"
        assert get_edge_color("") == "#9ca3af"


class TestGetEdgeStyle:
    """Test get_edge_style function."""

    def test_solid_lines(self):
        """Test relationships with solid lines."""
        assert get_edge_style("CREATED") == ""
        assert get_edge_style("TRIGGERED") == ""
        assert get_edge_style("RESPONDED_TO") == ""
        assert get_edge_style("CAUSED") == ""
        assert get_edge_style("RESOLVED") == ""

    def test_dashed_lines(self):
        """Test relationships with dashed lines."""
        assert get_edge_style("UPDATED") == "stroke-dasharray: 5, 5"
        assert get_edge_style("REFERENCED") == "stroke-dasharray: 2, 2"
        assert get_edge_style("ANALYZED") == "stroke-dasharray: 8, 4"
        assert get_edge_style("DEPENDS_ON") == "stroke-dasharray: 10, 5"
        assert get_edge_style("RELATES_TO") == "stroke-dasharray: 3, 3"
        assert get_edge_style("DERIVED_FROM") == "stroke-dasharray: 6, 3"
        assert get_edge_style("STORED") == "stroke-dasharray: 1, 1"

    def test_unknown_style(self):
        """Test default style for unknown relationships."""
        assert get_edge_style("UNKNOWN") == "stroke-dasharray: 4, 4"


class TestGetNodeColor:
    """Test get_node_color function."""

    def test_node_type_colors(self):
        """Test color mapping for node types."""
        assert get_node_color(NodeType.AGENT) == "#3b82f6"
        assert get_node_color(NodeType.USER) == "#10b981"
        assert get_node_color(NodeType.CHANNEL) == "#f59e0b"
        assert get_node_color(NodeType.CONCEPT) == "#ec4899"
        assert get_node_color(NodeType.IDENTITY) == "#06b6d4"
        assert get_node_color(NodeType.BEHAVIORAL) == "#84cc16"
        assert get_node_color(NodeType.SOCIAL) == "#f97316"
        assert get_node_color(NodeType.AUDIT_ENTRY) == "#6b7280"
        assert get_node_color(NodeType.CONFIG) == "#4b5563"
        assert get_node_color(NodeType.OBSERVATION) == "#fbbf24"


class TestGetNodeSize:
    """Test get_node_size function."""

    def test_base_size(self):
        """Test base size for simple node."""
        node = GraphNode(id="test", type=NodeType.CONCEPT, scope="local", attributes={}, version=1, updated_by="system")
        assert get_node_size(node) == 8

    def test_identity_scope_bonus(self):
        """Test IDENTITY scope adds size."""
        node = GraphNode(
            id="test", type=NodeType.IDENTITY, scope="identity", attributes={}, version=1, updated_by="system"
        )
        assert get_node_size(node) == 12  # Base 8 + 4 for IDENTITY

    def test_shared_scope_bonus(self):
        """Test community scope adds size."""
        node = GraphNode(
            id="test", type=NodeType.CONCEPT, scope="community", attributes={}, version=1, updated_by="system"
        )
        assert get_node_size(node) == 10  # Base 8 + 2 for community

    def test_attributes_bonus(self):
        """Test attributes add size."""
        node = GraphNode(
            id="test",
            type=NodeType.OBSERVATION,
            scope="local",
            attributes={"a": 1, "b": 2, "c": 3},
            version=1,
            updated_by="system",
        )
        assert get_node_size(node) == 11  # Base 8 + 3 attributes

    def test_max_size_cap(self):
        """Test size is capped at 20."""
        node = GraphNode(
            id="test",
            type=NodeType.OBSERVATION,
            scope="identity",  # +4
            attributes={f"attr{i}": i for i in range(10)},  # +4 (capped)
            version=1,
            updated_by="system",
        )
        # Base 8 + 4 (IDENTITY) + 4 (attributes capped) = 16
        assert get_node_size(node) == 16
        assert get_node_size(node) <= 20


class TestHierarchyPos:
    """Test hierarchy_pos function."""

    def test_empty_nodes(self):
        """Test with empty nodes list."""
        positions = hierarchy_pos([], [], 800, 600)
        assert positions == {}

    def test_single_node(self):
        """Test with single node."""
        node = GraphNode(
            id="node1", type=NodeType.CONCEPT, scope="local", attributes={}, version=1, updated_by="system"
        )
        positions = hierarchy_pos([node], [], 800, 600)

        assert "node1" in positions
        x, y = positions["node1"]
        assert x == 400  # Centered horizontally
        assert isinstance(y, (int, float))

    def test_multiple_nodes_same_type(self):
        """Test multiple nodes of same type are distributed horizontally."""
        nodes = [
            GraphNode(
                id=f"node{i}", type=NodeType.TASK_SUMMARY, scope="local", attributes={}, version=1, updated_by="system"
            )
            for i in range(3)
        ]
        positions = hierarchy_pos(nodes, [], 800, 600)

        assert len(positions) == 3
        # Check nodes are at same vertical level
        y_values = [pos[1] for pos in positions.values()]
        assert len(set(y_values)) == 1  # All same Y

    def test_different_node_types(self):
        """Test different node types are at different vertical levels."""
        nodes = [
            GraphNode(
                id="identity", type=NodeType.IDENTITY, scope="identity", attributes={}, version=1, updated_by="system"
            ),
            GraphNode(
                id="task", type=NodeType.TASK_SUMMARY, scope="local", attributes={}, version=1, updated_by="system"
            ),
            GraphNode(
                id="memory", type=NodeType.OBSERVATION, scope="community", attributes={}, version=1, updated_by="system"
            ),
        ]
        positions = hierarchy_pos(nodes, [], 800, 600)

        # Different types should have different Y positions
        y_values = [positions[node.id][1] for node in nodes]
        assert len(set(y_values)) == 3

    def test_with_edges_for_sorting(self):
        """Test nodes are sorted by connectivity when edges provided."""
        nodes = [
            GraphNode(
                id=f"node{i}", type=NodeType.CONCEPT, scope="local", attributes={}, version=1, updated_by="system"
            )
            for i in range(3)
        ]
        edges = [
            GraphEdge(source="node0", target="node1", relationship="CREATED", scope="local"),
            GraphEdge(source="node0", target="node2", relationship="CREATED", scope="local"),
            GraphEdge(source="node1", target="node2", relationship="UPDATED", scope="local"),
        ]

        positions = hierarchy_pos(nodes, edges, 800, 600)
        assert len(positions) == 3
        # node0 should be leftmost (most connected)
        assert positions["node0"][0] < positions["node2"][0]


class TestCalculateTimelineLayout:
    """Test calculate_timeline_layout function."""

    def test_empty_nodes(self):
        """Test with empty nodes list."""
        positions = calculate_timeline_layout([])
        assert positions == {}

    def test_nodes_without_timestamps(self):
        """Test falls back to hierarchy layout when no timestamps."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope="local",
                attributes={},
                version=1,
                updated_by="system",
                updated_at=None,
            )
        ]
        positions = calculate_timeline_layout(nodes)
        # Should fall back to hierarchy_pos
        assert len(positions) == 1

    def test_nodes_with_timestamps(self):
        """Test timeline layout with timestamps."""
        base_time = datetime.now()
        nodes = [
            GraphNode(
                id="early",
                type=NodeType.CONCEPT,
                scope="local",
                attributes={},
                version=1,
                updated_by="system",
                updated_at=base_time,
            ),
            GraphNode(
                id="late",
                type=NodeType.CONCEPT,
                scope="local",
                attributes={},
                version=1,
                updated_by="system",
                updated_at=base_time + timedelta(hours=1),
            ),
        ]

        positions = calculate_timeline_layout(nodes)

        assert len(positions) == 2
        # Later node should be further right
        assert positions["late"][0] > positions["early"][0]

    def test_different_types_different_tracks(self):
        """Test different node types get different vertical tracks."""
        base_time = datetime.now()
        nodes = [
            GraphNode(
                id="thought",
                type=NodeType.CONCEPT,
                scope="local",
                attributes={},
                version=1,
                updated_by="system",
                updated_at=base_time,
            ),
            GraphNode(
                id="task",
                type=NodeType.TASK_SUMMARY,
                scope="local",
                attributes={},
                version=1,
                updated_by="system",
                updated_at=base_time,
            ),
        ]

        positions = calculate_timeline_layout(nodes)

        # Different types should have different Y positions
        assert positions["thought"][1] != positions["task"][1]

    def test_custom_dimensions(self):
        """Test with custom width and height."""
        base_time = datetime.now()
        node = GraphNode(
            id="node",
            type=NodeType.OBSERVATION,
            scope="local",
            attributes={},
            version=1,
            updated_by="system",
            updated_at=base_time,
        )

        positions = calculate_timeline_layout([node], width=1600, height=900)

        assert "node" in positions
        x, y = positions["node"]
        # Should be within custom bounds (with padding)
        assert 0 < x < 1600
        assert 0 < y < 900


class TestCircularLayout:
    """Test _circular_layout function."""

    def test_empty_nodes(self):
        """Test with empty nodes list."""
        positions = _circular_layout([], 800, 600)
        assert positions == {}

    def test_single_node_centered(self):
        """Test single node is centered."""
        node = GraphNode(
            id="center", type=NodeType.CONCEPT, scope="local", attributes={}, version=1, updated_by="system"
        )

        positions = _circular_layout([node], 800, 600)

        x, y = positions["center"]
        # First node at angle 0 (rightmost point of circle)
        assert x > 400  # Right of center
        assert abs(y - 300) < 1  # Vertically centered

    def test_multiple_nodes_circular(self):
        """Test multiple nodes arranged in circle."""
        nodes = [
            GraphNode(
                id=f"node{i}", type=NodeType.OBSERVATION, scope="local", attributes={}, version=1, updated_by="system"
            )
            for i in range(4)
        ]

        positions = _circular_layout(nodes, 800, 600)

        assert len(positions) == 4
        # Check all nodes are roughly same distance from center
        center_x, center_y = 400, 300
        distances = [((x - center_x) ** 2 + (y - center_y) ** 2) ** 0.5 for x, y in positions.values()]
        # All distances should be similar (within 1 pixel)
        assert max(distances) - min(distances) < 1


class TestGenerateSVG:
    """Test generate_svg function."""

    def test_empty_graph(self):
        """Test SVG generation with empty graph."""
        svg = generate_svg([], [])

        assert '<svg width="800" height="600"' in svg
        assert "</svg>" in svg
        assert "<style>" in svg

    def test_single_node(self):
        """Test SVG with single node."""
        node = GraphNode(
            id="test_node", type=NodeType.CONCEPT, scope="local", attributes={}, version=1, updated_by="system"
        )

        svg = generate_svg([node], [])

        assert 'data-node-id="test_node"' in svg
        assert 'data-node-type="concept"' in svg
        assert "<circle" in svg
        assert "<text" in svg

    def test_node_and_edge(self):
        """Test SVG with nodes and edges."""
        nodes = [
            GraphNode(
                id="node1", type=NodeType.TASK_SUMMARY, scope="local", attributes={}, version=1, updated_by="system"
            ),
            GraphNode(
                id="node2", type=NodeType.TASK_SUMMARY, scope="local", attributes={}, version=1, updated_by="system"
            ),
        ]
        edges = [GraphEdge(source="node1", target="node2", relationship="CREATED", scope="local")]

        svg = generate_svg(nodes, edges)

        # We now use <path> for curved edges instead of <line>
        assert "<path" in svg
        assert 'stroke="#2563eb"' in svg  # CREATED color
        assert "CREATED" in svg  # Edge label

    def test_timeline_layout(self):
        """Test SVG with timeline layout."""
        base_time = datetime.now()
        nodes = [
            GraphNode(
                id="event1",
                type=NodeType.AUDIT_SUMMARY,
                scope="local",
                attributes={},
                version=1,
                updated_by="system",
                updated_at=base_time,
            ),
            GraphNode(
                id="event2",
                type=NodeType.AUDIT_SUMMARY,
                scope="local",
                attributes={},
                version=1,
                updated_by="system",
                updated_at=base_time + timedelta(minutes=30),
            ),
        ]

        svg = generate_svg(nodes, [], layout="timeline")

        assert 'data-node-id="event1"' in svg
        assert 'data-node-id="event2"' in svg

    def test_circular_layout(self):
        """Test SVG with circular layout."""
        nodes = [
            GraphNode(
                id=f"node{i}", type=NodeType.CONCEPT, scope="community", attributes={}, version=1, updated_by="system"
            )
            for i in range(6)
        ]

        svg = generate_svg(nodes, [], layout="circular")

        for i in range(6):
            assert f'data-node-id="node{i}"' in svg

    def test_custom_dimensions(self):
        """Test SVG with custom dimensions."""
        node = GraphNode(
            id="node", type=NodeType.OBSERVATION, scope="identity", attributes={}, version=1, updated_by="system"
        )

        svg = generate_svg([node], [], width=1200, height=800)

        assert '<svg width="1200" height="800"' in svg

    def test_long_node_id_truncation(self):
        """Test long node IDs are truncated in labels."""
        long_id = "this_is_a_very_long_node_id_that_should_be_truncated"
        node = GraphNode(
            id=long_id, type=NodeType.OBSERVATION, scope="local", attributes={}, version=1, updated_by="system"
        )

        svg = generate_svg([node], [])

        assert f'data-node-id="{long_id}"' in svg  # Full ID in data
        assert "..." in svg  # Truncation indicator in label

    def test_node_hover_title(self):
        """Test nodes have hover titles with info."""
        node = GraphNode(
            id="hover_test", type=NodeType.BEHAVIORAL, scope="identity", attributes={}, version=1, updated_by="system"
        )

        svg = generate_svg([node], [])

        assert "<title>" in svg
        assert "hover_test" in svg
        assert "Type: behavioral" in svg
        assert "Scope: identity" in svg

    def test_edge_with_missing_nodes(self):
        """Test edge is skipped if nodes don't exist."""
        node = GraphNode(
            id="node1", type=NodeType.TASK_SUMMARY, scope="local", attributes={}, version=1, updated_by="system"
        )
        edge = GraphEdge(source="node1", target="missing_node", relationship="DEPENDS_ON", scope="local")

        svg = generate_svg([node], [edge])

        # Edge should not be rendered
        assert "<line" not in svg
        assert "DEPENDS_ON" not in svg
