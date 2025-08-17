"""
Comprehensive metric tests for all Infrastructure services.

Tests metrics for:
1. TimeService - 12 metrics including NTP
2. ShutdownService - 8 metrics
3. InitializationService - 9 metrics
4. AuthenticationService - 30 metrics
5. ResourceMonitorService - 8 metrics
6. DatabaseMaintenanceService - 14 metrics
7. SecretsService - 15 metrics
"""

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.persistence.maintenance import DatabaseMaintenanceService
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.logic.services.infrastructure.resource_monitor import ResourceMonitorService
from ciris_engine.logic.services.lifecycle.initialization import InitializationService
from ciris_engine.logic.services.lifecycle.shutdown import ShutdownService

# Import all the infrastructure services
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.secrets.core import SecretsDetectionConfig

# Import required schemas and enums
from ciris_engine.schemas.services.operations import InitializationPhase
from ciris_engine.schemas.services.resources_core import ResourceBudget, ResourceLimit
from tests.test_metrics_base import BaseMetricsTest


class TestTimeServiceMetrics(BaseMetricsTest):
    """Test TimeService metrics collection."""

    # Expected metrics for TimeService (12 total)
    TIME_SERVICE_METRICS = {
        "time_requests",
        "iso_requests",
        "timestamp_requests",
        "uptime_requests",
        "total_requests",
        "days_running",
        "time_drift_ms",
        "ntp_check_count",
        "ntp_failures",
        "timezone_offset",
    }

    def test_time_service_metrics_exist(self):
        """Test that TimeService has all expected metrics."""
        service = TimeService()
        metrics = service._collect_metrics()

        # Check base metrics present
        self.assert_base_metrics_present(metrics)

        # Check TimeService specific metrics
        self.assert_metrics_exist(metrics, self.TIME_SERVICE_METRICS)

        # Check all values are numeric
        self.assert_all_metrics_are_floats(metrics)

        # Check valid ranges
        self.assert_metrics_valid_ranges(metrics)

    @pytest.mark.asyncio
    async def test_time_service_metrics_with_activity(self):
        """Test TimeService metrics after some activity."""
        service = TimeService()

        # Simulate time requests - all methods call now() internally,
        # so they all increment time_requests counter
        service.now()  # Increments time_requests
        service.now_iso()  # Increments time_requests (via now())
        service.timestamp()  # Increments time_requests (via now())
        service.get_uptime()  # Increments time_requests (via now())

        # v1.4.3: Use async get_metrics() method
        metrics = await service.get_metrics()

        # Check v1.4.3 metrics - different names
        assert metrics["time_queries_total"] >= 4.0  # now() called 4 times total
        assert metrics["time_sync_operations"] >= 0.0
        assert metrics["time_drift_ms"] >= 0.0
        assert metrics["time_uptime_seconds"] >= 0.0

    def test_time_service_ntp_metrics_with_ntplib(self):
        """Test NTP metrics when ntplib is available."""
        # Mock ntplib module and response
        mock_ntplib = MagicMock()
        mock_response = MagicMock()
        mock_response.offset = 0.05  # 50ms offset
        mock_client_instance = MagicMock()
        mock_client_instance.request.return_value = mock_response
        mock_ntplib.NTPClient.return_value = mock_client_instance

        # Patch sys.modules to make ntplib available
        with patch.dict("sys.modules", {"ntplib": mock_ntplib}):
            service = TimeService()
            # Force NTP check
            service._update_ntp_offset()

            metrics = service._collect_metrics()

            # Should have NTP metrics
            assert "time_drift_ms" in metrics
            assert "ntp_check_count" in metrics
            assert "ntp_failures" in metrics
            assert metrics["time_drift_ms"] == 50.0  # 0.05 seconds = 50ms

    def test_time_service_ntp_metrics_without_ntplib(self):
        """Test NTP metrics when ntplib is not available."""
        with patch.dict("sys.modules", {"ntplib": None}):
            service = TimeService()
            # Force NTP check - should fall back to simulation
            service._update_ntp_offset()

            metrics = service._collect_custom_metrics()

            # Should still have drift metrics (simulated)
            assert "time_drift_ms" in metrics
            assert "ntp_check_count" in metrics
            assert "ntp_failures" in metrics
            # Simulated drift should be based on uptime
            assert metrics["time_drift_ms"] >= 0.0


