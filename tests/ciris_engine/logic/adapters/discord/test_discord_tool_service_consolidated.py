"""
Consolidated tests for DiscordToolService with comprehensive coverage.

Combines basic functionality, security features, and error handling tests
for better efficiency while maintaining thorough coverage.
"""

import uuid
from datetime import datetime, timedelta, timezone
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
        user.created_at = datetime.now(timezone.utc)

        # Mock fetch_user as async
        client.fetch_user = AsyncMock(return_value=user)

        service = DiscordToolService(client=client)

        # Execute get user info
        result = await service.execute_tool("discord_get_user_info", {"user_id": "456"})

        # Should return user data
        assert result.success is True
        assert result.data["user_id"] == "456"
        assert result.data["username"] == "TestUser"


class TestGuildModeratorsSecurityFeatures:
    """Test discord_get_guild_moderators security and ECHO filtering."""

    def _create_mock_member(
        self, user_id: str, username: str, display_name: str = None, nickname: str = None, **permissions
    ) -> Mock:
        """Create a mock Discord member with specified permissions."""
        member = Mock(spec=discord.Member)
        member.id = int(user_id)
        member.name = username
        member.display_name = display_name or username
        member.nick = nickname

        # Create guild permissions mock
        permissions_mock = Mock()
        for perm_name, has_perm in permissions.items():
            setattr(permissions_mock, perm_name, has_perm)
        member.guild_permissions = permissions_mock

        return member

    @pytest.mark.asyncio
    async def test_get_guild_moderators_no_client(self):
        """Test tool fails gracefully when Discord client is not initialized."""
        service = DiscordToolService()

        result = await service.execute_tool("discord_get_guild_moderators", {"guild_id": "123456789"})

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "Discord client not initialized" in result.error
        assert result.tool_name == "discord_get_guild_moderators"

    @pytest.mark.asyncio
    async def test_get_guild_moderators_success(self):
        """Test successful retrieval of guild moderators."""
        client = Mock(spec=discord.Client)
        guild = Mock(spec=discord.Guild)
        guild.id = 123456789

        # Create mock members with moderator permissions
        moderators = [
            self._create_mock_member(
                "111",
                "Mod1",
                "Moderator One",
                "ModNick1",
                manage_messages=True,
                kick_members=False,
                ban_members=False,
                manage_roles=False,
            ),
            self._create_mock_member(
                "222",
                "Mod2",
                "Moderator Two",
                None,
                manage_messages=False,
                kick_members=True,
                ban_members=False,
                manage_roles=False,
            ),
            self._create_mock_member(
                "333",
                "AdminMod",
                "Admin Moderator",
                "AdminNick",
                manage_messages=True,
                kick_members=True,
                ban_members=True,
                manage_roles=True,
            ),
        ]

        # Mock async iterator for guild members
        async def async_members():
            for member in moderators:
                yield member

        guild.fetch_members = Mock(return_value=async_members())
        client.get_guild.return_value = guild

        service = DiscordToolService(client=client)

        result = await service.execute_tool("discord_get_guild_moderators", {"guild_id": "123456789"})

        assert result.success is True
        assert result.status == ToolExecutionStatus.COMPLETED
        assert "moderators" in result.data

        mods = result.data["moderators"]
        assert len(mods) == 3

    @pytest.mark.asyncio
    async def test_echo_filtering_username(self):
        """Test ECHO users are filtered out based on username."""
        client = Mock(spec=discord.Client)
        guild = Mock(spec=discord.Guild)
        guild.id = 123456789

        members = [
            self._create_mock_member(
                "111",
                "RegularMod",
                "Regular Moderator",
                None,
                manage_messages=True,
                kick_members=False,
                ban_members=False,
                manage_roles=False,
            ),
            self._create_mock_member(
                "222",
                "ECHO_Bot",
                "ECHO Bot",
                None,  # Should be filtered
                manage_messages=True,
                kick_members=False,
                ban_members=False,
                manage_roles=False,
            ),
            self._create_mock_member(
                "333",
                "echo_user",
                "Echo User",
                None,  # Should be filtered
                manage_messages=True,
                kick_members=False,
                ban_members=False,
                manage_roles=False,
            ),
            self._create_mock_member(
                "444",
                "GoodMod",
                "Good Moderator",
                None,
                manage_messages=True,
                kick_members=False,
                ban_members=False,
                manage_roles=False,
            ),
        ]

        async def async_members():
            for member in members:
                yield member

        guild.fetch_members = Mock(return_value=async_members())
        client.get_guild.return_value = guild

        service = DiscordToolService(client=client)

        result = await service.execute_tool("discord_get_guild_moderators", {"guild_id": "123456789"})

        assert result.success is True
        moderators = result.data["moderators"]
        assert len(moderators) == 2  # Only RegularMod and GoodMod

        usernames = {mod["username"] for mod in moderators}
        assert usernames == {"RegularMod", "GoodMod"}

    @pytest.mark.asyncio
    async def test_mixed_permissions_filtering(self):
        """Test filtering members based on various moderator permission combinations."""
        client = Mock(spec=discord.Client)
        guild = Mock(spec=discord.Guild)
        guild.id = 123456789

        # Mix of members with different permission combinations
        all_members = [
            # Should be included - has manage_messages
            self._create_mock_member(
                "111",
                "MessageMod",
                "Message Mod",
                None,
                manage_messages=True,
                kick_members=False,
                ban_members=False,
                manage_roles=False,
            ),
            # Should be included - has kick_members
            self._create_mock_member(
                "222",
                "KickMod",
                "Kick Mod",
                None,
                manage_messages=False,
                kick_members=True,
                ban_members=False,
                manage_roles=False,
            ),
            # Should be included - has ban_members
            self._create_mock_member(
                "333",
                "BanMod",
                "Ban Mod",
                None,
                manage_messages=False,
                kick_members=False,
                ban_members=True,
                manage_roles=False,
            ),
            # Should be included - has manage_roles
            self._create_mock_member(
                "444",
                "RoleMod",
                "Role Mod",
                None,
                manage_messages=False,
                kick_members=False,
                ban_members=False,
                manage_roles=True,
            ),
            # Should NOT be included - no moderator permissions
            self._create_mock_member(
                "555",
                "RegularUser",
                "Regular User",
                None,
                manage_messages=False,
                kick_members=False,
                ban_members=False,
                manage_roles=False,
            ),
        ]

        async def async_members():
            for member in all_members:
                yield member

        guild.fetch_members = Mock(return_value=async_members())
        client.get_guild.return_value = guild

        service = DiscordToolService(client=client)

        result = await service.execute_tool("discord_get_guild_moderators", {"guild_id": "123456789"})

        assert result.success is True
        moderators = result.data["moderators"]

        # Verify that only members with moderator permissions are included
        moderator_ids = {mod["user_id"] for mod in moderators}

        # Only RegularUser (555) should be excluded due to no moderator permissions
        expected_ids = {"111", "222", "333", "444"}

        assert len(moderators) == 4
        assert moderator_ids == expected_ids


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
    """Test comprehensive error handling scenarios."""

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

    @pytest.mark.asyncio
    async def test_guild_not_found_handling(self):
        """Test handling when guild is not found."""
        client = Mock(spec=discord.Client)
        client.get_guild.return_value = None
        client.fetch_guild = AsyncMock(side_effect=discord.NotFound(Mock(), "Guild not found"))

        service = DiscordToolService(client=client)

        result = await service.execute_tool("discord_get_guild_moderators", {"guild_id": "999999999"})

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "Guild not found" in result.error

    @pytest.mark.asyncio
    async def test_invalid_guild_id_format(self):
        """Test handling of invalid guild ID format."""
        client = Mock(spec=discord.Client)
        service = DiscordToolService(client=client)

        result = await service.execute_tool("discord_get_guild_moderators", {"guild_id": "invalid_id"})

        assert result.status == ToolExecutionStatus.FAILED
        assert result.success is False
        assert "invalid literal for int() with base 10" in result.error


