"""
Resource history helpers - modular functions for telemetry resource tracking.

Following CIRIS principles:
- No Exceptions: Each function has single responsibility
- Adaptive Coherence: Functions can evolve independently
- Type Safety: All inputs and outputs are typed
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from ciris_engine.logic.adapters.api.routes.telemetry_models import (
    ResourceDataPoint,
    ResourceMetricData,
    ResourceMetricStats,
)
from ciris_engine.schemas.services.graph.telemetry import MetricRecord


class ResourceMetricsCollector:
    """Collects and processes resource metrics following single responsibility principle."""

    @staticmethod
    async def fetch_metric_data(
        telemetry_service: Any, metric_name: str, start_time: datetime, end_time: datetime
    ) -> List[MetricRecord]:
        """Fetch a single metric's data from telemetry service."""
        if not hasattr(telemetry_service, "query_metrics"):
            return []

        try:
            result: List[MetricRecord] = await telemetry_service.query_metrics(
                metric_name=metric_name, start_time=start_time, end_time=end_time
            )
            return result
        except Exception:
            return []

    @staticmethod
    async def fetch_all_resource_metrics(
        telemetry_service: Any, start_time: datetime, end_time: datetime
    ) -> Tuple[List[MetricRecord], List[MetricRecord], List[MetricRecord]]:
        """Fetch all resource metrics concurrently."""
        cpu_data = await ResourceMetricsCollector.fetch_metric_data(
            telemetry_service, "cpu_percent", start_time, end_time
        )
        memory_data = await ResourceMetricsCollector.fetch_metric_data(
            telemetry_service, "memory_mb", start_time, end_time
        )
        disk_data = await ResourceMetricsCollector.fetch_metric_data(
            telemetry_service, "disk_usage_bytes", start_time, end_time
        )
        return cpu_data, memory_data, disk_data


class MetricValueExtractor:
    """Extracts values from metric data following single responsibility."""

    @staticmethod
    def extract_values(metric_data: Optional[List[MetricRecord]]) -> List[float]:
        """Extract numeric values from metric data."""
        if not metric_data:
            return [0]

        values = [float(d.value) for d in metric_data]
        return values if values else [0]

    @staticmethod
    def extract_all_values(
        cpu_data: List[MetricRecord], memory_data: List[MetricRecord], disk_data: List[MetricRecord]
    ) -> Tuple[List[float], List[float], List[float]]:
        """Extract values from all metric types."""
        return (
            MetricValueExtractor.extract_values(cpu_data),
            MetricValueExtractor.extract_values(memory_data),
            MetricValueExtractor.extract_values(disk_data),
        )


class MetricStatisticsCalculator:
    """Calculates statistics for metrics following single responsibility."""

    @staticmethod
    def calculate_basic_stats(values: List[float]) -> Dict[str, float]:
        """Calculate min, max, avg, current for a list of values."""
        if not values:
            return {"min": 0, "max": 0, "avg": 0, "current": 0}

        return {"min": min(values), "max": max(values), "avg": sum(values) / len(values), "current": values[-1]}

    @staticmethod
    def calculate_percentile(values: List[float], percentile: float = 0.95) -> float:
        """Calculate the specified percentile of values."""
        if not values:
            return 0

        sorted_vals = sorted(values)
        index = int(len(sorted_vals) * percentile)
        return sorted_vals[min(index, len(sorted_vals) - 1)]

    @staticmethod
    def calculate_trend(values: List[float]) -> str:
        """
        Determine trend direction from values.

        Returns: 'increasing', 'decreasing', or 'stable'
        """
        if len(values) < 2:
            return "stable"

        # Get recent and older samples
        sample_size = 5 if len(values) >= 5 else 2
        recent = values[-sample_size:]
        older = values[:-sample_size] if len(values) > sample_size else values[0:1]

        # Calculate averages
        recent_avg = sum(recent) / len(recent)
        older_avg = sum(older) / len(older)

        # Determine trend with 10% threshold
        if recent_avg > older_avg * 1.1:
            return "increasing"
        elif recent_avg < older_avg * 0.9:
            return "decreasing"
        return "stable"


class ResourceDataPointBuilder:
    """Builds typed ResourceDataPoint objects following type safety principle."""

    @staticmethod
    def build_data_points(metric_data: Optional[List[MetricRecord]], default_timestamp: str) -> List[ResourceDataPoint]:
        """Convert raw metric data to typed ResourceDataPoint objects."""
        if not metric_data:
            return []

        return [
            ResourceDataPoint(
                timestamp=d.timestamp.isoformat() if hasattr(d.timestamp, "isoformat") else str(d.timestamp),
                value=float(d.value),
            )
            for d in metric_data
        ]

    @staticmethod
    def build_all_data_points(
        cpu_data: List[MetricRecord],
        memory_data: List[MetricRecord],
        disk_data: List[MetricRecord],
        default_timestamp: str,
    ) -> Tuple[List[ResourceDataPoint], List[ResourceDataPoint], List[ResourceDataPoint]]:
        """Build data points for all resource types."""
        return (
            ResourceDataPointBuilder.build_data_points(cpu_data, default_timestamp),
            ResourceDataPointBuilder.build_data_points(memory_data, default_timestamp),
            ResourceDataPointBuilder.build_data_points(disk_data, default_timestamp),
        )


class ResourceMetricBuilder:
    """Builds complete ResourceMetricData objects following composition principle."""

    @staticmethod
    def build_metric(data_points: List[ResourceDataPoint], values: List[float], unit: str) -> ResourceMetricData:
        """Build a complete ResourceMetricData with stats."""
        stats_dict = MetricStatisticsCalculator.calculate_basic_stats(values)

        return ResourceMetricData(
            data=data_points,
            stats=ResourceMetricStats(
                min=stats_dict["min"], max=stats_dict["max"], avg=stats_dict["avg"], current=stats_dict["current"]
            ),
            unit=unit,
        )

    @staticmethod
    def build_all_metrics(
        cpu_points: List[ResourceDataPoint],
        cpu_values: List[float],
        memory_points: List[ResourceDataPoint],
        memory_values: List[float],
        disk_points: List[ResourceDataPoint],
        disk_values: List[float],
    ) -> Tuple[ResourceMetricData, ResourceMetricData, ResourceMetricData]:
        """Build ResourceMetricData for all resource types."""
        return (
            ResourceMetricBuilder.build_metric(cpu_points, cpu_values, "percent"),
            ResourceMetricBuilder.build_metric(memory_points, memory_values, "MB"),
            ResourceMetricBuilder.build_metric(disk_points, disk_values, "GB"),
        )
