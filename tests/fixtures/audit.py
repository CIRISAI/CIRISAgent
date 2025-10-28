"""
Central fixtures for audit service testing.

Provides comprehensive mock audit service with triple backend support:
1. Graph storage (via memory_bus)
2. File export (optional)
3. Hash chain (cryptographic integrity)
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock

import pytest

from ciris_engine.schemas.audit.hash_chain import AuditEntryResult
from ciris_engine.schemas.services.graph.audit import AuditEventData, VerificationReport


@pytest.fixture
def mock_audit_service() -> AsyncMock:
    """
    Create a fully-configured mock audit service for testing.

    The audit service has three backends:
    1. Graph storage (everything is memory) via memory_bus
    2. Optional file export for compliance
    3. Hash chain (cryptographic integrity)

    Returns:
        AsyncMock: Configured audit service mock with all methods
    """
    from uuid import uuid4

    mock = AsyncMock()

    # Track logged events for assertions - cast to avoid mypy attribute declaration error
    logged_events: List[Dict[str, Any]] = []
    mock.logged_events = logged_events

    async def mock_log_event(event_type: str, event_data: AuditEventData, **kwargs: Any) -> AuditEntryResult:
        """Mock log_event that tracks calls for testing.

        Returns AuditEntryResult per protocol specification.
        """
        entry_id = str(uuid4())
        sequence_num = len(logged_events) + 1
        logged_events.append(
            {
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
            }
        )
        # Return AuditEntryResult with all required fields
        return AuditEntryResult(
            entry_id=entry_id,
            sequence_number=sequence_num,
            entry_hash=f"mock_hash_{entry_id}",
            previous_hash=f"mock_prev_hash_{sequence_num-1}" if sequence_num > 1 else None,
            signature=f"mock_signature_{entry_id}",
            signing_key_id="mock_key_id",
        )

    mock.log_event = AsyncMock(side_effect=mock_log_event)

    # Query methods
    async def mock_query_events(query_params: Optional[Any] = None) -> List[Dict[str, Any]]:
        """Mock query_events that returns tracked events."""
        return logged_events

    mock.query_events = AsyncMock(side_effect=mock_query_events)

    # Verification methods
    async def mock_verify_audit_integrity() -> VerificationReport:
        """Mock audit integrity verification per protocol."""
        now = datetime.now(timezone.utc)
        return VerificationReport(
            verified=True,
            total_entries=len(logged_events),
            valid_entries=len(logged_events),
            invalid_entries=0,
            missing_entries=0,
            chain_intact=True,
            last_valid_entry=logged_events[-1]["entry_id"] if logged_events else None,
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
    async def mock_export_to_file(file_path: str, format: str = "jsonl") -> bool:
        """Mock file export."""
        return True

    mock.export_to_file = AsyncMock(side_effect=mock_export_to_file)

    # Service lifecycle methods
    async def mock_initialize() -> bool:
        """Mock initialization."""
        return True

    async def mock_shutdown() -> bool:
        """Mock shutdown."""
        return True

    mock.initialize = AsyncMock(side_effect=mock_initialize)
    mock.shutdown = AsyncMock(side_effect=mock_shutdown)

    # Health check
    async def mock_health_check() -> Dict[str, Any]:
        """Mock health check."""
        return {
            "healthy": True,
            "total_events": len(logged_events),
            "graph_backend": "connected",
            "hash_chain": "valid",
        }

    mock.health_check = AsyncMock(side_effect=mock_health_check)

    return mock


@pytest.fixture
def sample_audit_event() -> AuditEventData:
    """
    Provide a sample audit event for testing.

    Returns:
        AuditEventData: Sample audit event with all required fields
    """
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
def ownership_transfer_audit_event() -> AuditEventData:
    """
    Provide a sample task ownership transfer audit event.

    This is used for multi-occurrence shared task claiming tests.

    Returns:
        AuditEventData: Ownership transfer audit event
    """
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
