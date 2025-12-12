"""Additional tests for API adapter to increase coverage.

Covers uncovered code paths:
- _inject_service
- _log_service_registry
- _handle_auth_service
- _handle_bus_manager
- reinject_services
- get_channel_list
- is_healthy
- get_metrics
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.config import APIAdapterConfig


class TestAPIAdapterConfig:
    """Tests for APIAdapterConfig."""

    def test_default_values(self):
        """APIAdapterConfig has expected defaults."""
        config = APIAdapterConfig()
        # Default host is 127.0.0.1 for security
        assert config.host == "127.0.0.1"
        assert config.port == 8080
        assert config.interaction_timeout == 55.0

    def test_custom_values(self):
        """APIAdapterConfig accepts custom values."""
        config = APIAdapterConfig(
            host="127.0.0.1",
            port=9000,
            interaction_timeout=120,
        )
        assert config.host == "127.0.0.1"
        assert config.port == 9000

    def test_load_env_vars(self):
        """Config loads environment variables."""
        config = APIAdapterConfig()
        # Just verify the method exists and can be called
        config.load_env_vars()


class TestLogServiceRegistry:
    """Tests for _log_service_registry helper."""

    def test_logs_service_count(self):
        """Logs count of services in registry."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        mock_runtime = Mock()
        mock_runtime.essential_config = Mock()
        mock_runtime.time_service = Mock()

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)
            adapter.runtime = mock_runtime
            adapter.app = Mock()
            adapter.app.state = Mock()

            # Mock service registry
            mock_registry = Mock()
            mock_registry.get_all_services.return_value = [Mock(), Mock(), Mock()]

            # Should log without error
            adapter._log_service_registry(mock_registry)

    def test_handles_mock_registry(self):
        """Handles mock or test registry gracefully."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)
            adapter.runtime = Mock()
            adapter.app = Mock()
            adapter.app.state = Mock()

            # Mock registry that raises TypeError
            mock_registry = Mock()
            mock_registry.get_all_services.side_effect = TypeError()

            # Should not raise
            adapter._log_service_registry(mock_registry)


class TestInjectService:
    """Tests for _inject_service helper."""

    def test_injects_existing_service(self):
        """Injects service when runtime has attribute."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)

            mock_service = Mock()
            adapter.runtime = Mock()
            adapter.runtime.test_service = mock_service
            adapter.app = Mock()
            adapter.app.state = Mock()

            adapter._inject_service("test_service", "test_service", None)

            assert adapter.app.state.test_service == mock_service

    def test_injects_with_handler(self):
        """Calls handler after injection."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)

            mock_service = Mock()
            handler_called = []

            def handler(svc):
                handler_called.append(svc)

            adapter.runtime = Mock()
            adapter.runtime.test_service = mock_service
            adapter.app = Mock()
            adapter.app.state = Mock()

            adapter._inject_service("test_service", "test_service", handler)

            assert mock_service in handler_called

    def test_skips_missing_attribute(self):
        """Skips injection when runtime lacks attribute."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)

            adapter.runtime = Mock(spec=[])  # No attributes
            adapter.app = Mock()
            adapter.app.state = Mock()

            # Should not raise
            adapter._inject_service("nonexistent", "app_name", None)

    def test_skips_none_value(self):
        """Skips injection when attribute is None."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)

            adapter.runtime = Mock()
            adapter.runtime.test_service = None
            adapter.app = Mock()
            adapter.app.state = Mock()

            # Should not raise
            adapter._inject_service("test_service", "test_service", None)


class TestHandleAuthService:
    """Tests for _handle_auth_service helper."""

    def test_preserves_existing_auth_service(self):
        """Preserves existing APIAuthService with API keys."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform
        from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)
            adapter.runtime = Mock()
            adapter.app = Mock()
            adapter.app.state = Mock()

            # Create existing auth service with API keys
            existing_auth = APIAuthService()
            existing_auth._api_keys = {"key1": Mock()}
            adapter.app.state.auth_service = existing_auth

            # Handle new auth service
            new_auth_service = Mock()
            adapter._handle_auth_service(new_auth_service)

            # Existing instance should be preserved
            assert adapter.app.state.auth_service is existing_auth
            assert existing_auth._auth_service is new_auth_service

    def test_creates_new_auth_service(self):
        """Creates new APIAuthService when none exists."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform
        from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)
            adapter.runtime = Mock()
            adapter.app = Mock()
            adapter.app.state = Mock()
            adapter.app.state.auth_service = None

            mock_auth_service = Mock()
            adapter._handle_auth_service(mock_auth_service)

            assert isinstance(adapter.app.state.auth_service, APIAuthService)


class TestHandleBusManager:
    """Tests for _handle_bus_manager helper."""

    def test_injects_buses(self):
        """Injects tool_bus and memory_bus."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)
            adapter.runtime = Mock()
            adapter.app = Mock()
            adapter.app.state = Mock()

            mock_bus_manager = Mock()
            mock_bus_manager.tool = Mock()
            mock_bus_manager.memory = Mock()

            adapter._handle_bus_manager(mock_bus_manager)

            assert adapter.app.state.tool_bus is mock_bus_manager.tool
            assert adapter.app.state.memory_bus is mock_bus_manager.memory


