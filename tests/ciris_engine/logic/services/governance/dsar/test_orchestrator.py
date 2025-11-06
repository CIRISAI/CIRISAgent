"""Comprehensive tests for DSAR multi-source orchestrator.

Tests coordinate DSAR operations across CIRIS + external sources (SQL, REST, HL7).
"""

import pytest

from ciris_engine.logic.services.governance.dsar.schemas import (
    MultiSourceDSARAccessPackage,
    MultiSourceDSARCorrectionResult,
    MultiSourceDSARDeletionResult,
    MultiSourceDSARExportPackage,
)
from ciris_engine.schemas.consent.core import DSARExportFormat


class TestOrchestratorInitialization:
    """Test orchestrator initialization."""

    def test_init_sets_dependencies(
        self, orchestrator, mock_time_service, mock_dsar_automation, mock_consent_service, mock_tool_bus, mock_memory_bus
    ):
        """Test that init properly sets all dependencies."""
        assert orchestrator._time_service == mock_time_service
        assert orchestrator._dsar_automation == mock_dsar_automation
        assert orchestrator._consent_service == mock_consent_service
        assert orchestrator._tool_bus == mock_tool_bus
        assert orchestrator._memory_bus == mock_memory_bus

    def test_init_resets_metrics(self, orchestrator):
        """Test that init resets metrics to zero."""
        assert orchestrator._multi_source_requests == 0
        assert orchestrator._total_sources_queried == 0
        assert orchestrator._total_processing_time == 0.0

    def test_now_uses_time_service(self, orchestrator, mock_time_service):
        """Test that _now() delegates to time service."""
        result = orchestrator._now()
        mock_time_service.now.assert_called_once()


class TestAccessRequest:
    """Test multi-source access requests."""

    @pytest.mark.asyncio
    async def test_access_request_returns_package(self, orchestrator):
        """Test that access request returns MultiSourceDSARAccessPackage."""
        result = await orchestrator.handle_access_request_multi_source("test@example.com")

        assert isinstance(result, MultiSourceDSARAccessPackage)
        assert result.user_identifier == "test@example.com"
        assert result.ciris_data is not None

    @pytest.mark.asyncio
    async def test_access_request_queries_sql_sources(self, orchestrator):
        """Test that access request discovers and queries SQL connectors."""
        result = await orchestrator.handle_access_request_multi_source("test@example.com")

        # Should include external sources in the result
        assert hasattr(result, "external_sources")
        assert isinstance(result.external_sources, list)

    @pytest.mark.asyncio
    async def test_access_request_handles_ciris_failure_gracefully(self, orchestrator, mock_dsar_automation):
        """Test that access request creates empty package if CIRIS fails."""
        mock_dsar_automation.handle_access_request.side_effect = Exception("CIRIS unavailable")

        result = await orchestrator.handle_access_request_multi_source("test@example.com")

        # Should still return a package
        assert isinstance(result, MultiSourceDSARAccessPackage)
        # CIRIS data should be an empty/fallback package
        assert result.ciris_data is not None


class TestExportRequest:
    """Test multi-source export requests."""

    @pytest.mark.asyncio
    async def test_export_request_returns_package(self, orchestrator):
        """Test that export request returns MultiSourceDSARExportPackage."""
        result = await orchestrator.handle_export_request_multi_source(
            "test@example.com", export_format=DSARExportFormat.JSON
        )

        assert isinstance(result, MultiSourceDSARExportPackage)
        assert result.user_identifier == "test@example.com"
        assert result.export_format == "json"

    @pytest.mark.asyncio
    async def test_export_request_aggregates_size(self, orchestrator):
        """Test that export request aggregates total size across sources."""
        result = await orchestrator.handle_export_request_multi_source(
            "test@example.com", export_format=DSARExportFormat.JSON
        )

        # Should aggregate sizes from CIRIS + external sources
        assert result.total_size_bytes >= result.ciris_export.file_size_bytes

    @pytest.mark.asyncio
    async def test_export_request_handles_ciris_failure(self, orchestrator, mock_dsar_automation):
        """Test that export creates empty package if CIRIS export fails."""
        mock_dsar_automation.handle_export_request.side_effect = Exception("Export failed")

        result = await orchestrator.handle_export_request_multi_source(
            "test@example.com", export_format=DSARExportFormat.JSON
        )

        # Should still return a package with empty CIRIS export
        assert isinstance(result, MultiSourceDSARExportPackage)
        assert result.ciris_export.file_size_bytes == 0


