"""
Tests for refactored memory service helper methods.

Tests the new helper methods added to reduce complexity in recall() and search().
"""

import json
import pytest
from datetime import datetime, timedelta
from typing import Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

from ciris_engine.logic.services.graph.memory_service import LocalGraphMemoryService
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryQuery


@pytest.fixture
def memory_service(tmp_path):
    """Create memory service instance."""
    db_path = tmp_path / "test.db"
    service = LocalGraphMemoryService(
        db_path=str(db_path)
    )
    service.start()
    yield service
    service.stop()


@pytest.fixture
def sample_node():
    """Create a sample GraphNode for testing."""
    return GraphNode(
        id="test-node-1",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes={
            "content": "Test content",
            "tags": ["test", "sample"],
        },
        version=1,
        updated_by="test",
        updated_at=datetime.now()
    )


@pytest.fixture
def sample_nodes():
    """Create multiple sample nodes for testing."""
    nodes = []
    for i in range(5):
        nodes.append(GraphNode(
            id=f"test-node-{i}",
            type=NodeType.CONCEPT if i % 2 == 0 else NodeType.CONFIG,
            scope=GraphScope.LOCAL,
            attributes={
                "content": f"Content {i}",
                "tags": ["test"] if i % 2 == 0 else ["sample"],
            },
            version=1,
            updated_by="test",
            updated_at=datetime.now() - timedelta(hours=i)
        ))
    return nodes


