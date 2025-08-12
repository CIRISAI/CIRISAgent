"""
Comprehensive tests for memory.py API routes.

Tests all endpoints: store, recall, forget, timeline, create_edge.
Uses existing schemas from the codebase following Grace philosophy.
"""

import json
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

# Import route endpoints - use the actual function names from the routes
from ciris_engine.logic.adapters.api.routes.memory import get_timeline  # correct name
from ciris_engine.logic.adapters.api.routes.memory import query_memory  # correct name
from ciris_engine.logic.adapters.api.routes.memory import (
    CreateEdgeRequest,
    QueryRequest,
    StoreRequest,
    create_edge,
    forget_memory,
    recall_memory,
    router,
    store_memory,
)

# Import existing schemas - no new ones!
from ciris_engine.schemas.api.auth import AuthContext, Permission, UserRole
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphEdgeAttributes, GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@pytest.fixture
def mock_memory_service():
    """Create a mock memory service."""
    service = AsyncMock()
    service.memorize = AsyncMock()
    service.recall = AsyncMock()
    service.forget = AsyncMock()
    service.search = AsyncMock()
    service.create_edge = AsyncMock()
    return service


@pytest.fixture
def mock_request(mock_memory_service):
    """Create a mock request with memory service."""
    request = MagicMock()
    request.app.state.memory_service = mock_memory_service
    return request


@pytest.fixture
def sample_node():
    """Create a sample graph node for testing."""
    return GraphNode(
        id="test_node_1",
        type=NodeType.OBSERVATION,
        scope=GraphScope.LOCAL,
        attributes={"content": "Test memory", "timestamp": datetime.now(timezone.utc).isoformat()},
    )


@pytest.fixture
def sample_edge():
    """Create a sample graph edge for testing using correct field names."""
    return GraphEdge(
        source="node_1",
        target="node_2",
        relationship="relates_to",
        scope=GraphScope.LOCAL,
        weight=0.8,
        attributes=GraphEdgeAttributes(created_at=datetime.now(timezone.utc), context="test relationship"),
    )


@pytest.fixture
def auth_context():
    """Create a mock auth context using existing AuthContext schema."""
    return AuthContext(
        user_id="test_user",
        role=UserRole.ADMIN,
        permissions={
            Permission.VIEW_MEMORY,
            Permission.MANAGE_CONFIG,
            Permission.RUNTIME_CONTROL,
        },
        authenticated_at=datetime.now(timezone.utc),
    )


class TestStoreMemory:
    """Tests for the store_memory endpoint."""

    @pytest.mark.asyncio
    async def test_store_memory_success(self, mock_request, mock_memory_service, sample_node, auth_context):
        """Test successful memory storage."""
        # Setup - use correct MemoryOpResult structure
        mock_memory_service.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS, reason="Memory stored successfully", data={"node_id": sample_node.id}
        )

        # Execute
        with patch("ciris_engine.logic.adapters.api.routes.memory.require_admin", return_value=auth_context):
            response = await store_memory(mock_request, StoreRequest(node=sample_node), auth_context)

        # Assert
        assert response.data.status == MemoryOpStatus.SUCCESS
        assert response.data.data["node_id"] == sample_node.id
        mock_memory_service.memorize.assert_called_once_with(sample_node)

    @pytest.mark.asyncio
    async def test_store_memory_no_service(self, sample_node, auth_context):
        """Test store_memory when memory service is not available."""
        request = MagicMock()
        request.app.state.memory_service = None

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_admin", return_value=auth_context):
            with pytest.raises(HTTPException) as exc_info:
                await store_memory(request, StoreRequest(node=sample_node), auth_context)

        assert exc_info.value.status_code == 503
        assert "Memory service not available" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_store_memory_service_error(self, mock_request, mock_memory_service, sample_node, auth_context):
        """Test store_memory when service raises an error."""
        mock_memory_service.memorize.side_effect = Exception("Database error")

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_admin", return_value=auth_context):
            with pytest.raises(HTTPException) as exc_info:
                await store_memory(mock_request, StoreRequest(node=sample_node), auth_context)

        assert exc_info.value.status_code == 500
        assert "Database error" in str(exc_info.value.detail)


