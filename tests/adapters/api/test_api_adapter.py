"""
Comprehensive test suite for API adapter.

Tests:
- Adapter lifecycle (initialization, startup, shutdown)
- Service registration
- Message routing through APICommunicationService
- Channel management
- Error handling and reconnection
- Health checks
- Concurrent message handling
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.api.adapter import ApiPlatform
from ciris_engine.logic.adapters.api.api_communication import APICommunicationService
from ciris_engine.logic.adapters.api.api_runtime_control import APIRuntimeControlService
from ciris_engine.logic.adapters.api.api_tools import APIToolService
from ciris_engine.logic.adapters.api.config import APIAdapterConfig
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import IncomingMessage

logger = logging.getLogger(__name__)


# Mock persistence.add_correlation for all tests to avoid database issues
@pytest.fixture(autouse=True)
def mock_add_correlation():
    with patch("ciris_engine.logic.persistence.add_correlation") as mock:
        mock.return_value = "test-correlation-id"
        yield mock


@pytest.fixture
def mock_runtime():
    """Create a mock runtime with necessary services."""
    runtime = Mock()
    runtime.time_service = Mock()
    runtime.time_service.now.return_value = datetime.now(timezone.utc)
    runtime.memory_service = Mock()
    runtime.telemetry_service = Mock()
    runtime.audit_service = Mock()
    runtime.config_service = Mock()
    runtime.wa_auth_system = Mock()
    runtime.resource_monitor = Mock()
    runtime.task_scheduler = Mock()
    runtime.authentication_service = Mock()
    runtime.incident_management_service = Mock()
    runtime.service_registry = Mock()
    runtime.runtime_control_service = Mock()
    return runtime


@pytest.fixture
def api_config():
    """Create test API configuration."""
    return APIAdapterConfig(
        host="127.0.0.1",
        port=8888,
        interaction_timeout=30,
        max_request_size=1048576,
        cors_origins=["*"],
        ssl_cert_file=None,
        ssl_key_file=None,
    )


@pytest.fixture
def api_platform(mock_runtime, api_config):
    """Create API platform instance."""
    with patch("ciris_engine.logic.adapters.api.adapter.create_app") as mock_create_app:
        mock_app = Mock()
        mock_app.state = Mock()
        mock_create_app.return_value = mock_app

        platform = ApiPlatform(runtime=mock_runtime, adapter_config=api_config)
        return platform


class TestAPIAdapterLifecycle:
    """Test API adapter lifecycle management."""

    def test_initialization(self, mock_runtime, api_config):
        """Test API adapter initialization."""
        with patch("ciris_engine.logic.adapters.api.adapter.create_app") as mock_create_app:
            mock_app = Mock()
            mock_app.state = Mock()
            mock_create_app.return_value = mock_app

            platform = ApiPlatform(runtime=mock_runtime, adapter_config=api_config)

            assert platform.runtime == mock_runtime
            assert platform.config == api_config
            assert isinstance(platform.communication, APICommunicationService)
            assert isinstance(platform.runtime_control, APIRuntimeControlService)
            assert isinstance(platform.tool_service, APIToolService)
            assert platform.message_observer is None  # Created during start()

    def test_initialization_with_dict_config(self, mock_runtime):
        """Test initialization with dictionary config."""
        config_dict = {"host": "0.0.0.0", "port": 9999, "interaction_timeout": 60}

        with patch("ciris_engine.logic.adapters.api.adapter.create_app") as mock_create_app:
            mock_app = Mock()
            mock_app.state = Mock()
            mock_create_app.return_value = mock_app

            # Patch load_env_vars to prevent environment override
            with patch.object(APIAdapterConfig, "load_env_vars"):
                platform = ApiPlatform(runtime=mock_runtime, adapter_config=config_dict)

                assert platform.config.host == "0.0.0.0"
                assert platform.config.port == 9999
                assert platform.config.interaction_timeout == 60

    @pytest.mark.asyncio
    async def test_start_lifecycle(self, api_platform):
        """Test API adapter start lifecycle."""
        # Mock server
        mock_server = Mock()
        mock_server.serve = AsyncMock()
        mock_server.should_exit = False

        with patch("uvicorn.Server") as mock_server_class, patch("uvicorn.Config") as mock_config_class:
            mock_server_class.return_value = mock_server

            # Start the platform
            await api_platform.start()

            # Verify services were injected
            assert api_platform.app.state.api_config == api_platform.config
            assert api_platform.app.state.memory_service == api_platform.runtime.memory_service
            assert api_platform.app.state.time_service == api_platform.runtime.time_service

            # Verify message observer was created
            assert api_platform.message_observer is not None

            # Verify server was started
            assert api_platform._server is not None
            assert api_platform._server_task is not None

    @pytest.mark.asyncio
    async def test_stop_lifecycle(self, api_platform):
        """Test API adapter stop lifecycle."""
        # Mock running server
        api_platform._server = Mock()
        api_platform._server.should_exit = False

        # Create a proper async task
        async def dummy_task():
            return None

        api_platform._server_task = asyncio.create_task(dummy_task())

        # Stop the platform
        await api_platform.stop()

        # Verify server was shutdown
        assert api_platform._server.should_exit is True


class TestAPIServiceRegistration:
    """Test API adapter service registration."""

    def test_get_services_to_register(self, api_platform):
        """Test service registration list."""
        registrations = api_platform.get_services_to_register()

        assert len(registrations) == 3

        # Check communication service
        comm_reg = next(r for r in registrations if r.service_type == ServiceType.COMMUNICATION)
        assert comm_reg.provider == api_platform.communication
        assert comm_reg.priority == Priority.CRITICAL
        assert "send_message" in comm_reg.capabilities
        assert "fetch_messages" in comm_reg.capabilities

        # Check runtime control service
        runtime_reg = next(r for r in registrations if r.service_type == ServiceType.RUNTIME_CONTROL)
        assert runtime_reg.provider == api_platform.runtime_control
        assert runtime_reg.priority == Priority.CRITICAL
        assert "pause_processing" in runtime_reg.capabilities
        assert "resume_processing" in runtime_reg.capabilities

        # Check tool service
        tool_reg = next(r for r in registrations if r.service_type == ServiceType.TOOL)
        assert tool_reg.provider == api_platform.tool_service
        assert tool_reg.priority == Priority.CRITICAL
        assert "execute_tool" in tool_reg.capabilities
        assert "get_available_tools" in tool_reg.capabilities


class TestAPIMessageHandling:
    """Test API message handling functionality."""

    @pytest.mark.asyncio
    async def test_handle_message_via_observer(self, api_platform):
        """Test message handling through observer."""
        # Create mock observer
        mock_observer = Mock()
        mock_observer.handle_incoming_message = AsyncMock()
        mock_observer.start = AsyncMock()

        # Create test message with string timestamp
        test_msg = IncomingMessage(
            message_id=str(uuid.uuid4()),
            channel_id="api_127.0.0.1_8888",
            author_id="test_user",
            author_name="Test User",
            content="Test message",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Start platform to set up message handler
        with patch("uvicorn.Server") as mock_server_class, patch("uvicorn.Config"):
            # Configure the mock server instance
            mock_server = Mock()
            mock_server.serve = AsyncMock()
            mock_server_class.return_value = mock_server

            with patch("ciris_engine.logic.adapters.api.adapter.APIObserver", return_value=mock_observer):
                await api_platform.start()

                # Get the message handler function (it's called on_message, not handle_message)
                handle_message = api_platform.app.state.on_message

                # Call handler
                await handle_message(test_msg)

                # Verify observer was called
                mock_observer.handle_incoming_message.assert_called_once()
                called_msg = mock_observer.handle_incoming_message.call_args[0][0]
                assert called_msg.message_id == test_msg.message_id
                assert called_msg.content == test_msg.content

    @pytest.mark.asyncio
    async def test_message_channel_mapping(self, api_platform):
        """Test message ID to channel mapping for responses."""
        # Create mock observer
        api_platform.message_observer = Mock()
        api_platform.message_observer.handle_incoming_message = AsyncMock()

        # Start platform
        with patch("uvicorn.Server") as mock_server_class, patch("uvicorn.Config"):
            # Configure the mock server instance
            mock_server = Mock()
            mock_server.serve = AsyncMock()
            mock_server_class.return_value = mock_server

            await api_platform.start()

            # Create test message with string timestamp
            test_msg = IncomingMessage(
                message_id="msg-123",
                channel_id="api_127.0.0.1_8888",
                author_id="test_user",
                author_name="Test User",
                content="Test message",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            # Call handler (it's called on_message, not handle_message)
            handle_message = api_platform.app.state.on_message
            await handle_message(test_msg)

            # Verify channel mapping was stored
            assert api_platform.app.state.message_channel_map["api_127.0.0.1_8888"] == "msg-123"


class TestAPIChannelManagement:
    """Test API channel management."""

    def test_get_channel_list(self, api_platform):
        """Test getting channel list."""
        # API adapter uses its own get_channel_list method
        with patch(
            "ciris_engine.logic.adapters.api.adapter.get_active_channels_by_adapter"
        ) as mock_get_channels, patch("ciris_engine.logic.adapters.api.adapter.is_admin_channel") as mock_is_admin:
            # Mock the return value
            mock_get_channels.return_value = [
                {
                    "channel_id": "api_127.0.0.1_8888",
                    "channel_type": "api",
                    "is_active": True,
                    "last_activity": datetime.now(timezone.utc),
                },
                {
                    "channel_id": "api_192.168.1.1_8080",
                    "channel_type": "api",
                    "is_active": True,
                    "last_activity": datetime.now(timezone.utc),
                },
            ]

            # Mock is_admin_channel to return False for both channels
            mock_is_admin.return_value = False

            channels = api_platform.get_channel_list()

            assert len(channels) == 2
            assert any(c.channel_id == "api_127.0.0.1_8888" for c in channels)
            assert any(c.channel_id == "api_192.168.1.1_8080" for c in channels)
            assert all(c.channel_type == "api" for c in channels)
            assert all(c.is_active for c in channels)


class TestAPIErrorHandling:
    """Test API adapter error handling."""

    @pytest.mark.asyncio
    async def test_server_startup_error(self, api_platform):
        """Test handling of server startup errors."""
        with patch("uvicorn.Server") as mock_server_class, patch("uvicorn.Config"):
            mock_server = Mock()

            # Make serve() raise an exception
            async def failing_serve():
                raise Exception("Port already in use")

            mock_server.serve = failing_serve
            mock_server_class.return_value = mock_server

            # Start the platform - it creates a task that will fail
            await api_platform.start()

            # Give the task time to fail
            await asyncio.sleep(0.1)

            # Check that the server task failed
            assert api_platform._server_task is not None
            assert api_platform._server_task.done()
            with pytest.raises(Exception, match="Port already in use"):
                api_platform._server_task.result()

    @pytest.mark.asyncio
    async def test_message_handling_error(self, api_platform):
        """Test error handling in message processing."""
        # Create mock observer that raises error
        api_platform.message_observer = Mock()
        api_platform.message_observer.handle_incoming_message = AsyncMock(side_effect=Exception("Processing error"))

        # Start platform
        with patch("uvicorn.Server") as mock_server_class, patch("uvicorn.Config"):
            # Configure the mock server instance
            mock_server = Mock()
            mock_server.serve = AsyncMock()
            mock_server_class.return_value = mock_server

            await api_platform.start()

            # Create test message with string timestamp
            test_msg = IncomingMessage(
                message_id=str(uuid.uuid4()),
                channel_id="api_127.0.0.1_8888",
                author_id="test_user",
                author_name="Test User",
                content="Test message",
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

            # Handler should not raise exception (it's called on_message)
            handle_message = api_platform.app.state.on_message
            await handle_message(test_msg)  # Should log error but not raise


class TestAPIHealthCheck:
    """Test API health check functionality."""

    def test_is_healthy_running(self, api_platform):
        """Test health check when server is running."""
        api_platform._server = Mock()
        api_platform._server_task = Mock()
        api_platform._server_task.done.return_value = False

        assert api_platform.is_healthy() is True

    def test_is_healthy_not_started(self, api_platform):
        """Test health check when server not started."""
        assert api_platform.is_healthy() is False

    def test_is_healthy_task_completed(self, api_platform):
        """Test health check when server task completed."""
        api_platform._server = Mock()
        api_platform._server_task = Mock()
        api_platform._server_task.done.return_value = True

        assert api_platform.is_healthy() is False


class TestAPIAppCoverage:
    """Test app.py specific coverage."""

    @pytest.mark.asyncio
    async def test_lifespan_context_manager(self):
        """Test the lifespan context manager in app.py."""
        from ciris_engine.logic.adapters.api.app import lifespan

        app = Mock()
        async with lifespan(app):
            pass

    def test_create_app_with_runtime_all_services(self):
        """Test create_app initializes all service placeholders."""
        from ciris_engine.logic.adapters.api.app import create_app

        runtime = Mock()
        app = create_app(runtime=runtime)

        # This covers lines 85-122 in app.py
        assert app.state.memory_service is None
        assert app.state.config_service is None
        assert app.state.telemetry_service is None
        assert app.state.audit_service is None
        assert app.state.incident_management_service is None
        assert app.state.tsdb_consolidation_service is None
        assert app.state.time_service is None
        assert app.state.shutdown_service is None
        assert app.state.initialization_service is None
        assert app.state.authentication_service is None
        assert app.state.resource_monitor is None
        assert app.state.database_maintenance_service is None
        assert app.state.secrets_service is None
        assert app.state.wise_authority_service is None
        assert app.state.wa_service is None
        assert app.state.adaptive_filter_service is None
        assert app.state.visibility_service is None
        assert app.state.self_observation_service is None
        assert app.state.llm_service is None
        assert app.state.runtime_control_service is None
        assert app.state.task_scheduler is None
        assert app.state.secrets_tool_service is None
        assert app.state.service_registry is None
        assert app.state.agent_processor is None
        assert app.state.message_handler is None
        assert app.state.communication_service is None
        assert app.state.tool_service is None


class TestAPIConcurrentHandling:
    """Test concurrent message handling in API adapter."""

    @pytest.mark.asyncio
    async def test_concurrent_message_processing(self, api_platform):
        """Test handling multiple concurrent messages."""
        # Track call order
        call_order = []

        async def mock_handle(msg):
            call_order.append(msg.message_id)
            await asyncio.sleep(0.01)  # Simulate processing

        # Create mock observer
        mock_observer = Mock()
        mock_observer.handle_incoming_message = AsyncMock(side_effect=mock_handle)
        mock_observer.start = AsyncMock()

        # Start platform
        with patch("uvicorn.Server") as mock_server_class, patch("uvicorn.Config"):
            # Configure the mock server instance
            mock_server = Mock()
            mock_server.serve = AsyncMock()
            mock_server_class.return_value = mock_server

            with patch("ciris_engine.logic.adapters.api.adapter.APIObserver", return_value=mock_observer):
                await api_platform.start()

                # Create multiple test messages with string timestamps
                messages = []
                for i in range(5):
                    msg = IncomingMessage(
                        message_id=f"msg-{i}",
                        channel_id="api_127.0.0.1_8888",
                        author_id="test_user",
                        author_name="Test User",
                        content=f"Message {i}",
                        timestamp=datetime.now(timezone.utc).isoformat(),
                    )
                    messages.append(msg)

                # Handle messages concurrently (it's called on_message)
                handle_message = api_platform.app.state.on_message
                tasks = [handle_message(msg) for msg in messages]
                await asyncio.gather(*tasks)

                # Verify all messages were processed
                assert len(call_order) == 5
                assert all(f"msg-{i}" in call_order for i in range(5))

    @pytest.mark.asyncio
    async def test_app_creation_with_proxy_path(self):
        """Test that FastAPI app is created with correct root_path for proxy support."""
        from ciris_engine.logic.adapters.api.app import create_app

        # Test without proxy path
        config_no_proxy = APIAdapterConfig()
        app_no_proxy = create_app(adapter_config=config_no_proxy)
        assert app_no_proxy.root_path in ("", "/", None)

        # Test with proxy path
        config_with_proxy = APIAdapterConfig(proxy_path="/api/test-agent")
        app_with_proxy = create_app(adapter_config=config_with_proxy)
        assert app_with_proxy.root_path == "/api/test-agent"

        # Test that adapter config is loaded properly with env vars
        with patch("ciris_engine.logic.config.env_utils.get_env_var") as mock_get_env:
            mock_get_env.side_effect = lambda key: {
                "CIRIS_AGENT_ID": "sage-123",
                "CIRIS_PROXY_PATH": None,
            }.get(key)

            config = APIAdapterConfig()
            config.load_env_vars()
            app = create_app(adapter_config=config)
            assert app.root_path == "/api/sage-123"