class TestMemoryServiceHelpers:
    """Test helper methods in LocalGraphMemoryService."""

    @pytest.mark.asyncio
    async def test_process_node_with_edges(self, memory_service, sample_node):
        """Test _process_node_with_edges helper method."""
        # Test without edges
        result = await memory_service._process_node_with_edges(sample_node, include_edges=False)
        assert result.id == sample_node.id
        assert "_edges" not in result.attributes

        # Mock edge retrieval
        with patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node") as mock_get_edges:
            mock_edges = [
                MagicMock(
                    source="test-node-1",
                    target="test-node-2",
                    relationship="RELATES_TO",
                    weight=1.0,
                    attributes={"test": "attr"}
                )
            ]
            mock_get_edges.return_value = mock_edges

            # Test with edges
            result = await memory_service._process_node_with_edges(sample_node, include_edges=True)
            assert "_edges" in result.attributes
            assert len(result.attributes["_edges"]) == 1
            assert result.attributes["_edges"][0]["source"] == "test-node-1"

    @pytest.mark.asyncio
    async def test_fetch_connected_nodes(self, memory_service, sample_node):
        """Test _fetch_connected_nodes helper method."""
        # Test depth 0
        result = await memory_service._fetch_connected_nodes(sample_node, depth=0)
        assert len(result) == 1
        assert result[0].id == sample_node.id

        # Test depth > 0 with mock edges and nodes
        with patch("ciris_engine.logic.persistence.models.graph.get_edges_for_node") as mock_get_edges, \
             patch("ciris_engine.logic.persistence.models.graph.get_graph_node") as mock_get_node:

            # Setup mocks
            mock_edges = [
                MagicMock(
                    source="test-node-1",
                    target="test-node-2",
                    relationship="RELATES_TO",
                    weight=1.0,
                    scope=GraphScope.LOCAL,
                    attributes={}
                )
            ]
            mock_get_edges.return_value = mock_edges

            connected_node = GraphNode(
                id="test-node-2",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={"content": "Connected node"},
                version=1,
                updated_by="test",
                updated_at=datetime.now()
            )
            mock_get_node.return_value = connected_node

            # Test depth 1
            result = await memory_service._fetch_connected_nodes(sample_node, depth=1)
            assert len(result) == 1  # Only the start node at depth 1

            # Test depth 2
            mock_get_edges.side_effect = [mock_edges, []]  # First call returns edges, second returns none
            result = await memory_service._fetch_connected_nodes(sample_node, depth=2)
            assert len(result) == 2  # Start node plus connected node

    def test_apply_time_filters(self, memory_service, sample_nodes):
        """Test _apply_time_filters helper method."""
        # Test no filters
        result = memory_service._apply_time_filters(sample_nodes, None)
        assert len(result) == len(sample_nodes)

        # Test since filter - use slightly more than 2 hours to ensure node 2 is included
        since = datetime.now() - timedelta(hours=2, seconds=1)
        filters = {"since": since}
        result = memory_service._apply_time_filters(sample_nodes, filters)
        assert len(result) == 3  # Nodes 0, 1, 2

        # Test until filter - use slightly less than 2 hours to ensure node 2 is included
        until = datetime.now() - timedelta(hours=2, seconds=-1)
        filters = {"until": until}
        result = memory_service._apply_time_filters(sample_nodes, filters)
        assert len(result) == 3  # Nodes 2, 3, 4

        # Test both filters
        filters = {"since": since, "until": until}
        result = memory_service._apply_time_filters(sample_nodes, filters)
        assert len(result) == 1  # Only node 2

    def test_apply_tag_filters(self, memory_service, sample_nodes):
        """Test _apply_tag_filters helper method."""
        # Test no filters
        result = memory_service._apply_tag_filters(sample_nodes, None)
        assert len(result) == len(sample_nodes)

        # Test tag filter
        filters = {"tags": ["test"]}
        result = memory_service._apply_tag_filters(sample_nodes, filters)
        assert len(result) == 3  # Nodes 0, 2, 4

        filters = {"tags": ["sample"]}
        result = memory_service._apply_tag_filters(sample_nodes, filters)
        assert len(result) == 2  # Nodes 1, 3

        # Test multiple tags
        filters = {"tags": ["test", "sample"]}
        result = memory_service._apply_tag_filters(sample_nodes, filters)
        assert len(result) == 5  # All nodes match at least one tag

    def test_parse_search_query(self, memory_service):
        """Test _parse_search_query helper method."""
        # Test empty query
        terms, node_type, scope = memory_service._parse_search_query("")
        assert terms == []
        assert node_type is None
        assert scope is None

        # Test simple search terms
        terms, node_type, scope = memory_service._parse_search_query("hello world")
        assert terms == ["hello", "world"]
        assert node_type is None
        assert scope is None

        # Test with type filter
        terms, node_type, scope = memory_service._parse_search_query("type:concept hello")
        assert terms == ["hello"]
        assert node_type == "concept"
        assert scope is None

        # Test with scope filter
        terms, node_type, scope = memory_service._parse_search_query("scope:local world")
        assert terms == ["world"]
        assert node_type is None
        assert scope == GraphScope.LOCAL

        # Test with both filters
        terms, node_type, scope = memory_service._parse_search_query("type:config scope:identity test search")
        assert terms == ["test", "search"]
        assert node_type == "config"
        assert scope == GraphScope.IDENTITY

    def test_filter_nodes_by_content(self, memory_service, sample_nodes):
        """Test _filter_nodes_by_content helper method."""
        # Test no search terms
        result = memory_service._filter_nodes_by_content(sample_nodes, [])
        assert len(result) == len(sample_nodes)

        # Test search by node ID
        result = memory_service._filter_nodes_by_content(sample_nodes, ["test-node-2"])
        assert len(result) == 1
        assert result[0].id == "test-node-2"

        # Test search by content
        result = memory_service._filter_nodes_by_content(sample_nodes, ["content"])
        assert len(result) == 5  # All nodes have "content" in attributes

        # Test search by specific content
        result = memory_service._filter_nodes_by_content(sample_nodes, ["content 3"])
        assert len(result) == 1
        assert result[0].id == "test-node-3"

        # Test multiple search terms
        result = memory_service._filter_nodes_by_content(sample_nodes, ["test", "node"])
        assert len(result) == 5  # All nodes have "test-node" in ID

    @pytest.mark.asyncio
    async def test_recall_wildcard(self, memory_service):
        """Test _recall_wildcard helper method."""
        with patch("ciris_engine.logic.persistence.get_all_graph_nodes") as mock_get_all:
            mock_get_all.return_value = [
                GraphNode(
                    id="test-1",
                    type=NodeType.CONCEPT,
                    scope=GraphScope.LOCAL,
                    attributes={"content": "test"},
                    version=1,
                    updated_by="test",
                    updated_at=datetime.now()
                )
            ]

            query = MemoryQuery(
                node_id="*",
                scope=GraphScope.LOCAL,
                include_edges=False
            )

            result = await memory_service._recall_wildcard(query)
            assert len(result) == 1
            assert result[0].id == "test-1"
            mock_get_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_recall_single_node(self, memory_service, sample_node):
        """Test _recall_single_node helper method."""
        with patch("ciris_engine.logic.persistence.models.graph.get_graph_node") as mock_get:
            mock_get.return_value = sample_node

            query = MemoryQuery(
                node_id="test-node-1",
                scope=GraphScope.LOCAL,
                include_edges=False
            )

            result = await memory_service._recall_single_node(query)
            assert len(result) == 1
            assert result[0].id == "test-node-1"

    @pytest.mark.asyncio
    async def test_process_node_for_recall(self, memory_service, sample_node):
        """Test _process_node_for_recall helper method."""
        # Test without edges
        result = await memory_service._process_node_for_recall(sample_node, include_edges=False)
        assert result.id == sample_node.id
        assert "_edges" not in result.attributes

        # Test with edges
        with patch.object(memory_service, "_process_node_with_edges") as mock_process:
            mock_process.return_value = sample_node
            result = await memory_service._process_node_for_recall(sample_node, include_edges=True)
            mock_process.assert_called_once_with(result, include_edges=True)

    @pytest.mark.asyncio
    async def test_fetch_nodes_for_search(self, memory_service):
        """Test _fetch_nodes_for_search helper method."""
        with patch("ciris_engine.logic.persistence.get_nodes_by_type") as mock_by_type, \
             patch("ciris_engine.logic.persistence.get_all_graph_nodes") as mock_all:

            # Test with node_type
            mock_by_type.return_value = []
            await memory_service._fetch_nodes_for_search(GraphScope.LOCAL, "thought", 100)
            mock_by_type.assert_called_once()
            mock_all.assert_not_called()

            # Reset mocks
            mock_by_type.reset_mock()
            mock_all.reset_mock()

            # Test without node_type
            mock_all.return_value = []
            await memory_service._fetch_nodes_for_search(GraphScope.LOCAL, None, 100)
            mock_by_type.assert_not_called()
            mock_all.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_nodes_for_search(self, memory_service, sample_nodes):
        """Test _process_nodes_for_search helper method."""
        # Mock secrets processing
        with patch.object(memory_service, "_process_secrets_for_recall") as mock_secrets:
            mock_secrets.return_value = {"processed": True}

            result = await memory_service._process_nodes_for_search(sample_nodes)
            assert len(result) == len(sample_nodes)
            assert mock_secrets.call_count == len(sample_nodes)

            # Verify processed attributes
            for node in result:
                assert node.attributes == {"processed": True}


