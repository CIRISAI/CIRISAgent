"""
Comprehensive tests for DiscordToolService with FAIL FAST AND LOUD policy.

Tests the service layer that wraps Discord tools, ensuring proper error handling,
correlation tracking, and tool execution.
"""

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest

from ciris_engine.logic.adapters.discord.discord_tool_service import DiscordToolService
from ciris_engine.schemas.adapters.tools import ToolExecutionResult, ToolExecutionStatus, ToolInfo, ToolParameterSchema
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities


class TestDiscordToolServiceInitialization:
    """Test service initialization and configuration."""

    def test_init_without_client(self):
        """Test service can be initialized without a client."""
        service = DiscordToolService()
        assert service._client is None
        assert service._tools is not None
        assert len(service._tools) == 11  # All tools registered

    def test_init_with_client(self):
        """Test service initialization with Discord client."""
        client = Mock(spec=discord.Client)
        time_service = Mock()
        service = DiscordToolService(client=client, time_service=time_service)

        assert service._client is client
        assert service._time_service is time_service

    def test_set_client(self):
        """Test updating the Discord client after initialization."""
        service = DiscordToolService()
        client = Mock(spec=discord.Client)

        service.set_client(client)

        assert service._client is client

    def test_start_stop(self):
        """Test service lifecycle methods."""
        service = DiscordToolService()

        # Should not raise
        service.start()
        service.stop()


