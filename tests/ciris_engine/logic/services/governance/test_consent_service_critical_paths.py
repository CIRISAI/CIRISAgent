"""
Tests for ConsentService critical paths to reach 80% coverage.

Focuses on:
- get_consent() with cache, graph loading, and expiry handling
- revoke_consent() and decay protocol
- get_impact_report() with real TSDB data
- check_expiry() flows
- check_pending_partnership()
- Service infrastructure (tool schemas, execute_tool, etc.)
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from ciris_engine.logic.services.governance.consent.service import ConsentNotFoundError, ConsentService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import ConsentCategory, ConsentImpactReport, ConsentStatus, ConsentStream
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    mock = Mock(spec=TimeServiceProtocol)
    mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return mock


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    from ciris_engine.logic.buses.memory_bus import MemoryBus

    mock = AsyncMock(spec=MemoryBus)
    mock.search = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def consent_service(mock_time_service, mock_memory_bus):
    """Create consent service with mocked dependencies."""
    service = ConsentService(time_service=mock_time_service, memory_bus=mock_memory_bus, db_path=None)
    return service


class TestGetConsentCriticalPaths:
    """Test get_consent() with various edge cases."""

    @pytest.mark.asyncio
    async def test_get_consent_from_cache_valid(self, consent_service, mock_time_service):
        """Test getting valid consent from cache."""
        cached_status = ConsentStatus(
            user_id="cached_user",
            stream=ConsentStream.PARTNERED,
            categories=[ConsentCategory.INTERACTION],
            granted_at=mock_time_service.now() - timedelta(days=5),
            expires_at=None,  # PARTNERED doesn't expire
            last_modified=mock_time_service.now() - timedelta(days=1),
            impact_score=2.0,
            attribution_count=10,
        )
        consent_service._consent_cache["cached_user"] = cached_status

        result = await consent_service.get_consent("cached_user")

        assert result == cached_status
        assert consent_service._consent_checks == 1

    @pytest.mark.asyncio
    async def test_get_consent_from_cache_expired(self, consent_service, mock_time_service):
        """Test getting expired TEMPORARY consent from cache."""
        expired_status = ConsentStatus(
            user_id="expired_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=mock_time_service.now() - timedelta(days=20),
            expires_at=mock_time_service.now() - timedelta(days=1),  # Expired yesterday
            last_modified=mock_time_service.now() - timedelta(days=20),
            impact_score=0.5,
            attribution_count=2,
        )
        consent_service._consent_cache["expired_user"] = expired_status

        with pytest.raises(ConsentNotFoundError, match="has expired"):
            await consent_service.get_consent("expired_user")

        # Should be removed from cache
        assert "expired_user" not in consent_service._consent_cache

    @pytest.mark.asyncio
    async def test_get_consent_from_graph(self, consent_service, mock_time_service):
        """Test loading consent from graph when not in cache."""
        mock_node = Mock()
        mock_node.attributes = {
            "stream": "temporary",
            "categories": ["interaction", "preference"],
            "granted_at": mock_time_service.now().isoformat(),
            "expires_at": (mock_time_service.now() + timedelta(days=14)).isoformat(),
            "last_modified": mock_time_service.now().isoformat(),
            "impact_score": 1.5,
            "attribution_count": 5,
        }

        with patch("ciris_engine.logic.services.governance.consent.service.get_graph_node", return_value=mock_node):
            result = await consent_service.get_consent("graph_user")

            assert result.user_id == "graph_user"
            assert result.stream == ConsentStream.TEMPORARY
            assert len(result.categories) == 2
            # Should be cached
            assert "graph_user" in consent_service._consent_cache

    @pytest.mark.asyncio
    async def test_get_consent_from_graph_expired(self, consent_service, mock_time_service):
        """Test loading expired consent from graph."""
        mock_node = Mock()
        mock_node.attributes = {
            "stream": "temporary",
            "categories": ["interaction"],
            "granted_at": (mock_time_service.now() - timedelta(days=20)).isoformat(),
            "expires_at": (mock_time_service.now() - timedelta(days=1)).isoformat(),  # Expired
            "last_modified": (mock_time_service.now() - timedelta(days=20)).isoformat(),
            "impact_score": 0.0,
            "attribution_count": 0,
        }

        with patch("ciris_engine.logic.services.governance.consent.service.get_graph_node", return_value=mock_node):
            with pytest.raises(ConsentNotFoundError, match="has expired"):
                await consent_service.get_consent("expired_graph_user")

    @pytest.mark.asyncio
    async def test_get_consent_not_found_in_graph(self, consent_service):
        """Test getting consent when not found in graph."""
        with patch("ciris_engine.logic.services.governance.consent.service.get_graph_node", return_value=None):
            with pytest.raises(ConsentNotFoundError, match="No consent found"):
                await consent_service.get_consent("nonexistent_user")


class TestRevokeConsentDecayProtocol:
    """Test revoke_consent() and decay protocol."""

    @pytest.mark.asyncio
    async def test_revoke_consent_full_flow(self, consent_service, mock_time_service):
        """Test complete revoke consent and decay protocol."""
        existing = ConsentStatus(
            user_id="revoke_user",
            stream=ConsentStream.PARTNERED,
            categories=[ConsentCategory.INTERACTION, ConsentCategory.PREFERENCE],
            granted_at=mock_time_service.now() - timedelta(days=30),
            expires_at=None,
            last_modified=mock_time_service.now() - timedelta(days=10),
            impact_score=5.0,
            attribution_count=50,
        )

        consent_service.get_consent = AsyncMock(return_value=existing)

        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node") as mock_add:
            decay_status = await consent_service.revoke_consent("revoke_user", reason="User requested deletion")

            assert decay_status.user_id == "revoke_user"
            assert decay_status.identity_severed is True
            assert decay_status.patterns_anonymized is False
            assert decay_status.decay_complete_at == mock_time_service.now() + timedelta(days=90)

            # Should call add_graph_node 3 times (decay node, consent node, audit node)
            assert mock_add.call_count == 3

            # Should be in active decays
            assert "revoke_user" in consent_service._active_decays

            # Should be removed from cache
            assert "revoke_user" not in consent_service._consent_cache

    @pytest.mark.asyncio
    async def test_revoke_consent_with_filter_service(self, consent_service):
        """Test revoke consent triggers filter service anonymization."""
        existing = ConsentStatus(
            user_id="user_with_filter",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
            last_modified=datetime.now(timezone.utc),
            impact_score=0.0,
            attribution_count=0,
        )

        consent_service.get_consent = AsyncMock(return_value=existing)

        # Mock filter service
        mock_filter = AsyncMock()
        mock_filter.anonymize_user_profile = AsyncMock()
        consent_service._filter_service = mock_filter

        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node"):
            await consent_service.revoke_consent("user_with_filter")

            # Should call filter service
            mock_filter.anonymize_user_profile.assert_called_once_with("user_with_filter")


class TestCheckExpiry:
    """Test check_expiry() method."""

    @pytest.mark.asyncio
    async def test_check_expiry_not_expired(self, consent_service, mock_time_service):
        """Test check_expiry returns False for valid consent."""
        valid_status = ConsentStatus(
            user_id="valid_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=mock_time_service.now() - timedelta(days=5),
            expires_at=mock_time_service.now() + timedelta(days=9),  # Expires in future
            last_modified=mock_time_service.now() - timedelta(days=5),
            impact_score=0.0,
            attribution_count=0,
        )

        consent_service.get_consent = AsyncMock(return_value=valid_status)

        is_expired = await consent_service.check_expiry("valid_user")

        assert is_expired is False

    @pytest.mark.asyncio
    async def test_check_expiry_expired(self, consent_service, mock_time_service):
        """Test check_expiry returns True for expired consent."""
        expired_status = ConsentStatus(
            user_id="expired_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=mock_time_service.now() - timedelta(days=20),
            expires_at=mock_time_service.now() - timedelta(days=1),  # Already expired
            last_modified=mock_time_service.now() - timedelta(days=20),
            impact_score=0.0,
            attribution_count=0,
        )

        consent_service.get_consent = AsyncMock(return_value=expired_status)

        is_expired = await consent_service.check_expiry("expired_user")

        assert is_expired is True

    @pytest.mark.asyncio
    async def test_check_expiry_partnered_no_expiry(self, consent_service):
        """Test check_expiry for PARTNERED consent (no expiry)."""
        partnered_status = ConsentStatus(
            user_id="partner",
            stream=ConsentStream.PARTNERED,
            categories=[ConsentCategory.INTERACTION],
            granted_at=datetime.now(timezone.utc) - timedelta(days=100),
            expires_at=None,  # PARTNERED doesn't expire
            last_modified=datetime.now(timezone.utc),
            impact_score=10.0,
            attribution_count=100,
        )

        consent_service.get_consent = AsyncMock(return_value=partnered_status)

        is_expired = await consent_service.check_expiry("partner")

        assert is_expired is False

    @pytest.mark.asyncio
    async def test_check_expiry_user_not_found(self, consent_service):
        """Test check_expiry when user doesn't exist - FAIL FAST, FAIL LOUD."""
        consent_service.get_consent = AsyncMock(side_effect=ConsentNotFoundError("Not found"))

        # Should propagate the exception - no fake defaults!
        with pytest.raises(ConsentNotFoundError):
            await consent_service.check_expiry("nonexistent")


