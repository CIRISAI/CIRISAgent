"""
Tests for ConsentService grant_consent() and related helper methods.

Focuses on:
- grant_consent() flow with all consent streams
- PARTNERED applied directly when already partnered (WBD route: test_partnership_wbd_route.py)
- Gaming behavior detection
- Helper method coverage (_validate_consent_request, _get_previous_status, etc.)
- update_consent() method
- Tool handlers (degrade relationship; there is no upgrade tool)
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.services.governance.consent.service import (
    ConsentNotFoundError,
    ConsentService,
    ConsentValidationError,
)
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import ConsentCategory, ConsentRequest, ConsentStatus, ConsentStream


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


class TestValidateConsentRequest:
    """Test _validate_consent_request() helper method."""

    def test_validate_missing_user_id(self, consent_service):
        """Test validation fails when user_id is missing."""
        request = ConsentRequest(
            user_id="",  # Empty user ID
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
        )

        with pytest.raises(ConsentValidationError, match="User ID required"):
            consent_service._validate_consent_request(request)

    def test_validate_partnered_without_categories(self, consent_service):
        """Test validation fails for PARTNERED without categories."""
        request = ConsentRequest(
            user_id="test_user",
            stream=ConsentStream.PARTNERED,
            categories=[],  # No categories
        )

        with pytest.raises(ConsentValidationError, match="PARTNERED requires at least one category"):
            consent_service._validate_consent_request(request)

    def test_validate_valid_temporary_request(self, consent_service):
        """Test validation passes for valid TEMPORARY request."""
        request = ConsentRequest(
            user_id="test_user", stream=ConsentStream.TEMPORARY, categories=[ConsentCategory.INTERACTION]
        )

        # Should not raise
        consent_service._validate_consent_request(request)

    def test_validate_valid_partnered_request(self, consent_service):
        """Test validation passes for valid PARTNERED request."""
        request = ConsentRequest(
            user_id="test_user",
            stream=ConsentStream.PARTNERED,
            categories=[ConsentCategory.INTERACTION, ConsentCategory.PREFERENCE],
        )

        # Should not raise
        consent_service._validate_consent_request(request)


class TestGetPreviousStatus:
    """Test _get_previous_status() helper method."""

    @pytest.mark.asyncio
    async def test_get_previous_status_exists(self, consent_service):
        """Test retrieving existing consent status."""
        existing_status = ConsentStatus(
            user_id="test_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
            last_modified=datetime.now(timezone.utc),
            impact_score=0.0,
            attribution_count=0,
        )

        consent_service.get_consent = AsyncMock(return_value=existing_status)

        result = await consent_service._get_previous_status("test_user")

        assert result == existing_status
        consent_service.get_consent.assert_called_once_with("test_user")

    @pytest.mark.asyncio
    async def test_get_previous_status_not_found(self, consent_service):
        """Test returns None when no previous consent exists."""
        consent_service.get_consent = AsyncMock(side_effect=ConsentNotFoundError("Not found"))

        result = await consent_service._get_previous_status("new_user")

        assert result is None


class TestCreateConsentStatus:
    """Test _create_consent_status() helper method."""

    def test_create_temporary_consent_new_user(self, consent_service, mock_time_service):
        """Test creating TEMPORARY consent for new user."""
        request = ConsentRequest(
            user_id="new_user", stream=ConsentStream.TEMPORARY, categories=[ConsentCategory.INTERACTION]
        )

        status = consent_service._create_consent_status(request, previous_status=None)

        assert status.user_id == "new_user"
        assert status.stream == ConsentStream.TEMPORARY
        assert status.categories == [ConsentCategory.INTERACTION]
        assert status.expires_at is not None
        assert status.granted_at == mock_time_service.now()
        assert status.impact_score == 0.0
        assert status.attribution_count == 0

    def test_create_anonymous_consent_no_expiry(self, consent_service, mock_time_service):
        """Test creating ANONYMOUS consent has no expiry."""
        request = ConsentRequest(
            user_id="anon_user", stream=ConsentStream.ANONYMOUS, categories=[ConsentCategory.RESEARCH]
        )

        status = consent_service._create_consent_status(request, previous_status=None)

        assert status.stream == ConsentStream.ANONYMOUS
        assert status.expires_at is None

    def test_create_consent_preserves_previous_data(self, consent_service, mock_time_service):
        """Test creating consent preserves previous granted_at and scores."""
        previous = ConsentStatus(
            user_id="existing_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2023, 1, 15, tzinfo=timezone.utc),
            last_modified=datetime(2023, 1, 1, tzinfo=timezone.utc),
            impact_score=2.5,
            attribution_count=10,
        )

        request = ConsentRequest(
            user_id="existing_user", stream=ConsentStream.TEMPORARY, categories=[ConsentCategory.PREFERENCE]
        )

        status = consent_service._create_consent_status(request, previous_status=previous)

        assert status.granted_at == previous.granted_at  # Preserved
        assert status.impact_score == 2.5  # Preserved
        assert status.attribution_count == 10  # Preserved
        assert status.categories == [ConsentCategory.PREFERENCE]  # Updated


class TestPersistConsent:
    """Test _persist_consent() helper method."""

    @pytest.mark.asyncio
    async def test_persist_consent_stores_in_graph(self, consent_service, mock_time_service):
        """Test consent is persisted to graph storage."""
        status = ConsentStatus(
            user_id="test_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=mock_time_service.now(),
            expires_at=mock_time_service.now() + timedelta(days=14),
            last_modified=mock_time_service.now(),
            impact_score=0.0,
            attribution_count=0,
        )

        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node") as mock_add:
            await consent_service._persist_consent(status, None, "Test reason", "user")

            # Should call add_graph_node twice (consent node + audit node)
            assert mock_add.call_count == 2

    @pytest.mark.asyncio
    async def test_persist_consent_updates_cache(self, consent_service):
        """Test consent is cached after persistence."""
        status = ConsentStatus(
            user_id="test_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=datetime.now(timezone.utc),
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
            last_modified=datetime.now(timezone.utc),
            impact_score=0.0,
            attribution_count=0,
        )

        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node"):
            await consent_service._persist_consent(status, None, "Test", "user")

        assert "test_user" in consent_service._consent_cache
        assert consent_service._consent_cache["test_user"] == status


class TestGrantConsentFlow:
    """Test grant_consent() main flow."""

    @pytest.mark.asyncio
    async def test_grant_temporary_consent_new_user(self, consent_service):
        """Test granting TEMPORARY consent to new user."""
        request = ConsentRequest(
            user_id="new_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            reason="Testing",
        )

        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node"):
            consent_service.get_consent = AsyncMock(side_effect=ConsentNotFoundError())

            result = await consent_service.grant_consent(request)

            assert result.user_id == "new_user"
            assert result.stream == ConsentStream.TEMPORARY
            assert result.categories == [ConsentCategory.INTERACTION]

    @pytest.mark.asyncio
    async def test_grant_anonymous_consent(self, consent_service):
        """Test granting ANONYMOUS consent."""
        request = ConsentRequest(
            user_id="anon_user", stream=ConsentStream.ANONYMOUS, categories=[ConsentCategory.RESEARCH]
        )

        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node"):
            consent_service.get_consent = AsyncMock(side_effect=ConsentNotFoundError())

            result = await consent_service.grant_consent(request)

            assert result.stream == ConsentStream.ANONYMOUS
            assert result.expires_at is None

    @pytest.mark.asyncio
    async def test_grant_already_partnered_applies_directly(self, consent_service):
        """PARTNERED -> PARTNERED (new categories) applies directly, no deferral."""
        existing_partnered = ConsentStatus(
            user_id="partner_user",
            stream=ConsentStream.PARTNERED,
            categories=[ConsentCategory.INTERACTION],
            granted_at=datetime.now(timezone.utc),
            expires_at=None,
            last_modified=datetime.now(timezone.utc),
            impact_score=1.0,
            attribution_count=5,
        )

        request = ConsentRequest(
            user_id="partner_user", stream=ConsentStream.PARTNERED, categories=[ConsentCategory.PREFERENCE]
        )

        consent_service.get_consent = AsyncMock(return_value=existing_partnered)

        # Already PARTNERED: a category change is the user's own data choice and
        # applies directly — there is nothing to defer (#1251).
        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node"), patch(
            "ciris_engine.logic.services.governance.consent.service.find_open_partnership_task"
        ) as find_open:
            result = await consent_service.grant_consent(request)

        find_open.assert_not_called()
        assert result.stream == ConsentStream.PARTNERED
        assert result.categories == [ConsentCategory.PREFERENCE]
        assert result.attribution_count == 5


class TestUpdateConsentMethod:
    """Test update_consent() method."""

    @pytest.mark.asyncio
    async def test_update_consent_new_user(self, consent_service):
        """Test update_consent creates new consent for user."""
        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node"):
            consent_service.get_consent = AsyncMock(side_effect=ConsentNotFoundError())

            result = await consent_service.update_consent(
                "new_user", ConsentStream.TEMPORARY, [ConsentCategory.INTERACTION], reason="Tool update"
            )

            assert result.user_id == "new_user"
            assert result.stream == ConsentStream.TEMPORARY

    @pytest.mark.asyncio
    async def test_update_consent_existing_user(self, consent_service, mock_time_service):
        """Test update_consent updates existing user's consent."""
        existing = ConsentStatus(
            user_id="existing_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=datetime(2023, 1, 1, tzinfo=timezone.utc),
            expires_at=datetime(2023, 1, 15, tzinfo=timezone.utc),
            last_modified=datetime(2023, 1, 1, tzinfo=timezone.utc),
            impact_score=2.0,
            attribution_count=5,
        )

        with patch("ciris_engine.logic.services.governance.consent.service.add_graph_node"):
            consent_service.get_consent = AsyncMock(return_value=existing)

            result = await consent_service.update_consent(
                "existing_user", ConsentStream.ANONYMOUS, [ConsentCategory.RESEARCH]
            )

            # Should preserve granted_at and scores
            assert result.granted_at == existing.granted_at
            assert result.impact_score == 2.0
            assert result.attribution_count == 5
            # Should update stream and categories
            assert result.stream == ConsentStream.ANONYMOUS
            assert result.categories == [ConsentCategory.RESEARCH]