class TestIsHealthy:
    """Tests for is_healthy method."""

    def test_healthy_when_running(self):
        """Returns True when server is running."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)

            mock_task = Mock()
            mock_task.done.return_value = False

            adapter._server = Mock()
            adapter._server_task = mock_task

            assert adapter.is_healthy() is True

    def test_unhealthy_when_no_server(self):
        """Returns False when server is None."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)
            adapter._server = None
            adapter._server_task = None

            assert adapter.is_healthy() is False

    def test_unhealthy_when_task_done(self):
        """Returns False when server task is done."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)

            mock_task = Mock()
            mock_task.done.return_value = True

            adapter._server = Mock()
            adapter._server_task = mock_task

            assert adapter.is_healthy() is False


class TestGetMetrics:
    """Tests for get_metrics method."""

    def test_returns_metrics_dict(self):
        """Returns metrics dictionary."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)

            import time

            adapter._start_time = time.time()
            adapter._server = Mock()
            adapter._server_task = Mock()
            adapter._server_task.done.return_value = False

            # Mock communication service
            adapter.communication = Mock()
            mock_status = Mock()
            mock_status.metrics = {
                "requests_handled": 100,
                "error_count": 5,
                "avg_response_time_ms": 50.0,
            }
            adapter.communication.get_status.return_value = mock_status
            adapter.communication._websocket_clients = []

            metrics = adapter.get_metrics()

            assert "uptime_seconds" in metrics
            assert "healthy" in metrics
            assert "api_requests_total" in metrics
            assert "api_errors_total" in metrics

    def test_handles_metrics_error(self):
        """Returns zeros on metrics error."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)

            import time

            adapter._start_time = time.time()
            adapter._server = Mock()
            adapter._server_task = Mock()
            adapter._server_task.done.return_value = False

            # Mock communication service that raises
            adapter.communication = Mock()
            adapter.communication.get_status.side_effect = Exception("Error")

            metrics = adapter.get_metrics()

            assert metrics["api_requests_total"] == 0.0
            assert metrics["api_errors_total"] == 0.0


class TestGetChannelList:
    """Tests for get_channel_list method."""

    def test_returns_channel_contexts(self):
        """Returns list of ChannelContext objects."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform
        from ciris_engine.schemas.runtime.system_context import ChannelContext

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)

            # Mock the persistence functions
            with patch("ciris_engine.logic.adapters.api.adapter.get_active_channels_by_adapter") as mock_get_channels:
                with patch("ciris_engine.logic.adapters.api.adapter.is_admin_channel") as mock_is_admin:
                    mock_channel = Mock()
                    mock_channel.channel_id = "test-channel"
                    mock_channel.channel_name = "Test Channel"
                    mock_channel.last_activity = datetime.now(timezone.utc)
                    mock_channel.is_active = True
                    mock_channel.message_count = 10

                    mock_get_channels.return_value = [mock_channel]
                    mock_is_admin.return_value = False

                    channels = adapter.get_channel_list()

                    assert len(channels) == 1
                    assert isinstance(channels[0], ChannelContext)
                    assert channels[0].channel_id == "test-channel"


class TestReinjectServices:
    """Tests for reinject_services method."""

    def test_reinjects_available_services(self):
        """Re-injects services that become available."""
        from ciris_engine.logic.adapters.api.adapter import ApiPlatform

        with patch.object(ApiPlatform, "__init__", lambda self, runtime, **kwargs: None):
            adapter = ApiPlatform.__new__(ApiPlatform)

            adapter.runtime = Mock()
            adapter.runtime.test_service = Mock()
            adapter.runtime.runtime_control_service = Mock()
            adapter.runtime.runtime_control_service.adapter_manager = Mock()
            adapter.app = Mock()
            adapter.app.state = Mock()
            adapter.runtime_control = Mock()  # Required for _inject_adapter_manager_to_api_runtime_control

            # Mock the service configuration
            with patch("ciris_engine.logic.adapters.api.adapter.ApiServiceConfiguration") as mock_config:
                mock_config.get_current_mappings_as_tuples.return_value = [
                    ("test_service", "test_service", None),
                ]

                adapter.reinject_services()

                # Service should be injected
                assert adapter.app.state.test_service is adapter.runtime.test_service
