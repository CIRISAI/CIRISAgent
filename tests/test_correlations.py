"""
Tests for correlations persistence model - ensuring type safety and robustness.

These tests align with CIRIS principles:
- Type safety (proper schema usage)
- Database integrity
- Error handling
- Backward compatibility

Migrated for 2.9.0 A1 absorption: correlations.py now routes through the
ciris-persist substrate. Tests use the shared `persist_engine` fixture
(wires a real persist Engine module-global) instead of raw sqlite3 temp DBs.
"""

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

from ciris_engine.logic.persistence.models.correlations import (
    _parse_response_data,
    _update_correlation_impl,
    add_correlation,
    add_correlation_with_telemetry,
    get_active_channels_by_adapter,
    get_channel_last_activity,
    get_correlation,
    get_correlations_by_channel,
    get_correlations_by_task_and_action,
    get_correlations_by_type_and_time,
    get_metrics_timeseries,
    get_recent_correlations,
    is_admin_channel,
    update_correlation,
)
from ciris_engine.schemas.persistence.core import CorrelationUpdateRequest, MetricsQuery
from ciris_engine.schemas.telemetry.core import (
    CorrelationType,
    LogData,
    MetricData,
    ServiceCorrelation,
    ServiceCorrelationStatus,
    ServiceRequestData,
    ServiceResponseData,
    TraceContext,
)


@pytest.fixture
def temp_db(persist_engine):
    """Compat alias — older tests parameterize on `temp_db` for the db_path.

    Under the migrated implementation, `db_path` is accepted but ignored
    (the wired persist Engine owns the underlying SQLite database). Yield
    a non-None placeholder so call sites that pass `db_path=temp_db`
    continue to work without code changes.
    """
    return "<persist-engine-wired>"


@pytest.fixture
def sample_correlation():
    """Create a sample ServiceCorrelation for testing."""
    return ServiceCorrelation(
        correlation_id="test_corr_001",
        service_type="llm",
        handler_name="test_handler",
        action_type="process",
        request_data=ServiceRequestData(
            service_type="llm",
            method_name="process",
            task_id="task_123",
            thought_id="thought_456",
            channel_id="channel_789",
            request_timestamp=datetime.now(timezone.utc),
        ),
        response_data=ServiceResponseData(
            success=True, execution_time_ms=100.0, error_message=None, response_timestamp=datetime.now(timezone.utc)
        ),
        status=ServiceCorrelationStatus.COMPLETED,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        correlation_type=CorrelationType.SERVICE_INTERACTION,
        timestamp=datetime.now(timezone.utc),
        tags={"test": "true"},
        retention_policy="raw",
    )


@pytest.fixture
def time_service():
    """Create a mock time service."""
    service = MagicMock()
    service.now.return_value = datetime.now(timezone.utc)
    return service


@pytest.fixture
def telemetry_service():
    """Create a mock telemetry service."""
    from unittest.mock import AsyncMock

    service = MagicMock()
    service._store_correlation = AsyncMock(return_value="success")
    service.memorize_metric = AsyncMock(return_value="success")
    return service


def create_correlation_factory(
    correlation_id: str = "test_corr",
    service_type: str = "test_service",
    handler_name: str = "test_handler",
    action_type: str = "process",
    status: ServiceCorrelationStatus = ServiceCorrelationStatus.COMPLETED,
    correlation_type: CorrelationType = CorrelationType.SERVICE_INTERACTION,
    timestamp: datetime = None,
    channel_id: str = "test_channel",
    task_id: str = "test_task",
    metric_data: MetricData = None,
    trace_context: TraceContext = None,
    log_data: LogData = None,
    tags: dict = None,
    **kwargs,
) -> ServiceCorrelation:
    """Factory function to create ServiceCorrelation objects with sensible defaults."""
    if timestamp is None:
        timestamp = datetime.now(timezone.utc)

    if tags is None:
        tags = {"test": "true"}

    request_data = ServiceRequestData(
        service_type=service_type,
        method_name=action_type,
        task_id=task_id,
        thought_id=f"thought_{correlation_id}",
        channel_id=channel_id,
        request_timestamp=timestamp,
    )

    response_data = ServiceResponseData(
        success=status == ServiceCorrelationStatus.COMPLETED,
        execution_time_ms=100.0,
        error_message=None if status == ServiceCorrelationStatus.COMPLETED else "Test error",
        response_timestamp=timestamp,
    )

    return ServiceCorrelation(
        correlation_id=correlation_id,
        service_type=service_type,
        handler_name=handler_name,
        action_type=action_type,
        request_data=request_data,
        response_data=response_data,
        status=status,
        created_at=timestamp.isoformat(),
        updated_at=timestamp.isoformat(),
        correlation_type=correlation_type,
        timestamp=timestamp,
        metric_data=metric_data,
        trace_context=trace_context,
        log_data=log_data,
        tags=tags,
        retention_policy="raw",
        **kwargs,
    )


