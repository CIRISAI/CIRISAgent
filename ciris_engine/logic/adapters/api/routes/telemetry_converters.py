"""
Telemetry format converters - extracted from telemetry.py to reduce file size.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from ciris_engine.schemas.types import JSONDict


def convert_to_prometheus(data: JSONDict) -> str:
    """
    Convert telemetry data to Prometheus format.

    Refactored to reduce cognitive complexity by extracting helper methods.
    """
    converter = PrometheusConverter()
    return converter.convert(data)


def convert_to_graphite(data: JSONDict) -> str:
    """
    Convert telemetry data to Graphite format.

    Refactored to reduce cognitive complexity by extracting helper methods.
    """
    converter = GraphiteConverter()
    return converter.convert(data)


class PrometheusConverter:
    """Converter for Prometheus format with reduced complexity."""

    def __init__(self) -> None:
        self.lines: List[str] = []
        self.metrics_seen: set[str] = set()

    def convert(self, data: JSONDict) -> str:
        """Convert data to Prometheus format."""
        self._process_dict(data, "")
        return "\n".join(self.lines)

    def _process_dict(self, data: JSONDict, prefix: str) -> None:
        """Process a dictionary recursively."""
        for key, value in data.items():
            if self._should_skip_key(key):
                continue
            self._process_value(key, value, prefix)

    def _should_skip_key(self, key: str) -> bool:
        """Check if a key should be skipped."""
        return key.startswith("_")

    def _process_value(self, key: str, value: Any, prefix: str) -> None:
        """Process a single value based on its type."""
        # Special handling for custom_metrics - merge into parent namespace
        if key == "custom_metrics" and isinstance(value, dict):
            # Process custom_metrics directly into the parent prefix
            # This avoids creating separate "custom_metrics" namespaces
            self._process_dict(value, prefix)
            return

        full_key = self._build_key(key, prefix)

        if isinstance(value, dict):
            self._process_dict(value, full_key)
        elif isinstance(value, bool):
            self._add_boolean_metric(full_key, value)
        elif isinstance(value, (int, float)):
            self._add_numeric_metric(full_key, value)

    def _build_key(self, key: str, prefix: str) -> str:
        """Build the full key with prefix."""
        return f"{prefix}_{key}" if prefix else key

    def _sanitize_metric_name(self, key: str) -> str:
        """Sanitize metric name for Prometheus."""
        return f"ciris_{key}".replace(".", "_").replace("-", "_").lower()

    def _add_metric_metadata(self, metric_name: str, metric_type: str = "gauge") -> None:
        """Add HELP and TYPE lines for a metric if not already added."""
        if metric_name not in self.metrics_seen:
            self.metrics_seen.add(metric_name)
            # Add HELP line
            help_text = metric_name.replace("_", " ").replace("ciris ", "").title()
            self.lines.append(f"# HELP {metric_name} {help_text}")
            # Add TYPE line
            self.lines.append(f"# TYPE {metric_name} {metric_type}")

    def _add_boolean_metric(self, key: str, value: bool) -> None:
        """Add a boolean metric as 0 or 1."""
        metric_name = self._sanitize_metric_name(key)
        self._add_metric_metadata(metric_name, "gauge")
        self.lines.append(f"{metric_name} {1 if value else 0}")

    def _add_numeric_metric(self, key: str, value: float) -> None:
        """Add a numeric metric."""
        metric_name = self._sanitize_metric_name(key)
        # Determine metric type based on name patterns
        metric_type = "counter" if any(x in key.lower() for x in ["total", "count", "sum"]) else "gauge"
        self._add_metric_metadata(metric_name, metric_type)
        self.lines.append(f"{metric_name} {value}")


class GraphiteConverter:
    """Converter for Graphite format with reduced complexity."""

    def __init__(self) -> None:
        self.lines: List[str] = []
        self.timestamp = int(datetime.now(timezone.utc).timestamp())

    def convert(self, data: JSONDict) -> str:
        """Convert data to Graphite format."""
        self._process_dict(data, "ciris")
        return "\n".join(self.lines)

    def _process_dict(self, data: JSONDict, prefix: str) -> None:
        """Process a dictionary recursively."""
        for key, value in data.items():
            if self._should_skip_key(key):
                continue
            self._process_value(key, value, prefix)

    def _should_skip_key(self, key: str) -> bool:
        """Check if a key should be skipped."""
        return key.startswith("_")

    def _process_value(self, key: str, value: Any, prefix: str) -> None:
        """Process a single value based on its type."""
        full_key = f"{prefix}.{key}"

        if isinstance(value, dict):
            self._process_dict(value, full_key)
        elif isinstance(value, bool):
            self._add_metric(full_key, 1 if value else 0)
        elif isinstance(value, (int, float)):
            self._add_metric(full_key, value)

    def _add_metric(self, key: str, value: float) -> None:
        """Add a metric with timestamp."""
        self.lines.append(f"{key} {value} {self.timestamp}")
