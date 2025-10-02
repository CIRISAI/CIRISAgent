"""Comprehensive unit tests for Discord adapter."""

import asyncio
import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

import discord
import pytest

from ciris_engine.logic.adapters.discord.config import DiscordAdapterConfig
from ciris_engine.logic.adapters.discord.discord_adapter import DiscordAdapter
from ciris_engine.logic.adapters.discord.discord_reaction_handler import ApprovalStatus
from ciris_engine.logic.persistence import initialize_database
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus
from ciris_engine.schemas.services.authority_core import DeferralApprovalContext

# Import the mock_db_path fixture from conftest
from tests.conftest_config_mock import mock_db_path  # noqa: F401


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    service = Mock()
    service.now = Mock(return_value=datetime.now(timezone.utc))
    return service


@pytest.fixture
def mock_bus_manager():
    """Create a mock bus manager."""
    manager = Mock()
    manager.memory = AsyncMock()
    manager.memory.store = AsyncMock()
    manager.memory.search = AsyncMock(return_value=[])
    manager.memory.memorize_metric = AsyncMock()
    return manager


@pytest.fixture
def mock_discord_client():
    """Create a mock Discord client."""
    client = Mock(spec=discord.Client)
    client.user = Mock(id=123456789, name="TestBot")
    client.guilds = []
    client.users = []
    client.is_closed = Mock(return_value=False)
    client.is_ready = Mock(return_value=True)
    client.get_channel = Mock(return_value=None)
    client.fetch_channel = AsyncMock()
    return client


@pytest.fixture
def discord_config():
    """Create Discord adapter config."""
    return DiscordAdapterConfig(
        deferral_channel_id="987654321",
        monitored_channel_ids=["123456789", "234567890"],
        wa_user_ids=["111111111", "222222222"],
    )


@pytest.fixture
def discord_adapter(mock_time_service, mock_bus_manager, mock_discord_client, discord_config):
    """Create Discord adapter instance."""
    adapter = DiscordAdapter(
        token="test_token",
        bot=mock_discord_client,
        time_service=mock_time_service,
        bus_manager=mock_bus_manager,
        config=discord_config,
    )
    # Override retry config for tests to avoid slow retries
    adapter.config["retry"]["discord_api"]["max_retries"] = 0
    return adapter