@pytest.fixture
def correlation_factory():
    """Factory fixture for creating ServiceCorrelation objects."""
    return create_correlation_factory


@pytest.fixture
def populated_db(persist_engine, correlation_factory):
    """Database with sample correlations for testing."""
    base_time = datetime.now(timezone.utc)

    correlations = [
        correlation_factory("std_001", timestamp=base_time - timedelta(minutes=10)),
        correlation_factory("std_002", timestamp=base_time - timedelta(minutes=5)),
        correlation_factory(
            "api_001", channel_id="api_channel_123", action_type="speak", timestamp=base_time - timedelta(hours=1)
        ),
        correlation_factory(
            "api_002", channel_id="api_channel_123", action_type="observe", timestamp=base_time - timedelta(minutes=30)
        ),
        correlation_factory("llm_001", service_type="llm", action_type="think"),
        correlation_factory(
            "tel_001",
            service_type="telemetry",
            correlation_type=CorrelationType.METRIC_DATAPOINT,
            metric_data=MetricData(
                metric_name="test_metric", metric_value=42.0, metric_unit="count", metric_type="gauge", labels={}
            ),
        ),
        correlation_factory("admin_001", channel_id="api_admin_channel", tags={"user_role": "ADMIN", "test": "true"}),
        correlation_factory("failed_001", status=ServiceCorrelationStatus.FAILED),
    ]

    for corr in correlations:
        add_correlation(corr)

    return "<persist-engine-wired>"


class TestParseResponseData:
    """Test _parse_response_data function."""

    def test_parse_none_returns_none(self):
        assert _parse_response_data(None) is None

    def test_parse_empty_dict_returns_none(self):
        assert _parse_response_data({}) is None

    def test_adds_response_timestamp_if_missing(self):
        data = {"success": True, "error_message": None}
        result = _parse_response_data(data)

        assert result is not None
        assert "response_timestamp" in result
        assert result["success"] is True

    def test_preserves_existing_response_timestamp(self):
        timestamp = datetime.now(timezone.utc).isoformat()
        data = {"success": True, "response_timestamp": timestamp}
        result = _parse_response_data(data)

        assert result is not None
        assert result["response_timestamp"] == timestamp

    def test_uses_provided_timestamp_for_missing(self):
        timestamp = datetime.now(timezone.utc)
        data = {"success": False}
        result = _parse_response_data(data, timestamp)

        assert result is not None
        assert result["response_timestamp"] == timestamp.isoformat()


class TestAddCorrelation:
    """Test add_correlation function."""

    def test_add_correlation_success(self, sample_correlation, time_service, persist_engine):
        correlation_id = add_correlation(sample_correlation, time_service)

        assert correlation_id == "test_corr_001"

        retrieved = get_correlation(correlation_id)
        assert retrieved is not None
        assert retrieved.correlation_id == correlation_id

    def test_add_correlation_with_metric_data(self, time_service, persist_engine):
        correlation = ServiceCorrelation(
            correlation_id="metric_corr_001",
            service_type="telemetry",
            handler_name="metric_handler",
            action_type="record",
            status=ServiceCorrelationStatus.COMPLETED,
            correlation_type=CorrelationType.METRIC_DATAPOINT,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            timestamp=datetime.now(timezone.utc),
            metric_data=MetricData(
                metric_name="test_metric",
                metric_value=42.5,
                metric_unit="ms",
                metric_type="gauge",
                labels={"env": "test"},
            ),
        )

        correlation_id = add_correlation(correlation, time_service)
        assert correlation_id == "metric_corr_001"

        retrieved = get_correlation(correlation_id)
        assert retrieved is not None
        assert retrieved.metric_data is not None
        assert retrieved.metric_data.metric_name == "test_metric"
        assert retrieved.metric_data.metric_value == 42.5

    def test_add_correlation_with_trace_context(self, time_service, persist_engine):
        correlation = ServiceCorrelation(
            correlation_id="trace_corr_001",
            service_type="api",
            handler_name="trace_handler",
            action_type="trace",
            status=ServiceCorrelationStatus.PENDING,
            correlation_type=CorrelationType.TRACE_SPAN,
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            timestamp=datetime.now(timezone.utc),
            trace_context=TraceContext(
                trace_id="trace_123", span_id="span_456", span_name="test_span", parent_span_id="parent_789"
            ),
        )

        correlation_id = add_correlation(correlation, time_service)
        assert correlation_id == "trace_corr_001"

        retrieved = get_correlation(correlation_id)
        assert retrieved is not None
        assert retrieved.trace_context is not None
        assert retrieved.trace_context.trace_id == "trace_123"
        assert retrieved.trace_context.span_id == "span_456"
        assert retrieved.trace_context.parent_span_id == "parent_789"

    def test_add_correlation_handles_exception(self, sample_correlation, time_service, persist_engine):
        """Exceptions from the persist engine propagate."""
        mock_engine = MagicMock()
        mock_engine.correlation_record.side_effect = Exception("Engine error")
        with patch(
            "ciris_engine.logic.persistence.models.correlations._get_engine",
            return_value=mock_engine,
        ):
            with pytest.raises(Exception) as exc_info:
                add_correlation(sample_correlation, time_service)

            assert "Engine error" in str(exc_info.value)


