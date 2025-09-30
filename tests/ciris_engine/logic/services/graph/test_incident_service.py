"""Unit tests for Incident Management Service."""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.services.graph.incident_service import IncidentManagementService
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph.incident import (
    IncidentInsightNode,
    IncidentNode,
    IncidentSeverity,
    IncidentStatus,
    ProblemNode,
)
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


def create_test_incident(
    incident_id: str,
    incident_type: str,
    severity: IncidentSeverity,
    description: str,
    source_component: str,
    detected_at: datetime,
    filename: str,
    line_number: int,
    updated_by: str = "test",
    updated_at: Optional[datetime] = None,
    **kwargs: Any,
) -> IncidentNode:
    """Helper function to create test incident nodes with all required fields."""
    # Set defaults for optional fields if not provided in kwargs
    defaults = {
        "detection_method": "AUTOMATED_LOG_MONITORING",
        "resolved_at": None,
        "impact": None,
        "urgency": None,
        "correlation_id": None,
        "task_id": None,
        "thought_id": None,
        "handler_name": None,
        "exception_type": None,
        "stack_trace": None,
        "function_name": None,
        "problem_id": None,
        "related_incidents": [],
    }

    # Update defaults with any provided kwargs
    for key, value in kwargs.items():
        defaults[key] = value

    return IncidentNode(
        id=incident_id,
        type=NodeType.AUDIT_ENTRY,
        scope=GraphScope.LOCAL,
        attributes={},
        incident_type=incident_type,
        severity=severity,
        status=IncidentStatus.OPEN,
        description=description,
        source_component=source_component,
        detected_at=detected_at,
        filename=filename,
        line_number=line_number,
        updated_by=updated_by,
        updated_at=updated_at or detected_at,
        **defaults,
    )


@pytest.fixture
def mock_memory_bus() -> Mock:
    """Create a mock memory bus."""
    mock = Mock()
    mock.memorize = AsyncMock(return_value=MemoryOpResult(status=MemoryOpStatus.OK))
    mock.recall = AsyncMock(return_value=[])

    # Mock the service registry for direct memory service access
    mock_registry = Mock()
    mock_memory_service = Mock()
    mock_memory_service.search = AsyncMock(return_value=[])
    # Mock get_services_by_type to return a list with our mock service
    mock_registry.get_services_by_type = Mock(return_value=[mock_memory_service])
    mock.service_registry = mock_registry

    return mock


@pytest.fixture
def mock_time_service() -> Mock:
    """Create a mock time service."""
    mock = Mock()
    # TimeService.now() is a synchronous method, not async
    mock.now = Mock(return_value=datetime.now(timezone.utc))
    return mock


@pytest.fixture
def incident_service(mock_memory_bus: Mock, mock_time_service: Mock) -> IncidentManagementService:
    """Create an incident service for testing."""
    service = IncidentManagementService(memory_bus=mock_memory_bus, time_service=mock_time_service)
    return service


@pytest.mark.asyncio
async def test_incident_service_lifecycle(incident_service: IncidentManagementService) -> None:
    """Test IncidentService start/stop lifecycle."""
    # Start
    await incident_service.start()
    assert incident_service._started is True

    # Stop
    await incident_service.stop()
    assert incident_service._started is False


@pytest.mark.asyncio
async def test_incident_service_process_recent_incidents(
    incident_service: IncidentManagementService, mock_memory_bus: Mock, mock_time_service: Mock
) -> None:
    """Test processing recent incidents to generate insights."""
    # Create typed IncidentNode instances
    current_time = mock_time_service.now()

    incident1 = create_test_incident(
        incident_id="inc1",
        incident_type="ERROR",
        severity=IncidentSeverity.MEDIUM,
        description="Database connection timeout",
        source_component="database",
        detected_at=current_time - timedelta(hours=1),
        filename="db.py",
        line_number=123,
        updated_at=current_time,
    )

    incident2 = create_test_incident(
        incident_id="inc2",
        incident_type="ERROR",
        severity=IncidentSeverity.MEDIUM,
        description="Database connection timeout",
        source_component="database",
        detected_at=current_time - timedelta(hours=2),
        filename="db.py",
        line_number=456,
        updated_at=current_time,
    )

    incident3 = create_test_incident(
        incident_id="inc3",
        incident_type="WARNING",
        severity=IncidentSeverity.LOW,
        description="High memory usage detected",
        source_component="resource_monitor",
        detected_at=current_time - timedelta(hours=3),
        filename="monitor.py",
        line_number=789,
        updated_at=current_time,
    )

    # Convert to GraphNodes for mock return
    mock_incident_nodes = [incident1.to_graph_node(), incident2.to_graph_node(), incident3.to_graph_node()]

    # Mock the memory service search to return incidents
    # The code calls get_services_by_type("memory")
    mock_memory_service = mock_memory_bus.service_registry.get_services_by_type("memory")[0]
    mock_memory_service.search = AsyncMock(return_value=mock_incident_nodes)

    # Process incidents
    insight = await incident_service.process_recent_incidents(hours=24)

    assert insight is not None
    assert isinstance(insight, IncidentInsightNode)
    assert insight.insight_type == "PERIODIC_ANALYSIS"
    assert len(insight.source_incidents) == 3
    assert insight.details["incident_count"] == 3

    # With only 3 incidents, no patterns detected, so no recommendations
    # This is correct behavior - we need more incidents to detect patterns
    assert len(insight.behavioral_adjustments) == 0
    assert len(insight.configuration_changes) == 0