class TestRecallMemory:
    """Tests for the recall_memory endpoint."""

    @pytest.mark.asyncio
    async def test_recall_by_node_id(self, mock_request, mock_memory_service, sample_node, auth_context):
        """Test recall by specific node ID."""
        mock_memory_service.recall.return_value = [sample_node]

        query = QueryRequest(node_id="test_node_1")

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
            response = await query_memory(mock_request, query, auth_context)

        assert len(response.data) == 1
        assert response.data[0].id == sample_node.id
        mock_memory_service.recall.assert_called_once()

    @pytest.mark.asyncio
    async def test_recall_by_text_search(self, mock_request, mock_memory_service, sample_node, auth_context):
        """Test recall by text search query."""
        mock_memory_service.search.return_value = [sample_node]

        query = QueryRequest(query="test memory", limit=10)

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
            response = await query_memory(mock_request, query, auth_context)

        assert len(response.data) == 1
        mock_memory_service.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_recall_related_nodes(self, mock_request, mock_memory_service, auth_context):
        """Test recall of related nodes."""
        related_node = GraphNode(
            id="related_node",
            type=NodeType.OBSERVATION,
            scope=GraphScope.LOCAL,
            attributes={"content": "Related memory"},
        )
        source_node = GraphNode(
            id="source_node",
            type=NodeType.OBSERVATION,
            scope=GraphScope.LOCAL,
            attributes={"content": "Source memory"},
        )

        mock_memory_service.recall.return_value = [source_node, related_node]

        query = QueryRequest(related_to="source_node", include_edges=True, depth=2)

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
            response = await query_memory(mock_request, query, auth_context)

        # Should filter out the source node
        assert len(response.data) == 1
        assert response.data[0].id == "related_node"

    @pytest.mark.asyncio
    async def test_recall_by_type(self, mock_request, mock_memory_service, auth_context):
        """Test recall by node type."""
        typed_node = GraphNode(
            id="typed_node",
            type=NodeType.IDENTITY,
            scope=GraphScope.LOCAL,
            attributes={"name": "Test Identity"},
        )
        mock_memory_service.recall.return_value = [typed_node]

        query = QueryRequest(type=NodeType.IDENTITY)

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
            response = await query_memory(mock_request, query, auth_context)

        assert len(response.data) == 1
        assert response.data[0].type == NodeType.IDENTITY

    @pytest.mark.asyncio
    async def test_recall_with_time_filters(self, mock_request, mock_memory_service, auth_context):
        """Test recall with time-based filters."""
        now = datetime.now(timezone.utc)
        old_node = GraphNode(
            id="old_node",
            type=NodeType.OBSERVATION,
            scope=GraphScope.LOCAL,
            attributes={"content": "Old memory", "created_at": (now - timedelta(days=2)).isoformat()},
        )
        new_node = GraphNode(
            id="new_node",
            type=NodeType.OBSERVATION,
            scope=GraphScope.LOCAL,
            attributes={"content": "New memory", "created_at": now.isoformat()},
        )

        mock_memory_service.recall.return_value = [old_node, new_node]

        query = QueryRequest(type=NodeType.OBSERVATION, since=now - timedelta(days=1))

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
            response = await query_memory(mock_request, query, auth_context)

        # Should only return the new node
        assert len(response.data) == 1
        assert response.data[0].id == "new_node"

    @pytest.mark.asyncio
    async def test_recall_with_pagination(self, mock_request, mock_memory_service, auth_context):
        """Test recall with pagination."""
        nodes = [
            GraphNode(
                id=f"node_{i}",
                type=NodeType.OBSERVATION,
                scope=GraphScope.LOCAL,
                attributes={"content": f"Memory {i}"},
            )
            for i in range(10)
        ]
        mock_memory_service.recall.return_value = nodes

        query = QueryRequest(type=NodeType.OBSERVATION, limit=3, offset=2)

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
            response = await query_memory(mock_request, query, auth_context)

        assert len(response.data) == 3
        assert response.data[0].id == "node_2"
        assert response.data[2].id == "node_4"

    @pytest.mark.asyncio
    async def test_recall_no_service(self, auth_context):
        """Test recall when memory service is not available."""
        request = MagicMock()
        request.app.state.memory_service = None

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
            with pytest.raises(HTTPException) as exc_info:
                # recall_memory takes node_id as a direct parameter
                await recall_memory(request, "test", auth=auth_context)

        assert exc_info.value.status_code == 503


