"""Tests for SecretsService telemetry functionality."""

from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.secrets.filter import SecretsFilter
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.secrets.store import SecretsStore
from ciris_engine.schemas.secrets.core import PatternStats, SecretRecord


class TestSecretsServiceTelemetry:
    """Test the secrets service telemetry functionality."""

    @pytest.fixture
    def mock_time_service(self):
        """Create a mock time service."""
        mock = Mock()
        mock.now.return_value = datetime(2024, 1, 1, 12, 0, 0)
        return mock

    @pytest.fixture
    def mock_store(self):
        """Create a mock secrets store."""
        mock = Mock(spec=SecretsStore)
        mock.encryption_enabled = True
        mock.list_secrets = AsyncMock(
            return_value=[
                SecretRecord(
                    secret_uuid="uuid1",
                    encrypted_value=b"encrypted1",
                    encryption_key_ref="key1",
                    salt=b"salt1",
                    nonce=b"nonce1",
                    description="Test secret 1",
                    sensitivity_level="MEDIUM",
                    detected_pattern="api_key",
                    context_hint="test",
                    created_at=datetime(2024, 1, 1),
                    last_accessed=datetime(2024, 1, 1),
                    access_count=5,
                    source_message_id="msg1",
                    auto_decapsulate_for_actions=[],
                ),
                SecretRecord(
                    secret_uuid="uuid2",
                    encrypted_value=b"encrypted2",
                    encryption_key_ref="key2",
                    salt=b"salt2",
                    nonce=b"nonce2",
                    description="Test secret 2",
                    sensitivity_level="HIGH",
                    detected_pattern="password",
                    context_hint="test",
                    created_at=datetime(2024, 1, 1),
                    last_accessed=datetime(2024, 1, 1),
                    access_count=3,
                    source_message_id="msg2",
                    auto_decapsulate_for_actions=[],
                ),
            ]
        )
        return mock

    @pytest.fixture
    def mock_filter(self):
        """Create a mock secrets filter."""
        mock = Mock(spec=SecretsFilter)
        mock.get_pattern_stats.return_value = PatternStats(total_patterns=15, default_patterns=10, custom_patterns=5)
        return mock

    @pytest_asyncio.fixture
    async def secrets_service(self, mock_time_service, mock_store, mock_filter):
        """Create the secrets service."""
        service = SecretsService(time_service=mock_time_service, store=mock_store, filter_obj=mock_filter)
        await service.start()
        service._start_time = mock_time_service.now()
        return service

    @pytest.mark.asyncio
    async def test_get_telemetry(self, secrets_service):
        """Test getting telemetry data from secrets service."""
        # Set up some metrics
        secrets_service._error_count = 1

        telemetry = await secrets_service.get_telemetry()

        # Check required fields
        assert telemetry["service_name"] == "secrets"
        assert telemetry["healthy"] is True
        assert telemetry["encryption_enabled"] is True
        assert telemetry["error_count"] == 1
        assert telemetry["access_count"] == 8  # 5 + 3 from mock records
        assert telemetry["stored_secrets"] == 2
        assert telemetry["active_patterns"] == 15
        assert telemetry["default_patterns"] == 10
        assert telemetry["custom_patterns"] == 5
        assert telemetry["auto_forget_enabled"] is True
        assert telemetry["uptime_seconds"] >= 0
        assert "last_updated" in telemetry

    @pytest.mark.asyncio
    async def test_get_telemetry_no_secrets(self, secrets_service):
        """Test telemetry when no secrets are stored."""
        secrets_service.store.list_secrets = AsyncMock(return_value=[])

        telemetry = await secrets_service.get_telemetry()

        assert telemetry["service_name"] == "secrets"
        assert telemetry["healthy"] is True
        assert telemetry["access_count"] == 0
        assert telemetry["stored_secrets"] == 0

    @pytest.mark.asyncio
    async def test_get_telemetry_encryption_disabled(self, secrets_service):
        """Test telemetry with encryption disabled."""
        secrets_service.store.encryption_enabled = False

        telemetry = await secrets_service.get_telemetry()

        assert telemetry["encryption_enabled"] is False

    @pytest.mark.asyncio
    async def test_get_telemetry_error_handling(self, secrets_service):
        """Test telemetry handles errors gracefully."""
        # Mock store.list_secrets to raise an exception
        secrets_service.store.list_secrets = AsyncMock(side_effect=Exception("Database error"))

        telemetry = await secrets_service.get_telemetry()

        assert telemetry["service_name"] == "secrets"
        assert telemetry["healthy"] is False
        assert telemetry["error"] == "Database error"
        assert telemetry["error_count"] == 1
        assert telemetry["access_count"] == 0
