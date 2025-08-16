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
        NodeType.THOUGHT: "#3b82f6",  # Blue
        NodeType.TASK: "#10b981",  # Green
        NodeType.MESSAGE: "#f59e0b",  # Amber
        NodeType.ACTION: "#ef4444",  # Red
        NodeType.MEMORY: "#8b5cf6",  # Purple
        NodeType.CONCEPT: "#ec4899",  # Pink
        NodeType.IDENTITY: "#06b6d4",  # Cyan
        NodeType.BEHAVIORAL: "#84cc16",  # Lime
        NodeType.SOCIAL: "#f97316",  # Orange
        NodeType.AUDIT_ENTRY: "#6b7280",  # Gray
        NodeType.CONFIG: "#4b5563",  # Dark gray
        NodeType.WISDOM: "#fbbf24",  # Yellow
    }
    return type_colors.get(node_type, "#9ca3af")


def get_node_size(node: GraphNode) -> int:
    """Calculate node size based on importance."""
    base_size = 8

    # Adjust based on scope
    if node.scope == "IDENTITY":
        base_size += 4
    elif node.scope == "SHARED":
        base_size += 2

    # Adjust based on number of attributes
    if node.attributes:
        base_size += min(len(node.attributes), 4)

    return min(base_size, 20)  # Cap at 20


def hierarchy_pos(
    nodes: List[GraphNode], edges: List[GraphEdge], width: int = 800, height: int = 600
) -> Dict[str, Tuple[float, float]]:
    """
    Create a hierarchical layout for the graph.

    Groups nodes by type and arranges them in layers.
    """
    # Group nodes by type
    by_type: Dict[NodeType, List[GraphNode]] = {}
    for node in nodes:
        node_type = node.type
        if node_type not in by_type:
            by_type[node_type] = []
        by_type[node_type].append(node)

    # Define vertical layers for different types
    type_layers = {
        NodeType.IDENTITY: 0,
        NodeType.CONCEPT: 1,
        NodeType.WISDOM: 1,
        NodeType.TASK: 2,
        NodeType.THOUGHT: 3,
        NodeType.ACTION: 4,
        NodeType.MESSAGE: 5,
        NodeType.MEMORY: 6,
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

    # Get time range
    timestamps = []
    for node in nodes:
        if node.updated_at:
            timestamps.append(node.updated_at)
        elif node.created_at:
            timestamps.append(node.created_at)

    if not timestamps:
        # Fall back to simple layout if no timestamps
        return hierarchy_pos(nodes, [], width, height)

    min_time = min(timestamps)
    max_time = max(timestamps)
    time_range = (max_time - min_time).total_seconds()

    if time_range == 0:
        time_range = 1  # Avoid division by zero

    # Group nodes by type for vertical tracks
    tracks: Dict[NodeType, int] = {}
    track_count = 0

    positions = {}
    padding = TIMELINE_PADDING

    for node in nodes:
        # Get timestamp
        timestamp = node.updated_at or node.created_at
        if not timestamp:
            continue

        # Calculate horizontal position based on time
        time_offset = (timestamp - min_time).total_seconds()
        x = padding + (width - 2 * padding) * (time_offset / time_range)

        # Calculate vertical position based on type track
        if node.type not in tracks:
            tracks[node.type] = track_count
            track_count += 1

        track = tracks[node.type]
        track_height = (height - 2 * padding) / max(len(tracks), 1)
        y = padding + track * track_height + track_height / 2

        positions[node.id] = (x, y)

    return positions


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
    # Calculate node positions based on layout
    if layout == "timeline":
        positions = calculate_timeline_layout(nodes, width, height)
    elif layout == "circular":
        positions = _circular_layout(nodes, width, height)
    else:  # hierarchy
        positions = hierarchy_pos(nodes, edges, width, height)

    # Start SVG
    svg_parts = [
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

    # Draw edges
    svg_parts.append('<g id="edges">')
    for edge in edges:
        if edge.source in positions and edge.target in positions:
            x1, y1 = positions[edge.source]
            x2, y2 = positions[edge.target]

            # Calculate edge midpoint for label
            mid_x = (x1 + x2) / 2
            mid_y = (y1 + y2) / 2

            color = get_edge_color(edge.relationship)
            style = get_edge_style(edge.relationship)

            svg_parts.append(
                f'<line class="edge" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" ' f'stroke="{color}" {style}/>'
            )

            # Add edge label
            if edge.relationship:
                svg_parts.append(
                    f'<text class="edge-label" x="{mid_x}" y="{mid_y}" '
                    f'text-anchor="middle">{edge.relationship}</text>'
                )
    svg_parts.append("</g>")

    # Draw nodes
    svg_parts.append('<g id="nodes">')
    for node in nodes:
        if node.id in positions:
            x, y = positions[node.id]
            color = get_node_color(node.type)
            size = get_node_size(node)

            # Draw node circle
            svg_parts.append(
                f'<circle class="node" cx="{x}" cy="{y}" r="{size}" '
                f'fill="{color}" stroke="white" stroke-width="2" '
                f'data-node-id="{node.id}" data-node-type="{node.type}">'
                f"<title>{node.id}\nType: {node.type}\nScope: {node.scope}</title>"
                f"</circle>"
            )

            # Add node label
            label = node.id[:20] + "..." if len(node.id) > 20 else node.id
            svg_parts.append(
                f'<text class="node-label" x="{x}" y="{y + size + 12}" ' f'text-anchor="middle">{label}</text>'
            )
    svg_parts.append("</g>")

    svg_parts.append("</svg>")

    return "\n".join(svg_parts)


def _circular_layout(nodes: List[GraphNode], width: int, height: int) -> Dict[str, Tuple[float, float]]:
    """Create a circular layout for nodes."""
    positions = {}
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
