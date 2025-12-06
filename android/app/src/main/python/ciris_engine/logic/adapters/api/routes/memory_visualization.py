"""
Graph visualization utilities for memory API.

Extracted from memory.py to improve modularity and separation of concerns.
"""

import json
import logging
import math
from datetime import datetime
from typing import Any, Dict, List, Optional, Set, Tuple

from ciris_engine.schemas.services.graph_core import GraphEdge, GraphNode, NodeType
from ciris_engine.schemas.types import JSONDict

from .memory_visualization_helpers import TimelineLayoutCalculator

logger = logging.getLogger(__name__)

# Visualization Constants
TIMELINE_WIDTH = 1200
TIMELINE_HEIGHT = 800
TIMELINE_PADDING = 50
NODE_RADIUS = 8
HOVER_RADIUS = 12
TIMELINE_TRACK_HEIGHT = 100


def get_edge_color(relationship: str) -> str:
    """Get color for edge based on relationship type."""
    edge_colors = {
        "CREATED": "#2563eb",  # Blue
        "UPDATED": "#10b981",  # Green
        "REFERENCED": "#f59e0b",  # Amber
        "TRIGGERED": "#ef4444",  # Red
        "ANALYZED": "#8b5cf6",  # Purple
        "RESPONDED_TO": "#ec4899",  # Pink
        "CAUSED": "#dc2626",  # Dark red
        "RESOLVED": "#059669",  # Dark green
        "DEPENDS_ON": "#7c3aed",  # Violet
        "RELATES_TO": "#6b7280",  # Gray
        "DERIVED_FROM": "#0891b2",  # Cyan
        "STORED": "#4b5563",  # Dark gray
    }
    return edge_colors.get(relationship, "#9ca3af")  # Default gray


def get_edge_style(relationship: str) -> str:
    """Get stroke style for edge based on relationship type."""
    styles = {
        "CREATED": "",
        "UPDATED": "stroke-dasharray: 5, 5",
        "REFERENCED": "stroke-dasharray: 2, 2",
        "TRIGGERED": "",
        "ANALYZED": "stroke-dasharray: 8, 4",
        "RESPONDED_TO": "",
        "CAUSED": "",
        "RESOLVED": "",
        "DEPENDS_ON": "stroke-dasharray: 10, 5",
        "RELATES_TO": "stroke-dasharray: 3, 3",
        "DERIVED_FROM": "stroke-dasharray: 6, 3",
        "STORED": "stroke-dasharray: 1, 1",
    }
    return styles.get(relationship, "stroke-dasharray: 4, 4")


def get_node_color(node_type: NodeType) -> str:
    """Get color for node based on type."""
    # Map NodeType enums to colors
    type_colors = {
        NodeType.AGENT: "#3b82f6",  # Blue
        NodeType.USER: "#10b981",  # Green
        NodeType.CHANNEL: "#f59e0b",  # Amber
        NodeType.CONCEPT: "#ec4899",  # Pink
        NodeType.CONFIG: "#4b5563",  # Dark gray
        NodeType.TSDB_DATA: "#8b5cf6",  # Purple
        NodeType.TSDB_SUMMARY: "#7c3aed",  # Violet
        NodeType.CONVERSATION_SUMMARY: "#0891b2",  # Cyan
        NodeType.TRACE_SUMMARY: "#ef4444",  # Red
        NodeType.AUDIT_SUMMARY: "#dc2626",  # Dark red
        NodeType.TASK_SUMMARY: "#059669",  # Dark green
        NodeType.AUDIT_ENTRY: "#6b7280",  # Gray
        NodeType.IDENTITY_SNAPSHOT: "#06b6d4",  # Cyan
        NodeType.BEHAVIORAL: "#84cc16",  # Lime
        NodeType.SOCIAL: "#f97316",  # Orange
        NodeType.IDENTITY: "#06b6d4",  # Cyan
        NodeType.OBSERVATION: "#fbbf24",  # Yellow
    }
    return type_colors.get(node_type, "#9ca3af")


def get_node_size(node: GraphNode, edge_count: int = 0) -> int:
    """Calculate node size based on importance and connections."""
    base_size = 8

    # Adjust based on scope
    if node.scope == "identity":
        base_size += 4
    elif node.scope == "community":
        base_size += 2

    # Adjust based on number of connections
    if edge_count > 0:
        # Logarithmic scaling for edge count
        base_size += min(int(math.log(edge_count + 1) * 3), 12)

    # Adjust based on number of attributes
    if node.attributes:
        # Handle both GraphNodeAttributes and JSONDict
        if isinstance(node.attributes, dict):
            base_size += min(len(node.attributes), 4)
        else:
            # For GraphNodeAttributes, use the number of tags as a proxy for complexity
            base_size += min(len(node.attributes.tags), 4)

    return min(base_size, 20)  # Cap at 20


