"""
Test fixtures for ConsentService testing.

Provides reusable fixtures for testing the consent service functionality,
including decay protocol, partnership management, DSAR automation, and AIR.
"""

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock, MagicMock

import pytest

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.governance.consent import ConsentService
from ciris_engine.logic.services.governance.consent.air import ArtificialInteractionReminder
from ciris_engine.logic.services.governance.consent.decay import DecayProtocolManager
from ciris_engine.logic.services.governance.consent.dsar_automation import DSARAutomationService
from ciris_engine.logic.services.governance.consent.metrics import ConsentMetricsCollector
from ciris_engine.logic.services.governance.consent.partnership import PartnershipManager
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import (
    ConsentAuditEntry,
    ConsentCategory,
    ConsentDecayStatus,
    ConsentRequest,
    ConsentStatus,
    ConsentStream,
    DecayCounters,
    OperationalCounters,
    PartnershipCounters,
    PartnershipOutcome,
    PartnershipOutcomeType,
    PartnershipRequest,
)
from ciris_engine.schemas.services.graph_core import GraphNode, GraphScope, NodeType


@pytest.fixture
def mock_time_service():
    """Create a mock time service with predictable timestamps."""
    mock = Mock(spec=TimeServiceProtocol)
    mock.now.return_value = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
    return mock


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus for testing graph operations."""
    return AsyncMock(spec=MemoryBus)


@pytest.fixture
def consent_service_with_mocks(mock_time_service, mock_memory_bus):
    """Create a consent service with mocked dependencies."""
    service = ConsentService(time_service=mock_time_service, memory_bus=mock_memory_bus, db_path=None)
    return service


@pytest.fixture
def consent_service_without_memory_bus(mock_time_service):
    """Create a consent service without memory bus (cache-only mode)."""
    service = ConsentService(time_service=mock_time_service, memory_bus=None, db_path=None)
    return service


@pytest.fixture
def sample_temporary_consent(mock_time_service):
    """Create a sample temporary consent status."""
    now = mock_time_service.now()
    return ConsentStatus(
        user_id="temp_user_123",
        stream=ConsentStream.TEMPORARY,
        granted_at=now,
        expires_at=now + timedelta(days=14),
        last_modified=now,
        attribution_count=5,
        impact_score=0.7,
        categories=[ConsentCategory.INTERACTION, ConsentCategory.PREFERENCE],
    )


@pytest.fixture
def sample_permanent_consent(mock_time_service):
    """Create a sample permanent consent status."""
    now = mock_time_service.now()
    return ConsentStatus(
        user_id="perm_user_456",
        stream=ConsentStream.PARTNERED,
        granted_at=now - timedelta(days=60),
        expires_at=None,
        last_modified=now,
        attribution_count=25,
        impact_score=0.95,
        categories=[ConsentCategory.PREFERENCE, ConsentCategory.RESEARCH],
    )


@pytest.fixture
def sample_decaying_consent(mock_time_service):
    """Create a sample decaying consent status."""
    now = mock_time_service.now()
    return ConsentStatus(
        user_id="decay_user_789",
        stream=ConsentStream.TEMPORARY,  # Decaying uses temporary stream
        granted_at=now - timedelta(days=30),
        expires_at=now + timedelta(days=90),
        last_modified=now,
        attribution_count=12,
        impact_score=0.85,
        categories=[ConsentCategory.IMPROVEMENT, ConsentCategory.INTERACTION],
    )


@pytest.fixture
def expired_temporary_consent(mock_time_service):
    """Create an expired temporary consent status."""
    now = mock_time_service.now()
    return ConsentStatus(
        user_id="expired_user_001",
        stream=ConsentStream.TEMPORARY,
        granted_at=now - timedelta(days=19),  # Granted 19 days ago
        expires_at=now - timedelta(days=5),  # Expired 5 days ago
        last_modified=now - timedelta(days=5),
        attribution_count=3,
        impact_score=0.4,
        categories=[ConsentCategory.INTERACTION],
    )


@pytest.fixture
def mixed_consent_cache(
    sample_temporary_consent, sample_permanent_consent, sample_decaying_consent, expired_temporary_consent
):
    """Create a mixed cache with various consent types."""
    return {
        sample_temporary_consent.user_id: sample_temporary_consent,
        sample_permanent_consent.user_id: sample_permanent_consent,
        sample_decaying_consent.user_id: sample_decaying_consent,
        expired_temporary_consent.user_id: expired_temporary_consent,
    }


@pytest.fixture
def sample_consent_node_temporary(mock_time_service):
    """Create a sample temporary consent graph node."""
    return GraphNode(
        id="consent_temp_123",
        type=NodeType.CONCEPT,
        scope=GraphScope.IDENTITY,
        attributes={
            "service": "consent",
            "user_id": "temp_user_123",
            "stream": ConsentStream.TEMPORARY.value,
            "expires_at": (mock_time_service.now() + timedelta(days=14)).isoformat(),
            "attribution_count": 5,
            "impact_score": 0.7,
            "categories": ["interaction", "preference"],
        },
        updated_by="consent_service",
        updated_at=mock_time_service.now(),
    )


@pytest.fixture
def sample_consent_node_permanent(mock_time_service):
    """Create a sample permanent consent graph node."""
    return GraphNode(
        id="consent_perm_456",
        type=NodeType.CONCEPT,
        scope=GraphScope.IDENTITY,
        attributes={
            "service": "consent",
            "user_id": "perm_user_456",
            "stream": ConsentStream.PERMANENT.value,
            # No expires_at for permanent consents
            "attribution_count": 25,
            "impact_score": 0.95,
            "categories": ["preference", "research"],
        },
        updated_by="consent_service",
        updated_at=mock_time_service.now(),
    )


@pytest.fixture
def sample_consent_node_expired(mock_time_service):
    """Create a sample expired consent graph node."""
    return GraphNode(
        id="consent_expired_001",
        type=NodeType.CONCEPT,
        scope=GraphScope.IDENTITY,
        attributes={
            "service": "consent",
            "user_id": "expired_user_001",
            "stream": ConsentStream.TEMPORARY.value,
            "expires_at": (mock_time_service.now() - timedelta(days=5)).isoformat(),
            "attribution_count": 3,
            "impact_score": 0.4,
            "categories": ["interaction"],
        },
        updated_by="consent_service",
        updated_at=mock_time_service.now() - timedelta(days=10),
    )


@pytest.fixture
def mixed_consent_nodes(sample_consent_node_temporary, sample_consent_node_permanent, sample_consent_node_expired):
    """Create a list of mixed consent nodes for testing."""
    return [sample_consent_node_temporary, sample_consent_node_permanent, sample_consent_node_expired]


@pytest.fixture
def sample_user_interaction_nodes(mock_time_service):
    """Create sample user interaction nodes for metrics testing."""
    base_time = mock_time_service.now()
    return [
        GraphNode(
            id="interaction_001",
            type=NodeType.INTERACTION,
            scope=GraphScope.COMMUNITY,  # Fixed: SOCIAL doesn't exist, use COMMUNITY
            attributes={
                "user_id": "temp_user_123",
                "interaction_type": "message",
                "content": "Great feedback!",
                "timestamp": base_time.isoformat(),
            },
            updated_by="system",
            updated_at=base_time,
        ),
        GraphNode(
            id="interaction_002",
            type=NodeType.INTERACTION,
            scope=GraphScope.COMMUNITY,  # Fixed: SOCIAL doesn't exist, use COMMUNITY
            attributes={
                "user_id": "temp_user_123",
                "interaction_type": "reaction",
                "content": "👍",
                "timestamp": (base_time - timedelta(hours=2)).isoformat(),
            },
            updated_by="system",
            updated_at=base_time - timedelta(hours=2),
        ),
    ]


@pytest.fixture
def sample_user_contribution_nodes(mock_time_service):
    """Create sample user contribution nodes for metrics testing."""
    base_time = mock_time_service.now()
    return [
        GraphNode(
            id="contribution_001",
            type=NodeType.CONCEPT,
            scope=GraphScope.BEHAVIORAL,
            attributes={
                "contributor_id": "temp_user_123",
                "description": "Suggested improvement to user interface",
                "impact": "high",
                "timestamp": base_time.isoformat(),
            },
            updated_by="pattern_detector",
            updated_at=base_time,
        ),
        GraphNode(
            id="contribution_002",
            type=NodeType.CONCEPT,
            scope=GraphScope.BEHAVIORAL,
            attributes={
                "contributor_id": "temp_user_123",
                "description": "Identified bug in processing logic",
                "impact": "medium",
                "timestamp": (base_time - timedelta(days=1)).isoformat(),
            },
            updated_by="pattern_detector",
            updated_at=base_time - timedelta(days=1),
        ),
    ]


@pytest.fixture
def sample_audit_nodes(mock_time_service):
    """Create sample consent audit nodes."""
    base_time = mock_time_service.now()
    return [
        GraphNode(
            id="audit_001",
            type=NodeType.AUDIT,
            scope=GraphScope.IDENTITY,
            attributes={
                "user_id": "temp_user_123",
                "service": "consent",
                "action": "consent_granted",
                "details": {"stream": "temporary", "categories": ["feedback"]},
                "timestamp": base_time.isoformat(),
            },
            updated_by="consent_service",
            updated_at=base_time,
        ),
        GraphNode(
            id="audit_002",
            type=NodeType.AUDIT,
            scope=GraphScope.IDENTITY,
            attributes={
                "user_id": "temp_user_123",
                "service": "consent",
                "action": "consent_updated",
                "details": {"stream": "temporary", "new_categories": ["feedback", "participation"]},
                "timestamp": (base_time - timedelta(hours=6)).isoformat(),
            },
            updated_by="consent_service",
            updated_at=base_time - timedelta(hours=6),
        ),
    ]


@pytest.fixture
def malformed_consent_nodes(mock_time_service):
    """Create malformed consent nodes for error handling testing."""
    return [
        # Node without attributes
        GraphNode(
            id="malformed_001",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes=None,
            updated_by="test",
            updated_at=mock_time_service.now(),
        ),
        # Node with invalid date format
        GraphNode(
            id="malformed_002",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                "user_id": "bad_date_user",
                "stream": ConsentStream.TEMPORARY.value,
                "expires_at": "not-a-date",
            },
            updated_by="test",
            updated_at=mock_time_service.now(),
        ),
        # Node missing required fields
        GraphNode(
            id="malformed_003",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                # Missing user_id and stream
                "expires_at": mock_time_service.now().isoformat(),
            },
            updated_by="test",
            updated_at=mock_time_service.now(),
        ),
    ]


@pytest.fixture
def populated_consent_service(consent_service_with_mocks, mixed_consent_cache):
    """Create a consent service pre-populated with test data."""
    consent_service_with_mocks._consent_cache = mixed_consent_cache.copy()
    return consent_service_with_mocks


# ============================================================================
# Decay Protocol Fixtures
# ============================================================================


@pytest.fixture
def sample_decay_status(mock_time_service):
    """Create a sample decay status for testing."""
    now = mock_time_service.now()
    return ConsentDecayStatus(
        user_id="decay_user_001",
        decay_started=now,
        identity_severed=False,
        patterns_anonymized=False,
        decay_complete_at=now + timedelta(days=90),
        safety_patterns_retained=0,
    )


@pytest.fixture
def sample_decay_identity_severed(mock_time_service):
    """Create a decay status with identity severed."""
    now = mock_time_service.now()
    return ConsentDecayStatus(
        user_id="decay_user_002",
        decay_started=now - timedelta(days=1),
        identity_severed=True,
        patterns_anonymized=False,
        decay_complete_at=now + timedelta(days=89),
        safety_patterns_retained=0,
    )


@pytest.fixture
def sample_decay_completed(mock_time_service):
    """Create a completed decay status."""
    now = mock_time_service.now()
    return ConsentDecayStatus(
        user_id="decay_user_003",
        decay_started=now - timedelta(days=90),
        identity_severed=True,
        patterns_anonymized=True,
        decay_complete_at=now,
        safety_patterns_retained=5,
    )


@pytest.fixture
def decay_protocol_manager(mock_time_service):
    """Create a decay protocol manager for testing."""
    return DecayProtocolManager(time_service=mock_time_service)


# ============================================================================
# Partnership Fixtures
# ============================================================================


@pytest.fixture
def sample_partnership_request(mock_time_service):
    """Create a sample partnership request."""
    from ciris_engine.schemas.consent.core import PartnershipAgingStatus, PartnershipPriority

    now = mock_time_service.now()
    return PartnershipRequest(
        user_id="partnership_user_001",
        task_id="task_001",
        categories=[ConsentCategory.PREFERENCE, ConsentCategory.RESEARCH],
        reason="Want to collaborate on improving the system",
        channel_id="channel_123",
        created_at=now - timedelta(hours=2),
        age_hours=2.0,
        aging_status=PartnershipAgingStatus.NORMAL,
        priority=PartnershipPriority.NORMAL,
    )


@pytest.fixture
def sample_partnership_outcome_approved(mock_time_service):
    """Create an approved partnership outcome."""
    return PartnershipOutcome(
        user_id="partnership_user_001",
        outcome=PartnershipOutcomeType.APPROVED,
        decided_at=mock_time_service.now(),
        reason="User has been helpful and engaged",
    )


@pytest.fixture
def sample_partnership_outcome_rejected(mock_time_service):
    """Create a rejected partnership outcome."""
    return PartnershipOutcome(
        user_id="partnership_user_002",
        outcome=PartnershipOutcomeType.REJECTED,
        decided_at=mock_time_service.now(),
        reason="Insufficient engagement history",
    )


@pytest.fixture
def sample_partnership_outcome_deferred(mock_time_service):
    """Create a deferred partnership outcome."""
    return PartnershipOutcome(
        user_id="partnership_user_003",
        outcome=PartnershipOutcomeType.DEFERRED,
        decided_at=mock_time_service.now(),
        reason="Need more interaction time",
    )


@pytest.fixture
def partnership_manager(mock_time_service):
    """Create a partnership manager for testing."""
    return PartnershipManager(time_service=mock_time_service)


@pytest.fixture
def pending_partnership_data(mock_time_service):
    """Create sample pending partnership data structure."""
    return {
        "partnership_user_001": {
            "task_id": "task_001",
            "request": {
                "user_id": "partnership_user_001",
                "categories": ["preference", "research"],
                "reason": "Want to collaborate",
                "channel_id": "channel_123",
            },
            "created_at": mock_time_service.now().isoformat(),
            "channel_id": "channel_123",
        }
    }


# ============================================================================
# DSAR Automation Fixtures
# ============================================================================


@pytest.fixture
def dsar_automation_service(mock_time_service, mock_memory_bus, consent_service_with_mocks):
    """Create a DSAR automation service for testing."""
    return DSARAutomationService(
        time_service=mock_time_service, consent_service=consent_service_with_mocks, memory_bus=mock_memory_bus
    )


@pytest.fixture
def sample_conversation_summary_node(mock_time_service):
    """Create a sample conversation summary node for DSAR testing."""
    return GraphNode(
        id="conv_summary_001",
        type=NodeType.CONCEPT,
        scope=GraphScope.COMMUNITY,  # Fixed: SOCIAL doesn't exist, use COMMUNITY
        attributes={
            "channel_id": "channel_123",
            "participants": {
                "temp_user_123": {"message_count": 25, "last_active": mock_time_service.now().isoformat()},
                "other_user_456": {"message_count": 15, "last_active": mock_time_service.now().isoformat()},
            },
            "timestamp": mock_time_service.now().isoformat(),
        },
        updated_by="conversation_tracker",
        updated_at=mock_time_service.now(),
    )


@pytest.fixture
def sample_conversation_summary_nodes_multiple(mock_time_service):
    """Create multiple conversation summary nodes for testing aggregation."""
    base_time = mock_time_service.now()
    return [
        GraphNode(
            id="conv_summary_001",
            type=NodeType.CONCEPT,
            scope=GraphScope.COMMUNITY,  # Fixed: SOCIAL doesn't exist, use COMMUNITY
            attributes={
                "channel_id": "channel_123",
                "participants": {
                    "temp_user_123": {"message_count": 25},
                    "other_user_456": {"message_count": 15},
                },
            },
            updated_by="conversation_tracker",
            updated_at=base_time,
        ),
        GraphNode(
            id="conv_summary_002",
            type=NodeType.CONCEPT,
            scope=GraphScope.COMMUNITY,  # Fixed: SOCIAL doesn't exist, use COMMUNITY
            attributes={
                "channel_id": "channel_456",
                "participants": {
                    "temp_user_123": {"message_count": 10},
                    "other_user_789": {"message_count": 8},
                },
            },
            updated_by="conversation_tracker",
            updated_at=base_time - timedelta(days=1),
        ),
        GraphNode(
            id="conv_summary_003",
            type=NodeType.CONCEPT,
            scope=GraphScope.COMMUNITY,  # Fixed: SOCIAL doesn't exist, use COMMUNITY
            attributes={
                "channel_id": "channel_123",
                "participants": {
                    "temp_user_123": {"message_count": 5},
                },
            },
            updated_by="conversation_tracker",
            updated_at=base_time - timedelta(days=2),
        ),
    ]


# ============================================================================
# AIR (Artificial Interaction Reminder) Fixtures
# ============================================================================


@pytest.fixture
def air_service(mock_time_service):
    """Create an AIR service for testing."""
    return ArtificialInteractionReminder(time_service=mock_time_service)


@pytest.fixture
def sample_air_interaction_session():
    """Create a sample AIR interaction session tracking data."""
    return {
        "user_001": {
            "total_interactions": 150,
            "one_on_one_count": 45,
            "last_reminder_at": None,
            "reminders_sent": 0,
        },
        "user_002": {
            "total_interactions": 80,
            "one_on_one_count": 10,
            "last_reminder_at": None,
            "reminders_sent": 0,
        },
    }


@pytest.fixture
def sample_air_high_engagement():
    """Create AIR data for user with high 1:1 engagement (should trigger reminder)."""
    return {
        "user_high_engagement": {
            "total_interactions": 200,
            "one_on_one_count": 150,  # 75% - high parasocial risk
            "last_reminder_at": None,
            "reminders_sent": 0,
        }
    }


# ============================================================================
# Metrics Collection Fixtures
# ============================================================================


@pytest.fixture
def sample_partnership_counters():
    """Create sample partnership counters for metrics testing."""
    return PartnershipCounters(requests=10, approvals=7, rejections=2, pending_count=1)


@pytest.fixture
def sample_decay_counters():
    """Create sample decay counters for metrics testing."""
    return DecayCounters(total_initiated=15, completed=12, active_count=3)


@pytest.fixture
def sample_operational_counters():
    """Create sample operational counters for metrics testing."""
    return OperationalCounters(
        consent_checks=500, consent_grants=100, consent_revokes=25, expired_cleanups=10, tool_executions=200, tool_failures=5
    )


@pytest.fixture
def metrics_collector():
    """Create a metrics collector for testing."""
    return ConsentMetricsCollector()


@pytest.fixture
def comprehensive_counters(sample_partnership_counters, sample_decay_counters, sample_operational_counters):
    """Create a complete set of counters for comprehensive metrics testing."""
    return {
        "partnership": sample_partnership_counters,
        "decay": sample_decay_counters,
        "operational": sample_operational_counters,
    }
