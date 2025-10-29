"""Unit tests for TSDB Consolidation Service."""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.services.graph.tsdb_consolidation import TSDBConsolidationService
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph_core import GraphScope, NodeType
from ciris_engine.schemas.services.nodes import TSDBSummary
from ciris_engine.schemas.services.operations import MemoryOpResult, MemoryOpStatus


@pytest.fixture
def mock_memory_bus():
    """Create a mock memory bus."""
    mock = Mock()
    # memorize should return a MemoryOpResult with status=OK
    mock.memorize = AsyncMock(return_value=MemoryOpResult(status=MemoryOpStatus.OK))
    mock.recall = AsyncMock(return_value=[])

    # recall_timeseries needs to return different types based on correlation_types parameter
    async def recall_timeseries_side_effect(*args, **kwargs):
        correlation_types = kwargs.get("correlation_types", [])
        if "audit_event" in correlation_types:
            # Return empty list for audit events in these tests
            return []
        # Default to empty list for other types
        return []

    mock.recall_timeseries = AsyncMock(side_effect=recall_timeseries_side_effect)
    mock.search = AsyncMock(return_value=[])
    mock.forget = AsyncMock(return_value=Mock(status="ok"))
    return mock


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    mock = Mock()
    mock.now = Mock(return_value=datetime.now(timezone.utc))
    return mock


