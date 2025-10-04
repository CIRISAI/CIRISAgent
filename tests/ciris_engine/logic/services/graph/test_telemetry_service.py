"""Unit tests for Telemetry Service.

IMPORTANT: TelemetryNode has been REMOVED from the codebase.
Telemetry now uses memorize_metric() which stores data as correlations.
The GraphTelemetryService routes all metrics through the memory bus.
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.buses.memory_bus import MemoryBus
from ciris_engine.logic.services.graph.telemetry_service import GraphTelemetryService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.runtime.resources import ResourceUsage
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.services.graph.telemetry import ResourceData, TelemetryData
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

    # Mock memorize_metric to return success
    bus.memorize_metric = AsyncMock(
        return_value=MemoryOpResult(status=MemoryOpStatus.OK, data={"node_id": "test-node-123"}, reason="Success")
    )

    # Mock memorize to return success
    bus.memorize = AsyncMock(
        return_value=MemoryOpResult(status=MemoryOpStatus.OK, data={"node_id": "test-node-456"}, reason="Success")
    )

    # Mock recall_timeseries to return empty list initially
    bus.recall_timeseries = AsyncMock(return_value=[])

    return bus


@pytest.fixture
def telemetry_service(memory_bus, time_service):
    """Create a telemetry service for testing."""
    return GraphTelemetryService(memory_bus=memory_bus, time_service=time_service)


@pytest.mark.asyncio
async def test_telemetry_service_lifecycle(telemetry_service, memory_bus):
    """Test TelemetryService start/stop lifecycle."""
    # Start
    await telemetry_service.start()

    # Stop
    await telemetry_service.stop()

    # Should have recorded shutdown metric
    memory_bus.memorize_metric.assert_called()
    last_call = memory_bus.memorize_metric.call_args
    assert last_call[1]["metric_name"] == "telemetry_service.shutdown"
    assert last_call[1]["value"] == 1.0


@pytest.mark.asyncio
async def test_telemetry_service_record_metric(telemetry_service, memory_bus):
    """Test recording a telemetry metric."""
    # Record a metric
    await telemetry_service.record_metric(metric_name="test.metric", value=42.5, tags={"environment": "test"})

    # Verify memorize_metric was called correctly
    memory_bus.memorize_metric.assert_called_once()
    call_args = memory_bus.memorize_metric.call_args[1]
    assert call_args["metric_name"] == "test.metric"
    assert call_args["value"] == 42.5
    assert call_args["tags"]["environment"] == "test"
    assert call_args["scope"] == "local"
    assert call_args["handler_name"] == "telemetry_service"


@pytest.mark.asyncio
async def test_telemetry_service_process_snapshot(telemetry_service, memory_bus):
    """Test processing a system snapshot."""
    # Create a snapshot with telemetry data
    # Note: SystemSnapshot is from runtime context, not telemetry service
    # So we need to test the internal methods directly

    # Test storing telemetry metrics
    telemetry_data = TelemetryData(metrics={"requests": 100, "errors": 5}, events={"startup": "completed"})

    await telemetry_service._store_telemetry_metrics(
        telemetry=telemetry_data, thought_id="test-thought-123", task_id="test-task-456"
    )

    # Verify metrics were recorded
    assert memory_bus.memorize_metric.call_count >= 2  # At least 2 metrics

    # Test storing resource usage
    resource_data = ResourceData(llm={"tokens_used": 500, "cost_cents": 0.5})

    resource_usage = ResourceUsage(tokens_used=500, cost_cents=0.5)

    await telemetry_service._record_resource_usage("llm_service", resource_usage)

    # Verify resource metrics were recorded
    metric_names = [call[1]["metric_name"] for call in memory_bus.memorize_metric.call_args_list]
    assert "llm_service.tokens_used" in metric_names
    assert "llm_service.cost_cents" in metric_names


@pytest.mark.asyncio
async def test_telemetry_service_query_metrics(telemetry_service, memory_bus):
    """Test querying telemetry metrics."""
    # Set up mock data to return
    base_time = datetime.now(timezone.utc)
    mock_metrics = []

    for i in range(5):
        mock_metric = Mock()
        mock_metric.metric_name = "query.test"
        mock_metric.value = i * 10.0
        mock_metric.timestamp = base_time + timedelta(seconds=i)  # Return datetime, not string
        mock_metric.tags = {"test": "true"}
        mock_metrics.append(mock_metric)

    memory_bus.recall_timeseries.return_value = mock_metrics

    # Query all metrics
    metrics = await telemetry_service.query_metrics(metric_name="query.test")
    assert len(metrics) == 5

    # Verify the bus was called correctly
    memory_bus.recall_timeseries.assert_called_with(
        scope="local", hours=24, start_time=None, end_time=None, handler_name="telemetry_service"  # Default
    )

    # Query with time range
    start_time = base_time + timedelta(seconds=2)
    end_time = base_time + timedelta(seconds=4)
    metrics = await telemetry_service.query_metrics(metric_name="query.test", start_time=start_time, end_time=end_time)
    # Should filter to 3 metrics (seconds 2, 3, 4)
    assert len(metrics) == 3


@pytest.mark.asyncio
async def test_telemetry_service_aggregation(telemetry_service, memory_bus):
    """Test metric aggregation."""
    # Set up mock data for the query
    values = [10, 20, 30, 40, 50]
    mock_metrics = []
    base_time = datetime.now(timezone.utc)

    for i, value in enumerate(values):
        mock_metric = Mock()
        mock_metric.metric_name = "aggregate.test"
        mock_metric.value = float(value)
        mock_metric.timestamp = base_time - timedelta(seconds=30 - i)  # Return datetime, not string
        mock_metric.tags = {}
        mock_metrics.append(mock_metric)

    memory_bus.recall_timeseries.return_value = mock_metrics

    # Get aggregated stats
    stats = await telemetry_service.get_metric_summary(metric_name="aggregate.test", window_minutes=60)

    assert stats is not None
    assert stats["count"] == 5.0
    assert stats["sum"] == 150.0
    assert stats["avg"] == 30.0
    assert stats["min"] == 10.0
    assert stats["max"] == 50.0


@pytest.mark.asyncio
async def test_telemetry_service_different_metric_types(telemetry_service, memory_bus):
    """Test recording different metric types."""
    # Counter - should accumulate
    for i in range(3):
        await telemetry_service.record_metric(metric_name="requests.total", value=1)

    # Gauge - point-in-time value
    await telemetry_service.record_metric(metric_name="memory.usage", value=75.5)

    # Histogram - distribution
    response_times = [100, 150, 200, 250, 300]
    for rt in response_times:
        await telemetry_service.record_metric(metric_name="response.time", value=rt)

    # Verify metrics were recorded
    assert memory_bus.memorize_metric.call_count == 9  # 3 + 1 + 5


def test_telemetry_service_capabilities(telemetry_service):
    """Test TelemetryService.get_capabilities() returns correct info."""
    caps = telemetry_service.get_capabilities()
    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "GraphTelemetryService"  # Uses class name by default
    assert caps.version == "1.0.0"
    # Check actions from _get_actions()
    assert "record_metric" in caps.actions
    assert "query_metrics" in caps.actions
    assert "get_metric_summary" in caps.actions
    assert "get_metric_count" in caps.actions
    assert "get_telemetry_summary" in caps.actions
    assert "process_system_snapshot" in caps.actions
    assert "get_resource_usage" in caps.actions
    assert "get_telemetry_status" in caps.actions
    # Dependencies from BaseGraphService
    assert "MemoryBus" in caps.dependencies
    assert "TimeService" in caps.dependencies
    # Note: The base implementation doesn't add metadata automatically


@pytest.mark.asyncio
async def test_telemetry_service_status(telemetry_service, memory_bus):
    """Test TelemetryService.get_status() returns correct status."""
    await telemetry_service.start()

    status = telemetry_service.get_status()
    assert isinstance(status, ServiceStatus)
    assert status.is_healthy is True
    assert status.service_name == "GraphTelemetryService"  # Uses class name by default
    assert status.service_type == "telemetry"  # ServiceType.TELEMETRY from get_service_type()

    # Record some metrics to populate cache
    for i in range(10):
        await telemetry_service.record_metric(metric_name=f"status.metric{i}", value=i)

    status = telemetry_service.get_status()
    assert status.metrics.get("total_metrics_cached", 0) > 0  # Correct metric name
    assert status.metrics.get("unique_metric_types", 0) > 0


@pytest.mark.asyncio
async def test_telemetry_service_tags_and_metadata(telemetry_service, memory_bus):
    """Test metric tags and metadata handling."""
    # Record metrics with different tags
    await telemetry_service.record_metric(
        metric_name="api.requests", value=1, tags={"endpoint": "/users", "method": "GET", "status": "200"}
    )

    await telemetry_service.record_metric(
        metric_name="api.requests", value=1, tags={"endpoint": "/users", "method": "POST", "status": "201"}
    )

    await telemetry_service.record_metric(
        metric_name="api.requests", value=1, tags={"endpoint": "/products", "method": "GET", "status": "404"}
    )

    # Set up mock to return filtered results
    mock_metrics = [
        Mock(
            metric_name="api.requests",
            value=1.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tags={"endpoint": "/users", "method": "GET", "status": "200"},
        ),
        Mock(
            metric_name="api.requests",
            value=1.0,
            timestamp=datetime.now(timezone.utc).isoformat(),
            tags={"endpoint": "/users", "method": "POST", "status": "201"},
        ),
    ]
    memory_bus.recall_timeseries.return_value = mock_metrics

    # Query with tag filter
    metrics = await telemetry_service.query_metrics(metric_name="api.requests", tags={"endpoint": "/users"})
    # Should get metrics for /users endpoint
    assert len(metrics) == 2


@pytest.mark.asyncio
async def test_telemetry_service_performance_metrics(telemetry_service, memory_bus):
    """Test recording performance-related metrics."""
    # Simulate recording various performance metrics
    perf_metrics = {
        "cpu.usage": 45.2,
        "memory.heap": 1024.5,
        "disk.io.read": 150.0,
        "disk.io.write": 75.0,
        "network.throughput.in": 1000.0,
        "network.throughput.out": 500.0,
    }

    for metric_name, value in perf_metrics.items():
        await telemetry_service.record_metric(
            metric_name=metric_name, value=value, tags={"host": "test-host", "region": "us-east-1"}
        )

    # Verify all metrics were recorded
    assert memory_bus.memorize_metric.call_count == len(perf_metrics)


@pytest.mark.asyncio
async def test_telemetry_service_error_handling(telemetry_service, memory_bus):
    """Test telemetry service error handling."""
    # Test when memory bus fails
    memory_bus.memorize_metric.side_effect = Exception("Bus error")

    # Should not raise, just log error
    await telemetry_service.record_metric(metric_name="test.metric", value=42)

    # Reset for next test
    memory_bus.memorize_metric.side_effect = None
    memory_bus.memorize_metric.reset_mock()

    # Test query when bus fails
    memory_bus.recall_timeseries.side_effect = Exception("Query error")

    # Should raise MetricCollectionError (fail fast and loud)
    from ciris_engine.logic.services.graph.telemetry_service.exceptions import MetricCollectionError

    with pytest.raises(MetricCollectionError, match="Failed to query metrics: Query error"):
        await telemetry_service.query_metrics("test.metric")


@pytest.mark.asyncio
async def test_telemetry_service_batch_recording(telemetry_service, memory_bus):
    """Test batch recording of metrics."""
    # Prepare batch of metrics
    base_time = datetime.now(timezone.utc)

    # Record 100 metrics
    for i in range(100):
        await telemetry_service.record_metric(metric_name="batch.test", value=float(i), tags={"batch_id": "test123"})

    # Verify all were recorded
    assert memory_bus.memorize_metric.call_count == 100

    # Verify caching behavior
    assert "batch.test" in telemetry_service._recent_metrics
    assert len(telemetry_service._recent_metrics["batch.test"]) <= telemetry_service._max_cached_metrics


@pytest.mark.asyncio
async def test_telemetry_service_resource_usage(telemetry_service, memory_bus):
    """Test recording resource usage metrics."""
    # Test _record_resource_usage method
    usage = ResourceUsage(
        tokens_used=1000,
        tokens_input=800,
        tokens_output=200,
        cost_cents=0.5,
        carbon_grams=0.1,
        energy_kwh=0.001,
        model_used="test-model",
    )

    await telemetry_service._record_resource_usage("llm_service", usage)

    # Should have recorded 6 different metrics (excluding model_used which is a string)
    assert memory_bus.memorize_metric.call_count == 6

    # Check that each metric was recorded
    metric_names = [call[1]["metric_name"] for call in memory_bus.memorize_metric.call_args_list]
    assert "llm_service.tokens_used" in metric_names
    assert "llm_service.tokens_input" in metric_names
    assert "llm_service.tokens_output" in metric_names
    assert "llm_service.cost_cents" in metric_names
    assert "llm_service.carbon_grams" in metric_names
    assert "llm_service.energy_kwh" in metric_names


@pytest.mark.asyncio
async def test_telemetry_service_health_check(telemetry_service):
    """Test service health check."""
    # Start the service first
    await telemetry_service.start()
    # Should be healthy with memory bus and time service
    health = await telemetry_service.is_healthy()
    assert health is True


@pytest.mark.asyncio
async def test_telemetry_service_get_node_type(telemetry_service):
    """Test get_node_type returns correct value."""
    node_type = telemetry_service.get_node_type()
    assert node_type == "TELEMETRY"  # Still returns TELEMETRY for compatibility