class TestForgetMemory:
    """Tests for the forget_memory endpoint."""

    @pytest.mark.asyncio
    async def test_forget_memory_success(self, mock_request, mock_memory_service, sample_node, auth_context):
        """Test successful memory deletion."""
        # The forget endpoint first recalls the node, then forgets it
        mock_memory_service.recall.return_value = [sample_node]
        mock_memory_service.forget.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS, reason="Memory forgotten", data={"node_id": "test_node_1"}
        )

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_admin", return_value=auth_context):
            response = await forget_memory(mock_request, "test_node_1", auth_context)

        assert response.data.status == MemoryOpStatus.SUCCESS
        assert response.data.data["node_id"] == "test_node_1"
        # Verify it was called with the node object, not the ID
        mock_memory_service.forget.assert_called_once_with(sample_node)

    @pytest.mark.asyncio
    async def test_forget_memory_not_found(self, mock_request, mock_memory_service, auth_context):
        """Test forget when node doesn't exist."""
        # Recall returns empty list when node not found
        mock_memory_service.recall.return_value = []

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_admin", return_value=auth_context):
            with pytest.raises(HTTPException) as exc_info:
                await forget_memory(mock_request, "nonexistent", auth_context)

        assert exc_info.value.status_code == 404
        assert "not found" in str(exc_info.value.detail).lower()


class TestCreateEdge:
    """Tests for the create_edge endpoint."""

    @pytest.mark.asyncio
    async def test_create_edge_success(self, mock_request, mock_memory_service, sample_edge, auth_context):
        """Test successful edge creation."""
        mock_memory_service.create_edge.return_value = MemoryOpResult(
            status=MemoryOpStatus.SUCCESS,
            reason="Edge created",
            data={"edge_id": f"{sample_edge.source}->{sample_edge.target}"},
        )

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_admin", return_value=auth_context):
            response = await create_edge(mock_request, CreateEdgeRequest(edge=sample_edge), auth_context)

        assert response.data.status == MemoryOpStatus.SUCCESS
        mock_memory_service.create_edge.assert_called_once_with(sample_edge)

    @pytest.mark.asyncio
    async def test_create_edge_service_error(self, mock_request, mock_memory_service, sample_edge, auth_context):
        """Test edge creation when service fails."""
        mock_memory_service.create_edge.side_effect = Exception("Graph error")

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_admin", return_value=auth_context):
            with pytest.raises(HTTPException) as exc_info:
                await create_edge(mock_request, CreateEdgeRequest(edge=sample_edge), auth_context)

        assert exc_info.value.status_code == 500
        assert "Graph error" in str(exc_info.value.detail)


