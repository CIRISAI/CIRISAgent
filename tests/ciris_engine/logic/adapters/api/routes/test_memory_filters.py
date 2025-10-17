"""
Unit tests for memory filter helper functions.

Tests the memory filtering functions that provide role-based access control:
- filter_nodes_by_user_attribution (Defense Layer 2)
- get_user_allowed_ids (OAuth identity resolution)
- build_user_filter_sql (Defense Layer 1)
- should_apply_user_filtering (Role-based filtering decision)
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.memory_filters import (
    build_user_filter_sql,
    filter_nodes_by_user_attribution,
    get_user_allowed_ids,
    should_apply_user_filtering,
)
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.services.graph_core import GraphNode, GraphNodeAttributes, GraphScope, NodeType


class TestFilterNodesByUserAttribution:
    """Tests for filter_nodes_by_user_attribution (Defense Layer 2)."""

    def test_empty_allowed_ids(self):
        """Should return empty list when no users are allowed."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes=GraphNodeAttributes(
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    created_by="user123",
                ),
            )
        ]

        result = filter_nodes_by_user_attribution(nodes, set())

        assert result == []

    def test_filter_by_created_by(self):
        """Should include nodes where created_by matches allowed user."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes=GraphNodeAttributes(
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    created_by="user123",
                ),
            ),
            GraphNode(
                id="node2",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes=GraphNodeAttributes(
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    created_by="user456",
                ),
            ),
        ]

        allowed_ids = {"user123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)

        assert len(result) == 1
        assert result[0].id == "node1"

    def test_filter_by_user_list(self):
        """Should include nodes where user appears in user_list."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": "other_user",
                    "user_list": ["user123", "user456"],
                },
            )
        ]

        allowed_ids = {"user123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)

        assert len(result) == 1
        assert result[0].id == "node1"

    def test_filter_by_task_summaries(self):
        """Should include nodes where user appears in task_summaries."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": "other_user",
                    "task_summaries": {
                        "task1": {
                            "user_id": "user123",
                            "description": "Test task",
                        }
                    },
                },
            )
        ]

        allowed_ids = {"user123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)

        assert len(result) == 1
        assert result[0].id == "node1"

    def test_filter_by_conversations(self):
        """Should include nodes where user is author in conversations."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": "other_user",
                    "conversations_by_channel": {
                        "channel1": [
                            {
                                "author_id": "user123",
                                "content": "Hello",
                            },
                            {
                                "author_id": "user456",
                                "content": "Hi",
                            },
                        ]
                    },
                },
            )
        ]

        allowed_ids = {"user123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)

        assert len(result) == 1
        assert result[0].id == "node1"

    def test_exclude_unmatched_nodes(self):
        """Should exclude nodes with no matching attribution."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes=GraphNodeAttributes(
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    created_by="user456",
                ),
            )
        ]

        allowed_ids = {"user123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)

        assert len(result) == 0

    def test_oauth_identity_matching(self):
        """Should match OAuth identities in allowed_ids."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes=GraphNodeAttributes(
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    created_by="discord:discord_123",
                ),
            )
        ]

        allowed_ids = {"user123", "discord:discord_123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)

        assert len(result) == 1
        assert result[0].id == "node1"

    def test_multiple_attribution_methods(self):
        """Should match on any attribution method."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": "other_user",
                    "user_list": ["user789"],
                    "task_summaries": {"task1": {"user_id": "user456"}},
                    "conversations_by_channel": {"channel1": [{"author_id": "user123", "content": "Hello"}]},
                },
            )
        ]

        # Should match on conversations (user123)
        allowed_ids = {"user123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)
        assert len(result) == 1

        # Should match on user_list (user789)
        allowed_ids = {"user789"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)
        assert len(result) == 1

        # Should match on task_summaries (user456)
        allowed_ids = {"user456"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)
        assert len(result) == 1

    def test_dict_attributes(self):
        """Should handle dict attributes correctly."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={"created_by": "user123"},
            )
        ]

        allowed_ids = {"user123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)

        assert len(result) == 1

    def test_pydantic_model_dump(self):
        """Should handle Pydantic models with model_dump."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes=GraphNodeAttributes(
                    created_at=datetime.now(timezone.utc),
                    updated_at=datetime.now(timezone.utc),
                    created_by="user123",
                ),
            )
        ]

        allowed_ids = {"user123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)

        assert len(result) == 1

    def test_invalid_task_summaries_format(self):
        """Should handle invalid task_summaries format gracefully."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": "other_user",
                    "task_summaries": "not_a_dict",  # Invalid format
                },
            )
        ]

        allowed_ids = {"user123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)

        assert len(result) == 0

    def test_invalid_conversations_format(self):
        """Should handle invalid conversations format gracefully."""
        nodes = [
            GraphNode(
                id="node1",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "created_by": "other_user",
                    "conversations_by_channel": "not_a_dict",  # Invalid
                },
            )
        ]

        allowed_ids = {"user123"}
        result = filter_nodes_by_user_attribution(nodes, allowed_ids)

        assert len(result) == 0


