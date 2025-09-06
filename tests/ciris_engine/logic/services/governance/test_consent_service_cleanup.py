"""
Comprehensive tests for ConsentService cleanup functionality.

Tests the refactored cleanup_expired method and all its helper functions.
Focuses on cognitive complexity reduction and comprehensive coverage.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock, patch

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.governance.consent import ConsentService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import ConsentStatus, ConsentStream, ConsentCategory
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


class TestConsentServiceCleanup:
    """Test suite for ConsentService cleanup functionality."""

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock(spec=TimeServiceProtocol)
        mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        return mock

    @pytest.fixture
    def mock_memory_bus(self):
        """Create a mock memory bus."""
        mock = AsyncMock(spec=MemoryBus)
        # Pre-configure the query_nodes method to avoid AttributeError
        mock.query_nodes = AsyncMock()
        return mock

    @pytest.fixture
    def consent_service(self, mock_time_service, mock_memory_bus):
        """Create consent service with mocked dependencies."""
        service = ConsentService(
            time_service=mock_time_service,
            memory_bus=mock_memory_bus,
            db_path=None
        )
        # Initialize some test cache data
        service._consent_cache = {}
        return service

    @pytest.fixture
    def expired_consent_status(self, mock_time_service):
        """Create an expired temporary consent status."""
        now = mock_time_service.now()
        return ConsentStatus(
            user_id="expired_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=now - timedelta(days=15),
            expires_at=now - timedelta(days=1),  # Expired yesterday
            last_modified=now - timedelta(days=1),
            attribution_count=5,
            impact_score=0.8
        )

    @pytest.fixture
    def valid_consent_status(self, mock_time_service):
        """Create a valid (non-expired) temporary consent status."""
        now = mock_time_service.now()
        return ConsentStatus(
            user_id="valid_user", 
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.PREFERENCE],
            granted_at=now - timedelta(days=5),
            expires_at=now + timedelta(days=1),  # Expires tomorrow
            last_modified=now - timedelta(days=2),
            attribution_count=3,
            impact_score=0.6
        )

    @pytest.fixture
    def permanent_consent_status(self, mock_time_service):
        """Create a partnered consent status (never expires)."""
        now = mock_time_service.now()
        return ConsentStatus(
            user_id="permanent_user",
            stream=ConsentStream.PARTNERED,
            categories=[ConsentCategory.IMPROVEMENT, ConsentCategory.SHARING],
            granted_at=now - timedelta(days=30),
            expires_at=None,
            last_modified=now - timedelta(days=10),
            attribution_count=10,
            impact_score=0.9
        )

    @pytest.fixture
    def expired_consent_node(self, mock_time_service):
        """Create an expired consent node."""
        return GraphNode(
            id="expired_consent_node",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "expired_user",
                "stream": ConsentStream.TEMPORARY.value,
                "expires_at": (mock_time_service.now() - timedelta(days=1)).isoformat()
            },
            updated_by="test",
            updated_at=mock_time_service.now()
        )

    @pytest.fixture
    def valid_consent_node(self, mock_time_service):
        """Create a valid (non-expired) consent node."""
        return GraphNode(
            id="valid_consent_node",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "valid_user",
                "stream": ConsentStream.TEMPORARY.value,
                "expires_at": (mock_time_service.now() + timedelta(days=1)).isoformat()
            },
            updated_by="test",
            updated_at=mock_time_service.now()
        )

    @pytest.fixture
    def permanent_consent_node(self, mock_time_service):
        """Create a permanent consent node."""
        return GraphNode(
            id="permanent_consent_node",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "permanent_user",
                "stream": ConsentStream.PERMANENT.value,
                # No expires_at for permanent consents
            },
            updated_by="test",
            updated_at=mock_time_service.now()
        )

    # Test main cleanup_expired function (should have low cognitive complexity now)
    @pytest.mark.asyncio
    async def test_cleanup_expired_success(self, consent_service, expired_consent_status):
        """Test successful cleanup of expired consents."""
        # Setup cache with expired consent
        consent_service._consent_cache["expired_user"] = expired_consent_status
        
        # Mock the helper methods
        consent_service._find_expired_user_ids = AsyncMock(return_value=["expired_user"])
        consent_service._perform_cleanup = Mock(return_value=1)
        
        result = await consent_service.cleanup_expired()
        
        assert result == 1
        assert consent_service._expired_cleanups == 1
        consent_service._find_expired_user_ids.assert_called_once()
        consent_service._perform_cleanup.assert_called_once_with(["expired_user"])

    @pytest.mark.asyncio
    async def test_cleanup_expired_no_expired_consents(self, consent_service, valid_consent_status):
        """Test cleanup when no consents are expired."""
        # Setup cache with valid consent
        consent_service._consent_cache["valid_user"] = valid_consent_status
        
        # Mock the helper methods
        consent_service._find_expired_user_ids = AsyncMock(return_value=[])
        consent_service._perform_cleanup = Mock(return_value=0)
        
        result = await consent_service.cleanup_expired()
        
        assert result == 0
        assert consent_service._expired_cleanups == 1

    # Test _find_expired_user_ids (routing function)
    @pytest.mark.asyncio
    async def test_find_expired_user_ids_with_memory_bus(self, consent_service, mock_time_service):
        """Test _find_expired_user_ids routes to graph method when memory bus available."""
        current_time = mock_time_service.now()
        consent_service._find_expired_from_graph = AsyncMock(return_value=["user1", "user2"])
        
        result = await consent_service._find_expired_user_ids(current_time)
        
        assert result == ["user1", "user2"]
        consent_service._find_expired_from_graph.assert_called_once_with(current_time)

    @pytest.mark.asyncio
    async def test_find_expired_user_ids_without_memory_bus(self, mock_time_service):
        """Test _find_expired_user_ids routes to cache method when no memory bus."""
        service = ConsentService(time_service=mock_time_service, memory_bus=None)
        service._find_expired_from_cache = Mock(return_value=["cached_user"])
        current_time = mock_time_service.now()
        
        result = await service._find_expired_user_ids(current_time)
        
        assert result == ["cached_user"]
        service._find_expired_from_cache.assert_called_once_with(current_time)

    # Test _find_expired_from_graph
    @pytest.mark.asyncio
    async def test_find_expired_from_graph_success(
        self, consent_service, mock_time_service, expired_consent_node, valid_consent_node
    ):
        """Test successful graph query for expired consents."""
        current_time = mock_time_service.now()
        consent_service._memory_bus.query_nodes.return_value = [expired_consent_node, valid_consent_node]
        
        # Mock the node extraction method
        consent_service._extract_expired_user_from_node = Mock()
        consent_service._extract_expired_user_from_node.side_effect = ["expired_user", None]
        
        result = await consent_service._find_expired_from_graph(current_time)
        
        assert result == ["expired_user"]
        consent_service._memory_bus.query_nodes.assert_called_once_with(
            node_type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={"service": "consent"}
        )

    @pytest.mark.asyncio
    async def test_find_expired_from_graph_query_exception(self, consent_service, mock_time_service):
        """Test graph query exception handling with cache fallback."""
        current_time = mock_time_service.now()
        consent_service._memory_bus.query_nodes.side_effect = Exception("Graph query failed")
        consent_service._find_expired_from_cache = Mock(return_value=["cache_fallback_user"])
        
        result = await consent_service._find_expired_from_graph(current_time)
        
        assert result == ["cache_fallback_user"]
        consent_service._find_expired_from_cache.assert_called_once_with(current_time)

    # Test _extract_expired_user_from_node
    def test_extract_expired_user_from_node_expired(self, consent_service, expired_consent_node, mock_time_service):
        """Test extraction of user ID from expired consent node."""
        current_time = mock_time_service.now()
        
        result = consent_service._extract_expired_user_from_node(expired_consent_node, current_time)
        
        assert result == "expired_user"

    def test_extract_expired_user_from_node_not_expired(self, consent_service, valid_consent_node, mock_time_service):
        """Test extraction returns None for non-expired consent node."""
        current_time = mock_time_service.now()
        
        result = consent_service._extract_expired_user_from_node(valid_consent_node, current_time)
        
        assert result is None

    def test_extract_expired_user_from_node_no_attributes(self, consent_service, mock_time_service):
        """Test extraction returns None for node without attributes."""
        node = Mock()
        node.attributes = None
        current_time = mock_time_service.now()
        
        result = consent_service._extract_expired_user_from_node(node, current_time)
        
        assert result is None

    def test_extract_expired_user_from_node_not_temporary(self, consent_service, mock_time_service):
        """Test extraction returns None for non-temporary consent."""
        current_time = mock_time_service.now()
        
        # Create a partnered (non-temporary) consent node
        partnered_node = GraphNode(
            id="partnered_consent_node",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "partnered_user",
                "stream": ConsentStream.PARTNERED.value,
                # No expires_at for partnered consents
            },
            updated_by="test",
            updated_at=mock_time_service.now()
        )
        
        result = consent_service._extract_expired_user_from_node(partnered_node, current_time)
        
        assert result is None

    def test_extract_expired_user_from_node_invalid_date(self, consent_service, mock_time_service):
        """Test extraction handles invalid date format gracefully."""
        node = Mock()
        node.attributes = {
            "service": "consent",
            "user_id": "test_user",
            "stream": ConsentStream.TEMPORARY.value,
            "expires_at": "invalid-date-format"
        }
        current_time = mock_time_service.now()
        
        with patch('ciris_engine.logic.services.governance.consent.service.logger') as mock_logger:
            result = consent_service._extract_expired_user_from_node(node, current_time)
            
            assert result is None
            mock_logger.warning.assert_called_once()

    # Test _find_expired_from_cache
    def test_find_expired_from_cache_mixed_consents(
        self, consent_service, mock_time_service, expired_consent_status, 
        valid_consent_status, permanent_consent_status
    ):
        """Test cache-based expired consent detection."""
        current_time = mock_time_service.now()
        consent_service._consent_cache = {
            "expired_user": expired_consent_status,
            "valid_user": valid_consent_status,
            "permanent_user": permanent_consent_status
        }
        
        result = consent_service._find_expired_from_cache(current_time)
        
        assert result == ["expired_user"]

    def test_find_expired_from_cache_empty_cache(self, consent_service, mock_time_service):
        """Test cache-based detection with empty cache."""
        current_time = mock_time_service.now()
        consent_service._consent_cache = {}
        
        result = consent_service._find_expired_from_cache(current_time)
        
        assert result == []

    # Test _is_cache_entry_expired
    def test_is_cache_entry_expired_true(self, consent_service, expired_consent_status, mock_time_service):
        """Test expired cache entry detection."""
        current_time = mock_time_service.now()
        
        result = consent_service._is_cache_entry_expired(expired_consent_status, current_time)
        
        assert result is True

    def test_is_cache_entry_expired_false(self, consent_service, valid_consent_status, mock_time_service):
        """Test non-expired cache entry detection."""
        current_time = mock_time_service.now()
        
        result = consent_service._is_cache_entry_expired(valid_consent_status, current_time)
        
        assert result is False

    def test_is_cache_entry_expired_permanent(self, consent_service, permanent_consent_status, mock_time_service):
        """Test partnered consent never expires."""
        current_time = mock_time_service.now()
        
        result = consent_service._is_cache_entry_expired(permanent_consent_status, current_time)
        
        assert result is False

    def test_is_cache_entry_expired_no_expiry(self, consent_service, mock_time_service):
        """Test consent without expiry date never expires."""
        current_time = mock_time_service.now()
        now = mock_time_service.now()
        status = ConsentStatus(
            user_id="test_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.RESEARCH],
            granted_at=now - timedelta(days=1),
            expires_at=None,  # No expiry date
            last_modified=now - timedelta(hours=1),
            attribution_count=1,
            impact_score=0.5
        )
        
        result = consent_service._is_cache_entry_expired(status, current_time)
        
        assert result is False

    # Test _perform_cleanup
    def test_perform_cleanup_success(self, consent_service, expired_consent_status):
        """Test successful cleanup of expired consents from cache."""
        consent_service._consent_cache = {
            "expired_user": expired_consent_status,
            "other_user": Mock()
        }
        
        with patch('ciris_engine.logic.services.governance.consent.service.logger') as mock_logger:
            result = consent_service._perform_cleanup(["expired_user"])
            
            assert result == 1
            assert "expired_user" not in consent_service._consent_cache
            assert "other_user" in consent_service._consent_cache  # Unchanged
            mock_logger.info.assert_called_once()

    def test_perform_cleanup_user_not_in_cache(self, consent_service):
        """Test cleanup when user is not in cache."""
        consent_service._consent_cache = {}
        
        result = consent_service._perform_cleanup(["nonexistent_user"])
        
        assert result == 0
        assert consent_service._consent_cache == {}

    def test_perform_cleanup_empty_list(self, consent_service, expired_consent_status):
        """Test cleanup with empty expired user list."""
        consent_service._consent_cache = {"user": expired_consent_status}
        
        result = consent_service._perform_cleanup([])
        
        assert result == 0
        assert "user" in consent_service._consent_cache  # Unchanged

    # Integration tests
    @pytest.mark.asyncio
    async def test_full_cleanup_integration_with_graph(
        self, consent_service, mock_time_service, expired_consent_node, valid_consent_node
    ):
        """Integration test: full cleanup flow with graph queries."""
        # Setup
        consent_service._consent_cache = {
            "expired_user": Mock(),
            "valid_user": Mock(),
            "unrelated_user": Mock()
        }
        consent_service._memory_bus.query_nodes.return_value = [expired_consent_node, valid_consent_node]
        
        # Execute
        result = await consent_service.cleanup_expired()
        
        # Verify
        assert result == 1
        assert "expired_user" not in consent_service._consent_cache
        assert "valid_user" in consent_service._consent_cache
        assert "unrelated_user" in consent_service._consent_cache

    @pytest.mark.asyncio
    async def test_full_cleanup_integration_cache_fallback(
        self, consent_service, expired_consent_status, valid_consent_status
    ):
        """Integration test: full cleanup flow with cache fallback."""
        # Setup - no memory bus
        service = ConsentService(time_service=consent_service._time_service, memory_bus=None)
        service._consent_cache = {
            "expired_user": expired_consent_status,
            "valid_user": valid_consent_status
        }
        
        # Execute
        result = await service.cleanup_expired()
        
        # Verify
        assert result == 1
        assert "expired_user" not in service._consent_cache
        assert "valid_user" in service._consent_cache