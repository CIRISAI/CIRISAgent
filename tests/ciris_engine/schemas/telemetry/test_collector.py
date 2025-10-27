"""Tests for telemetry collector schemas."""

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.telemetry.collector import (
    HealthDetails,
    HealthStatus,
    MetricEntry,
    ProcessingQueueStatus,
    ProcessorStateSnapshot,
    SingleStepResult,
)


class TestHealthDetails:
    """Tests for HealthDetails schema."""

    def test_valid_health_details(self):
        """Test creating valid HealthDetails."""
        details = HealthDetails(
            adapters="healthy",
            services="healthy",
            processor="healthy",
            error=None,
        )

        assert details.adapters == "healthy"
        assert details.services == "healthy"
        assert details.processor == "healthy"
        assert details.error is None

    def test_health_details_with_defaults(self):
        """Test HealthDetails with default values."""
        details = HealthDetails()

        assert details.adapters == "unknown"
        assert details.services == "unknown"
        assert details.processor == "unknown"
        assert details.error is None

    def test_health_details_with_error(self):
        """Test HealthDetails with error message."""
        details = HealthDetails(
            adapters="error",
            services="degraded",
            processor="critical",
            error="Multiple services offline",
        )

        assert details.adapters == "error"
        assert details.services == "degraded"
        assert details.processor == "critical"
        assert details.error == "Multiple services offline"


class TestHealthStatus:
    """Tests for HealthStatus schema."""

    def test_valid_health_status(self):
        """Test creating valid HealthStatus."""
        status = HealthStatus(
            overall="healthy",
            details=HealthDetails(
                adapters="healthy",
                services="healthy",
                processor="healthy",
            ),
        )

        assert status.overall == "healthy"
        assert status.details.adapters == "healthy"
        assert status.details.services == "healthy"
        assert status.details.processor == "healthy"

    def test_health_status_with_default_details(self):
        """Test HealthStatus with default details."""
        status = HealthStatus(overall="unknown")

        assert status.overall == "unknown"
        assert status.details.adapters == "unknown"
        assert status.details.services == "unknown"
        assert status.details.processor == "unknown"

    def test_health_status_degraded(self):
        """Test degraded health status."""
        status = HealthStatus(
            overall="degraded",
            details=HealthDetails(
                adapters="healthy",
                services="degraded",
                processor="healthy",
                error="Some services degraded",
            ),
        )

        assert status.overall == "degraded"
        assert status.details.services == "degraded"
        assert status.details.error == "Some services degraded"


class TestMetricEntry:
    """Tests for MetricEntry schema."""

    def test_valid_metric_entry(self):
        """Test creating valid MetricEntry."""
        entry = MetricEntry(
            timestamp="2025-01-27T10:00:00Z",
            value=42.5,
            tags={"service": "llm", "operation": "call"},
        )

        assert entry.timestamp == "2025-01-27T10:00:00Z"
        assert entry.value == 42.5
        assert entry.tags == {"service": "llm", "operation": "call"}

    def test_metric_entry_without_tags(self):
        """Test MetricEntry without tags."""
        entry = MetricEntry(
            timestamp="2025-01-27T10:00:00Z",
            value=100.0,
        )

        assert entry.timestamp == "2025-01-27T10:00:00Z"
        assert entry.value == 100.0
        assert entry.tags == {}

    def test_metric_entry_missing_required_fields(self):
        """Test that missing required fields raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            MetricEntry(timestamp="2025-01-27T10:00:00Z")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"][0] == "value"


class TestProcessorStateSnapshot:
    """Tests for ProcessorStateSnapshot schema."""

    def test_valid_processor_state(self):
        """Test creating valid ProcessorStateSnapshot."""
        state = ProcessorStateSnapshot(
            thoughts_pending=5,
            thoughts_processing=2,
            current_round=3,
        )

        assert state.thoughts_pending == 5
        assert state.thoughts_processing == 2
        assert state.current_round == 3

    def test_processor_state_with_defaults(self):
        """Test ProcessorStateSnapshot with default values."""
        state = ProcessorStateSnapshot()

        assert state.thoughts_pending == 0
        assert state.thoughts_processing == 0
        assert state.current_round == 0


class TestSingleStepResult:
    """Tests for SingleStepResult schema."""

    def test_valid_single_step_result_completed(self):
        """Test creating valid completed SingleStepResult."""
        before = ProcessorStateSnapshot(
            thoughts_pending=3,
            thoughts_processing=0,
            current_round=0,
        )
        after = ProcessorStateSnapshot(
            thoughts_pending=2,
            thoughts_processing=1,
            current_round=1,
        )

        result = SingleStepResult(
            status="completed",
            round_number=1,
            execution_time_ms=150,
            before_state=before,
            after_state=after,
            processing_result={"thoughts_processed": 1},
            timestamp="2025-01-27T10:00:00Z",
            summary={"success": True, "count": 1},
        )

        assert result.status == "completed"
        assert result.round_number == 1
        assert result.execution_time_ms == 150
        assert result.before_state.thoughts_pending == 3
        assert result.after_state.thoughts_pending == 2
        assert result.timestamp == "2025-01-27T10:00:00Z"

    def test_single_step_result_with_error(self):
        """Test SingleStepResult with error."""
        result = SingleStepResult(
            status="error",
            error="Processing failed: timeout",
            timestamp="2025-01-27T10:00:00Z",
        )

        assert result.status == "error"
        assert result.error == "Processing failed: timeout"
        assert result.round_number is None
        assert result.execution_time_ms is None

    def test_single_step_result_missing_required_fields(self):
        """Test that missing required fields raises ValidationError."""
        with pytest.raises(ValidationError) as exc_info:
            SingleStepResult(status="completed")

        errors = exc_info.value.errors()
        assert len(errors) == 1
        assert errors[0]["loc"][0] == "timestamp"


class TestProcessingQueueStatus:
    """Tests for ProcessingQueueStatus schema."""

    def test_valid_queue_status_available(self):
        """Test creating valid ProcessingQueueStatus for available queue."""
        status = ProcessingQueueStatus(
            status="available",
            size=5,
            capacity=100,
            oldest_item_age="2m30s",
        )

        assert status.status == "available"
        assert status.size == 5
        assert status.capacity == 100
        assert status.oldest_item_age == "2m30s"

    def test_queue_status_unavailable(self):
        """Test ProcessingQueueStatus for unavailable queue."""
        status = ProcessingQueueStatus(status="unavailable")

        assert status.status == "unavailable"
        assert status.size is None
        assert status.capacity is None
        assert status.oldest_item_age is None

    def test_queue_status_with_all_none(self):
        """Test ProcessingQueueStatus with all optional fields None."""
        status = ProcessingQueueStatus()

        assert status.status is None
        assert status.size is None
        assert status.capacity is None
        assert status.oldest_item_age is None

    def test_queue_status_with_unlimited_capacity(self):
        """Test ProcessingQueueStatus with unlimited capacity."""
        status = ProcessingQueueStatus(
            status="available",
            size=10,
            capacity="unlimited",
        )

        assert status.status == "available"
        assert status.size == 10
        assert status.capacity == "unlimited"