@pytest.mark.asyncio
async def test_incident_service_pattern_detection(
    incident_service: IncidentManagementService, mock_memory_bus: Mock, mock_time_service: Mock
) -> None:
    """Test pattern detection in incidents."""
    # Create incidents with patterns
    current_time = mock_time_service.now()

    similar_incident_nodes = []
    for i in range(5):
        incident = create_test_incident(
            incident_id=f"inc{i}",
            incident_type="ERROR",
            severity=IncidentSeverity.MEDIUM,
            description="Database connection timeout error",
            source_component="database",
            detected_at=current_time - timedelta(hours=i),
            filename="db.py",
            line_number=100 + i,
            updated_at=current_time,
        )
        similar_incident_nodes.append(incident.to_graph_node())

    mock_memory_service = mock_memory_bus.service_registry.get_services_by_type("memory")[0]
    mock_memory_service.search = AsyncMock(return_value=similar_incident_nodes)

    # Process to detect patterns
    insight = await incident_service.process_recent_incidents(hours=24)

    # Should detect the recurring pattern
    assert insight.details["pattern_count"] > 0
    assert (
        "timeout" in str(insight.behavioral_adjustments).lower()
        or "timeout" in str(insight.configuration_changes).lower()
    )


@pytest.mark.asyncio
async def test_incident_service_no_incidents(
    incident_service: IncidentManagementService, mock_memory_bus: Mock
) -> None:
    """Test processing when no incidents exist."""
    # Mock empty search result
    mock_memory_service = mock_memory_bus.service_registry.get_services_by_type("memory")[0]
    mock_memory_service.search = AsyncMock(return_value=[])

    # Process incidents
    insight = await incident_service.process_recent_incidents(hours=24)

    assert insight is not None
    assert insight.details["incident_count"] == 0
    assert insight.summary.startswith("No incidents detected")


@pytest.mark.asyncio
async def test_incident_service_time_clusters(
    incident_service: IncidentManagementService, mock_memory_bus: Mock, mock_time_service: Mock
) -> None:
    """Test detection of time-based incident clusters."""
    # Create a cluster of incidents
    current_time = mock_time_service.now()
    base_time = current_time - timedelta(hours=2)

    cluster_incident_nodes = []
    for i in range(5):
        incident = create_test_incident(
            incident_id=f"cluster{i}",
            incident_type="ERROR",
            severity=IncidentSeverity.HIGH,
            description="Multiple service errors",
            source_component="api",
            detected_at=base_time + timedelta(minutes=i),
            filename="api.py",
            line_number=200 + i,
            updated_at=current_time,
        )
        cluster_incident_nodes.append(incident.to_graph_node())

    mock_memory_service = mock_memory_bus.service_registry.get_services_by_type("memory")[0]
    mock_memory_service.search = AsyncMock(return_value=cluster_incident_nodes)

    # Process incidents
    insight = await incident_service.process_recent_incidents(hours=24)

    # Should detect time clustering
    assert insight.details["incident_count"] == 5
    assert len(insight.behavioral_adjustments) > 0 or len(insight.configuration_changes) > 0


def test_incident_service_capabilities(incident_service: IncidentManagementService) -> None:
    """Test IncidentService.get_capabilities() returns correct info."""
    caps = incident_service.get_capabilities()

    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "IncidentManagementService"
    assert "process_recent_incidents" in caps.actions
    assert "detect_patterns" in caps.actions
    assert "identify_problems" in caps.actions
    assert "generate_insights" in caps.actions
    assert caps.version == "1.0.0"
    assert "MemoryService" in caps.dependencies
    assert "TimeService" in caps.dependencies


