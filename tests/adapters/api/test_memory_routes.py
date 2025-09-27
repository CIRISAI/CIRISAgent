"""
Integration tests for memory.py API routes.

Tests the actual API endpoints using FastAPI TestClient.
Uses existing schemas from the codebase - no new schemas!
"""

import json
from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import require_admin, require_observer

# Import the router we're testing
from ciris_engine.logic.adapters.api.routes.memory import router

# Import EXISTING schemas - no new ones!
from ciris_engine.schemas.api.auth import AuthContext, Permission, UserRole
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphEdgeAttributes, GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus, MemoryQuery


@pytest.fixture
def app():
    """Create a FastAPI app with the memory router."""
    app = FastAPI()
    app.include_router(router)

    # Mock memory service
    mock_memory_service = AsyncMock()
    app.state.memory_service = mock_memory_service

    # Mock auth service (required by auth dependencies)
    mock_auth_service = MagicMock()
    app.state.auth_service = mock_auth_service

    return app


@pytest.fixture
def client(app):
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def auth_context():
    """Create a valid auth context."""
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


@pytest.fixture
def sample_node():
    """Create a sample GraphNode using existing schema."""
    return GraphNode(
        id="test_node_1",
        type=NodeType.OBSERVATION,
        scope=GraphScope.LOCAL,
        attributes={"content": "Test memory", "timestamp": datetime.now(timezone.utc).isoformat()},
    )


@pytest.fixture
def sample_edge():
    """Create a sample GraphEdge using existing schema."""
    return GraphEdge(
        source="node_1",
        target="node_2",
        relationship="relates_to",
        scope=GraphScope.LOCAL,
        weight=0.8,
        attributes=GraphEdgeAttributes(created_at=datetime.now(timezone.utc), context="test relationship"),
    )


class TestStoreMemory:
    """Test the /memory/store endpoint."""

    def test_store_memory_success(self, client, app, sample_node, auth_context):
        """Test successful memory storage."""
        # Setup mock response
        app.state.memory_service.memorize.return_value = MemoryOpResult(
            status=MemoryOpStatus.OK, reason="Memory stored successfully", data={"node_id": sample_node.id}
        )

        # Mock auth dependency - need to override the dependency directly
        def override_auth():
            return auth_context

        app.dependency_overrides[require_admin] = override_auth

        response = client.post(
            "/memory/store",
            json={"node": sample_node.model_dump(mode="json")},
        )

        assert response.status_code == 200
        data = response.json()
        # Response has data and metadata at top level
        assert "data" in data
        assert "metadata" in data
        # The MemoryOpResult is in data["data"]
        assert data["data"]["status"] == "ok"
        assert data["data"]["data"]["node_id"] == sample_node.id

    def test_store_memory_no_service(self, client, app, sample_node, auth_context):
        """Test when memory service is not available."""
        app.state.memory_service = None
        app.dependency_overrides[require_admin] = lambda: auth_context

        response = client.post(
            "/memory/store",
            json={"node": sample_node.model_dump(mode="json")},
        )

        assert response.status_code == 503
        assert "Memory service not available" in response.json()["detail"]