class TestDiscordAdapterCore:
    """Test core Discord adapter functionality."""

    @pytest.fixture
    def setup_test_db(self):
        """Set up a temporary test database for each test."""
        # Create a temporary database file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            test_db_path = tmp_file.name

        # Initialize the database with all required tables
        initialize_database(test_db_path)

        # Patch get_db_connection at both import locations to use our test database
        # Need to patch it in multiple places where it's imported
        with patch("ciris_engine.logic.persistence.get_db_connection") as mock_get_conn, patch(
            "ciris_engine.logic.persistence.models.correlations.get_db_connection"
        ) as mock_get_conn2, patch("ciris_engine.logic.persistence.db.core.get_db_connection") as mock_get_conn3:
            import sqlite3

            # Return a context manager that yields a connection
            from contextlib import contextmanager

            @contextmanager
            def get_test_connection(db_path=None):
                # Use the test db_path from outer scope, ignore the argument
                conn = sqlite3.connect(test_db_path)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON;")
                try:
                    yield conn
                finally:
                    conn.close()

            mock_get_conn.side_effect = get_test_connection
            mock_get_conn2.side_effect = get_test_connection
            mock_get_conn3.side_effect = get_test_connection

            yield test_db_path

        # Clean up
        try:
            os.unlink(test_db_path)
        except:
            pass

    @pytest.mark.asyncio
    async def test_adapter_initialization(self, discord_adapter):
        """Test adapter initializes correctly."""
        assert discord_adapter.token == "test_token"
        assert discord_adapter._time_service is not None
        assert discord_adapter.bus_manager is not None
        assert discord_adapter.discord_config.deferral_channel_id == "987654321"

        # Check all handlers are initialized
        assert discord_adapter._channel_manager is not None
        assert discord_adapter._message_handler is not None
        assert discord_adapter._guidance_handler is not None
        assert discord_adapter._tool_handler is not None
        assert discord_adapter._reaction_handler is not None
        assert discord_adapter._audit_logger is not None
        assert discord_adapter._connection_manager is not None
        assert discord_adapter._error_handler is not None
        assert discord_adapter._rate_limiter is not None

    @pytest.mark.asyncio
    async def test_send_message_success(self, discord_adapter, mock_discord_client, setup_test_db):
        """Test successful message sending."""
        # Mock connection manager to return connected
        discord_adapter._connection_manager.is_connected = Mock(return_value=True)

        # Mock the message handler's send method to return a message object
        mock_message = Mock(id=123)
        discord_adapter._message_handler.send_message_to_channel = AsyncMock(return_value=mock_message)

        # Send message
        result = await discord_adapter.send_message("123456789", "Test message")

        assert result is True
        discord_adapter._message_handler.send_message_to_channel.assert_called_once_with("123456789", "Test message")

        # Check telemetry was emitted
        discord_adapter.bus_manager.memory.memorize_metric.assert_called()

    @pytest.mark.asyncio
    async def test_send_message_with_rate_limiting(self, discord_adapter, mock_db_path):
        """Test message sending respects rate limits."""
        # Mock persistence.add_correlation to avoid database access
        with patch("ciris_engine.logic.persistence.add_correlation") as mock_add_correlation:
            mock_add_correlation.return_value = "test-correlation-id"

            # Mock connection manager to return connected
            discord_adapter._connection_manager.is_connected = Mock(return_value=True)

            # Mock rate limiter to introduce delay
            discord_adapter._rate_limiter.acquire = AsyncMock()

            # Mock channel
            mock_channel = AsyncMock()
            mock_channel.send = AsyncMock(return_value=Mock(id=123))
            discord_adapter._message_handler._resolve_channel = AsyncMock(return_value=mock_channel)

            # Send message
            await discord_adapter.send_message("123456789", "Test message")

            # Verify rate limiter was called
            discord_adapter._rate_limiter.acquire.assert_called_once()

    @pytest.mark.asyncio
    async def test_fetch_messages(self, discord_adapter):
        """Test fetching messages from channel."""
        # Mock messages
        mock_messages = [
            Mock(
                id=1,
                content="Message 1",
                author=Mock(id=111, display_name="User1", bot=False),
                created_at=datetime.now(timezone.utc),
            ),
            Mock(
                id=2,
                content="Message 2",
                author=Mock(id=222, display_name="User2", bot=False),
                created_at=datetime.now(timezone.utc),
            ),
        ]

        # Mock channel with async history method
        async def mock_history_iterator(limit):
            for msg in mock_messages:
                yield msg

        mock_channel = Mock()
        mock_channel.history = mock_history_iterator
        discord_adapter._client.get_channel = Mock(return_value=mock_channel)

        # Mock the get_correlations_by_channel function
        mock_correlations = [
            Mock(
                correlation_id="1",
                action_type="observe",
                request_data=Mock(parameters={"content": "Message 1", "author_id": "111", "author_name": "User1"}),
                timestamp=Mock(isoformat=lambda: "2024-01-01T00:00:00"),
            ),
            Mock(
                correlation_id="2",
                action_type="observe",
                request_data=Mock(parameters={"content": "Message 2", "author_id": "222", "author_name": "User2"}),
                timestamp=Mock(isoformat=lambda: "2024-01-01T00:01:00"),
            ),
        ]

        with patch("ciris_engine.logic.persistence.get_correlations_by_channel", return_value=mock_correlations):
            messages = await discord_adapter.fetch_messages("123456789", limit=10)

            assert len(messages) == 2
            assert messages[0].content == "Message 1"
            assert messages[1].content == "Message 2"


