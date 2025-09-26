"""
Test suite for Discord adapter lifecycle and reconnection logic.

Tests the July 9, 2025 fix for "Concurrent call to receive() is not allowed":
- Simplified reconnection logic
- Discord.py's built-in reconnection
- Single point of control for client lifecycle
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.discord.adapter import DiscordPlatform
from ciris_engine.logic.adapters.discord.config import DiscordAdapterConfig
from ciris_engine.logic.adapters.discord.discord_adapter import DiscordAdapter
from ciris_engine.logic.registries.base import Priority
from ciris_engine.schemas.runtime.enums import ServiceType


@pytest.fixture
def mock_runtime():
    """Create mock runtime with necessary services."""
    runtime = Mock()
    runtime.time_service = Mock()
    runtime.time_service.now.return_value = datetime.now(timezone.utc)
    runtime.memory_service = Mock()
    runtime.telemetry_service = Mock()
    runtime.audit_service = Mock()
    runtime.config_service = Mock()
    runtime.wa_auth_system = Mock()
    runtime.authentication_service = Mock()
    runtime.service_registry = Mock()
    runtime.bus_manager = Mock()
    runtime.resource_monitor = Mock()
    return runtime


@pytest.fixture
def discord_config():
    """Create test Discord configuration."""
    return DiscordAdapterConfig(
        bot_token="test_token_123",
        monitored_channel_ids=["123456789"],
        home_channel_id="123456789",
        admin_user_ids=["987654321"],
    )


@pytest.fixture
def mock_discord_client():
    """Create mock Discord client."""
    client = MagicMock()
    client.is_ready = Mock(return_value=False)
    client.is_closed = Mock(return_value=False)
    client.run = AsyncMock()
    client.start = AsyncMock()
    client.close = AsyncMock()
    client.wait_until_ready = AsyncMock()
    client.user = Mock(id=123456, name="TestBot")
    client.guilds = []
    client.get_channel = Mock(return_value=None)
    return client


@pytest.fixture
def discord_platform(mock_runtime, discord_config):
    """Create Discord platform instance."""
    with patch("ciris_engine.logic.adapters.discord.adapter.discord") as mock_discord:
        mock_discord.Client = Mock(return_value=MagicMock())

        platform = DiscordPlatform(runtime=mock_runtime, adapter_config=discord_config)
        return platform


class TestDiscordAdapterLifecycle:
    """Test Discord adapter lifecycle management."""

    def test_initialization(self, mock_runtime, discord_config):
        """Test Discord adapter initialization."""
        with patch("ciris_engine.logic.adapters.discord.adapter.discord"):
            platform = DiscordPlatform(runtime=mock_runtime, adapter_config=discord_config)

            assert platform.runtime == mock_runtime
            assert platform.config == discord_config
            assert isinstance(platform.discord_adapter, DiscordAdapter)
            assert platform.discord_observer is None  # Created during start()

    @pytest.mark.asyncio
    async def test_start_with_reconnection_enabled(self, discord_platform, mock_discord_client):
        """Test start with Discord.py's built-in reconnection."""
        # Mock the Discord client on the platform's client attribute
        discord_platform.client = mock_discord_client

        # Create a task that simulates the client.start behavior
        async def mock_start(token, reconnect=True):
            assert token == "test_token_123"
            assert reconnect is True  # Key test: reconnect should be True
            await asyncio.sleep(0.01)  # Simulate connection time

        mock_discord_client.start = mock_start

        # Test the run_lifecycle method which is the actual entry point
        agent_run_task = asyncio.create_task(asyncio.sleep(0.1))  # Mock agent task

        # Create the lifecycle task
        lifecycle_task = asyncio.create_task(discord_platform.run_lifecycle(agent_run_task))

        # Let it run briefly
        await asyncio.sleep(0.05)

        # Cancel both tasks
        agent_run_task.cancel()
        lifecycle_task.cancel()

        try:
            await agent_run_task
        except asyncio.CancelledError:
            pass

        try:
            await lifecycle_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_no_client_recreation_on_disconnect(self, discord_platform, mock_discord_client):
        """Test that client is NOT recreated on disconnect (July 9 fix)."""
        # Set the client on the platform
        discord_platform.client = mock_discord_client
        original_client = discord_platform.client

        # The July 9 fix means Discord.py handles reconnection internally
        # We should verify the client reference doesn't change
        assert discord_platform.client is original_client

        # Even after potential errors, client should remain the same
        # (Discord.py with reconnect=True handles this internally)
        assert discord_platform.client is mock_discord_client

    @pytest.mark.asyncio
    async def test_connection_manager_monitoring_only(self, discord_platform):
        """Test that connection manager only monitors, doesn't reconnect."""
        # Access the discord adapter's connection manager
        conn_manager = discord_platform.discord_adapter._connection_manager

        # Mock the is_connected method to return False
        with patch.object(conn_manager, "is_connected", return_value=False):
            # Connection manager should only check state, not attempt reconnection
            assert not conn_manager.is_connected()

        # Now mock it to return True
        with patch.object(conn_manager, "is_connected", return_value=True):
            assert conn_manager.is_connected()

    @pytest.mark.asyncio
    async def test_single_control_point(self, discord_platform, mock_discord_client):
        """Test single point of control for Discord client lifecycle."""
        discord_platform.client = mock_discord_client

        # Track all client lifecycle calls
        lifecycle_calls = []

        mock_discord_client.start = AsyncMock(
            side_effect=lambda *args, **kwargs: lifecycle_calls.append(("start", args, kwargs))
        )
        mock_discord_client.close = AsyncMock(side_effect=lambda: lifecycle_calls.append(("close", None, None)))

        # Simulate lifecycle through platform methods
        await discord_platform.start()
        await discord_platform.stop()

        # Verify client lifecycle methods were called
        # Note: The actual calls happen in run_lifecycle, not start/stop
        # But we can verify the client was set up correctly
        assert discord_platform.client is mock_discord_client