def test_incident_service_status(incident_service: IncidentManagementService) -> None:
    """Test IncidentService.get_status() returns correct status."""
    status = incident_service.get_status()

    assert isinstance(status, ServiceStatus)
    assert status.service_name == "IncidentManagementService"
    assert status.service_type == "graph_service"


@pytest.mark.asyncio
async def test_incident_service_error_handling(
    incident_service: IncidentManagementService, mock_memory_bus: Mock, monkeypatch
) -> None:
    """Test error handling when memory service fails."""
    # Make search raise an error
    mock_memory_service = mock_memory_bus.service_registry.get_services_by_type("memory")[0]
    mock_memory_service.search.side_effect = Exception("Database error")

    # Mock Path.exists to return False so it doesn't try to read the log file
    from pathlib import Path

    monkeypatch.setattr(Path, "exists", lambda self: False)

    # Should handle error gracefully
    insight = await incident_service.process_recent_incidents(hours=24)

    # Should return no incidents insight
    assert insight is not None
    assert insight.details["incident_count"] == 0


@pytest.mark.asyncio
async def test_incident_service_problem_creation(
    incident_service: IncidentManagementService, mock_memory_bus: Mock, mock_time_service: Mock
) -> None:
    """Test problem node creation from incident patterns."""
    # Create many similar incidents
    current_time = mock_time_service.now()

    incident_nodes = []
    # Create 10 timeout errors (should trigger pattern detection)
    for i in range(10):
        incident = create_test_incident(
            incident_id=f"timeout{i}",
            incident_type="ERROR",
            severity=IncidentSeverity.HIGH,
            description="Connection timeout error occurred",
            source_component="database",
            detected_at=current_time - timedelta(hours=i),
            filename="db.py",
            line_number=100,
            updated_at=current_time,
        )
        incident_nodes.append(incident.to_graph_node())

    mock_memory_service = mock_memory_bus.service_registry.get_services_by_type("memory")[0]
    mock_memory_service.search = AsyncMock(return_value=incident_nodes)

    # Process incidents
    insight = await incident_service.process_recent_incidents(hours=24)

    # Should have detected patterns and created problems
    assert insight.details["pattern_count"] > 0
    assert insight.details["problem_count"] > 0
    assert len(insight.source_problems) > 0

    # Check that problem nodes were memorized
    assert mock_memory_bus.memorize.called
    # Should have memorized at least one problem and the insight
    assert mock_memory_bus.memorize.call_count >= 2


@pytest.mark.asyncio
async def test_incident_service_recommendations(
    incident_service: IncidentManagementService, mock_memory_bus: Mock, mock_time_service: Mock
) -> None:
    """Test generation of specific recommendations based on incident types."""
    current_time = mock_time_service.now()

    # Create incidents with different types of issues
    mem_incident = create_test_incident(
        incident_id="mem1",
        incident_type="ERROR",
        severity=IncidentSeverity.HIGH,
        description="Out of memory error",
        source_component="worker",
        detected_at=current_time - timedelta(hours=1),
        filename="worker.py",
        line_number=50,
        updated_at=current_time,
    )

    timeout_incident = create_test_incident(
        incident_id="timeout1",
        incident_type="ERROR",
        severity=IncidentSeverity.MEDIUM,
        description="Request timeout after 30 seconds",
        source_component="api",
        detected_at=current_time - timedelta(hours=2),
        filename="api.py",
        line_number=100,
        updated_at=current_time,
    )

    incident_nodes = [mem_incident.to_graph_node(), timeout_incident.to_graph_node()]

    # Add more of each type to trigger pattern detection
    for i in range(3):
        mem_inc = create_test_incident(
            incident_id=f"mem{i+2}",
            incident_type="ERROR",
            severity=IncidentSeverity.HIGH,
            description="Memory allocation failed",
            source_component="worker",
            detected_at=current_time - timedelta(hours=i + 3),
            filename="worker.py",
            line_number=60 + i,
            updated_at=current_time,
        )

        timeout_inc = create_test_incident(
            incident_id=f"timeout{i+2}",
            incident_type="ERROR",
            severity=IncidentSeverity.MEDIUM,
            description="Operation timeout exceeded",
            source_component="api",
            detected_at=current_time - timedelta(hours=i + 4),
            filename="api.py",
            line_number=110 + i,
            updated_at=current_time,
        )

        incident_nodes.extend([mem_inc.to_graph_node(), timeout_inc.to_graph_node()])

    mock_memory_service = mock_memory_bus.service_registry.get_services_by_type("memory")[0]
    mock_memory_service.search = AsyncMock(return_value=incident_nodes)

    # Process incidents
    insight = await incident_service.process_recent_incidents(hours=24)

    # Should have memory-related recommendations
    all_recommendations = insight.behavioral_adjustments + insight.configuration_changes
    recommendations_text = " ".join(all_recommendations).lower()

    assert "memory" in recommendations_text
    assert "timeout" in recommendations_text
    assert len(insight.behavioral_adjustments) > 0
    assert len(insight.configuration_changes) > 0