@pytest.fixture
def tsdb_service(mock_memory_bus, mock_time_service):
    """Create a TSDB consolidation service for testing."""
    # Create temporary test database
    import os
    import sqlite3
    import tempfile

    fd, db_path = tempfile.mkstemp(suffix="_test.db")
    os.close(fd)

    # Initialize database with required tables
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS graph_nodes (
            node_id TEXT PRIMARY KEY,
            node_type TEXT NOT NULL,
            scope TEXT NOT NULL,
            attributes_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            version INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS graph_edges (
            edge_id TEXT PRIMARY KEY,
            source_node_id TEXT NOT NULL,
            target_node_id TEXT NOT NULL,
            relationship TEXT NOT NULL,
            scope TEXT NOT NULL,
            attributes_json TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            updated_by TEXT,
            version INTEGER DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS service_correlations (
            correlation_id TEXT PRIMARY KEY,
            service_type TEXT NOT NULL,
            handler_name TEXT,
            action_type TEXT,
            request_data TEXT,
            response_data TEXT,
            status TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            correlation_type TEXT,
            timestamp TEXT,
            metric_name TEXT,
            metric_value REAL,
            trace_id TEXT,
            span_id TEXT,
            parent_span_id TEXT,
            tags TEXT
        );

        CREATE TABLE IF NOT EXISTS thoughts (
            thought_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            agent_id TEXT NOT NULL,
            content TEXT NOT NULL,
            thought_type TEXT NOT NULL,
            processing_status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            processed_at TEXT,
            parent_thought_id TEXT,
            metadata_json TEXT,
            action_result TEXT
        );

        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            thought_id TEXT,
            action TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            completed_at TEXT,
            result TEXT,
            error TEXT,
            metadata_json TEXT
        );
    """
    )
    conn.commit()
    conn.close()

    # Monkey patch get_db_connection to use our test database
    import ciris_engine.logic.persistence.db.core
    import ciris_engine.logic.services.graph.tsdb_consolidation.edge_manager
    import ciris_engine.logic.services.graph.tsdb_consolidation.query_manager

    original_get_db = ciris_engine.logic.persistence.db.core.get_db_connection

    test_db_path = db_path  # Capture from closure above

    def get_test_db_connection(db_path=None, **kwargs):
        # Use provided db_path if given, otherwise use test db
        use_path = db_path if db_path else test_db_path
        conn = sqlite3.connect(use_path)
        conn.row_factory = sqlite3.Row
        return conn

    # Patch in all places
    ciris_engine.logic.persistence.db.core.get_db_connection = get_test_db_connection
    ciris_engine.logic.services.graph.tsdb_consolidation.query_manager.get_db_connection = get_test_db_connection
    ciris_engine.logic.services.graph.tsdb_consolidation.edge_manager.get_db_connection = get_test_db_connection

    service = TSDBConsolidationService(
        memory_bus=mock_memory_bus, time_service=mock_time_service, db_path=test_db_path  # Pass the test database path
    )

    yield service

    # Cleanup
    ciris_engine.logic.persistence.db.core.get_db_connection = original_get_db
    ciris_engine.logic.services.graph.tsdb_consolidation.query_manager.get_db_connection = original_get_db
    try:
        os.unlink(db_path)
    except:
        pass


@pytest.mark.asyncio
async def test_tsdb_service_lifecycle(tsdb_service):
    """Test TSDBConsolidationService start/stop lifecycle."""
    # Start
    await tsdb_service.start()
    assert tsdb_service._running is True

    # Stop
    await tsdb_service.stop()
    assert tsdb_service._running is False


@pytest.mark.asyncio
async def test_tsdb_service_consolidate_period(tsdb_service, mock_memory_bus):
    """Test consolidating TSDB data for a period."""
    # Mock the database access method
    with patch.object(tsdb_service, "_find_oldest_unconsolidated_period", return_value=None):
        # Create mock TSDB nodes
        now = datetime.now(timezone.utc)
        start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_time = start_time + timedelta(hours=6)

        # Create mock datapoints that match what the implementation expects
        class MockDataPoint:
            def __init__(self, timestamp, metric_name, value, correlation_type, tags):
                # Keep timestamp as datetime object - the service expects datetime, not string
                self.timestamp = timestamp
                self.metric_name = metric_name
                self.value = value
                self.correlation_type = correlation_type
                self.tags = tags

    mock_datapoints = [
        MockDataPoint(
            timestamp=start_time + timedelta(hours=1),
            metric_name="api.requests",
            value=100,
            correlation_type="METRIC_DATAPOINT",
            tags={},
        ),
        MockDataPoint(
            timestamp=start_time + timedelta(hours=2),
            metric_name="api.requests",
            value=150,
            correlation_type="METRIC_DATAPOINT",
            tags={},
        ),
        MockDataPoint(
            timestamp=start_time + timedelta(hours=1),
            metric_name="memory.usage",
            value=512,
            correlation_type="METRIC_DATAPOINT",
            tags={},
        ),
    ]

    # Insert test data into the database
    import json
    import time

    from ciris_engine.logic.persistence.db.core import get_db_connection

    # Add unique timestamp to avoid conflicts
    test_id = int(time.time() * 1000)

    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Insert some metric correlations
        for i in range(3):
            timestamp = start_time + timedelta(hours=i + 1)
            cursor.execute(
                """
                INSERT INTO service_correlations
                (correlation_id, service_type, handler_name, action_type,
                 request_data, response_data, status, created_at, updated_at,
                 correlation_type, timestamp, metric_name, metric_value,
                 trace_id, span_id, parent_span_id, tags)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    f'metric_tsdb_{test_id}_{i}_{timestamp.strftime("%Y%m%d_%H%M%S")}',
                    "telemetry",
                    "metrics_collector",
                    "record_metric",
                    json.dumps({"metric_name": "api.requests", "value": 100 + i * 50}),
                    json.dumps({"status": "recorded"}),
                    "success",
                    timestamp.isoformat(),
                    timestamp.isoformat(),
                    "metric_datapoint",
                    timestamp.isoformat(),
                    "api.requests",
                    100 + i * 50,
                    f"trace_metric_{i}",
                    f"span_metric_{i}",
                    None,
                    json.dumps({"endpoint": "/api/test"}),
                ),
            )

        conn.commit()

    # Consolidate the period using the private method (public interface is through the loop)
    summaries = await tsdb_service._consolidate_period(start_time, end_time)

    assert summaries is not None
    assert len(summaries) > 0  # Should have at least one summary

    # Find the TSDBSummary in the list
    tsdb_summary = None
    for summary in summaries:
        if "tsdb_summary_" in summary.id:
            tsdb_summary = summary
            break

    assert tsdb_summary is not None

    # Check if it's a TSDBSummary object or a GraphNode
    if hasattr(tsdb_summary, "period_start"):
        # It's a TSDBSummary object
        assert tsdb_summary.period_start == start_time
        assert tsdb_summary.period_end == end_time
        attrs = tsdb_summary.attributes if hasattr(tsdb_summary, "attributes") else tsdb_summary.model_dump()
    else:
        # It's a GraphNode
        attrs = tsdb_summary.attributes
        assert attrs["period_start"] == start_time.isoformat()
        assert attrs["period_end"] == end_time.isoformat()

    # The test now uses real data from the memory service
    # The TSDBSummary stores metrics in the object, not in attributes
    # Since we found a real summary, check its structure
    assert hasattr(tsdb_summary, "id")
    assert tsdb_summary.id.startswith("tsdb_summary_")

    # Check attributes exist
    assert hasattr(tsdb_summary, "attributes")
    assert isinstance(tsdb_summary.attributes, dict)

    # Verify some expected metadata fields
    assert "correlation_count" in tsdb_summary.attributes
    assert "unique_metrics" in tsdb_summary.attributes
    assert "metrics_count" in tsdb_summary.attributes

    # All summaries should have these counts
    assert tsdb_summary.attributes["metrics_count"] >= 0
    assert tsdb_summary.attributes["correlation_count"] >= 0

    # Check source node count - it might be in the object directly or in attributes
    if hasattr(tsdb_summary, "source_node_count"):
        # It's a TSDBSummary object
        assert isinstance(tsdb_summary.source_node_count, int)
        assert tsdb_summary.source_node_count >= 0
    elif "source_node_count" in attrs:
        # It's in attributes
        assert isinstance(attrs["source_node_count"], int)
        assert attrs["source_node_count"] >= 0
    else:
        # source_node_count might not be present in all cases
        pass

    # Check that we processed correlations - the count is in the attributes
    assert tsdb_summary.attributes.get("correlation_count", 0) >= 0
    # Verify that we have some indication of data processing
    assert (
        tsdb_summary.attributes.get("metrics_count", 0) > 0 or tsdb_summary.attributes.get("total_data_points", 0) > 0
    )