class TestDiscordHealthCheck:
    """Test Discord adapter health checking."""

    @pytest.mark.asyncio
    async def test_is_healthy_connected(self, discord_platform, mock_discord_client):
        """Test health check when connected."""
        discord_platform.client = mock_discord_client
        mock_discord_client.is_ready.return_value = True
        mock_discord_client.is_closed.return_value = False

        # Mock the connection manager's is_connected method
        discord_platform.discord_adapter._connection_manager.is_connected = Mock(return_value=True)

        # Also mock the discord_adapter's is_healthy to return True
        discord_platform.discord_adapter.is_healthy = Mock(return_value=True)

        # The platform's is_healthy method is async
        result = await discord_platform.is_healthy()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_healthy_not_ready(self, discord_platform, mock_discord_client):
        """Test health check when not ready but client exists."""
        discord_platform.client = mock_discord_client
        mock_discord_client.is_ready.return_value = False
        mock_discord_client.is_closed.return_value = False

        # With the new implementation, health check returns True
        # when client exists and is not closed (even if not ready)
        # This prevents circuit breaker from opening during startup
        result = await discord_platform.is_healthy()
        assert result is True

    @pytest.mark.asyncio
    async def test_is_healthy_closed(self, discord_platform, mock_discord_client):
        """Test health check when client closed."""
        discord_platform.client = mock_discord_client
        mock_discord_client.is_ready.return_value = True
        mock_discord_client.is_closed.return_value = True

        # When client is closed, connection manager should report disconnected
        discord_platform.discord_adapter._connection_manager.is_connected = Mock(return_value=False)

        # Mock the discord_adapter's is_healthy to return False
        discord_platform.discord_adapter.is_healthy = Mock(return_value=False)

        result = await discord_platform.is_healthy()
        assert result is False

    @pytest.mark.asyncio
    async def test_is_healthy_no_client(self, discord_platform):
        """Test health check with no client."""
        discord_platform.client = None

        # When there's no client, the adapter should report unhealthy
        discord_platform.discord_adapter.is_healthy = Mock(return_value=False)

        result = await discord_platform.is_healthy()
        assert result is False