class TestToolHandlers:
    """Test tool handler methods."""

    @pytest.mark.asyncio
    async def test_degrade_relationship_tool_to_temporary(self, consent_service):
        """Test degrade_relationship_tool downgrades to TEMPORARY."""
        existing = ConsentStatus(
            user_id="user1",
            stream=ConsentStream.PARTNERED,
            categories=[ConsentCategory.INTERACTION, ConsentCategory.PREFERENCE],
            granted_at=datetime.now(timezone.utc),
            expires_at=None,
            last_modified=datetime.now(timezone.utc),
            impact_score=5.0,
            attribution_count=20,
        )

        consent_service.get_consent = AsyncMock(return_value=existing)

        updated_status = ConsentStatus(
            user_id="user1",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=existing.granted_at,
            expires_at=datetime.now(timezone.utc) + timedelta(days=14),
            last_modified=datetime.now(timezone.utc),
            impact_score=5.0,
            attribution_count=20,
        )
        consent_service.update_consent = AsyncMock(return_value=updated_status)

        result = await consent_service._degrade_relationship_tool(
            {"user_id": "user1", "target_stream": "TEMPORARY", "reason": "User requested"}
        )

        assert result["success"] is True
        assert result["current_stream"] == "TEMPORARY"

    @pytest.mark.asyncio
    async def test_degrade_relationship_tool_creates_anonymous_if_not_found(self, consent_service):
        """Test degrade tool creates ANONYMOUS consent if user not found."""
        consent_service.get_consent = AsyncMock(side_effect=ConsentNotFoundError())

        new_status = ConsentStatus(
            user_id="new_user",
            stream=ConsentStream.ANONYMOUS,
            categories=[ConsentCategory.RESEARCH],
            granted_at=datetime.now(timezone.utc),
            expires_at=None,
            last_modified=datetime.now(timezone.utc),
            impact_score=0.0,
            attribution_count=0,
        )
        consent_service.update_consent = AsyncMock(return_value=new_status)

        result = await consent_service._degrade_relationship_tool({"user_id": "new_user", "target_stream": "ANONYMOUS"})

        assert result["success"] is True
        assert result["message"] == "Created ANONYMOUS consent for proactive opt-out"