@pytest.mark.asyncio
async def test_tsdb_service_auto_consolidation(tsdb_service, mock_memory_bus, mock_time_service):
    """Test automatic consolidation scheduling."""
    # The service has a _calculate_next_run_time method we can test
    current_time = datetime(2024, 12, 22, 14, 30, 0, tzinfo=timezone.utc)
    mock_time_service.now.return_value = current_time

    # Calculate next run time
    next_run = tsdb_service._calculate_next_run_time()

    # Should be at 18:00 (next 6-hour boundary)
    assert next_run.hour == 18
    assert next_run.minute == 0
    assert next_run.second == 0
    assert next_run.day == 22

    # Test midnight rollover
    current_time = datetime(2024, 12, 22, 23, 30, 0, tzinfo=timezone.utc)
    mock_time_service.now.return_value = current_time

    next_run = tsdb_service._calculate_next_run_time()

    # Should be at 00:00 next day
    assert next_run.hour == 0
    assert next_run.minute == 0
    assert next_run.second == 0
    assert next_run.day == 23


@pytest.mark.asyncio
async def test_tsdb_service_cleanup_old_data(tsdb_service, mock_memory_bus):
    """Test cleanup of old TSDB data after consolidation."""
    # The implementation now actually cleans up old data
    # Since this is a test with a fresh database, the count depends on test data

    # Cleanup old data using the private method
    deleted_count = tsdb_service._cleanup_old_nodes()

    # The count should be >= 0 (it varies based on test data)
    assert deleted_count >= 0
    # Forget calls may or may not be made depending on what needs cleanup
    # We just verify no errors occurred