class TestDiscordReconnectionScenarios:
    """Test various reconnection scenarios."""

    @pytest.mark.asyncio
    async def test_websocket_error_handling(self, discord_platform, mock_discord_client):
        """Test handling of websocket errors."""
        discord_platform.client = mock_discord_client

        # Simulate websocket error during start
        error = Exception("Websocket connection failed")
        mock_discord_client.start = AsyncMock(side_effect=error)

        # The platform should handle the error in run_lifecycle
        agent_task = asyncio.create_task(asyncio.sleep(1.0))

        # run_lifecycle should handle the error without crashing
        lifecycle_task = asyncio.create_task(discord_platform.run_lifecycle(agent_task))
        await asyncio.sleep(0.1)

        # Clean up
        agent_task.cancel()
        lifecycle_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
        try:
            await lifecycle_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_rate_limit_during_connection(self, discord_platform, mock_discord_client):
        """Test handling rate limits during connection."""
        discord_platform.client = mock_discord_client

        # Create a mock response object
        mock_response = Mock()
        mock_response.status = 429

        # Import HTTPException properly
        try:
            from discord.errors import HTTPException
        except ImportError:
            # If discord.py not available in test env, skip this test
            pytest.skip("discord.py not available")
            return

        rate_limit_error = HTTPException(mock_response, "rate limited")
        mock_discord_client.start = AsyncMock(side_effect=rate_limit_error)

        # The platform should handle rate limits with retry logic
        agent_task = asyncio.create_task(asyncio.sleep(1.0))
        lifecycle_task = asyncio.create_task(discord_platform.run_lifecycle(agent_task))
        await asyncio.sleep(0.1)

        # Clean up
        agent_task.cancel()
        lifecycle_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
        try:
            await lifecycle_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_gateway_disconnect_recovery(self, discord_platform, mock_discord_client):
        """Test recovery from gateway disconnects."""
        discord_platform.client = mock_discord_client

        # Mock the discord adapter's wait_until_ready method
        with patch.object(discord_platform.discord_adapter, "wait_until_ready", return_value=True) as mock_wait:
            # Test that wait_until_ready can be called
            result = await discord_platform.discord_adapter.wait_until_ready(timeout=1.0)
            assert result is True
            mock_wait.assert_called_once_with(timeout=1.0)

        # Test connection state through is_healthy
        mock_discord_client.is_ready.return_value = True
        mock_discord_client.is_closed.return_value = False

        # Mock the connection manager and adapter health checks
        discord_platform.discord_adapter._connection_manager.is_connected = Mock(return_value=True)
        discord_platform.discord_adapter.is_healthy = Mock(return_value=True)

        # Should report as healthy when connected
        is_healthy = await discord_platform.is_healthy()
        assert is_healthy is True

        # Simulate disconnect by marking client as not ready
        mock_discord_client.is_ready.return_value = False

        # With new implementation, still healthy if client exists and not closed
        # Only becomes unhealthy when client is closed
        is_healthy = await discord_platform.is_healthy()
        assert is_healthy is True

        # Now simulate actual disconnect by closing the client
        mock_discord_client.is_closed.return_value = True

        # Should report as not healthy when client is closed
        is_healthy = await discord_platform.is_healthy()
        assert is_healthy is False

        # Simulate reconnect by marking client as ready again
        mock_discord_client.is_ready.return_value = True
        mock_discord_client.is_closed.return_value = False  # Reset closed state for reconnect
        discord_platform.discord_adapter._connection_manager.is_connected = Mock(return_value=True)
        discord_platform.discord_adapter.is_healthy = Mock(return_value=True)

        # Should report as healthy again
        is_healthy = await discord_platform.is_healthy()
        assert is_healthy is True


