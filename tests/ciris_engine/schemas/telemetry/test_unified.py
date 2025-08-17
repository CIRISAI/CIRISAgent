"""
Unit tests for unified telemetry schemas.

Tests all schema models to achieve 100% coverage.
"""

from datetime import datetime, timezone
from typing import Dict

import pytest
from pydantic import ValidationError

from ciris_engine.schemas.telemetry.unified import MetricDataPoint, ResourceMetricWithStats, ResourceTimeSeriesData


class TestMetricDataPoint:
    """Test MetricDataPoint schema."""

    def test_create_with_required_fields(self):
        """Test creating MetricDataPoint with required fields."""
        timestamp = datetime.now(timezone.utc)
        point = MetricDataPoint(timestamp=timestamp, value=42.5)

        assert point.timestamp == timestamp
        assert point.value == 42.5
        assert point.tags == {}

    def test_create_with_tags(self):
        """Test creating MetricDataPoint with tags."""
        timestamp = datetime.now(timezone.utc)
        tags = {"service": "telemetry", "environment": "production"}
        point = MetricDataPoint(timestamp=timestamp, value=99.9, tags=tags)

        assert point.tags == tags

    def test_timestamp_serialization(self):
        """Test timestamp is serialized to ISO format."""
        timestamp = datetime(2024, 1, 15, 10, 30, 45, tzinfo=timezone.utc)
        point = MetricDataPoint(timestamp=timestamp, value=10.0)

        # Serialize to dict
        data = point.model_dump()
        assert data["timestamp"] == "2024-01-15T10:30:45+00:00"

    def test_missing_required_fields(self):
        """Test validation error for missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            MetricDataPoint(value=10.0)  # Missing timestamp

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("timestamp",) for error in errors)

    def test_invalid_value_type(self):
        """Test validation error for invalid value type."""
        with pytest.raises(ValidationError) as exc_info:
            MetricDataPoint(timestamp=datetime.now(timezone.utc), value="not a number")

        errors = exc_info.value.errors()
        assert any("value" in str(error) for error in errors)


class TestResourceMetricWithStats:
    """Test ResourceMetricWithStats schema."""

    def test_create_with_valid_data(self):
        """Test creating ResourceMetricWithStats with valid data."""
        timestamp = datetime.now(timezone.utc)
        data_points = [
            MetricDataPoint(timestamp=timestamp, value=10.0),
            MetricDataPoint(timestamp=timestamp, value=20.0),
        ]
        stats = {"min": 10.0, "max": 20.0, "avg": 15.0, "current": 20.0}

        metric = ResourceMetricWithStats(data=data_points, stats=stats, unit="percent")

        assert len(metric.data) == 2
        assert metric.stats == stats
        assert metric.unit == "percent"

    def test_empty_data_list(self):
        """Test creating ResourceMetricWithStats with empty data list."""
        metric = ResourceMetricWithStats(data=[], stats={"min": 0, "max": 0, "avg": 0}, unit="MB")

        assert metric.data == []
        assert metric.unit == "MB"

    def test_missing_required_fields(self):
        """Test validation error for missing required fields."""
        with pytest.raises(ValidationError) as exc_info:
            ResourceMetricWithStats(data=[], stats={})  # Missing unit

        errors = exc_info.value.errors()
        assert any(error["loc"] == ("unit",) for error in errors)

    def test_serialization(self):
        """Test serialization of ResourceMetricWithStats."""
        timestamp = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        metric = ResourceMetricWithStats(
            data=[MetricDataPoint(timestamp=timestamp, value=50.0)], stats={"current": 50.0}, unit="GB"
        )

        data = metric.model_dump()
        assert data["unit"] == "GB"
        assert len(data["data"]) == 1
        assert data["data"][0]["timestamp"] == "2024-01-15T10:00:00+00:00"


class TestResourceTimeSeriesData:
    """Test ResourceTimeSeriesData schema."""

    def test_create_with_all_fields(self):
        """Test creating ResourceTimeSeriesData with all fields."""
        timestamp = datetime.now(timezone.utc)
        data_points = [
            MetricDataPoint(timestamp=timestamp, value=10.0),
            MetricDataPoint(timestamp=timestamp, value=20.0),
            MetricDataPoint(timestamp=timestamp, value=30.0),
        ]

        series = ResourceTimeSeriesData(
            metric_name="cpu_usage",
            data_points=data_points,
            unit="percent",
            current=30.0,
            average=20.0,
            min=10.0,
            max=30.0,
            percentile_95=28.5,
            trend="up",
        )

        assert series.metric_name == "cpu_usage"
        assert len(series.data_points) == 3
        assert series.unit == "percent"
        assert series.current == 30.0
        assert series.average == 20.0
        assert series.min == 10.0
        assert series.max == 30.0
        assert series.percentile_95 == 28.5
        assert series.trend == "up"

    def test_trend_values(self):
        """Test different trend values."""
        timestamp = datetime.now(timezone.utc)
        base_data = {
            "metric_name": "memory",
            "data_points": [MetricDataPoint(timestamp=timestamp, value=100)],
            "unit": "MB",
            "current": 100,
            "average": 100,
            "min": 100,
            "max": 100,
            "percentile_95": 100,
        }

        # Test each valid trend
        for trend in ["up", "down", "stable"]:
            series = ResourceTimeSeriesData(**base_data, trend=trend)
            assert series.trend == trend

    def test_statistics_validation(self):
        """Test statistics fields accept various numeric values."""
        timestamp = datetime.now(timezone.utc)
        series = ResourceTimeSeriesData(
            metric_name="disk_io",
            data_points=[MetricDataPoint(timestamp=timestamp, value=0)],
            unit="IOPS",
            current=0.0,
            average=0.0,
            min=0.0,
            max=0.0,
            percentile_95=0.0,
            trend="stable",
        )

        assert series.current == 0.0
        assert series.min == 0.0

    def test_missing_required_statistics(self):
        """Test validation error for missing statistics fields."""
        timestamp = datetime.now(timezone.utc)

        with pytest.raises(ValidationError) as exc_info:
            ResourceTimeSeriesData(
                metric_name="test",
                data_points=[MetricDataPoint(timestamp=timestamp, value=1)],
                unit="test",
                # Missing: current, average, min, max, percentile_95, trend
            )

        errors = exc_info.value.errors()
        required_fields = {"current", "average", "min", "max", "percentile_95", "trend"}
        error_fields = {error["loc"][0] for error in errors if len(error["loc"]) > 0}
        assert required_fields.issubset(error_fields)

    def test_serialization_with_nested_timestamps(self):
        """Test serialization handles nested timestamp serialization."""
        timestamp1 = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        timestamp2 = datetime(2024, 1, 15, 10, 5, 0, tzinfo=timezone.utc)

        series = ResourceTimeSeriesData(
            metric_name="network_throughput",
            data_points=[
                MetricDataPoint(timestamp=timestamp1, value=1000),
                MetricDataPoint(timestamp=timestamp2, value=1500),
            ],
            unit="Mbps",
            current=1500,
            average=1250,
            min=1000,
            max=1500,
            percentile_95=1450,
            trend="up",
        )

        data = series.model_dump()
        assert data["data_points"][0]["timestamp"] == "2024-01-15T10:00:00+00:00"
        assert data["data_points"][1]["timestamp"] == "2024-01-15T10:05:00+00:00"

    def test_edge_case_empty_data_points(self):
        """Test with empty data points list."""
        series = ResourceTimeSeriesData(
            metric_name="no_data",
            data_points=[],
            unit="none",
            current=0,
            average=0,
            min=0,
            max=0,
            percentile_95=0,
            trend="stable",
        )

        assert series.data_points == []
        assert series.metric_name == "no_data"