class TestUpdateCorrelation:
    """Test update_correlation function."""

    def test_update_with_new_signature(self, time_service, persist_engine, sample_correlation):
        """status + response_data update via persist's correlation_update_status.

        Note: persist's contract is `correlation_record` insert-only and
        `correlation_update_status` mutates only `status` + `response_data`,
        so the `tags` and `metric_value` fields on CorrelationUpdateRequest
        are no-ops on the persisted row (production code never sets them on
        update). The legacy SQL implementation did support them.
        """
        add_correlation(sample_correlation, time_service)

        update_request = CorrelationUpdateRequest(
            correlation_id="test_corr_001",
            status=ServiceCorrelationStatus.FAILED,
            response_data={"success": "false", "error_message": "Test error", "execution_time_ms": "200.5"},
        )

        result = update_correlation(update_request, time_service)
        assert result is True

        retrieved = get_correlation("test_corr_001")
        assert retrieved is not None
        assert retrieved.status == ServiceCorrelationStatus.FAILED

    def test_update_status_only(self, time_service, persist_engine, sample_correlation):
        """Status-only updates flow through correlation_update_status cleanly."""
        add_correlation(sample_correlation, time_service)

        update_request = CorrelationUpdateRequest(
            correlation_id="test_corr_001",
            status=ServiceCorrelationStatus.FAILED,
        )

        assert update_correlation(update_request, time_service) is True

        retrieved = get_correlation("test_corr_001")
        assert retrieved is not None
        assert retrieved.status == ServiceCorrelationStatus.FAILED

    def test_update_with_old_signature(self, time_service, persist_engine, sample_correlation):
        add_correlation(sample_correlation, time_service)

        updated_corr = ServiceCorrelation(
            correlation_id="test_corr_001",
            service_type="llm",
            handler_name="test_handler",
            action_type="process",
            response_data=ServiceResponseData(
                success=False,
                error_message="Old signature error",
                execution_time_ms=500.0,
                response_timestamp=datetime.now(timezone.utc),
            ),
            status=ServiceCorrelationStatus.FAILED,
            correlation_type=CorrelationType.SERVICE_INTERACTION,
            timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
        )

        result = update_correlation("test_corr_001", updated_corr, time_service)
        assert result is True

        retrieved = get_correlation("test_corr_001")
        assert retrieved is not None
        assert retrieved.status == ServiceCorrelationStatus.FAILED

    def test_update_nonexistent_returns_false(self, time_service, persist_engine):
        update_request = CorrelationUpdateRequest(correlation_id="nonexistent", status=ServiceCorrelationStatus.FAILED)

        result = update_correlation(update_request, time_service)
        assert result is False

    def test_update_invalid_arguments_raises(self):
        with pytest.raises(ValueError) as exc_info:
            update_correlation("invalid", "not_a_correlation")

        assert "Invalid arguments" in str(exc_info.value)


class TestGetCorrelation:
    """Test get_correlation function."""

    def test_get_existing_correlation(self, sample_correlation, time_service, persist_engine):
        add_correlation(sample_correlation, time_service)

        retrieved = get_correlation("test_corr_001")
        assert retrieved is not None
        assert retrieved.correlation_id == "test_corr_001"
        assert retrieved.service_type == "llm"
        assert retrieved.handler_name == "test_handler"

    def test_get_nonexistent_returns_none(self, persist_engine):
        retrieved = get_correlation("nonexistent")
        assert retrieved is None

    def test_get_handles_engine_error(self, persist_engine):
        """Engine-side errors return None gracefully."""
        mock_engine = MagicMock()
        mock_engine.correlation_get.side_effect = Exception("Engine down")
        with patch(
            "ciris_engine.logic.persistence.models.correlations._get_engine",
            return_value=mock_engine,
        ):
            retrieved = get_correlation("any_id")
            assert retrieved is None