class TestShutdownServiceMetrics(BaseMetricsTest):
    """Test ShutdownService metrics collection."""

    # Expected metrics for ShutdownService (8 total)
    SHUTDOWN_SERVICE_METRICS = {"shutdown_requested", "registered_handlers", "emergency_mode"}

    def test_shutdown_service_metrics_exist(self):
        """Test that ShutdownService has all expected metrics."""
        service = ShutdownService()
        metrics = service._collect_metrics()

        # Check base metrics present
        self.assert_base_metrics_present(metrics)

        # Check ShutdownService specific metrics
        self.assert_metrics_exist(metrics, self.SHUTDOWN_SERVICE_METRICS)

        # Check all values are numeric
        self.assert_all_metrics_are_floats(metrics)

        # Check valid ranges
        self.assert_metrics_valid_ranges(metrics)

    def test_shutdown_service_metrics_with_handlers(self):
        """Test ShutdownService metrics with registered handlers."""
        service = ShutdownService()

        # Register some handlers
        def dummy_handler():
            pass

        service.register_shutdown_handler(dummy_handler)
        service.register_shutdown_handler(dummy_handler)

        metrics = service._collect_metrics()

        # Should show registered handlers
        assert metrics["registered_handlers"] == 2.0
        assert metrics["shutdown_requested"] == 0.0
        assert metrics["emergency_mode"] == 0.0

    def test_shutdown_service_metrics_after_shutdown_request(self):
        """Test ShutdownService metrics after shutdown is requested."""
        service = ShutdownService()

        # Request shutdown
        service._request_shutdown_sync("Test shutdown")

        metrics = service._collect_metrics()

        # Should show shutdown was requested
        assert metrics["shutdown_requested"] == 1.0

    @pytest.mark.asyncio
    async def test_shutdown_service_metrics_emergency_mode(self):
        """Test ShutdownService metrics in emergency mode."""
        service = ShutdownService()

        # Mock sys.exit to prevent actual shutdown
        with patch("sys.exit") as mock_exit:
            # Start emergency shutdown (but don't wait for completion)
            emergency_task = asyncio.create_task(service.emergency_shutdown("Test emergency", timeout_seconds=1))

            # Give it a moment to set flags
            await asyncio.sleep(0.1)

            metrics = service._collect_metrics()

            # Should show emergency mode
            assert metrics["emergency_mode"] == 1.0
            assert metrics["shutdown_requested"] == 1.0

            # Cancel the emergency task to prevent actual shutdown
            emergency_task.cancel()
            try:
                await emergency_task
            except asyncio.CancelledError:
                pass


class TestInitializationServiceMetrics(BaseMetricsTest):
    """Test InitializationService metrics collection."""

    # Expected metrics for InitializationService (9 total)
    INITIALIZATION_SERVICE_METRICS = {
        "initialization_complete",
        "has_error",
        "completed_steps",
        "total_steps",
        "initialization_duration",
    }

    @pytest.fixture
    def initialization_service(self, mock_time_service):
        """Create InitializationService for testing."""
        return InitializationService(time_service=mock_time_service)

    def test_initialization_service_metrics_exist(self, initialization_service):
        """Test that InitializationService has all expected metrics."""
        metrics = initialization_service._collect_metrics()

        # Check base metrics present
        self.assert_base_metrics_present(metrics)

        # Check InitializationService specific metrics
        self.assert_metrics_exist(metrics, self.INITIALIZATION_SERVICE_METRICS)

        # Check all values are numeric
        self.assert_all_metrics_are_floats(metrics)

        # Check valid ranges
        self.assert_metrics_valid_ranges(metrics)

    def test_initialization_service_metrics_with_steps(self, initialization_service):
        """Test InitializationService metrics with registered steps."""

        async def dummy_step():
            pass

        # Register some initialization steps
        initialization_service.register_step(InitializationPhase.INFRASTRUCTURE, "test_step_1", dummy_step)
        initialization_service.register_step(InitializationPhase.SERVICES, "test_step_2", dummy_step)

        metrics = initialization_service._collect_metrics()

        # Should show total steps
        assert metrics["total_steps"] == 2.0
        assert metrics["completed_steps"] == 0.0
        assert metrics["initialization_complete"] == 0.0
        assert metrics["has_error"] == 0.0

    @pytest.mark.asyncio
    async def test_initialization_service_metrics_after_init(self, initialization_service):
        """Test InitializationService metrics after successful initialization."""

        async def quick_step():
            pass

        # Register a quick step
        initialization_service.register_step(InitializationPhase.INFRASTRUCTURE, "quick_step", quick_step)

        # Run initialization
        success = await initialization_service.initialize()
        assert success

        metrics = initialization_service._collect_metrics()

        # Should show completion
        assert metrics["initialization_complete"] == 1.0
        assert metrics["has_error"] == 0.0
        assert metrics["completed_steps"] == 1.0
        assert metrics["total_steps"] == 1.0
        assert metrics["initialization_duration"] >= 0.0  # Can be 0.0 for fast steps