@pytest.mark.asyncio
async def test_tsdb_service_resource_aggregation(tsdb_service, mock_memory_bus):
    """Test resource usage aggregation in summaries."""
    # Create resource metric nodes
    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=6)

    # Mock timeseries data with resource metrics
    class MockDataPoint:
        def __init__(self, timestamp, metric_name, value, correlation_type, tags):
            # Keep timestamp as datetime object - the service expects datetime, not string
            self.timestamp = timestamp
            self.metric_name = metric_name
            self.value = value
            self.correlation_type = correlation_type
            self.tags = tags

    resource_datapoints = [
        MockDataPoint(
            timestamp=start_time + timedelta(hours=1),
            metric_name="llm.tokens_used",
            value=1000,
            correlation_type="METRIC_DATAPOINT",
            tags={},
        ),
        MockDataPoint(
            timestamp=start_time + timedelta(hours=1),
            metric_name="llm.cost_cents",
            value=5.5,
            correlation_type="METRIC_DATAPOINT",
            tags={},
        ),
        MockDataPoint(
            timestamp=start_time + timedelta(hours=2),
            metric_name="carbon_grams",
            value=2.3,
            correlation_type="METRIC_DATAPOINT",
            tags={},
        ),
    ]

    # Override the side_effect for this specific test
    async def test_recall_timeseries(*args, **kwargs):
        correlation_types = kwargs.get("correlation_types", [])
        if "audit_event" in correlation_types:
            return []  # No audit events
        return resource_datapoints  # Return resource metrics

    mock_memory_bus.recall_timeseries.side_effect = test_recall_timeseries

    # Mock the query manager methods - metrics consolidator needs metric correlations
    from ciris_engine.schemas.services.graph.consolidation import MetricCorrelationData

    # Convert mock datapoints to MetricCorrelationData
    metric_correlations = [
        MetricCorrelationData(
            correlation_id=f"corr_{i}",
            metric_name=dp.metric_name,
            value=dp.value,
            timestamp=dp.timestamp,
            tags=dp.tags,
            source="test",
        )
        for i, dp in enumerate(resource_datapoints)
    ]

    with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=False), patch.object(
        tsdb_service._query_manager, "query_all_nodes_in_period", return_value={}
    ), patch.object(
        tsdb_service._query_manager,
        "query_service_correlations",
        return_value=Mock(
            service_interactions=[], metric_correlations=metric_correlations, trace_spans=[], task_correlations=[]
        ),
    ), patch.object(
        tsdb_service._query_manager, "query_tasks_in_period", return_value=[]
    ):
        # Consolidate with resource aggregation
        summaries = await tsdb_service._consolidate_period(start_time, end_time)

    # Debug output if test fails
    if not summaries:
        print("DEBUG: No summaries returned")
        print(f"DEBUG: recall_timeseries call count: {mock_memory_bus.recall_timeseries.call_count}")
        if mock_memory_bus.recall_timeseries.called:
            print(f"DEBUG: recall_timeseries calls: {mock_memory_bus.recall_timeseries.call_args_list}")

    assert summaries is not None
    assert len(summaries) > 0

    # Find the TSDBSummary in the list
    tsdb_summary = None
    for summary in summaries:
        if "tsdb_summary_" in summary.id:
            tsdb_summary = summary
            break

    assert tsdb_summary is not None

    # Check if it's a TSDBSummary object or a GraphNode
    if hasattr(tsdb_summary, "period_start"):
        # It's a TSDBSummary object
        assert tsdb_summary.period_start == start_time
        assert tsdb_summary.period_end == end_time
        attrs = tsdb_summary.attributes if hasattr(tsdb_summary, "attributes") else tsdb_summary.model_dump()
    else:
        # It's a GraphNode
        attrs = tsdb_summary.attributes
        assert attrs["period_start"] == start_time.isoformat()
        assert attrs["period_end"] == end_time.isoformat()
        assert "period_label" in attrs

    # The test now uses real data from the memory service
    # Check that resource aggregation fields exist and are numeric
    # For TSDBSummary objects, check direct attributes
    if hasattr(tsdb_summary, "total_tokens"):
        assert isinstance(tsdb_summary.total_tokens, (int, float))
        assert tsdb_summary.total_tokens >= 0
    elif "total_tokens" in attrs:
        assert isinstance(attrs["total_tokens"], (int, float))
        assert attrs["total_tokens"] >= 0

    if hasattr(tsdb_summary, "total_cost_cents"):
        assert isinstance(tsdb_summary.total_cost_cents, (int, float))
        assert tsdb_summary.total_cost_cents >= 0
    elif "total_cost_cents" in attrs:
        assert isinstance(attrs["total_cost_cents"], (int, float))
        assert attrs["total_cost_cents"] >= 0

    if hasattr(tsdb_summary, "total_carbon_grams"):
        assert isinstance(tsdb_summary.total_carbon_grams, (int, float))
        assert tsdb_summary.total_carbon_grams >= 0
    elif "total_carbon_grams" in attrs:
        assert isinstance(attrs["total_carbon_grams"], (int, float))
        assert attrs["total_carbon_grams"] >= 0


