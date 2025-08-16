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
        # The route now uses recall_node which returns a single node
        app.state.memory_service.recall_node.return_value = sample_node
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
        with patch("ciris_engine.logic.adapters.api.routes.memory.get_db_connection", return_value=mock_conn):
            response = client.get("/memory/timeline")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert "memories" in data["data"]
        assert "buckets" in data["data"]
        assert "total" in data["data"]

    def test_timeline_with_filters(self, client, app, auth_context):
        """Test timeline with scope and type filters."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_cursor.fetchall.return_value = []

        app.dependency_overrides[require_observer] = lambda: auth_context
        with patch("ciris_engine.logic.adapters.api.routes.memory.get_db_connection", return_value=mock_conn):
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
        app.state.memory_service.recall.return_value = []

        app.dependency_overrides[require_admin] = lambda: auth_context
        response = client.delete("/memory/nonexistent")

        assert response.status_code == 404


class TestCreateEdge:
    """Test the /memory/edge endpoint."""

    def test_create_edge_success(self, client, app, sample_edge, auth_context):
        """Test successful edge creation."""
        app.state.memory_service.create_edge.return_value = MemoryOpResult(
            status=MemoryOpStatus.OK,
            reason="Edge created",
            data={"edge_id": f"{sample_edge.source}->{sample_edge.target}"},
        )

        app.dependency_overrides[require_admin] = lambda: auth_context
        # Use model_dump with mode='json' to properly serialize datetime
        response = client.post(
            "/memory/edges", json={"edge": sample_edge.model_dump(mode="json")}  # Correct endpoint is /edges not /edge
        )

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        # The MemoryOpResult is in data["data"]
        assert data["data"]["status"] == "ok"


class TestMemoryStats:
    """Test the /memory/stats endpoint."""

    def test_get_memory_stats(self, client, app, auth_context):
        """Test getting memory statistics."""

        # Create sqlite3.Row-like objects that support both dict and index access
        class MockRow:
            def __init__(self, **kwargs):
                self._data = kwargs

            def __getitem__(self, key):
                return self._data.get(key)

        # Mock database query for stats
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        # get_db_connection is used as a context manager
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=None)

        # Mock the various count queries - stats endpoint expects dict-style results
        # Order matters! Follow the exact order of fetchone() calls in the stats endpoint
        mock_cursor.fetchone.side_effect = [
            MockRow(total=100),  # Total nodes (line 646)
            MockRow(count=50),  # Recent nodes 24h (line 678)
            MockRow(oldest="2025-01-01T00:00:00+00:00", newest="2025-08-12T22:00:00+00:00"),  # Date range (line 689)
        ]
        mock_cursor.fetchall.side_effect = [
            [
                MockRow(node_type="observation", count=60),
                MockRow(node_type="identity", count=20),
                MockRow(node_type="event", count=20),
            ],  # By type
            [MockRow(scope="LOCAL", count=80), MockRow(scope="GLOBAL", count=20)],  # By scope
        ]

        app.dependency_overrides[require_observer] = lambda: auth_context
        with patch("ciris_engine.logic.adapters.api.routes.memory.get_db_connection", return_value=mock_conn):
            response = client.get("/memory/stats")

        assert response.status_code == 200
        data = response.json()
        assert "data" in data
        assert data["data"]["total_nodes"] == 100
        assert data["data"]["recent_nodes_24h"] == 50