class TestMemoryTimeline:
    """Tests for the get_memory_timeline endpoint."""

    @pytest.mark.asyncio
    async def test_timeline_direct_db_query(self, auth_context):
        """Test timeline retrieval using direct database query."""
        request = MagicMock()
        request.app.state.memory_service = None  # Force direct DB path

        # Mock database connection
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            (
                "node_1",
                "LOCAL",
                "observation",
                '{"content": "Test"}',
                1,
                "system",
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            )
        ]

        with patch("ciris_engine.logic.adapters.api.routes.memory.get_db_connection", return_value=mock_conn):
            with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
                response = await get_timeline(
                    request, hours=24, scope=GraphScope.LOCAL, node_type=NodeType.OBSERVATION, auth=auth_context
                )

        assert len(response.data) == 1
        assert response.data[0].id == "node_1"
        assert response.data[0].type == NodeType.OBSERVATION

    @pytest.mark.asyncio
    async def test_timeline_with_memory_service(self, mock_request, mock_memory_service, auth_context):
        """Test timeline retrieval using memory service."""
        nodes = [
            GraphNode(
                id=f"node_{i}",
                type=NodeType.OBSERVATION,
                scope=GraphScope.LOCAL,
                attributes={"content": f"Memory {i}", "created_at": datetime.now(timezone.utc).isoformat()},
            )
            for i in range(5)
        ]
        mock_memory_service.search.return_value = nodes

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
            response = await get_timeline(mock_request, hours=12, auth=auth_context)

        assert len(response.data) == 5
        mock_memory_service.search.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeline_empty_result(self, mock_request, mock_memory_service, auth_context):
        """Test timeline with no matching memories."""
        mock_memory_service.search.return_value = []

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
            response = await get_timeline(mock_request, hours=1, auth=auth_context)

        assert len(response.data) == 0
        assert response.data == []


class TestQueryValidation:
    """Tests for query validation."""

    def test_query_requires_at_least_one_field(self):
        """Test that QueryRequest requires at least one query field."""
        # This should be valid - has node_id
        query = QueryRequest(node_id="test")
        assert query.node_id == "test"

        # This should be valid - has query text
        query = QueryRequest(query="search text")
        assert query.query == "search text"

        # This should be valid - has type
        query = QueryRequest(type=NodeType.OBSERVATION)
        assert query.type == NodeType.OBSERVATION

    def test_query_pagination_limits(self):
        """Test pagination parameter limits."""
        # Valid limit
        query = QueryRequest(node_id="test", limit=100)
        assert query.limit == 100

        # Invalid limit (too high) should raise validation error
        with pytest.raises(ValueError):
            QueryRequest(node_id="test", limit=10000)

        # Invalid offset (negative) should raise validation error
        with pytest.raises(ValueError):
            QueryRequest(node_id="test", offset=-1)

    def test_query_depth_limits(self):
        """Test graph traversal depth limits."""
        # Valid depth
        query = QueryRequest(related_to="node", depth=2)
        assert query.depth == 2

        # Invalid depth (too high) should raise validation error
        with pytest.raises(ValueError):
            QueryRequest(related_to="node", depth=10)


class TestErrorHandling:
    """Tests for error handling across all endpoints."""

    @pytest.mark.asyncio
    async def test_store_handles_validation_error(self, mock_request, mock_memory_service, sample_node, auth_context):
        """Test store endpoint handles validation errors gracefully."""
        from pydantic import ValidationError

        mock_memory_service.memorize.side_effect = ValidationError.from_exception_data(
            "ValidationError", [{"type": "value_error", "loc": ("field",), "msg": "Invalid value"}]
        )

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_admin", return_value=auth_context):
            with pytest.raises(HTTPException) as exc_info:
                await store_memory(mock_request, StoreRequest(node=sample_node), auth_context)

        assert exc_info.value.status_code == 500

    @pytest.mark.asyncio
    async def test_recall_handles_network_error(self, mock_request, mock_memory_service, auth_context):
        """Test recall endpoint handles network errors."""
        mock_memory_service.recall.side_effect = ConnectionError("Network unreachable")

        query = QueryRequest(node_id="test")

        with patch("ciris_engine.logic.adapters.api.routes.memory.require_observer", return_value=auth_context):
            with pytest.raises(HTTPException) as exc_info:
                await recall_memory(mock_request, query, auth_context)

        assert exc_info.value.status_code == 500
        assert "Network unreachable" in str(exc_info.value.detail)