class TestCheckPendingPartnership:
    """Test check_pending_partnership() method."""

    @pytest.mark.asyncio
    async def test_check_pending_partnership_exists(self, consent_service):
        """Test checking pending partnership that exists."""
        consent_service._pending_partnerships["pending_user"] = {
            "task_id": "task_123",
            "request": Mock(),
            "created_at": datetime.now(timezone.utc),
        }

        # Mock the handler to return pending status
        with patch("ciris_engine.logic.utils.consent.partnership_utils.PartnershipRequestHandler") as MockHandler:
            mock_handler = Mock()
            mock_handler.check_task_outcome.return_value = ("pending", None)
            MockHandler.return_value = mock_handler

            status = await consent_service.check_pending_partnership("pending_user")

            assert status == "pending"

    @pytest.mark.asyncio
    async def test_check_pending_partnership_not_exists(self, consent_service):
        """Test checking pending partnership that doesn't exist."""
        task_id = await consent_service.check_pending_partnership("no_pending_user")

        assert task_id is None


class TestGetImpactReport:
    """Test get_impact_report() with TSDB data."""

    @pytest.mark.asyncio
    async def test_get_impact_report_no_memory_bus(self, consent_service):
        """Test get_impact_report fails without memory bus."""
        # First mock get_consent to return a valid status
        status = ConsentStatus(
            user_id="user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
            last_modified=datetime.now(timezone.utc),
            impact_score=0.0,
            attribution_count=0,
        )
        consent_service.get_consent = AsyncMock(return_value=status)

        # Now set memory_bus to None
        consent_service._memory_bus = None

        with pytest.raises(ValueError, match="Memory bus required"):
            await consent_service.get_impact_report("user")

    @pytest.mark.asyncio
    async def test_get_impact_report_with_data(self, consent_service, mock_time_service):
        """Test get_impact_report with real TSDB data."""
        # Mock consent
        status = ConsentStatus(
            user_id="impact_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=mock_time_service.now() - timedelta(days=5),
            expires_at=mock_time_service.now() + timedelta(days=9),
            last_modified=mock_time_service.now(),
            impact_score=2.5,
            attribution_count=15,
        )
        consent_service.get_consent = AsyncMock(return_value=status)

        # Mock conversation summaries
        conv1 = Mock()
        conv1.attributes = {
            "participants": {
                "impact_user": {"user_id": "impact_user", "message_count": 10},
                "other_user": {"user_id": "other_user", "message_count": 5},
            }
        }
        conv2 = Mock()
        conv2.attributes = {
            "participants": {
                "impact_user": {"user_id": "impact_user", "message_count": 8},
            }
        }

        # Mock task summaries
        task1 = Mock()
        task1.attributes = {"author_id": "impact_user", "task_type": "improvement"}
        task2 = Mock()
        task2.attributes = {"author_id": "other_user", "task_type": "research"}

        # Mock memory bus to return different data for different calls
        async def mock_search(query, filters):
            if filters.node_type == NodeType.CONVERSATION_SUMMARY.value:
                return [conv1, conv2]
            elif filters.node_type == NodeType.TASK_SUMMARY.value:
                return [task1, task2]
            return []

        consent_service._memory_bus.search = AsyncMock(side_effect=mock_search)
        consent_service._get_example_contributions = AsyncMock(return_value=["Example contribution"])

        report = await consent_service.get_impact_report("impact_user")

        assert isinstance(report, ConsentImpactReport)
        assert report.user_id == "impact_user"
        assert report.total_interactions == 18  # 10 + 8 from conversations
        assert report.patterns_contributed == 1  # 1 task by impact_user
        assert len(report.example_contributions) == 1


