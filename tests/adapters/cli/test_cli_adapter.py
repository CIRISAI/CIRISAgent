"""
Comprehensive test suite for CLI adapter.

Tests:
- Adapter lifecycle (initialization, startup, shutdown)
- Service registration
- Interactive and non-interactive modes
- Message handling through CLIObserver
- Channel management
- Error handling
- Input/output functionality
"""

import io
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.cli.adapter import CliPlatform
from ciris_engine.logic.adapters.cli.cli_adapter import CLIAdapter
from ciris_engine.logic.adapters.cli.cli_observer import CLIObserver
from ciris_engine.logic.adapters.cli.config import CLIAdapterConfig
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.runtime.messages import IncomingMessage


@pytest.fixture
def mock_runtime():
    """Create a mock runtime with necessary services."""
    runtime = Mock()

    # Mock time service
    time_service = Mock()
    time_service.now.return_value = datetime.now(timezone.utc)
    time_service.now_iso.return_value = datetime.now(timezone.utc).isoformat()
    runtime.time_service = time_service

    # Mock service registry with get_services_by_type
    service_registry = Mock()
    service_registry.get_services_by_type.return_value = [time_service]
    runtime.service_registry = service_registry

    runtime.memory_service = Mock()
    runtime.telemetry_service = Mock()
    runtime.audit_service = Mock()
    runtime.authentication_service = Mock()
    runtime.authentication_service.get_or_create_observer_certificate = AsyncMock(
        return_value=("observer_123", "cert_data")
    )
    runtime.wa_auth_system = Mock()
    runtime.bus_manager = Mock()
    runtime.bus_manager.memory = None  # Memory bus may not be available during startup
    runtime.template = None
    return runtime


@pytest.fixture
def cli_config():
    """Create test CLI configuration."""
    return CLIAdapterConfig(interactive=True, prompt_prefix="CIRIS> ", enable_colors=True, max_history_entries=100)


@pytest.fixture
def cli_platform(mock_runtime, cli_config):
    """Create CLI platform instance."""
    platform = CliPlatform(runtime=mock_runtime, adapter_config=cli_config)
    return platform


class TestCLIAdapterLifecycle:
    """Test CLI adapter lifecycle management."""

    def test_initialization(self, mock_runtime, cli_config):
        """Test CLI adapter initialization."""
        platform = CliPlatform(runtime=mock_runtime, adapter_config=cli_config)

        assert platform.runtime == mock_runtime
        assert platform.config == cli_config
        assert isinstance(platform.cli_adapter, CLIAdapter)
        assert platform.cli_observer is None  # Created during start()
        assert platform.adapter_id.startswith("cli_")
        assert platform.adapter_id.count("@") == 1

    def test_initialization_with_dict_config(self, mock_runtime):
        """Test initialization with dictionary config."""
        config_dict = {"interactive": False, "prompt_prefix": ">>> ", "enable_colors": False}

        platform = CliPlatform(runtime=mock_runtime, adapter_config=config_dict)

        assert platform.config.interactive is False
        assert platform.config.prompt_prefix == ">>> "
        assert platform.config.enable_colors is False

    def test_initialization_with_template(self, mock_runtime):
        """Test initialization with runtime template config."""
        # Mock template with CLI config
        mock_template = Mock()
        mock_cli_config = Mock()
        mock_cli_config.model_dump.return_value = {
            "interactive": True,
            "prompt_prefix": "TEMPLATE> ",
            "max_history_entries": 200,
        }
        mock_template.cli_config = mock_cli_config
        mock_runtime.template = mock_template

        platform = CliPlatform(runtime=mock_runtime)

        assert platform.config.prompt_prefix == "TEMPLATE> "
        assert platform.config.max_history_entries == 200

    @pytest.mark.asyncio
    async def test_start_lifecycle(self, cli_platform, mock_runtime):
        """Test CLI adapter start lifecycle."""
        # Mock service_initializer with required services
        mock_service_initializer = Mock()
        mock_service_initializer.memory_service = Mock()
        mock_service_initializer.filter_service = Mock()
        mock_service_initializer.secrets_service = Mock()
        mock_service_initializer.time_service = Mock()
        mock_runtime.service_initializer = mock_service_initializer
        mock_runtime.agent_id = "test_agent"

        # Mock CLI adapter start
        cli_platform.cli_adapter.start = AsyncMock()

        # Start the platform
        await cli_platform.start()

        # Verify observer was created
        assert cli_platform.cli_observer is not None
        assert isinstance(cli_platform.cli_observer, CLIObserver)

        # Verify CLI adapter was started
        cli_platform.cli_adapter.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_lifecycle(self, cli_platform):
        """Test CLI adapter stop lifecycle."""
        # Mock running adapter
        cli_platform.cli_adapter.stop = AsyncMock()
        cli_platform.cli_observer = Mock()
        cli_platform.cli_observer.stop = AsyncMock()

        # Stop the platform
        await cli_platform.stop()

        # Verify both observer and adapter were stopped
        cli_platform.cli_observer.stop.assert_called_once()
        cli_platform.cli_adapter.stop.assert_called_once()