class TestRefactoredIntegration:
    """Integration tests for refactored methods."""

    @pytest.mark.asyncio
    async def test_recall_with_helpers(self, memory_service):
        """Test recall() using new helper methods."""
        # Store a node first
        node = GraphNode(
            id="integration-test",
            type=NodeType.CONCEPT,
            scope=GraphScope.LOCAL,
            attributes={"test": "data"},
            version=1,
            updated_by="test",
            updated_at=datetime.now()
        )
        await memory_service.memorize(node)

        # Test recall with wildcard
        query = MemoryQuery(node_id="*", scope=GraphScope.LOCAL)
        result = await memory_service.recall(query)
        assert any(n.id == "integration-test" for n in result)

        # Test recall specific node
        query = MemoryQuery(node_id="integration-test", scope=GraphScope.LOCAL)
        result = await memory_service.recall(query)
        assert len(result) == 1
        assert result[0].id == "integration-test"

    @pytest.mark.asyncio
    async def test_search_with_helpers(self, memory_service):
        """Test search() using new helper methods."""
        # Store some nodes
        for i in range(3):
            node = GraphNode(
                id=f"search-test-{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={"content": f"Search content {i}"},
                version=1,
                updated_by="test",
                updated_at=datetime.now()
            )
            await memory_service.memorize(node)

        # Test search
        result = await memory_service.search("search-test")
        assert len(result) >= 3

        # Test search with type filter in query
        result = await memory_service.search("type:concept search")
        assert all(n.type == NodeType.CONCEPT for n in result if n.id.startswith("search-test"))

        # Test search by content
        result = await memory_service.search("content 1")
        matching = [n for n in result if n.id == "search-test-1"]
        assert len(matching) >= 1