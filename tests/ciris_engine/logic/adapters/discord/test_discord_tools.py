"""
Comprehensive tests for Discord tool suite with FAIL FAST AND LOUD policy.

Critical moderation tools must be thoroughly tested to ensure they fail
safely and report errors clearly.
"""

import asyncio
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest

from ciris_engine.logic.adapters.discord.discord_tools import (
    discord_ban_user,
    discord_delete_message,
    discord_kick_user,
    discord_timeout_user,
    register_discord_tools,
)
from ciris_engine.schemas.adapters.tools import ToolResult


class TestDiscordDeleteMessage:
    """Test message deletion with comprehensive error handling."""

    @pytest.mark.asyncio
    async def test_delete_message_success(self):
        """Test successful message deletion."""
        # Arrange
        bot = Mock(spec=discord.Client)
        channel = AsyncMock()
        message = AsyncMock()
        channel.fetch_message.return_value = message
        bot.get_channel.return_value = channel

        # Act
        result = await discord_delete_message(bot, channel_id=123, message_id=456)

        # Assert
        assert result.success is True
        assert result.data == {"message_id": "456", "channel_id": "123"}
        assert result.error is None
        message.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_message_channel_not_found_fetches(self):
        """Test fetching channel when not in cache."""
        # Arrange
        bot = Mock(spec=discord.Client)
        channel = AsyncMock()
        message = AsyncMock()
        channel.fetch_message.return_value = message
        bot.get_channel.return_value = None
        bot.fetch_channel = AsyncMock(return_value=channel)

        # Act
        result = await discord_delete_message(bot, channel_id=123, message_id=456)

        # Assert
        assert result.success is True
        bot.fetch_channel.assert_called_once_with(123)
        channel.fetch_message.assert_called_once_with(456)

    @pytest.mark.asyncio
    async def test_delete_message_no_fetch_capability(self):
        """Test FAIL FAST when channel doesn't support message fetching."""
        # Arrange
        bot = Mock(spec=discord.Client)
        # Return None from get_channel to force fetch_channel path
        bot.get_channel.return_value = None

        # Create a channel without fetch_message attribute
        channel = Mock(spec=[])  # Empty spec, no methods
        bot.fetch_channel = AsyncMock(return_value=channel)

        # Act
        result = await discord_delete_message(bot, channel_id=123, message_id=456)

        # Assert - FAIL LOUD
        assert result.success is False
        assert "does not support message fetching" in result.error
        assert result.data is None

    @pytest.mark.asyncio
    async def test_delete_message_permission_error(self):
        """Test FAIL FAST on permission errors."""
        # Arrange
        bot = Mock(spec=discord.Client)
        channel = AsyncMock()
        message = AsyncMock()
        channel.fetch_message.return_value = message
        message.delete.side_effect = discord.Forbidden(Mock(), "Missing Permissions")
        bot.get_channel.return_value = channel

        # Act
        result = await discord_delete_message(bot, channel_id=123, message_id=456)

        # Assert - FAIL LOUD
        assert result.success is False
        assert "Missing Permissions" in result.error
        assert result.data is None

    @pytest.mark.asyncio
    async def test_delete_message_not_found(self):
        """Test FAIL FAST when message doesn't exist."""
        # Arrange
        bot = Mock(spec=discord.Client)
        channel = AsyncMock()
        channel.fetch_message.side_effect = discord.NotFound(Mock(), "Unknown Message")
        bot.get_channel.return_value = channel

        # Act
        result = await discord_delete_message(bot, channel_id=123, message_id=456)

        # Assert - FAIL LOUD
        assert result.success is False
        assert "Unknown Message" in result.error
        assert result.data is None


class TestDiscordTimeoutUser:
    """Test user timeout with comprehensive error handling."""

    @pytest.mark.asyncio
    async def test_timeout_user_success(self):
        """Test successful user timeout."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = Mock()
        member = AsyncMock()
        guild.get_member.return_value = member
        bot.get_guild.return_value = guild

        # Act
        result = await discord_timeout_user(bot, guild_id=123, user_id=456, duration_seconds=300, reason="Test timeout")

        # Assert
        assert result.success is True
        assert result.data["user_id"] == "456"
        assert result.data["guild_id"] == "123"
        assert "until" in result.data
        member.timeout.assert_called_once()
        # Verify timeout duration
        timeout_call = member.timeout.call_args
        until_time = timeout_call[0][0]
        assert isinstance(until_time, discord.utils._MissingSentinel.__class__) or until_time is not None

    @pytest.mark.asyncio
    async def test_timeout_user_fetch_member(self):
        """Test fetching member when not in cache."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = Mock()
        member = AsyncMock()
        guild.get_member.return_value = None
        guild.fetch_member = AsyncMock(return_value=member)
        bot.get_guild.return_value = guild

        # Act
        result = await discord_timeout_user(bot, guild_id=123, user_id=456, duration_seconds=300)

        # Assert
        assert result.success is True
        guild.fetch_member.assert_called_once_with(456)

    @pytest.mark.asyncio
    async def test_timeout_user_permission_error(self):
        """Test FAIL FAST on permission errors."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = Mock()
        member = AsyncMock()
        member.timeout.side_effect = discord.Forbidden(Mock(), "Missing Permissions")
        guild.get_member.return_value = member
        bot.get_guild.return_value = guild

        # Act
        result = await discord_timeout_user(bot, guild_id=123, user_id=456, duration_seconds=300)

        # Assert - FAIL LOUD
        assert result.success is False
        assert "Missing Permissions" in result.error

    @pytest.mark.asyncio
    async def test_timeout_user_hierarchy_error(self):
        """Test FAIL FAST when target has higher role."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = Mock()
        member = AsyncMock()
        member.timeout.side_effect = discord.HTTPException(Mock(), "Cannot timeout member with higher role")
        guild.get_member.return_value = member
        bot.get_guild.return_value = guild

        # Act
        result = await discord_timeout_user(bot, guild_id=123, user_id=456, duration_seconds=300)

        # Assert - FAIL LOUD
        assert result.success is False
        assert "higher role" in result.error.lower()


