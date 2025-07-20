"""
Tests for TimelineQueryService.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch, call
from typing import List, Dict, Any

from ciris_engine.logic.services.memory_service.timeline_query_service import TimelineQueryService
from ciris_engine.schemas.services.graph_core import GraphNode, GraphEdge, GraphScope, NodeType, GraphEdgeAttributes
from ciris_engine.schemas.adapters.memory import TimelineResponse


class TestTimelineQueryService:
    """Test cases for TimelineQueryService."""
    
    @pytest.fixture
    def mock_memory_service(self):
        """Create mock memory service."""
        return Mock()
    
    @pytest.fixture
    def service(self, mock_memory_service):
        """Create timeline query service instance."""
        return TimelineQueryService(mock_memory_service)
    
    @pytest.fixture
    def sample_nodes(self):
        """Create sample nodes for testing."""
        now = datetime.now(timezone.utc)
        nodes = []
        
        # Create nodes across different hours
        for i in range(10):
            node = GraphNode(
                id=f"node-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={
                    "created_at": (now - timedelta(hours=i)).isoformat(),
                    "content": f"Test node {i}"
                },
                version=1,
                updated_by="test",
                updated_at=now - timedelta(hours=i)
            )
            nodes.append(node)
            
        return nodes
    
    @pytest.mark.asyncio
    async def test_get_timeline_basic(self, service, sample_nodes):
        """Test basic timeline query."""
        with patch('ciris_engine.logic.services.memory_service.timeline_query_service.get_db_connection') as mock_db:
            # Mock database connection and cursor
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.__exit__.return_value = None
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn
            
            # Mock database rows
            mock_rows = []
            for node in sample_nodes[:5]:
                mock_rows.append({
                    'node_id': node.id,
                    'scope': node.scope.value,
                    'node_type': node.type.value,
                    'attributes_json': '{"created_at": "' + node.attributes['created_at'] + '"}',
                    'version': node.version,
                    'updated_by': node.updated_by,
                    'updated_at': node.updated_at.isoformat()
                })
            
            mock_cursor.fetchall.return_value = mock_rows
            
            # Execute timeline query
            result = await service.get_timeline(
                hours=24,
                bucket_size="hour",
                limit=10
            )
            
            # Verify result
            assert isinstance(result, TimelineResponse)
            assert len(result.memories) <= 10
            assert result.total >= 0
            assert result.buckets is not None
            assert result.start_time is not None
            assert result.end_time is not None
    
    @pytest.mark.asyncio
    async def test_get_timeline_with_filters(self, service):
        """Test timeline query with scope and type filters."""
        with patch('ciris_engine.logic.services.memory_service.timeline_query_service.get_db_connection') as mock_db:
            # Mock database
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.__exit__.return_value = None
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn
            
            mock_cursor.fetchall.return_value = []
            
            # Execute with filters
            result = await service.get_timeline(
                hours=48,
                bucket_size="day",
                scope=GraphScope.GLOBAL,
                node_type=NodeType.TASK,
                limit=50
            )
            
            # Verify SQL was called with filters
            calls = mock_cursor.execute.call_args_list
            assert len(calls) > 0
            
            # Check that filters were included in query
            for call_args in calls:
                query = call_args[0][0]
                params = call_args[0][1]
                
                if "scope = ?" in query:
                    assert GraphScope.GLOBAL.value in params
                if "node_type = ?" in query:
                    assert NodeType.TASK.value in params
    
    @pytest.mark.asyncio
    async def test_get_timeline_with_edges(self, service, sample_nodes):
        """Test timeline query with edge fetching."""
        with patch('ciris_engine.logic.services.memory_service.timeline_query_service.get_db_connection') as mock_db:
            # Mock database for nodes
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.__exit__.return_value = None
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn
            
            # First call returns nodes
            node_rows = [{
                'node_id': 'node-1',
                'scope': 'local',
                'node_type': 'concept',
                'attributes_json': '{"created_at": "2024-01-01T00:00:00+00:00"}',
                'version': 1,
                'updated_by': 'test',
                'updated_at': '2024-01-01T00:00:00+00:00'
            }]
            
            # Second call returns edges
            edge_rows = [(
                'edge-1',  # edge_id
                'node-1',  # source_node_id
                'node-2',  # target_node_id
                'local',   # scope
                'relates_to',  # relationship
                1.0,       # weight
                '{"context": "test"}',  # attributes_json
                '2024-01-01T00:00:00+00:00'  # created_at
            )]
            
            mock_cursor.fetchall.side_effect = [node_rows, edge_rows]
            
            # Execute with edge fetching
            result = await service.get_timeline(
                hours=1,
                bucket_size="hour",
                limit=10,
                include_edges=True
            )
            
            # Verify edges were fetched
            assert result.edges is not None
            assert len(result.edges) == 1
            assert result.edges[0].source == 'node-1'
            assert result.edges[0].target == 'node-2'
    
    @pytest.mark.asyncio
    async def test_fallback_to_memory_service(self, service, mock_memory_service):
        """Test fallback to memory service when direct query fails."""
        with patch('ciris_engine.logic.services.memory_service.timeline_query_service.get_db_connection') as mock_db:
            # Make database connection fail
            mock_db.side_effect = Exception("Database error")
            
            # Mock memory service response
            now = datetime.now(timezone.utc)
            mock_nodes = [
                GraphNode(
                    id="fallback-node",
                    type=NodeType.CONCEPT,
                    scope=GraphScope.LOCAL,
                    attributes={"created_at": now.isoformat()},
                    version=1,
                    updated_by="test",
                    updated_at=now
                )
            ]
            mock_memory_service.search.return_value = mock_nodes
            
            # Execute timeline query
            result = await service.get_timeline(
                hours=24,
                bucket_size="hour",
                limit=10
            )
            
            # Verify fallback was used
            mock_memory_service.search.assert_called_once()
            assert len(result.memories) == 1
            assert result.memories[0].id == "fallback-node"
    
    def test_time_bucket_creation(self, service):
        """Test time bucket creation logic."""
        now = datetime.now(timezone.utc)
        start_time = now - timedelta(hours=3)
        
        # Create nodes at different times
        nodes = [
            GraphNode(
                id=f"node-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={"created_at": (now - timedelta(hours=i)).isoformat()},
                version=1,
                updated_by="test",
                updated_at=now - timedelta(hours=i)
            )
            for i in range(3)
        ]
        
        # Test hour buckets
        hour_buckets = service._create_time_buckets(
            nodes, start_time, now, "hour"
        )
        
        # Should have 3 hour buckets
        assert len(hour_buckets) >= 3
        
        # Test day buckets
        day_buckets = service._create_time_buckets(
            nodes, start_time, now, "day"
        )
        
        # Should have 1 day bucket
        assert len(day_buckets) >= 1
    
    def test_node_time_extraction(self, service):
        """Test extracting time from nodes with different attribute structures."""
        now = datetime.now(timezone.utc)
        
        # Node with dict attributes and created_at
        node1 = GraphNode(
            id="node-1",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={"created_at": now.isoformat()},
            version=1,
            updated_by="test"
        )
        
        # Node with dict attributes and timestamp
        node2 = GraphNode(
            id="node-2",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={"timestamp": (now - timedelta(hours=1)).isoformat()},
            version=1,
            updated_by="test"
        )
        
        # Node with updated_at
        node3 = GraphNode(
            id="node-3",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={},
            version=1,
            updated_by="test",
            updated_at=now - timedelta(hours=2)
        )
        
        # Test time extraction
        time1 = service._get_node_time(node1)
        time2 = service._get_node_time(node2)
        time3 = service._get_node_time(node3)
        
        assert time1 is not None
        assert time2 is not None
        assert time3 is not None
        assert time1 > time2 > time3
    
    def test_node_sampling(self, service):
        """Test even sampling of nodes across time buckets."""
        now = datetime.now(timezone.utc)
        
        # Create many nodes across different hours
        nodes = []
        for hour in range(24):
            # Create multiple nodes per hour
            for i in range(5):
                node = GraphNode(
                    id=f"node-{hour}-{i}",
                    type=NodeType.CONCEPT,
                    scope=GraphScope.LOCAL,
                    attributes={},
                    version=1,
                    updated_by="test",
                    updated_at=now - timedelta(hours=hour, minutes=i)
                )
                nodes.append(node)
        
        # Sample to get 50 nodes from 120 total
        sampled = service._sample_nodes_evenly(nodes, 50)
        
        assert len(sampled) == 50
        
        # Check that we have representation from multiple hours
        hours_represented = set()
        for node in sampled:
            if node.updated_at:
                hours_represented.add(node.updated_at.hour)
        
        # Should have nodes from multiple hours
        assert len(hours_represented) > 10