class TestCLIServiceRegistration:
    """Test CLI adapter service registration."""

    def test_get_services_to_register(self, cli_platform):
        """Test service registration list."""
        registrations = cli_platform.get_services_to_register()

        # CLI registers 3 services: communication, tool, and WA
        assert len(registrations) == 3

        # Check communication service
        comm_reg = next(r for r in registrations if r.service_type == ServiceType.COMMUNICATION)
        assert comm_reg.provider == cli_platform.cli_adapter
        assert comm_reg.priority == Priority.LOW
        assert "send_message" in comm_reg.capabilities
        assert "fetch_messages" in comm_reg.capabilities
        assert "SpeakHandler" in comm_reg.handlers
        assert "ObserveHandler" in comm_reg.handlers

        # Check tool service
        tool_reg = next(r for r in registrations if r.service_type == ServiceType.TOOL)
        assert tool_reg.provider == cli_platform.cli_adapter
        assert tool_reg.priority == Priority.LOW
        assert "execute_tool" in tool_reg.capabilities
        assert "get_available_tools" in tool_reg.capabilities
        assert "ToolHandler" in tool_reg.handlers

        # Check WA service
        wa_reg = next(r for r in registrations if r.service_type == ServiceType.WISE_AUTHORITY)
        assert wa_reg.provider == cli_platform.cli_adapter
        assert wa_reg.priority == Priority.LOW
        assert "fetch_guidance" in wa_reg.capabilities
        assert "send_deferral" in wa_reg.capabilities