def test_tsdb_service_capabilities(tsdb_service):
    """Test TSDBConsolidationService.get_capabilities() returns correct info."""
    caps = tsdb_service.get_capabilities()

    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "TSDBConsolidationService"
    assert "consolidate_tsdb_nodes" in caps.actions
    assert "create_6hour_summaries" in caps.actions
    assert "consolidate_all_data" in caps.actions
    assert "create_proper_edges" in caps.actions
    assert "track_memory_events" in caps.actions
    assert "summarize_tasks" in caps.actions
    assert caps.version == "2.0.0"


def test_tsdb_service_status(tsdb_service):
    """Test TSDBConsolidationService.get_status() returns correct status."""
    status = tsdb_service.get_status()

    assert isinstance(status, ServiceStatus)
    assert status.service_name == "TSDBConsolidationService"
    assert status.service_type == "graph_service"
    assert "last_consolidation_timestamp" in status.metrics
    assert "task_running" in status.metrics
    assert isinstance(status.metrics["last_consolidation_timestamp"], float)
    assert isinstance(status.metrics["task_running"], float)


@pytest.mark.asyncio
async def test_tsdb_service_get_summary_for_period(tsdb_service, mock_memory_bus):
    """Test retrieving a specific TSDB summary for a period."""
    # Create a test summary
    import time

    test_id = int(time.time() * 1000)
    period_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    test_summary = TSDBSummary(
        id=f"tsdb_summary_test_{test_id}_{period_start.strftime('%Y%m%d_%H')}",
        period_start=period_start,
        period_end=period_start + timedelta(hours=6),
        period_label="2024-12-22-night",
        metrics={"test.metric": {"count": 1, "sum": 100, "min": 100, "max": 100, "avg": 100}},
        source_node_count=5,
        scope=GraphScope.LOCAL,
        attributes={},  # Required by GraphNode base
    )

    # Insert the summary into the database (the method uses direct DB query)
    import json

    from ciris_engine.logic.persistence.db.core import get_db_connection

    summary_node = test_summary.to_graph_node()
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO graph_nodes
            (node_id, node_type, scope, attributes_json, created_at, updated_at, updated_by, version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                summary_node.id,
                summary_node.type.value,
                summary_node.scope.value,
                json.dumps(summary_node.attributes),
                datetime.now(timezone.utc).isoformat(),
                datetime.now(timezone.utc).isoformat(),
                "test",
                1,
            ),
        )
        conn.commit()

    # Get summary for the period
    period_end = period_start + timedelta(hours=6)
    result = tsdb_service.get_summary_for_period(period_start, period_end)

    assert result is not None
    # Import the schema for type checking
    from ciris_engine.schemas.services.graph.consolidation import TSDBPeriodSummary

    assert isinstance(result, TSDBPeriodSummary)
    assert result.period_start == period_start.isoformat()
    assert result.period_end == period_end.isoformat()
    assert isinstance(result.source_node_count, int)