class TestGetCorrelationsByTaskAndAction:
    """Test get_correlations_by_task_and_action function."""

    def test_get_by_task_and_action(self, time_service, persist_engine):
        for i in range(3):
            correlation = ServiceCorrelation(
                correlation_id=f"task_corr_{i}",
                service_type="llm",
                handler_name=f"handler_{i}",
                action_type="process",
                request_data=ServiceRequestData(
                    service_type="llm",
                    method_name="process",
                    task_id="task_123",
                    thought_id=f"thought_{i}",
                    channel_id="channel_789",
                    request_timestamp=datetime.now(timezone.utc),
                ),
                status=ServiceCorrelationStatus.COMPLETED if i < 2 else ServiceCorrelationStatus.FAILED,
                correlation_type=CorrelationType.SERVICE_INTERACTION,
                timestamp=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            add_correlation(correlation, time_service)

        correlations = get_correlations_by_task_and_action("task_123", "process")
        assert len(correlations) == 3

        completed = get_correlations_by_task_and_action(
            "task_123", "process", status=ServiceCorrelationStatus.COMPLETED
        )
        assert len(completed) == 2

        failed = get_correlations_by_task_and_action(
            "task_123", "process", status=ServiceCorrelationStatus.FAILED
        )
        assert len(failed) == 1

    def test_get_empty_list_for_no_matches(self, persist_engine):
        correlations = get_correlations_by_task_and_action("nonexistent_task", "nonexistent_action")
        assert correlations == []


class TestGetCorrelationsByTypeAndTime:
    """Test get_correlations_by_type_and_time function."""

    def test_get_by_type_and_time(self, time_service, persist_engine):
        base_time = datetime.now(timezone.utc)
        for i in range(5):
            correlation = ServiceCorrelation(
                correlation_id=f"typed_{i}",
                service_type="test",
                handler_name="handler",
                action_type="action",
                status=ServiceCorrelationStatus.COMPLETED,
                correlation_type=(
                    CorrelationType.SERVICE_INTERACTION if i % 2 == 0 else CorrelationType.METRIC_DATAPOINT
                ),
                timestamp=base_time - timedelta(hours=i),
                created_at=(base_time - timedelta(hours=i)).isoformat(),
                updated_at=(base_time - timedelta(hours=i)).isoformat(),
            )
            add_correlation(correlation, time_service)

        start_time = (base_time - timedelta(hours=3)).isoformat()
        end_time = base_time.isoformat()

        service_correlations = get_correlations_by_type_and_time(
            correlation_type=CorrelationType.SERVICE_INTERACTION,
            start_time=start_time,
            end_time=end_time,
        )
        assert len(service_correlations) == 2  # i=0, 2 within 3 hours

        metric_correlations = get_correlations_by_type_and_time(
            correlation_type=CorrelationType.METRIC_DATAPOINT,
            start_time=(base_time - timedelta(days=1)).isoformat(),
            end_time=base_time.isoformat(),
        )
        assert len(metric_correlations) == 2  # i=1, 3


class TestGetCorrelationsByChannel:
    """Test get_correlations_by_channel function."""

    def test_get_by_channel(self, time_service, persist_engine):
        channels = ["channel_123", "channel_123", "channel_456", "channel_123"]
        for i, channel_id in enumerate(channels):
            correlation = ServiceCorrelation(
                correlation_id=f"channel_corr_{i}",
                service_type="communication",
                handler_name=f"handler_{i}",
                action_type="speak",
                request_data=ServiceRequestData(
                    service_type="communication",
                    method_name="message",
                    task_id=f"task_{i}",
                    thought_id=f"thought_{i}",
                    channel_id=channel_id,
                    request_timestamp=datetime.now(timezone.utc),
                ),
                status=ServiceCorrelationStatus.COMPLETED,
                correlation_type=CorrelationType.SERVICE_INTERACTION,
                timestamp=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
            )
            add_correlation(correlation, time_service)

        channel_correlations = get_correlations_by_channel("channel_123")
        assert len(channel_correlations) == 3

        other_correlations = get_correlations_by_channel("channel_456")
        assert len(other_correlations) == 1
        assert other_correlations[0].correlation_id == "channel_corr_2"


class TestGetMetricsTimeseries:
    """Test get_metrics_timeseries function."""

    def test_get_metrics_by_name(self, time_service, persist_engine):
        for i in range(5):
            correlation = ServiceCorrelation(
                correlation_id=f"metric_{i}",
                service_type="telemetry",
                handler_name="metric_handler",
                action_type="record",
                status=ServiceCorrelationStatus.COMPLETED,
                correlation_type=CorrelationType.METRIC_DATAPOINT,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                timestamp=datetime.now(timezone.utc) - timedelta(hours=i),
                metric_data=MetricData(
                    metric_name="cpu_usage" if i % 2 == 0 else "memory_usage",
                    metric_value=50.0 + i * 10,
                    metric_unit="percent",
                    metric_type="gauge",
                    labels={},
                ),
            )
            add_correlation(correlation, time_service)

        query = MetricsQuery(
            metric_name="cpu_usage",
            start_time=datetime.now(timezone.utc) - timedelta(days=1),
            end_time=datetime.now(timezone.utc),
        )

        cpu_metrics = get_metrics_timeseries(query)
        assert len(cpu_metrics) == 3  # i=0, 2, 4
        assert all(c.metric_data.metric_name == "cpu_usage" for c in cpu_metrics)

    def test_get_metrics_with_time_range(self, time_service, persist_engine):
        base_time = datetime.now(timezone.utc)

        for i in range(5):
            correlation = ServiceCorrelation(
                correlation_id=f"timed_metric_{i}",
                service_type="telemetry",
                handler_name="metric_handler",
                action_type="record",
                status=ServiceCorrelationStatus.COMPLETED,
                correlation_type=CorrelationType.METRIC_DATAPOINT,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                timestamp=base_time - timedelta(hours=i * 2),
                metric_data=MetricData(
                    metric_name="test_metric",
                    metric_value=float(i),
                    metric_unit="count",
                    metric_type="counter",
                    labels={},
                ),
            )
            add_correlation(correlation, time_service)

        query = MetricsQuery(metric_name="test_metric", start_time=base_time - timedelta(hours=6), end_time=base_time)

        recent_metrics = get_metrics_timeseries(query)
        assert len(recent_metrics) == 4  # i=0,1,2,3 (within 6 hours)


class TestGetRecentCorrelations:
    """Test get_recent_correlations function."""

    def test_get_recent_correlations_default_limit(self, time_service, persist_engine):
        base_time = datetime.now(timezone.utc)

        for i in range(10):
            correlation = ServiceCorrelation(
                correlation_id=f"recent_corr_{i}",
                service_type="test_service",
                handler_name=f"handler_{i}",
                action_type="test_action",
                status=ServiceCorrelationStatus.COMPLETED,
                correlation_type=CorrelationType.SERVICE_INTERACTION,
                timestamp=base_time - timedelta(minutes=i),
                created_at=(base_time - timedelta(minutes=i)).isoformat(),
                updated_at=(base_time - timedelta(minutes=i)).isoformat(),
                retention_policy="raw",
            )
            add_correlation(correlation, time_service)

        recent = get_recent_correlations()

        assert len(recent) == 10
        assert recent[0].correlation_id == "recent_corr_0"
        assert recent[9].correlation_id == "recent_corr_9"

    def test_get_recent_correlations_custom_limit(self, time_service, persist_engine):
        base_time = datetime.now(timezone.utc)

        for i in range(15):
            correlation = ServiceCorrelation(
                correlation_id=f"limited_corr_{i}",
                service_type="test_service",
                handler_name="handler",
                action_type="action",
                status=ServiceCorrelationStatus.COMPLETED,
                correlation_type=CorrelationType.SERVICE_INTERACTION,
                timestamp=base_time - timedelta(seconds=i),
                created_at=(base_time - timedelta(seconds=i)).isoformat(),
                updated_at=(base_time - timedelta(seconds=i)).isoformat(),
            )
            add_correlation(correlation, time_service)

        recent = get_recent_correlations(limit=5)

        assert len(recent) == 5
        for i in range(5):
            assert recent[i].correlation_id == f"limited_corr_{i}"

    def test_get_recent_correlations_mixed_types(self, time_service, persist_engine):
        base_time = datetime.now(timezone.utc)

        correlation_types = [
            CorrelationType.SERVICE_INTERACTION,
            CorrelationType.METRIC_DATAPOINT,
            CorrelationType.LOG_ENTRY,
            CorrelationType.TRACE_SPAN,
        ]

        for i, corr_type in enumerate(correlation_types):
            correlation = ServiceCorrelation(
                correlation_id=f"mixed_corr_{i}",
                service_type="mixed_service",
                handler_name="handler",
                action_type="action",
                status=ServiceCorrelationStatus.COMPLETED,
                correlation_type=corr_type,
                timestamp=base_time - timedelta(minutes=i),
                created_at=(base_time - timedelta(minutes=i)).isoformat(),
                updated_at=(base_time - timedelta(minutes=i)).isoformat(),
            )
            add_correlation(correlation, time_service)

        recent = get_recent_correlations(limit=10)

        assert len(recent) == 4
        types_found = {corr.correlation_type for corr in recent}
        assert types_found == set(correlation_types)

    def test_get_recent_correlations_with_metric_data(self, time_service, persist_engine):
        for i in range(3):
            correlation = ServiceCorrelation(
                correlation_id=f"metric_recent_{i}",
                service_type="telemetry",
                handler_name="metric_handler",
                action_type="record",
                status=ServiceCorrelationStatus.COMPLETED,
                correlation_type=CorrelationType.METRIC_DATAPOINT,
                timestamp=datetime.now(timezone.utc) - timedelta(seconds=i),
                created_at=(datetime.now(timezone.utc) - timedelta(seconds=i)).isoformat(),
                updated_at=(datetime.now(timezone.utc) - timedelta(seconds=i)).isoformat(),
                metric_data=MetricData(
                    metric_name=f"test_metric_{i}",
                    metric_value=float(100 + i),
                    metric_unit="ms",
                    metric_type="gauge",
                    labels={"test": f"value_{i}"},
                ),
            )
            add_correlation(correlation, time_service)

        recent = get_recent_correlations(limit=5)

        assert len(recent) == 3
        for i, corr in enumerate(recent):
            assert corr.metric_data is not None
            assert corr.metric_data.metric_name == f"test_metric_{i}"
            assert corr.metric_data.metric_value == float(100 + i)

    def test_get_recent_correlations_with_trace_context(self, time_service, persist_engine):
        for i in range(2):
            correlation = ServiceCorrelation(
                correlation_id=f"trace_recent_{i}",
                service_type="api",
                handler_name="trace_handler",
                action_type="process",
                status=ServiceCorrelationStatus.COMPLETED,
                correlation_type=CorrelationType.TRACE_SPAN,
                timestamp=datetime.now(timezone.utc) - timedelta(seconds=i),
                created_at=(datetime.now(timezone.utc) - timedelta(seconds=i)).isoformat(),
                updated_at=(datetime.now(timezone.utc) - timedelta(seconds=i)).isoformat(),
                trace_context=TraceContext(
                    trace_id=f"trace_{i}",
                    span_id=f"span_{i}",
                    span_name=f"test_span_{i}",
                    parent_span_id=f"parent_{i}" if i > 0 else None,
                ),
            )
            add_correlation(correlation, time_service)

        recent = get_recent_correlations(limit=5)

        assert len(recent) == 2
        for i, corr in enumerate(recent):
            assert corr.trace_context is not None
            assert corr.trace_context.trace_id == f"trace_{i}"
            assert corr.trace_context.span_id == f"span_{i}"

    def test_get_recent_correlations_with_log_data(self, time_service, persist_engine):
        for i in range(2):
            correlation = ServiceCorrelation(
                correlation_id=f"log_recent_{i}",
                service_type="logging",
                handler_name="log_handler",
                action_type="log",
                status=ServiceCorrelationStatus.COMPLETED,
                correlation_type=CorrelationType.LOG_ENTRY,
                timestamp=datetime.now(timezone.utc) - timedelta(seconds=i),
                created_at=(datetime.now(timezone.utc) - timedelta(seconds=i)).isoformat(),
                updated_at=(datetime.now(timezone.utc) - timedelta(seconds=i)).isoformat(),
                log_data=LogData(
                    log_level="INFO" if i == 0 else "ERROR",
                    log_message=f"Test message {i}",
                    logger_name="test_logger",
                    module_name="test_module",
                    function_name="test_function",
                    line_number=100 + i,
                ),
            )
            add_correlation(correlation, time_service)

        recent = get_recent_correlations(limit=5)

        assert len(recent) == 2
        for i, corr in enumerate(recent):
            assert corr.log_data is not None
            assert corr.log_data.log_level == ("INFO" if i == 0 else "ERROR")

    def test_get_recent_correlations_with_complex_request_data(self, time_service, persist_engine):
        correlation = ServiceCorrelation(
            correlation_id="complex_request",
            service_type="complex_service",
            handler_name="complex_handler",
            action_type="complex_action",
            request_data=ServiceRequestData(
                service_type="complex_service",
                method_name="complex_method",
                task_id="complex_task_123",
                thought_id="complex_thought_456",
                channel_id="complex_channel_789",
                request_timestamp=datetime.now(timezone.utc),
            ),
            response_data=ServiceResponseData(
                success=True,
                execution_time_ms=250.5,
                error_message=None,
                response_timestamp=datetime.now(timezone.utc),
            ),
            status=ServiceCorrelationStatus.COMPLETED,
            correlation_type=CorrelationType.SERVICE_INTERACTION,
            timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc).isoformat(),
            updated_at=datetime.now(timezone.utc).isoformat(),
            tags={"environment": "test", "priority": "high"},
        )

        add_correlation(correlation, time_service)

        recent = get_recent_correlations(limit=1)

        assert len(recent) == 1
        retrieved = recent[0]
        assert retrieved.correlation_id == "complex_request"
        assert retrieved.request_data is not None
        assert retrieved.response_data is not None
        assert retrieved.tags["environment"] == "test"
        assert retrieved.tags["priority"] == "high"

    def test_get_recent_correlations_empty_database(self, persist_engine):
        recent = get_recent_correlations()
        assert recent == []

    def test_get_recent_correlations_handles_engine_error(self, persist_engine):
        """Engine-side errors return an empty list."""
        mock_engine = MagicMock()
        mock_engine.correlation_query.side_effect = Exception("Engine down")
        with patch(
            "ciris_engine.logic.persistence.models.correlations._get_engine",
            return_value=mock_engine,
        ):
            recent = get_recent_correlations()
            assert recent == []

    def test_get_recent_correlations_zero_limit(self, correlation_factory, time_service, persist_engine):
        correlation = correlation_factory("test_zero_limit")
        add_correlation(correlation, time_service)

        recent = get_recent_correlations(limit=0)
        assert recent == []


