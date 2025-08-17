"""
Unit tests for memory_queries module.

Tests database query utilities for memory API.
"""

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.routes.memory_queries import (
    _parse_datetime,
    get_memory_stats,
    query_timeline_nodes,
    search_nodes,
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


class TestParseDateTime:
    """Test the _parse_datetime utility function."""

    def test_parse_none(self):
        """Test parsing None returns None."""
        assert _parse_datetime(None) is None

    def test_parse_datetime_object(self):
        """Test parsing datetime object returns same object."""
        dt = datetime.now()
        assert _parse_datetime(dt) == dt

    def test_parse_iso_string(self):
        """Test parsing ISO format string."""
        dt_str = "2024-01-15T10:30:45"
        result = _parse_datetime(dt_str)
        assert result is not None
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15

    def test_parse_iso_with_timezone(self):
        """Test parsing ISO format with timezone."""
        dt_str = "2024-01-15T10:30:45+00:00"
        result = _parse_datetime(dt_str)
        assert result is not None

    def test_parse_iso_with_z_timezone(self):
        """Test parsing ISO format with Z timezone."""
        dt_str = "2024-01-15T10:30:45Z"
        result = _parse_datetime(dt_str)
        assert result is not None

    def test_parse_invalid_string(self):
        """Test parsing invalid string returns None."""
        assert _parse_datetime("not a date") is None

    def test_parse_invalid_type(self):
        """Test parsing invalid type returns None."""
        assert _parse_datetime(12345) is None


class TestQueryTimelineNodes:
    """Test query_timeline_nodes function."""

    @pytest.mark.asyncio
    async def test_no_db_path(self):
        """Test returns empty list when no db_path."""
        memory_service = Mock()
        memory_service.db_path = None

        result = await query_timeline_nodes(memory_service)
        assert result == []

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory_query_helpers.DatabaseExecutor.execute_query")
    async def test_successful_query(self, mock_execute):
        """Test successful query returns GraphNodes."""
        # Mock database rows
        mock_execute.return_value = [
            (
                "node1",  # node_id
                "local",  # scope
                "concept",  # node_type
                '{"content": "test"}',  # attributes_json
                1,  # version
                "system",  # updated_by
                "2024-01-15T10:00:00",  # updated_at
                "2024-01-15T09:00:00",  # created_at
            )
        ]

        memory_service = Mock()
        memory_service.db_path = "/test/db.sqlite"

        result = await query_timeline_nodes(memory_service, hours=24)

        assert len(result) == 1
        assert result[0].id == "node1"
        assert result[0].scope == "local"
        assert result[0].type == "concept"

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory_query_helpers.DatabaseExecutor.execute_query")
    async def test_with_filters(self, mock_execute):
        """Test query with scope and node_type filters."""
        mock_execute.return_value = []

        memory_service = Mock()
        memory_service.db_path = "/test/db.sqlite"

        await query_timeline_nodes(
            memory_service, hours=48, scope="identity", node_type="observation", limit=50, exclude_metrics=True
        )

        # Verify execute_query was called
        mock_execute.assert_called_once()
        # call_args[0] is the positional args tuple
        args = mock_execute.call_args[0]
        # execute_query takes (db_path, query, params)
        db_path, query, params = args

        # Check query contains expected clauses
        assert "WHERE updated_at >=" in query
        assert "AND scope = ?" in query
        assert "AND node_type = ?" in query
        assert "LIMIT ?" in query

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory_query_helpers.DatabaseExecutor.execute_query")
    async def test_exclude_metrics_false(self, mock_execute):
        """Test query without excluding metrics."""
        mock_execute.return_value = []

        memory_service = Mock()
        memory_service.db_path = "/test/db.sqlite"

        await query_timeline_nodes(memory_service, exclude_metrics=False)

        db_path, query, params = mock_execute.call_args[0]
        assert "tsdb_data" not in query  # Should not exclude metrics


class TestSearchNodes:
    """Test search_nodes function."""

    @pytest.mark.asyncio
    async def test_no_db_path(self):
        """Test returns empty list when no db_path."""
        memory_service = Mock()
        memory_service.db_path = None

        result = await search_nodes(memory_service)
        assert result == []

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory_query_helpers.DatabaseExecutor.execute_query")
    async def test_text_search(self, mock_execute):
        """Test search with text query."""
        mock_execute.return_value = []

        memory_service = Mock()
        memory_service.db_path = "/test/db.sqlite"

        await search_nodes(memory_service, query="test search")

        db_path, query, params = mock_execute.call_args[0]
        assert "attributes_json LIKE ?" in query
        assert "%test search%" in params

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory_query_helpers.DatabaseExecutor.execute_query")
    async def test_search_with_tags(self, mock_execute):
        """Test search with tags filter."""
        mock_execute.return_value = []

        memory_service = Mock()
        memory_service.db_path = "/test/db.sqlite"

        await search_nodes(memory_service, tags=["important", "urgent"])

        db_path, query, params = mock_execute.call_args[0]
        # Should have two LIKE clauses for tags
        assert query.count("attributes_json LIKE ?") == 2
        assert '%"important"%' in str(params)
        assert '%"urgent"%' in str(params)

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory_query_helpers.DatabaseExecutor.execute_query")
    async def test_search_with_time_range(self, mock_execute):
        """Test search with time range filters."""
        mock_execute.return_value = []

        memory_service = Mock()
        memory_service.db_path = "/test/db.sqlite"

        since = datetime(2024, 1, 1)
        until = datetime(2024, 1, 31)

        await search_nodes(memory_service, since=since, until=until)

        db_path, query, params = mock_execute.call_args[0]
        assert "updated_at >= ?" in query
        assert "updated_at <= ?" in query
        assert since.isoformat() in params
        assert until.isoformat() in params

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory_query_helpers.DatabaseExecutor.execute_query")
    async def test_search_with_pagination(self, mock_execute):
        """Test search with pagination."""
        mock_execute.return_value = []

        memory_service = Mock()
        memory_service.db_path = "/test/db.sqlite"

        await search_nodes(memory_service, limit=10, offset=20)

        db_path, query, params = mock_execute.call_args[0]
        assert "LIMIT 10 OFFSET 20" in query

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory_query_helpers.DatabaseExecutor.execute_query")
    async def test_search_with_all_filters(self, mock_execute):
        """Test search with all filters combined."""
        mock_execute.return_value = [
            (
                "search_result",
                "community",
                "concept",
                '{"name": "found"}',
                2,
                "user",
                datetime.now().isoformat(),
                None,
            )
        ]

        memory_service = Mock()
        memory_service.db_path = "/test/db.sqlite"

        result = await search_nodes(
            memory_service,
            query="concept",
            node_type=NodeType.CONCEPT,
            scope=GraphScope.COMMUNITY,
            since=datetime(2024, 1, 1),
            until=datetime(2024, 12, 31),
            tags=["tag1"],
            limit=5,
            offset=0,
        )

        assert len(result) == 1
        assert result[0].id == "search_result"


class TestGetMemoryStats:
    """Test get_memory_stats function."""

    @pytest.mark.asyncio
    async def test_no_db_path(self):
        """Test returns default stats when no db_path."""
        memory_service = Mock()
        memory_service.db_path = None

        stats = await get_memory_stats(memory_service)

        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0
        assert stats["nodes_by_type"] == {}
        assert stats["nodes_by_scope"] == {}

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory_queries.get_db_connection")
    @patch("os.path.exists")
    @patch("os.path.getsize")
    async def test_successful_stats(self, mock_getsize, mock_exists, mock_get_conn):
        """Test successful stats retrieval."""
        # Mock database connection and cursor
        mock_cursor = MagicMock()
        mock_conn = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=None)
        mock_get_conn.return_value = mock_conn

        # Mock query results
        mock_cursor.fetchone.side_effect = [
            (100,),  # total_nodes
            (50,),  # total_edges
            (10,),  # nodes_24h
            (5,),  # edges_24h
        ]

        mock_cursor.fetchall.side_effect = [
            [("THOUGHT", 30), ("MEMORY", 20), ("TASK", 50)],  # nodes_by_type
            [("SYSTEM", 60), ("IDENTITY", 40)],  # nodes_by_scope
        ]

        # Mock file size
        mock_exists.return_value = True
        mock_getsize.return_value = 1024 * 1024 * 10  # 10 MB

        memory_service = Mock()
        memory_service.db_path = "/test/db.sqlite"

        stats = await get_memory_stats(memory_service)

        assert stats["total_nodes"] == 100
        assert stats["total_edges"] == 50
        assert stats["nodes_by_type"]["THOUGHT"] == 30
        assert stats["nodes_by_type"]["MEMORY"] == 20
        assert stats["nodes_by_scope"]["SYSTEM"] == 60
        assert stats["recent_activity"]["nodes_24h"] == 10
        assert stats["recent_activity"]["edges_24h"] == 5
        assert stats["storage_size_mb"] == 10.0

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.adapters.api.routes.memory_queries.get_db_connection")
    async def test_database_error(self, mock_get_conn):
        """Test handles database errors gracefully."""
        mock_get_conn.side_effect = Exception("Database error")

        memory_service = Mock()
        memory_service.db_path = "/test/db.sqlite"

        stats = await get_memory_stats(memory_service)

        # Should return default stats on error
        assert stats["total_nodes"] == 0
        assert stats["total_edges"] == 0