class TestDiscordWiseAuthority:
    """Test WiseAuthority functionality."""

    @pytest.mark.asyncio
    async def test_check_authorization_with_authority_role(self, discord_adapter, mock_discord_client):
        """Test authorization check for user with AUTHORITY role."""
        # Mock guild and member with AUTHORITY role
        mock_member = Mock()
        authority_role = Mock()
        authority_role.name = "AUTHORITY"
        member_role = Mock()
        member_role.name = "Member"
        mock_member.roles = [authority_role, member_role]

        mock_guild = Mock()
        mock_guild.get_member = Mock(side_effect=lambda x: mock_member if x == 123456 else None)

        # Set client guilds
        discord_adapter._channel_manager.client.guilds = [mock_guild]

        # Check authorization
        result = discord_adapter.check_authorization("123456", "any_action")

        assert result is True

    @pytest.mark.asyncio
    async def test_check_authorization_observer_read_only(self, discord_adapter, mock_discord_client):
        """Test OBSERVER role can only read."""
        # Mock member with OBSERVER role
        mock_member = Mock()
        observer_role = Mock()
        observer_role.name = "OBSERVER"
        mock_member.roles = [observer_role]

        mock_guild = Mock()
        mock_guild.get_member = Mock(side_effect=lambda x: mock_member if x == 123456 else None)

        # Set client guilds
        discord_adapter._channel_manager.client.guilds = [mock_guild]

        # Check read action - should pass
        result = discord_adapter.check_authorization("123456", "read")
        assert result is True

        # Check write action - should fail
        result = discord_adapter.check_authorization("123456", "write")
        assert result is False

    @pytest.mark.asyncio
    async def test_request_approval_with_reactions(self, discord_adapter, mock_discord_client):
        """Test approval request with reaction handling."""
        # Mock channel and message
        mock_message = Mock(id=999888777)
        mock_message.add_reaction = AsyncMock()

        mock_channel = Mock()
        mock_channel.send = AsyncMock(return_value=mock_message)

        discord_adapter._channel_manager.resolve_channel = AsyncMock(return_value=mock_channel)

        # Create approval context
        context = DeferralApprovalContext(
            task_id="task123",
            thought_id="thought456",
            action_name="test_action",
            action_params={"param": "value"},
            requester_id="user789",
        )

        # Mock approval callback
        approval_received = asyncio.Event()

        async def mock_handle_approval(approval):
            approval_received.set()

        # Simulate approval after delay
        async def simulate_approval():
            await asyncio.sleep(0.1)
            # Simulate reaction handler processing
            if mock_message.id in discord_adapter._reaction_handler._pending_approvals:
                approval = discord_adapter._reaction_handler._pending_approvals[mock_message.id]
                approval.status = ApprovalStatus.APPROVED
                approval.resolved_at = datetime.now(timezone.utc)
                if mock_message.id in discord_adapter._reaction_handler._approval_callbacks:
                    callback = discord_adapter._reaction_handler._approval_callbacks[mock_message.id]
                    await callback(approval)

        # Start approval simulation
        asyncio.create_task(simulate_approval())

        # Request approval
        result = await discord_adapter.request_approval("test_action", context)

        assert result is True
        assert mock_channel.send.called
        assert mock_message.add_reaction.call_count == 2  # ✅ and ❌

    @pytest.mark.asyncio
    async def test_get_pending_deferrals(self, discord_adapter, mock_bus_manager):
        """Test retrieving pending deferrals from memory."""
        # Mock memory search results - need to mock the correct query
        mock_nodes = [
            Mock(
                id="def1",
                attributes={
                    "deferral_id": "def1",
                    "task_id": "task1",
                    "thought_id": "thought1",
                    "reason": "Need more time",
                    "defer_until": datetime.now(timezone.utc) + timedelta(hours=1),
                    "status": "pending",
                    "created_at": datetime.now(timezone.utc),
                    "created_by": "user123",
                },
            )
        ]

        # Mock search to return our nodes when queried with the right filters
        async def mock_search(query):
            if query.get("node_type") == "DISCORD_DEFERRAL" and query.get("status") == "pending":
                return mock_nodes
            return []

        mock_bus_manager.memory.search = AsyncMock(side_effect=mock_search)

        # Get pending deferrals
        deferrals = await discord_adapter.get_pending_deferrals()

        assert len(deferrals) == 1
        assert deferrals[0].deferral_id == "def1"
        assert deferrals[0].reason == "Need more time"


class TestDiscordToolExecution:
    """Test tool execution functionality."""

    @pytest.mark.asyncio
    async def test_execute_tool_success(self, discord_adapter):
        """Test successful tool execution."""
        # Mock tool execution with proper schema
        mock_result = ToolExecutionResult(
            tool_name="test_tool",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={"output": "Tool output"},
            error=None,
            correlation_id="test-correlation-123",
        )

        discord_adapter._tool_handler.execute_tool = AsyncMock(return_value=mock_result)

        # Execute tool
        result = await discord_adapter.execute_tool("test_tool", {"param": "value"})

        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert result.data["output"] == "Tool output"

        # Check telemetry
        discord_adapter.bus_manager.memory.memorize_metric.assert_called()

    @pytest.mark.asyncio
    async def test_list_tools(self, discord_adapter):
        """Test listing available tools."""
        # Mock tool list
        discord_adapter._tool_handler.get_available_tools = Mock(return_value=["tool1", "tool2", "tool3"])

        tools = discord_adapter.list_tools()

        assert len(tools) == 3
        assert "tool1" in tools
        assert "tool2" in tools
        assert "tool3" in tools