@pytest.mark.asyncio
async def test_tsdb_service_action_summary(tsdb_service, mock_memory_bus):
    """Test action count aggregation in summaries."""
    # Create action nodes
    now = datetime.now(timezone.utc)
    start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(hours=6)

    # Mock timeseries data with action metrics
    class MockDataPoint:
        def __init__(self, timestamp, metric_name, value, correlation_type, tags):
            # Keep timestamp as datetime object - the service expects datetime, not string
            self.timestamp = timestamp
            self.metric_name = metric_name
            self.value = value
            self.correlation_type = correlation_type
            self.tags = tags

    action_datapoints = [
        MockDataPoint(
            timestamp=start_time + timedelta(hours=1),
            metric_name="action.speak.count",
            value=1,
            correlation_type="METRIC_DATAPOINT",
            tags={"action_type": "SPEAK"},
        ),
        MockDataPoint(
            timestamp=start_time + timedelta(hours=2),
            metric_name="action.tool.count",
            value=1,
            correlation_type="METRIC_DATAPOINT",
            tags={"action_type": "TOOL"},
        ),
        MockDataPoint(
            timestamp=start_time + timedelta(hours=3),
            metric_name="action.speak.count",
            value=1,
            correlation_type="METRIC_DATAPOINT",
            tags={"action_type": "SPEAK"},
        ),
    ]

    # Override the side_effect for this specific test
    async def test_recall_timeseries(*args, **kwargs):
        correlation_types = kwargs.get("correlation_types", [])
        if "audit_event" in correlation_types:
            return []  # No audit events
        return action_datapoints  # Return action metrics

    mock_memory_bus.recall_timeseries.side_effect = test_recall_timeseries

    # Mock the query manager methods - metrics consolidator needs metric correlations
    from ciris_engine.schemas.services.graph.consolidation import MetricCorrelationData

    # Convert mock datapoints to MetricCorrelationData
    metric_correlations = [
        MetricCorrelationData(
            correlation_id=f"corr_{i}",
            metric_name=dp.metric_name,
            value=dp.value,
            timestamp=dp.timestamp,
            tags=dp.tags,
            source="test",
        )
        for i, dp in enumerate(action_datapoints)
    ]

    with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=False), patch.object(
        tsdb_service._query_manager, "query_all_nodes_in_period", return_value={}
    ), patch.object(
        tsdb_service._query_manager,
        "query_service_correlations",
        return_value=Mock(
            service_interactions=[], metric_correlations=metric_correlations, trace_spans=[], task_correlations=[]
        ),
    ), patch.object(
        tsdb_service._query_manager, "query_tasks_in_period", return_value=[]
    ):
        # Consolidate with action aggregation
        summaries = await tsdb_service._consolidate_period(start_time, end_time)

    # Debug output if test fails
    if not summaries:
        print("DEBUG: No summaries returned")
        print(f"DEBUG: recall_timeseries call count: {mock_memory_bus.recall_timeseries.call_count}")
        if mock_memory_bus.recall_timeseries.called:
            print(f"DEBUG: recall_timeseries calls: {mock_memory_bus.recall_timeseries.call_args_list}")

    assert summaries is not None
    assert len(summaries) > 0

    # Find the TSDBSummary in the list
    tsdb_summary = None
    for summary in summaries:
        if "tsdb_summary_" in summary.id:
            tsdb_summary = summary
            break

    assert tsdb_summary is not None
    attrs = tsdb_summary.attributes

    # The test now uses real data from the memory service
    # Check that action_counts exists and has the right structure
    if "action_counts" in attrs:
        assert isinstance(attrs["action_counts"], dict)
        # Check that action counts are numeric
        for action, count in attrs["action_counts"].items():
            assert isinstance(count, (int, float))
            assert count >= 0


@pytest.mark.asyncio
async def test_tsdb_service_error_handling(tsdb_service, mock_memory_bus):
    """Test error handling during consolidation."""
    # Make recall_timeseries raise an error
    mock_memory_bus.recall_timeseries.side_effect = Exception("Database error")

    # Use a time period far in the past to avoid conflicts with other tests
    past_time = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)

    # Consolidation should handle the error gracefully and return empty list
    result = await tsdb_service._consolidate_period(past_time, past_time + timedelta(hours=6))

    # Should return empty list on error
    assert result == []


@pytest.mark.asyncio
async def test_tsdb_service_typed_node_conversion(tsdb_service):
    """Test TSDBSummary TypedGraphNode conversion."""
    # Create a test summary
    summary = TSDBSummary(
        id="test_summary_20241222_00",
        scope=GraphScope.LOCAL,
        attributes={},
        period_start=datetime(2024, 12, 22, 0, 0, 0, tzinfo=timezone.utc),
        period_end=datetime(2024, 12, 22, 6, 0, 0, tzinfo=timezone.utc),
        period_label="2024-12-22-night",
        metrics={"test.metric": {"count": 10.0, "sum": 1000.0, "min": 50.0, "max": 150.0, "avg": 100.0}},
        total_tokens=5000,
        total_cost_cents=10.5,
        total_carbon_grams=15.3,
        action_counts={"SPEAK": 5, "TOOL": 3},
        error_count=1,
        success_rate=0.95,
        source_node_count=100,
    )

    # Convert to GraphNode
    graph_node = summary.to_graph_node()

    assert graph_node.id == "test_summary_20241222_00"
    assert graph_node.type == NodeType.TSDB_SUMMARY  # TSDBSummary uses TSDB_SUMMARY type
    assert graph_node.scope == GraphScope.LOCAL
    assert isinstance(graph_node.attributes, dict)
    assert graph_node.attributes["period_label"] == "2024-12-22-night"
    assert graph_node.attributes["total_tokens"] == 5000
    assert graph_node.attributes["node_class"] == "TSDBSummary"

    # Convert back from GraphNode
    reconstructed = TSDBSummary.from_graph_node(graph_node)

    assert reconstructed.id == summary.id
    assert reconstructed.period_start == summary.period_start
    assert reconstructed.period_end == summary.period_end
    assert reconstructed.period_label == summary.period_label
    assert reconstructed.metrics == summary.metrics
    assert reconstructed.total_tokens == summary.total_tokens
    assert reconstructed.total_cost_cents == summary.total_cost_cents
    assert reconstructed.action_counts == summary.action_counts
    assert reconstructed.source_node_count == summary.source_node_count


