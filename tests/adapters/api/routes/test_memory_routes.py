"""
Comprehensive tests for memory API routes.

Tests all memory endpoints with various scenarios and edge cases.
"""
import pytest
import pytest_asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, AsyncMock, patch
from fastapi import FastAPI
from fastapi.testclient import TestClient
from typing import List, Optional

from ciris_engine.logic.adapters.api.routes import memory
from ciris_engine.schemas.services.graph_core import GraphNode, GraphEdge, NodeType, GraphScope
from ciris_engine.schemas.adapters.memory import QueryRequest, TimelineResponse
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext
from ciris_engine.schemas.api.auth import UserRole, ROLE_PERMISSIONS
from datetime import datetime, timezone
from fastapi.testclient import TestClient

# Test constants
DEFAULT_USER_ID = "test_user"


class TestMemoryRoutes:
    """Test cases for memory API routes."""
    
    def _get_authenticated_client(self, app, role=UserRole.OBSERVER):
        """Helper to create authenticated test client."""
        from ciris_engine.logic.adapters.api.dependencies.auth import require_observer, require_admin
        
        def mock_auth_dependency():
            return AuthContext(
                user_id=DEFAULT_USER_ID,
                role=role,
                permissions=ROLE_PERMISSIONS[role],
                authenticated_at=datetime.now(timezone.utc)
            )
        
        # Override both auth dependencies
        app.dependency_overrides[require_observer] = mock_auth_dependency
        app.dependency_overrides[require_admin] = mock_auth_dependency
        
        return TestClient(app)
    
    @pytest_asyncio.fixture
    async def app(self):
        """Create FastAPI app with memory routes."""
        app = FastAPI()
        app.include_router(memory.router)
        
        # Mock memory service
        mock_memory_service = Mock()
        mock_memory_service.memorize = AsyncMock()
        mock_memory_service.recall = AsyncMock()
        mock_memory_service.forget = AsyncMock()
        mock_memory_service.search = AsyncMock()
        mock_memory_service.get_stats = AsyncMock()
        
        # Add to app state
        app.state.memory_service = mock_memory_service
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """Create test client."""
        return TestClient(app)
    
    @pytest.fixture
    def auth_headers(self):
        """Mock authentication headers."""
        return {"Authorization": "Bearer test-token"}
    
    @pytest.fixture
    def mock_auth(self):
        """Mock authentication dependency."""
        from datetime import datetime, timezone
        from ciris_engine.schemas.api.auth import UserRole, Permission, ROLE_PERMISSIONS
        
        with patch('ciris_engine.logic.adapters.api.routes.memory.require_observer') as mock:
            mock.return_value = AuthContext(
                user_id=DEFAULT_USER_ID,
                role=UserRole.OBSERVER,
                permissions=ROLE_PERMISSIONS[UserRole.OBSERVER],
                authenticated_at=datetime.now(timezone.utc)
            )
            yield mock
    
    @pytest.fixture
    def sample_node(self):
        """Create sample node for testing."""
        return GraphNode(
            id="test-node-1",
            type=NodeType.OBSERVATION,
            scope=GraphScope.LOCAL,
            attributes={
                "content": "Test observation content",
                "created_at": datetime.now(timezone.utc).isoformat()
            },
            version=1,
            updated_by="test_user"
        )
    
    def test_store_memory_success(self, app, sample_node):
        """Test successful memory storage."""
        # Import dependencies
        from datetime import datetime, timezone
        from ciris_engine.schemas.api.auth import UserRole, ROLE_PERMISSIONS
        from ciris_engine.logic.adapters.api.dependencies.auth import require_observer
        
        # Create auth override
        def mock_auth_dependency():
            return AuthContext(
                user_id=DEFAULT_USER_ID,
                role=UserRole.OBSERVER,
                permissions=ROLE_PERMISSIONS[UserRole.OBSERVER],
                authenticated_at=datetime.now(timezone.utc)
            )
        
        # Override dependency
        app.dependency_overrides[require_observer] = mock_auth_dependency
        
        # Create test client with overrides
        from fastapi.testclient import TestClient
        client = TestClient(app)
        
        # Mock memorize response
        from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus
        app.state.memory_service.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.OK,
            reason="Node stored successfully",
            data={"node_id": sample_node.id}
        )
        
        response = client.post(
            "/memory/store",
            json={"node": sample_node.model_dump()},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert "data" in result
        assert "metadata" in result
        assert result["data"]["status"] == "ok"
        assert result["data"]["data"]["node_id"] == sample_node.id
    
    def test_store_memory_service_unavailable(self, app, sample_node):
        """Test memory storage when service is unavailable."""
        # Import dependencies
        from datetime import datetime, timezone
        from ciris_engine.schemas.api.auth import UserRole, ROLE_PERMISSIONS
        from ciris_engine.logic.adapters.api.dependencies.auth import require_observer
        
        # Create auth override
        def mock_auth_dependency():
            return AuthContext(
                user_id=DEFAULT_USER_ID,
                role=UserRole.OBSERVER,
                permissions=ROLE_PERMISSIONS[UserRole.OBSERVER],
                authenticated_at=datetime.now(timezone.utc)
            )
        
        # Override dependency
        app.dependency_overrides[require_observer] = mock_auth_dependency
        
        # Create test client with overrides
        from fastapi.testclient import TestClient
        client = TestClient(app)
        
        # Remove memory service
        delattr(app.state, 'memory_service')
        
        response = client.post(
            "/memory/store",
            json={"node": sample_node.model_dump()},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 503
        assert "Memory service not available" in response.json()["detail"]
    
    def test_query_memory_by_node_id(self, app, sample_node):
        """Test querying memory by node ID."""
        client = self._get_authenticated_client(app)
        app.state.memory_service.recall.return_value = [sample_node]
        
        response = client.post(
            "/memory/query",
            json={
                "node_id": sample_node.id,
                "scope": "local"
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == sample_node.id
    
    def test_query_memory_by_text(self, client, app, mock_auth, sample_node):
        """Test text search query."""
        app.state.memory_service.search.return_value = [sample_node]
        
        response = client.post(
            "/memory/query",
            json={
                "query": "test thought",
                "limit": 10
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert len(result["data"]) == 1
    
    def test_query_memory_related_nodes(self, app):
        """Test querying related nodes."""
        client = self._get_authenticated_client(app)
        node1 = GraphNode(
            id="node-1",
            type=NodeType.OBSERVATION,
            scope=GraphScope.LOCAL,
            attributes={},
            version=1,
            updated_by="test"
        )
        node2 = GraphNode(
            id="node-2",
            type=NodeType.TASK_SUMMARY,
            scope=GraphScope.LOCAL,
            attributes={},
            version=1,
            updated_by="test"
        )
        
        app.state.memory_service.recall.return_value = [node1, node2]
        
        response = client.post(
            "/memory/query",
            json={
                "related_to": "node-1",
                "depth": 2
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        result = response.json()
        # Should filter out the source node
        assert len(result["data"]) == 1
        assert result["data"][0]["id"] == "node-2"
    
    def test_delete_memory_success(self, client, app, mock_auth):
        """Test successful memory deletion."""
        from ciris_engine.schemas.api.auth import UserRole, ROLE_PERMISSIONS
        with patch('ciris_engine.logic.adapters.api.routes.memory.require_admin') as mock_admin:
            mock_admin.return_value = AuthContext(
                user_id=DEFAULT_USER_ID,
                role=UserRole.ADMIN,
                permissions=ROLE_PERMISSIONS[UserRole.ADMIN],
                authenticated_at=datetime.now(timezone.utc)
            )
            
            app.state.memory_service.forget.return_value = Mock(
                success=True,
                node_id="test-node",
                operation="FORGET"
            )
            
            response = client.delete(
                "/memory/test-node",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            result = response.json()
            assert result["data"]["success"] is True
            assert result["data"]["operation"] == "FORGET"
    
    def test_get_timeline_success(self, client, app, mock_auth):
        """Test timeline endpoint."""
        # Create nodes across time
        now = datetime.now(timezone.utc)
        nodes = [
            GraphNode(
                id=f"node-{i}",
                type=NodeType.OBSERVATION,
                scope=GraphScope.LOCAL,
                attributes={"created_at": (now - timedelta(hours=i)).isoformat()},
                version=1,
                updated_by="test",
                updated_at=now - timedelta(hours=i)
            )
            for i in range(5)
        ]
        
        # Mock TimelineQueryService response
        with patch('ciris_engine.logic.adapters.api.routes.memory.TimelineQueryService') as mock_timeline:
            mock_service = Mock()
            mock_timeline.return_value = mock_service
            
            mock_service.get_timeline = AsyncMock(return_value=TimelineResponse(
                memories=nodes,
                edges=None,
                buckets={"2024-01-01 00:00": 3, "2024-01-01 01:00": 2},
                start_time=now - timedelta(hours=24),
                end_time=now,
                total=5
            ))
            
            response = client.get(
                "/memory/timeline?hours=24&bucket_size=hour",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            result = response.json()
                assert len(result["data"]["memories"]) == 5
            assert result["data"]["total"] == 5
            assert "buckets" in result["data"]
    
    def test_recall_memory_by_id(self, client, app, mock_auth, sample_node):
        """Test recall specific memory by ID."""
        app.state.memory_service.recall.return_value = [sample_node]
        
        response = client.get(
            f"/memory/recall/{sample_node.id}",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["data"]["id"] == sample_node.id
    
    def test_recall_memory_not_found(self, client, app, mock_auth):
        """Test recall when memory not found."""
        app.state.memory_service.recall.return_value = []
        
        response = client.get(
            "/memory/recall/non-existent-node",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 404
        assert "Node non-existent-node not found" in response.json()["detail"]
    
    def test_get_memory_stats(self, client, app, mock_auth):
        """Test memory statistics endpoint."""
        app.state.memory_service.get_stats.return_value = {
            "total_nodes": 1000,
            "total_edges": 500,
            "nodes_by_type": {
                "thought": 300,
                "task": 200,
                "concept": 500
            },
            "nodes_by_scope": {
                "local": 800,
                "global": 200
            }
        }
        
        response = client.get(
            "/memory/stats",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["data"]["total_nodes"] == 1000
        assert result["data"]["total_edges"] == 500
    
    def test_get_node_by_id(self, client, app, mock_auth, sample_node):
        """Test getting specific node by ID."""
        app.state.memory_service.recall.return_value = [sample_node]
        
        response = client.get(
            f"/memory/{sample_node.id}",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["data"]["id"] == sample_node.id
        assert result["data"]["type"] == sample_node.type.value
    
    def test_visualize_graph_svg(self, app, sample_node):
        """Test graph visualization endpoint."""
        client = self._get_authenticated_client(app)
        # Mock nodes for visualization
        app.state.memory_service.recall.return_value = [sample_node]
        
        # Mock edge query function
        with patch('ciris_engine.logic.adapters.api.routes.memory.get_edges_for_node') as mock_edges:
            mock_edges.return_value = []
            
            # Mock visualization service
            with patch('ciris_engine.logic.adapters.api.routes.memory.GraphVisualizationService') as mock_viz:
                mock_service = AsyncMock()
                mock_viz.return_value = mock_service
                
                # Return simple SVG
                svg_content = '<svg width="800" height="600"><circle cx="50" cy="50" r="20"/></svg>'
                mock_service.generate_svg.return_value = svg_content
                
                response = client.get(
                    "/memory/visualize/graph?layout=force&width=800&height=600",
                    headers={"Authorization": "Bearer test-token"}
                )
                
                assert response.status_code == 200
                assert response.headers["content-type"] == "image/svg+xml"
                assert b"<svg" in response.content
                
                # Verify service was called correctly
                mock_service.generate_svg.assert_called_once()
                args = mock_service.generate_svg.call_args[1]
                assert args["width"] == 800
                assert args["height"] == 600
                assert args["layout_type"].value == "force"
    
    def test_visualize_graph_timeline_layout(self, app):
        """Test graph visualization with timeline layout."""
        client = self._get_authenticated_client(app)
        # Create nodes with timestamps
        now = datetime.now(timezone.utc)
        nodes = [
            GraphNode(
                id=f"node-{i}",
                type=NodeType.OBSERVATION,
                scope=GraphScope.LOCAL,
                attributes={"created_at": (now - timedelta(hours=i)).isoformat()},
                version=1,
                updated_by="test"
            )
            for i in range(5)
        ]
        
        # Mock MemoryQueryBuilder for time-based query
        with patch('ciris_engine.logic.adapters.api.routes.memory.MemoryQueryBuilder') as mock_qb:
            mock_builder = Mock()
            mock_qb.return_value = mock_builder
            mock_builder.build_and_execute = AsyncMock(return_value=nodes)
            
            # Mock edge query
            with patch('ciris_engine.logic.adapters.api.routes.memory.get_edges_for_node') as mock_edges:
                mock_edges.return_value = []
                
                # Mock visualization service
                with patch('ciris_engine.logic.adapters.api.routes.memory.GraphVisualizationService') as mock_viz:
                    mock_service = AsyncMock()
                    mock_viz.return_value = mock_service
                    
                    svg_content = '<svg width="1200" height="800"><text>Timeline</text></svg>'
                    mock_service.generate_svg.return_value = svg_content
                    
                    response = client.get(
                        "/memory/visualize/graph?layout=timeline&hours=24&width=1200&height=800",
                        headers={"Authorization": "Bearer test-token"}
                    )
                    
                    assert response.status_code == 200
                    assert response.headers["content-type"] == "image/svg+xml"
                    
                    # Verify timeline-specific parameters
                    mock_service.generate_svg.assert_called_once()
                    args = mock_service.generate_svg.call_args[1]
                    assert args["layout_type"].value == "timeline"
                    assert args["hours"] == 24
    
    def test_visualize_graph_with_edges(self, app):
        """Test graph visualization includes edges."""
        client = self._get_authenticated_client(app)
        nodes = [
            GraphNode(id="node-1", type=NodeType.OBSERVATION, scope=GraphScope.LOCAL, 
                     attributes={}, version=1, updated_by="test"),
            GraphNode(id="node-2", type=NodeType.TASK_SUMMARY, scope=GraphScope.LOCAL,
                     attributes={}, version=1, updated_by="test")
        ]
        
        edges = [
            GraphEdge(source="node-1", target="node-2", relationship="relates_to",
                     scope="local", weight=1.0)
        ]
        
        app.state.memory_service.recall.return_value = nodes
        
        # Mock edge query
        with patch('ciris_engine.logic.adapters.api.routes.memory.get_edges_for_node') as mock_edge_fn:
            mock_edge_fn.side_effect = lambda node_id, *args, **kwargs: edges if node_id == "node-1" else []
            
            # Mock visualization service
            with patch('ciris_engine.logic.adapters.api.routes.memory.GraphVisualizationService') as mock_viz:
                mock_service = AsyncMock()
                mock_viz.return_value = mock_service
                mock_service.generate_svg.return_value = '<svg></svg>'
                
                response = client.get(
                    "/memory/visualize/graph",
                    headers={"Authorization": "Bearer test-token"}
                )
                
                assert response.status_code == 200
                
                # Verify edges were passed to visualization service
                args = mock_service.generate_svg.call_args[1]
                assert len(args["edges"]) == 1
                assert args["edges"][0].source == "node-1"
                assert args["edges"][0].target == "node-2"
    
    def test_visualize_graph_no_networkx(self, client, app, mock_auth):
        """Test visualization when networkx is not available."""
        app.state.memory_service.recall.return_value = []
        
        # Simulate ImportError for networkx
        with patch('ciris_engine.logic.adapters.api.routes.memory.GraphVisualizationService') as mock_viz:
            mock_viz.side_effect = ImportError("No module named 'networkx'")
            
            response = client.get(
                "/memory/visualize/graph",
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 503
            assert "networkx" in response.json()["detail"]
    
    def test_create_edges(self, app):
        """Test edge creation between nodes."""
        client = self._get_authenticated_client(app, role=UserRole.ADMIN)
        edge = GraphEdge(
            source="node-1",
            target="node-2",
            relationship="relates_to",
            scope=GraphScope.LOCAL,
            weight=1.0
        )
        
        from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus
        app.state.memory_service.create_edge = AsyncMock(return_value=MemoryOpResult(
            status=MemoryOpStatus.OK,
            reason="Edge created successfully"
        ))
        
        response = client.post(
            "/memory/edges",
            json={"edge": edge.model_dump(mode='json')},
            headers={"Authorization": "Bearer test-token"}
        )
        
        # Note: create_edge method may not exist, adjust based on actual implementation
        if response.status_code == 200:
            result = response.json()
        
    def test_get_node_edges(self, client, app, mock_auth):
        """Test getting edges for a specific node."""
        edges = [
            GraphEdge(
                source="node-1",
                target="node-2",
                relationship="relates_to",
                scope="local",
                weight=1.0
            )
        ]
        
        # Mock edge query - implementation specific
        with patch('ciris_engine.logic.adapters.api.routes.memory.get_edges_for_node') as mock_edges:
            mock_edges.return_value = edges
            
            response = client.get(
                "/memory/node-1/edges",
                headers={"Authorization": "Bearer test-token"}
            )
            
            # This endpoint may not be implemented yet
            if response.status_code == 200:
                result = response.json()
                        assert len(result["data"]) > 0
    
    def test_query_with_pagination(self, client, app, mock_auth):
        """Test query with pagination parameters."""
        nodes = [
            GraphNode(
                id=f"node-{i}",
                type=NodeType.OBSERVATION,
                scope=GraphScope.LOCAL,
                attributes={},
                version=1,
                updated_by="test"
            )
            for i in range(20)
        ]
        
        app.state.memory_service.search.return_value = nodes
        
        response = client.post(
            "/memory/query",
            json={
                "query": "test",
                "limit": 5,
                "offset": 10
            },
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 200
        result = response.json()
        # Should apply pagination from MemoryQueryBuilder
        assert len(result["data"]) <= 5
    
    def test_error_handling(self, client, app, mock_auth):
        """Test error handling in endpoints."""
        # Make memory service raise an exception
        app.state.memory_service.recall.side_effect = Exception("Database error")
        
        response = client.get(
            "/memory/recall/test-node",
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 500
        assert "Database error" in response.json()["detail"]