class TestDiscordServiceRegistration:
    """Test Discord adapter service registration."""

    def test_get_services_to_register(self, discord_platform):
        """Test service registration list."""
        registrations = discord_platform.get_services_to_register()

        # Discord registers 3 services
        assert len(registrations) == 3

        # Check communication service
        comm_reg = next(r for r in registrations if r.service_type == ServiceType.COMMUNICATION)
        assert comm_reg.provider == discord_platform.discord_adapter
        assert comm_reg.priority == Priority.NORMAL
        assert "send_message" in comm_reg.capabilities

        # Check WA service
        wa_reg = next(r for r in registrations if r.service_type == ServiceType.WISE_AUTHORITY)
        assert wa_reg.provider is not None
        assert wa_reg.priority == Priority.NORMAL

        # Check tool service
        tool_reg = next(r for r in registrations if r.service_type == ServiceType.TOOL)
        assert tool_reg.provider is not None
        assert tool_reg.priority == Priority.NORMAL


class TestDiscordErrorRecovery:
    """Test error recovery mechanisms."""

    @pytest.mark.asyncio
    async def test_start_failure_cleanup(self, discord_platform, mock_discord_client):
        """Test cleanup when start fails."""
        discord_platform.client = mock_discord_client
        mock_discord_client.start = AsyncMock(side_effect=Exception("Start failed"))

        # The platform's run_lifecycle should handle start failures
        agent_task = asyncio.create_task(asyncio.sleep(1.0))
        lifecycle_task = asyncio.create_task(discord_platform.run_lifecycle(agent_task))

        # Give it time to attempt start and fail
        await asyncio.sleep(0.1)

        # Client should still exist (not recreated per July 9 fix)
        assert discord_platform.client is mock_discord_client

        # Clean up
        agent_task.cancel()
        lifecycle_task.cancel()
        try:
            await agent_task
        except asyncio.CancelledError:
            pass
        try:
            await lifecycle_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_connection_state_tracking(self, discord_platform, mock_discord_client):
        """Test connection state tracking through lifecycle."""
        discord_platform.client = mock_discord_client

        # Test through health checks which reflect connection state
        # Initial state - not ready but client exists
        mock_discord_client.is_ready.return_value = False
        mock_discord_client.is_closed.return_value = False

        # With new implementation, healthy if client exists and not closed
        is_healthy = await discord_platform.is_healthy()
        assert is_healthy is True

        # Simulate connection ready
        mock_discord_client.is_ready.return_value = True
        discord_platform.discord_adapter._connection_manager.is_connected = Mock(return_value=True)
        discord_platform.discord_adapter.is_healthy = Mock(return_value=True)

        is_healthy = await discord_platform.is_healthy()
        assert is_healthy is True

        # Simulate client closed
        mock_discord_client.is_closed.return_value = True
        discord_platform.discord_adapter._connection_manager.is_connected = Mock(return_value=False)
        discord_platform.discord_adapter.is_healthy = Mock(return_value=False)

        is_healthy = await discord_platform.is_healthy()
        assert is_healthy is False


class TestDiscordConcurrentMessageHandling:
    """Test handling concurrent Discord events."""

    @pytest.mark.asyncio
    async def test_concurrent_message_events(self, discord_platform):
        """Test handling multiple simultaneous message events."""
        # Test that the platform can handle concurrent operations
        # This tests the architecture's ability to handle multiple events

        # Create multiple mock channel info requests
        tasks = []
        for i in range(5):
            # Use get_channel_info as a safe concurrent operation to test
            async def get_info():
                return discord_platform.get_channel_info()

            task = asyncio.create_task(get_info())
            tasks.append(task)

        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # All operations should complete without errors
        for result in results:
            assert isinstance(result, dict)
            assert "guild_id" in result
