"""
Comprehensive tests for ConsentService 14-day graph cleanup functionality.

Tests the graph node deletion via memory_bus.forget() for expired consents.
"""

from datetime import datetime, timedelta, timezone
from typing import List
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.services.governance.consent import ConsentService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import ConsentCategory, ConsentStatus, ConsentStream
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


def _ok_result() -> MemoryOpResult:
    """Create successful MemoryOpResult."""
    return MemoryOpResult(status=MemoryOpStatus.OK)


def _error_result() -> MemoryOpResult:
    """Create failed MemoryOpResult."""
    return MemoryOpResult(status=MemoryOpStatus.ERROR, error="Test error")


class TestConsentServiceGraphCleanup:
    """Test suite for ConsentService 14-day graph cleanup functionality."""

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock(spec=TimeServiceProtocol)
        mock.now.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        return mock

    @pytest.fixture
    def mock_memory_bus(self):
        """Create a mock memory bus with forget capability."""
        mock = AsyncMock()
        mock.search = AsyncMock(return_value=[])
        mock.forget = AsyncMock(return_value=_ok_result())
        return mock

    @pytest.fixture
    def consent_service(self, mock_time_service, mock_memory_bus):
        """Create consent service with mocked dependencies."""
        service = ConsentService(time_service=mock_time_service, memory_bus=mock_memory_bus, db_path=None)
        service._consent_cache = {}
        return service

    @pytest.fixture
    def expired_consent_node_15_days(self, mock_time_service):
        """Create a consent node expired 15 days ago (beyond 14-day retention)."""
        now = mock_time_service.now()
        return GraphNode(
            id="consent_expired_15d",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "user_expired_15d",
                "stream": ConsentStream.TEMPORARY.value,
                "expires_at": (now - timedelta(days=15)).isoformat(),
            },
            updated_by="test",
            updated_at=now - timedelta(days=15),
        )

    @pytest.fixture
    def expired_consent_node_1_day(self, mock_time_service):
        """Create a consent node expired 1 day ago (within soft window)."""
        now = mock_time_service.now()
        return GraphNode(
            id="consent_expired_1d",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "user_expired_1d",
                "stream": ConsentStream.TEMPORARY.value,
                "expires_at": (now - timedelta(days=1)).isoformat(),
            },
            updated_by="test",
            updated_at=now - timedelta(days=1),
        )

    @pytest.fixture
    def valid_consent_node(self, mock_time_service):
        """Create a valid (non-expired) consent node."""
        now = mock_time_service.now()
        return GraphNode(
            id="consent_valid",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "user_valid",
                "stream": ConsentStream.TEMPORARY.value,
                "expires_at": (now + timedelta(days=7)).isoformat(),
            },
            updated_by="test",
            updated_at=now,
        )

    @pytest.fixture
    def partnered_consent_node(self, mock_time_service):
        """Create a partnered consent node (never expires)."""
        now = mock_time_service.now()
        return GraphNode(
            id="consent_partnered",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "user_partnered",
                "stream": ConsentStream.PARTNERED.value,
            },
            updated_by="test",
            updated_at=now - timedelta(days=30),
        )

    # ========== Test _find_expired_nodes ==========

    @pytest.mark.asyncio
    async def test_find_expired_nodes_returns_expired_only(
        self,
        consent_service,
        mock_memory_bus,
        mock_time_service,
        expired_consent_node_15_days,
        expired_consent_node_1_day,
        valid_consent_node,
    ):
        """Test _find_expired_nodes returns only expired nodes."""
        mock_memory_bus.search.return_value = [
            expired_consent_node_15_days,
            expired_consent_node_1_day,
            valid_consent_node,
        ]
        current_time = mock_time_service.now()

        nodes, user_ids = await consent_service._find_expired_nodes(current_time)

        # Both expired nodes should be found
        assert len(nodes) == 2
        assert "user_expired_15d" in user_ids
        assert "user_expired_1d" in user_ids
        assert "user_valid" not in user_ids

    @pytest.mark.asyncio
    async def test_find_expired_nodes_excludes_partnered(
        self, consent_service, mock_memory_bus, mock_time_service, expired_consent_node_1_day, partnered_consent_node
    ):
        """Test _find_expired_nodes excludes partnered consents."""
        mock_memory_bus.search.return_value = [
            expired_consent_node_1_day,
            partnered_consent_node,
        ]
        current_time = mock_time_service.now()

        nodes, user_ids = await consent_service._find_expired_nodes(current_time)

        assert len(nodes) == 1
        assert "user_expired_1d" in user_ids
        assert "user_partnered" not in user_ids

    @pytest.mark.asyncio
    async def test_find_expired_nodes_empty_graph(self, consent_service, mock_memory_bus, mock_time_service):
        """Test _find_expired_nodes with empty graph returns empty."""
        mock_memory_bus.search.return_value = []
        current_time = mock_time_service.now()

        nodes, user_ids = await consent_service._find_expired_nodes(current_time)

        assert nodes == []
        assert user_ids == []

    @pytest.mark.asyncio
    async def test_find_expired_nodes_includes_cache(self, consent_service, mock_memory_bus, mock_time_service):
        """Test _find_expired_nodes also checks cache."""
        mock_memory_bus.search.return_value = []
        current_time = mock_time_service.now()

        # Add expired entry to cache
        consent_service._consent_cache["cache_expired"] = ConsentStatus(
            user_id="cache_expired",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=current_time - timedelta(days=20),
            expires_at=current_time - timedelta(days=5),
            last_modified=current_time - timedelta(days=5),
            attribution_count=0,
            impact_score=0.0,
        )

        nodes, user_ids = await consent_service._find_expired_nodes(current_time)

        # Cache expired user should be included
        assert "cache_expired" in user_ids

    # ========== Test _delete_expired_from_graph ==========

    @pytest.mark.asyncio
    async def test_delete_expired_from_graph_success(
        self, consent_service, mock_memory_bus, expired_consent_node_15_days
    ):
        """Test successful deletion of expired nodes from graph."""
        mock_memory_bus.forget.return_value = _ok_result()

        deleted = await consent_service._delete_expired_from_graph([expired_consent_node_15_days])

        assert deleted == 1
        mock_memory_bus.forget.assert_called_once()
        # forget() is called with node as positional arg
        call_args = mock_memory_bus.forget.call_args[0]
        assert call_args[0] == expired_consent_node_15_days

    @pytest.mark.asyncio
    async def test_delete_expired_from_graph_multiple(
        self, consent_service, mock_memory_bus, expired_consent_node_15_days, expired_consent_node_1_day
    ):
        """Test deletion of multiple expired nodes."""
        mock_memory_bus.forget.return_value = _ok_result()

        deleted = await consent_service._delete_expired_from_graph(
            [
                expired_consent_node_15_days,
                expired_consent_node_1_day,
            ]
        )

        assert deleted == 2
        assert mock_memory_bus.forget.call_count == 2

    @pytest.mark.asyncio
    async def test_delete_expired_from_graph_partial_failure(
        self, consent_service, mock_memory_bus, expired_consent_node_15_days, expired_consent_node_1_day
    ):
        """Test partial failure in deletion returns correct count."""
        # First call succeeds, second fails
        mock_memory_bus.forget.side_effect = [
            _ok_result(),
            _error_result(),
        ]

        deleted = await consent_service._delete_expired_from_graph(
            [
                expired_consent_node_15_days,
                expired_consent_node_1_day,
            ]
        )

        assert deleted == 1  # Only first deletion counted

    @pytest.mark.asyncio
    async def test_delete_expired_from_graph_empty_list(self, consent_service, mock_memory_bus):
        """Test deletion with empty list returns 0."""
        deleted = await consent_service._delete_expired_from_graph([])

        assert deleted == 0
        mock_memory_bus.forget.assert_not_called()

    @pytest.mark.asyncio
    async def test_delete_expired_from_graph_no_memory_bus(self, mock_time_service, expired_consent_node_15_days):
        """Test deletion without memory bus returns 0."""
        service = ConsentService(time_service=mock_time_service, memory_bus=None)

        deleted = await service._delete_expired_from_graph([expired_consent_node_15_days])

        assert deleted == 0

    @pytest.mark.asyncio
    async def test_delete_expired_from_graph_exception_handling(
        self, consent_service, mock_memory_bus, expired_consent_node_15_days, expired_consent_node_1_day
    ):
        """Test exception handling during deletion."""
        mock_memory_bus.forget.side_effect = [
            Exception("Network error"),
            _ok_result(),
        ]

        with patch("ciris_engine.logic.services.governance.consent.service.logger") as mock_logger:
            deleted = await consent_service._delete_expired_from_graph(
                [
                    expired_consent_node_15_days,
                    expired_consent_node_1_day,
                ]
            )

            # Exception on first, success on second
            assert deleted == 1
            mock_logger.warning.assert_called()

    # ========== Test full cleanup_expired integration ==========

    @pytest.mark.asyncio
    async def test_cleanup_expired_full_flow(
        self, consent_service, mock_memory_bus, mock_time_service, expired_consent_node_15_days, valid_consent_node
    ):
        """Integration test: full cleanup deletes from graph and cache."""
        mock_memory_bus.search.return_value = [
            expired_consent_node_15_days,
            valid_consent_node,
        ]
        mock_memory_bus.forget.return_value = _ok_result()

        # Add matching cache entry
        now = mock_time_service.now()
        consent_service._consent_cache["user_expired_15d"] = ConsentStatus(
            user_id="user_expired_15d",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=now - timedelta(days=30),
            expires_at=now - timedelta(days=15),
            last_modified=now - timedelta(days=15),
            attribution_count=0,
            impact_score=0.0,
        )

        result = await consent_service.cleanup_expired()

        # Should delete 1 from graph + 1 from cache = 2 total
        assert result == 2
        assert "user_expired_15d" not in consent_service._consent_cache
        mock_memory_bus.forget.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_expired_graph_only(
        self, consent_service, mock_memory_bus, mock_time_service, expired_consent_node_15_days
    ):
        """Test cleanup when expired consent is only in graph."""
        mock_memory_bus.search.return_value = [expired_consent_node_15_days]
        mock_memory_bus.forget.return_value = _ok_result()
        # Empty cache
        consent_service._consent_cache = {}

        result = await consent_service.cleanup_expired()

        assert result == 1
        mock_memory_bus.forget.assert_called_once()

    @pytest.mark.asyncio
    async def test_cleanup_expired_cache_only(self, consent_service, mock_memory_bus, mock_time_service):
        """Test cleanup when expired consent is only in cache."""
        mock_memory_bus.search.return_value = []  # Nothing in graph
        now = mock_time_service.now()

        consent_service._consent_cache["cache_only_expired"] = ConsentStatus(
            user_id="cache_only_expired",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=now - timedelta(days=20),
            expires_at=now - timedelta(days=5),
            last_modified=now - timedelta(days=5),
            attribution_count=0,
            impact_score=0.0,
        )

        result = await consent_service.cleanup_expired()

        assert result == 1
        assert "cache_only_expired" not in consent_service._consent_cache
        mock_memory_bus.forget.assert_not_called()  # Nothing to delete from graph

    @pytest.mark.asyncio
    async def test_cleanup_expired_preserves_valid(
        self, consent_service, mock_memory_bus, mock_time_service, expired_consent_node_15_days, valid_consent_node
    ):
        """Test cleanup preserves valid consents."""
        mock_memory_bus.search.return_value = [
            expired_consent_node_15_days,
            valid_consent_node,
        ]
        mock_memory_bus.forget.return_value = _ok_result()

        now = mock_time_service.now()
        consent_service._consent_cache = {
            "user_expired_15d": ConsentStatus(
                user_id="user_expired_15d",
                stream=ConsentStream.TEMPORARY,
                categories=[ConsentCategory.INTERACTION],
                granted_at=now - timedelta(days=30),
                expires_at=now - timedelta(days=15),
                last_modified=now - timedelta(days=15),
                attribution_count=0,
                impact_score=0.0,
            ),
            "user_valid": ConsentStatus(
                user_id="user_valid",
                stream=ConsentStream.TEMPORARY,
                categories=[ConsentCategory.PREFERENCE],
                granted_at=now - timedelta(days=5),
                expires_at=now + timedelta(days=7),
                last_modified=now,
                attribution_count=0,
                impact_score=0.0,
            ),
        }

        await consent_service.cleanup_expired()

        # Valid user should still be in cache
        assert "user_valid" in consent_service._consent_cache
        assert "user_expired_15d" not in consent_service._consent_cache

    @pytest.mark.asyncio
    async def test_cleanup_expired_increments_counter(self, consent_service, mock_memory_bus):
        """Test cleanup increments the cleanup counter."""
        mock_memory_bus.search.return_value = []
        initial_count = consent_service._expired_cleanups

        await consent_service.cleanup_expired()

        assert consent_service._expired_cleanups == initial_count + 1

    @pytest.mark.asyncio
    async def test_cleanup_expired_14_day_boundary(self, consent_service, mock_memory_bus, mock_time_service):
        """Test cleanup at exact 14-day boundary."""
        now = mock_time_service.now()

        # Exactly 14 days expired - should be cleaned up
        exactly_14_days = GraphNode(
            id="consent_14d",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "user_14d",
                "stream": ConsentStream.TEMPORARY.value,
                "expires_at": (now - timedelta(days=14)).isoformat(),
            },
            updated_by="test",
            updated_at=now - timedelta(days=14),
        )

        # 13 days 23 hours - should still be cleaned up (expired)
        almost_14_days = GraphNode(
            id="consent_13d23h",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "user_13d23h",
                "stream": ConsentStream.TEMPORARY.value,
                "expires_at": (now - timedelta(days=13, hours=23)).isoformat(),
            },
            updated_by="test",
            updated_at=now - timedelta(days=13, hours=23),
        )

        mock_memory_bus.search.return_value = [exactly_14_days, almost_14_days]
        mock_memory_bus.forget.return_value = _ok_result()

        result = await consent_service.cleanup_expired()

        # Both should be cleaned up since both are expired
        assert result == 2