class TestGetActiveChannelsByAdapter:
    """Test get_active_channels_by_adapter function."""

    def test_get_active_channels_api_adapter(self, correlation_factory, time_service, persist_engine):
        base_time = datetime.now(timezone.utc)
        correlations = [
            correlation_factory(
                "api_1", channel_id="api_channel_123", action_type="speak", timestamp=base_time - timedelta(hours=1)
            ),
            correlation_factory(
                "api_2",
                channel_id="api_channel_456",
                action_type="observe",
                timestamp=base_time - timedelta(minutes=30),
            ),
            correlation_factory(
                "discord_1",
                channel_id="discord_channel_789",
                action_type="speak",
                timestamp=base_time - timedelta(minutes=15),
            ),
        ]

        for corr in correlations:
            add_correlation(corr, time_service)

        channels = get_active_channels_by_adapter("api", since_days=0.1, time_service=time_service)

        assert len(channels) == 2
        channel_ids = [ch.channel_id for ch in channels]
        assert "api_channel_123" in channel_ids
        assert "api_channel_456" in channel_ids
        assert "discord_channel_789" not in channel_ids

    def test_get_active_channels_with_memory_graph(self, correlation_factory, time_service, persist_engine):
        correlation = correlation_factory("api_1", channel_id="api_test_channel", action_type="speak")
        add_correlation(correlation, time_service)

        channels = get_active_channels_by_adapter("api", since_days=1, time_service=time_service)

        channel_ids = [ch.channel_id for ch in channels]
        assert "api_test_channel" in channel_ids
        test_channel = next(ch for ch in channels if ch.channel_id == "api_test_channel")
        assert test_channel.message_count >= 1

    def test_get_active_channels_no_time_service(self, correlation_factory, persist_engine):
        correlation = correlation_factory("api_1", channel_id="api_no_time", action_type="speak")
        add_correlation(correlation)

        channels = get_active_channels_by_adapter("api", since_days=1)

        channel_ids = [ch.channel_id for ch in channels]
        assert "api_no_time" in channel_ids

    def test_get_active_channels_engine_error(self, time_service, persist_engine):
        """Engine errors return empty list."""
        mock_engine = MagicMock()
        mock_engine.correlation_query.side_effect = Exception("Engine down")
        with patch(
            "ciris_engine.logic.persistence.models.correlations._get_engine",
            return_value=mock_engine,
        ):
            channels = get_active_channels_by_adapter("api", since_days=1, time_service=time_service)
            assert channels == []