def hierarchy_pos(
    nodes: List[GraphNode], edges: List[GraphEdge], width: int = 800, height: int = 600
) -> Dict[str, Tuple[float, float]]:
    """
    Create a hierarchical layout for the graph.

    Groups nodes by type and arranges them in layers.
    """
    # Build adjacency information from edges for better layout
    connections: Dict[str, int] = {}
    for edge in edges:
        connections[edge.source] = connections.get(edge.source, 0) + 1
        connections[edge.target] = connections.get(edge.target, 0) + 1

    # Group nodes by type
    by_type: Dict[NodeType, List[GraphNode]] = {}
    for node in nodes:
        node_type = node.type
        if node_type not in by_type:
            by_type[node_type] = []
        by_type[node_type].append(node)

    # Sort nodes within each type by connectivity (most connected first)
    for node_type in by_type:
        by_type[node_type].sort(key=lambda n: connections.get(n.id, 0), reverse=True)

    # Define vertical layers for different types
    type_layers = {
        NodeType.IDENTITY: 0,
        NodeType.CONCEPT: 1,
        NodeType.OBSERVATION: 1,
        NodeType.AGENT: 2,
        NodeType.USER: 3,
        NodeType.CHANNEL: 4,
        NodeType.TASK_SUMMARY: 5,
        NodeType.AUDIT_SUMMARY: 6,
        NodeType.BEHAVIORAL: 7,
        NodeType.SOCIAL: 7,
        NodeType.AUDIT_ENTRY: 8,
        NodeType.CONFIG: 9,
    }

    positions = {}
    padding = 50

    # Calculate positions for each node
    for node_type, type_nodes in by_type.items():
        layer = type_layers.get(node_type, 5)
        layer_y = padding + (height - 2 * padding) * (layer / 9)

        # Distribute nodes horizontally within the layer
        num_nodes = len(type_nodes)
        if num_nodes == 1:
            positions[type_nodes[0].id] = (width / 2, layer_y)
        else:
            spacing = (width - 2 * padding) / (num_nodes - 1)
            for i, node in enumerate(type_nodes):
                x = padding + i * spacing
                positions[node.id] = (x, layer_y)

    return positions


def calculate_timeline_layout(
    nodes: List[GraphNode], width: int = TIMELINE_WIDTH, height: int = TIMELINE_HEIGHT
) -> Dict[str, Tuple[float, float]]:
    """
    Create a timeline layout for nodes based on their timestamps.

    Arranges nodes chronologically with vertical separation by type.
    """
    if not nodes:
        return {}

    # Use helper to calculate positions
    positions = TimelineLayoutCalculator.build_positions(nodes, width, height, TIMELINE_PADDING)

    # Fall back to hierarchy layout if no timestamps
    if not positions:
        return hierarchy_pos(nodes, [], width, height)

    return positions


def _get_layout_positions(
    layout: str, nodes: List[GraphNode], edges: List[GraphEdge], width: int, height: int
) -> Dict[str, Tuple[float, float]]:
    """Get node positions based on layout type."""
    if layout == "timeline":
        return calculate_timeline_layout(nodes, width, height)
    elif layout == "circular":
        return _circular_layout(nodes, width, height)
    else:  # hierarchy
        return hierarchy_pos(nodes, edges, width, height)


def _generate_svg_header(width: int, height: int) -> List[str]:
    """Generate SVG header with styles."""
    return [
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">',
        "<style>",
        ".node { cursor: pointer; }",
        ".node:hover { opacity: 0.8; }",
        ".edge { stroke-width: 2; fill: none; opacity: 0.6; }",
        ".edge:hover { opacity: 1; stroke-width: 3; }",
        ".node-label { font-family: monospace; font-size: 10px; fill: #374151; pointer-events: none; }",
        ".edge-label { font-family: monospace; font-size: 8px; fill: #6b7280; pointer-events: none; }",
        "</style>",
    ]