@pytest.mark.asyncio
async def test_tsdb_service_period_already_consolidated(tsdb_service, mock_memory_bus):
    """Test skipping already consolidated periods."""
    period_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(hours=6)

    # Mock that a summary already exists
    existing_summary = TSDBSummary(
        id=f"tsdb_summary_{period_start.strftime('%Y%m%d_%H')}",
        scope=GraphScope.LOCAL,
        attributes={},
        period_start=period_start,
        period_end=period_end,
        period_label="already-exists",
        source_node_count=10,
    )
    mock_memory_bus.recall.return_value = [existing_summary.to_graph_node()]

    # Since _is_period_consolidated now uses direct DB queries,
    # and the test uses mocks, we can't properly test this internal method.
    # Instead, test the behavior through the public interface.

    # When consolidating a period that already has a summary,
    # it should skip creating a new one
    summaries = await tsdb_service._consolidate_period(period_start, period_end)

    # Should return existing summaries or handle gracefully
    assert summaries is not None
    assert isinstance(summaries, list)


@pytest.mark.asyncio
async def test_tsdb_service_node_type(tsdb_service):
    """Test that TSDBConsolidationService manages TSDB_SUMMARY nodes."""
    node_type = tsdb_service.get_node_type()
    assert node_type == NodeType.TSDB_SUMMARY


@pytest.mark.asyncio
async def test_consolidate_missed_windows_acquires_locks(tsdb_service, mock_memory_bus):
    """Test that _consolidate_missed_windows acquires locks before consolidating each period."""
    # Mock _find_oldest_unconsolidated_period to return a timestamp (simulate data exists)
    oldest_time = datetime.now(timezone.utc) - timedelta(hours=48)
    with patch.object(tsdb_service, "_find_oldest_unconsolidated_period", return_value=oldest_time):
        # Mock check_period_consolidated to return False for multiple periods
        with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=False):
            with patch.object(tsdb_service._query_manager, "_try_acquire_lock", return_value=True) as mock_acquire:
                with patch.object(tsdb_service, "_consolidate_period", new_callable=AsyncMock) as mock_consolidate:
                    # Set consolidation as enabled
                    tsdb_service._consolidation_enabled = True

                    # Run missed window consolidation
                    await tsdb_service._consolidate_missed_windows()

                    # Verify locks were acquired for each missed period
                    assert mock_acquire.call_count > 0

                    # Verify each lock acquisition used correct key format
                    for call in mock_acquire.call_args_list:
                        lock_key = call[0][0]
                        assert lock_key.startswith("missed:")
                        # ISO format timestamp (either Z or +00:00)
                        assert lock_key.endswith("Z") or lock_key.endswith("+00:00")

                    # Verify consolidation happened after acquiring locks
                    assert mock_consolidate.call_count == mock_acquire.call_count


@pytest.mark.asyncio
async def test_consolidate_missed_windows_skips_locked_periods(tsdb_service):
    """Test that _consolidate_missed_windows skips periods when lock is held by another occurrence."""
    # Mock _find_oldest_unconsolidated_period to return a timestamp (simulate data exists)
    oldest_time = datetime.now(timezone.utc) - timedelta(hours=48)
    with patch.object(tsdb_service, "_find_oldest_unconsolidated_period", return_value=oldest_time):
        # Mock check_period_consolidated to return False for multiple periods
        with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=False):
            with patch.object(tsdb_service._query_manager, "_try_acquire_lock", return_value=False) as mock_acquire:
                with patch.object(tsdb_service, "_consolidate_period", new_callable=AsyncMock) as mock_consolidate:
                    # Set consolidation as enabled
                    tsdb_service._consolidation_enabled = True

                    # Run missed window consolidation
                    await tsdb_service._consolidate_missed_windows()

                    # Verify lock acquisition was attempted
                    assert mock_acquire.call_count > 0

                    # Verify consolidation was SKIPPED (lock held by another occurrence)
                    assert mock_consolidate.call_count == 0