class TestGetChannelLastActivity:
    """Test get_channel_last_activity function."""

    def test_get_channel_last_activity_found(self, correlation_factory, time_service, persist_engine):
        target_time = datetime.now(timezone.utc) - timedelta(hours=2)
        correlation = correlation_factory(
            "activity_1", channel_id="api_active_channel", action_type="speak", timestamp=target_time
        )
        add_correlation(correlation, time_service)

        last_activity = get_channel_last_activity("api_active_channel")

        assert last_activity is not None
        assert abs((last_activity - target_time).total_seconds()) < 5

    def test_get_channel_last_activity_not_found(self, persist_engine):
        last_activity = get_channel_last_activity("nonexistent_channel")
        assert last_activity is None

    def test_get_channel_last_activity_memory_graph_fallback(self, correlation_factory, time_service, persist_engine):
        correlation = correlation_factory("memory_1", channel_id="api_memory_channel", action_type="speak")
        add_correlation(correlation, time_service)

        last_activity = get_channel_last_activity("api_memory_channel")
        assert last_activity is not None

    def test_get_channel_last_activity_engine_error(self, persist_engine):
        """Engine errors return None."""
        mock_engine = MagicMock()
        mock_engine.correlation_query.side_effect = Exception("Engine down")
        with patch(
            "ciris_engine.logic.persistence.models.correlations._get_engine",
            return_value=mock_engine,
        ):
            last_activity = get_channel_last_activity("any_channel")
            assert last_activity is None


