"""
Telemetry format converters - extracted from telemetry.py to reduce file size.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple


def convert_to_prometheus(data: Dict) -> str:
    """
    Convert telemetry data to Prometheus format.

    Refactored to reduce cognitive complexity by extracting helper methods.
    """
    converter = PrometheusConverter()
    return converter.convert(data)


def convert_to_graphite(data: Dict) -> str:
    """
    Convert telemetry data to Graphite format.

    Refactored to reduce cognitive complexity by extracting helper methods.
    """
    converter = GraphiteConverter()
    return converter.convert(data)


class PrometheusConverter:
    """Converter for Prometheus format with reduced complexity."""

    def __init__(self):
        self.lines: List[str] = []

    def convert(self, data: Dict) -> str:
        """Convert data to Prometheus format."""
        self._process_dict(data, "")
        return "\n".join(self.lines)

    def _process_dict(self, data: Dict, prefix: str) -> None:
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
        return f"ciris_{key}".replace(".", "_").replace("-", "_")

    def _add_boolean_metric(self, key: str, value: bool) -> None:
        """Add a boolean metric as 0 or 1."""
        metric_name = self._sanitize_metric_name(key)
        self.lines.append(f"{metric_name} {1 if value else 0}")

    def _add_numeric_metric(self, key: str, value: float) -> None:
        """Add a numeric metric."""
        metric_name = self._sanitize_metric_name(key)
        self.lines.append(f"{metric_name} {value}")


class GraphiteConverter:
    """Converter for Graphite format with reduced complexity."""

    def __init__(self):
        self.lines: List[str] = []
        self.timestamp = int(datetime.now(timezone.utc).timestamp())

    def convert(self, data: Dict) -> str:
        """Convert data to Graphite format."""
        self._process_dict(data, "ciris")
        return "\n".join(self.lines)

    def _process_dict(self, data: Dict, prefix: str) -> None:
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
