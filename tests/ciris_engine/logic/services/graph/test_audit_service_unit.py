"""Unit tests for GraphAuditService."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Generator
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.services.graph.audit_service import GraphAuditService
from ciris_engine.schemas.runtime.audit import AuditActionContext
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph.audit import AuditEventData, VerificationReport
from ciris_engine.schemas.services.graph_core import GraphNode, NodeType


class TestGraphAuditService:
    """Test cases for GraphAuditService."""

    @pytest.fixture
    def mock_time_service(self) -> Mock:
        """Create mock time service."""
        current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_service = Mock()
        mock_service.now.return_value = current_time
        mock_service.now_iso.return_value = current_time.isoformat()
        return mock_service

    @pytest.fixture
    def mock_memory_bus(self) -> Mock:
        """Create mock memory bus."""
        bus = Mock()
        bus.memorize = AsyncMock()
        bus.recall = AsyncMock(return_value=[])
        bus.search = AsyncMock(return_value=[])
        return bus

    @pytest.fixture
    def audit_service(self, mock_time_service: Mock, mock_memory_bus: Mock) -> Generator[GraphAuditService, None, None]:
        """Create GraphAuditService instance."""
        import tempfile

        with tempfile.TemporaryDirectory() as temp_dir:
            service = GraphAuditService(
                memory_bus=mock_memory_bus,
                time_service=mock_time_service,
                retention_days=30,
                db_path=f"{temp_dir}/test_audit.db",  # Use temporary database
                export_path=f"{temp_dir}/audit_export.jsonl",  # Provide export path
            )
            yield service

    @pytest.mark.asyncio
    async def test_start_stop(self, audit_service: GraphAuditService) -> None:
        """Test service start and stop."""
        # Start
        await audit_service.start()
        # Service should be started

        # Stop
        await audit_service.stop()
        # Service should be stopped

    @pytest.mark.asyncio
    async def test_log_event(self, audit_service: GraphAuditService, mock_memory_bus: Mock) -> None:
        """Test logging an event."""
        await audit_service.start()

        # Log an event
        event_data = AuditEventData(
            entity_id="TestService",
            actor="system",
            outcome="success",
            severity="info",
            action="start",
            resource="service",
            reason="service startup",
            metadata={"version": "1.0.0"},
        )

        await audit_service.log_event(event_type="service_start", event_data=event_data)

        # Should create and store audit entry
        mock_memory_bus.memorize.assert_called_once()
        call_args = mock_memory_bus.memorize.call_args[1]
        node = call_args["node"]

        assert isinstance(node, GraphNode)
        # Check the audit entry was created properly
        assert node.type == NodeType.AUDIT_ENTRY
        assert call_args["handler_name"] == "audit_service"

    @pytest.mark.asyncio
    async def test_log_action(self, audit_service: GraphAuditService, mock_memory_bus: Mock) -> None:
        """Test logging an action."""
        await audit_service.start()

        # Log an action
        context = AuditActionContext(
            thought_id="thought123",
            task_id="task123",
            handler_name="auth_handler",
            parameters={"user_id": "user123", "method": "token"},
        )

        await audit_service.log_action(action_type=HandlerActionType.TOOL, context=context, outcome="success")

        mock_memory_bus.memorize.assert_called_once()
        call_args = mock_memory_bus.memorize.call_args[1]
        node = call_args["node"]

        assert call_args["handler_name"] == "audit_service"
        assert call_args["metadata"]["immutable"] is True

    @pytest.mark.asyncio
    async def test_log_authentication_failure(self, audit_service: GraphAuditService, mock_memory_bus: Mock) -> None:
        """Test logging failed authentication."""
        await audit_service.start()

        # Log failed auth event
        event_data = AuditEventData(
            entity_id="user123",
            actor="auth_service",
            outcome="failure",
            severity="warning",
            action="authenticate",
            resource="auth",
            reason="Invalid credentials",
            metadata={"method": "password", "ip_address": "192.168.1.1"},
        )

        await audit_service.log_event(event_type="auth_failure", event_data=event_data)

        mock_memory_bus.memorize.assert_called_once()
        call_args = mock_memory_bus.memorize.call_args[1]

        assert call_args["handler_name"] == "audit_service"
        assert call_args["metadata"]["immutable"] is True

    @pytest.mark.asyncio
    async def test_log_configuration_change(self, audit_service: GraphAuditService, mock_memory_bus: Mock) -> None:
        """Test logging configuration changes."""
        await audit_service.start()

        event_data = AuditEventData(
            entity_id="ConfigService",
            actor="admin",
            outcome="success",
            severity="info",
            action="update_config",
            resource="config",
            reason="configuration update",
            metadata={"config_key": "max_retries", "old_value": "3", "new_value": "5"},
        )

        await audit_service.log_event(event_type="config_change", event_data=event_data)

        mock_memory_bus.memorize.assert_called_once()
        call_args = mock_memory_bus.memorize.call_args[1]

        assert call_args["handler_name"] == "audit_service"

    @pytest.mark.asyncio
    async def test_log_data_access(self, audit_service: GraphAuditService, mock_memory_bus: Mock) -> None:
        """Test logging data access events."""
        await audit_service.start()

        event_data = AuditEventData(
            entity_id="patient_record:12345",
            actor="user123",
            outcome="success",
            severity="info",
            action="read",
            resource="patient_record",
            reason="data access",
            metadata={"resource_type": "patient_record", "resource_id": "12345"},
        )

        await audit_service.log_event(event_type="data_access", event_data=event_data)

        mock_memory_bus.memorize.assert_called_once()
        call_args = mock_memory_bus.memorize.call_args[1]

        assert call_args["handler_name"] == "audit_service"

    @pytest.mark.asyncio
    async def test_log_error(self, audit_service: GraphAuditService, mock_memory_bus: Mock) -> None:
        """Test logging error events."""
        await audit_service.start()

        event_data = AuditEventData(
            entity_id="DataProcessor",
            actor="system",
            outcome="error",
            severity="error",
            action="process_data",
            resource="data_processor",
            reason="Invalid input format",
            metadata={
                "error_type": "ValidationError",
                "error_message": "Invalid input format",
                "stack_trace": "File x, line y...",
            },
        )

        await audit_service.log_event(event_type="error", event_data=event_data)

        mock_memory_bus.memorize.assert_called_once()
        call_args = mock_memory_bus.memorize.call_args[1]

        assert call_args["handler_name"] == "audit_service"

    @pytest.mark.asyncio
    async def test_query_audit_trail(
        self, audit_service: GraphAuditService, mock_memory_bus: Mock, mock_time_service: Mock
    ) -> None:
        """Test querying audit trail."""
        from ciris_engine.schemas.services.graph.audit import AuditQuery

        await audit_service.start()

        # Mock search to return empty list (since query_audit_trail now uses search)
        mock_memory_bus.search = AsyncMock(return_value=[])

        # Create query object
        query = AuditQuery(
            start_time=mock_time_service.now() - timedelta(hours=1), end_time=mock_time_service.now(), limit=10
        )

        # Query audit trail
        entries = await audit_service.query_audit_trail(query)

        # Should call search
        mock_memory_bus.search.assert_called_once()

        # Should return list (empty in this case)
        assert isinstance(entries, list)

    @pytest.mark.asyncio
    async def test_get_audit_trail(self, audit_service: GraphAuditService, mock_memory_bus: Mock) -> None:
        """Test getting audit trail for entity."""
        await audit_service.start()

        # Mock recall_timeseries
        mock_memory_bus.recall_timeseries = AsyncMock(return_value=[])

        # Get audit trail for specific entity
        entries = await audit_service.get_audit_trail(entity_id="entity123", hours=24)

        # Should call recall_timeseries
        mock_memory_bus.recall_timeseries.assert_called_once()
        call_args = mock_memory_bus.recall_timeseries.call_args

        assert call_args[1]["scope"] == "local"
        assert call_args[1]["handler_name"] == "audit_service"

        # Should return list
        assert isinstance(entries, list)

    @pytest.mark.asyncio
    async def test_verify_audit_integrity(self, audit_service: GraphAuditService) -> None:
        """Test audit integrity verification."""
        await audit_service.start()

        # Hash chain is enabled by default, so with no entries it should verify successfully
        report = await audit_service.verify_audit_integrity()

        assert isinstance(report, VerificationReport)
        assert report.verified is True  # Empty chain verifies successfully
        assert report.total_entries == 0
        assert report.valid_entries == 0
        assert report.invalid_entries == 0
        assert report.chain_intact is True
        assert len(report.errors) == 0

    @pytest.mark.asyncio
    async def test_export_audit_data(self, audit_service, mock_memory_bus):
        """Test exporting audit data."""
        await audit_service.start()

        # Mock query results
        mock_memory_bus.recall_timeseries = AsyncMock(return_value=[])

        # Export should work now that export_path is configured
        result = await audit_service.export_audit_data(
            start_time=datetime.now(timezone.utc) - timedelta(days=1), format="jsonl"
        )
        # Should return a valid path string
        assert result is not None
        assert isinstance(result, str)
        assert "audit_export" in result

    def test_get_capabilities(self, audit_service):
        """Test getting service capabilities."""
        caps = audit_service.get_capabilities()

        assert isinstance(caps, ServiceCapabilities)
        assert caps.service_name == "GraphAuditService"
        assert "log_action" in caps.actions
        assert "log_event" in caps.actions
        assert "query_audit_trail" in caps.actions
        assert caps.version == "2.0.0"  # GraphAuditService is v2

    def test_get_status(self, audit_service):
        """Test getting service status."""
        status = audit_service.get_status()

        assert isinstance(status, ServiceStatus)
        # Service is not started in this test, so it won't be healthy
        assert status.is_healthy is False
        assert "cached_entries" in status.metrics
        assert "pending_exports" in status.metrics
        assert "hash_chain_enabled" in status.metrics

    @pytest.mark.asyncio
    async def test_concurrent_log_events(self, audit_service, mock_memory_bus):
        """Test concurrent event logging."""
        await audit_service.start()

        # Create multiple events concurrently
        tasks = []
        for i in range(10):
            event_data = AuditEventData(
                entity_id=f"Service{i}",
                actor="system",
                outcome="success",
                severity="info",
                action="data_access",
                metadata={"index": i},
            )
            task = audit_service.log_event(event_type="data_access", event_data=event_data)
            tasks.append(task)

        await asyncio.gather(*tasks)

        # All should succeed
        assert mock_memory_bus.memorize.call_count == 10

    @pytest.mark.asyncio
    async def test_log_with_large_metadata(self, audit_service, mock_memory_bus):
        """Test logging with large metadata objects."""
        await audit_service.start()

        # Create large metadata - must be flat dict with primitive values
        large_metadata = {
            "data": "x" * 10000,  # 10KB of data
            "item_count": 100,
            "processing_time": 45.67,
            "is_large": True,
            "nested_level1": "value1",
            "nested_level2": "value2",
        }

        event_data = AuditEventData(
            entity_id="LargeService",
            actor="system",
            outcome="success",
            severity="info",
            action="data_access",
            metadata=large_metadata,
        )

        await audit_service.log_event(event_type="data_access", event_data=event_data)

        # Should handle large data
        mock_memory_bus.memorize.assert_called_once()

    def test_get_node_type(self, audit_service):
        """Test that audit service uses correct node type."""
        node_type = audit_service.get_node_type()
        assert node_type == "AUDIT"