class TestIsAdminChannel:
    """Test is_admin_channel function."""

    def test_is_admin_channel_true_for_admin_role(self, correlation_factory, time_service, persist_engine):
        correlation = correlation_factory(
            "admin_1", channel_id="api_admin_channel", tags={"user_role": "ADMIN", "test": "true"}
        )
        add_correlation(correlation, time_service)

        assert is_admin_channel("api_admin_channel") is True

    def test_is_admin_channel_true_for_authority_role(self, correlation_factory, time_service, persist_engine):
        correlation = correlation_factory("auth_1", channel_id="api_authority_channel", tags={"user_role": "AUTHORITY"})
        add_correlation(correlation, time_service)

        assert is_admin_channel("api_authority_channel") is True

    def test_is_admin_channel_true_for_system_admin(self, correlation_factory, time_service, persist_engine):
        correlation = correlation_factory(
            "sys_1", channel_id="api_sysadmin_channel", tags={"user_role": "SYSTEM_ADMIN"}
        )
        add_correlation(correlation, time_service)

        assert is_admin_channel("api_sysadmin_channel") is True

    def test_is_admin_channel_true_for_is_admin_flag(self, correlation_factory, time_service, persist_engine):
        """Identifying admin channel by is_admin flag (Python-side comparison now allows string '1')."""
        correlation = correlation_factory("flag_1", channel_id="api_isadmin_channel", tags={"is_admin": "1"})
        add_correlation(correlation, time_service)

        assert is_admin_channel("api_isadmin_channel") is True

    def test_is_admin_channel_true_for_auth_role_nested(self, correlation_factory, time_service, persist_engine):
        correlation = correlation_factory(
            "nested_1", channel_id="api_nested_channel", tags={"auth.role": "ADMIN"}
        )
        add_correlation(correlation, time_service)

        result = is_admin_channel("api_nested_channel")
        assert isinstance(result, bool)
        # `auth.role` flat key matches the admin role path
        assert result is True

    def test_is_admin_channel_false_for_regular_user(self, correlation_factory, time_service, persist_engine):
        correlation = correlation_factory("user_1", channel_id="api_user_channel", tags={"user_role": "USER"})
        add_correlation(correlation, time_service)

        assert is_admin_channel("api_user_channel") is False

    def test_is_admin_channel_false_for_discord_channel(self, correlation_factory, time_service, persist_engine):
        correlation = correlation_factory("discord_1", channel_id="discord_admin_channel", tags={"user_role": "ADMIN"})
        add_correlation(correlation, time_service)

        assert is_admin_channel("discord_admin_channel") is False

    def test_is_admin_channel_false_for_nonexistent_channel(self, persist_engine):
        assert is_admin_channel("api_nonexistent") is False

    def test_is_admin_channel_engine_error(self, persist_engine):
        """Engine errors return False (deny by default)."""
        mock_engine = MagicMock()
        mock_engine.correlation_query.side_effect = Exception("Engine down")
        with patch(
            "ciris_engine.logic.persistence.models.correlations._get_engine",
            return_value=mock_engine,
        ):
            assert is_admin_channel("api_any_channel") is False