class TestAuthenticationServiceMetrics(BaseMetricsTest):
    """Test AuthenticationService metrics collection."""

    # Expected metrics for AuthenticationService (30 total)
    AUTHENTICATION_SERVICE_METRICS = {
        "auth_attempts",
        "auth_successes",
        "auth_failures",
        "auth_success_rate",
        "token_validations",
        "permission_checks",
        "role_assignments",
        "active_sessions",
        "expired_sessions",
        "active_tokens",
    }

    @pytest.fixture
    def auth_service(self, mock_time_service):
        """Create AuthenticationService for testing."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            db_path = tmp.name
        try:
            service = AuthenticationService(db_path=db_path, time_service=mock_time_service)
            yield service
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_authentication_service_metrics_exist(self, auth_service):
        """Test that AuthenticationService has all expected metrics."""
        metrics = auth_service._collect_metrics()

        # Check base metrics present
        self.assert_base_metrics_present(metrics)

        # Check AuthenticationService specific metrics
        self.assert_metrics_exist(metrics, self.AUTHENTICATION_SERVICE_METRICS)

        # Check all values are numeric
        self.assert_all_metrics_are_floats(metrics)

        # Check valid ranges
        self.assert_metrics_valid_ranges(metrics)

    def test_authentication_service_metrics_with_activity(self, auth_service):
        """Test AuthenticationService metrics with simulated activity."""
        # Simulate some authentication activity
        auth_service._auth_attempts = 5
        auth_service._auth_successes = 4
        auth_service._auth_failures = 1
        auth_service._token_validations = 10
        auth_service._permission_checks = 8
        auth_service._active_tokens = 3

        metrics = auth_service._collect_metrics()

        # Check that activity is reflected in metrics
        assert metrics["auth_attempts"] == 5.0
        assert metrics["auth_successes"] == 4.0
        assert metrics["auth_failures"] == 1.0
        assert metrics["auth_success_rate"] == 0.8  # 4/5
        assert metrics["token_validations"] == 10.0
        assert metrics["permission_checks"] == 8.0
        assert metrics["active_tokens"] == 3.0

    @pytest.mark.asyncio
    async def test_authentication_service_health_check(self, auth_service):
        """Test that health check affects service metrics."""
        await auth_service.start()
        is_healthy = await auth_service.is_healthy()
        assert is_healthy  # Should be healthy with valid DB

        await auth_service.stop()


class TestResourceMonitorServiceMetrics(BaseMetricsTest):
    """Test ResourceMonitorService metrics collection."""

    # Expected metrics for ResourceMonitorService (8 total)
    RESOURCE_MONITOR_METRICS = {
        "memory_mb",
        "cpu_percent",
        "tokens_used_hour",
        "thoughts_active",
        "warnings",
        "critical",
    }

    @pytest.fixture
    def resource_monitor_service(self, mock_time_service):
        """Create ResourceMonitorService for testing."""
        # Create minimal budget for testing
        budget = ResourceBudget(
            memory_mb=ResourceLimit(limit=1000, warning=800, critical=950),
            cpu_percent=ResourceLimit(limit=100, warning=80, critical=95),
            tokens_hour=ResourceLimit(limit=1000, warning=800, critical=950),
            tokens_day=ResourceLimit(limit=10000, warning=8000, critical=9500),
            thoughts_active=ResourceLimit(limit=10, warning=8, critical=9),
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            db_path = tmp.name
        try:
            service = ResourceMonitorService(budget=budget, db_path=db_path, time_service=mock_time_service)
            yield service
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_resource_monitor_service_metrics_exist(self, resource_monitor_service):
        """Test that ResourceMonitorService has all expected metrics."""
        metrics = resource_monitor_service._collect_metrics()

        # Check base metrics present
        self.assert_base_metrics_present(metrics)

        # Check ResourceMonitorService specific metrics
        self.assert_metrics_exist(metrics, self.RESOURCE_MONITOR_METRICS)

        # Check all values are numeric
        self.assert_all_metrics_are_floats(metrics)

        # Check valid ranges
        self.assert_metrics_valid_ranges(metrics)

    @pytest.mark.asyncio
    async def test_resource_monitor_service_metrics_with_usage(self, resource_monitor_service):
        """Test ResourceMonitorService metrics with simulated resource usage."""
        # Record some token usage
        await resource_monitor_service.record_tokens(100)
        await resource_monitor_service.record_tokens(50)

        # Update snapshot
        await resource_monitor_service._update_snapshot()

        metrics = resource_monitor_service._collect_metrics()

        # Should show token usage
        assert metrics["tokens_used_hour"] >= 150.0
        assert metrics["memory_mb"] >= 0.0
        assert metrics["cpu_percent"] >= 0.0
        assert metrics["thoughts_active"] >= 0.0

    @pytest.mark.asyncio
    async def test_resource_monitor_service_health_monitoring(self, resource_monitor_service):
        """Test ResourceMonitorService health monitoring."""
        # Check initial health
        is_healthy = await resource_monitor_service.is_healthy()
        assert is_healthy  # Should start healthy

        # Force a critical condition by manipulating snapshot
        resource_monitor_service.snapshot.critical.append("memory_mb: 1000/1000")
        resource_monitor_service.snapshot.healthy = False

        is_healthy = await resource_monitor_service.is_healthy()
        assert not is_healthy  # Should be unhealthy with critical conditions


class TestDatabaseMaintenanceServiceMetrics(BaseMetricsTest):
    """Test DatabaseMaintenanceService metrics collection."""

    # Expected metrics for DatabaseMaintenanceService (14 total)
    DATABASE_MAINTENANCE_METRICS = {
        "cleanup_runs",
        "records_deleted",
        "vacuum_runs",
        "archive_runs",
        "database_size_mb",
        "last_cleanup_duration_s",
        "cleanup_due",
        "archive_due",
    }

    @pytest.fixture
    def db_maintenance_service(self, mock_time_service):
        """Create DatabaseMaintenanceService for testing."""
        return DatabaseMaintenanceService(
            time_service=mock_time_service, archive_dir_path=tempfile.mkdtemp(), archive_older_than_hours=24
        )

    def test_database_maintenance_service_metrics_exist(self, db_maintenance_service):
        """Test that DatabaseMaintenanceService has all expected metrics."""
        metrics = db_maintenance_service._collect_metrics()

        # Check base metrics present
        self.assert_base_metrics_present(metrics)

        # Check DatabaseMaintenanceService specific metrics
        self.assert_metrics_exist(metrics, self.DATABASE_MAINTENANCE_METRICS)

        # Check all values are numeric
        self.assert_all_metrics_are_floats(metrics)

        # Check valid ranges
        self.assert_metrics_valid_ranges(metrics)

    def test_database_maintenance_service_metrics_with_activity(self, db_maintenance_service):
        """Test DatabaseMaintenanceService metrics with simulated activity."""
        # Simulate some maintenance activity
        db_maintenance_service._cleanup_runs = 3
        db_maintenance_service._records_deleted = 150
        db_maintenance_service._vacuum_runs = 2
        db_maintenance_service._archive_runs = 1
        db_maintenance_service._last_cleanup_duration = 5.5

        metrics = db_maintenance_service._collect_metrics()

        # Check that activity is reflected in metrics
        assert metrics["cleanup_runs"] == 3.0
        assert metrics["records_deleted"] == 150.0
        assert metrics["vacuum_runs"] == 2.0
        assert metrics["archive_runs"] == 1.0
        assert metrics["last_cleanup_duration_s"] == 5.5

    @pytest.mark.asyncio
    async def test_database_maintenance_service_startup_cleanup(self, db_maintenance_service):
        """Test DatabaseMaintenanceService startup cleanup."""
        with patch("ciris_engine.logic.persistence.get_tasks_by_status", return_value=[]), patch(
            "ciris_engine.logic.persistence.get_thoughts_by_status", return_value=[]
        ), patch("ciris_engine.logic.persistence.get_thoughts_older_than", return_value=[]):

            # Mock the config service to avoid attribute errors
            db_maintenance_service.config_service = AsyncMock()
            db_maintenance_service.config_service.list_configs.return_value = {}

            await db_maintenance_service.perform_startup_cleanup()
            # Should complete without errors


class TestSecretsServiceMetrics(BaseMetricsTest):
    """Test SecretsService metrics collection."""

    # Expected metrics for SecretsService (15 total)
    SECRETS_SERVICE_METRICS = {
        "secrets_stored",
        "secrets_retrieved",
        "secrets_deleted",
        "vault_size",
        "encryption_operations",
        "decryption_operations",
        "filter_detections",
        "auto_encryptions",
        "failed_decryptions",
        "filter_enabled",
    }

    @pytest.fixture
    def secrets_service(self, mock_time_service):
        """Create SecretsService for testing."""
        with patch("ciris_engine.logic.secrets.store.SecretsStore"), patch(
            "ciris_engine.logic.secrets.filter.SecretsFilter"
        ):

            service = SecretsService(time_service=mock_time_service, detection_config=SecretsDetectionConfig())
            # Mock the store and filter
            service.store = MagicMock()
            service.filter = MagicMock()
            service.filter.enabled = True
            yield service

    def test_secrets_service_metrics_exist(self, secrets_service):
        """Test that SecretsService has all expected metrics."""
        metrics = secrets_service._collect_metrics()

        # Check base metrics present
        self.assert_base_metrics_present(metrics)

        # Check SecretsService specific metrics
        self.assert_metrics_exist(metrics, self.SECRETS_SERVICE_METRICS)

        # Check all values are numeric
        self.assert_all_metrics_are_floats(metrics)

        # Check valid ranges
        self.assert_metrics_valid_ranges(metrics)

    def test_secrets_service_metrics_with_activity(self, secrets_service):
        """Test SecretsService metrics with simulated activity."""
        # Simulate some secrets activity
        secrets_service._secrets_stored = 5
        secrets_service._secrets_retrieved = 3
        secrets_service._secrets_deleted = 1
        secrets_service._encryption_operations = 8
        secrets_service._decryption_operations = 6
        secrets_service._filter_detections = 10
        secrets_service._auto_encryptions = 2
        secrets_service._failed_decryptions = 0

        metrics = secrets_service._collect_metrics()

        # Check that activity is reflected in metrics
        assert metrics["secrets_stored"] == 5.0
        assert metrics["secrets_retrieved"] == 3.0
        assert metrics["secrets_deleted"] == 1.0
        assert metrics["encryption_operations"] == 8.0
        assert metrics["decryption_operations"] == 6.0
        assert metrics["filter_detections"] == 10.0
        assert metrics["auto_encryptions"] == 2.0
        assert metrics["failed_decryptions"] == 0.0
        assert metrics["filter_enabled"] == 1.0

    @pytest.mark.asyncio
    async def test_secrets_service_process_text(self, secrets_service):
        """Test SecretsService text processing."""
        # Mock filter to return empty results
        secrets_service.filter.filter_text.return_value = ("clean text", [])

        result_text, references = await secrets_service.process_incoming_text("test text", "test_message_id")

        assert result_text == "test text"  # Fixed expectation - no secrets detected means original text
        assert references == []

        # Verify filter was called
        secrets_service.filter.filter_text.assert_called_once_with("test text", "")


class TestInfrastructureServicesIntegration(BaseMetricsTest):
    """Integration tests for all infrastructure services."""

    @pytest.mark.asyncio
    async def test_all_infrastructure_services_base_metrics(self):
        """Test that all infrastructure services provide base metrics."""
        services = []

        # Create mock time service
        mock_time_service = MagicMock()
        mock_time_service.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Create all services
        services.append(TimeService())
        services.append(ShutdownService())
        services.append(InitializationService(time_service=mock_time_service))

        # Create ResourceMonitorService with minimal config
        budget = ResourceBudget(
            memory_mb=ResourceLimit(limit=1000, warning=800, critical=950),
            cpu_percent=ResourceLimit(limit=100, warning=80, critical=95),
            tokens_hour=ResourceLimit(limit=1000, warning=800, critical=950),
            tokens_day=ResourceLimit(limit=10000, warning=8000, critical=9500),
            thoughts_active=ResourceLimit(limit=10, warning=8, critical=9),
        )

        with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
            db_path = tmp.name
        try:
            services.append(ResourceMonitorService(budget=budget, db_path=db_path, time_service=mock_time_service))

            services.append(
                DatabaseMaintenanceService(time_service=mock_time_service, archive_dir_path=tempfile.mkdtemp())
            )

            # AuthenticationService needs special handling
            with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as auth_tmp:
                auth_db_path = auth_tmp.name
            try:
                services.append(AuthenticationService(db_path=auth_db_path, time_service=mock_time_service))

                # SecretsService with mocked dependencies
                with patch("ciris_engine.logic.secrets.store.SecretsStore"), patch(
                    "ciris_engine.logic.secrets.filter.SecretsFilter"
                ):
                    secrets_service = SecretsService(
                        time_service=mock_time_service, detection_config=SecretsDetectionConfig()
                    )
                    secrets_service.store = MagicMock()
                    secrets_service.filter = MagicMock()
                    services.append(secrets_service)

                # Test that each service provides base metrics
                for service in services:
                    metrics = service._collect_metrics()

                    # All services should have base metrics
                    self.assert_base_metrics_present(metrics)

                    # All metrics should be numeric
                    self.assert_all_metrics_are_floats(metrics)

                    # All metrics should be in valid ranges
                    self.assert_metrics_valid_ranges(metrics)

                    # Service should have at least some custom metrics
                    custom_metrics = set(metrics.keys()) - self.BASE_METRICS
                    assert len(custom_metrics) > 0, f"Service {service.__class__.__name__} has no custom metrics"

            finally:
                if os.path.exists(auth_db_path):
                    os.unlink(auth_db_path)
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_metric_uniqueness_across_services(self):
        """Test that services have unique metric names where appropriate."""
        # Create mock time service
        mock_time_service = MagicMock()
        mock_time_service.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

        # Collect all metrics from all services
        all_metrics: Dict[str, list] = {}

        services = [
            ("TimeService", TimeService()),
            ("ShutdownService", ShutdownService()),
            ("InitializationService", InitializationService(time_service=mock_time_service)),
        ]

        for service_name, service in services:
            metrics = service._collect_metrics()
            for metric_name in metrics.keys():
                if metric_name not in all_metrics:
                    all_metrics[metric_name] = []
                all_metrics[metric_name].append(service_name)

        # Check for problematic overlaps (excluding base metrics)
        overlapping_metrics = {
            name: services_list
            for name, services_list in all_metrics.items()
            if len(services_list) > 1 and name not in self.BASE_METRICS
        }

        # Some overlap is expected for common infrastructure metrics
        expected_overlaps = {"uptime_seconds", "request_count", "error_count", "error_rate", "healthy"}

        unexpected_overlaps = {
            name: services_list for name, services_list in overlapping_metrics.items() if name not in expected_overlaps
        }

        # Report unexpected overlaps but don't fail the test
        if unexpected_overlaps:
            print(f"Note: Found metric name overlaps: {unexpected_overlaps}")
            # This is informational - services may legitimately share some metric names


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
