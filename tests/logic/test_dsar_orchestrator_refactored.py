import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from ciris_engine.schemas.dsar import (
    MultiSourceDSARAccessPackage,
    MultiSourceDSARExportPackage,
    MultiSourceDSARDeletionResult,
    DataSourceExport,
    DataSourceDeletion
)
from ciris_engine.schemas.consent.core import (
    DSARAccessPackage,
    DSARExportPackage,
    DSARDeletionStatus,
    DSARExportFormat,
    ConsentStatus,
    ConsentStream,
    ConsentImpactReport
)

@pytest.fixture
def mock_auth_service():
    service = AsyncMock()
    # Mock Ed25519 signing - protocol says this is synchronous
    service.sign_data = MagicMock(return_value="mock_ed25519_signature")
    service.get_system_wa_id = AsyncMock(return_value="system_agent_001")
    return service

@pytest.fixture
def mock_time_service():
    service = MagicMock()
    service.now.return_value = datetime(2025, 12, 18, 12, 0, 0, tzinfo=timezone.utc)
    return service

@pytest.fixture
def mock_dsar_automation():
    service = AsyncMock()
    # Access Package mock
    now = datetime(2025, 12, 18, 12, 0, 0, tzinfo=timezone.utc)
    access_pkg = DSARAccessPackage(
        user_id="test@example.com",
        request_id="REQ-123",
        generated_at=now,
        consent_status=ConsentStatus(
            user_id="test@example.com",
            stream=ConsentStream.TEMPORARY,
            categories=[],
            granted_at=now,
            last_modified=now,
        ),
        consent_history=[],
        interaction_summary={},
        contribution_metrics=ConsentImpactReport(
            user_id="test@example.com",
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
    service.handle_access_request.return_value = access_pkg
    
    # Export Package mock
    export_pkg = DSARExportPackage(
        user_id="test@example.com",
        request_id="REQ-123",
        export_format=DSARExportFormat.JSON,
        generated_at=now,
        file_path=None,
        file_size_bytes=100,
        record_counts={},
        checksum="hash",
        includes_readme=True,
    )
    service.handle_export_request.return_value = export_pkg
    
    # Deletion Status mock
    del_status = DSARDeletionStatus(
        ticket_id="REQ-123",
        user_id="test@example.com",
        decay_started=now,
        current_phase="identity_severed",
        completion_percentage=10.0,
        estimated_completion=now,
        milestones_completed=[],
        next_milestone="purging",
        safety_patterns_retained=0,
    )
    service.get_deletion_status.return_value = del_status
    
    return service

@pytest.fixture
def mock_tool_bus():
    bus = AsyncMock()
    # Mock tool discovery
    bus.get_tools_by_metadata = AsyncMock(return_value=[
        ("sql_1", {"source_type": "sql", "connector_id": "ext_db", "data_source": True, "data_source_type": "sql"})
    ])
    
    # Mock tool results
    mock_res = MagicMock()
    mock_res.success = True
    mock_res.data = {
        "data": {"users": [{"id": 1}]},
        "tables_scanned": ["users"],
        "total_records": 1,
        "success": True,
        "tables_affected": ["users"],
        "total_records_deleted": 1,
        "zero_data_confirmed": True
    }
    bus.execute_tool = AsyncMock(return_value=mock_res)
    return bus

@pytest.fixture
def orchestrator(mock_time_service, mock_dsar_automation, mock_auth_service, mock_tool_bus):
    # We will implement this in ciris_engine.logic.dsar_orchestrator
    try:
        from ciris_engine.logic.dsar_orchestrator import DsarOrchestrator
    except ImportError:
        # Fallback for TDD
        return None

    return DsarOrchestrator(
        time_service=mock_time_service,
        dsar_automation=mock_dsar_automation,
        consent_service=AsyncMock(),
        tool_bus=mock_tool_bus,
        memory_bus=AsyncMock(),
        auth_service=mock_auth_service
    )

@pytest.mark.asyncio
async def test_access_request_returns_signed_package(orchestrator):
    if orchestrator is None:
        pytest.fail("DsarOrchestrator not implemented")
        
    with patch("ciris_engine.logic.utils.identity_resolution.resolve_user_identity", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None
        
        result = await orchestrator.handle_access_request_multi_source("test@example.com")
        
        assert isinstance(result, MultiSourceDSARAccessPackage)
        assert result.signature == "mock_ed25519_signature"
        assert len(result.external_sources) > 0
        assert result.external_sources[0].signature == "mock_ed25519_signature"

@pytest.mark.asyncio
async def test_export_request_returns_signed_package(orchestrator):
    if orchestrator is None:
        pytest.fail("DsarOrchestrator not implemented")
        
    with patch("ciris_engine.logic.utils.identity_resolution.resolve_user_identity", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None
        
        result = await orchestrator.handle_export_request_multi_source("test@example.com", DSARExportFormat.JSON)
        
        assert isinstance(result, MultiSourceDSARExportPackage)
        assert result.signature == "mock_ed25519_signature"

@pytest.mark.asyncio
async def test_deletion_request_returns_signed_result(orchestrator):
    if orchestrator is None:
        pytest.fail("DsarOrchestrator not implemented")
        
    with patch("ciris_engine.logic.utils.identity_resolution.resolve_user_identity", new_callable=AsyncMock) as mock_resolve:
        mock_resolve.return_value = None
        
        result = await orchestrator.handle_deletion_request_multi_source("test@example.com")
        
        assert isinstance(result, MultiSourceDSARDeletionResult)
        assert result.signature == "mock_ed25519_signature"
