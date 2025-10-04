"""Unit tests for LocalGraphMemoryService."""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpStatus, MemoryQuery


@pytest.fixture
def time_service():
    """Create a time service for testing."""
    return TimeService()


@pytest.fixture
def secrets_service():
    """Create a mock secrets service for testing."""
    service = MagicMock(spec=SecretsService)
    service.process_and_store = AsyncMock(return_value="encrypted_value")
    service.retrieve = AsyncMock(return_value="decrypted_value")
    service.filter_string = AsyncMock(side_effect=lambda x, _: x)  # Pass through
    # process_incoming_text should return the original text unchanged and empty secret refs
    service.process_incoming_text = AsyncMock(side_effect=lambda text, **kwargs: (text, []))
    return service


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest_asyncio.fixture
async def memory_service(temp_db, secrets_service, time_service):
    """Create a memory service for testing."""
    service = LocalGraphMemoryService(db_path=temp_db, secrets_service=secrets_service, time_service=time_service)
    await service.start()
    yield service
    await service.stop()


@pytest.mark.asyncio
async def test_memory_service_memorize(memory_service):
    """Test storing a node in memory."""
    # Create a test node
    node = GraphNode(
        id="test_node_1",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes=GraphNodeAttributes(created_by="test_user", tags=["test", "memory"]),
    )

    # Store the node
    result = await memory_service.memorize(node)

    # Verify success
    assert result.status == MemoryOpStatus.OK
    assert result.error is None


