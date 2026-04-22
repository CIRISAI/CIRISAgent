"""
Memory visualization helpers - modular functions for graph layout.

Following CIRIS principles:
- Single Responsibility: Each function handles one layout aspect
- Type Safety: All inputs and outputs are typed
- Separation of Concerns: Layout logic separated from visualization
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple

from ciris_engine.schemas.services.graph_core import GraphNode, NodeType


class TimelineLayoutCalculator:
    """Calculates timeline-based node positions."""

    @staticmethod
    def extract_timestamp(node: GraphNode) -> Optional[datetime]:
        """Extract the most relevant timestamp from a node."""
        # GraphNode only has updated_at, created_at is in attributes
        if node.updated_at:
            return node.updated_at
        # Try to get created_at from attributes if they're typed
        if hasattr(node.attributes, "created_at"):
            return node.attributes.created_at
        return None

    @staticmethod
    def calculate_time_range(nodes: List[GraphNode]) -> Tuple[Optional[datetime], Optional[datetime], float]:
        """Calculate min, max times and range in seconds."""
        timestamps = []
        for node in nodes:
            timestamp = TimelineLayoutCalculator.extract_timestamp(node)
            if timestamp:
                timestamps.append(timestamp)

        if not timestamps:
            return None, None, 1.0

        min_time = min(timestamps)
        max_time = max(timestamps)
        time_range = (max_time - min_time).total_seconds()

        # Avoid division by zero
        if time_range == 0:
            time_range = 1.0

        return min_time, max_time, time_range

    @staticmethod
    def calculate_horizontal_position(
        timestamp: datetime, min_time: datetime, time_range: float, width: int, padding: int
    ) -> float:
        """Calculate X position based on timestamp."""
        time_offset = (timestamp - min_time).total_seconds()
        return padding + (width - 2 * padding) * (time_offset / time_range)

    @staticmethod
    def calculate_vertical_position(
        node_type: NodeType, type_tracks: Dict[NodeType, int], height: int, padding: int
    ) -> Tuple[float, Dict[NodeType, int], int]:
        """Calculate Y position based on node type track."""
        # Get or assign track
        if node_type not in type_tracks:
            track_index = len(type_tracks)
            type_tracks = dict(type_tracks)  # Create new dict to avoid mutation
            type_tracks[node_type] = track_index
        else:
            track_index = type_tracks[node_type]

        # Calculate position
        num_tracks = max(len(type_tracks), 1)
        track_height = (height - 2 * padding) / num_tracks
        y_position = padding + track_index * track_height + track_height / 2

        return y_position, type_tracks, num_tracks

    @staticmethod
    def build_positions(
        nodes: List[GraphNode], width: int, height: int, padding: int
    ) -> Dict[str, Tuple[float, float]]:
        """Build all node positions for timeline layout."""
        positions: Dict[str, Tuple[float, float]] = {}

        # Calculate time range
        min_time, _, time_range = TimelineLayoutCalculator.calculate_time_range(nodes)
        if min_time is None:
            return positions

        # Track assignments for node types
        type_tracks: Dict[NodeType, int] = {}

        for node in nodes:
            timestamp = TimelineLayoutCalculator.extract_timestamp(node)
            if not timestamp:
                continue

            # Calculate X position
            x = TimelineLayoutCalculator.calculate_horizontal_position(timestamp, min_time, time_range, width, padding)

            # Calculate Y position
            y, type_tracks, _ = TimelineLayoutCalculator.calculate_vertical_position(
                node.type, type_tracks, height, padding
            )

            positions[node.id] = (x, y)

        return positions
