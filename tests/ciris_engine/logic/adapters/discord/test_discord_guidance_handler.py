"""
Comprehensive tests for DiscordGuidanceHandler.

Tests Discord wise authority guidance and deferral operations using proper schemas.
"""

import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import discord
import pytest
from discord import ui

from ciris_engine.logic.adapters.discord.discord_guidance_handler import DeferralHelperView, DiscordGuidanceHandler


class MockMessage:
    """Mock Discord message for testing."""

    def __init__(
        self,
        content: str = "",
        author_id: int = 123456,
        author_name: str = "TestUser",
        is_bot: bool = False,
        message_id: int = 999,
        reference_id: Optional[int] = None,
    ):
        self.content = content
        self.id = message_id
        self.author = Mock()
        self.author.id = author_id
        self.author.bot = is_bot
        self.author.display_name = author_name
        self.author.name = author_name

        if reference_id:
            self.reference = Mock()
            self.reference.message_id = reference_id
        else:
            self.reference = None


class MockChannel:
    """Mock Discord channel for testing."""

    def __init__(self, channel_id: int = 987654321, messages: Optional[List[MockMessage]] = None):
        self.id = channel_id
        self.messages = messages or []
        self.send = AsyncMock(return_value=MockMessage(message_id=1000))

    async def history(self, limit: int = 10):
        """Mock history method that yields messages."""
        for msg in self.messages[:limit]:
            yield msg


class MockGuild:
    """Mock Discord guild for testing."""

    def __init__(self, guild_id: int = 111222333):
        self.id = guild_id
        self.members = {}

    def get_member(self, user_id: int):
        """Get a member by ID."""
        return self.members.get(user_id)


class MockMember:
    """Mock Discord guild member for testing."""

    def __init__(self, user_id: int, roles: Optional[List[str]] = None):
        self.id = user_id
        self.roles = []
        if roles:
            for role_name in roles:
                role = Mock()
                role.name = role_name
                self.roles.append(role)


@pytest.fixture
def mock_discord_client():
    """Create a mock Discord client."""
    client = Mock(spec=discord.Client)
    client.user = Mock(id=888888888, name="CIRISBot")
    client.guilds = []
    client.get_channel = Mock(return_value=None)
    client.fetch_channel = AsyncMock(return_value=None)
    return client


@pytest.fixture
def mock_time_service():
    """Create a mock time service."""
    time_service = Mock()
    time_service.now = Mock(return_value=datetime(2025, 1, 18, 12, 0, 0, tzinfo=timezone.utc))
    time_service.now_iso = Mock(return_value="2025-01-18T12:00:00Z")
    return time_service


@pytest.fixture
def mock_memory_service():
    """Create a mock memory service."""
    memory_service = Mock()
    memory_service.search = AsyncMock(return_value=[])
    return memory_service


@pytest.fixture
def guidance_handler(mock_discord_client, mock_time_service, mock_memory_service):
    """Create DiscordGuidanceHandler instance."""
    return DiscordGuidanceHandler(
        client=mock_discord_client, time_service=mock_time_service, memory_service=mock_memory_service
    )


