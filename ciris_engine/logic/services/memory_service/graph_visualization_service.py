"""
Graph Visualization Service for Memory API.

Extracts complex SVG generation and layout logic from the memory routes.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple, Any, TYPE_CHECKING
from enum import Enum

from ciris_engine.schemas.services.graph_core import GraphNode, GraphEdge, GraphScope, NodeType

if TYPE_CHECKING:
    import networkx as nx

logger = logging.getLogger(__name__)


class LayoutType(str, Enum):
    """Graph layout algorithms."""
    FORCE = "force"
    TIMELINE = "timeline"
    HIERARCHICAL = "hierarchical"


class NodeStyle:
    """Visual style configuration for nodes."""
    
    def __init__(self, color: str, shape: str = "circle", size: int = 30):
        self.color = color
        self.shape = shape
        self.size = size


class EdgeStyle:
    """Visual style configuration for edges."""
    
    def __init__(self, color: str = "#999", width: int = 2, dashed: bool = False):
        self.color = color
        self.width = width
        self.dashed = dashed


class GraphVisualizationService:
    """Service for generating graph visualizations."""
    
    # Node type to color mapping
    NODE_COLORS = {
        NodeType.THOUGHT: "#FF6B6B",      # Red - active thoughts
        NodeType.TASK: "#4ECDC4",         # Teal - tasks
        NodeType.CONVERSATION: "#95E1D3", # Light teal - conversations
        NodeType.MESSAGE: "#74B9FF",      # Light blue - messages
        NodeType.CONCEPT: "#A29BFE",      # Purple - concepts
        NodeType.IDENTITY: "#FFEAA7",     # Yellow - identity
        NodeType.METRIC: "#FD79A8",       # Pink - metrics
        NodeType.TOOL: "#FDCB6E",         # Orange - tools
        NodeType.AUDIT: "#636E72",        # Gray - audit
        NodeType.INCIDENT: "#D63031",     # Dark red - incidents
        NodeType.TSDB_DATA: "#00B894",    # Green - time series data
    }
    
    # Edge relationship to style mapping
    EDGE_STYLES = {
        "replied_to": EdgeStyle("#74B9FF", 2),
        "thought_about": EdgeStyle("#FF6B6B", 2, dashed=True),
        "relates_to": EdgeStyle("#999", 1),
        "follows": EdgeStyle("#4ECDC4", 2),
        "depends_on": EdgeStyle("#FD79A8", 2),
        "created": EdgeStyle("#95E1D3", 2),
        "updated": EdgeStyle("#FDCB6E", 1, dashed=True),
    }
    
    def __init__(self):
        """Initialize visualization service."""
        pass
    
    async def generate_svg(
        self,
        nodes: List[GraphNode],
        edges: List[GraphEdge],
        layout_type: LayoutType,
        width: int,
        height: int,
        hours: Optional[int] = None
    ) -> str:
        """
        Generate SVG visualization of nodes and edges.
        
        Args:
            nodes: List of graph nodes to visualize
            edges: List of edges between nodes
            layout_type: Layout algorithm to use
            width: SVG width in pixels
            height: SVG height in pixels
            hours: Hours to look back (for timeline layout)
            
        Returns:
            SVG string
        """
        if not nodes:
            return self._generate_empty_svg(width, height)
        
        # Import networkx here to avoid import errors
        try:
            import networkx as nx
        except ImportError:
            logger.error("NetworkX not available for graph visualization")
            return self._generate_error_svg(width, height, "Visualization library not available")
        
        # Create graph
        graph = self._create_networkx_graph(nodes, edges)
        
        # Calculate layout
        pos = self._calculate_layout(graph, layout_type, width, height, nodes, hours)
        
        # Generate SVG
        return self._render_svg(graph, pos, nodes, edges, width, height)
    
    def _generate_empty_svg(self, width: int, height: int) -> str:
        """Generate SVG for empty graph."""
        return f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
            <rect width="{width}" height="{height}" fill="#f8f9fa"/>
            <text x="{width//2}" y="{height//2}" text-anchor="middle" font-family="Arial" font-size="16" fill="#6c757d">
                No memories found
            </text>
        </svg>'''
    
    def _generate_error_svg(self, width: int, height: int, error_msg: str) -> str:
        """Generate SVG for error state."""
        return f'''<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">
            <rect width="{width}" height="{height}" fill="#fff5f5"/>
            <text x="{width//2}" y="{height//2}" text-anchor="middle" font-family="Arial" font-size="16" fill="#d63031">
                Error: {error_msg}
            </text>
        </svg>'''
    
    def _create_networkx_graph(
        self,
        nodes: List[GraphNode],
        edges: List[GraphEdge]
    ) -> "nx.Graph":
        """Create NetworkX graph from nodes and edges."""
        import networkx as nx
        
        G = nx.Graph()
        
        # Add nodes
        for node in nodes:
            G.add_node(node.id, data=node)
        
        # Add edges
        for edge in edges:
            if edge.source in G and edge.target in G:
                G.add_edge(
                    edge.source,
                    edge.target,
                    relationship=edge.relationship,
                    weight=edge.weight or 1.0,
                    data=edge
                )
        
        return G
    
    def _calculate_layout(
        self,
        graph: "nx.Graph",
        layout_type: LayoutType,
        width: int,
        height: int,
        nodes: List[GraphNode],
        hours: Optional[int] = None
    ) -> Dict[str, Tuple[float, float]]:
        """Calculate node positions based on layout type."""
        import networkx as nx
        
        # Add margins
        margin = 50
        effective_width = width - 2 * margin
        effective_height = height - 2 * margin
        
        if layout_type == LayoutType.TIMELINE:
            pos = self._timeline_layout(nodes, effective_width, effective_height, hours)
        elif layout_type == LayoutType.HIERARCHICAL:
            pos = self._hierarchical_layout(graph, effective_width, effective_height)
        else:  # FORCE
            pos = self._force_layout(graph, effective_width, effective_height)
        
        # Apply margins
        for node_id in pos:
            x, y = pos[node_id]
            pos[node_id] = (x + margin, y + margin)
        
        return pos
    
    def _timeline_layout(
        self,
        nodes: List[GraphNode],
        width: float,
        height: float,
        hours: Optional[int] = None
    ) -> Dict[str, Tuple[float, float]]:
        """Calculate timeline layout with nodes arranged by time."""
        pos = {}
        
        # Get time range
        now = datetime.now(timezone.utc)
        if hours:
            start_time = now - timedelta(hours=hours)
        else:
            # Find min time from nodes
            min_time = None
            for node in nodes:
                node_time = self._get_node_time(node)
                if node_time and (min_time is None or node_time < min_time):
                    min_time = node_time
            start_time = min_time or (now - timedelta(days=7))
        
        time_range = (now - start_time).total_seconds()
        if time_range <= 0:
            time_range = 1  # Prevent division by zero
        
        # Group nodes by type for y-positioning
        type_groups: Dict[NodeType, List[GraphNode]] = {}
        for node in nodes:
            if node.type not in type_groups:
                type_groups[node.type] = []
            type_groups[node.type].append(node)
        
        # Calculate y positions for each type
        num_types = len(type_groups)
        type_y_positions = {}
        if num_types > 0:
            y_step = height / (num_types + 1)
            for i, node_type in enumerate(sorted(type_groups.keys(), key=lambda t: t.value)):
                type_y_positions[node_type] = (i + 1) * y_step
        
        # Position nodes
        for node in nodes:
            # X position based on time
            node_time = self._get_node_time(node)
            if node_time:
                time_offset = (node_time - start_time).total_seconds()
                x = (time_offset / time_range) * width
            else:
                x = width / 2  # Default to center if no time
            
            # Y position based on type
            base_y = type_y_positions.get(node.type, height / 2)
            
            # Add some jitter to prevent overlap
            import random
            y = base_y + random.uniform(-20, 20)
            
            pos[node.id] = (x, y)
        
        return pos
    
    def _hierarchical_layout(
        self,
        graph: "nx.Graph",
        width: float,
        height: float
    ) -> Dict[str, Tuple[float, float]]:
        """Calculate hierarchical layout."""
        import networkx as nx
        
        try:
            # Try to create a tree layout
            if nx.is_tree(graph):
                pos = nx.spring_layout(graph, k=width/10, iterations=50)
            else:
                # Use spectral layout for non-trees
                pos = nx.spectral_layout(graph)
            
            # Scale to fit
            self._scale_positions(pos, width, height)
            
        except Exception as e:
            logger.warning(f"Hierarchical layout failed: {e}, falling back to spring")
            pos = nx.spring_layout(graph, k=width/10, iterations=50)
            self._scale_positions(pos, width, height)
        
        return pos
    
    def _force_layout(
        self,
        graph: "nx.Graph",
        width: float,
        height: float
    ) -> Dict[str, Tuple[float, float]]:
        """Calculate force-directed layout."""
        import networkx as nx
        
        # Use spring layout with appropriate parameters
        k = min(width, height) / (len(graph) ** 0.5) if len(graph) > 0 else 1
        pos = nx.spring_layout(
            graph,
            k=k,
            iterations=50,
            weight='weight',
            scale=min(width, height) / 2
        )
        
        # Scale to fit
        self._scale_positions(pos, width, height)
        
        return pos
    
    def _scale_positions(
        self,
        pos: Dict[str, Tuple[float, float]],
        width: float,
        height: float
    ) -> None:
        """Scale positions to fit within dimensions."""
        if not pos:
            return
        
        # Find bounds
        x_values = [p[0] for p in pos.values()]
        y_values = [p[1] for p in pos.values()]
        
        min_x, max_x = min(x_values), max(x_values)
        min_y, max_y = min(y_values), max(y_values)
        
        x_range = max_x - min_x if max_x > min_x else 1
        y_range = max_y - min_y if max_y > min_y else 1
        
        # Scale and center
        for node_id in pos:
            x, y = pos[node_id]
            new_x = ((x - min_x) / x_range) * width
            new_y = ((y - min_y) / y_range) * height
            pos[node_id] = (new_x, new_y)
    
    def _get_node_time(self, node: GraphNode) -> Optional[datetime]:
        """Extract timestamp from node."""
        if isinstance(node.attributes, dict):
            time_val = node.attributes.get('created_at') or node.attributes.get('timestamp')
        else:
            time_val = getattr(node.attributes, 'created_at', None)
        
        if not time_val and hasattr(node, 'updated_at'):
            time_val = node.updated_at
        
        if time_val:
            if isinstance(time_val, str):
                return datetime.fromisoformat(time_val.replace('Z', '+00:00'))
            elif isinstance(time_val, datetime):
                if time_val.tzinfo is None:
                    return time_val.replace(tzinfo=timezone.utc)
                return time_val
        
        return None
    
    def _render_svg(
        self,
        graph: "nx.Graph",
        pos: Dict[str, Tuple[float, float]],
        nodes: List[GraphNode],
        edges: List[GraphEdge],
        width: int,
        height: int
    ) -> str:
        """Render graph as SVG."""
        svg_parts = [
            f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg">',
            f'<rect width="{width}" height="{height}" fill="#f8f9fa"/>',
            self._generate_defs(),
        ]
        
        # Draw edges first (so they appear behind nodes)
        for edge in edges:
            if edge.source in pos and edge.target in pos:
                svg_parts.append(self._render_edge(edge, pos))
        
        # Draw nodes
        node_map = {node.id: node for node in nodes}
        for node_id, (x, y) in pos.items():
            if node_id in node_map:
                svg_parts.append(self._render_node(node_map[node_id], x, y))
        
        svg_parts.append('</svg>')
        return '\n'.join(svg_parts)
    
    def _generate_defs(self) -> str:
        """Generate SVG defs section with markers."""
        return '''<defs>
            <marker id="arrowhead-default" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 10 3.5, 0 7" fill="#999" />
            </marker>
            <marker id="arrowhead-primary" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 10 3.5, 0 7" fill="#4ECDC4" />
            </marker>
            <marker id="arrowhead-danger" markerWidth="10" markerHeight="7" refX="9" refY="3.5" orient="auto">
                <polygon points="0 0, 10 3.5, 0 7" fill="#FF6B6B" />
            </marker>
        </defs>'''
    
    def _render_edge(
        self,
        edge: GraphEdge,
        pos: Dict[str, Tuple[float, float]]
    ) -> str:
        """Render a single edge."""
        x1, y1 = pos[edge.source]
        x2, y2 = pos[edge.target]
        
        # Get edge style
        style = self.EDGE_STYLES.get(edge.relationship, EdgeStyle())
        
        # Calculate edge path
        stroke_dasharray = "5,5" if style.dashed else "none"
        
        return f'''<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" 
            stroke="{style.color}" 
            stroke-width="{style.width}" 
            stroke-dasharray="{stroke_dasharray}"
            marker-end="url(#arrowhead-default)" />'''
    
    def _render_node(
        self,
        node: GraphNode,
        x: float,
        y: float
    ) -> str:
        """Render a single node."""
        # Get node color
        color = self.NODE_COLORS.get(node.type, "#999")
        
        # Get node label
        label = self._get_node_label(node)
        
        # Render circle and label
        return f'''<g>
            <circle cx="{x}" cy="{y}" r="20" fill="{color}" stroke="#fff" stroke-width="2"/>
            <text x="{x}" y="{y + 30}" text-anchor="middle" font-family="Arial" font-size="12" fill="#2d3436">
                {self._escape_svg(label)}
            </text>
        </g>'''
    
    def _get_node_label(self, node: GraphNode) -> str:
        """Get display label for node."""
        # Try to get a meaningful label from attributes
        if isinstance(node.attributes, dict):
            # Check common label fields
            for field in ['name', 'title', 'label', 'content']:
                if field in node.attributes:
                    label = str(node.attributes[field])
                    # Truncate long labels
                    if len(label) > 20:
                        return label[:17] + "..."
                    return label
        
        # Fall back to node ID (truncated)
        if len(node.id) > 20:
            return node.id[:17] + "..."
        return node.id
    
    def _escape_svg(self, text: str) -> str:
        """Escape text for SVG."""
        return (text
            .replace('&', '&amp;')
            .replace('<', '&lt;')
            .replace('>', '&gt;')
            .replace('"', '&quot;')
            .replace("'", '&apos;'))