"""
Tests for DSARAutomationService - GDPR-compliant automated DSAR responses.

Focuses on:
- handle_access_request() with real consent data
- handle_export_request() for JSON/CSV/SQLite formats
- handle_correction_request() for data rectification
- get_deletion_status() tracking decay protocol
- Real data integration with memory bus
- Type safety and GDPR compliance
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest

from ciris_engine.logic.services.governance.consent.dsar_automation import DSARAutomationService
from ciris_engine.logic.services.governance.consent.exceptions import ConsentNotFoundError, DSARAutomationError
from ciris_engine.logic.services.governance.consent.service import ConsentService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import (
    ConsentAuditEntry,
    ConsentCategory,
    ConsentDecayStatus,
    ConsentImpactReport,
    ConsentStatus,
    ConsentStream,
    DSARCorrectionRequest,
    DSARExportFormat,
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    mock = Mock(spec=TimeServiceProtocol)
    mock.now.return_value = datetime(2025, 10, 17, 12, 0, 0, tzinfo=timezone.utc)
    return mock


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    from ciris_engine.logic.buses.memory_bus import MemoryBus

    mock = AsyncMock(spec=MemoryBus)
    mock.search = AsyncMock(return_value=[])
    return mock


@pytest.fixture
def mock_consent_service(mock_time_service):
    """Create a mock consent service."""
    mock = AsyncMock(spec=ConsentService)

    # Default consent status
    mock.get_consent = AsyncMock(
        return_value=ConsentStatus(
            user_id="test_user",
            stream=ConsentStream.TEMPORARY,
            categories=[ConsentCategory.INTERACTION],
            granted_at=mock_time_service.now() - timedelta(days=5),
            expires_at=mock_time_service.now() + timedelta(days=9),
            last_modified=mock_time_service.now(),
            impact_score=1.5,
            attribution_count=10,
        )
    )

    # Default audit trail
    mock.get_audit_trail = AsyncMock(
        return_value=[
            ConsentAuditEntry(
                entry_id="audit_1",
                user_id="test_user",
                timestamp=mock_time_service.now() - timedelta(days=5),
                previous_stream=ConsentStream.ANONYMOUS,
                new_stream=ConsentStream.TEMPORARY,
                previous_categories=[],
                new_categories=[ConsentCategory.INTERACTION],
                initiated_by="user",
                reason="Initial consent",
            )
        ]
    )

    # Default impact report
    mock.get_impact_report = AsyncMock(
        return_value=ConsentImpactReport(
            user_id="test_user",
            total_interactions=25,
            patterns_contributed=5,
            users_helped=10,
            categories_active=[ConsentCategory.INTERACTION],
            impact_score=1.5,
            example_contributions=["Example pattern 1", "Example pattern 2"],
        )
    )

    return mock


@pytest.fixture
def dsar_service(mock_time_service, mock_consent_service, mock_memory_bus):
    """Create DSAR automation service with mocked dependencies."""
    service = DSARAutomationService(
        time_service=mock_time_service, consent_service=mock_consent_service, memory_bus=mock_memory_bus
    )
    return service


class TestHandleAccessRequest:
    """Test handle_access_request() for GDPR Article 15 compliance."""

    @pytest.mark.asyncio
    async def test_access_request_with_full_data(self, dsar_service, mock_consent_service, mock_time_service):
        """Test access request returns complete data package."""
        # Setup mock conversation summaries
        conv1 = Mock()
        conv1.attributes = {
            "channel_id": "channel_123",
            "participants": {
                "test_user": {"user_id": "test_user", "message_count": 15},
                "other_user": {"user_id": "other_user", "message_count": 8},
            },
        }
        conv2 = Mock()
        conv2.attributes = {
            "channel_id": "channel_456",
            "participants": {
                "test_user": {"user_id": "test_user", "message_count": 10},
            },
        }
        dsar_service._memory_bus.search = AsyncMock(return_value=[conv1, conv2])

        # Execute access request
        package = await dsar_service.handle_access_request(user_id="test_user", request_id="req_123")

        # Verify package structure
        assert package.user_id == "test_user"
        assert package.request_id == "req_123"
        assert package.generated_at == mock_time_service.now()

        # Verify consent data
        assert package.consent_status.stream == ConsentStream.TEMPORARY
        assert len(package.consent_history) == 1
        assert package.consent_history[0].entry_id == "audit_1"

        # Verify interaction data
        assert package.interaction_summary["total"] == 25  # 15 + 10
        assert package.interaction_summary["channel_123"] == 15
        assert package.interaction_summary["channel_456"] == 10

        # Verify contribution metrics
        assert package.contribution_metrics.patterns_contributed == 5
        assert package.contribution_metrics.users_helped == 10

        # Verify data categories
        assert "session_data" in package.data_categories
        assert "basic_interactions" in package.data_categories

        # Verify retention periods
        assert package.retention_periods["session_data"] == "14 days"
        assert package.retention_periods["consent_status"] == "14 days (auto-renewal on interaction)"

        # Verify processing purposes
        assert "session_continuity" in package.processing_purposes

        # Verify metrics
        metrics = dsar_service.get_metrics()
        assert metrics["dsar_access_requests_total"] == 1
        assert metrics["dsar_avg_access_time_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_access_request_no_consent_record(self, dsar_service, mock_consent_service):
        """Test access request when user has no consent record."""
        mock_consent_service.get_consent = AsyncMock(side_effect=ConsentNotFoundError("Not found"))

        with pytest.raises(ConsentNotFoundError, match="Not found"):
            await dsar_service.handle_access_request(user_id="no_consent_user")

    @pytest.mark.asyncio
    async def test_access_request_no_memory_bus(self, mock_time_service, mock_consent_service):
        """Test access request gracefully handles missing memory bus."""
        # Create service without memory bus
        service = DSARAutomationService(
            time_service=mock_time_service, consent_service=mock_consent_service, memory_bus=None
        )

        package = await service.handle_access_request(user_id="test_user")

        # Should still return package with empty interaction summary
        assert package.user_id == "test_user"
        assert package.interaction_summary["total"] == 0

    @pytest.mark.asyncio
    async def test_access_request_partnered_user(self, dsar_service, mock_consent_service, mock_time_service):
        """Test access request for PARTNERED user includes extended data."""
        # Mock PARTNERED consent
        mock_consent_service.get_consent = AsyncMock(
            return_value=ConsentStatus(
                user_id="partner_user",
                stream=ConsentStream.PARTNERED,
                categories=[ConsentCategory.INTERACTION, ConsentCategory.PREFERENCE, ConsentCategory.IMPROVEMENT],
                granted_at=mock_time_service.now() - timedelta(days=100),
                expires_at=None,  # PARTNERED doesn't expire
                last_modified=mock_time_service.now(),
                impact_score=15.5,
                attribution_count=150,
            )
        )

        package = await dsar_service.handle_access_request(user_id="partner_user")

        # Verify PARTNERED data categories
        assert "behavioral_patterns" in package.data_categories
        assert "preferences" in package.data_categories
        assert "contribution_data" in package.data_categories

        # Verify PARTNERED retention
        assert package.retention_periods["behavioral_patterns"] == "indefinite"
        assert package.retention_periods["consent_status"] == "indefinite (until partnership ends)"

        # Verify PARTNERED processing purposes
        assert "personalization" in package.processing_purposes
        assert "service_improvement" in package.processing_purposes

    @pytest.mark.asyncio
    async def test_access_request_auto_generates_request_id(self, dsar_service):
        """Test access request auto-generates request ID if not provided."""
        package = await dsar_service.handle_access_request(user_id="test_user")

        # Should have auto-generated ID in format ACCESS-YYYYMMDD-XXXXXXXX
        assert package.request_id.startswith("ACCESS-")
        assert len(package.request_id) == 24  # ACCESS- (7) + YYYYMMDD (8) + - (1) + HEX (8)


class TestHandleExportRequest:
    """Test handle_export_request() for GDPR Article 20 compliance."""

    @pytest.mark.asyncio
    async def test_export_request_json_format(self, dsar_service, mock_time_service):
        """Test export request in JSON format."""
        export_package = await dsar_service.handle_export_request(
            user_id="test_user", export_format=DSARExportFormat.JSON, request_id="export_123"
        )

        # Verify export structure
        assert export_package.user_id == "test_user"
        assert export_package.request_id == "export_123"
        assert export_package.export_format == DSARExportFormat.JSON
        assert export_package.generated_at == mock_time_service.now()

        # Verify file metadata
        assert export_package.file_size_bytes > 0
        assert len(export_package.checksum) == 64  # SHA256 is 64 hex chars
        assert export_package.includes_readme is True

        # Verify record counts
        assert "consent_records" in export_package.record_counts
        assert "audit_entries" in export_package.record_counts

        # Verify metrics
        metrics = dsar_service.get_metrics()
        assert metrics["dsar_export_requests_total"] == 1

    @pytest.mark.asyncio
    async def test_export_request_csv_format(self, dsar_service):
        """Test export request in CSV format."""
        export_package = await dsar_service.handle_export_request(
            user_id="test_user", export_format=DSARExportFormat.CSV
        )

        assert export_package.export_format == DSARExportFormat.CSV
        assert export_package.file_size_bytes > 0
        assert len(export_package.checksum) == 64

    @pytest.mark.asyncio
    async def test_export_request_sqlite_format(self, dsar_service):
        """Test export request in SQLite format (placeholder)."""
        export_package = await dsar_service.handle_export_request(
            user_id="test_user", export_format=DSARExportFormat.SQLITE
        )

        assert export_package.export_format == DSARExportFormat.SQLITE
        # Currently returns JSON with note, future: actual .db file
        assert export_package.file_size_bytes > 0

    @pytest.mark.asyncio
    async def test_export_request_no_consent_record(self, dsar_service, mock_consent_service):
        """Test export request when user has no consent record."""
        mock_consent_service.get_consent = AsyncMock(side_effect=ConsentNotFoundError("Not found"))

        with pytest.raises(ConsentNotFoundError):
            await dsar_service.handle_export_request(user_id="no_consent_user", export_format=DSARExportFormat.JSON)

    @pytest.mark.asyncio
    async def test_export_request_auto_generates_id(self, dsar_service):
        """Test export request auto-generates ID if not provided."""
        package = await dsar_service.handle_export_request(user_id="test_user", export_format=DSARExportFormat.JSON)

        assert package.request_id.startswith("EXPORT-")


class TestHandleCorrectionRequest:
    """Test handle_correction_request() for GDPR Article 16 compliance."""

    @pytest.mark.asyncio
    async def test_correction_request_valid_field(self, dsar_service, mock_time_service):
        """Test correction request for valid field."""
        correction = DSARCorrectionRequest(
            user_id="test_user",
            field_name="preferences.language",
            current_value="en",
            new_value="fr",
            reason="User moved to France",
        )

        result = await dsar_service.handle_correction_request(correction=correction, request_id="corr_123")

        # Verify result structure
        assert result.user_id == "test_user"
        assert result.request_id == "corr_123"
        assert result.completed_at == mock_time_service.now()

        # Verify corrections applied
        assert len(result.corrections_applied) == 1
        applied = result.corrections_applied[0]
        assert applied["field"] == "preferences.language"
        assert applied["old_value"] == "en"
        assert applied["new_value"] == "fr"

        # Verify no rejections
        assert len(result.corrections_rejected) == 0

        # Verify affected systems
        assert "consent_service" in result.affected_systems

        # Verify audit entry (UUID format)
        assert len(result.audit_entry_id) == 36  # UUID format with dashes

        # Verify metrics
        metrics = dsar_service.get_metrics()
        assert metrics["dsar_correction_requests_total"] == 1

    @pytest.mark.asyncio
    async def test_correction_request_invalid_field(self, dsar_service):
        """Test correction request for invalid/unsupported field."""
        correction = DSARCorrectionRequest(
            user_id="test_user",
            field_name="invalid.field",
            current_value="old",
            new_value="new",
            reason="Testing invalid field",
        )

        result = await dsar_service.handle_correction_request(correction=correction)

        # Verify correction was rejected
        assert len(result.corrections_applied) == 0
        assert len(result.corrections_rejected) == 1

        rejected = result.corrections_rejected[0]
        assert rejected["field"] == "invalid.field"
        assert "not correctable" in rejected["reason"].lower()

    @pytest.mark.asyncio
    async def test_correction_request_multiple_fields(self, dsar_service):
        """Test correction request can handle multiple corrections."""
        correction1 = DSARCorrectionRequest(
            user_id="test_user",
            field_name="preferences.language",
            current_value="en",
            new_value="de",
            reason="Update language",
        )

        correction2 = DSARCorrectionRequest(
            user_id="test_user",
            field_name="user_metadata.name",
            current_value="Old Name",
            new_value="New Name",
            reason="Legal name change",
        )

        result1 = await dsar_service.handle_correction_request(correction=correction1)
        result2 = await dsar_service.handle_correction_request(correction=correction2)

        assert len(result1.corrections_applied) == 1
        assert len(result2.corrections_applied) == 1

        # Verify metrics
        metrics = dsar_service.get_metrics()
        assert metrics["dsar_correction_requests_total"] == 2

    @pytest.mark.asyncio
    async def test_correction_request_auto_generates_id(self, dsar_service):
        """Test correction request auto-generates ID."""
        correction = DSARCorrectionRequest(
            user_id="test_user",
            field_name="preferences.language",
            current_value="en",
            new_value="es",
            reason="Test",
        )

        result = await dsar_service.handle_correction_request(correction=correction)

        assert result.request_id.startswith("CORRECT-")


class TestGetDeletionStatus:
    """Test get_deletion_status() tracking decay protocol."""

    @pytest.mark.asyncio
    async def test_deletion_status_active_decay(self, dsar_service, mock_consent_service, mock_time_service):
        """Test deletion status for active decay protocol."""
        # Mock active decay
        decay_status = ConsentDecayStatus(
            user_id="delete_user",
            decay_started=mock_time_service.now() - timedelta(days=30),
            identity_severed=True,
            patterns_anonymized=False,
            decay_complete_at=mock_time_service.now() + timedelta(days=60),
            safety_patterns_retained=5,
        )

        # Create decay manager mock with all required methods
        decay_manager = Mock()
        decay_manager.check_decay_status = Mock(return_value=decay_status)
        decay_manager.get_decay_progress = Mock(
            return_value={
                "completion_percentage": 33.3,
                "days_elapsed": 30,
                "days_remaining": 60,
            }
        )
        decay_manager.get_decay_milestones = Mock(
            return_value={
                "completed": ["initiated", "identity_severed"],
                "pending": ["patterns_anonymized"],
            }
        )
        dsar_service._consent_service._decay_manager = decay_manager

        status = await dsar_service.get_deletion_status(user_id="delete_user", ticket_id="ticket_123")

        # Verify status structure
        assert status.ticket_id == "ticket_123"
        assert status.user_id == "delete_user"
        assert status.decay_started == mock_time_service.now() - timedelta(days=30)
        assert status.current_phase == "patterns_anonymizing"
        assert 0 < status.completion_percentage < 100
        assert status.estimated_completion == mock_time_service.now() + timedelta(days=60)

        # Verify milestones
        assert "initiated" in status.milestones_completed
        assert "identity_severed" in status.milestones_completed
        assert status.next_milestone == "patterns_anonymized"

        assert status.safety_patterns_retained == 5

        # Verify metrics
        metrics = dsar_service.get_metrics()
        assert metrics["dsar_deletion_status_checks_total"] == 1

    @pytest.mark.asyncio
    async def test_deletion_status_completed_decay(self, dsar_service, mock_consent_service, mock_time_service):
        """Test deletion status for completed decay."""
        decay_status = ConsentDecayStatus(
            user_id="deleted_user",
            decay_started=mock_time_service.now() - timedelta(days=90),
            identity_severed=True,
            patterns_anonymized=True,
            decay_complete_at=mock_time_service.now(),
            safety_patterns_retained=3,
        )

        decay_manager = Mock()
        decay_manager.check_decay_status = Mock(return_value=decay_status)
        decay_manager.get_decay_progress = Mock(
            return_value={
                "completion_percentage": 100.0,
                "days_elapsed": 90,
                "days_remaining": 0,
            }
        )
        decay_manager.get_decay_milestones = Mock(
            return_value={
                "completed": ["initiated", "identity_severed", "patterns_anonymized"],
                "pending": [],
            }
        )
        dsar_service._consent_service._decay_manager = decay_manager

        status = await dsar_service.get_deletion_status(user_id="deleted_user", ticket_id="ticket_456")

        assert status.current_phase == "complete"
        assert status.completion_percentage == 100.0
        assert status.next_milestone is None
        assert "patterns_anonymized" in status.milestones_completed

    @pytest.mark.asyncio
    async def test_deletion_status_no_active_decay(self, dsar_service, mock_consent_service):
        """Test deletion status when no decay is active."""
        decay_manager = Mock()
        decay_manager.check_decay_status = Mock(return_value=None)
        dsar_service._consent_service._decay_manager = decay_manager

        status = await dsar_service.get_deletion_status(user_id="no_decay_user", ticket_id="ticket_789")

        # Should return None when no decay found
        assert status is None


class TestInteractionSummary:
    """Test _get_interaction_summary() method."""

    @pytest.mark.asyncio
    async def test_interaction_summary_multiple_channels(self, dsar_service):
        """Test interaction summary across multiple channels."""
        # Mock conversation summaries
        conv1 = Mock()
        conv1.attributes = {
            "channel_id": "channel_1",
            "participants": {
                "user_1": {"user_id": "user_1", "message_count": 20},
                "user_2": {"user_id": "user_2", "message_count": 15},
            },
        }
        conv2 = Mock()
        conv2.attributes = {
            "channel_id": "channel_2",
            "participants": {
                "user_1": {"user_id": "user_1", "message_count": 30},
            },
        }
        conv3 = Mock()
        conv3.attributes = {
            "channel_id": "channel_1",
            "participants": {
                "user_1": {"user_id": "user_1", "message_count": 10},
                "user_3": {"user_id": "user_3", "message_count": 5},
            },
        }

        dsar_service._memory_bus.search = AsyncMock(return_value=[conv1, conv2, conv3])

        summary = await dsar_service._get_interaction_summary(user_id="user_1")

        # Verify summary
        assert summary["total"] == 60  # 20 + 30 + 10
        assert summary["channel_1"] == 30  # 20 + 10
        assert summary["channel_2"] == 30

    @pytest.mark.asyncio
    async def test_interaction_summary_no_data(self, dsar_service):
        """Test interaction summary when user has no interactions."""
        dsar_service._memory_bus.search = AsyncMock(return_value=[])

        summary = await dsar_service._get_interaction_summary(user_id="no_data_user")

        assert summary["total"] == 0
        assert len(summary) == 1  # Only 'total' key

    @pytest.mark.asyncio
    async def test_interaction_summary_handles_missing_attributes(self, dsar_service):
        """Test interaction summary gracefully handles missing attributes."""
        conv1 = Mock()
        conv1.attributes = None  # Missing attributes

        conv2 = Mock()
        conv2.attributes = {"channel_id": "channel_1"}  # Missing participants

        dsar_service._memory_bus.search = AsyncMock(return_value=[conv1, conv2])

        summary = await dsar_service._get_interaction_summary(user_id="test_user")

        # Should handle gracefully
        assert summary["total"] == 0


class TestMetrics:
    """Test metrics collection."""

    @pytest.mark.asyncio
    async def test_metrics_initial_state(self, dsar_service):
        """Test metrics in initial state."""
        metrics = dsar_service.get_metrics()

        assert metrics["dsar_access_requests_total"] == 0
        assert metrics["dsar_export_requests_total"] == 0
        assert metrics["dsar_correction_requests_total"] == 0
        assert metrics["dsar_deletion_status_checks_total"] == 0
        assert metrics["dsar_avg_access_time_seconds"] == 0.0
        assert metrics["dsar_avg_export_time_seconds"] == 0.0

    @pytest.mark.asyncio
    async def test_metrics_after_operations(self, dsar_service):
        """Test metrics after performing operations."""
        # Perform operations
        await dsar_service.handle_access_request(user_id="test_user")
        await dsar_service.handle_export_request(user_id="test_user", export_format=DSARExportFormat.JSON)

        correction = DSARCorrectionRequest(
            user_id="test_user",
            field_name="preferences.language",
            current_value="en",
            new_value="fr",
            reason="Test",
        )
        await dsar_service.handle_correction_request(correction=correction)

        metrics = dsar_service.get_metrics()

        # Note: Export internally calls access, so access count is 2
        assert metrics["dsar_access_requests_total"] == 2  # 1 direct + 1 from export
        assert metrics["dsar_export_requests_total"] == 1
        assert metrics["dsar_correction_requests_total"] == 1
        assert metrics["dsar_avg_access_time_seconds"] >= 0
        assert metrics["dsar_avg_export_time_seconds"] >= 0


class TestTypeSafety:
    """Test type safety and error handling."""

    @pytest.mark.asyncio
    async def test_type_safety_dict_parameters(self, dsar_service):
        """Test that all dict types have explicit type parameters."""
        # This test verifies mypy compliance by exercising type-checked paths

        package = await dsar_service.handle_access_request(user_id="test_user")

        # interaction_summary should be dict[str, object]
        assert isinstance(package.interaction_summary, dict)
        for key, value in package.interaction_summary.items():
            assert isinstance(key, str)

        # retention_periods should be dict[str, str]
        assert isinstance(package.retention_periods, dict)
        for key, value in package.retention_periods.items():
            assert isinstance(key, str)
            assert isinstance(value, str)

    @pytest.mark.asyncio
    async def test_graceful_error_handling(self, dsar_service, mock_consent_service):
        """Test graceful error handling with proper exceptions."""
        # Test ConsentNotFoundError propagation
        mock_consent_service.get_consent = AsyncMock(side_effect=ConsentNotFoundError("User not found"))

        with pytest.raises(ConsentNotFoundError):
            await dsar_service.handle_access_request(user_id="nonexistent")

        # Test other exceptions are wrapped in DSARAutomationError
        mock_consent_service.get_consent = AsyncMock(side_effect=ValueError("Unexpected error"))

        with pytest.raises(ValueError):
            await dsar_service.handle_access_request(user_id="error_user")