class TestDiscordGuidanceHandler:
    """Test suite for DiscordGuidanceHandler."""

    def test_initialization(self, mock_discord_client, mock_time_service, mock_memory_service):
        """Test handler initialization."""
        handler = DiscordGuidanceHandler(
            client=mock_discord_client, time_service=mock_time_service, memory_service=mock_memory_service
        )

        assert handler.client == mock_discord_client
        assert handler._memory_service == mock_memory_service
        assert handler._time_service == mock_time_service
        assert handler._wa_cache == {}

    def test_initialization_without_time_service(self, mock_discord_client, mock_memory_service):
        """Test handler creates default time service if not provided."""
        with patch("ciris_engine.logic.services.lifecycle.time.TimeService") as mock_ts_class:
            mock_ts_instance = Mock()
            mock_ts_class.return_value = mock_ts_instance

            handler = DiscordGuidanceHandler(client=mock_discord_client, memory_service=mock_memory_service)

            mock_ts_class.assert_called_once()
            assert handler._time_service == mock_ts_instance

    def test_set_client(self, guidance_handler):
        """Test setting Discord client after initialization."""
        new_client = Mock(spec=discord.Client)
        guidance_handler.set_client(new_client)
        assert guidance_handler.client == new_client

    def test_set_memory_service(self, guidance_handler):
        """Test setting memory service after initialization."""
        new_memory_service = Mock()
        guidance_handler.set_memory_service(new_memory_service)
        assert guidance_handler._memory_service == new_memory_service

    @pytest.mark.asyncio
    async def test_is_registered_wa_cached(self, guidance_handler):
        """Test WA registration check with cached result."""
        discord_id = "123456"
        guidance_handler._wa_cache[discord_id] = True

        result = await guidance_handler._is_registered_wa(discord_id)
        assert result is True
        # Should not call memory service when cached
        guidance_handler._memory_service.search.assert_not_called()

    @pytest.mark.asyncio
    async def test_is_registered_wa_bot_own_id(self, guidance_handler):
        """Test bot's own ID is always registered as WA."""
        discord_id = "888888888"  # Bot's ID
        result = await guidance_handler._is_registered_wa(discord_id)

        assert result is True
        assert guidance_handler._wa_cache[discord_id] is True

    @pytest.mark.asyncio
    async def test_is_registered_wa_memory_service_found(self, guidance_handler):
        """Test WA registration check via memory service."""
        discord_id = "123456"
        # Mock memory service returns a node
        guidance_handler._memory_service.search.return_value = [{"node_id": "wa_node"}]

        result = await guidance_handler._is_registered_wa(discord_id)

        assert result is True
        assert guidance_handler._wa_cache[discord_id] is True
        guidance_handler._memory_service.search.assert_called_once_with(f"node_type:DISCORD_WA discord_id:{discord_id}")

    @pytest.mark.asyncio
    async def test_is_registered_wa_memory_service_not_found(self, guidance_handler):
        """Test WA registration check when not found in memory."""
        discord_id = "123456"
        guidance_handler._memory_service.search.return_value = []

        result = await guidance_handler._is_registered_wa(discord_id)

        assert result is False
        assert guidance_handler._wa_cache[discord_id] is False

    @pytest.mark.asyncio
    async def test_is_registered_wa_memory_service_error(self, guidance_handler):
        """Test WA registration falls back to Discord roles on error."""
        discord_id = "123456"
        guidance_handler._memory_service.search.side_effect = Exception("Memory error")

        # Mock Discord role check to return False
        with patch.object(guidance_handler, "_check_discord_roles", return_value=False) as mock_check:
            result = await guidance_handler._is_registered_wa(discord_id)

            assert result is False
            mock_check.assert_called_once_with(discord_id)

    @pytest.mark.asyncio
    async def test_is_registered_wa_no_memory_service(self, guidance_handler):
        """Test WA registration falls back to Discord roles without memory service."""
        discord_id = "123456"
        guidance_handler._memory_service = None

        with patch.object(guidance_handler, "_check_discord_roles", return_value=True) as mock_check:
            result = await guidance_handler._is_registered_wa(discord_id)

            assert result is True
            mock_check.assert_called_once_with(discord_id)

    def test_check_discord_roles_authority(self, guidance_handler):
        """Test checking Discord roles for AUTHORITY role."""
        discord_id = "123456"
        guild = MockGuild()
        member = MockMember(int(discord_id), roles=["AUTHORITY"])
        guild.members[int(discord_id)] = member
        guidance_handler.client.guilds = [guild]
        guild.get_member = Mock(return_value=member)

        result = guidance_handler._check_discord_roles(discord_id)
        assert result is True

    def test_check_discord_roles_observer(self, guidance_handler):
        """Test checking Discord roles for OBSERVER role."""
        discord_id = "123456"
        guild = MockGuild()
        member = MockMember(int(discord_id), roles=["Observer"])  # Case insensitive
        guild.members[int(discord_id)] = member
        guidance_handler.client.guilds = [guild]
        guild.get_member = Mock(return_value=member)

        result = guidance_handler._check_discord_roles(discord_id)
        assert result is True

    def test_check_discord_roles_no_appropriate_role(self, guidance_handler):
        """Test checking Discord roles without appropriate roles."""
        discord_id = "123456"
        guild = MockGuild()
        member = MockMember(int(discord_id), roles=["Member", "User"])
        guild.members[int(discord_id)] = member
        guidance_handler.client.guilds = [guild]
        guild.get_member = Mock(return_value=member)

        result = guidance_handler._check_discord_roles(discord_id)
        assert result is False

    def test_check_discord_roles_no_client(self, guidance_handler):
        """Test checking Discord roles without client."""
        guidance_handler.client = None
        result = guidance_handler._check_discord_roles("123456")
        assert result is False

    def test_check_discord_roles_member_not_found(self, guidance_handler):
        """Test checking Discord roles when member not found."""
        guild = MockGuild()
        guild.get_member = Mock(return_value=None)
        guidance_handler.client.guilds = [guild]

        result = guidance_handler._check_discord_roles("123456")
        assert result is False

    def test_check_discord_roles_exception(self, guidance_handler):
        """Test checking Discord roles handles exceptions."""
        guild = MockGuild()
        guild.get_member = Mock(side_effect=Exception("Guild error"))
        guidance_handler.client.guilds = [guild]

        result = guidance_handler._check_discord_roles("123456")
        assert result is False

    @pytest.mark.asyncio
    async def test_fetch_guidance_from_channel_no_client(self, guidance_handler):
        """Test fetching guidance without client raises error."""
        guidance_handler.client = None

        with pytest.raises(RuntimeError, match="Discord client is not initialized"):
            await guidance_handler.fetch_guidance_from_channel("123", {})

    @pytest.mark.asyncio
    async def test_fetch_guidance_from_channel_not_found(self, guidance_handler):
        """Test fetching guidance when channel not found."""
        with patch.object(guidance_handler, "_resolve_channel", return_value=None):
            with pytest.raises(RuntimeError, match="Deferral channel .* not found"):
                await guidance_handler.fetch_guidance_from_channel("123", {})

    @pytest.mark.asyncio
    async def test_fetch_guidance_from_channel_success(self, guidance_handler):
        """Test successfully fetching guidance from channel."""
        # Create mock channel with guidance message
        request_msg = MockMessage(message_id=1000)
        guidance_msg = MockMessage(
            content="This is guidance", author_id=777, author_name="WiseAuthority", message_id=1001, reference_id=1000
        )

        channel = MockChannel(messages=[guidance_msg])
        channel.send = AsyncMock(return_value=request_msg)

        with patch.object(guidance_handler, "_resolve_channel", return_value=channel):
            with patch.object(guidance_handler, "_is_registered_wa", return_value=True):
                result = await guidance_handler.fetch_guidance_from_channel("123", {"test": "context"})

                assert result["guidance"] == "This is guidance"
                assert result["is_reply"] is True
                assert result["is_unsolicited"] is False
                assert result["author_id"] == "777"
                assert result["author_name"] == "WiseAuthority"

    @pytest.mark.asyncio
    async def test_fetch_guidance_from_channel_no_guidance(self, guidance_handler):
        """Test fetching guidance when no guidance found."""
        channel = MockChannel(messages=[])

        with patch.object(guidance_handler, "_resolve_channel", return_value=channel):
            result = await guidance_handler.fetch_guidance_from_channel("123", {})

            assert result == {"guidance": None}

    @pytest.mark.asyncio
    async def test_fetch_guidance_from_channel_non_wa_user(self, guidance_handler):
        """Test fetching guidance ignores non-WA users."""
        guidance_msg = MockMessage(content="Not WA guidance", author_id=777)
        channel = MockChannel(messages=[guidance_msg])

        with patch.object(guidance_handler, "_resolve_channel", return_value=channel):
            with patch.object(guidance_handler, "_is_registered_wa", return_value=False):
                result = await guidance_handler.fetch_guidance_from_channel("123", {})

                assert result == {"guidance": None}

    @pytest.mark.asyncio
    async def test_fetch_guidance_from_channel_bot_message(self, guidance_handler):
        """Test fetching guidance ignores bot messages."""
        bot_msg = MockMessage(content="Bot message", is_bot=True)
        channel = MockChannel(messages=[bot_msg])

        with patch.object(guidance_handler, "_resolve_channel", return_value=channel):
            result = await guidance_handler.fetch_guidance_from_channel("123", {})

            assert result == {"guidance": None}

    @pytest.mark.asyncio
    async def test_send_deferral_to_channel_no_client(self, guidance_handler):
        """Test sending deferral without client raises error."""
        guidance_handler.client = None

        with pytest.raises(RuntimeError, match="Discord client is not initialized"):
            await guidance_handler.send_deferral_to_channel("123", "thought_id", "reason")

    @pytest.mark.asyncio
    async def test_send_deferral_to_channel_not_found(self, guidance_handler):
        """Test sending deferral when channel not found."""
        with patch.object(guidance_handler, "_resolve_channel", return_value=None):
            with pytest.raises(RuntimeError, match="Deferral channel .* not found"):
                await guidance_handler.send_deferral_to_channel("123", "thought_id", "reason")

    @pytest.mark.asyncio
    async def test_send_deferral_to_channel_success(self, guidance_handler):
        """Test successfully sending deferral to channel."""
        channel = MockChannel()

        context = {
            "task_id": "task_123",
            "priority": "HIGH",
            "task_description": "Test task",
            "thought_content": "Test thought",
            "attempted_action": "test_action",
            "max_rounds_reached": True,
        }

        with patch.object(guidance_handler, "_resolve_channel", return_value=channel):
            await guidance_handler.send_deferral_to_channel("123", "thought_id", "Test reason", context)

            channel.send.assert_called_once()
            call_args = channel.send.call_args
            assert "embed" in call_args.kwargs
            assert "view" in call_args.kwargs

            embed = call_args.kwargs["embed"]
            assert embed.title == "CIRIS Deferral Report"
            assert "Test reason" in embed.description

    def test_build_deferral_report_basic(self, guidance_handler):
        """Test building basic deferral report."""
        report = guidance_handler._build_deferral_report("thought_123", "Test reason")

        assert "**[CIRIS Deferral Report]**" in report
        assert "**Thought ID:** `thought_123`" in report
        assert "**Reason:** Test reason" in report
        assert "**Timestamp:**" in report

    def test_build_deferral_report_with_context(self, guidance_handler):
        """Test building deferral report with full context."""
        context = {
            "task_id": "task_456",
            "task_description": "Complex task description",
            "thought_content": "Deep thought content",
            "conversation_context": "Previous conversation",
            "priority": "URGENT",
            "attempted_action": "analyze",
            "max_rounds_reached": True,
        }

        report = guidance_handler._build_deferral_report("thought_123", "Test reason", context)

        assert "**Task ID:** `task_456`" in report
        assert "Complex task description" in report
        assert "Deep thought content" in report
        assert "Previous conversation" in report
        assert "**Priority:** URGENT" in report
        assert "**Attempted Action:** analyze" in report
        assert "Maximum processing rounds reached" in report

    def test_truncate_text_short(self, guidance_handler):
        """Test text truncation with short text."""
        text = "Short text"
        result = guidance_handler._truncate_text(text, 100)
        assert result == text

    def test_truncate_text_long(self, guidance_handler):
        """Test text truncation with long text."""
        text = "A" * 100
        result = guidance_handler._truncate_text(text, 50)
        assert result == "A" * 47 + "..."
        assert len(result) == 50

    def test_split_message_short(self, guidance_handler):
        """Test message splitting with short message."""
        content = "Short message"
        chunks = guidance_handler._split_message(content)
        assert len(chunks) == 1
        assert chunks[0] == content

    def test_split_message_long(self, guidance_handler):
        """Test message splitting with long message."""
        content = "A" * 3000  # Exceeds Discord limit
        chunks = guidance_handler._split_message(content, max_length=1950)

        assert len(chunks) == 2
        assert len(chunks[0]) <= 1950
        assert len(chunks[1]) <= 1950
        assert chunks[0] + chunks[1] == content

    def test_split_message_with_newlines(self, guidance_handler):
        """Test message splitting preserves newlines."""
        lines = ["Line " + str(i) * 100 for i in range(20)]
        content = "\n".join(lines)
        chunks = guidance_handler._split_message(content, max_length=500)

        assert len(chunks) > 1
        for chunk in chunks:
            assert len(chunk) <= 500

    @pytest.mark.asyncio
    async def test_resolve_channel_found(self, guidance_handler):
        """Test resolving channel successfully."""
        channel = MockChannel()
        guidance_handler.client.get_channel.return_value = channel

        result = await guidance_handler._resolve_channel("987654321")
        assert result == channel

    @pytest.mark.asyncio
    async def test_resolve_channel_fetch(self, guidance_handler):
        """Test resolving channel via fetch when get returns None."""
        channel = MockChannel()
        guidance_handler.client.get_channel.return_value = None
        guidance_handler.client.fetch_channel.return_value = channel

        result = await guidance_handler._resolve_channel("987654321")
        assert result == channel

    @pytest.mark.asyncio
    async def test_resolve_channel_invalid_id(self, guidance_handler):
        """Test resolving channel with invalid ID."""
        result = await guidance_handler._resolve_channel("invalid")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_channel_not_found(self, guidance_handler):
        """Test resolving channel when not found."""
        guidance_handler.client.get_channel.return_value = None
        guidance_handler.client.fetch_channel.side_effect = discord.NotFound(Mock(), "Not found")

        result = await guidance_handler._resolve_channel("987654321")
        assert result is None

    @pytest.mark.asyncio
    async def test_resolve_channel_no_client(self, guidance_handler):
        """Test resolving channel without client."""
        guidance_handler.client = None
        result = await guidance_handler._resolve_channel("987654321")
        assert result is None


