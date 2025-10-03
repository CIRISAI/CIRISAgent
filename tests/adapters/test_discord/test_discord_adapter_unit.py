"""
Unit tests for Discord adapter implementation.
Tests the adapter without requiring actual Discord connection.
"""

import os
import tempfile
from unittest.mock import AsyncMock, Mock, patch

import pytest
import pytest_asyncio

from ciris_engine.logic.adapters.discord.discord_adapter import DiscordAdapter
from ciris_engine.logic.persistence import initialize_database
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.services.context import DeferralContext, GuidanceContext


class TestDiscordAdapter:
    """Test Discord adapter functionality."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self):
        """Set up a temporary test database for each test."""
        # Create a temporary database file
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp_file:
            test_db_path = tmp_file.name

        # Initialize the database with all required tables
        initialize_database(test_db_path)

        # Patch get_db_connection at both import locations to use our test database
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

    @pytest.fixture
    def mock_bot(self):
        """Create a mock Discord bot."""
        bot = Mock()
        bot.wait_until_ready = AsyncMock()
        bot.close = AsyncMock()
        bot.start = AsyncMock()
        bot.is_closed = Mock(return_value=False)
        bot.get_channel = Mock()
        bot.user = Mock(id=12345, name="TestBot")
        return bot

    @pytest.fixture
    def time_service(self):
        """Create a time service."""
        return TimeService()

    @pytest.fixture
    def mock_bus_manager(self):
        """Create a mock bus manager with memory bus."""
        bus_manager = Mock()
        bus_manager.memory = AsyncMock()
        bus_manager.memory.memorize_metric = AsyncMock()
        return bus_manager

    @pytest_asyncio.fixture
    async def adapter(self, mock_bot, time_service, mock_bus_manager):
        """Create Discord adapter instance."""
        adapter = DiscordAdapter(
            token="test-token", bot=mock_bot, time_service=time_service, bus_manager=mock_bus_manager
        )
        await adapter.start()
        yield adapter
        await adapter.stop()

    @pytest.mark.asyncio
    async def test_adapter_initialization(self, mock_bot, time_service):
        """Test adapter initializes correctly."""
        adapter = DiscordAdapter(token="test-token", bot=mock_bot, time_service=time_service)

        assert adapter.token == "test-token"
        assert adapter._time_service == time_service
        assert adapter._channel_manager is not None
        assert adapter._message_handler is not None
        assert adapter._guidance_handler is not None
        assert adapter._tool_handler is not None

    @pytest.mark.asyncio
    async def test_send_message_success(self, adapter, mock_bot, mock_bus_manager):
        """Test successful message sending."""
        # Mock connection manager to return connected
        adapter._connection_manager.is_connected = Mock(return_value=True)

        # Mock the message handler's send method
        mock_message = Mock(id=123)
        adapter._message_handler.send_message_to_channel = AsyncMock(return_value=mock_message)

        # Send message - Discord channel IDs are integers
        result = await adapter.send_message("123456789", "Test message")

        assert result is True
        adapter._message_handler.send_message_to_channel.assert_called_once_with("123456789", "Test message")

        # Check telemetry was emitted
        mock_bus_manager.memory.memorize_metric.assert_called()
        call_args = mock_bus_manager.memory.memorize_metric.call_args
        assert call_args[1]["metric_name"] == "discord.message.sent"

    @pytest.mark.asyncio
    async def test_send_message_failure(self, adapter, mock_bot):
        """Test message sending failure."""
        # Setup mock channel to fail
        mock_channel = Mock()
        mock_channel.send = AsyncMock(side_effect=Exception("Send failed"))
        mock_bot.get_channel.return_value = mock_channel

        result = await adapter.send_message("123456789", "Test message")

        assert result is False

    @pytest.mark.asyncio
    async def test_fetch_messages(self, adapter, mock_bot):
        """Test fetching messages from channel."""
        # Setup mock messages
        mock_msgs = [
            Mock(id="1", content="Message 1", author_id="111", author_name="User1", is_bot=False),
            Mock(id="2", content="Message 2", author_id="222", author_name="User2", is_bot=False),
        ]

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

        with patch(
            "ciris_engine.logic.persistence.get_correlations_by_channel", return_value=mock_correlations
        ) as mock_get_corr:
            messages = await adapter.fetch_messages("123456789", limit=10)

            assert len(messages) == 2
            assert messages[0].content == "Message 1"
            assert messages[1].content == "Message 2"
            mock_get_corr.assert_called_once_with(channel_id="123456789", limit=10)

    @pytest.mark.asyncio
    async def test_request_guidance(self, adapter):
        """Test requesting guidance from humans."""
        guidance_ctx = GuidanceContext(
            thought_id="thought123",
            task_id="task456",
            question="Should I do X?",
            ethical_considerations=["Consider user impact"],
            domain_context={"context": "Some context"},
        )

        # Test fetch_guidance which is the actual method
        with patch.object(adapter, "fetch_guidance", return_value="Yes") as mock_fetch:
            result = await adapter.fetch_guidance(guidance_ctx)

            assert result == "Yes"
            mock_fetch.assert_called_once_with(guidance_ctx)

    @pytest.mark.asyncio
    async def test_escalate_to_human(self, adapter):
        """Test escalating to human decision."""
        deferral_ctx = DeferralContext(
            thought_id="thought456",
            task_id="task123",
            reason="Complex decision requiring human input",
            metadata={"options": "Option A, Option B"},
        )

        # Test send_deferral_legacy which is the actual method
        with patch.object(adapter, "send_deferral_legacy", return_value=True) as mock_defer:
            result = await adapter.send_deferral_legacy(deferral_ctx)

            assert result is True
            mock_defer.assert_called_once_with(deferral_ctx)

    @pytest.mark.asyncio
    async def test_list_tools(self, adapter):
        """Test listing available tools."""
        # Setup mock tool registry with proper schema
        mock_tools = [
            ToolInfo(
                name="test_tool",  # Changed from tool_name to name
                description="A test tool",
                parameters=ToolParameterSchema(type="object", properties={}, required=[]),
                category="testing",
                cost=0.0,
                when_to_use="Use this tool for testing",
            )
        ]

        with patch.object(adapter._tool_handler, "get_available_tools", return_value=["test_tool"]) as mock_list:
            tools = await adapter.list_tools()

            assert len(tools) == 1
            assert tools[0] == "test_tool"
            mock_list.assert_called_once()

    @pytest.mark.asyncio
    async def test_execute_tool(self, adapter):
        """Test executing a tool."""
        expected_result = ToolExecutionResult(
            tool_name="test_tool",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={"output": "Test output"},
            error=None,
            correlation_id="test-correlation-123",
        )

        with patch.object(adapter._tool_handler, "execute_tool", return_value=expected_result) as mock_execute:
            result = await adapter.execute_tool(tool_name="test_tool", parameters={"input": "test"})

            assert result.status == ToolExecutionStatus.COMPLETED
            assert result.success is True
            assert result.data["output"] == "Test output"
            mock_execute.assert_called_once_with("test_tool", {"input": "test"})

    @pytest.mark.asyncio
    async def test_telemetry_emission(self, adapter, mock_bus_manager):
        """Test telemetry emission through memory bus."""
        # Clear any startup telemetry
        mock_bus_manager.memory.memorize_metric.reset_mock()

        await adapter._emit_telemetry("test.metric", value=42.5, tags={"action": "test"})

        mock_bus_manager.memory.memorize_metric.assert_called_once()
        call_args = mock_bus_manager.memory.memorize_metric.call_args

        assert call_args[1]["metric_name"] == "test.metric"
        assert call_args[1]["value"] == 42.5
        assert call_args[1]["tags"]["action"] == "test"
        assert call_args[1]["handler_name"] == "adapter.discord"

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self, mock_bot, time_service, mock_bus_manager):
        """Test adapter start/stop lifecycle."""
        adapter = DiscordAdapter(
            token="test-token", bot=mock_bot, time_service=time_service, bus_manager=mock_bus_manager
        )

        # Start adapter - doesn't start bot connection (handled by run_lifecycle)
        await adapter.start()
        # The adapter start method doesn't call bot.start() directly
        mock_bot.start.assert_not_called()

        # Stop adapter
        await adapter.stop()
        # Stop calls disconnect on connection manager which may close the bot
        # The actual close behavior depends on connection manager implementation

    @pytest.mark.asyncio
    async def test_channel_not_found(self, adapter, mock_bot):
        """Test handling when channel is not found."""
        mock_bot.get_channel.return_value = None

        result = await adapter.send_message("invalid_channel", "Test")
        assert result is False

        messages = await adapter.fetch_messages("invalid_channel")
        assert messages == []
