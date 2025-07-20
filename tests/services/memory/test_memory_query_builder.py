"""
Tests for MemoryQueryBuilder.
"""
import pytest
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, MagicMock, patch
from typing import List

from ciris_engine.logic.services.memory_service.memory_query_builder import (
    MemoryQueryBuilder, QueryType
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.adapters.memory import QueryRequest, MemorySearchFilter
from ciris_engine.schemas.services.operations import MemoryQuery


class TestMemoryQueryBuilder:
    """Test cases for MemoryQueryBuilder."""
    
    @pytest.fixture
    def mock_memory_service(self):
        """Create mock memory service."""
        return Mock()
    
    @pytest.fixture
    def builder(self, mock_memory_service):
        """Create query builder instance."""
        return MemoryQueryBuilder(mock_memory_service)
    
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
                updated_by="test",
                updated_at=now
            ),
            GraphNode(
                id="node-2",
                type=NodeType.TASK,
                scope=GraphScope.GLOBAL,
                attributes={"title": "Test task", "created_at": (now - timedelta(hours=1)).isoformat()},
                version=1,
                updated_by="test",
                updated_at=now - timedelta(hours=1)
            )
        ]
    
    def test_determine_query_type(self, builder):
        """Test query type determination."""
        # Node ID query
        req1 = QueryRequest(node_id="node-123")
        assert builder.determine_query_type(req1) == QueryType.NODE_ID
        
        # Text search query
        req2 = QueryRequest(query="search text")
        assert builder.determine_query_type(req2) == QueryType.TEXT_SEARCH
        
        # Related nodes query
        req3 = QueryRequest(related_to="node-456")
        assert builder.determine_query_type(req3) == QueryType.RELATED
        
        # Time range query
        req4 = QueryRequest(since=datetime.now(timezone.utc) - timedelta(hours=1))
        assert builder.determine_query_type(req4) == QueryType.TIME_RANGE
        
        # Type filter query
        req5 = QueryRequest(type=NodeType.TASK)
        assert builder.determine_query_type(req5) == QueryType.TYPE_FILTER
        
        # Wildcard query
        req6 = QueryRequest(node_id="*")
        assert builder.determine_query_type(req6) == QueryType.WILDCARD
    
    @pytest.mark.asyncio
    async def test_query_by_node_id(self, builder, mock_memory_service, sample_nodes):
        """Test querying by node ID."""
        mock_memory_service.recall.return_value = [sample_nodes[0]]
        
        request = QueryRequest(
            node_id="node-1",
            scope=GraphScope.LOCAL,
            include_edges=True
        )
        
        result = await builder.build_and_execute(request)
        
        # Verify correct query was made
        mock_memory_service.recall.assert_called_once()
        call_args = mock_memory_service.recall.call_args[0][0]
        assert isinstance(call_args, MemoryQuery)
        assert call_args.node_id == "node-1"
        assert call_args.scope == GraphScope.LOCAL
        assert call_args.include_edges is True
        
        assert len(result) == 1
        assert result[0].id == "node-1"
    
    @pytest.mark.asyncio
    async def test_query_by_text(self, builder, mock_memory_service, sample_nodes):
        """Test text search query."""
        mock_memory_service.search.return_value = sample_nodes
        
        request = QueryRequest(
            query="test",
            scope=GraphScope.LOCAL,
            limit=10
        )
        
        result = await builder.build_and_execute(request)
        
        # Verify search was called
        mock_memory_service.search.assert_called_once_with(
            "test",
            filters=MemorySearchFilter(
                scope=GraphScope.LOCAL.value,
                node_type=None,
                tags=None,
                limit=10
            )
        )
        
        assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_query_by_text_with_time_filter(self, builder, mock_memory_service, sample_nodes):
        """Test text search with time filtering."""
        mock_memory_service.search.return_value = sample_nodes
        
        now = datetime.now(timezone.utc)
        request = QueryRequest(
            query="test",
            since=now - timedelta(minutes=30),
            until=now,
            limit=10
        )
        
        result = await builder.build_and_execute(request)
        
        # Should only return the recent node
        assert len(result) == 1
        assert result[0].id == "node-1"
    
    @pytest.mark.asyncio
    async def test_query_related_nodes(self, builder, mock_memory_service, sample_nodes):
        """Test querying related nodes."""
        # Return both nodes as if they're related
        mock_memory_service.recall.return_value = sample_nodes
        
        request = QueryRequest(
            related_to="node-1",
            depth=2
        )
        
        result = await builder.build_and_execute(request)
        
        # Should filter out the source node
        assert len(result) == 1
        assert result[0].id == "node-2"
    
    @pytest.mark.asyncio
    async def test_query_by_time_range_with_db(self, builder):
        """Test time range query with direct database access."""
        with patch('ciris_engine.logic.services.memory_service.memory_query_builder.get_db_connection') as mock_db:
            # Mock database connection
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.__enter__.return_value = mock_conn
            mock_conn.__exit__.return_value = None
            mock_conn.cursor.return_value = mock_cursor
            mock_db.return_value = mock_conn
            
            # Mock database results
            now = datetime.now(timezone.utc)
            mock_cursor.fetchall.return_value = [{
                'node_id': 'time-node',
                'scope': 'local',
                'node_type': 'thought',
                'attributes_json': '{"content": "Time-based node"}',
                'version': 1,
                'updated_by': 'test',
                'updated_at': now.isoformat()
            }]
            
            request = QueryRequest(
                since=now - timedelta(hours=1),
                until=now,
                scope=GraphScope.LOCAL,
                limit=50
            )
            
            result = await builder.build_and_execute(request)
            
            # Verify SQL was executed
            mock_cursor.execute.assert_called_once()
            query = mock_cursor.execute.call_args[0][0]
            assert "WHERE updated_at >= ?" in query
            assert "AND scope = ?" in query
            assert "ORDER BY updated_at DESC" in query
            
            assert len(result) == 1
            assert result[0].id == "time-node"
    
    @pytest.mark.asyncio
    async def test_query_by_time_range_fallback(self, builder, mock_memory_service, sample_nodes):
        """Test time range query fallback when DB fails."""
        with patch('ciris_engine.logic.services.memory_service.memory_query_builder.get_db_connection') as mock_db:
            # Make DB connection fail
            mock_db.side_effect = Exception("Database error")
            
            # Mock fallback response
            mock_memory_service.recall.return_value = sample_nodes
            
            now = datetime.now(timezone.utc)
            request = QueryRequest(
                since=now - timedelta(hours=2),
                until=now
            )
            
            result = await builder.build_and_execute(request)
            
            # Should have used fallback
            mock_memory_service.recall.assert_called_once()
            assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_query_by_type(self, builder, mock_memory_service):
        """Test querying by node type."""
        task_nodes = [
            GraphNode(
                id="task-1",
                type=NodeType.TASK,
                scope=GraphScope.LOCAL,
                attributes={},
                version=1,
                updated_by="test"
            )
        ]
        
        mock_memory_service.recall.return_value = task_nodes
        
        request = QueryRequest(
            type=NodeType.TASK,
            scope=GraphScope.LOCAL
        )
        
        result = await builder.build_and_execute(request)
        
        # Verify type filter was applied
        call_args = mock_memory_service.recall.call_args[0][0]
        assert call_args.type == NodeType.TASK
        
        assert len(result) == 1
        assert result[0].type == NodeType.TASK
    
    def test_get_node_time(self, builder):
        """Test time extraction from nodes."""
        now = datetime.now(timezone.utc)
        
        # Test with dict attributes
        node1 = GraphNode(
            id="test-1",
            type=NodeType.THOUGHT,
            scope=GraphScope.LOCAL,
            attributes={"created_at": now.isoformat()},
            version=1,
            updated_by="test"
        )
        
        time1 = builder._get_node_time(node1)
        assert time1 is not None
        assert abs((time1 - now).total_seconds()) < 1
        
        # Test with updated_at fallback
        node2 = GraphNode(
            id="test-2",
            type=NodeType.THOUGHT,
            scope=GraphScope.LOCAL,
            attributes={},
            version=1,
            updated_by="test",
            updated_at=now
        )
        
        time2 = builder._get_node_time(node2)
        assert time2 == now
        
        # Test with no time
        node3 = GraphNode(
            id="test-3",
            type=NodeType.THOUGHT,
            scope=GraphScope.LOCAL,
            attributes={},
            version=1,
            updated_by="test"
        )
        
        time3 = builder._get_node_time(node3)
        assert time3 is None
    
    def test_filter_by_time(self, builder, sample_nodes):
        """Test time filtering of nodes."""
        now = datetime.now(timezone.utc)
        
        # Filter to last 30 minutes
        filtered = builder._filter_by_time(
            sample_nodes,
            since=now - timedelta(minutes=30),
            until=now
        )
        
        # Should only include the recent node
        assert len(filtered) == 1
        assert filtered[0].id == "node-1"
        
        # Filter to exclude all
        filtered2 = builder._filter_by_time(
            sample_nodes,
            since=now + timedelta(hours=1),
            until=now + timedelta(hours=2)
        )
        
        assert len(filtered2) == 0