class TestToolExecution:
    """Test tool execution with various scenarios."""

    @pytest.mark.asyncio
    async def test_execute_tool_no_client(self):
        """Test FAIL FAST when client is not initialized."""
        service = DiscordToolService()

        result = await service.execute_tool("discord_send_message", {"channel_id": 123, "content": "test"})

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "Discord client not initialized" in result.error
        assert result.tool_name == "discord_send_message"

    @pytest.mark.asyncio
    async def test_execute_unknown_tool(self):
        """Test FAIL FAST with unknown tool name."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)

        result = await service.execute_tool("discord_unknown_tool", {})

        assert result.status == ToolExecutionStatus.NOT_FOUND
        assert result.success is False
        assert "Unknown Discord tool" in result.error

    @pytest.mark.asyncio
    async def test_execute_tool_with_correlation_id(self):
        """Test that correlation ID is properly handled."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)
        correlation_id = str(uuid.uuid4())

        # Mock the internal tool method
        mock_result = {"success": True, "data": {"message": "sent"}}
        service._tools["discord_send_message"] = AsyncMock(return_value=mock_result)

        result = await service.execute_tool(
            "discord_send_message", {"channel_id": 123, "content": "test", "correlation_id": correlation_id}
        )

        assert result.correlation_id == correlation_id
        assert result.success is True
        # Verify correlation_id was removed from parameters passed to tool
        service._tools["discord_send_message"].assert_called_once_with({"channel_id": 123, "content": "test"})

    @pytest.mark.asyncio
    async def test_execute_tool_success(self):
        """Test successful tool execution."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)

        # Mock the delete message tool
        mock_result = {"success": True, "data": {"deleted": True}}
        service._tools["discord_delete_message"] = AsyncMock(return_value=mock_result)

        result = await service.execute_tool("discord_delete_message", {"channel_id": 123, "message_id": 456})

        assert result.status == ToolExecutionStatus.COMPLETED
        assert result.success is True
        assert result.data == {"deleted": True}
        assert result.error is None

    @pytest.mark.asyncio
    async def test_execute_tool_failure(self):
        """Test tool execution failure with clear error reporting."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)

        # Mock tool failure
        mock_result = {"success": False, "error": "Permission denied"}
        service._tools["discord_ban_user"] = AsyncMock(return_value=mock_result)

        result = await service.execute_tool("discord_ban_user", {"guild_id": 123, "user_id": 456})

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert result.error == "Permission denied"

    @pytest.mark.asyncio
    async def test_execute_tool_exception(self):
        """Test FAIL LOUD when tool raises exception."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)

        # Mock tool raising exception
        service._tools["discord_timeout_user"] = AsyncMock(side_effect=Exception("Unexpected error in timeout"))

        result = await service.execute_tool("discord_timeout_user", {"guild_id": 123, "user_id": 456, "duration": 300})

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "Unexpected error in timeout" in result.error


class TestToolRegistry:
    """Test tool registration and discovery."""

    @pytest.mark.asyncio
    async def test_get_available_tools(self):
        """Test getting list of available tools."""
        service = DiscordToolService()
        tools = await service.get_available_tools()

        assert isinstance(tools, list)
        assert len(tools) == 11
        assert "discord_send_message" in tools
        assert "discord_delete_message" in tools
        assert "discord_timeout_user" in tools
        assert "discord_ban_user" in tools

    @pytest.mark.asyncio
    async def test_get_tool_info(self):
        """Test getting info for specific tool."""
        service = DiscordToolService()

        # Get info for delete message tool
        info = await service.get_tool_info("discord_delete_message")

        assert info is not None
        assert info.name == "discord_delete_message"
        assert info.description == "Delete a message from a Discord channel"
        assert info.category == "discord"
        assert isinstance(info.parameters, ToolParameterSchema)

    @pytest.mark.asyncio
    async def test_get_tool_info_unknown(self):
        """Test getting info for unknown tool returns None."""
        service = DiscordToolService()

        info = await service.get_tool_info("unknown_tool")

        assert info is None

    @pytest.mark.asyncio
    async def test_list_tools(self):
        """Test listing tools."""
        service = DiscordToolService()
        tools = await service.list_tools()

        assert isinstance(tools, list)
        assert len(tools) == 11
        assert "discord_send_message" in tools


class TestServiceCapabilities:
    """Test service capability reporting."""

    def test_get_capabilities(self):
        """Test service capabilities are properly reported."""
        service = DiscordToolService()
        caps = service.get_capabilities()

        assert isinstance(caps, ServiceCapabilities)
        assert caps.service_name == "DiscordToolService"
        assert "execute_tool" in caps.actions
        assert "get_available_tools" in caps.actions
        assert caps.version == "1.0.0"
        assert isinstance(caps.metadata, dict)

    def test_get_service_type(self):
        """Test service type is correct."""
        service = DiscordToolService()

        assert service.get_service_type() == ServiceType.TOOL


class TestSpecificTools:
    """Test specific Discord tool implementations."""

    @pytest.mark.asyncio
    async def test_send_message_tool(self):
        """Test send message tool execution."""
        client = Mock(spec=discord.Client)
        # Create a proper TextChannel mock
        channel = AsyncMock(spec=discord.TextChannel)
        channel.send = AsyncMock(return_value=Mock(id=123456))
        client.get_channel.return_value = channel

        service = DiscordToolService(client=client)

        # Execute send message
        result = await service.execute_tool("discord_send_message", {"channel_id": 123, "content": "Test message"})

        # Verify result
        assert result.success is True
        assert result.status == ToolExecutionStatus.COMPLETED
        channel.send.assert_called_once_with("Test message")

    @pytest.mark.asyncio
    async def test_send_embed_tool(self):
        """Test send embed tool execution."""
        client = Mock(spec=discord.Client)
        # Create a proper TextChannel mock
        channel = AsyncMock(spec=discord.TextChannel)
        channel.send = AsyncMock(return_value=Mock(id=123456))
        client.get_channel.return_value = channel

        service = DiscordToolService(client=client)

        # Execute send embed
        result = await service.execute_tool(
            "discord_send_embed",
            {"channel_id": 123, "title": "Test Embed", "description": "Test Description", "color": 0xFF0000},
        )

        # Verify result
        assert result.success is True
        assert result.status == ToolExecutionStatus.COMPLETED
        # Verify channel.send was called with an embed
        channel.send.assert_called_once()
        call_args = channel.send.call_args
        assert "embed" in call_args.kwargs
        embed = call_args.kwargs["embed"]
        assert isinstance(embed, discord.Embed)

    @pytest.mark.asyncio
    async def test_get_user_info_tool(self):
        """Test get user info tool."""
        client = Mock(spec=discord.Client)
        user = Mock(spec=discord.User)
        user.id = 456
        user.name = "TestUser"
        user.discriminator = "1234"
        user.avatar = None  # No avatar for simplicity
        user.bot = False
        user.created_at = datetime.utcnow()

        # Mock fetch_user as async
        client.fetch_user = AsyncMock(return_value=user)

        service = DiscordToolService(client=client)

        # Execute get user info
        result = await service.execute_tool("discord_get_user_info", {"user_id": "456"})

        # Should return user data
        assert result.success is True
        assert result.data["user_id"] == "456"
        assert result.data["username"] == "TestUser"


class TestResultStorage:
    """Test result storage and retrieval."""

    @pytest.mark.asyncio
    async def test_store_result(self):
        """Test that results are stored for retrieval."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)

        # Mock successful execution
        mock_result = {"success": True, "data": {"test": "data"}}
        service._tools["discord_send_message"] = AsyncMock(return_value=mock_result)

        result = await service.execute_tool("discord_send_message", {"channel_id": 123, "content": "test"})

        # Result should be stored
        assert result.correlation_id in service._results
        assert service._results[result.correlation_id] == result

    @pytest.mark.asyncio
    async def test_get_tool_result(self):
        """Test retrieving stored results."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)
        correlation_id = str(uuid.uuid4())

        # Store a result
        result = ToolExecutionResult(
            tool_name="test_tool",
            status=ToolExecutionStatus.COMPLETED,
            success=True,
            data={"test": "data"},
            correlation_id=correlation_id,
        )
        service._results[correlation_id] = result

        # Retrieve it using the async get_tool_result method
        retrieved = await service.get_tool_result(correlation_id)
        assert retrieved == result

        # Non-existent result should return None
        assert await service.get_tool_result("non-existent") is None


class TestErrorHandling:
    """Test comprehensive error handling."""

    @pytest.mark.asyncio
    async def test_network_error_handling(self):
        """Test handling of network errors."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)

        # Mock network error
        service._tools["discord_send_message"] = AsyncMock(side_effect=discord.HTTPException(Mock(), "Network timeout"))

        result = await service.execute_tool("discord_send_message", {"channel_id": 123, "content": "test"})

        assert result.status == ToolExecutionStatus.FAILED
        assert "Network timeout" in result.error

    @pytest.mark.asyncio
    async def test_rate_limit_handling(self):
        """Test handling of rate limits."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)

        # Mock rate limit error
        service._tools["discord_ban_user"] = AsyncMock(side_effect=discord.RateLimited(retry_after=5.0))

        result = await service.execute_tool("discord_ban_user", {"guild_id": 123, "user_id": 456})

        assert result.status == ToolExecutionStatus.FAILED
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_permission_error_handling(self):
        """Test handling of permission errors."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)

        # Mock permission error
        mock_result = {"success": False, "error": "Missing Permissions: BAN_MEMBERS"}
        service._tools["discord_ban_user"] = AsyncMock(return_value=mock_result)

        result = await service.execute_tool("discord_ban_user", {"guild_id": 123, "user_id": 456})

        assert result.status == ToolExecutionStatus.FAILED
        assert "Missing Permissions" in result.error
        assert "BAN_MEMBERS" in result.error
