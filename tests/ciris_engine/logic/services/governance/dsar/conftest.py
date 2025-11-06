"""Shared fixtures for DSAR orchestrator tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus
from ciris_engine.schemas.consent.core import (
    ConsentCategory,
    ConsentDecayStatus,
    ConsentImpactReport,
    ConsentStatus,
    ConsentStream,
    DSARAccessPackage,
    DSARDeletionStatus,
    DSARExportFormat,
    DSARExportPackage,
)
from ciris_engine.schemas.identity import UserIdentifier, UserIdentityNode


@pytest.fixture
def sample_consent_status():
    """Sample ConsentStatus for testing."""
    return ConsentStatus(
        user_id="test@example.com",
        stream=ConsentStream.PARTNERED,
        categories=[ConsentCategory.INTERACTION],
        granted_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        expires_at=None,
        last_modified=datetime(2025, 1, 10, tzinfo=timezone.utc),
        impact_score=5.0,
        attribution_count=3,
    )


@pytest.fixture
def sample_consent_impact_report():
    """Sample ConsentImpactReport for testing."""
    return ConsentImpactReport(
        user_id="test@example.com",
        total_interactions=10,
        patterns_contributed=5,
        users_helped=2,
        categories_active=[ConsentCategory.INTERACTION],
        impact_score=5.0,
        example_contributions=["Helped with code review", "Shared debugging tip"],
    )


@pytest.fixture
def sample_dsar_access_package(sample_consent_status, sample_consent_impact_report):
    """Sample DSARAccessPackage for testing."""
    return DSARAccessPackage(
        user_id="test@example.com",
        request_id="TEST-REQ-001",
        generated_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
        consent_status=sample_consent_status,
        consent_history=[],
        interaction_summary={"discord": {"count": 5, "last": "2025-01-10"}},
        contribution_metrics=sample_consent_impact_report,
        data_categories=["interactions", "consent"],
        retention_periods={"interactions": "14 days", "consent": "perpetual"},
        processing_purposes=["personalization", "improvement"],
    )


@pytest.fixture
def sample_dsar_export_package():
    """Sample DSARExportPackage for testing."""
    return DSARExportPackage(
        user_id="test@example.com",
        request_id="TEST-REQ-001",
        export_format=DSARExportFormat.JSON,
        generated_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
        file_path=None,
        file_size_bytes=1024,
        record_counts={"interactions": 5, "consent": 1},
        checksum="abc123",
        includes_readme=True,
    )


@pytest.fixture
def sample_decay_status():
    """Sample ConsentDecayStatus for testing."""
    return ConsentDecayStatus(
        user_id="test@example.com",
        decay_started=datetime(2025, 1, 15, tzinfo=timezone.utc),
        identity_severed=True,
        patterns_anonymized=False,
        decay_complete_at=datetime(2025, 4, 15, tzinfo=timezone.utc),
        safety_patterns_retained=0,
    )


@pytest.fixture
def sample_dsar_deletion_status():
    """Sample DSARDeletionStatus for testing."""
    return DSARDeletionStatus(
        ticket_id="TEST-REQ-001",
        user_id="test@example.com",
        decay_started=datetime(2025, 1, 15, tzinfo=timezone.utc),
        current_phase="identity_severed",
        completion_percentage=10.0,
        estimated_completion=datetime(2025, 4, 15, tzinfo=timezone.utc),
        milestones_completed=["identity_severed"],
        next_milestone="patterns_anonymizing",
        safety_patterns_retained=0,
    )


@pytest.fixture
def sample_identity_node():
    """Sample UserIdentityNode for testing."""
    return UserIdentityNode(
        primary_id="test@example.com",
        identifiers=[
            UserIdentifier(
                identifier_type="email",
                identifier_value="test@example.com",
                confidence=1.0,
                source="manual",
                verified=True,
            )
        ],
        total_identifiers=1,
        last_updated="2025-01-15T12:00:00Z",
    )


@pytest.fixture
def mock_time_service():
    """Mock time service."""
    service = MagicMock()
    service.now.return_value = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    return service


@pytest.fixture
def mock_dsar_automation(sample_dsar_access_package, sample_dsar_export_package, sample_dsar_deletion_status):
    """Mock DSAR automation service with proper return values."""
    service = AsyncMock()
    service.handle_access_request.return_value = sample_dsar_access_package
    service.handle_export_request.return_value = sample_dsar_export_package
    service.handle_deletion_request.return_value = sample_dsar_deletion_status
    service.get_deletion_status.return_value = sample_dsar_deletion_status  # Added for new ConsentService integration
    service.handle_correction_request.return_value = {
        "corrections_applied": 1,
        "fields_updated": ["email"],
    }
    return service


@pytest.fixture
def mock_tool_bus():
    """Mock tool bus with SQL connector responses."""
    bus = AsyncMock()

    # Mock SQL connector discovery (async method)
    async def mock_get_tools(**kwargs):
        return [
            ("sql_connector_1", {"source_type": "sql", "connector_id": "postgres_db"}),
        ]

    bus.get_tools_by_metadata = mock_get_tools

    # Mock SQL tool execution
    bus.execute_tool.return_value = ToolExecutionResult(
        tool_name="sql_export_user",
        status=ToolExecutionStatus.COMPLETED,
        success=True,
        data={
            "success": True,
            "export_data": {
                "users": [{"id": 1, "email": "test@example.com", "name": "Test User"}],
            },
            "tables_queried": ["users"],
            "total_records": 1,
        },
        error=None,
        correlation_id="test-correlation-id",
    )

    return bus


@pytest.fixture
def mock_memory_bus():
    """Mock memory bus."""
    return AsyncMock()


@pytest.fixture
def mock_consent_service(sample_decay_status):
    """Mock consent service with decay status."""
    service = AsyncMock()
    service.revoke_consent.return_value = sample_decay_status
    return service


@pytest.fixture
def orchestrator(mock_time_service, mock_dsar_automation, mock_consent_service, mock_tool_bus, mock_memory_bus):
    """Create DSAR orchestrator instance with all dependencies mocked."""
    from ciris_engine.logic.services.governance.dsar.orchestrator import DSAROrchestrator

    return DSAROrchestrator(
        time_service=mock_time_service,
        dsar_automation=mock_dsar_automation,
        consent_service=mock_consent_service,
        tool_bus=mock_tool_bus,
        memory_bus=mock_memory_bus,
    )