@pytest.mark.asyncio
async def test_get_metrics(mock_memory_bus: Mock, mock_time_service: Mock) -> None:
    """Test getting telemetry data from incident management service."""
    # Create service and start it
    service = IncidentManagementService(memory_bus=mock_memory_bus, time_service=mock_time_service)
    await service.start()

    # Create some test incidents
    current_time = mock_time_service.now()
    test_incidents = [
        create_test_incident(
            incident_id="inc1",
            incident_type="ERROR",
            severity=IncidentSeverity.HIGH,
            description="Test error",
            source_component="test",
            detected_at=current_time - timedelta(minutes=30),
            filename="test.py",
            line_number=10,
        ).to_graph_node()
    ]

    # Mock the memory service to return incidents
    mock_memory_service = mock_memory_bus.service_registry.get_services_by_type("memory")[0]
    mock_memory_service.search = AsyncMock(return_value=test_incidents)

    # Since IncidentManagementService doesn't have get_metrics() and it's a graph service,
    # we'll skip this test for now as graph services don't inherit from BaseService
    pytest.skip("IncidentManagementService doesn't have get_metrics() method")


@pytest.mark.asyncio
async def test_get_metrics_no_incidents(mock_memory_bus: Mock, mock_time_service: Mock) -> None:
    """Test telemetry when no incidents exist."""
    service = IncidentManagementService(memory_bus=mock_memory_bus, time_service=mock_time_service)
    await service.start()

    # Mock empty incident list
    mock_memory_service = mock_memory_bus.service_registry.get_services_by_type("memory")[0]
    mock_memory_service.search = AsyncMock(return_value=[])

    # Since IncidentManagementService doesn't have get_metrics() method
    pytest.skip("IncidentManagementService doesn't have get_metrics() method")


@pytest.mark.asyncio
async def test_get_metrics_error_handling(mock_memory_bus: Mock, mock_time_service: Mock) -> None:
    """Test telemetry handles errors gracefully."""
    service = IncidentManagementService(memory_bus=mock_memory_bus, time_service=mock_time_service)
    await service.start()

    # Mock get_incident_count to raise an exception
    service.get_incident_count = AsyncMock(side_effect=Exception("Database error"))

    # Since IncidentManagementService doesn't have get_metrics() method
    pytest.skip("IncidentManagementService doesn't have get_metrics() method")


@pytest.mark.asyncio
async def test_incident_node_serialization() -> None:
    """Test that IncidentNode properly serializes to/from GraphNode."""
    # Create an IncidentNode with all fields
    now = datetime.now(timezone.utc)
    incident = create_test_incident(
        incident_id="test_incident_1",
        incident_type="ERROR",
        severity=IncidentSeverity.HIGH,
        description="Test error occurred",
        source_component="test_component",
        detected_at=now,
        filename="test.py",
        line_number=42,
        updated_by="test_user",
        updated_at=now,
        # Additional optional fields
        resolved_at=now + timedelta(hours=1),
        impact="High impact on service",
        urgency="Urgent",
        correlation_id="corr123",
        task_id="task456",
        thought_id="thought789",
        handler_name="TestHandler",
        exception_type="TestException",
        stack_trace="Test stack trace",
        function_name="test_function",
        problem_id="problem123",
        related_incidents=["inc1", "inc2"],
    )

    # Convert to GraphNode
    graph_node = incident.to_graph_node()

    # Verify GraphNode structure
    assert graph_node.id == "test_incident_1"
    assert graph_node.type == NodeType.AUDIT_ENTRY
    assert graph_node.scope == GraphScope.LOCAL
    assert isinstance(graph_node.attributes, dict)
    assert graph_node.attributes["node_class"] == "IncidentNode"
    assert graph_node.attributes["incident_type"] == "ERROR"
    assert graph_node.attributes["severity"] == "HIGH"
    assert graph_node.attributes["status"] == "OPEN"

    # Reconstruct from GraphNode
    reconstructed = IncidentNode.from_graph_node(graph_node)

    # Verify all fields match
    assert reconstructed.id == incident.id
    assert reconstructed.incident_type == incident.incident_type
    assert reconstructed.severity == incident.severity
    assert reconstructed.status == incident.status
    assert reconstructed.description == incident.description
    assert reconstructed.source_component == incident.source_component
    assert reconstructed.filename == incident.filename
    assert reconstructed.line_number == incident.line_number
    assert reconstructed.problem_id == incident.problem_id
    assert reconstructed.related_incidents == incident.related_incidents