class TestServiceInfrastructure:
    """Test service infrastructure methods."""

    @pytest.mark.asyncio
    async def test_execute_tool_upgrade_relationship(self, consent_service):
        """Test execute_tool dispatches to upgrade handler."""
        consent_service._upgrade_relationship_tool = AsyncMock(
            return_value={"success": True, "status": "PENDING_APPROVAL"}
        )

        result = await consent_service.execute_tool("upgrade_relationship", {"user_id": "test"})

        assert result.status.value == "completed"
        consent_service._upgrade_relationship_tool.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool_unknown_tool(self, consent_service):
        """Test execute_tool with unknown tool."""
        result = await consent_service.execute_tool("unknown_tool", {})

        assert result.status.value == "not_found"
        assert "unknown tool" in result.error.lower()

    @pytest.mark.asyncio
    async def test_get_tool_schema(self, consent_service):
        """Test getting tool parameter schema."""
        schema = await consent_service.get_tool_schema("upgrade_relationship")

        assert schema is not None
        assert schema.type == "object"
        assert "user_id" in schema.properties

    @pytest.mark.asyncio
    async def test_get_tool_schema_unknown(self, consent_service):
        """Test getting schema for unknown tool."""
        schema = await consent_service.get_tool_schema("unknown_tool")

        assert schema is None

    @pytest.mark.asyncio
    async def test_validate_parameters_valid(self, consent_service):
        """Test validating valid parameters."""
        is_valid = await consent_service.validate_parameters("upgrade_relationship", {"user_id": "test"})

        assert is_valid is True

    @pytest.mark.asyncio
    async def test_validate_parameters_missing_required(self, consent_service):
        """Test validating parameters with missing required field."""
        is_valid = await consent_service.validate_parameters("upgrade_relationship", {})

        assert is_valid is False