def _render_edge(edge: GraphEdge, positions: Dict[str, Tuple[float, float]]) -> List[str]:
    """Render a single edge as SVG elements with curved path."""
    if edge.source not in positions or edge.target not in positions:
        return []

    x1, y1 = positions[edge.source]
    x2, y2 = positions[edge.target]

    # Calculate control point for quadratic bezier curve
    dx = x2 - x1
    dy = y2 - y1
    distance = math.sqrt(dx * dx + dy * dy) if (dx * dx + dy * dy) > 0 else 1

    # Create a slight curve for better visibility
    offset = min(25, distance * 0.15)  # Curve amount
    cx = (x1 + x2) / 2 - (dy / distance) * offset
    cy = (y1 + y2) / 2 + (dx / distance) * offset

    # Use quadratic bezier path
    path = f"M {x1},{y1} Q {cx},{cy} {x2},{y2}"

    color = get_edge_color(edge.relationship)
    style = get_edge_style(edge.relationship)

    parts = [f'<path class="edge" d="{path}" fill="none" stroke="{color}" ' f'stroke-width="2" opacity="0.5" {style}/>']

    if edge.relationship:
        # Place label at the control point for better positioning
        parts.append(
            f'<text class="edge-label" x="{cx}" y="{cy}" text-anchor="middle" '
            f'font-size="10" fill="{color}">{edge.relationship}</text>'
        )

    return parts


def _render_node(node: GraphNode, position: Tuple[float, float], edge_count: int = 0) -> List[str]:
    """Render a single node as SVG elements."""
    x, y = position
    color = get_node_color(node.type)
    size = get_node_size(node, edge_count)

    # Get string values for type and scope
    type_str = node.type.value if hasattr(node.type, "value") else str(node.type)
    scope_str = node.scope.value if hasattr(node.scope, "value") else str(node.scope)

    # Truncate label if needed
    label = node.id[:20] + "..." if len(node.id) > 20 else node.id

    return [
        f'<circle class="node" cx="{x}" cy="{y}" r="{size}" '
        f'fill="{color}" stroke="white" stroke-width="2" '
        f'data-node-id="{node.id}" data-node-type="{type_str}">'
        f"<title>{node.id}\nType: {type_str}\nScope: {scope_str}</title>"
        f"</circle>",
        f'<text class="node-label" x="{x}" y="{y + size + 12}" text-anchor="middle">{label}</text>',
    ]


def generate_svg(
    nodes: List[GraphNode],
    edges: List[GraphEdge],
    layout: str = "hierarchy",
    width: int = 800,
    height: int = 600,
) -> str:
    """
    Generate an SVG visualization of the graph.

    Args:
        nodes: List of graph nodes
        edges: List of graph edges
        layout: Layout algorithm ("hierarchy", "timeline", "circular")
        width: SVG width
        height: SVG height

    Returns:
        SVG string
    """
    # Get node positions
    positions = _get_layout_positions(layout, nodes, edges, width, height)

    # Build SVG parts
    svg_parts = _generate_svg_header(width, height)

    # Draw edges
    svg_parts.append('<g id="edges">')
    for edge in edges:
        svg_parts.extend(_render_edge(edge, positions))
    svg_parts.append("</g>")

    # Calculate edge counts for each node
    edge_counts: Dict[str, int] = {}
    for edge in edges:
        edge_counts[edge.source] = edge_counts.get(edge.source, 0) + 1
        edge_counts[edge.target] = edge_counts.get(edge.target, 0) + 1

    # Draw nodes with edge counts for sizing
    svg_parts.append('<g id="nodes">')
    for node in nodes:
        if node.id in positions:
            edge_count = edge_counts.get(node.id, 0)
            svg_parts.extend(_render_node(node, positions[node.id], edge_count))
    svg_parts.append("</g>")

    svg_parts.append("</svg>")

    return "\n".join(svg_parts)


def _circular_layout(nodes: List[GraphNode], width: int, height: int) -> Dict[str, Tuple[float, float]]:
    """Create a circular layout for nodes."""
    positions: Dict[str, Tuple[float, float]] = {}
    center_x = width / 2
    center_y = height / 2
    radius = min(width, height) / 2 - 50

    num_nodes = len(nodes)
    if num_nodes == 0:
        return positions

    angle_step = 2 * math.pi / num_nodes

    for i, node in enumerate(nodes):
        angle = i * angle_step
        x = center_x + radius * math.cos(angle)
        y = center_y + radius * math.sin(angle)
        positions[node.id] = (x, y)

    return positions