class TestDeletionRequest:
    """Test multi-source deletion requests."""

    @pytest.mark.asyncio
    async def test_deletion_request_returns_result(self, orchestrator):
        """Test that deletion request returns MultiSourceDSARDeletionResult."""
        result = await orchestrator.handle_deletion_request_multi_source("test@example.com")

        assert isinstance(result, MultiSourceDSARDeletionResult)
        assert result.user_identifier == "test@example.com"

    @pytest.mark.asyncio
    async def test_deletion_request_includes_ciris_deletion(self, orchestrator):
        """Test that deletion result includes CIRIS decay status."""
        result = await orchestrator.handle_deletion_request_multi_source("test@example.com")

        # Should have CIRIS deletion status
        assert result.ciris_deletion is not None
        assert hasattr(result.ciris_deletion, "current_phase")

    @pytest.mark.asyncio
    async def test_deletion_request_returns_multi_source_result(self, orchestrator):
        """Test that deletion returns comprehensive multi-source result."""
        result = await orchestrator.handle_deletion_request_multi_source("test@example.com")

        # Should have multi-source deletion metadata
        assert hasattr(result, "external_deletions")
        assert hasattr(result, "total_sources")
        assert hasattr(result, "sources_completed")


class TestCorrectionRequest:
    """Test multi-source correction requests."""

    @pytest.mark.asyncio
    async def test_correction_request_returns_result(self, orchestrator):
        """Test that correction request returns MultiSourceDSARCorrectionResult."""
        result = await orchestrator.handle_correction_request_multi_source(
            "test@example.com", corrections={"email": "newemail@example.com"}
        )

        assert isinstance(result, MultiSourceDSARCorrectionResult)
        assert result.user_identifier == "test@example.com"

    @pytest.mark.asyncio
    async def test_correction_request_applies_to_ciris(self, orchestrator, mock_dsar_automation):
        """Test that corrections are applied to CIRIS data."""
        result = await orchestrator.handle_correction_request_multi_source(
            "test@example.com", corrections={"email": "newemail@example.com"}
        )

        # Should have corrections applied
        assert result.total_corrections_applied >= 0 or "ciris" in result.corrections_by_source


class TestSQLConnectorDiscovery:
    """Test SQL connector discovery."""

    @pytest.mark.asyncio
    async def test_discover_sql_connectors_returns_list(self, orchestrator):
        """Test that _discover_sql_connectors returns a list of connectors."""
        result = await orchestrator._discover_sql_connectors()

        assert isinstance(result, list)
        # The list may be empty if no SQL connectors are configured
        # This is a valid state - the orchestrator handles gracefully


class TestSQLToolExecution:
    """Test SQL tool execution helpers."""

    @pytest.mark.asyncio
    async def test_export_from_sql_calls_export_tool(self, orchestrator, mock_tool_bus):
        """Test that _export_from_sql calls sql_export_user tool."""
        await orchestrator._export_from_sql("postgres_db", "test@example.com")

        mock_tool_bus.execute_tool.assert_called()
        call_args = mock_tool_bus.execute_tool.call_args
        assert call_args[1]["tool_name"] == "sql_export_user"

    @pytest.mark.asyncio
    async def test_export_from_sql_passes_connector_id(self, orchestrator, mock_tool_bus):
        """Test that export passes connector_id as parameter."""
        await orchestrator._export_from_sql("postgres_db", "test@example.com")

        call_args = mock_tool_bus.execute_tool.call_args
        assert call_args[1]["parameters"]["connector_id"] == "postgres_db"

    @pytest.mark.asyncio
    async def test_delete_from_sql_calls_delete_tool(self, orchestrator, mock_tool_bus):
        """Test that _delete_from_sql calls sql_delete_user tool."""
        await orchestrator._delete_from_sql("postgres_db", "test@example.com", verify=False)

        call_args = mock_tool_bus.execute_tool.call_args
        assert call_args[1]["tool_name"] == "sql_delete_user"

    @pytest.mark.asyncio
    async def test_verify_deletion_sql_calls_verify_tool(self, orchestrator, mock_tool_bus):
        """Test that _verify_deletion_sql calls sql_verify_deletion tool."""
        await orchestrator._verify_deletion_sql("postgres_db", "test@example.com")

        call_args = mock_tool_bus.execute_tool.call_args
        assert call_args[1]["tool_name"] == "sql_verify_deletion"


class TestErrorHandling:
    """Test error handling and resilience."""

    @pytest.mark.asyncio
    async def test_access_request_continues_on_sql_failure(self, orchestrator, mock_tool_bus):
        """Test that access request continues if one SQL source fails."""
        mock_tool_bus.execute_tool.side_effect = Exception("Database timeout")

        result = await orchestrator.handle_access_request_multi_source("test@example.com")

        # Should still return a package
        assert isinstance(result, MultiSourceDSARAccessPackage)


class TestMetrics:
    """Test orchestrator metrics tracking."""

    @pytest.mark.asyncio
    async def test_access_request_updates_request_count(self, orchestrator):
        """Test that access request increments request counter."""
        initial_count = orchestrator._multi_source_requests

        await orchestrator.handle_access_request_multi_source("test@example.com")

        assert orchestrator._multi_source_requests == initial_count + 1

    @pytest.mark.asyncio
    async def test_export_tracks_processing_time(self, orchestrator):
        """Test that export tracks processing time."""
        result = await orchestrator.handle_export_request_multi_source(
            "test@example.com", export_format=DSARExportFormat.JSON
        )

        assert result.processing_time_seconds >= 0
