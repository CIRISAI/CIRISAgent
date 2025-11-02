"""
Tests for identity_resolution utilities - graph-based cross-system identity mapping.

Focuses on:
- get_or_create_identity_node() for node management
- add_identity_mapping() for creating identity links
- get_all_identifiers() for graph traversal
- resolve_user_identity() for identity resolution
- remove_identity_mapping() for unlinking identifiers
- get_identity_graph() for visualization
- merge_user_identities() for merging graphs
- validate_identity_mapping() for confidence scoring
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from ciris_engine.logic.utils import identity_resolution
from ciris_engine.schemas.identity import IdentityConfidence, UserIdentifier, UserIdentityNode
from ciris_engine.schemas.services.graph_core import GraphEdge, GraphEdgeAttributes, GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@pytest.fixture
def mock_memory_service():
    """Create a mock memory service for testing."""
    from ciris_engine.protocols.services.graph.memory import MemoryServiceProtocol

    mock = AsyncMock(spec=MemoryServiceProtocol)

    # Default empty recall
    mock.recall = AsyncMock(return_value=[])

    # Default successful memorize
    mock.memorize = AsyncMock(side_effect=lambda node: MemoryOpResult(status=MemoryOpStatus.OK, data=node))

    # Default successful create_edge
    mock.create_edge = AsyncMock(side_effect=lambda edge: MemoryOpResult(status=MemoryOpStatus.OK, data=edge))

    # Default empty edges
    mock.get_node_edges = AsyncMock(return_value=[])

    return mock


@pytest.fixture
def sample_identity_nodes():
    """Create sample identity nodes for testing."""
    return {
        "email": GraphNode(
            id="user_identity:email:user@example.com",
            type=NodeType.IDENTITY,
            scope=GraphScope.ENVIRONMENT,
            attributes={
                "identifier_type": "email",
                "identifier_value": "user@example.com",
                "created_by": "identity_resolution",
            },
        ),
        "discord": GraphNode(
            id="user_identity:discord_id:123456789",
            type=NodeType.IDENTITY,
            scope=GraphScope.ENVIRONMENT,
            attributes={
                "identifier_type": "discord_id",
                "identifier_value": "123456789",
                "created_by": "identity_resolution",
            },
        ),
        "reddit": GraphNode(
            id="user_identity:reddit_username:cooluser",
            type=NodeType.IDENTITY,
            scope=GraphScope.ENVIRONMENT,
            attributes={
                "identifier_type": "reddit_username",
                "identifier_value": "cooluser",
                "created_by": "identity_resolution",
            },
        ),
    }


@pytest.fixture
def sample_identity_edges():
    """Create sample identity edges for testing."""
    return {
        "email_discord": GraphEdge(
            source="user_identity:email:user@example.com",
            target="user_identity:discord_id:123456789",
            relationship="same_as",
            scope=GraphScope.ENVIRONMENT,
            weight=1.0,
            attributes=GraphEdgeAttributes(context="source=oauth,confidence=1.0"),
        ),
        "discord_reddit": GraphEdge(
            source="user_identity:discord_id:123456789",
            target="user_identity:reddit_username:cooluser",
            relationship="same_as",
            scope=GraphScope.ENVIRONMENT,
            weight=1.0,
            attributes=GraphEdgeAttributes(context="source=manual,confidence=1.0"),
        ),
    }


class TestGetOrCreateIdentityNode:
    """Test get_or_create_identity_node() helper function."""

    @pytest.mark.asyncio
    async def test_create_new_node(self, mock_memory_service):
        """Test creating a new identity node."""
        # Execute
        node = await identity_resolution.get_or_create_identity_node("user@example.com", "email", mock_memory_service)

        # Verify node structure
        assert node.id == "user_identity:email:user@example.com"
        assert node.type == NodeType.IDENTITY
        assert node.scope == GraphScope.ENVIRONMENT
        assert node.attributes["identifier_type"] == "email"
        assert node.attributes["identifier_value"] == "user@example.com"
        assert node.attributes["created_by"] == "identity_resolution"

        # Verify memory operations
        mock_memory_service.recall.assert_awaited_once()
        mock_memory_service.memorize.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_get_existing_node(self, mock_memory_service, sample_identity_nodes):
        """Test getting an existing identity node."""
        # Setup existing node
        existing_node = sample_identity_nodes["email"]
        mock_memory_service.recall = AsyncMock(return_value=[existing_node])

        # Execute
        node = await identity_resolution.get_or_create_identity_node("user@example.com", "email", mock_memory_service)

        # Verify returns existing node
        assert node.id == existing_node.id
        assert node == existing_node

        # Verify no new node created
        mock_memory_service.memorize.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_create_with_metadata(self, mock_memory_service):
        """Test creating node with custom metadata."""
        # Execute
        node = await identity_resolution.get_or_create_identity_node(
            "user@example.com",
            "email",
            mock_memory_service,
            metadata={"source": "oauth", "verified": True},
        )

        # Verify metadata included
        assert node.attributes["source"] == "oauth"
        assert node.attributes["verified"] is True


class TestAddIdentityMapping:
    """Test add_identity_mapping() for creating identity links."""

    @pytest.mark.asyncio
    async def test_add_mapping_creates_nodes_and_edge(self, mock_memory_service):
        """Test adding identity mapping creates nodes and edge."""
        # Execute
        edge = await identity_resolution.add_identity_mapping(
            "user@example.com",
            "email",
            "123456789",
            "discord_id",
            mock_memory_service,
            confidence=1.0,
            source="oauth",
        )

        # Verify edge structure
        assert edge.source == "user_identity:email:user@example.com"
        assert edge.target == "user_identity:discord_id:123456789"
        assert edge.relationship == "same_as"
        assert edge.scope == GraphScope.ENVIRONMENT
        assert edge.weight == 1.0
        assert "source=oauth" in edge.attributes.context
        assert "confidence=1.0" in edge.attributes.context

        # Verify nodes created (2 recalls for existence check, 2 memorize for creation)
        assert mock_memory_service.recall.await_count == 2
        assert mock_memory_service.memorize.await_count == 2

        # Verify edge created
        mock_memory_service.create_edge.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_add_mapping_with_existing_nodes(self, mock_memory_service, sample_identity_nodes):
        """Test adding mapping reuses existing nodes."""
        # Setup existing nodes
        email_node = sample_identity_nodes["email"]
        discord_node = sample_identity_nodes["discord"]

        def recall_side_effect(query):
            if "email:user@example.com" in query.node_id:
                return [email_node]
            elif "discord_id:123456789" in query.node_id:
                return [discord_node]
            return []

        mock_memory_service.recall = AsyncMock(side_effect=recall_side_effect)

        # Execute
        edge = await identity_resolution.add_identity_mapping(
            "user@example.com",
            "email",
            "123456789",
            "discord_id",
            mock_memory_service,
            confidence=0.8,
            source="manual",
        )

        # Verify edge created
        assert edge.source == email_node.id
        assert edge.target == discord_node.id
        assert edge.weight == 0.8

        # Verify no new nodes created
        mock_memory_service.memorize.assert_not_awaited()


class TestGetAllIdentifiers:
    """Test get_all_identifiers() for graph traversal."""

    @pytest.mark.asyncio
    async def test_single_identifier(self, mock_memory_service, sample_identity_nodes):
        """Test getting single identifier (no connections)."""
        # Setup single node
        email_node = sample_identity_nodes["email"]
        mock_memory_service.recall = AsyncMock(return_value=[email_node])
        mock_memory_service.get_node_edges = AsyncMock(return_value=[])

        # Execute
        identifiers = await identity_resolution.get_all_identifiers("user@example.com", mock_memory_service)

        # Verify single identifier returned
        assert len(identifiers) == 1
        assert identifiers[0].identifier_type == "email"
        assert identifiers[0].identifier_value == "user@example.com"
        assert identifiers[0].confidence == 1.0

    @pytest.mark.asyncio
    async def test_multiple_identifiers_connected(
        self, mock_memory_service, sample_identity_nodes, sample_identity_edges
    ):
        """Test getting all identifiers via graph traversal."""
        email_node = sample_identity_nodes["email"]
        discord_node = sample_identity_nodes["discord"]
        reddit_node = sample_identity_nodes["reddit"]
        edge1 = sample_identity_edges["email_discord"]
        edge2 = sample_identity_edges["discord_reddit"]

        # Setup recall responses
        def recall_side_effect(query):
            if "email:user@example.com" in query.node_id:
                return [email_node]
            elif "discord_id:123456789" in query.node_id:
                return [discord_node]
            elif "reddit_username:cooluser" in query.node_id:
                return [reddit_node]
            return []

        # Setup edges
        def get_edges_side_effect(node_id, scope):
            if "email:user@example.com" in node_id:
                return [edge1]
            elif "discord_id:123456789" in node_id:
                return [edge1, edge2]
            elif "reddit_username:cooluser" in node_id:
                return [edge2]
            return []

        mock_memory_service.recall = AsyncMock(side_effect=recall_side_effect)
        mock_memory_service.get_node_edges = AsyncMock(side_effect=get_edges_side_effect)

        # Execute from email
        identifiers = await identity_resolution.get_all_identifiers("user@example.com", mock_memory_service)

        # Verify all 3 identifiers found
        assert len(identifiers) == 3
        types_found = {id.identifier_type for id in identifiers}
        assert "email" in types_found
        assert "discord_id" in types_found
        assert "reddit_username" in types_found

    @pytest.mark.asyncio
    async def test_no_identifier_found(self, mock_memory_service):
        """Test handling non-existent identifier."""
        # Setup no nodes found
        mock_memory_service.recall = AsyncMock(return_value=[])

        # Execute
        identifiers = await identity_resolution.get_all_identifiers("nonexistent@example.com", mock_memory_service)

        # Verify empty list
        assert len(identifiers) == 0


class TestResolveUserIdentity:
    """Test resolve_user_identity() for identity resolution."""

    @pytest.mark.asyncio
    async def test_resolve_existing_identity(self, mock_memory_service, sample_identity_nodes, sample_identity_edges):
        """Test resolving existing user identity."""
        email_node = sample_identity_nodes["email"]
        discord_node = sample_identity_nodes["discord"]
        edge1 = sample_identity_edges["email_discord"]

        # Setup recall responses
        def recall_side_effect(query):
            if "email:user@example.com" in query.node_id:
                return [email_node]
            elif "discord_id:123456789" in query.node_id:
                return [discord_node]
            return []

        # Setup edges
        def get_edges_side_effect(node_id, scope):
            if "email:user@example.com" in node_id:
                return [edge1]
            elif "discord_id:123456789" in node_id:
                return [edge1]
            return []

        mock_memory_service.recall = AsyncMock(side_effect=recall_side_effect)
        mock_memory_service.get_node_edges = AsyncMock(side_effect=get_edges_side_effect)

        # Execute
        identity = await identity_resolution.resolve_user_identity(
            "user@example.com", mock_memory_service, identifier_type="email"
        )

        # Verify identity node
        assert identity is not None
        assert identity.primary_id == "user@example.com"
        assert len(identity.identifiers) >= 1
        assert identity.graph_node_id == "user_identity:email:user@example.com"

    @pytest.mark.asyncio
    async def test_resolve_nonexistent_identity(self, mock_memory_service):
        """Test resolving non-existent identity returns None."""
        # Setup no nodes found
        mock_memory_service.recall = AsyncMock(return_value=[])

        # Execute
        identity = await identity_resolution.resolve_user_identity("nonexistent@example.com", mock_memory_service)

        # Verify None returned
        assert identity is None


class TestRemoveIdentityMapping:
    """Test remove_identity_mapping() for unlinking identifiers."""

    @pytest.mark.asyncio
    async def test_remove_existing_mapping(self, mock_memory_service, sample_identity_edges):
        """Test removing existing identity mapping."""
        edge = sample_identity_edges["email_discord"]

        # Setup edges
        mock_memory_service.get_node_edges = AsyncMock(return_value=[edge])

        # Execute
        result = await identity_resolution.remove_identity_mapping(
            "user@example.com",
            "email",
            "123456789",
            "discord_id",
            mock_memory_service,
        )

        # Verify mapping found
        assert result is True

    @pytest.mark.asyncio
    async def test_remove_nonexistent_mapping(self, mock_memory_service):
        """Test removing non-existent mapping returns False."""
        # Setup no edges
        mock_memory_service.get_node_edges = AsyncMock(return_value=[])

        # Execute
        result = await identity_resolution.remove_identity_mapping(
            "user@example.com",
            "email",
            "nonexistent",
            "discord_id",
            mock_memory_service,
        )

        # Verify not found
        assert result is False


class TestGetIdentityGraph:
    """Test get_identity_graph() for visualization."""

    @pytest.mark.asyncio
    async def test_get_single_node_graph(self, mock_memory_service, sample_identity_nodes):
        """Test getting graph with single node."""
        email_node = sample_identity_nodes["email"]

        mock_memory_service.recall = AsyncMock(return_value=[email_node])
        mock_memory_service.get_node_edges = AsyncMock(return_value=[])

        # Execute
        graph = await identity_resolution.get_identity_graph("user@example.com", mock_memory_service, depth=2)

        # Verify graph structure
        assert len(graph["nodes"]) == 1
        assert len(graph["edges"]) == 0
        assert graph["nodes"][0]["identifier_type"] == "email"
        assert graph["nodes"][0]["identifier_value"] == "user@example.com"

    @pytest.mark.asyncio
    async def test_get_connected_graph(self, mock_memory_service, sample_identity_nodes, sample_identity_edges):
        """Test getting graph with connected nodes."""
        email_node = sample_identity_nodes["email"]
        discord_node = sample_identity_nodes["discord"]
        edge1 = sample_identity_edges["email_discord"]

        # Setup recall responses
        def recall_side_effect(query):
            if "email:user@example.com" in query.node_id:
                return [email_node]
            elif "discord_id:123456789" in query.node_id:
                return [discord_node]
            return []

        # Setup edges
        def get_edges_side_effect(node_id, scope):
            if "email:user@example.com" in node_id:
                return [edge1]
            elif "discord_id:123456789" in node_id:
                return [edge1]
            return []

        mock_memory_service.recall = AsyncMock(side_effect=recall_side_effect)
        mock_memory_service.get_node_edges = AsyncMock(side_effect=get_edges_side_effect)

        # Execute
        graph = await identity_resolution.get_identity_graph("user@example.com", mock_memory_service, depth=2)

        # Verify graph structure
        assert len(graph["nodes"]) == 2
        assert len(graph["edges"]) >= 1
        assert graph["edges"][0]["relationship"] == "same_as"
        assert graph["edges"][0]["confidence"] == 1.0


class TestMergeUserIdentities:
    """Test merge_user_identities() for merging identity graphs."""

    @pytest.mark.asyncio
    async def test_merge_two_separate_identities(
        self, mock_memory_service, sample_identity_nodes, sample_identity_edges
    ):
        """Test merging two separate identity graphs."""
        email_node = sample_identity_nodes["email"]
        discord_node = sample_identity_nodes["discord"]
        reddit_node = sample_identity_nodes["reddit"]
        edge1 = sample_identity_edges["email_discord"]

        # Setup recall responses
        def recall_side_effect(query):
            if "email:user@example.com" in query.node_id:
                return [email_node]
            elif "email:olduser@example.com" in query.node_id:
                return [reddit_node]  # Pretend reddit is secondary email
            elif "discord_id:123456789" in query.node_id:
                return [discord_node]
            return []

        # Setup edges - primary has discord, secondary has nothing
        def get_edges_side_effect(node_id, scope):
            if "email:user@example.com" in node_id:
                return [edge1]
            elif "discord_id:123456789" in node_id:
                return [edge1]
            return []

        mock_memory_service.recall = AsyncMock(side_effect=recall_side_effect)
        mock_memory_service.get_node_edges = AsyncMock(side_effect=get_edges_side_effect)

        # Execute merge
        merged = await identity_resolution.merge_user_identities(
            "user@example.com",
            "olduser@example.com",
            mock_memory_service,
        )

        # Verify merged identity
        assert merged is not None
        # At minimum should have primary identifier
        assert any(id.identifier_value == "user@example.com" for id in merged.identifiers)


class TestValidateIdentityMapping:
    """Test validate_identity_mapping() for confidence scoring."""

    @pytest.mark.asyncio
    async def test_validate_direct_oauth_mapping(self, mock_memory_service, sample_identity_edges):
        """Test validating direct OAuth mapping has high confidence."""
        edge = sample_identity_edges["email_discord"]

        mock_memory_service.get_node_edges = AsyncMock(return_value=[edge])

        # Mock get_all_identifiers to return empty (no conflicts)
        with patch(
            "ciris_engine.logic.utils.identity_resolution.get_all_identifiers",
            return_value=[],
        ):
            # Execute
            confidence = await identity_resolution.validate_identity_mapping(
                "user@example.com",
                "email",
                "123456789",
                "discord_id",
                mock_memory_service,
            )

            # Verify high confidence
            assert confidence.score == 1.0
            assert confidence.recommendation == "accept"
            assert len(confidence.evidence) > 0

    @pytest.mark.asyncio
    async def test_validate_no_mapping(self, mock_memory_service):
        """Test validating non-existent mapping has zero confidence."""
        mock_memory_service.get_node_edges = AsyncMock(return_value=[])

        # Execute
        confidence = await identity_resolution.validate_identity_mapping(
            "user@example.com",
            "email",
            "nonexistent",
            "discord_id",
            mock_memory_service,
        )

        # Verify zero confidence
        assert confidence.score == 0.0
        assert confidence.recommendation == "reject"
        assert len(confidence.evidence) > 0


class TestIdentityResolutionIntegration:
    """Integration tests for complete identity resolution workflows."""

    @pytest.mark.asyncio
    async def test_complete_identity_lifecycle(self, mock_memory_service):
        """Test complete lifecycle: create, link, resolve, unlink."""
        # Step 1: Add first mapping
        edge1 = await identity_resolution.add_identity_mapping(
            "user@example.com",
            "email",
            "123456789",
            "discord_id",
            mock_memory_service,
            source="oauth",
        )
        assert edge1.relationship == "same_as"

        # Setup mock to return created nodes
        email_node = GraphNode(
            id="user_identity:email:user@example.com",
            type=NodeType.IDENTITY,
            scope=GraphScope.ENVIRONMENT,
            attributes={
                "identifier_type": "email",
                "identifier_value": "user@example.com",
                "created_by": "identity_resolution",
            },
        )
        discord_node = GraphNode(
            id="user_identity:discord_id:123456789",
            type=NodeType.IDENTITY,
            scope=GraphScope.ENVIRONMENT,
            attributes={
                "identifier_type": "discord_id",
                "identifier_value": "123456789",
                "created_by": "identity_resolution",
            },
        )

        # Setup recall to return nodes
        def recall_side_effect(query):
            if "email:user@example.com" in query.node_id:
                return [email_node]
            elif "discord_id:123456789" in query.node_id:
                return [discord_node]
            return []

        # Setup edges
        def get_edges_side_effect(node_id, scope):
            if "email:user@example.com" in node_id or "discord_id:123456789" in node_id:
                return [edge1]
            return []

        mock_memory_service.recall = AsyncMock(side_effect=recall_side_effect)
        mock_memory_service.get_node_edges = AsyncMock(side_effect=get_edges_side_effect)

        # Step 2: Resolve identity
        identity = await identity_resolution.resolve_user_identity("user@example.com", mock_memory_service)
        assert identity is not None
        assert len(identity.identifiers) >= 1

        # Step 3: Validate mapping
        confidence = await identity_resolution.validate_identity_mapping(
            "user@example.com",
            "email",
            "123456789",
            "discord_id",
            mock_memory_service,
        )
        assert confidence.score > 0.0