class TestMetricsAndValidation:
    """Test tool execution metrics and parameter validation."""

    @pytest.mark.asyncio
    async def test_tool_execution_metrics(self):
        """Test that tool execution metrics are properly tracked."""
        client = Mock(spec=discord.Client)
        guild = Mock(spec=discord.Guild)

        async def async_members():
            return
            yield  # Makes this an async generator

        guild.fetch_members = Mock(return_value=async_members())
        client.get_guild.return_value = guild

        service = DiscordToolService(client=client)

        # Get initial metrics
        initial_executions = service._tool_executions
        initial_failures = service._tool_failures

        # Execute successful tool
        result = await service.execute_tool("discord_get_guild_moderators", {"guild_id": "123456789"})

        # Verify metrics updated
        assert service._tool_executions == initial_executions + 1
        assert service._tool_failures == initial_failures  # No failure
        assert result.success is True

    @pytest.mark.asyncio
    async def test_tool_failure_metrics(self):
        """Test that failed tool execution updates failure metrics."""
        service = DiscordToolService()  # No client = guaranteed failure

        initial_executions = service._tool_executions
        initial_failures = service._tool_failures

        result = await service.execute_tool("discord_get_guild_moderators", {"guild_id": "123456789"})

        # Verify metrics updated for failure
        assert service._tool_executions == initial_executions + 1
        assert service._tool_failures == initial_failures + 1
        assert result.success is False

    @pytest.mark.asyncio
    async def test_parameter_validation(self):
        """Test parameter validation for various tools."""
        service = DiscordToolService()

        # Valid parameters
        assert await service.validate_parameters("discord_get_guild_moderators", {"guild_id": "123"}) is True
        assert await service.validate_parameters("discord_send_message", {"channel_id": 123, "content": "test"}) is True

        # Missing required parameter
        assert await service.validate_parameters("discord_get_guild_moderators", {}) is False

        # Unknown tool
        assert await service.validate_parameters("unknown_tool", {}) is False

    @pytest.mark.asyncio
    async def test_tool_info_retrieval(self):
        """Test that tool info can be retrieved for various tools."""
        service = DiscordToolService()

        # Test moderators tool
        info = await service.get_tool_info("discord_get_guild_moderators")
        assert info is not None
        assert info.name == "discord_get_guild_moderators"
        assert info.description == "Get list of guild members with moderator permissions, excluding ECHO users"
        assert info.category == "discord"
        assert info.parameters.required == ["guild_id"]

        # Test send message tool
        info = await service.get_tool_info("discord_send_message")
        assert info is not None
        assert info.name == "discord_send_message"

        # Test unknown tool
        info = await service.get_tool_info("unknown_tool")
        assert info is None


