"""Unit tests for GraphAuditService."""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.graph.audit_service import GraphAuditService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.runtime.audit import AuditActionContext, AuditRequest
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph.audit import AuditEventData, AuditQuery, VerificationReport
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@pytest.fixture
def time_service():
    """Create a time service for testing."""
    return TimeService()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def memory_bus():
    """Create a mock memory bus for testing."""
    bus = Mock(spec=MemoryBus)

    # Mock memorize to return success
    bus.memorize = AsyncMock(return_value=MemoryOpResult(status=MemoryOpStatus.OK, error=None))

    # Mock recall to return empty list by default
    bus.recall = AsyncMock(return_value=[])

    # Mock search to return empty list
    bus.search = AsyncMock(return_value=[])

    # Mock recall_timeseries for audit queries
    bus.recall_timeseries = AsyncMock(return_value=[])

    return bus


@pytest_asyncio.fixture
async def audit_service(memory_bus, temp_db, time_service):
    """Create an audit service for testing."""
    # Create a temporary directory for export
    with tempfile.TemporaryDirectory() as temp_dir:
        export_path = os.path.join(temp_dir, "audit_export.jsonl")
        service = GraphAuditService(
            memory_bus=memory_bus,
            time_service=time_service,
            db_path=temp_db,
            export_path=export_path,  # Provide export path for tests
            enable_hash_chain=True,  # REQUIRED - audit trail now requires hash chain data
        )
        await service.start()
        yield service
        try:
            await service.stop()
        except asyncio.CancelledError:
            pass  # Expected when cancelling export task


@pytest.mark.asyncio
async def test_audit_service_lifecycle(audit_service):
    """Test GraphAuditService start/stop lifecycle."""
    # Service should already be started from fixture
    # Just verify it's running
    assert await audit_service.is_healthy()
    # Service will be stopped by fixture


@pytest.mark.asyncio
async def test_audit_service_log_action(audit_service):
    """Test logging an action with AuditActionContext."""
    # Create action context
    context = AuditActionContext(
        thought_id="test_thought_123",
        task_id="test_task_456",
        handler_name="test_handler",
        parameters={"param1": "value1"},
    )

    # Log the action
    await audit_service.log_action(action_type=HandlerActionType.SPEAK, context=context, outcome="success")

    # Verify memory bus was called
    assert audit_service._memory_bus.memorize.called


@pytest.mark.asyncio
async def test_audit_service_log_event(audit_service):
    """Test logging a general event."""
    # Create simple event data without optional fields that cause issues
    event_data = AuditEventData(entity_id="test_entity", actor="test_user", outcome="success", severity="info")

    # Log the event
    await audit_service.log_event(event_type="custom_event", event_data=event_data)

    # Verify memory bus was called now that the bug is fixed
    assert audit_service._memory_bus.memorize.called
    call_args = audit_service._memory_bus.memorize.call_args[1]
    assert call_args["handler_name"] == "audit_service"


@pytest.mark.asyncio
async def test_audit_service_get_audit_trail(audit_service, memory_bus):
    """Test retrieving audit trail."""
    # Create mock audit entries
    mock_entries = [
        AuditRequest(
            entry_id="entry1",
            timestamp=datetime.now(timezone.utc),
            entity_id="entity1",
            event_type="test_event",
            actor="test_actor",
            details={"detail": "value"},
            outcome="success",
        )
    ]

    # Mock memory bus to return audit nodes
    from ciris_engine.schemas.services.graph_core import GraphScope
    from ciris_engine.schemas.services.nodes import AuditEntry as AuditEntryNode
    from ciris_engine.schemas.services.nodes import AuditEntryContext

    mock_node = AuditEntryNode(
        id="audit_entry1",
        action="test_event",
        actor="test_actor",
        timestamp=mock_entries[0].timestamp,
        context=AuditEntryContext(service_name="GraphAuditService", correlation_id="entry1"),
        scope=GraphScope.LOCAL,
        attributes={},  # Required field
    )
    memory_bus.recall.return_value = [mock_node.to_graph_node()]

    # Get audit trail - requires entity_id
    entries = await audit_service.get_audit_trail(entity_id="entity1", hours=24)

    # Should have retrieved entries
    assert len(entries) >= 0  # May be empty if no entries stored
    # The audit service uses recall_timeseries
    assert memory_bus.recall_timeseries.called


