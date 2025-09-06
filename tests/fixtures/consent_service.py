"""
Test fixtures for ConsentService testing.

Provides reusable fixtures for testing the consent service functionality.
"""

import pytest
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional
from unittest.mock import AsyncMock, Mock

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.governance.consent import ConsentService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.consent.core import ConsentStatus, ConsentStream, ConsentCategory
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
    service = ConsentService(
        time_service=mock_time_service,
        memory_bus=mock_memory_bus,
        db_path=None
    )
    return service


@pytest.fixture
def consent_service_without_memory_bus(mock_time_service):
    """Create a consent service without memory bus (cache-only mode)."""
    service = ConsentService(
        time_service=mock_time_service,
        memory_bus=None,
        db_path=None
    )
    return service


@pytest.fixture
def sample_temporary_consent(mock_time_service):
    """Create a sample temporary consent status."""
    return ConsentStatus(
        user_id="temp_user_123",
        stream=ConsentStream.TEMPORARY,
        expires_at=mock_time_service.now() + timedelta(days=14),
        attribution_count=5,
        impact_score=0.7,
        categories=[ConsentCategory.FEEDBACK, ConsentCategory.PARTICIPATION]
    )


@pytest.fixture
def sample_permanent_consent():
    """Create a sample permanent consent status."""
    return ConsentStatus(
        user_id="perm_user_456",
        stream=ConsentStream.PERMANENT,
        expires_at=None,
        attribution_count=25,
        impact_score=0.95,
        categories=[ConsentCategory.PARTNERSHIP, ConsentCategory.ANALYTICS]
    )


@pytest.fixture
def sample_decaying_consent(mock_time_service):
    """Create a sample decaying consent status."""
    return ConsentStatus(
        user_id="decay_user_789",
        stream=ConsentStream.DECAYING,
        expires_at=mock_time_service.now() + timedelta(days=90),
        attribution_count=12,
        impact_score=0.85,
        categories=[ConsentCategory.IMPROVEMENT, ConsentCategory.FEEDBACK]
    )


@pytest.fixture
def expired_temporary_consent(mock_time_service):
    """Create an expired temporary consent status."""
    return ConsentStatus(
        user_id="expired_user_001",
        stream=ConsentStream.TEMPORARY, 
        expires_at=mock_time_service.now() - timedelta(days=5),  # Expired 5 days ago
        attribution_count=3,
        impact_score=0.4,
        categories=[ConsentCategory.FEEDBACK]
    )


@pytest.fixture
def mixed_consent_cache(sample_temporary_consent, sample_permanent_consent, 
                       sample_decaying_consent, expired_temporary_consent):
    """Create a mixed cache with various consent types."""
    return {
        sample_temporary_consent.user_id: sample_temporary_consent,
        sample_permanent_consent.user_id: sample_permanent_consent,
        sample_decaying_consent.user_id: sample_decaying_consent,
        expired_temporary_consent.user_id: expired_temporary_consent
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
            "categories": ["feedback", "participation"]
        },
        updated_by="consent_service",
        updated_at=mock_time_service.now()
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
            "categories": ["partnership", "analytics"]
        },
        updated_by="consent_service",
        updated_at=mock_time_service.now()
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
            "categories": ["feedback"]
        },
        updated_by="consent_service",
        updated_at=mock_time_service.now() - timedelta(days=10)
    )


@pytest.fixture
def mixed_consent_nodes(sample_consent_node_temporary, sample_consent_node_permanent,
                       sample_consent_node_expired):
    """Create a list of mixed consent nodes for testing."""
    return [
        sample_consent_node_temporary,
        sample_consent_node_permanent, 
        sample_consent_node_expired
    ]


@pytest.fixture
def sample_user_interaction_nodes(mock_time_service):
    """Create sample user interaction nodes for metrics testing."""
    base_time = mock_time_service.now()
    return [
        GraphNode(
            id="interaction_001",
            type=NodeType.INTERACTION,
            scope=GraphScope.SOCIAL,
            attributes={
                "user_id": "temp_user_123",
                "interaction_type": "message",
                "content": "Great feedback!",
                "timestamp": base_time.isoformat()
            },
            updated_by="system",
            updated_at=base_time
        ),
        GraphNode(
            id="interaction_002", 
            type=NodeType.INTERACTION,
            scope=GraphScope.SOCIAL,
            attributes={
                "user_id": "temp_user_123",
                "interaction_type": "reaction", 
                "content": "👍",
                "timestamp": (base_time - timedelta(hours=2)).isoformat()
            },
            updated_by="system",
            updated_at=base_time - timedelta(hours=2)
        )
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
                "timestamp": base_time.isoformat()
            },
            updated_by="pattern_detector",
            updated_at=base_time
        ),
        GraphNode(
            id="contribution_002",
            type=NodeType.CONCEPT, 
            scope=GraphScope.BEHAVIORAL,
            attributes={
                "contributor_id": "temp_user_123",
                "description": "Identified bug in processing logic",
                "impact": "medium",
                "timestamp": (base_time - timedelta(days=1)).isoformat()
            },
            updated_by="pattern_detector",
            updated_at=base_time - timedelta(days=1)
        )
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
                "timestamp": base_time.isoformat()
            },
            updated_by="consent_service",
            updated_at=base_time
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
                "timestamp": (base_time - timedelta(hours=6)).isoformat()
            },
            updated_by="consent_service",
            updated_at=base_time - timedelta(hours=6)
        )
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
            updated_at=mock_time_service.now()
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
                "expires_at": "not-a-date"
            },
            updated_by="test",
            updated_at=mock_time_service.now()
        ),
        # Node missing required fields
        GraphNode(
            id="malformed_003",
            type=NodeType.CONCEPT,
            scope=GraphScope.IDENTITY,
            attributes={
                "service": "consent",
                # Missing user_id and stream
                "expires_at": mock_time_service.now().isoformat()
            },
            updated_by="test", 
            updated_at=mock_time_service.now()
        )
    ]


@pytest.fixture
def populated_consent_service(consent_service_with_mocks, mixed_consent_cache):
    """Create a consent service pre-populated with test data."""
    consent_service_with_mocks._consent_cache = mixed_consent_cache.copy()
    return consent_service_with_mocks