class TestQueryMemory:
    """Test the /memory/query endpoint."""

    def test_query_by_node_id(self, client, app, sample_node, auth_context):
        """Test querying by specific node ID."""
        # The route uses recall method with a MemoryQuery
        # Mock the recall method to return a list with the sample node
        app.state.memory_service.recall = AsyncMock(return_value=[sample_node])
        app.dependency_overrides[require_observer] = lambda: auth_context

        response = client.post(
            "/memory/query",
            json={"node_id": "test_node_1"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1
        assert data["data"][0]["id"] == sample_node.id

    def test_query_by_type(self, client, app, sample_node, auth_context, monkeypatch):
        """Test querying by node type."""

        # Mock the search_nodes function since it queries the database
        async def mock_search_nodes(**kwargs):
            return [sample_node]

        monkeypatch.setattr("ciris_engine.logic.adapters.api.routes.memory.search_nodes", mock_search_nodes)
        app.dependency_overrides[require_observer] = lambda: auth_context

        response = client.post(
            "/memory/query",
            json={"type": "observation"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 1

    def test_query_requires_at_least_one_param(self, client, app, auth_context, monkeypatch):
        """Test that query requires at least one parameter."""

        # The API now allows empty queries and uses search_nodes for general search
        async def mock_search_nodes(**kwargs):
            return []  # Return empty list for empty query

        monkeypatch.setattr("ciris_engine.logic.adapters.api.routes.memory.search_nodes", mock_search_nodes)
        app.dependency_overrides[require_observer] = lambda: auth_context

        response = client.post(
            "/memory/query",
            json={},  # No query parameters
        )

        # API now accepts empty queries and returns empty results
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert len(data["data"]) == 0


class TestMemoryTimeline:
    """Test the /memory/timeline endpoint."""

    def test_timeline_default_params(self, client, app, auth_context):
        """Test timeline with default parameters."""
        # Mock the database query for timeline
        nodes = [
            GraphNode(
                id=f"node_{i}", type=NodeType.OBSERVATION, scope=GraphScope.LOCAL, attributes={"content": f"Memory {i}"}
            )
            for i in range(5)
        ]

        # The timeline endpoint does a direct DB query, so we need to mock that
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = [
            (
                f"node_{i}",
                "LOCAL",
                "observation",
                json.dumps({"content": f"Memory {i}"}),
                1,
                "system",
                datetime.now(timezone.utc),
                datetime.now(timezone.utc),
            )
            for i in range(5)
        ]

        app.dependency_overrides[require_observer] = lambda: auth_context

        # Mock query_timeline_nodes function to return actual node objects
        # Add updated_at to nodes
        for node in nodes:
            node.updated_at = datetime.now(timezone.utc) - timedelta(hours=1)

        async def mock_query_timeline_nodes(**kwargs):
            return nodes

        with patch(
            "ciris_engine.logic.adapters.api.routes.memory.query_timeline_nodes",
            new=AsyncMock(side_effect=mock_query_timeline_nodes),
        ):
            response = client.get("/memory/timeline")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "memories" in data["data"]
        assert "buckets" in data["data"]
        assert "total" in data["data"]

    def test_timeline_with_filters(self, client, app, auth_context):
        """Test timeline with scope and type filters."""
        app.dependency_overrides[require_observer] = lambda: auth_context

        # Mock query_timeline_nodes to return empty result for filtered query
        async def mock_query_timeline_nodes(**kwargs):
            return []

        with patch(
            "ciris_engine.logic.adapters.api.routes.memory.query_timeline_nodes",
            new=AsyncMock(side_effect=mock_query_timeline_nodes),
        ):
            response = client.get(
                "/memory/timeline",
                params={
                    "hours": 12,
                    "scope": "local",  # GraphScope enum expects lowercase
                    "type": "observation",  # NodeType enum accepts this
                    "limit": 100,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["total"] == 0


class TestForgetMemory:
    """Test the /memory/forget endpoint."""

    def test_forget_memory_success(self, client, app, sample_node, auth_context):
        """Test successful memory deletion."""
        # The forget endpoint first recalls the node, then forgets it
        app.state.memory_service.recall_node.return_value = sample_node
        app.state.memory_service.forget.return_value = MemoryOpResult(
            status=MemoryOpStatus.OK, reason="Memory forgotten", data={"node_id": "test_node_1"}
        )

        app.dependency_overrides[require_admin] = lambda: auth_context
        response = client.delete("/memory/test_node_1")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        # The MemoryOpResult is in data["data"]
        assert data["data"]["status"] == "ok"

    def test_forget_memory_not_found(self, client, app, auth_context):
        """Test forgetting a non-existent node."""
        # The memory service returns an error status for non-existent nodes
        app.state.memory_service.forget.return_value = MemoryOpResult(
            status=MemoryOpStatus.ERROR, reason="Node not found", data={"node_id": "nonexistent"}
        )

        app.dependency_overrides[require_admin] = lambda: auth_context
        response = client.delete("/memory/nonexistent")

        # The endpoint returns 200 even for not found, with error in the result
        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["status"] == "error"
        assert "not found" in data["data"]["reason"].lower()


class TestMemoryStats:
    """Test the /memory/stats endpoint."""

    def test_get_memory_stats(self, client, app, auth_context):
        """Test getting memory statistics."""
        app.dependency_overrides[require_observer] = lambda: auth_context

        # Mock get_memory_stats function to return expected stats
        mock_stats = {
            "total_nodes": 100,
            "nodes_by_type": {"observation": 60, "identity": 20, "event": 20},
            "nodes_by_scope": {"LOCAL": 80, "GLOBAL": 20},
            "recent_activity": {"nodes_24h": 50},
            "date_range": {"oldest": "2025-01-01T00:00:00+00:00", "newest": "2025-08-12T22:00:00+00:00"},
        }

        async def mock_get_memory_stats(memory_service):
            return mock_stats

        # Also mock query_timeline_nodes which is called to get the newest node
        async def mock_query_timeline_nodes(**kwargs):
            return []  # Return empty list, endpoint will handle it

        with patch(
            "ciris_engine.logic.adapters.api.routes.memory.get_memory_stats",
            new=AsyncMock(side_effect=mock_get_memory_stats),
        ), patch(
            "ciris_engine.logic.adapters.api.routes.memory.query_timeline_nodes",
            new=AsyncMock(side_effect=mock_query_timeline_nodes),
        ):
            response = client.get("/memory/stats")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["total_nodes"] == 100
        assert data["data"]["recent_nodes_24h"] == 50
        assert data["data"]["nodes_by_type"]["observation"] == 60
