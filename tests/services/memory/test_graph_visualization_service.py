"""
Tests for GraphVisualizationService.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from ciris_engine.logic.services.memory_service.graph_visualization_service import (
    GraphVisualizationService, LayoutType, NodeStyle, EdgeStyle
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphEdge, NodeType, GraphScope


class TestGraphVisualizationService:
    """Test cases for GraphVisualizationService."""
    
    @pytest.fixture
    def service(self):
        """Create visualization service instance."""
        return GraphVisualizationService()
    
    @pytest.fixture
    def sample_nodes(self):
        """Create sample nodes for testing."""
        now = datetime.now(timezone.utc)
        return [
            GraphNode(
                id="node-1",
                type=NodeType.THOUGHT,
                scope=GraphScope.LOCAL,
                attributes={"content": "Test thought", "created_at": now.isoformat()},
                version=1,
                updated_by="test"
            ),
            GraphNode(
                id="node-2",
                type=NodeType.TASK,
                scope=GraphScope.LOCAL,
                attributes={"title": "Test task", "created_at": (now - timedelta(hours=1)).isoformat()},
                version=1,
                updated_by="test"
            ),
            GraphNode(
                id="node-3",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={"name": "Test concept", "created_at": (now - timedelta(hours=2)).isoformat()},
                version=1,
                updated_by="test"
            )
        ]
    
    @pytest.fixture
    def sample_edges(self):
        """Create sample edges for testing."""
        return [
            GraphEdge(
                source="node-1",
                target="node-2",
                relationship="relates_to",
                scope="local",
                weight=1.0
            ),
            GraphEdge(
                source="node-2",
                target="node-3",
                relationship="depends_on",
                scope="local",
                weight=0.8
            )
        ]
    
    @pytest.mark.asyncio
    async def test_generate_empty_svg(self, service):
        """Test SVG generation for empty graph."""
        svg = await service.generate_svg(
            nodes=[],
            edges=[],
            layout_type=LayoutType.FORCE,
            width=800,
            height=600
        )
        
        assert '<svg width="800" height="600"' in svg
        assert "No memories found" in svg
    
    @pytest.mark.asyncio
    async def test_generate_svg_without_networkx(self, service, sample_nodes, sample_edges):
        """Test SVG generation when NetworkX is not available."""
        with patch.dict('sys.modules', {'networkx': None}):
            svg = await service.generate_svg(
                nodes=sample_nodes,
                edges=sample_edges,
                layout_type=LayoutType.FORCE,
                width=800,
                height=600
            )
            
            assert "Error:" in svg
            assert "Visualization library not available" in svg
    
    @pytest.mark.asyncio
    async def test_generate_svg_force_layout(self, service, sample_nodes, sample_edges):
        """Test SVG generation with force layout."""
        # Mock networkx to avoid dependency in tests
        with patch('ciris_engine.logic.services.memory_service.graph_visualization_service.nx') as mock_nx:
            # Mock graph
            mock_graph = Mock()
            mock_graph.__len__ = Mock(return_value=3)
            mock_nx.Graph.return_value = mock_graph
            
            # Mock layout positions
            mock_positions = {
                "node-1": (100, 100),
                "node-2": (200, 200),
                "node-3": (300, 300)
            }
            mock_nx.spring_layout.return_value = mock_positions
            
            svg = await service.generate_svg(
                nodes=sample_nodes,
                edges=sample_edges,
                layout_type=LayoutType.FORCE,
                width=800,
                height=600
            )
            
            # Verify SVG structure
            assert '<svg width="800" height="600"' in svg
            assert '<circle' in svg  # Nodes
            assert '<line' in svg    # Edges
            assert '</svg>' in svg
    
    @pytest.mark.asyncio
    async def test_generate_svg_timeline_layout(self, service, sample_nodes):
        """Test SVG generation with timeline layout."""
        with patch('ciris_engine.logic.services.memory_service.graph_visualization_service.nx'):
            svg = await service.generate_svg(
                nodes=sample_nodes,
                edges=[],
                layout_type=LayoutType.TIMELINE,
                width=1200,
                height=400,
                hours=24
            )
            
            assert '<svg width="1200" height="400"' in svg
    
    def test_node_colors(self, service):
        """Test node color mapping."""
        assert service.NODE_COLORS[NodeType.THOUGHT] == "#FF6B6B"
        assert service.NODE_COLORS[NodeType.TASK] == "#4ECDC4"
        assert service.NODE_COLORS[NodeType.CONCEPT] == "#A29BFE"
    
    def test_edge_styles(self, service):
        """Test edge style mapping."""
        replied_style = service.EDGE_STYLES["replied_to"]
        assert replied_style.color == "#74B9FF"
        assert replied_style.width == 2
        assert not replied_style.dashed
        
        thought_style = service.EDGE_STYLES["thought_about"]
        assert thought_style.dashed
    
    def test_get_node_time(self, service):
        """Test time extraction from nodes."""
        now = datetime.now(timezone.utc)
        
        # Test dict attributes with created_at
        node1 = GraphNode(
            id="test-1",
            type=NodeType.THOUGHT,
            scope=GraphScope.LOCAL,
            attributes={"created_at": now.isoformat()},
            version=1,
            updated_by="test"
        )
        
        time1 = service._get_node_time(node1)
        assert time1 is not None
        assert abs((time1 - now).total_seconds()) < 1
        
        # Test fallback to updated_at
        node2 = GraphNode(
            id="test-2",
            type=NodeType.THOUGHT,
            scope=GraphScope.LOCAL,
            attributes={},
            version=1,
            updated_by="test",
            updated_at=now
        )
        
        time2 = service._get_node_time(node2)
        assert time2 == now
    
    def test_get_node_label(self, service):
        """Test node label extraction."""
        # Test with name attribute
        node1 = GraphNode(
            id="very-long-node-id-that-should-be-truncated",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={"name": "Concept Name"},
            version=1,
            updated_by="test"
        )
        
        label1 = service._get_node_label(node1)
        assert label1 == "Concept Name"
        
        # Test with long content
        node2 = GraphNode(
            id="node-2",
            type=NodeType.THOUGHT,
            scope=GraphScope.LOCAL,
            attributes={"content": "This is a very long thought content that should be truncated"},
            version=1,
            updated_by="test"
        )
        
        label2 = service._get_node_label(node2)
        assert label2.endswith("...")
        assert len(label2) == 20
        
        # Test fallback to ID
        node3 = GraphNode(
            id="short-id",
            type=NodeType.TASK,
            scope=GraphScope.LOCAL,
            attributes={},
            version=1,
            updated_by="test"
        )
        
        label3 = service._get_node_label(node3)
        assert label3 == "short-id"
    
    def test_escape_svg(self, service):
        """Test SVG text escaping."""
        text = 'Test & <special> "chars" \'here\''
        escaped = service._escape_svg(text)
        
        assert '&amp;' in escaped
        assert '&lt;' in escaped
        assert '&gt;' in escaped
        assert '&quot;' in escaped
        assert '&apos;' in escaped
    
    def test_timeline_layout_calculation(self, service):
        """Test timeline layout position calculation."""
        now = datetime.now(timezone.utc)
        nodes = [
            GraphNode(
                id=f"node-{i}",
                type=NodeType.THOUGHT,
                scope=GraphScope.LOCAL,
                attributes={"created_at": (now - timedelta(hours=i)).isoformat()},
                version=1,
                updated_by="test"
            )
            for i in range(5)
        ]
        
        pos = service._timeline_layout(nodes, 1000, 600, hours=24)
        
        # Should have positions for all nodes
        assert len(pos) == 5
        
        # Nodes should be ordered by time along x-axis
        x_positions = [pos[f"node-{i}"][0] for i in range(5)]
        # Most recent (node-0) should be rightmost
        assert x_positions[0] > x_positions[4]
    
    def test_scale_positions(self, service):
        """Test position scaling."""
        pos = {
            "a": (0, 0),
            "b": (1, 1),
            "c": (0.5, 0.5)
        }
        
        service._scale_positions(pos, 100, 100)
        
        # Check scaling worked
        assert pos["a"] == (0, 0)
        assert pos["b"] == (100, 100)
        assert 45 < pos["c"][0] < 55  # Should be around 50