class TestDeferralHelperView:
    """Test suite for DeferralHelperView Discord UI."""

    def test_initialization(self):
        """Test view initialization."""
        context = {"task_id": "task_123"}

        # Mock the parent class __init__ to avoid event loop requirement
        with patch.object(ui.View, "__init__", return_value=None):
            view = DeferralHelperView("thought_456", context)

            assert view.thought_id == "thought_456"
            assert view.context == context

    @pytest.mark.asyncio
    async def test_approve_button(self):
        """Test approve button interaction."""
        with patch.object(ui.View, "__init__", return_value=None):
            view = DeferralHelperView("thought_123")
            interaction = Mock(spec=discord.Interaction)
            interaction.response = AsyncMock()

            button = Mock(spec=ui.Button)
            await view.approve_button(interaction, button)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "APPROVE thought_123" in call_args.args[0]
            assert call_args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_reject_button(self):
        """Test reject button interaction."""
        with patch.object(ui.View, "__init__", return_value=None):
            view = DeferralHelperView("thought_123")
            interaction = Mock(spec=discord.Interaction)
            interaction.response = AsyncMock()

            button = Mock(spec=ui.Button)
            await view.reject_button(interaction, button)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            assert "REJECT thought_123" in call_args.args[0]
            assert call_args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_info_button_basic(self):
        """Test info button with basic context."""
        with patch.object(ui.View, "__init__", return_value=None):
            view = DeferralHelperView("thought_123", {})
            interaction = Mock(spec=discord.Interaction)
            interaction.response = AsyncMock()

            button = Mock(spec=ui.Button)
            await view.info_button(interaction, button)

            interaction.response.send_message.assert_called_once()
            call_args = interaction.response.send_message.call_args
            message = call_args.args[0]
            assert "Detailed Task/Thought Information" in message
            assert "thought_123" in message
            assert call_args.kwargs["ephemeral"] is True

    @pytest.mark.asyncio
    async def test_info_button_full_context(self):
        """Test info button with full context."""
        context = {
            "task_id": "task_456",
            "task_description": "Complex task",
            "thought_history": [{"content": "Thought 1"}, {"content": "Thought 2"}],
            "ponder_notes": ["Question 1", "Question 2"],
            "current_round": 3,
            "max_rounds": 5,
            "attempted_actions": ["action1", "action2"],
        }

        with patch.object(ui.View, "__init__", return_value=None):
            view = DeferralHelperView("thought_123", context)
            interaction = Mock(spec=discord.Interaction)
            interaction.response = AsyncMock()

            button = Mock(spec=ui.Button)
            await view.info_button(interaction, button)

            interaction.response.send_message.assert_called_once()
            message = interaction.response.send_message.call_args.args[0]

            assert "task_456" in message
            assert "Complex task" in message
            assert "Thought 1" in message
            assert "Question 1" in message
            assert "3/5" in message
            assert "action1" in message

    @pytest.mark.asyncio
    async def test_info_button_message_truncation(self):
        """Test info button truncates long messages."""
        # Create context with very long content
        context = {
            "task_description": "A" * 2000,
            "thought_history": [{"content": f"Thought {i}" * 100} for i in range(10)],
        }

        with patch.object(ui.View, "__init__", return_value=None):
            view = DeferralHelperView("thought_123", context)
            interaction = Mock(spec=discord.Interaction)
            interaction.response = AsyncMock()

            button = Mock(spec=ui.Button)
            await view.info_button(interaction, button)

            interaction.response.send_message.assert_called_once()
            message = interaction.response.send_message.call_args.args[0]
            assert len(message) <= 2000  # Discord's message limit

    def test_truncate_text_in_view(self):
        """Test text truncation in view."""
        with patch.object(ui.View, "__init__", return_value=None):
            view = DeferralHelperView("thought_123")
            text = "A" * 100
            result = view._truncate_text(text, 50)
            assert result == "A" * 47 + "..."
            assert len(result) == 50