@pytest.mark.asyncio
async def test_memory_service_recall(memory_service):
    """Test recalling a node from memory."""
    # First store a node
    node = GraphNode(
        id="test_recall_1",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes={
            "content": "Test recall content",
            "test": "data",
            "created_by": "test_user",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await memory_service.memorize(node)

    # Recall the node
    query = MemoryQuery(node_id="test_recall_1", scope=GraphScope.LOCAL)
    nodes = await memory_service.recall(query)

    # Verify we got the node back
    assert len(nodes) == 1
    recalled = nodes[0]
    assert recalled.id == "test_recall_1"
    assert recalled.attributes["content"] == "Test recall content"
    assert recalled.attributes["test"] == "data"


@pytest.mark.asyncio
async def test_memory_service_forget(memory_service):
    """Test forgetting a node from memory."""
    # Store a node
    node = GraphNode(
        id="test_forget_1",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes=GraphNodeAttributes(created_by="test_user", tags=["forget", "test"]),
    )
    await memory_service.memorize(node)

    # Forget the node
    result = await memory_service.forget(node)
    assert result.status == MemoryOpStatus.OK

    # Try to recall - should get empty list
    query = MemoryQuery(node_id="test_forget_1", scope=GraphScope.LOCAL)
    nodes = await memory_service.recall(query)
    assert len(nodes) == 0


@pytest.mark.asyncio
async def test_memory_service_search(memory_service):
    """Test searching nodes in memory."""
    # Store multiple nodes
    nodes = [
        GraphNode(
            id=f"search_node_{i}",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={
                "content": f"Search content {i}",
                "category": "test" if i % 2 == 0 else "other",
                "created_by": "test_user",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        for i in range(5)
    ]

    for node in nodes:
        await memory_service.memorize(node)

    # Search by type
    from ciris_engine.schemas.services.graph.memory import MemorySearchFilter

    filter = MemorySearchFilter(node_type=NodeType.CONCEPT, scope=GraphScope.LOCAL)
    results = await memory_service.search("", filters=filter)
    # The search returns all matching nodes
    assert len(results) == 5  # All nodes are returned

    # Search with limit - NOTE: The current implementation doesn't respect the limit filter
    filter_with_limit = MemorySearchFilter(node_type=NodeType.CONCEPT, scope=GraphScope.LOCAL, limit=2)
    results = await memory_service.search("", filters=filter_with_limit)
    # The implementation DOES respect the limit filter
    assert len(results) == 2  # Returns only 2 nodes as requested


# Note: update_identity method doesn't exist in LocalGraphMemoryService
# This test has been removed


@pytest.mark.asyncio
async def test_memory_service_timeseries(memory_service):
    """Test memorizing metrics and recalling timeseries data."""
    # Store some metrics using memorize_metric
    for i in range(3):
        result = await memory_service.memorize_metric(
            metric_name="test_metric",
            value=i * 10.0,
            tags={"test": "data", "index": str(i)},  # Add unique tag
            scope="local",
        )
        assert result.status == MemoryOpStatus.OK
        # Add small delay to ensure different timestamps
        await asyncio.sleep(0.01)

    # Recall timeseries data
    retrieved = await memory_service.recall_timeseries(scope="local", hours=24)

    # Should have at least the 3 metrics we stored
    assert len(retrieved) >= 3

    # Find our test metrics
    test_metrics = [dp for dp in retrieved if dp.metric_name == "test_metric"]
    assert len(test_metrics) >= 3


def test_memory_service_capabilities(memory_service):
    """Test MemoryService.get_capabilities() returns correct info."""
    caps = memory_service.get_capabilities()
    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "LocalGraphMemoryService"  # Uses class name by default
    assert caps.version == "1.0.0"
    assert "memorize" in caps.actions
    assert "recall" in caps.actions
    assert "forget" in caps.actions
    assert "search" in caps.actions
    assert "memorize_metric" in caps.actions
    assert "memorize_log" in caps.actions
    assert "recall_timeseries" in caps.actions
    assert "export_identity_context" in caps.actions
    # BaseGraphService adds MemoryBus dependency, LocalGraphMemoryService also uses TimeService
    assert "MemoryBus" in caps.dependencies  # From BaseGraphService
    assert "TimeService" in caps.dependencies  # From _register_dependencies
    # SecretsService is not listed as a dependency in _register_dependencies


@pytest.mark.asyncio
async def test_memory_service_status(memory_service):
    """Test MemoryService.get_status() returns correct status."""
    status = memory_service.get_status()
    assert isinstance(status, ServiceStatus)
    assert status.service_name == "LocalGraphMemoryService"  # Uses class name by default
    assert status.service_type == "memory"  # ServiceType.MEMORY from get_service_type()
    assert status.is_healthy is True
    assert status.metrics["secrets_enabled"] == 1.0  # Should have secrets service from fixture

    # Add some nodes and check status
    for i in range(3):
        node = GraphNode(
            id=f"status_node_{i}",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes=GraphNodeAttributes(created_by="test_user", tags=[f"status_{i}"]),
        )
        await memory_service.memorize(node)

    status = memory_service.get_status()
    assert status.is_healthy is True


@pytest.mark.asyncio
async def test_memory_service_secrets_integration(memory_service, secrets_service):
    """Test that secrets are processed during memorize/recall."""
    # Create node with potential secrets
    node = GraphNode(
        id="secret_node",
        type=NodeType.CONFIG,
        scope=GraphScope.LOCAL,
        attributes={
            "content": "password: secret123",
            "api_key": "sk-12345",
            "created_by": "test_user",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )

    # Store node - secrets should be processed
    await memory_service.memorize(node)

    # Verify secrets service was called
    assert secrets_service.process_incoming_text.called

    # Recall node - secrets should be decrypted
    query = MemoryQuery(node_id="secret_node", scope=GraphScope.LOCAL)
    nodes = await memory_service.recall(query)

    assert len(nodes) == 1


@pytest.mark.asyncio
async def test_memory_service_graph_query(memory_service):
    """Test complex graph queries."""
    # Store nodes with relationships
    parent = GraphNode(
        id="parent_node",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes=GraphNodeAttributes(created_by="test_user", tags=["parent"]),
    )
    await memory_service.memorize(parent)

    child = GraphNode(
        id="child_node",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes={
            "content": "Child content",
            "parent_id": "parent_node",
            "created_by": "test_user",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    await memory_service.memorize(child)

    # Query with depth
    query = MemoryQuery(node_id="parent_node", scope=GraphScope.LOCAL, include_edges=True, depth=1)
    nodes = await memory_service.recall(query)

    # Should get parent node
    assert len(nodes) >= 1
    assert nodes[0].id == "parent_node"