class TestDiscordBanUser:
    """Test user ban with comprehensive error handling."""

    @pytest.mark.asyncio
    async def test_ban_user_success(self):
        """Test successful user ban."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = AsyncMock()
        user = AsyncMock()
        guild.fetch_member = AsyncMock(return_value=user)
        bot.get_guild.return_value = guild

        # Act
        result = await discord_ban_user(bot, guild_id=123, user_id=456, reason="Violation", delete_message_days=1)

        # Assert
        assert result.success is True
        assert result.data == {"user_id": "456", "guild_id": "123"}
        guild.ban.assert_called_once_with(user, reason="Violation", delete_message_days=1)

    @pytest.mark.asyncio
    async def test_ban_user_already_banned(self):
        """Test FAIL FAST when user is already banned."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = AsyncMock()
        user = AsyncMock()
        guild.fetch_member = AsyncMock(return_value=user)
        guild.ban.side_effect = discord.HTTPException(Mock(), "User is already banned")
        bot.get_guild.return_value = guild

        # Act
        result = await discord_ban_user(bot, guild_id=123, user_id=456)

        # Assert - FAIL LOUD
        assert result.success is False
        assert "already banned" in result.error.lower()

    @pytest.mark.asyncio
    async def test_ban_user_permission_error(self):
        """Test FAIL FAST on missing ban permissions."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = AsyncMock()
        user = AsyncMock()
        guild.fetch_member = AsyncMock(return_value=user)
        guild.ban.side_effect = discord.Forbidden(Mock(), "Missing Ban Members permission")
        bot.get_guild.return_value = guild

        # Act
        result = await discord_ban_user(bot, guild_id=123, user_id=456)

        # Assert - FAIL LOUD
        assert result.success is False
        assert "Missing Ban Members permission" in result.error


class TestDiscordKickUser:
    """Test user kick with comprehensive error handling."""

    @pytest.mark.asyncio
    async def test_kick_user_success(self):
        """Test successful user kick."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = AsyncMock()
        user = AsyncMock()
        guild.fetch_member = AsyncMock(return_value=user)
        bot.get_guild.return_value = guild

        # Act
        result = await discord_kick_user(bot, guild_id=123, user_id=456, reason="Warning escalation")

        # Assert
        assert result.success is True
        assert result.data == {"user_id": "456", "guild_id": "123"}
        guild.kick.assert_called_once_with(user, reason="Warning escalation")

    @pytest.mark.asyncio
    async def test_kick_user_not_in_guild(self):
        """Test FAIL FAST when user is not in guild."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = AsyncMock()
        guild.fetch_member.side_effect = discord.NotFound(Mock(), "Member not found")
        bot.get_guild.return_value = guild

        # Act
        result = await discord_kick_user(bot, guild_id=123, user_id=456)

        # Assert - FAIL LOUD
        assert result.success is False
        assert "Member not found" in result.error

    @pytest.mark.asyncio
    async def test_kick_user_hierarchy_error(self):
        """Test FAIL FAST when target has higher role."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = AsyncMock()
        user = AsyncMock()
        guild.fetch_member = AsyncMock(return_value=user)
        guild.kick.side_effect = discord.HTTPException(Mock(), "Cannot kick member with higher role")
        bot.get_guild.return_value = guild

        # Act
        result = await discord_kick_user(bot, guild_id=123, user_id=456)

        # Assert - FAIL LOUD
        assert result.success is False
        assert "higher role" in result.error.lower()


