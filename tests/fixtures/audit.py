"""
Central fixtures for audit service testing.

Provides comprehensive mock audit service with triple backend support:
1. Graph storage (via memory_bus)
2. File export (optional)
3. Hash chain (cryptographic integrity)
"""

from unittest.mock import AsyncMock, Mock
from datetime import datetime, timezone

import pytest


@pytest.fixture
def mock_audit_service():
    """
    Create a fully-configured mock audit service for testing.

    The audit service has three backends:
    1. Graph storage (everything is memory) via memory_bus
    2. Optional file export for compliance
    3. Cryptographic hash chain for integrity

    Returns:
        AsyncMock: Configured audit service mock with all methods
    """
    from ciris_engine.schemas.services.graph.audit import AuditEventData
    from ciris_engine.schemas.audit.hash_chain import AuditEntryResult
    from uuid import uuid4

    mock = AsyncMock()

    # Track logged events for assertions
    mock.logged_events = []

    async def mock_log_event(event_type: str, event_data: AuditEventData, **kwargs):
        """Mock log_event that tracks calls for testing.

        Returns AuditEntryResult per protocol specification.
        """
        entry_id = str(uuid4())
        mock.logged_events.append({
            "entry_id": entry_id,
            "event_type": event_type,
            "entity_id": event_data.entity_id,
            "actor": event_data.actor,
            "outcome": event_data.outcome,
            "severity": event_data.severity,
            "action": event_data.action,
            "resource": event_data.resource,
            "metadata": event_data.metadata,
            "timestamp": datetime.now(timezone.utc),
        })
        # Return AuditEntryResult as per protocol
        return AuditEntryResult(
            entry_id=entry_id,
            timestamp=datetime.now(timezone.utc),
            previous_hash="mock_previous_hash",
            current_hash="mock_current_hash",
            chain_valid=True,
        )

    mock.log_event = AsyncMock(side_effect=mock_log_event)

    # Query methods
    async def mock_query_events(query_params=None):
        """Mock query_events that returns tracked events."""
        return mock.logged_events

    mock.query_events = AsyncMock(side_effect=mock_query_events)

    # Verification methods
    async def mock_verify_audit_integrity():
        """Mock audit integrity verification per protocol."""
        from ciris_engine.schemas.services.graph.audit import VerificationReport

        now = datetime.now(timezone.utc)
        return VerificationReport(
            verified=True,
            total_entries=len(mock.logged_events),
            valid_entries=len(mock.logged_events),
            invalid_entries=0,
            missing_entries=0,
            chain_intact=True,
            last_valid_entry=mock.logged_events[-1]["entry_id"] if mock.logged_events else None,
            first_invalid_entry=None,
            verification_started=now,
            verification_completed=now,
            duration_ms=1.0,
            errors=[],
            warnings=[],
        )

    mock.verify_audit_integrity = AsyncMock(side_effect=mock_verify_audit_integrity)
    mock.get_verification_report = AsyncMock(side_effect=mock_verify_audit_integrity)

    # Export methods
    async def mock_export_to_file(file_path: str, format: str = "jsonl"):
        """Mock file export."""
        return True

    mock.export_to_file = AsyncMock(side_effect=mock_export_to_file)

    # Service lifecycle methods
    async def mock_initialize():
        """Mock initialization."""
        return True

    async def mock_shutdown():
        """Mock shutdown."""
        return True

    mock.initialize = AsyncMock(side_effect=mock_initialize)
    mock.shutdown = AsyncMock(side_effect=mock_shutdown)

    # Health check
    async def mock_health_check():
        """Mock health check."""
        return {
            "healthy": True,
            "total_events": len(mock.logged_events),
            "graph_backend": "connected",
            "hash_chain": "valid",
        }

    mock.health_check = AsyncMock(side_effect=mock_health_check)

    return mock


@pytest.fixture
def sample_audit_event():
    """
    Provide a sample audit event for testing.

    Returns:
        AuditEventData: Sample audit event with all required fields
    """
    from ciris_engine.schemas.services.graph.audit import AuditEventData

    return AuditEventData(
        entity_id="test-entity-123",
        actor="test-user",
        outcome="success",
        severity="info",
        action="test_action",
        resource="test_resource",
        metadata={
            "test_key": "test_value",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        },
    )


@pytest.fixture
def ownership_transfer_audit_event():
    """
    Provide a sample task ownership transfer audit event.

    This is used for multi-occurrence shared task claiming tests.

    Returns:
        AuditEventData: Ownership transfer audit event
    """
    from ciris_engine.schemas.services.graph.audit import AuditEventData

    return AuditEventData(
        entity_id="test-task-456",
        actor="system",
        outcome="success",
        severity="info",
        action="task_ownership_transfer",
        resource="task",
        metadata={
            "task_id": "test-task-456",
            "from_occurrence_id": "__shared__",
            "to_occurrence_id": "occurrence-123",
            "task_type": "shared_coordination",
        },
    )