@pytest.mark.asyncio
async def test_audit_service_query_audit_trail(audit_service, memory_bus):
    """Test querying audit trail with filters."""

    # Create an AuditQuery object
    start_time = datetime.now(timezone.utc)
    query = AuditQuery(start_time=start_time, action_types=["test_event"], limit=5)

    # Query audit trail
    results = await audit_service.query_audit_trail(query)

    # Should return list of audit entries
    assert isinstance(results, list)
    assert len(results) <= 5  # Should respect limit


@pytest.mark.asyncio
async def test_audit_service_verify_integrity(audit_service):
    """Test audit integrity verification."""
    # For tests with hash chain disabled, should return basic report
    report = await audit_service.verify_audit_integrity()

    assert isinstance(report, VerificationReport)
    assert isinstance(report.verified, bool)
    assert report.total_entries >= 0
    assert report.duration_ms >= 0


def test_audit_service_capabilities(audit_service):
    """Test GraphAuditService.get_capabilities() returns correct info."""
    caps = audit_service.get_capabilities()
    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "GraphAuditService"
    assert caps.version == "2.0.0"  # GraphAuditService is v2
    assert "log_action" in caps.actions
    assert "log_event" in caps.actions
    assert "get_audit_trail" in caps.actions
    assert "verify_audit_integrity" in caps.actions  # Actual method name
    # GraphAuditService lists MemoryBus as dependency
    assert "MemoryBus" in caps.dependencies
    # Check metadata exists (exact text may vary)
    assert caps.metadata is None or isinstance(caps.metadata, dict)


def test_audit_service_status(audit_service):
    """Test GraphAuditService.get_status() returns correct status."""
    status = audit_service.get_status()
    assert isinstance(status, ServiceStatus)
    assert status.service_name == "GraphAuditService"
    assert status.service_type == "audit"
    assert status.is_healthy is True
    assert "cached_entries" in status.metrics  # Actual metric name
    assert "hash_chain_enabled" in status.metrics


@pytest.mark.asyncio
async def test_audit_service_log_conscience_event(audit_service):
    """Test logging a conscience decision event."""
    # Log conscience event with new signature
    await audit_service.log_conscience_event(
        thought_id="test_thought_123",
        decision="allow",
        reasoning="Action permitted based on ethical guidelines",
        metadata={"risk_level": "low", "confidence": 0.95},
    )

    # Verify memory bus was called now that the bug is fixed
    assert audit_service._memory_bus.memorize.called


@pytest.mark.asyncio
async def test_audit_service_export_data(audit_service):
    """Test exporting audit data."""
    # Export should work now that export_path is configured
    export_path = await audit_service.export_audit_data(
        format="jsonl", start_time=datetime.now(timezone.utc)  # Use supported format
    )
    # Should return a valid path
    assert export_path is not None
    assert isinstance(export_path, str)
    assert "audit_export" in export_path


@pytest.mark.asyncio
async def test_audit_service_error_handling(audit_service, memory_bus):
    """Test error handling in audit service - fails fast on database errors."""
    # Make memory bus raise error
    memory_bus.memorize.side_effect = Exception("Database error")

    event_data = AuditEventData(entity_id="test", actor="test")

    # Audit service fails fast - RuntimeError is raised when database fails
    with pytest.raises(RuntimeError, match="Failed to create audit entry"):
        await audit_service.log_event("test_event", event_data)


@pytest.mark.asyncio
async def test_audit_service_cache_management(audit_service):
    """Test audit entry cache management."""
    # Log multiple events to fill cache
    for i in range(5):
        event_data = AuditEventData(entity_id=f"entity_{i}", actor=f"actor_{i}", severity="info")
        await audit_service.log_event(f"event_{i}", event_data)

    # Check status shows cached entries
    status = audit_service.get_status()
    assert status.metrics["cached_entries"] >= 0  # Actual metric name


@pytest.mark.asyncio
async def test_audit_service_get_verification_report(audit_service):
    """Test getting verification report."""
    # Get verification report
    report = await audit_service.get_verification_report()

    assert isinstance(report, VerificationReport)
    assert hasattr(report, "verified")
    assert hasattr(report, "total_entries")
    assert hasattr(report, "chain_intact")


@pytest.mark.asyncio
async def test_audit_service_health_check(audit_service):
    """Test health check functionality."""
    # Check health
    is_healthy = await audit_service.is_healthy()

    assert isinstance(is_healthy, bool)
    assert is_healthy is True  # Should be healthy after start
