
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from typing import List

from ciris_engine.logic.services.governance.dsar.orchestrator import DSAROrchestrator
from ciris_engine.schemas.consent.core import (
    ConsentStatus, ConsentStream, DSARAccessPackage, DSARExportPackage,
    DSARDeletionStatus, ConsentImpactReport, DSARExportFormat
)
from ciris_engine.logic.services.governance.dsar.schemas import DataSourceExport, MultiSourceDSARAccessPackage, MultiSourceDSARExportPackage

@pytest.fixture
def mock_time_service():
    service = MagicMock()
    service.now.return_value = datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    return service

@pytest.fixture
def mock_dsar_automation():
    service = AsyncMock()
    # Setup default return for handle_access_request
    access_package = DSARAccessPackage(
        user_id="test_user",
        request_id="REQ-123",
        generated_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        consent_status=ConsentStatus(
            user_id="test_user",
            stream=ConsentStream.TEMPORARY,
            categories=[],
            granted_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            last_modified=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        ),
        consent_history=[],
        interaction_summary={},
        contribution_metrics=ConsentImpactReport(
            user_id="test_user",
            total_interactions=0,
            patterns_contributed=0,
            users_helped=0,
            categories_active=[],
            impact_score=0.0,
            example_contributions=[],
        ),
        data_categories=[],
        retention_periods={},
        processing_purposes=[],
    )
    service.handle_access_request.return_value = access_package

    # Setup default return for handle_export_request
    export_package = DSARExportPackage(
        user_id="test_user",
        request_id="REQ-123",
        export_format=DSARExportFormat.JSON,
        generated_at=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        file_path="/tmp/test.json",
        file_size_bytes=1024,
        record_counts={"table1": 10},
        checksum="abc123hash",
        includes_readme=True,
    )
    service.handle_export_request.return_value = export_package

    # Setup default return for get_deletion_status
    deletion_status = DSARDeletionStatus(
        ticket_id="DEL-123",
        user_id="test_user",
        decay_started=datetime(2023, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        current_phase="identity_severed",
        completion_percentage=0.0,
        estimated_completion=datetime(2023, 4, 1, 12, 0, 0, tzinfo=timezone.utc),
        milestones_completed=[],
        next_milestone="interaction_history_purged",
        safety_patterns_retained=0,
    )
    service.get_deletion_status.return_value = deletion_status

    return service

@pytest.fixture
def mock_consent_service():
    service = AsyncMock()
    return service

@pytest.fixture
def mock_tool_bus():
    bus = AsyncMock()
    # Mock tool discovery - explicit MagicMock for sync method
    mock_tool = MagicMock()
    mock_tool.get_service_metadata.return_value = {"connector_id": "sql_connector_1"}
    bus.get_tools_by_metadata = MagicMock(return_value=[mock_tool])

    # Robust side effect based on tool name
    def execute_tool_side_effect(tool_name, parameters, handler_name=None):
        mock_res = MagicMock()
        if tool_name == "sql_export_user":
            mock_res.data = {
                "data": {"table1": [{"id": 1}]},
                "tables_scanned": ["table1"],
                "total_records": 1
            }
        elif tool_name == "sql_delete_user":
            mock_res.success = True
            mock_res.data = {
                "success": True,
                "tables_affected": ["table1"],
                "total_records_deleted": 1
            }
        elif tool_name == "sql_verify_deletion":
            mock_res.data = {"zero_data_confirmed": True}
        return mock_res

    bus.execute_tool.side_effect = execute_tool_side_effect
    return bus

@pytest.fixture
def mock_memory_bus():
    bus = AsyncMock()
    return bus

@pytest.fixture
def dsar_orchestrator(mock_time_service, mock_dsar_automation, mock_consent_service, mock_tool_bus, mock_memory_bus):
    return DSAROrchestrator(
        time_service=mock_time_service,
        dsar_automation=mock_dsar_automation,
        consent_service=mock_consent_service,
        tool_bus=mock_tool_bus,
        memory_bus=mock_memory_bus,
    )

@pytest.mark.asyncio
async def test_init(dsar_orchestrator):
    assert dsar_orchestrator._multi_source_requests == 0

@pytest.mark.asyncio
async def test_handle_access_request_multi_source(dsar_orchestrator):
    with patch("ciris_engine.logic.utils.identity_resolution.resolve_user_identity", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None # Mock identity resolution result

        result = await dsar_orchestrator.handle_access_request_multi_source(
            user_identifier="test_user@example.com"
        )

        assert result.user_identifier == "test_user@example.com"
        assert len(result.external_sources) == 1
        assert result.external_sources[0].source_id == "sql_connector_1"
        assert result.total_records == 1

@pytest.mark.asyncio
async def test_handle_export_request_multi_source(dsar_orchestrator):
    with patch("ciris_engine.logic.utils.identity_resolution.resolve_user_identity", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None

        result = await dsar_orchestrator.handle_export_request_multi_source(
            user_identifier="test_user@example.com",
            export_format=DSARExportFormat.JSON
        )

        assert result.user_identifier == "test_user@example.com"
        assert result.export_format == "json"
        assert len(result.external_exports) == 1

@pytest.mark.asyncio
async def test_handle_deletion_request_multi_source(dsar_orchestrator):
    with patch("ciris_engine.logic.utils.identity_resolution.resolve_user_identity", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None

        result = await dsar_orchestrator.handle_deletion_request_multi_source(
            user_identifier="test_user@example.com"
        )

        assert result.user_identifier == "test_user@example.com"
        assert len(result.external_deletions) == 1
        assert result.external_deletions[0].success is True
        assert result.external_deletions[0].verification_passed is True

@pytest.mark.asyncio
async def test_handle_correction_request_multi_source(dsar_orchestrator):
    with patch("ciris_engine.logic.utils.identity_resolution.resolve_user_identity", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None

        result = await dsar_orchestrator.handle_correction_request_multi_source(
            user_identifier="test_user@example.com",
            corrections={"name": "New Name"}
        )

        assert result.user_identifier == "test_user@example.com"
        assert "ciris" in result.corrections_by_source
        assert result.corrections_by_source["ciris"] == {"name": "New Name"}

# --- Resilience Tests (Restored & Adapted) ---

@pytest.mark.asyncio
async def test_access_request_handles_ciris_failure_gracefully(dsar_orchestrator, mock_dsar_automation):
    """Test that access request creates empty package if CIRIS fails."""
    mock_dsar_automation.handle_access_request.side_effect = Exception("CIRIS unavailable")

    with patch("ciris_engine.logic.utils.identity_resolution.resolve_user_identity", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None

        result = await dsar_orchestrator.handle_access_request_multi_source("test@example.com")

        # Should still return a package
        assert isinstance(result, MultiSourceDSARAccessPackage)
        # CIRIS data should be an empty/fallback package
        assert result.ciris_data is not None
        assert result.ciris_data.user_id == "test@example.com"

@pytest.mark.asyncio
async def test_export_request_handles_ciris_failure(dsar_orchestrator, mock_dsar_automation):
    """Test that export creates empty package if CIRIS export fails."""
    mock_dsar_automation.handle_export_request.side_effect = Exception("Export failed")

    with patch("ciris_engine.logic.utils.identity_resolution.resolve_user_identity", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None

        result = await dsar_orchestrator.handle_export_request_multi_source(
            "test@example.com", export_format=DSARExportFormat.JSON
        )

        # Should still return a package with empty CIRIS export
        assert isinstance(result, MultiSourceDSARExportPackage)
        assert result.ciris_export.file_size_bytes == 0

@pytest.mark.asyncio
async def test_access_request_continues_on_sql_failure(dsar_orchestrator, mock_tool_bus):
    """Test that access request continues if one SQL source fails."""
    # Tool bus fails execution
    mock_tool_bus.execute_tool.side_effect = Exception("Database timeout")

    with patch("ciris_engine.logic.utils.identity_resolution.resolve_user_identity", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None

        result = await dsar_orchestrator.handle_access_request_multi_source("test@example.com")

        # Should still return a package
        assert isinstance(result, MultiSourceDSARAccessPackage)
        # Should contain error info for the source
        assert len(result.external_sources) == 1
        assert len(result.external_sources[0].errors) > 0
        assert "Database timeout" in result.external_sources[0].errors[0]
