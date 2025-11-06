"""Unit tests for DSAROrchestrator ConsentService integration."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.services.governance.consent import ConsentService
from ciris_engine.logic.services.governance.consent.dsar_automation import DSARAutomationService
from ciris_engine.logic.services.governance.dsar.orchestrator import DSAROrchestrator
from ciris_engine.logic.services.governance.dsar.schemas import (
    DataSourceDeletion,
    MultiSourceDSARDeletionResult,
)
from ciris_engine.schemas.consent.core import ConsentDecayStatus, DSARDeletionStatus


@pytest.fixture
def mock_time_service():
    """Mock time service."""
    time_service = MagicMock()
    time_service.now.return_value = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    return time_service


@pytest.fixture
def mock_consent_service():
    """Mock consent service."""
    consent_service = AsyncMock(spec=ConsentService)

    # Mock revoke_consent to return decay status
    consent_service.revoke_consent.return_value = ConsentDecayStatus(
        user_id="test@example.com",
        decay_started=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        identity_severed=True,
        patterns_anonymized=False,
        decay_complete_at=datetime(2025, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
        safety_patterns_retained=0,
    )

    return consent_service


@pytest.fixture
def mock_dsar_automation():
    """Mock DSAR automation service."""
    dsar_automation = AsyncMock(spec=DSARAutomationService)

    # Mock get_deletion_status
    dsar_automation.get_deletion_status.return_value = DSARDeletionStatus(
        ticket_id="REQ-DELETE-001",
        user_id="test@example.com",
        decay_started=datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc),
        current_phase="identity_severed",
        completion_percentage=5.0,
        estimated_completion=datetime(2025, 4, 15, 12, 0, 0, tzinfo=timezone.utc),
        milestones_completed=["consent_revoked"],
        next_milestone="interaction_history_purged",
        safety_patterns_retained=0,
    )

    return dsar_automation


@pytest.fixture
def mock_tool_bus():
    """Mock tool bus."""
    tool_bus = MagicMock()  # Not AsyncMock - get_tools_by_metadata is not async
    tool_bus.get_tools_by_metadata.return_value = []  # No SQL connectors by default
    tool_bus.execute_tool = AsyncMock()  # But execute_tool IS async
    return tool_bus


@pytest.fixture
def mock_memory_bus():
    """Mock memory bus."""
    return AsyncMock()


@pytest.fixture
def orchestrator(mock_time_service, mock_dsar_automation, mock_consent_service, mock_tool_bus, mock_memory_bus):
    """Create orchestrator with all mocked dependencies."""
    return DSAROrchestrator(
        time_service=mock_time_service,
        dsar_automation=mock_dsar_automation,
        consent_service=mock_consent_service,
        tool_bus=mock_tool_bus,
        memory_bus=mock_memory_bus,
    )


class TestDSAROrchestratorConsentIntegration:
    """Test ConsentService integration in DSAROrchestrator."""

    @pytest.mark.asyncio
    async def test_deletion_request_calls_revoke_consent(
        self, orchestrator, mock_consent_service, mock_dsar_automation
    ):
        """Test that deletion request properly calls revoke_consent."""
        with patch(
            "ciris_engine.logic.utils.identity_resolution.resolve_user_identity"
        ) as mock_resolve:
            mock_resolve.return_value = None  # identity_node is Optional

            result = await orchestrator.handle_deletion_request_multi_source(
                user_identifier="test@example.com", request_id="REQ-DELETE-001"
            )

            # Verify revoke_consent was called
            mock_consent_service.revoke_consent.assert_called_once()
            call_args = mock_consent_service.revoke_consent.call_args
            assert call_args.kwargs["user_id"] == "test@example.com"
            assert "GDPR Article 17" in call_args.kwargs["reason"]

            # Verify get_deletion_status was called after revoke
            mock_dsar_automation.get_deletion_status.assert_called_once_with("test@example.com", "REQ-DELETE-001")

            # Verify result contains real deletion status
            assert isinstance(result, MultiSourceDSARDeletionResult)
            assert result.ciris_deletion.current_phase == "identity_severed"
            assert result.ciris_deletion.completion_percentage == 5.0

    @pytest.mark.asyncio
    async def test_deletion_request_no_fake_data(self, orchestrator, mock_consent_service, mock_dsar_automation):
        """Test that deletion request never creates fake placeholder status."""
        with patch(
            "ciris_engine.logic.utils.identity_resolution.resolve_user_identity"
        ) as mock_resolve:
            mock_resolve.return_value = None  # identity_node is Optional

            result = await orchestrator.handle_deletion_request_multi_source(
                user_identifier="test@example.com", request_id="REQ-DELETE-001"
            )

            # Verify we got real status from DSAR automation
            assert result.ciris_deletion.ticket_id == "REQ-DELETE-001"
            assert result.ciris_deletion.current_phase != "pending"  # Not fake placeholder
            assert result.ciris_deletion.completion_percentage > 0  # Real progress

    @pytest.mark.asyncio
    async def test_deletion_request_creates_fallback_when_no_status(
        self, orchestrator, mock_consent_service, mock_dsar_automation
    ):
        """Test fallback status creation when get_deletion_status returns None."""
        # Make get_deletion_status return None
        mock_dsar_automation.get_deletion_status.return_value = None

        with patch(
            "ciris_engine.logic.utils.identity_resolution.resolve_user_identity"
        ) as mock_resolve:
            mock_resolve.return_value = None  # identity_node is Optional

            result = await orchestrator.handle_deletion_request_multi_source(
                user_identifier="test@example.com", request_id="REQ-DELETE-001"
            )

            # Verify revoke_consent was still called
            mock_consent_service.revoke_consent.assert_called_once()

            # Verify fallback status was created
            assert result.ciris_deletion.current_phase == "identity_severed"
            assert result.ciris_deletion.completion_percentage == 0.0

    @pytest.mark.asyncio
    async def test_deletion_request_with_sql_connectors(self, orchestrator, mock_consent_service, mock_tool_bus):
        """Test deletion request with SQL connectors."""
        # Mock SQL connector discovery
        mock_service = MagicMock()
        mock_service.get_service_metadata.return_value = {"connector_id": "sql_postgres_test", "service_name": "test"}
        mock_tool_bus.get_tools_by_metadata.return_value = [mock_service]  # Not async

        # Mock SQL deletion AND verification (two separate tool calls)
        async def mock_execute_tool(tool_name, parameters, **kwargs):
            result = AsyncMock()
            if tool_name == "sql_delete_user":
                result.data = {"success": True, "tables_affected": ["users"], "total_records_deleted": 5}
                result.success = True
            elif tool_name == "sql_verify_deletion":
                result.data = {"zero_data_confirmed": True}
                result.success = True
            else:
                result.success = False
            return result

        mock_tool_bus.execute_tool = AsyncMock(side_effect=mock_execute_tool)

        with patch(
            "ciris_engine.logic.utils.identity_resolution.resolve_user_identity"
        ) as mock_resolve:
            mock_resolve.return_value = None  # identity_node is Optional

            result = await orchestrator.handle_deletion_request_multi_source(
                user_identifier="test@example.com", request_id="REQ-DELETE-001"
            )

            # Verify consent was revoked
            mock_consent_service.revoke_consent.assert_called_once()

            # Verify external deletions were recorded
            assert len(result.external_deletions) == 1
            assert result.external_deletions[0].source_id == "sql_postgres_test"
            assert result.external_deletions[0].verification_passed is True

            # Verify total sources count
            assert result.total_sources == 2  # CIRIS + 1 SQL connector

    @pytest.mark.asyncio
    async def test_deletion_request_handles_revoke_consent_failure(
        self, orchestrator, mock_consent_service, mock_dsar_automation
    ):
        """Test that deletion request raises error when revoke_consent fails."""
        # Make revoke_consent fail
        mock_consent_service.revoke_consent.side_effect = Exception("Consent revocation failed")

        with patch(
            "ciris_engine.logic.utils.identity_resolution.resolve_user_identity"
        ) as mock_resolve:
            mock_resolve.return_value = None  # identity_node is Optional

            # Verify HTTPException is raised
            with pytest.raises(Exception) as exc_info:
                await orchestrator.handle_deletion_request_multi_source(
                    user_identifier="test@example.com", request_id="REQ-DELETE-001"
                )

            # Verify error contains helpful message
            assert "Failed to initiate CIRIS deletion" in str(exc_info.value)


class TestGetDeletionStatusMultiSource:
    """Test get_deletion_status_multi_source implementation."""

    @pytest.mark.asyncio
    async def test_get_deletion_status_returns_current_state(
        self, orchestrator, mock_dsar_automation, mock_tool_bus
    ):
        """Test that get_deletion_status returns current deletion state."""
        # Mock no SQL connectors
        mock_tool_bus.get_tools_by_metadata.return_value = []

        with patch(
            "ciris_engine.logic.utils.identity_resolution.resolve_user_identity"
        ) as mock_resolve:
            mock_resolve.return_value = None  # identity_node is Optional

            result = await orchestrator.get_deletion_status_multi_source(
                user_identifier="test@example.com", request_id="REQ-DELETE-001"
            )

            # Verify get_deletion_status was called
            mock_dsar_automation.get_deletion_status.assert_called_once_with("test@example.com", "REQ-DELETE-001")

            # Verify result structure
            assert isinstance(result, MultiSourceDSARDeletionResult)
            assert result.ciris_deletion.completion_percentage == 5.0
            assert result.total_sources == 1  # CIRIS only

    @pytest.mark.asyncio
    async def test_get_deletion_status_verifies_sql_deletions(self, orchestrator, mock_tool_bus):
        """Test that get_deletion_status verifies SQL deletions."""
        # Mock SQL connector
        mock_service = MagicMock()
        mock_service.get_service_metadata.return_value = {"connector_id": "sql_postgres_test"}
        mock_tool_bus.get_tools_by_metadata.return_value = [mock_service]  # Not async

        # Mock verification result
        mock_verification_result = AsyncMock()
        mock_verification_result.data = {"zero_data_confirmed": True}
        mock_verification_result.success = True
        mock_tool_bus.execute_tool = AsyncMock(return_value=mock_verification_result)

        with patch(
            "ciris_engine.logic.utils.identity_resolution.resolve_user_identity"
        ) as mock_resolve:
            mock_resolve.return_value = None  # identity_node is Optional

            result = await orchestrator.get_deletion_status_multi_source(
                user_identifier="test@example.com", request_id="REQ-DELETE-001"
            )

            # Verify verification was called
            assert mock_tool_bus.execute_tool.called

            # Verify external deletions
            assert len(result.external_deletions) == 1
            assert result.external_deletions[0].verification_passed is True
            assert result.sources_completed == 1
            assert result.sources_failed == 0

    @pytest.mark.asyncio
    async def test_get_deletion_status_handles_failed_verification(self, orchestrator, mock_tool_bus):
        """Test get_deletion_status when SQL verification fails."""
        # Mock SQL connector
        mock_service = MagicMock()
        mock_service.get_service_metadata.return_value = {"connector_id": "sql_postgres_test"}
        mock_tool_bus.get_tools_by_metadata.return_value = [mock_service]  # Not async

        # Mock verification failure
        mock_verification_result = AsyncMock()
        mock_verification_result.data = {"zero_data_confirmed": False}
        mock_verification_result.success = True
        mock_tool_bus.execute_tool = AsyncMock(return_value=mock_verification_result)

        with patch(
            "ciris_engine.logic.utils.identity_resolution.resolve_user_identity"
        ) as mock_resolve:
            mock_resolve.return_value = None  # identity_node is Optional

            result = await orchestrator.get_deletion_status_multi_source(
                user_identifier="test@example.com", request_id="REQ-DELETE-001"
            )

            # Verify failure recorded
            assert len(result.external_deletions) == 1
            assert result.external_deletions[0].verification_passed is False
            assert result.sources_completed == 0
            assert result.sources_failed == 1
            assert "data still present" in result.external_deletions[0].errors[0]

    @pytest.mark.asyncio
    async def test_get_deletion_status_creates_fallback_when_none(
        self, orchestrator, mock_dsar_automation, mock_tool_bus
    ):
        """Test fallback creation when DSAR automation returns None."""
        # Make get_deletion_status return None
        mock_dsar_automation.get_deletion_status.return_value = None
        mock_tool_bus.get_tools_by_metadata.return_value = []

        with patch(
            "ciris_engine.logic.utils.identity_resolution.resolve_user_identity"
        ) as mock_resolve:
            mock_resolve.return_value = None  # identity_node is Optional

            result = await orchestrator.get_deletion_status_multi_source(
                user_identifier="test@example.com", request_id="REQ-DELETE-001"
            )

            # Verify fallback was created
            assert result.ciris_deletion.current_phase == "unknown"
            assert result.ciris_deletion.completion_percentage == 0.0


class TestOrchestratorInitialization:
    """Test orchestrator initialization with ConsentService."""

    def test_orchestrator_requires_consent_service(
        self, mock_time_service, mock_dsar_automation, mock_consent_service, mock_tool_bus, mock_memory_bus
    ):
        """Test that orchestrator requires ConsentService in constructor."""
        orchestrator = DSAROrchestrator(
            time_service=mock_time_service,
            dsar_automation=mock_dsar_automation,
            consent_service=mock_consent_service,
            tool_bus=mock_tool_bus,
            memory_bus=mock_memory_bus,
        )

        # Verify consent service is stored
        assert orchestrator._consent_service is mock_consent_service
        assert orchestrator._dsar_automation is mock_dsar_automation
        assert orchestrator._tool_bus is mock_tool_bus
        assert orchestrator._memory_bus is mock_memory_bus