class TestAddCorrelationWithTelemetry:
    """Test add_correlation_with_telemetry function."""

    @pytest.mark.asyncio
    async def test_add_correlation_with_telemetry_success(
        self, correlation_factory, time_service, telemetry_service, persist_engine
    ):
        correlation = correlation_factory("telemetry_1")

        correlation_id = await add_correlation_with_telemetry(correlation, time_service, telemetry_service)

        assert correlation_id == "telemetry_1"

        stored = get_correlation(correlation_id)
        assert stored is not None
        assert stored.correlation_id == correlation_id

        assert telemetry_service._store_correlation.called

    @pytest.mark.asyncio
    async def test_add_correlation_with_telemetry_no_services(self, correlation_factory, persist_engine):
        correlation = correlation_factory("no_services_1")

        correlation_id = await add_correlation_with_telemetry(correlation)

        assert correlation_id == "no_services_1"

        stored = get_correlation(correlation_id)
        assert stored is not None

    @pytest.mark.asyncio
    async def test_add_correlation_with_telemetry_engine_error(
        self, correlation_factory, time_service, telemetry_service, persist_engine
    ):
        """Engine errors during persistence propagate."""
        correlation = correlation_factory("error_1")
        mock_engine = MagicMock()
        mock_engine.correlation_record.side_effect = Exception("Engine down")
        with patch(
            "ciris_engine.logic.persistence.models.correlations._get_engine",
            return_value=mock_engine,
        ):
            with pytest.raises(Exception):
                await add_correlation_with_telemetry(correlation, time_service, telemetry_service)