class TestGetUserAllowedIds:
    """Tests for get_user_allowed_ids (OAuth identity resolution)."""

    @pytest.mark.asyncio
    async def test_base_user_id_always_included(self):
        """Should always include the base user_id."""
        auth_service = Mock()
        mock_conn = Mock()
        mock_conn.execute_fetchall = AsyncMock(return_value=[])
        mock_conn.__aenter__ = AsyncMock(return_value=mock_conn)
        mock_conn.__aexit__ = AsyncMock(return_value=None)

        mock_db = Mock()
        mock_db.connection = Mock(return_value=mock_conn)
        auth_service.db_manager = mock_db

        result = await get_user_allowed_ids(auth_service, "user123")

        assert "user123" in result
        assert len(result) == 1

    @pytest.mark.asyncio
    async def test_oauth_identities_added(self):
        """Should add OAuth identities to allowed set."""
        import sqlite3
        from unittest.mock import MagicMock, patch

        auth_service = Mock()
        auth_service.db_path = ":memory:"

        # Create actual in-memory SQLite database for testing
        with sqlite3.connect(":memory:") as conn:
            # Create wa_cert table
            conn.execute(
                """
                CREATE TABLE wa_cert (
                    wa_id TEXT,
                    oauth_provider TEXT,
                    oauth_external_id TEXT,
                    active INTEGER
                )
            """
            )
            # Insert test OAuth identities
            conn.execute(
                "INSERT INTO wa_cert (wa_id, oauth_provider, oauth_external_id, active) VALUES (?, ?, ?, ?)",
                ("user123", "discord", "discord_123", 1),
            )
            conn.execute(
                "INSERT INTO wa_cert (wa_id, oauth_provider, oauth_external_id, active) VALUES (?, ?, ?, ?)",
                ("user123", "google", "google_456", 1),
            )
            conn.commit()

            # Patch sqlite3.connect directly in the sqlite3 module
            with patch("sqlite3.connect", return_value=conn):
                result = await get_user_allowed_ids(auth_service, "user123")

        assert "user123" in result
        assert "discord:discord_123" in result
        assert "discord_123" in result
        assert "google:google_456" in result
        assert "google_456" in result
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_database_error_handling(self):
        """Should handle database errors gracefully."""
        from unittest.mock import patch

        auth_service = Mock()
        auth_service.db_path = "/nonexistent/path/to/db.db"

        # Patch sqlite3.connect directly in the sqlite3 module
        with patch("sqlite3.connect", side_effect=Exception("DB error")):
            result = await get_user_allowed_ids(auth_service, "user123")

        # Should still include base user_id even when DB query fails
        assert "user123" in result
        assert len(result) == 1


class TestBuildUserFilterSql:
    """Tests for build_user_filter_sql (Defense Layer 1)."""

    def test_empty_allowed_ids(self):
        """Should return blocking clause for empty allowed_ids."""
        where_clause, params = build_user_filter_sql(set())

        assert where_clause == "AND 1 = 0"
        assert params == []

    def test_single_user_id(self):
        """Should build correct SQL for single user."""
        where_clause, params = build_user_filter_sql({"user123"})

        assert "json_extract(attributes_json, '$.created_by')" in where_clause
        assert "IN (?)" in where_clause
        assert params == ["user123"]

    def test_multiple_user_ids(self):
        """Should build correct SQL for multiple users."""
        where_clause, params = build_user_filter_sql({"user123", "user456", "user789"})

        assert "json_extract(attributes_json, '$.created_by')" in where_clause
        assert "IN (?,?,?)" in where_clause
        assert len(params) == 3
        assert set(params) == {"user123", "user456", "user789"}


class TestShouldApplyUserFiltering:
    """Tests for should_apply_user_filtering."""

    def test_observer_requires_filtering(self):
        """OBSERVER role should require filtering."""
        result = should_apply_user_filtering(UserRole.OBSERVER)
        assert result is True

    def test_admin_bypasses_filtering(self):
        """ADMIN role should bypass filtering."""
        result = should_apply_user_filtering(UserRole.ADMIN)
        assert result is False