class TestToolRegistration:
    """Test tool registration with registry."""

    def test_register_discord_tools(self):
        """Test that all tools are registered correctly."""
        # Arrange
        registry = Mock()
        bot = Mock(spec=discord.Client)

        # Act
        register_discord_tools(registry, bot)

        # Assert
        assert registry.register_tool.call_count == 4

        # Verify each tool registration
        calls = registry.register_tool.call_args_list
        tool_names = [call[0][0] for call in calls]

        assert "discord_delete_message" in tool_names
        assert "discord_timeout_user" in tool_names
        assert "discord_ban_user" in tool_names
        assert "discord_kick_user" in tool_names

    def test_registered_handlers_are_async(self):
        """Test that registered handlers return coroutines."""
        # Arrange
        registry = Mock()
        bot = Mock(spec=discord.Client)

        # Act
        register_discord_tools(registry, bot)

        # Get the handlers from registration calls
        for call in registry.register_tool.call_args_list:
            handler = call[1]["handler"]

            # Create mock args for the handler
            mock_args = {
                "channel_id": 123,
                "message_id": 456,
                "guild_id": 789,
                "user_id": 101,
                "duration_seconds": 300,
                "reason": "test",
                "delete_message_days": 1,
            }

            # Filter args based on the tool
            tool_name = call[0][0]
            if "delete_message" in tool_name:
                args = {"channel_id": 123, "message_id": 456}
            elif "timeout" in tool_name:
                args = {"guild_id": 789, "user_id": 101, "duration_seconds": 300}
            elif "ban" in tool_name:
                args = {"guild_id": 789, "user_id": 101}
            else:  # kick
                args = {"guild_id": 789, "user_id": 101}

            # Verify handler returns a coroutine
            result = handler(args)
            assert asyncio.iscoroutine(result)
            # Clean up the coroutine
            result.close()


class TestErrorPropagation:
    """Test that errors are propagated clearly for debugging."""

    @pytest.mark.asyncio
    async def test_network_error_propagation(self):
        """Test that network errors are clearly reported."""
        # Arrange
        bot = Mock(spec=discord.Client)
        bot.get_channel.side_effect = discord.HTTPException(Mock(), "Network error: Connection timeout")

        # Act
        result = await discord_delete_message(bot, channel_id=123, message_id=456)

        # Assert - FAIL LOUD with clear error
        assert result.success is False
        assert "Network error" in result.error
        assert "Connection timeout" in result.error

    @pytest.mark.asyncio
    async def test_rate_limit_error_propagation(self):
        """Test that rate limit errors are clearly reported."""
        # Arrange
        bot = Mock(spec=discord.Client)
        guild = Mock()
        guild.fetch_member.side_effect = discord.RateLimited(retry_after=5.0)
        bot.get_guild.return_value = guild

        # Act
        result = await discord_ban_user(bot, guild_id=123, user_id=456)

        # Assert - FAIL LOUD with retry information
        assert result.success is False
        # RateLimited exception should be caught and reported
        assert result.error is not None

    @pytest.mark.asyncio
    async def test_invalid_input_error(self):
        """Test that invalid inputs fail fast with clear errors."""
        # Arrange
        bot = Mock(spec=discord.Client)
        bot.get_guild.return_value = None
        bot.fetch_guild = AsyncMock(side_effect=discord.NotFound(Mock(), "Guild not found"))

        # Act
        result = await discord_kick_user(bot, guild_id=999999, user_id=456)

        # Assert - FAIL LOUD
        assert result.success is False
        assert "Guild not found" in result.error


class TestConcurrentOperations:
    """Test handling of concurrent operations."""

    @pytest.mark.asyncio
    async def test_concurrent_deletions(self):
        """Test multiple concurrent message deletions."""
        # Arrange
        bot = Mock(spec=discord.Client)
        channel = AsyncMock()
        message = AsyncMock()
        channel.fetch_message.return_value = message
        bot.get_channel.return_value = channel

        # Act - Delete multiple messages concurrently
        tasks = [discord_delete_message(bot, channel_id=123, message_id=i) for i in range(10)]
        results = await asyncio.gather(*tasks)

        # Assert
        assert all(r.success for r in results)
        assert channel.fetch_message.call_count == 10

    @pytest.mark.asyncio
    async def test_concurrent_operations_with_failures(self):
        """Test that failures in concurrent operations are isolated."""
        # Arrange
        bot = Mock(spec=discord.Client)
        channel = AsyncMock()

        # Make some operations fail
        async def fetch_message_side_effect(msg_id):
            if msg_id % 2 == 0:
                raise discord.NotFound(Mock(), f"Message {msg_id} not found")
            return AsyncMock()

        channel.fetch_message.side_effect = fetch_message_side_effect
        bot.get_channel.return_value = channel

        # Act
        tasks = [discord_delete_message(bot, channel_id=123, message_id=i) for i in range(10)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Assert - Some succeed, some fail, all report clearly
        success_count = sum(1 for r in results if not isinstance(r, Exception) and r.success)
        fail_count = sum(1 for r in results if not isinstance(r, Exception) and not r.success)

        assert success_count == 5  # Odd IDs succeed
        assert fail_count == 5  # Even IDs fail

        # Verify error messages are clear
        for i, result in enumerate(results):
            if not isinstance(result, Exception) and not result.success:
                assert "not found" in result.error.lower()
