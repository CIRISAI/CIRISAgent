"""Tests for SecretsService telemetry functionality.

2.9.7 wave 2: the Python SecretsFilter was deleted — telemetry now runs
against a real persist engine (shared `persist_engine` fixture), with
`filter_enabled` derived from the substrate filter catalog.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.schemas.runtime.enums import SensitivityLevel
from ciris_engine.schemas.secrets.service import FilterUpdateRequest, PatternConfig


class TestSecretsServiceTelemetry:
    """Test the secrets service telemetry functionality."""

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock()
        mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        return mock

    @pytest_asyncio.fixture
    async def secrets_service(self, persist_engine, mock_time_service):
        """Create the secrets service against a real persist engine."""
        service = SecretsService(time_service=mock_time_service)
        await service.start()
        service._start_time = mock_time_service.now()
        yield service
        await service.stop()

    @pytest.mark.asyncio
    async def test_get_metrics(self, secrets_service):
        """Test getting telemetry data from secrets service."""
        # Set up some metrics
        secrets_service._error_count = 1

        metrics = await secrets_service.get_metrics()

        # Check base metrics
        assert "uptime_seconds" in metrics
        assert "request_count" in metrics
        assert "error_count" in metrics
        assert "error_rate" in metrics
        assert "healthy" in metrics

        # Check service-specific metrics
        assert metrics["error_count"] == 1.0
        assert metrics["secrets_stored"] == 0.0  # Counter, not from store
        assert metrics["secrets_retrieved"] == 0.0
        assert metrics["secrets_deleted"] == 0.0
        assert metrics["vault_size"] == 0.0
        assert metrics["encryption_operations"] == 0.0
        assert metrics["decryption_operations"] == 0.0
        assert metrics["filter_detections"] == 0.0
        assert metrics["auto_encryptions"] == 0.0
        assert metrics["failed_decryptions"] == 0.0
        # Persist's default filter catalog is empty → filter disabled
        assert metrics["filter_enabled"] == 0.0

    @pytest.mark.asyncio
    async def test_get_metrics_no_secrets(self, secrets_service):
        """Test telemetry when no secrets are stored."""
        metrics = await secrets_service.get_metrics()

        assert metrics["healthy"] == 1.0
        assert metrics["secrets_stored"] == 0.0
        assert metrics["secrets_retrieved"] == 0.0
        assert metrics["secrets_active"] == 0.0

    @pytest.mark.asyncio
    async def test_get_metrics_filter_enabled_after_catalog_seed(self, secrets_service):
        """`filter_enabled` flips to 1.0 once the substrate catalog has patterns."""
        metrics = await secrets_service.get_metrics()
        assert metrics["filter_enabled"] == 0.0

        result = await secrets_service.update_filter_config(
            FilterUpdateRequest(
                patterns=[
                    PatternConfig(
                        name="api_key",
                        pattern="sk-[A-Za-z0-9]{10}",
                        sensitivity=SensitivityLevel.HIGH,
                        enabled=True,
                    )
                ]
            ),
            accessor="test",
        )
        assert result.success is True

        metrics = await secrets_service.get_metrics()
        assert metrics["filter_enabled"] == 1.0

    @pytest.mark.asyncio
    async def test_get_metrics_error_handling(self, secrets_service):
        """Test telemetry handles errors gracefully."""
        # Force the active-secrets probe to fail — falls back to task secrets
        secrets_service.store = Mock()
        secrets_service.store.list_secrets = AsyncMock(side_effect=Exception("Database error"))

        # Simulate an error has occurred in the service
        secrets_service._error_count = 1

        metrics = await secrets_service.get_metrics()

        # When there's an error, metrics should still be returned but with error indicators
        assert metrics["healthy"] == 1.0  # Service may still report healthy
        assert metrics["error_count"] == 1.0
        assert metrics["secrets_stored"] == 0.0
