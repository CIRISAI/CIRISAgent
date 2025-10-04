"""
Central fixtures for telemetry API testing.

Provides comprehensive, properly-typed mocks for all telemetry endpoint dependencies.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.fixture
def mock_api_telemetry_service():
    """Create a fully-configured telemetry service for API tests."""
    from ciris_engine.schemas.runtime.system_context import TelemetrySummary

    mock = AsyncMock()
    now = datetime.now(timezone.utc)

    # Telemetry summary with all fields
    telemetry_summary = TelemetrySummary(
        window_start=now - timedelta(hours=24),
        window_end=now,
        uptime_seconds=86400.0,
        messages_processed_24h=1000,
        thoughts_processed_24h=500,
        tasks_completed_24h=200,
        errors_24h=5,
        messages_current_hour=42,
        thoughts_current_hour=25,
        errors_current_hour=1,
        tokens_last_hour=15000.0,
        cost_last_hour_cents=2.5,
        carbon_last_hour_grams=0.5,
        energy_last_hour_kwh=0.001,
        tokens_24h=350000.0,
        cost_24h_cents=58.0,
        carbon_24h_grams=12.0,
        energy_24h_kwh=0.024,
        error_rate_percent=0.5,
        avg_thought_depth=3.2,
        queue_saturation=0.3,
    )

    # Configure all async methods with proper return types
    mock.get_telemetry_summary = AsyncMock(return_value=telemetry_summary)

    # Return dict directly (not a custom class) to support 'in' operator and dict methods
    aggregated_telemetry_data = {
        "system_healthy": True,
        "services_online": 35,
        "services_total": 35,
        "overall_error_rate": 0.0,
        "overall_uptime_seconds": 86400.0,
        "total_errors": 0,
        "total_requests": 1000,
        "services": {},
        "timestamp": now.isoformat(),
    }

    mock.get_aggregated_telemetry = AsyncMock(return_value=aggregated_telemetry_data)

    # Query metrics - returns list of metric point objects (not dicts)
    async def mock_query_metrics(metric_name, start_time=None, end_time=None, **kwargs):
        # Return objects with .timestamp, .value, .metric, .tags attributes
        class MetricPoint:
            def __init__(self, timestamp, value, metric, tags=None):
                self.timestamp = timestamp
                self.value = value
                self.metric = metric
                self.tags = tags or {}

        return [
            MetricPoint(timestamp=now - timedelta(minutes=i * 5), value=45.5 + i, metric=metric_name)
            for i in range(12)  # Last hour in 5-minute intervals
        ]

    mock.query_metrics = AsyncMock(side_effect=mock_query_metrics)

    # Get metric count - returns int, not Mock
    mock.get_metric_count = AsyncMock(return_value=1500)

    # Sync get_metrics for service health checks
    mock.get_metrics = Mock(
        return_value={"uptime_seconds": 86400.0, "messages_processed": 1000, "errors": 0, "healthy": True}
    )

    # Other methods
    mock.collect_all = AsyncMock(return_value={})
    mock.is_healthy = Mock(return_value=True)

    return mock


@pytest.fixture
def mock_api_visibility_service():
    """Create a fully-configured visibility service for API tests."""
    mock = AsyncMock()

    # Current state with concrete types (not Mock to avoid serialization issues)
    class CurrentTask:
        description = "Processing user request"
        task_id = "task_123"

    class CurrentState:
        reasoning_depth = 3
        current_task = CurrentTask()

    mock.get_current_state = AsyncMock(return_value=CurrentState())

    # System status
    mock.get_system_status = AsyncMock(
        return_value={"status": "healthy", "active_tasks": 5, "reasoning_depth": 3, "processing_queue_size": 10}
    )

    # Task history - return objects with attributes (not dicts)
    class TaskHistoryItem:
        def __init__(self, task_id, description, status, timestamp):
            self.task_id = task_id
            self.description = description
            self.status = status
            self.timestamp = timestamp

    mock.get_task_history = AsyncMock(
        return_value=[
            TaskHistoryItem(
                task_id=f"task_{i}",
                description=f"Task {i}",
                status="completed",
                timestamp=datetime.now(timezone.utc) - timedelta(minutes=i),
            )
            for i in range(10)
        ]
    )

    # Reasoning traces
    mock.get_reasoning_trace = AsyncMock(return_value=None)
    mock.query_traces = AsyncMock(return_value=[])
    mock.get_current_reasoning = AsyncMock(return_value=None)
    mock.get_recent_traces = AsyncMock(return_value=[])

    # Metrics
    mock.get_metrics = Mock(return_value={"visibility_metrics": 100, "status": "healthy", "traces_stored": 500})
    mock.is_healthy = Mock(return_value=True)

    return mock


@pytest.fixture
def mock_api_incident_service():
    """Create a fully-configured incident management service for API tests."""
    from ciris_engine.schemas.services.graph.incident import IncidentNode, IncidentInsightNode, IncidentSeverity, IncidentStatus
    from ciris_engine.schemas.services.graph_core import NodeType, GraphScope

    mock = AsyncMock()
    now = datetime.now(timezone.utc)

    # Incident counting - returns int, not MagicMock
    mock.count_active_incidents = AsyncMock(return_value=2)

    # Get incident count for specific time window (used by telemetry endpoint)
    async def mock_get_incident_count(hours=None, **kwargs):
        return 3  # Return int, not Mock

    mock.get_incident_count = AsyncMock(side_effect=mock_get_incident_count)

    # Query incidents - returns list of IncidentNode objects
    async def mock_query_incidents(start_time=None, end_time=None, severity=None, status=None, **kwargs):
        # Create sample incident nodes matching the schema
        incidents = []
        for i in range(5):
            incident = IncidentNode(
                id=f"inc-00{i}",
                type=NodeType.AUDIT_ENTRY,
                scope=GraphScope.LOCAL,
                attributes={},  # Required field for GraphNode base class
                incident_type="ERROR" if i % 2 == 0 else "WARNING",
                severity=IncidentSeverity.HIGH if i < 2 else IncidentSeverity.MEDIUM,
                status=IncidentStatus.INVESTIGATING if i < 2 else IncidentStatus.OPEN,
                description=f"Test incident {i}",
                source_component="test_component",
                detected_at=now - timedelta(hours=i),
                filename="test.py",
                line_number=100 + i,
                updated_by="test",
                updated_at=now,
            )

            # Apply filters (case-insensitive to match production)
            if severity and incident.severity.value.upper() != severity.upper():
                continue
            if status and incident.status.value.upper() != status.upper():
                continue

            incidents.append(incident)

        return incidents

    mock.query_incidents = AsyncMock(side_effect=mock_query_incidents)

    # Get insights - returns list of IncidentInsightNode objects
    async def mock_get_insights(start_time=None, end_time=None, limit=10, **kwargs):
        insights = []
        for i in range(min(limit, 5)):
            insight = IncidentInsightNode(
                id=f"insight-00{i}",
                type=NodeType.CONCEPT,
                scope=GraphScope.LOCAL,
                attributes={},  # Required field for GraphNode base class
                insight_type="PATTERN_DETECTED" if i % 2 == 0 else "PERIODIC_ANALYSIS",
                summary=f"Insight {i}: Pattern detected in error logs",
                details={"pattern_count": i + 1, "affected_components": ["test_component"]},
                analysis_timestamp=now - timedelta(hours=i * 2),
                updated_by="incident_service",
                updated_at=now,
            )
            insights.append(insight)

        return insights

    mock.get_insights = AsyncMock(side_effect=mock_get_insights)

    # Metrics - concrete dict, not MagicMock
    mock.get_metrics = Mock(
        return_value={"total_incidents": 10, "active_incidents": 2, "resolved_incidents": 8, "healthy": True}
    )
    mock.is_healthy = Mock(return_value=True)

    return mock


@pytest.fixture
def mock_api_wise_authority():
    """Create a fully-configured wise authority service for API tests."""
    mock = AsyncMock()

    # Deferral counting - returns int, not MagicMock
    mock.count_active_deferrals = AsyncMock(return_value=1)

    # Get pending deferrals (used by telemetry endpoint)
    mock.get_pending_deferrals = AsyncMock(
        return_value=[
            {
                "deferral_id": "def_1",
                "reason": "Requires human input",
                "timestamp": datetime.now(timezone.utc) - timedelta(hours=1),
            }
        ]
    )

    # Get active deferrals (alias for compatibility)
    mock.get_active_deferrals = AsyncMock(
        return_value=[
            {
                "deferral_id": "def_1",
                "reason": "Requires human input",
                "timestamp": datetime.now(timezone.utc) - timedelta(hours=1),
            }
        ]
    )

    # Metrics - concrete dict, not MagicMock
    mock.get_metrics = Mock(
        return_value={"total_deferrals": 5, "active_deferrals": 1, "resolved_deferrals": 4, "healthy": True}
    )
    mock.is_healthy = Mock(return_value=True)

    return mock


@pytest.fixture
def mock_api_time_service():
    """Create a fully-configured time service for API tests."""
    mock = Mock()

    # Uptime - returns float seconds (not timedelta)
    mock.get_uptime = Mock(return_value=88245.0)

    # Legacy uptime property - returns timedelta
    mock.uptime = Mock(return_value=timedelta(hours=24, minutes=30, seconds=45))

    # Get metrics - concrete dict with float values
    mock.get_metrics = Mock(
        return_value={"uptime_seconds": 88245.0, "current_time": datetime.now(timezone.utc).isoformat()}
    )

    # Now - returns datetime
    mock.now = Mock(return_value=datetime.now(timezone.utc))

    mock.is_healthy = Mock(return_value=True)

    return mock


@pytest.fixture
def mock_api_resource_monitor():
    """Create a fully-configured resource monitor for API tests."""
    mock = Mock()

    # Snapshot with all concrete float/int values (not Mock to avoid serialization issues)
    class Snapshot:
        cpu_percent = 45.5
        memory_mb = 512.0
        memory_percent = 25.0
        disk_usage_bytes = 20500000000
        active_threads = 50
        open_files = 100
        timestamp = datetime.now(timezone.utc).isoformat()
        warnings = []

    mock.snapshot = Snapshot()

    # Budget with concrete float values (not Mock to avoid serialization issues)
    class Budget:
        max_memory_mb = 2048.0
        max_cpu_percent = 100.0
        max_disk_bytes = 100000000000

    mock.budget = Budget()

    # Get metrics - concrete dict with float values
    mock.get_metrics = Mock(
        return_value={
            "cpu_percent": 45.5,  # float
            "memory_mb": 512.0,  # float
            "disk_usage_gb": 20.5,  # float
            "network_connections": 15,  # int
            "open_files": 100,  # int
            "thread_count": 50,  # int
        }
    )

    mock.is_healthy = Mock(return_value=True)

    return mock


@pytest.fixture
def complete_api_telemetry_setup(
    mock_api_telemetry_service,
    mock_api_visibility_service,
    mock_api_incident_service,
    mock_api_wise_authority,
    mock_api_time_service,
    mock_api_resource_monitor,
):
    """
    Complete fixture providing all services needed for telemetry API testing.

    All mocks use concrete types (float, int, str, dict) instead of MagicMock
    to avoid Pydantic serialization warnings.
    """
    return {
        "telemetry_service": mock_api_telemetry_service,
        "visibility_service": mock_api_visibility_service,
        "incident_management_service": mock_api_incident_service,
        "wise_authority_service": mock_api_wise_authority,
        "time_service": mock_api_time_service,
        "resource_monitor": mock_api_resource_monitor,
    }
