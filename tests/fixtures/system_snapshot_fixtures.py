"""
Central fixtures for system snapshot testing.

Provides comprehensive mocking for all system snapshot dependencies
to avoid architectural coupling issues and enable proper isolated testing.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest


@pytest.fixture
def mock_time_service():
    """Create a mock time service with fixed time."""
    time_service = Mock()
    # Fixed time for consistent testing
    fixed_time = datetime(2025, 9, 27, 12, 0, 0, tzinfo=timezone.utc)
    time_service.now.return_value = fixed_time
    return time_service


@pytest.fixture
def mock_resource_monitor():
    """Create a mock resource monitor."""
    mock = Mock()
    mock.snapshot = Mock(critical=[], healthy=True)
    mock.get_resource_alerts = Mock(return_value=[])
    return mock


@pytest.fixture
def comprehensive_system_snapshot_mocks():
    """
    Comprehensive fixture that mocks ALL system snapshot dependencies.

    This addresses the architectural issue where helper functions
    directly access global persistence and services instead of
    receiving them as parameters.
    """
    with patch("ciris_engine.logic.context.system_snapshot_helpers.persistence") as mock_persistence, patch(
        "ciris_engine.logic.context.system_snapshot.persistence"
    ) as mock_main_persistence, patch(
        "ciris_engine.logic.context.system_snapshot.build_secrets_snapshot"
    ) as mock_secrets, patch(
        "ciris_engine.logic.persistence.models.tasks.get_db_connection"
    ) as mock_task_db, patch(
        "ciris_engine.logic.persistence.models.graph.get_db_connection"
    ) as mock_graph_db, patch(
        "ciris_engine.logic.config.db_paths.get_sqlite_db_full_path"
    ) as mock_db_path:

        # Mock database path to avoid config dependency
        mock_db_path.return_value = "/tmp/test.db"

        # Mock database connections
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=None)

        mock_task_db.return_value = mock_conn
        mock_graph_db.return_value = mock_conn

        # Mock persistence functions
        mock_persistence.get_recent_completed_tasks.return_value = []
        mock_persistence.get_top_tasks.return_value = []
        mock_persistence.get_db_connection.return_value = mock_conn

        # Mock queue status
        queue_status_mock = Mock()
        queue_status_mock.total_tasks = 0
        queue_status_mock.total_thoughts = 0
        queue_status_mock.pending_tasks = 0
        queue_status_mock.pending_thoughts = 0
        queue_status_mock.processing_thoughts = 0
        mock_persistence.get_queue_status.return_value = queue_status_mock
        mock_main_persistence.get_queue_status.return_value = queue_status_mock

        # Mock secrets snapshot
        mock_secrets.return_value = {"detected_secrets": [], "secrets_filter_version": 1, "total_secrets_stored": 0}

        yield {
            "persistence": mock_persistence,
            "main_persistence": mock_main_persistence,
            "secrets": mock_secrets,
            "task_db": mock_task_db,
            "graph_db": mock_graph_db,
            "db_path": mock_db_path,
            "db_connection": mock_conn,
            "cursor": mock_cursor,
        }


@pytest.fixture
def mock_memory_service():
    """Create a comprehensive mock memory service."""
    mock = AsyncMock()

    # Mock recall method for various queries
    async def mock_recall(query):
        if "agent/identity" in str(query.node_id):
            # Return mock agent identity
            identity_node = Mock()
            identity_node.attributes = Mock()
            identity_node.attributes.model_dump = Mock(
                return_value={
                    "agent_id": "test_agent",
                    "description": "Test Agent",
                    "role_description": "Testing",
                    "trust_level": 0.9,
                    "permitted_actions": ["test"],
                    "restricted_capabilities": [],
                }
            )
            return [identity_node]
        elif "user/" in str(query.node_id):
            # Extract user ID from query
            user_id = str(query.node_id).split("/")[-1]
            user_node = Mock()
            user_node.id = f"user/{user_id}"
            user_node.attributes = {
                "username": f"user_{user_id}",
                "email": f"user_{user_id}@example.com",
                "last_seen": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "trust_level": 0.8,
                "is_wa": False,
            }
            return [user_node]
        elif "channel/" in str(query.node_id):
            # Return mock channel context
            channel_node = Mock()
            channel_node.attributes = {
                "channel_id": "test_channel",
                "channel_name": "Test Channel",
            }
            return [channel_node]
        return []

    mock.recall = mock_recall
    mock.query_nodes = AsyncMock(return_value=[])
    mock.memorize = AsyncMock(return_value=Mock(success=True))

    return mock


@pytest.fixture
def mock_service_registry():
    """Create a mock service registry."""
    mock = Mock()
    mock.get_provider_info.return_value = {"handlers": {}, "global_services": {}}
    mock.get_circuit_breaker_states.return_value = {}
    return mock


@pytest.fixture
def mock_runtime():
    """Create a mock runtime."""
    mock = Mock()
    mock.current_shutdown_context = None
    mock.adapter_manager = Mock(_adapters={})
    mock.service_registry = Mock()
    mock.bus_manager = Mock()
    return mock


@pytest.fixture
def mock_secrets_service():
    """Create a mock secrets service."""
    mock = AsyncMock()
    mock.get_secrets_stats = AsyncMock(return_value={"total_secrets_stored": 0, "secrets_filter_version": 1})
    return mock


@pytest.fixture
def mock_telemetry_service():
    """Create a comprehensive mock telemetry service with all required async methods."""
    from datetime import timedelta

    from ciris_engine.schemas.runtime.system_context import TelemetrySummary

    mock = AsyncMock()
    now = datetime.now(timezone.utc)

    # Create telemetry summary
    telemetry_summary = TelemetrySummary(
        window_start=now - timedelta(hours=24),
        window_end=now,
        uptime_seconds=86400.0,
        messages_processed_24h=1000,
        thoughts_processed_24h=500,
        tasks_completed_24h=200,
        errors_24h=5,
        messages_current_hour=42,
    )

    # Mock all async methods
    mock.get_telemetry_summary = AsyncMock(return_value=telemetry_summary)
    mock.get_aggregated_telemetry = AsyncMock(
        return_value=Mock(
            system_healthy=True,
            services_online=35,
            services_total=35,
            overall_error_rate=0.0,
            overall_uptime_seconds=86400.0,
            total_errors=0,
            total_requests=1000,
            services={},
        )
    )
    mock.query_metrics = AsyncMock(return_value=[])
    mock.get_metrics = AsyncMock(return_value={"uptime_seconds": 86400.0, "messages_processed": 1000, "errors": 0})
    mock.collect_all = AsyncMock(return_value={})

    return mock


@pytest.fixture
def mock_visibility_service():
    """Create a comprehensive mock visibility service with all required async methods."""
    mock = AsyncMock()

    # Mock current state
    current_state = Mock()
    current_state.reasoning_depth = 3
    current_state.current_task = Mock(description="Processing user request")
    mock.get_current_state = AsyncMock(return_value=current_state)

    # Mock system status
    mock.get_system_status = AsyncMock(return_value={"status": "healthy", "active_tasks": 5, "reasoning_depth": 3})

    # Mock task history
    mock.get_task_history = AsyncMock(return_value=[])

    # Mock reasoning traces
    mock.get_reasoning_trace = AsyncMock(return_value=None)
    mock.query_traces = AsyncMock(return_value=[])
    mock.get_current_reasoning = AsyncMock(return_value=None)
    mock.get_recent_traces = AsyncMock(return_value=[])

    # Mock metrics
    mock.get_metrics = Mock(return_value={"visibility_metrics": 100, "status": "healthy"})

    return mock


@pytest.fixture
def mock_incident_service():
    """Create a comprehensive mock incident management service."""
    mock = AsyncMock()

    # Mock incident counting
    mock.count_active_incidents = AsyncMock(return_value=2)
    mock.get_recent_incidents = AsyncMock(return_value=[])
    mock.get_insights = AsyncMock(return_value=[])

    # Mock metrics
    mock.get_metrics = Mock(return_value={"total_incidents": 10, "active_incidents": 2, "resolved_incidents": 8})

    return mock


@pytest.fixture
def mock_wise_authority():
    """Create a comprehensive mock wise authority service."""
    mock = AsyncMock()

    # Mock deferral counting
    mock.count_active_deferrals = AsyncMock(return_value=1)
    mock.get_active_deferrals = AsyncMock(return_value=[])

    # Mock metrics
    mock.get_metrics = Mock(return_value={"total_deferrals": 5, "active_deferrals": 1, "resolved_deferrals": 4})

    return mock


@pytest.fixture
def mock_graphql_provider():
    """Create a mock GraphQL provider."""
    mock = AsyncMock()
    mock.enrich_context = AsyncMock(return_value=None)
    return mock


@pytest.fixture
def complete_system_snapshot_setup(
    mock_time_service,
    mock_resource_monitor,
    comprehensive_system_snapshot_mocks,
    mock_memory_service,
    mock_service_registry,
    mock_runtime,
    mock_secrets_service,
    mock_telemetry_service,
    mock_visibility_service,
    mock_incident_service,
    mock_wise_authority,
    mock_graphql_provider,
):
    """
    Complete setup fixture that provides all dependencies needed
    for system snapshot testing without architectural coupling issues.
    """
    return {
        "time_service": mock_time_service,
        "resource_monitor": mock_resource_monitor,
        "memory_service": mock_memory_service,
        "service_registry": mock_service_registry,
        "runtime": mock_runtime,
        "secrets_service": mock_secrets_service,
        "telemetry_service": mock_telemetry_service,
        "visibility_service": mock_visibility_service,
        "incident_service": mock_incident_service,
        "wise_authority": mock_wise_authority,
        "graphql_provider": mock_graphql_provider,
        "mocks": comprehensive_system_snapshot_mocks,
    }