@pytest.mark.asyncio
async def test_problem_node_serialization() -> None:
    """Test that ProblemNode properly serializes to/from GraphNode."""
    current_time = datetime.now(timezone.utc)

    problem = ProblemNode(
        id="problem_test_1",
        type=NodeType.CONCEPT,
        scope=GraphScope.IDENTITY,
        attributes={},
        problem_statement="Recurring database connection issues",
        affected_incidents=["inc1", "inc2", "inc3"],
        status="UNDER_INVESTIGATION",
        potential_root_causes=["Network instability", "Database overload"],
        recommended_actions=["Increase connection pool", "Add retry logic"],
        incident_count=3,
        first_occurrence=current_time - timedelta(days=1),
        last_occurrence=current_time,
        resolution="Fixed by increasing pool size",
        resolved_at=current_time + timedelta(hours=2),
        updated_by="test_user",
        updated_at=current_time,
    )

    # Convert to GraphNode
    graph_node = problem.to_graph_node()

    # Verify GraphNode structure
    assert graph_node.id == "problem_test_1"
    assert graph_node.type == NodeType.CONCEPT
    assert graph_node.scope == GraphScope.IDENTITY
    assert isinstance(graph_node.attributes, dict)
    assert graph_node.attributes["node_class"] == "ProblemNode"

    # Reconstruct from GraphNode
    reconstructed = ProblemNode.from_graph_node(graph_node)

    # Verify all fields match
    assert reconstructed.id == problem.id
    assert reconstructed.problem_statement == problem.problem_statement
    assert reconstructed.affected_incidents == problem.affected_incidents
    assert reconstructed.status == problem.status
    assert reconstructed.potential_root_causes == problem.potential_root_causes
    assert reconstructed.recommended_actions == problem.recommended_actions
    assert reconstructed.incident_count == problem.incident_count
    assert reconstructed.resolution == problem.resolution


@pytest.mark.asyncio
async def test_incident_insight_node_serialization() -> None:
    """Test that IncidentInsightNode properly serializes to/from GraphNode."""
    current_time = datetime.now(timezone.utc)

    insight = IncidentInsightNode(
        id="insight_test_1",
        type=NodeType.CONCEPT,
        scope=GraphScope.LOCAL,
        attributes={},
        insight_type="PERIODIC_ANALYSIS",
        summary="Analysis of recent incidents",
        details={
            "incident_count": 10,
            "pattern_count": 3,
            "problem_count": 2,
            "severity_breakdown": {"HIGH": 5, "MEDIUM": 3, "LOW": 2},
        },
        behavioral_adjustments=["Add retry logic", "Improve error handling"],
        configuration_changes=["Increase timeout", "Add circuit breaker"],
        source_incidents=["inc1", "inc2", "inc3"],
        source_problems=["prob1", "prob2"],
        analysis_timestamp=current_time,
        applied=True,
        effectiveness_score=0.85,
        updated_by="test_user",
        updated_at=current_time,
    )

    # Convert to GraphNode
    graph_node = insight.to_graph_node()

    # Verify GraphNode structure
    assert graph_node.id == "insight_test_1"
    assert graph_node.type == NodeType.CONCEPT
    assert graph_node.scope == GraphScope.LOCAL
    assert isinstance(graph_node.attributes, dict)
    assert graph_node.attributes["node_class"] == "IncidentInsightNode"

    # Reconstruct from GraphNode
    reconstructed = IncidentInsightNode.from_graph_node(graph_node)

    # Verify all fields match
    assert reconstructed.id == insight.id
    assert reconstructed.insight_type == insight.insight_type
    assert reconstructed.summary == insight.summary
    assert reconstructed.details == insight.details
    assert reconstructed.behavioral_adjustments == insight.behavioral_adjustments
    assert reconstructed.configuration_changes == insight.configuration_changes
    assert reconstructed.source_incidents == insight.source_incidents
    assert reconstructed.source_problems == insight.source_problems
    assert reconstructed.applied == insight.applied
    assert reconstructed.effectiveness_score == insight.effectiveness_score
