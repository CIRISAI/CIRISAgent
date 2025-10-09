"""Tests for automatic user node creation in system_snapshot_helpers.py

Tests cover:
- Automatic node creation when user doesn't exist
- Admin user defaults (wa-, admin)
- Regular user defaults
- Node persistence via memory service
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.context.system_snapshot_helpers import (
    _create_default_user_node,
    _determine_if_admin_user,
    _enrich_single_user_profile,
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType

# =============================================================================
# ADMIN DETECTION TESTS
# =============================================================================


def test_determine_if_admin_user_wa_prefix():
    """Test admin detection for WA user IDs."""
    assert _determine_if_admin_user("wa-2025-08-25-391F3E") is True
    assert _determine_if_admin_user("WA-test-123") is True


def test_determine_if_admin_user_admin():
    """Test admin detection for 'admin' user ID."""
    assert _determine_if_admin_user("admin") is True
    assert _determine_if_admin_user("ADMIN") is True
    assert _determine_if_admin_user("admin_123") is True


def test_determine_if_admin_user_regular():
    """Test admin detection for regular user IDs."""
    assert _determine_if_admin_user("test-user-123") is False
    assert _determine_if_admin_user("user_456") is False
    assert _determine_if_admin_user("123456789") is False


# =============================================================================
# DEFAULT NODE CREATION TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_create_default_user_node_admin():
    """Test creating default node for admin user."""
    # Setup mock memory service
    memory_service = AsyncMock()
    memory_service.memorize = AsyncMock()

    # Create node for admin user
    node = await _create_default_user_node("admin", memory_service, "test-channel")

    # Verify node structure
    assert node is not None
    assert node.id == "user/admin"
    assert node.type == NodeType.USER
    assert node.scope == GraphScope.LOCAL

    # Verify admin attributes
    attrs = node.attributes
    assert attrs["user_id"] == "admin"
    assert attrs["display_name"] == "Admin"
    assert attrs["trust_level"] == 1.0
    assert "first_seen" in attrs
    assert attrs["created_by"] == "UserEnrichment"
    assert attrs["channels"] == ["test-channel"]

    # Verify memorize was called
    memory_service.memorize.assert_called_once()
    call_args = memory_service.memorize.call_args
    assert call_args[0][0] == node  # First arg is the node


@pytest.mark.asyncio
async def test_create_default_user_node_wa_user():
    """Test creating default node for WA user."""
    memory_service = AsyncMock()
    memory_service.memorize = AsyncMock()

    # Create node for WA user
    node = await _create_default_user_node("wa-2025-test", memory_service, None)

    # Verify node structure
    assert node is not None
    assert node.id == "user/wa-2025-test"

    # Verify WA-specific attributes
    attrs = node.attributes
    assert attrs["user_id"] == "wa-2025-test"
    assert attrs["display_name"] == "Admin"
    assert attrs["trust_level"] == 1.0
    assert attrs["is_wa"] is True  # WA users should be marked
    assert "channels" not in attrs  # No channel provided

    # Verify memorize was called
    memory_service.memorize.assert_called_once()


@pytest.mark.asyncio
async def test_create_default_user_node_regular_user():
    """Test creating default node for regular user."""
    memory_service = AsyncMock()
    memory_service.memorize = AsyncMock()

    # Create node for regular user
    node = await _create_default_user_node("user-123", memory_service, "discord-456")

    # Verify node structure
    assert node is not None
    assert node.id == "user/user-123"

    # Verify regular user attributes
    attrs = node.attributes
    assert attrs["user_id"] == "user-123"
    assert attrs["display_name"] == "User_user-123"
    assert attrs["trust_level"] == 0.5  # Lower trust for new users
    assert attrs["communication_style"] == "formal"
    assert attrs["preferred_language"] == "en"
    assert attrs["timezone"] == "UTC"
    assert attrs["channels"] == ["discord-456"]

    # Verify memorize was called
    memory_service.memorize.assert_called_once()


@pytest.mark.asyncio
async def test_create_default_user_node_handles_errors():
    """Test error handling during node creation."""
    # Setup memory service that fails
    memory_service = AsyncMock()
    memory_service.memorize = AsyncMock(side_effect=RuntimeError("Database error"))

    # Should return None on error, not raise
    node = await _create_default_user_node("test-user", memory_service, None)

    assert node is None


# =============================================================================
# ENRICHMENT WITH AUTOCREATION TESTS
# =============================================================================


@pytest.mark.asyncio
async def test_enrich_single_user_profile_creates_node_when_missing():
    """Test that enrichment creates node when user doesn't exist."""
    # Setup mock memory service
    memory_service = AsyncMock()
    # First call (recall) returns empty - no existing node
    memory_service.recall = AsyncMock(return_value=[])
    # Second call (after creation) should also return empty for edges query
    memory_service.memorize = AsyncMock()

    # Mock the persistence.get_db_connection to avoid database access
    import ciris_engine.logic.persistence as persistence_module

    mock_conn = Mock()
    mock_cursor = Mock()
    mock_cursor.fetchall = Mock(return_value=[])
    mock_conn.cursor = Mock(return_value=mock_cursor)
    mock_conn.__enter__ = Mock(return_value=mock_conn)
    mock_conn.__exit__ = Mock(return_value=False)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(persistence_module, "get_db_connection", Mock(return_value=mock_conn))

        # Call enrichment
        profile = await _enrich_single_user_profile("test-user-789", memory_service, "test-channel")

        # Verify node was created
        memory_service.memorize.assert_called_once()
        created_node = memory_service.memorize.call_args[0][0]
        assert created_node.id == "user/test-user-789"
        assert created_node.type == NodeType.USER

        # Verify profile was returned
        assert profile is not None
        assert profile.user_id == "test-user-789"
        assert profile.display_name == "User_test-user-789"


@pytest.mark.asyncio
async def test_enrich_single_user_profile_uses_existing_node():
    """Test that enrichment uses existing node without creating new one."""
    # Setup mock memory service
    memory_service = AsyncMock()

    # Create existing node
    existing_node = GraphNode(
        id="user/existing-user",
        type=NodeType.USER,
        scope=GraphScope.LOCAL,
        attributes={
            "user_id": "existing-user",
            "display_name": "Existing User",
            "first_seen": datetime.now(timezone.utc).isoformat(),
            "trust_level": 0.8,
        },
    )

    # Recall returns existing node
    memory_service.recall = AsyncMock(return_value=[existing_node])

    # Mock the persistence for edges
    import ciris_engine.logic.persistence as persistence_module

    mock_conn = Mock()
    mock_cursor = Mock()
    mock_cursor.fetchall = Mock(return_value=[])
    mock_conn.cursor = Mock(return_value=mock_cursor)
    mock_conn.__enter__ = Mock(return_value=mock_conn)
    mock_conn.__exit__ = Mock(return_value=False)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(persistence_module, "get_db_connection", Mock(return_value=mock_conn))

        # Call enrichment
        profile = await _enrich_single_user_profile("existing-user", memory_service, None)

        # Verify node was NOT created (memorize not called)
        memory_service.memorize.assert_not_called()

        # Verify profile was returned from existing node
        assert profile is not None
        assert profile.user_id == "existing-user"
        assert profile.display_name == "Existing User"
        assert profile.trust_level == 0.8