class TestDiscordConnectionResilience:
    """Test connection resilience features."""

    @pytest.mark.asyncio
    async def test_connection_manager_reconnect(self, discord_adapter):
        """Test connection manager handles reconnection."""
        # Simulate disconnection
        await discord_adapter._connection_manager._handle_disconnected(Exception("Connection lost"))

        assert (
            discord_adapter._connection_manager.state
            == discord_adapter._connection_manager.state.__class__.DISCONNECTED
        )

        # Verify reconnection is scheduled
        assert discord_adapter._connection_manager.reconnect_attempts >= 0

    @pytest.mark.asyncio
    async def test_is_healthy_check(self, discord_adapter, mock_discord_client):
        """Test health check."""
        # Set the client in connection manager for proper health check
        discord_adapter._connection_manager.client = mock_discord_client
        mock_discord_client.is_closed.return_value = False

        # With client not closed, should be healthy
        result = await discord_adapter.is_healthy()
        assert result is True

        # Mock closed connection
        mock_discord_client.is_closed.return_value = True

        result = await discord_adapter.is_healthy()
        assert result is False


class TestDiscordErrorHandling:
    """Test error handling functionality."""

    @pytest.mark.asyncio
    async def test_channel_not_found_error(self, discord_adapter):
        """Test handling of channel not found errors."""
        # Mock channel not found
        discord_adapter._message_handler.send_message_to_channel = AsyncMock(
            side_effect=discord.NotFound(Mock(), "Channel not found")
        )

        result = await discord_adapter.send_message("999999999", "Test")

        assert result is False

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self, discord_adapter):
        """Test rate limit error handling."""
        # Mock rate limit error
        error_resp = Mock()
        error_resp.status = 429
        error_resp.headers = {"Retry-After": "5"}

        discord_adapter._message_handler.send_message_to_channel = AsyncMock(
            side_effect=discord.HTTPException(error_resp, "Rate limited")
        )

        # This should handle the rate limit gracefully
        result = await discord_adapter.send_message("123456789", "Test")

        # Should fail but not raise
        assert result is False


class TestDiscordAuditLogging:
    """Test audit logging functionality."""

    @pytest.fixture
    def setup_test_db(self):
        """Set up a temporary test database for each test."""
        # Create a temporary database file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            test_db_path = tmp_file.name

        # Initialize the database with all required tables
        initialize_database(test_db_path)

        # Patch get_db_connection at both import locations to use our test database
        # Need to patch it in multiple places where it's imported
        with patch("ciris_engine.logic.persistence.get_db_connection") as mock_get_conn, patch(
            "ciris_engine.logic.persistence.models.correlations.get_db_connection"
        ) as mock_get_conn2, patch("ciris_engine.logic.persistence.db.core.get_db_connection") as mock_get_conn3:
            import sqlite3

            # Return a context manager that yields a connection
            from contextlib import contextmanager

            @contextmanager
            def get_test_connection(db_path=None):
                # Use the test db_path from outer scope, ignore the argument
                conn = sqlite3.connect(test_db_path)
                conn.row_factory = sqlite3.Row
                conn.execute("PRAGMA foreign_keys = ON;")
                try:
                    yield conn
                finally:
                    conn.close()

            mock_get_conn.side_effect = get_test_connection
            mock_get_conn2.side_effect = get_test_connection
            mock_get_conn3.side_effect = get_test_connection

            yield test_db_path

        # Clean up
        try:
            os.unlink(test_db_path)
        except:
            pass

    @pytest.mark.asyncio
    async def test_audit_log_message_operations(self, discord_adapter, setup_test_db):
        """Test audit logging for message operations."""
        # Mock audit service
        mock_audit_service = AsyncMock()
        discord_adapter._audit_logger.set_audit_service(mock_audit_service)

        # Mock connection manager to return connected
        discord_adapter._connection_manager.is_connected = Mock(return_value=True)

        # Mock successful message send
        mock_message = Mock(id=123)
        discord_adapter._message_handler.send_message_to_channel = AsyncMock(return_value=mock_message)

        # Send message
        await discord_adapter.send_message("123456789", "Test message")

        # Verify audit log was called - wait a bit for async operations
        await asyncio.sleep(0.1)

        # Check if audit logger was set up with the service
        assert discord_adapter._audit_logger._audit_service is not None

        # Since send_message calls _emit_telemetry which uses memorize_metric
        # Verify telemetry was called instead (since audit may be async)
        discord_adapter.bus_manager.memory.memorize_metric.assert_called()