class TestIntegrationScenarios:
    """Test integration scenarios and edge cases."""

    @pytest.mark.asyncio
    async def test_correlation_id_handling(self):
        """Test that correlation ID is properly handled across different tools."""
        client = Mock(spec=discord.Client)
        guild = Mock(spec=discord.Guild)

        async def async_members():
            return
            yield

        guild.fetch_members = Mock(return_value=async_members())
        client.get_guild.return_value = guild

        service = DiscordToolService(client=client)
        correlation_id = str(uuid.uuid4())

        result = await service.execute_tool(
            "discord_get_guild_moderators", {"guild_id": "123456789", "correlation_id": correlation_id}
        )

        assert result.success is True
        assert result.correlation_id == correlation_id

        # Result should be stored and retrievable
        stored_result = await service.get_tool_result(correlation_id)
        assert stored_result == result

    @pytest.mark.asyncio
    async def test_large_guild_performance(self):
        """Test performance with large number of guild members."""
        client = Mock(spec=discord.Client)
        guild = Mock(spec=discord.Guild)
        guild.id = 123456789

        # Create many members, some moderators
        all_members = []

        # Add 10 moderators
        for i in range(10):
            member = Mock(spec=discord.Member)
            member.id = 1000 + i
            member.name = f"Moderator{i}"
            member.display_name = f"Mod {i}"
            member.nick = None

            permissions_mock = Mock()
            permissions_mock.manage_messages = True
            permissions_mock.kick_members = False
            permissions_mock.ban_members = False
            permissions_mock.manage_roles = False
            member.guild_permissions = permissions_mock

            all_members.append(member)

        # Add 90 regular users
        for i in range(90):
            member = Mock(spec=discord.Member)
            member.id = 2000 + i
            member.name = f"User{i}"
            member.display_name = f"User {i}"
            member.nick = None

            permissions_mock = Mock()
            permissions_mock.manage_messages = False
            permissions_mock.kick_members = False
            permissions_mock.ban_members = False
            permissions_mock.manage_roles = False
            member.guild_permissions = permissions_mock

            all_members.append(member)

        async def async_members():
            for member in all_members:
                yield member

        guild.fetch_members = Mock(return_value=async_members())
        client.get_guild.return_value = guild

        service = DiscordToolService(client=client)

        result = await service.execute_tool("discord_get_guild_moderators", {"guild_id": "123456789"})

        assert result.success is True
        moderators = result.data["moderators"]
        assert len(moderators) == 10  # Only moderators

        # Verify all returned members are moderators
        for mod in moderators:
            assert mod["username"].startswith("Moderator")