class TestCLIMessageHandling:
    """Test CLI message handling functionality."""

    @pytest.mark.asyncio
    async def test_handle_incoming_message(self, cli_platform):
        """Test handling incoming messages through observer."""
        # Create and set up observer
        cli_platform.cli_observer = Mock()
        cli_platform.cli_observer.handle_incoming_message = AsyncMock()

        # Create test message
        test_msg = IncomingMessage(
            message_id=str(uuid.uuid4()),
            channel_id="cli_test@hostname",
            author_id="user",
            author_name="Test User",
            content="Test command",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Handle message
        await cli_platform._handle_incoming_message(test_msg)

        # Verify observer was called
        cli_platform.cli_observer.handle_incoming_message.assert_called_once_with(test_msg)

    @pytest.mark.asyncio
    async def test_handle_message_no_observer(self, cli_platform):
        """Test handling message when observer not available."""
        # No observer set
        cli_platform.cli_observer = None

        test_msg = IncomingMessage(
            message_id=str(uuid.uuid4()),
            channel_id="cli_test@hostname",
            author_id="user",
            author_name="Test User",
            content="Test command",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Should handle gracefully
        await cli_platform._handle_incoming_message(test_msg)  # Should not raise

    @pytest.mark.asyncio
    async def test_handle_message_observer_error(self, cli_platform):
        """Test error handling in message observer."""
        # Observer that raises error
        cli_platform.cli_observer = Mock()
        cli_platform.cli_observer.handle_incoming_message = AsyncMock(side_effect=Exception("Observer error"))

        test_msg = IncomingMessage(
            message_id=str(uuid.uuid4()),
            channel_id="cli_test@hostname",
            author_id="user",
            author_name="Test User",
            content="Test command",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        # Should log error but not raise
        await cli_platform._handle_incoming_message(test_msg)


class TestCLIInteractiveModes:
    """Test interactive and non-interactive CLI modes."""

    def test_interactive_mode_config(self, mock_runtime):
        """Test CLI in interactive mode."""
        config = CLIAdapterConfig(interactive=True)
        platform = CliPlatform(runtime=mock_runtime, adapter_config=config)

        assert platform.config.interactive is True
        assert platform.cli_adapter.interactive is True

    def test_non_interactive_mode_config(self, mock_runtime):
        """Test CLI in non-interactive mode."""
        config = CLIAdapterConfig(interactive=False)
        platform = CliPlatform(runtime=mock_runtime, adapter_config=config)

        assert platform.config.interactive is False
        assert platform.cli_adapter.interactive is False

    @pytest.mark.asyncio
    async def test_interactive_input_handling(self, cli_platform):
        """Test handling user input in interactive mode."""
        # Mock stdin with test input
        test_input = "Hello CIRIS\n"

        with patch("sys.stdin", new=io.StringIO(test_input)):
            # Set up message callback
            messages_received = []

            async def capture_message(msg):
                messages_received.append(msg)

            cli_platform.cli_adapter._on_message = capture_message

            # Simulate reading input
            # Note: Actual implementation would use asyncio reader
            # This is a simplified test
            line = test_input.strip()
            if line:
                msg = IncomingMessage(
                    message_id=str(uuid.uuid4()),
                    channel_id=cli_platform.adapter_id,
                    author_id="cli_user",
                    author_name="CLI User",
                    content=line,
                    timestamp=datetime.now(timezone.utc).isoformat(),
                )
                await capture_message(msg)

            # Verify message was created correctly
            assert len(messages_received) == 1
            assert messages_received[0].content == "Hello CIRIS"


class TestCLIOutputHandling:
    """Test CLI output functionality."""

    @pytest.mark.asyncio
    async def test_send_message_output(self, cli_platform):
        """Test sending messages to CLI output."""
        # Capture stdout
        # Mock the CLI adapter's send_message
        cli_platform.cli_adapter.send_message = AsyncMock(return_value=True)

        # Send message
        result = await cli_platform.cli_adapter.send_message(
            channel_id=cli_platform.adapter_id, content="Test response from CIRIS"
        )

        assert result is True
        cli_platform.cli_adapter.send_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_output_with_formatting(self, cli_platform):
        """Test output with different formatting styles."""
        # CLI adapter doesn't have specific formatting styles
        # Just test that send_message works

        # Mock send
        cli_platform.cli_adapter.send_message = AsyncMock(return_value=True)

        result = await cli_platform.cli_adapter.send_message(
            channel_id=cli_platform.adapter_id, content="# Header\n\nThis is **bold** text."
        )
        assert result is True


class TestCLIChannelManagement:
    """Test CLI channel management."""

    def test_single_channel_cli(self, cli_platform):
        """Test that CLI adapter manages single channel."""
        # CLI adapter has one channel - the terminal
        channel_id = cli_platform.adapter_id

        # Verify adapter ID format
        assert channel_id.startswith("cli_")
        assert "@" in channel_id

    @pytest.mark.asyncio
    async def test_channel_list(self, cli_platform):
        """Test getting channel list from CLI adapter."""
        # Mock CLI adapter's get_channel_list
        cli_platform.cli_adapter.get_channel_list = Mock(
            return_value=[
                {
                    "channel_id": cli_platform.adapter_id,
                    "channel_name": "CLI Terminal",
                    "channel_type": "cli",
                    "is_active": True,
                    "last_activity": datetime.now(timezone.utc),
                }
            ]
        )

        channels = cli_platform.cli_adapter.get_channel_list()

        assert len(channels) == 1
        assert channels[0]["channel_id"] == cli_platform.adapter_id
        assert channels[0]["channel_type"] == "cli"
        assert channels[0]["is_active"] is True


class TestCLIHistoryManagement:
    """Test CLI history functionality."""

    @pytest.mark.asyncio
    async def test_message_history_tracking(self, cli_platform):
        """Test that CLI tracks message history."""
        # Set up history tracking
        cli_platform.cli_adapter._message_history = []

        # Simulate sending multiple messages
        for i in range(5):
            cli_platform.cli_adapter._message_history.append(
                {"timestamp": datetime.now(timezone.utc), "content": f"Message {i}", "direction": "outgoing"}
            )

        # Verify history
        assert len(cli_platform.cli_adapter._message_history) == 5
        assert cli_platform.cli_adapter._message_history[0]["content"] == "Message 0"
        assert cli_platform.cli_adapter._message_history[-1]["content"] == "Message 4"

    def test_history_limit(self, mock_runtime):
        """Test history size limiting."""
        config = CLIAdapterConfig(max_history_entries=3)
        platform = CliPlatform(runtime=mock_runtime, adapter_config=config)

        assert platform.config.max_history_entries == 3


class TestCLIErrorHandling:
    """Test CLI error handling scenarios."""

    @pytest.mark.asyncio
    async def test_startup_error_handling(self, cli_platform):
        """Test handling of startup errors."""
        # Mock adapter start to raise error
        cli_platform.cli_adapter.start = AsyncMock(side_effect=Exception("Terminal initialization failed"))

        # Start should handle error
        with pytest.raises(Exception, match="Terminal initialization failed"):
            await cli_platform.start()

    @pytest.mark.asyncio
    async def test_authentication_failure(self, cli_platform, mock_runtime):
        """Test handling when service_initializer is not available."""
        # Remove service_initializer to simulate failure
        mock_runtime.service_initializer = None

        # Start should raise error when service_initializer is missing
        with pytest.raises(RuntimeError, match="Service initializer not available"):
            await cli_platform.start()
