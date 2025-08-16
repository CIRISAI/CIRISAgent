"""Base test class for service metrics testing."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Set
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class BaseMetricsTest:
    """Base test class for testing service metrics collection."""

    # Base metrics that every service should have
    BASE_METRICS = {"uptime_seconds", "request_count", "error_count", "error_rate", "healthy"}

    # Metrics that should always be non-negative
    NON_NEGATIVE_METRICS = {
        "uptime_seconds",
        "request_count",
        "error_count",
        "error_rate",
        "total_calls",
        "total_failures",
        "total_successes",
        "cache_hits",
        "cache_misses",
        "api_calls",
        "tokens_used",
        "days_running",
        "time_requests",
        "auth_attempts",
        "auth_successes",
        "auth_failures",
    }

    # Metrics that should be between 0 and 1 (rates/ratios)
    RATIO_METRICS = {
        "error_rate",
        "success_rate",
        "hit_rate",
        "cache_hit_rate",
        "auth_success_rate",
        "api_success_rate",
        "healthy",
    }

    @pytest.fixture
    def mock_time_service(self):
        """Mock time service for consistent testing."""
        time_service = MagicMock()
        time_service.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        time_service.now_iso.return_value = "2024-01-01T12:00:00+00:00"
        time_service.timestamp.return_value = 1704110400.0
        return time_service

    @pytest.fixture
    def mock_memory_service(self):
        """Mock memory service."""
        memory = AsyncMock()
        memory.memorize.return_value = None
        memory.recall.return_value = None
        memory.get_metrics = AsyncMock(return_value={})
        return memory

    @pytest.fixture
    def mock_config_service(self):
        """Mock config service."""
        config = AsyncMock()
        config.get_config.return_value = None
        config.set_config.return_value = None
        config.list_configs.return_value = {}
        return config

    @pytest.fixture
    def mock_audit_service(self):
        """Mock audit service."""
        audit = AsyncMock()
        audit.log_event.return_value = None
        audit.get_metrics = AsyncMock(return_value={})
        return audit

    def assert_metrics_exist(self, metrics: Dict[str, float], expected_metrics: Set[str]):
        """Assert that expected metrics exist in the metrics dict."""
        missing = expected_metrics - set(metrics.keys())
        extra = set(metrics.keys()) - expected_metrics - self.BASE_METRICS

        assert not missing, f"Missing expected metrics: {missing}"
        # Extra metrics are ok, services can have more than expected

    def assert_base_metrics_present(self, metrics: Dict[str, float]):
        """Assert that all base metrics are present."""
        missing_base = self.BASE_METRICS - set(metrics.keys())
        assert not missing_base, f"Missing base metrics: {missing_base}"

    def assert_all_metrics_are_floats(self, metrics: Dict[str, float]):
        """Assert all metric values are floats."""
        for key, value in metrics.items():
            assert isinstance(value, (int, float)), f"Metric {key} is not numeric: {type(value)}"
            # Ensure it can be converted to float
            float(value)

    def assert_metrics_valid_ranges(self, metrics: Dict[str, float]):
        """Assert metrics are within valid ranges."""
        for key, value in metrics.items():
            # Check non-negative metrics
            if any(pattern in key for pattern in self.NON_NEGATIVE_METRICS):
                assert value >= 0, f"Metric {key} should be non-negative: {value}"

            # Check ratio metrics (0-1 range, or slightly above 1 for rates)
            if any(pattern in key for pattern in self.RATIO_METRICS):
                if "rate" in key and key != "error_rate":
                    # Some rates can exceed 1 (e.g., processing_rate_per_sec)
                    assert value >= 0, f"Rate metric {key} should be non-negative: {value}"
                else:
                    # True ratios should be 0-1
                    assert 0 <= value <= 1.0001, f"Ratio metric {key} should be 0-1: {value}"

    async def get_service_metrics(self, service: Any) -> Dict[str, float]:
        """Get metrics from a service (handles both sync and async)."""
        if hasattr(service, "get_metrics"):
            result = service.get_metrics()
            if asyncio.iscoroutine(result):
                return await result
            return result
        elif hasattr(service, "_collect_custom_metrics"):
            return service._collect_custom_metrics()
        else:
            raise AttributeError(f"Service {service.__class__.__name__} has no metrics method")

    async def verify_service_metrics_base_requirements(self, service: Any):
        """Verify that a service meets base metric requirements.

        This is a helper method, not a test itself. Test methods should call this
        with their own service fixtures.
        """
        metrics = await self.get_service_metrics(service)

        # Basic checks
        assert isinstance(metrics, dict), "Metrics should be a dict"
        assert len(metrics) > 0, "Metrics should not be empty"

        # Check all values are numeric
        self.assert_all_metrics_are_floats(metrics)

        # Check base metrics present
        self.assert_base_metrics_present(metrics)

        # Check valid ranges
        self.assert_metrics_valid_ranges(metrics)

        return metrics

    def create_service_with_activity(self, service_class, *args, **kwargs):
        """Create a service and simulate some activity for metric generation."""
        service = service_class(*args, **kwargs)

        # Simulate some activity if the service tracks it
        if hasattr(service, "_track_request"):
            for _ in range(5):
                service._track_request()

        if hasattr(service, "_track_error"):
            service._track_error(Exception("Test error"))

        # Set start time for uptime calculation
        if hasattr(service, "_start_time"):
            service._start_time = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)

        return service

    async def assert_metric_increases(
        self, service: Any, metric_name: str, action: callable, min_increase: float = 1.0
    ):
        """Assert that a metric increases after an action."""
        metrics_before = await self.get_service_metrics(service)
        initial_value = metrics_before.get(metric_name, 0)

        # Perform action
        result = action()
        if asyncio.iscoroutine(result):
            await result

        metrics_after = await self.get_service_metrics(service)
        final_value = metrics_after.get(metric_name, 0)

        assert (
            final_value >= initial_value + min_increase
        ), f"Metric {metric_name} did not increase by at least {min_increase}: {initial_value} -> {final_value}"

    def assert_required_metrics(self, metrics: Dict[str, float], required: Set[str]):
        """Assert that all required metrics are present and valid."""
        for metric in required:
            assert metric in metrics, f"Required metric '{metric}' not found"
            assert isinstance(
                metrics[metric], (int, float)
            ), f"Metric '{metric}' is not numeric: {type(metrics[metric])}"