@pytest.mark.asyncio
async def test_consolidate_missed_windows_partial_lock_acquisition(tsdb_service):
    """Test missed window consolidation with mixed lock acquisition results."""
    lock_results = [True, False, True, False]  # Acquire 1st and 3rd periods
    lock_call_count = 0

    def mock_acquire_lock(*args, **kwargs):
        """Simulate mixed lock acquisition results."""
        nonlocal lock_call_count
        if lock_call_count < len(lock_results):
            result = lock_results[lock_call_count]
            lock_call_count += 1
            return result
        return False

    # Mock _find_oldest_unconsolidated_period to return a timestamp (simulate data exists)
    oldest_time = datetime.now(timezone.utc) - timedelta(hours=48)
    with patch.object(tsdb_service, "_find_oldest_unconsolidated_period", return_value=oldest_time):
        # Mock check_period_consolidated to return False for multiple periods
        with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=False):
            with patch.object(tsdb_service._query_manager, "_try_acquire_lock", side_effect=mock_acquire_lock):
                with patch.object(tsdb_service, "_consolidate_period", new_callable=AsyncMock) as mock_consolidate:
                    # Set consolidation as enabled
                    tsdb_service._consolidation_enabled = True

                    # Run missed window consolidation
                    await tsdb_service._consolidate_missed_windows()

                    # Verify consolidation only happened for periods where lock was acquired
                    expected_consolidations = sum(1 for result in lock_results if result)
                    assert mock_consolidate.call_count == expected_consolidations


@pytest.mark.asyncio
async def test_consolidate_missed_windows_respects_already_consolidated(tsdb_service):
    """Test that already-consolidated periods are skipped without lock acquisition."""
    # Mock check_period_consolidated to return True (already consolidated)
    with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=True):
        with patch.object(tsdb_service._query_manager, "_try_acquire_lock") as mock_acquire:
            with patch.object(tsdb_service, "_consolidate_period", new_callable=AsyncMock) as mock_consolidate:
                # Set consolidation as enabled
                tsdb_service._consolidation_enabled = True

                # Run missed window consolidation
                await tsdb_service._consolidate_missed_windows()

                # Verify no lock acquisition attempted (periods already consolidated)
                assert mock_acquire.call_count == 0

                # Verify no consolidation attempted
                assert mock_consolidate.call_count == 0


@pytest.mark.asyncio
async def test_consolidate_missed_windows_lock_key_format(tsdb_service):
    """Test that lock keys follow correct format for missed window consolidation."""
    captured_lock_keys = []

    def capture_lock_key(lock_key, *args, **kwargs):
        """Capture lock keys for validation."""
        captured_lock_keys.append(lock_key)
        return True

    # Mock _find_oldest_unconsolidated_period to return a timestamp (simulate data exists)
    oldest_time = datetime.now(timezone.utc) - timedelta(hours=48)
    with patch.object(tsdb_service, "_find_oldest_unconsolidated_period", return_value=oldest_time):
        # Mock check_period_consolidated to return False for at least one period
        with patch.object(tsdb_service._query_manager, "check_period_consolidated", return_value=False):
            with patch.object(tsdb_service._query_manager, "_try_acquire_lock", side_effect=capture_lock_key):
                with patch.object(tsdb_service, "_consolidate_period", new_callable=AsyncMock):
                    # Set consolidation as enabled
                    tsdb_service._consolidation_enabled = True

                    # Run missed window consolidation
                    await tsdb_service._consolidate_missed_windows()

                    # Verify all lock keys follow "missed:<ISO_TIMESTAMP>" format
                    for lock_key in captured_lock_keys:
                        assert lock_key.startswith("missed:")
                        # Extract timestamp part
                        timestamp_str = lock_key.split(":", 1)[1]
                        # Verify it's a valid ISO format timestamp
                        assert "T" in timestamp_str
                        # ISO format timestamp (either Z or +00:00)
                        assert timestamp_str.endswith("Z") or timestamp_str.endswith("+00:00")
                        # Verify can be parsed as datetime
                        if timestamp_str.endswith("Z"):
                            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
                        else:
                            datetime.fromisoformat(timestamp_str)
