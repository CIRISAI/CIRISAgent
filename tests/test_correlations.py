"""
Tests for correlations persistence model - ensuring type safety and robustness.

These tests align with CIRIS principles:
- Type safety (proper schema usage)
- Database integrity
- Error handling
- Backward compatibility
"""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from ciris_engine.logic.persistence.models.correlations import (
    _parse_response_data,
    _update_correlation_impl,
    add_correlation,
    get_correlation,
    get_correlations_by_channel,
    get_correlations_by_task_and_action,
    get_correlations_by_type_and_time,
    get_metrics_timeseries,
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
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    # Initialize database schema
    from ciris_engine.logic.persistence.db import get_db_connection

    with get_db_connection(db_path=db_path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS service_correlations (
                correlation_id TEXT PRIMARY KEY,
                service_type TEXT,
                handler_name TEXT,
                action_type TEXT,
                request_data TEXT,
                response_data TEXT,
                status TEXT,
                created_at TEXT,
                updated_at TEXT,
                correlation_type TEXT,
                timestamp TEXT,
                metric_name TEXT,
                metric_value REAL,
                log_level TEXT,
                trace_id TEXT,
                span_id TEXT,
                parent_span_id TEXT,
                tags TEXT,
                retention_policy TEXT
            )
        """
        )
        conn.commit()

    yield db_path

    # Cleanup
    Path(db_path).unlink(missing_ok=True)


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


class TestParseResponseData:
    """Test _parse_response_data function."""

    def test_parse_none_returns_none(self):
        """Test that None input returns None."""
        assert _parse_response_data(None) is None

    def test_parse_empty_dict_returns_none(self):
        """Test that empty dict returns None."""
        assert _parse_response_data({}) is None

    def test_adds_response_timestamp_if_missing(self):
        """Test that response_timestamp is added for backward compatibility."""
        data = {"success": True, "error_message": None}
        result = _parse_response_data(data)

        assert result is not None
        assert "response_timestamp" in result
        assert result["success"] is True

    def test_preserves_existing_response_timestamp(self):
        """Test that existing response_timestamp is preserved."""
        timestamp = datetime.now(timezone.utc).isoformat()
        data = {"success": True, "response_timestamp": timestamp}
        result = _parse_response_data(data)

        assert result is not None
        assert result["response_timestamp"] == timestamp

    def test_uses_provided_timestamp_for_missing(self):
        """Test that provided timestamp is used when response_timestamp missing."""
        timestamp = datetime.now(timezone.utc)
        data = {"success": False}
        result = _parse_response_data(data, timestamp)

        assert result is not None
        assert result["response_timestamp"] == timestamp.isoformat()


class TestAddCorrelation:
    """Test add_correlation function."""

    def test_add_correlation_success(self, sample_correlation, time_service, temp_db):
        """Test successful correlation addition."""
        correlation_id = add_correlation(sample_correlation, time_service, db_path=temp_db)

        assert correlation_id == "test_corr_001"

        # Verify it was added to database
        retrieved = get_correlation(correlation_id, db_path=temp_db)
        assert retrieved is not None
        assert retrieved.correlation_id == correlation_id

    def test_add_correlation_with_metric_data(self, time_service, temp_db):
        """Test adding correlation with metric data."""
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

        correlation_id = add_correlation(correlation, time_service, db_path=temp_db)
        assert correlation_id == "metric_corr_001"

        retrieved = get_correlation(correlation_id, db_path=temp_db)
        assert retrieved is not None
        assert retrieved.metric_data is not None
        assert retrieved.metric_data.metric_name == "test_metric"
        assert retrieved.metric_data.metric_value == 42.5

    def test_add_correlation_with_trace_context(self, time_service, temp_db):
        """Test adding correlation with trace context."""
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

        correlation_id = add_correlation(correlation, time_service, db_path=temp_db)
        assert correlation_id == "trace_corr_001"

        retrieved = get_correlation(correlation_id, db_path=temp_db)
        assert retrieved is not None
        assert retrieved.trace_context is not None
        assert retrieved.trace_context.trace_id == "trace_123"
        assert retrieved.trace_context.span_id == "span_456"
        assert retrieved.trace_context.parent_span_id == "parent_789"

    def test_add_correlation_handles_exception(self, sample_correlation, time_service):
        """Test that exceptions are handled properly."""
        with patch("ciris_engine.logic.persistence.models.correlations.get_db_connection") as mock_db:
            mock_db.side_effect = Exception("Database error")

            with pytest.raises(Exception) as exc_info:
                add_correlation(sample_correlation, time_service)

            assert "Database error" in str(exc_info.value)


class TestUpdateCorrelation:
    """Test update_correlation function."""

    def test_update_with_new_signature(self, time_service, temp_db, sample_correlation):
        """Test update with new CorrelationUpdateRequest signature."""
        # First add a correlation
        add_correlation(sample_correlation, time_service, db_path=temp_db)

        # Update it
        update_request = CorrelationUpdateRequest(
            correlation_id="test_corr_001",
            status=ServiceCorrelationStatus.FAILED,
            response_data={"success": "false", "error_message": "Test error", "execution_time_ms": "200.5"},
            metric_value=200.5,
            tags={"updated": "true"},
        )

        result = update_correlation(update_request, time_service, db_path=temp_db)
        assert result is True

        # Verify update
        retrieved = get_correlation("test_corr_001", db_path=temp_db)
        assert retrieved is not None
        assert retrieved.status == ServiceCorrelationStatus.FAILED
        assert retrieved.tags["updated"] == "true"

    def test_update_with_old_signature(self, time_service, temp_db, sample_correlation):
        """Test backward compatibility with old signature."""
        # First add a correlation
        add_correlation(sample_correlation, time_service, db_path=temp_db)

        # Create an updated correlation
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

        # Use old signature
        result = update_correlation("test_corr_001", updated_corr, time_service, db_path=temp_db)
        assert result is True

        # Verify update
        retrieved = get_correlation("test_corr_001", db_path=temp_db)
        assert retrieved is not None
        assert retrieved.status == ServiceCorrelationStatus.FAILED

    def test_update_nonexistent_returns_false(self, time_service, temp_db):
        """Test updating non-existent correlation returns False."""
        update_request = CorrelationUpdateRequest(correlation_id="nonexistent", status=ServiceCorrelationStatus.FAILED)

        result = update_correlation(update_request, time_service, db_path=temp_db)
        assert result is False

    def test_update_invalid_arguments_raises(self):
        """Test that invalid arguments raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            update_correlation("invalid", "not_a_correlation")

        assert "Invalid arguments" in str(exc_info.value)


class TestGetCorrelation:
    """Test get_correlation function."""

    def test_get_existing_correlation(self, sample_correlation, time_service, temp_db):
        """Test retrieving an existing correlation."""
        add_correlation(sample_correlation, time_service, db_path=temp_db)

        retrieved = get_correlation("test_corr_001", db_path=temp_db)
        assert retrieved is not None
        assert retrieved.correlation_id == "test_corr_001"
        assert retrieved.service_type == "llm"
        assert retrieved.handler_name == "test_handler"

    def test_get_nonexistent_returns_none(self, temp_db):
        """Test that non-existent correlation returns None."""
        retrieved = get_correlation("nonexistent", db_path=temp_db)
        assert retrieved is None

    def test_get_handles_malformed_data(self, temp_db):
        """Test handling of malformed database data."""
        # Insert malformed data directly
        from ciris_engine.logic.persistence.db import get_db_connection

        with get_db_connection(db_path=temp_db) as conn:
            conn.execute(
                """
                INSERT INTO service_correlations (
                    correlation_id, service_type, handler_name, action_type,
                    request_data, response_data, status, correlation_type,
                    timestamp, retention_policy
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    "malformed_001",
                    "test",
                    "handler",
                    "action",
                    "invalid_json",
                    "{not valid json}",
                    "COMPLETED",
                    "service_interaction",
                    datetime.now(timezone.utc).isoformat(),
                    "raw",
                ),
            )
            conn.commit()

        # Should handle gracefully
        retrieved = get_correlation("malformed_001", db_path=temp_db)
        assert retrieved is None  # Returns None on parse error


class TestGetCorrelationsByTaskAndAction:
    """Test get_correlations_by_task_and_action function."""

    def test_get_by_task_and_action(self, time_service, temp_db):
        """Test retrieving correlations by task and action."""
        # Add multiple correlations
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
            add_correlation(correlation, time_service, db_path=temp_db)

        # Get all correlations for task
        correlations = get_correlations_by_task_and_action("task_123", "process", db_path=temp_db)
        assert len(correlations) == 3

        # Get only completed correlations
        completed = get_correlations_by_task_and_action(
            "task_123", "process", status=ServiceCorrelationStatus.COMPLETED, db_path=temp_db
        )
        assert len(completed) == 2

        # Get only failed correlations
        failed = get_correlations_by_task_and_action(
            "task_123", "process", status=ServiceCorrelationStatus.FAILED, db_path=temp_db
        )
        assert len(failed) == 1

    def test_get_empty_list_for_no_matches(self, temp_db):
        """Test that empty list is returned when no matches."""
        correlations = get_correlations_by_task_and_action("nonexistent_task", "nonexistent_action", db_path=temp_db)
        assert correlations == []


class TestGetCorrelationsByTypeAndTime:
    """Test get_correlations_by_type_and_time function."""

    def test_get_by_type_and_time(self, time_service, temp_db):
        """Test getting correlations by type and time range."""
        # Add correlations with different timestamps
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
            add_correlation(correlation, time_service, db_path=temp_db)

        # Get service interactions from last 3 hours
        start_time = base_time - timedelta(hours=3)
        end_time = base_time

        service_correlations = get_correlations_by_type_and_time(
            correlation_type=CorrelationType.SERVICE_INTERACTION,
            start_time=start_time,
            end_time=end_time,
            db_path=temp_db,
        )
        assert len(service_correlations) == 2  # i=0,2 within 3 hours

        # Get all metrics
        metric_correlations = get_correlations_by_type_and_time(
            correlation_type=CorrelationType.METRIC_DATAPOINT,
            start_time=base_time - timedelta(days=1),
            end_time=base_time,
            db_path=temp_db,
        )
        assert len(metric_correlations) == 2  # i=1,3


class TestGetCorrelationsByChannel:
    """Test get_correlations_by_channel function."""

    def test_get_by_channel(self, time_service, temp_db):
        """Test getting correlations by channel ID."""
        # Add correlations for different channels
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
            add_correlation(correlation, time_service, db_path=temp_db)

        # Get correlations for channel_123
        channel_correlations = get_correlations_by_channel("channel_123", db_path=temp_db)
        assert len(channel_correlations) == 3

        # Get correlations for channel_456
        other_correlations = get_correlations_by_channel("channel_456", db_path=temp_db)
        assert len(other_correlations) == 1
        assert other_correlations[0].correlation_id == "channel_corr_2"


class TestGetMetricsTimeseries:
    """Test get_metrics_timeseries function."""

    def test_get_metrics_by_name(self, time_service, temp_db):
        """Test getting metrics timeseries by name."""
        # Add metric correlations
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
            add_correlation(correlation, time_service, db_path=temp_db)

        # Query CPU metrics
        query = MetricsQuery(
            metric_name="cpu_usage",
            start_time=datetime.now(timezone.utc) - timedelta(days=1),
            end_time=datetime.now(timezone.utc),
        )

        cpu_metrics = get_metrics_timeseries(query, db_path=temp_db)
        assert len(cpu_metrics) == 3  # i=0, 2, 4
        assert all(c.metric_data.metric_name == "cpu_usage" for c in cpu_metrics)

    def test_get_metrics_with_time_range(self, time_service, temp_db):
        """Test getting metrics with time range."""
        base_time = datetime.now(timezone.utc)

        # Add metrics at different times
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
            add_correlation(correlation, time_service, db_path=temp_db)

        # Query last 6 hours
        query = MetricsQuery(metric_name="test_metric", start_time=base_time - timedelta(hours=6), end_time=base_time)

        recent_metrics = get_metrics_timeseries(query, db_path=temp_db)
        assert len(recent_metrics) == 4  # i=0,1,2,3 (within 6 hours)
