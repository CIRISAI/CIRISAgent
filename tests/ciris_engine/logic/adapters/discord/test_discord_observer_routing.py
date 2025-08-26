"""
Comprehensive tests for Discord observer routing logic.
Tests that messages are properly routed to task creation or WA feedback based on channel and author.
"""

import uuid
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.discord.discord_observer import DiscordObserver
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.runtime.messages import DiscordMessage
from ciris_engine.schemas.runtime.models import Task, Thought
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.services.filters_core import FilterResult, FilterPriority


class TestDiscordObserverRouting:
    """Test Discord observer message routing logic."""

    @pytest.fixture
    def time_service(self):
        """Create a time service."""
        return TimeService()

    @pytest.fixture
    def mock_memory_service(self):
        """Create mock memory service."""
        memory = AsyncMock()
        memory.recall = AsyncMock(return_value=[])
        memory.get_correlation_history = AsyncMock(return_value=[])
        return memory

    @pytest.fixture
    def mock_bus_manager(self):
        """Create mock bus manager."""
        bus_manager = Mock()
        bus_manager.communication = AsyncMock()
        return bus_manager

    @pytest.fixture
    def observer(self, time_service, mock_memory_service, mock_bus_manager):
        """Create observer instance with test configuration."""
        observer = DiscordObserver(
            agent_id="test_agent",
            monitored_channel_ids=["1396158748606726354", "1382010877171073108"],  # ai-social, etc
            deferral_channel_id="1382008300576702565",  # deferral channel
            wa_user_ids=["537080239679864862"],  # Eric's ID
            time_service=time_service,
            memory_service=mock_memory_service,
            bus_manager=mock_bus_manager,
        )
        return observer

    @pytest.mark.asyncio
    async def test_priority_message_in_monitored_channel_from_wa_creates_task(self, observer):
        """Test that priority messages in monitored channels create tasks even from WA users."""
        msg = DiscordMessage(
            message_id="test_msg_1",
            content="@Echo help me",
            author_id="537080239679864862",  # WA user
            author_name="Eric",
            channel_id="1396158748606726354",  # Monitored channel (ai-social)
            is_bot=False,
            is_dm=False,
        )

        filter_result = FilterResult(
            message_id=msg.message_id,
            priority=FilterPriority.CRITICAL,
            triggered_filters=["at_mention"],
            should_process=True,
            reasoning="Message triggered filters: at_mention -> critical priority"
        )

        with patch.object(observer, '_create_priority_observation_result', new_callable=AsyncMock) as mock_create:
            await observer._handle_priority_observation(msg, filter_result)
            
            # Should create task despite author being in WA list
            mock_create.assert_called_once_with(msg, filter_result)

    @pytest.mark.asyncio
    async def test_priority_message_in_monitored_channel_from_non_wa_creates_task(self, observer):
        """Test that priority messages in monitored channels create tasks from non-WA users."""
        msg = DiscordMessage(
            message_id="test_msg_2",
            content="@Echo help me",
            author_id="123456789",  # Non-WA user
            author_name="SomeUser",
            channel_id="1396158748606726354",  # Monitored channel (ai-social)
            is_bot=False,
            is_dm=False,
        )

        filter_result = FilterResult(
            message_id=msg.message_id,
            priority=FilterPriority.CRITICAL,
            triggered_filters=["at_mention"],
            should_process=True,
            reasoning="Message triggered filters: at_mention -> critical priority"
        )

        with patch.object(observer, '_create_priority_observation_result', new_callable=AsyncMock) as mock_create:
            await observer._handle_priority_observation(msg, filter_result)
            
            # Should create task
            mock_create.assert_called_once_with(msg, filter_result)

    @pytest.mark.asyncio
    async def test_priority_message_in_deferral_channel_from_wa_routes_to_feedback(self, observer):
        """Test that priority messages in deferral channel from WA users route to feedback."""
        msg = DiscordMessage(
            message_id="test_msg_3",
            content="Guidance for deferred task",
            author_id="537080239679864862",  # WA user
            author_name="Eric",
            channel_id="1382008300576702565",  # Deferral channel
            is_bot=False,
            is_dm=False,
        )

        filter_result = FilterResult(
            message_id=msg.message_id,
            priority=FilterPriority.CRITICAL,
            triggered_filters=["name_mention"],
            should_process=True,
            reasoning="Message triggered filters: name_mention -> critical priority"
        )

        with patch.object(observer, '_add_to_feedback_queue', new_callable=AsyncMock) as mock_feedback:
            await observer._handle_priority_observation(msg, filter_result)
            
            # Should route to WA feedback queue
            mock_feedback.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_priority_message_in_deferral_channel_from_non_wa_ignored(self, observer):
        """Test that priority messages in deferral channel from non-WA users are ignored."""
        msg = DiscordMessage(
            message_id="test_msg_4",
            content="Random message",
            author_id="123456789",  # Non-WA user
            author_name="SomeUser",
            channel_id="1382008300576702565",  # Deferral channel
            is_bot=False,
            is_dm=False,
        )

        filter_result = FilterResult(
            message_id=msg.message_id,
            priority=FilterPriority.CRITICAL,
            triggered_filters=["caps_abuse"],
            should_process=True,
            reasoning="Message triggered filters: caps_abuse -> critical priority"
        )

        with patch.object(observer, '_create_priority_observation_result', new_callable=AsyncMock) as mock_create:
            with patch.object(observer, '_add_to_feedback_queue', new_callable=AsyncMock) as mock_feedback:
                await observer._handle_priority_observation(msg, filter_result)
                
                # Should NOT create task or route to feedback
                mock_create.assert_not_called()
                mock_feedback.assert_not_called()

    @pytest.mark.asyncio
    async def test_passive_message_in_monitored_channel_from_wa_creates_task(self, observer):
        """Test that passive messages in monitored channels create tasks even from WA users."""
        msg = DiscordMessage(
            message_id="test_msg_5",
            content="Hello everyone",
            author_id="537080239679864862",  # WA user
            author_name="Eric",
            channel_id="1382010877171073108",  # Another monitored channel
            is_bot=False,
            is_dm=False,
        )

        with patch.object(observer, '_create_passive_observation_result', new_callable=AsyncMock) as mock_create:
            await observer._handle_passive_observation(msg)
            
            # Should create task despite author being in WA list
            mock_create.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_passive_message_in_deferral_channel_from_wa_routes_to_feedback(self, observer):
        """Test that passive messages in deferral channel from WA users route to feedback."""
        msg = DiscordMessage(
            message_id="test_msg_6",
            content="Thought ID: abc123 - Approved",
            author_id="537080239679864862",  # WA user
            author_name="Eric",
            channel_id="1382008300576702565",  # Deferral channel
            is_bot=False,
            is_dm=False,
        )

        # Mock the feedback queue to avoid actual task creation
        with patch.object(observer, '_add_to_feedback_queue', new_callable=AsyncMock) as mock_feedback:
            await observer._handle_passive_observation(msg)
            
            # Should route to WA feedback queue
            mock_feedback.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_message_in_unmonitored_channel_ignored(self, observer):
        """Test that messages in unmonitored channels are ignored."""
        msg = DiscordMessage(
            message_id="test_msg_7",
            content="Random message",
            author_id="537080239679864862",  # WA user
            author_name="Eric",
            channel_id="9999999999",  # Unmonitored channel
            is_bot=False,
            is_dm=False,
        )

        with patch.object(observer, '_create_passive_observation_result', new_callable=AsyncMock) as mock_create:
            with patch.object(observer, '_add_to_feedback_queue', new_callable=AsyncMock) as mock_feedback:
                await observer._handle_passive_observation(msg)
                
                # Should NOT create task or route to feedback
                mock_create.assert_not_called()
                mock_feedback.assert_not_called()

    @pytest.mark.asyncio
    async def test_channel_id_extraction_with_discord_channelid_format(self, observer):
        """Test that channel IDs with discord_channelid format are properly extracted."""
        msg = DiscordMessage(
            message_id="test_msg_8a",
            content="Test message",
            author_id="123456789",  # Non-WA user
            author_name="TestUser",
            channel_id="discord_1396158748606726354",  # Format: discord_channelid
            is_bot=False,
            is_dm=False,
        )

        with patch.object(observer, '_create_passive_observation_result', new_callable=AsyncMock) as mock_create:
            await observer._handle_passive_observation(msg)
            
            # Should create task - the extraction should handle the prefix
            mock_create.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_channel_id_extraction_with_discord_guild_channel_format(self, observer):
        """Test that channel IDs with discord_guildid_channelid format are properly extracted."""
        msg = DiscordMessage(
            message_id="test_msg_8b",
            content="Test message",
            author_id="123456789",  # Non-WA user
            author_name="TestUser",
            channel_id="discord_12345_1396158748606726354",  # Format: discord_guildid_channelid
            is_bot=False,
            is_dm=False,
        )

        with patch.object(observer, '_create_passive_observation_result', new_callable=AsyncMock) as mock_create:
            await observer._handle_passive_observation(msg)
            
            # Should create task - the extraction should handle the prefix
            mock_create.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_default_wa_user_name_check(self, observer):
        """Test that DEFAULT_WA username 'somecomputerguy' is recognized."""
        msg = DiscordMessage(
            message_id="test_msg_9",
            content="Guidance message",
            author_id="999999999",  # Not in WA list by ID
            author_name="somecomputerguy",  # But matches DEFAULT_WA
            channel_id="1382008300576702565",  # Deferral channel
            is_bot=False,
            is_dm=False,
        )

        with patch('ciris_engine.logic.utils.constants.DEFAULT_WA', 'somecomputerguy'):
            with patch.object(observer, '_add_to_feedback_queue', new_callable=AsyncMock) as mock_feedback:
                await observer._handle_passive_observation(msg)
                
                # Should route to feedback because username matches DEFAULT_WA
                mock_feedback.assert_called_once_with(msg)

    @pytest.mark.asyncio
    async def test_wa_feedback_validation_rejects_non_wa_user(self, observer):
        """Test that _add_to_feedback_queue validates WA authority."""
        msg = DiscordMessage(
            message_id="test_msg_10",
            content="Fake guidance",
            author_id="999999999",  # Not WA
            author_name="FakeUser",
            channel_id="1382008300576702565",  # Deferral channel
            is_bot=False,
            is_dm=False,
        )

        with patch.object(observer, '_send_deferral_message', new_callable=AsyncMock) as mock_send:
            await observer._add_to_feedback_queue(msg)
            
            # Should send error message about unauthorized user
            mock_send.assert_called_once()
            call_args = mock_send.call_args[0][0]
            assert "Not Authorized" in call_args
            assert "FakeUser" in call_args

    @pytest.mark.asyncio
    async def test_multiple_monitored_channels(self, observer):
        """Test that observer handles multiple monitored channels correctly."""
        # Test first monitored channel
        msg1 = DiscordMessage(
            message_id="test_msg_11",
            content="Message in channel 1",
            author_id="537080239679864862",  # WA user
            author_name="Eric",
            channel_id="1396158748606726354",  # First monitored channel
            is_bot=False,
            is_dm=False,
        )

        # Test second monitored channel
        msg2 = DiscordMessage(
            message_id="test_msg_12",
            content="Message in channel 2",
            author_id="537080239679864862",  # WA user
            author_name="Eric",
            channel_id="1382010877171073108",  # Second monitored channel
            is_bot=False,
            is_dm=False,
        )

        with patch.object(observer, '_create_passive_observation_result', new_callable=AsyncMock) as mock_create:
            await observer._handle_passive_observation(msg1)
            await observer._handle_passive_observation(msg2)
            
            # Both should create tasks
            assert mock_create.call_count == 2
            assert mock_create.call_args_list[0][0][0] == msg1
            assert mock_create.call_args_list[1][0][0] == msg2


class TestDiscordObserverTaskCreation:
    """Test actual task creation logic in Discord observer."""

    @pytest.fixture
    def mock_persistence(self):
        """Mock persistence module."""
        with patch('ciris_engine.logic.adapters.discord.discord_observer.persistence') as mock:
            mock.add_task = Mock()
            mock.add_thought = Mock()
            mock.get_thought_by_id = Mock(return_value=None)
            yield mock

    @pytest.fixture
    def observer_with_persistence(self, mock_persistence):
        """Create observer with mocked persistence."""
        observer = DiscordObserver(
            agent_id="test_agent",
            monitored_channel_ids=["1396158748606726354"],
            deferral_channel_id="1382008300576702565",
            wa_user_ids=["537080239679864862"],
        )
        return observer

    @pytest.mark.asyncio
    async def test_create_priority_observation_creates_task_and_thought(self, observer_with_persistence, mock_persistence):
        """Test that _create_priority_observation_result creates both task and thought."""
        msg = DiscordMessage(
            message_id="test_msg_13",
            content="@Echo urgent help",
            author_id="123456789",
            author_name="TestUser",
            channel_id="1396158748606726354",
            is_bot=False,
            is_dm=False,
        )

        filter_result = FilterResult(
            message_id=msg.message_id,
            priority=FilterPriority.CRITICAL,
            triggered_filters=["at_mention"],
            should_process=True,
            reasoning="Message triggered filters: at_mention -> critical priority"
        )

        # Need to patch the base class method since it's inherited
        with patch('ciris_engine.logic.adapters.base_observer.persistence', mock_persistence):
            with patch('ciris_engine.logic.adapters.base_observer.uuid.uuid4', return_value=uuid.UUID('12345678-1234-5678-1234-567812345678')):
                await observer_with_persistence._create_priority_observation_result(msg, filter_result)

                # Should have added a task
                assert mock_persistence.add_task.called
                task = mock_persistence.add_task.call_args[0][0]
                assert isinstance(task, Task)
                assert task.priority == 10  # Critical priority
                assert "TestUser" in task.description
                assert "123456789" in task.description
                
                # Should have added a thought
                assert mock_persistence.add_thought.called
                thought = mock_persistence.add_thought.call_args[0][0]
                assert isinstance(thought, Thought)
                assert thought.status == ThoughtStatus.PENDING

    @pytest.mark.asyncio
    async def test_create_passive_observation_creates_task_and_thought(self, observer_with_persistence, mock_persistence):
        """Test that _create_passive_observation_result creates both task and thought."""
        msg = DiscordMessage(
            message_id="test_msg_14",
            content="Hello everyone",
            author_id="123456789",
            author_name="TestUser",
            channel_id="1396158748606726354",
            is_bot=False,
            is_dm=False,
        )

        # Need to patch the base class method since it's inherited
        with patch('ciris_engine.logic.adapters.base_observer.persistence', mock_persistence):
            with patch('ciris_engine.logic.adapters.base_observer.uuid.uuid4', return_value=uuid.UUID('12345678-1234-5678-1234-567812345678')):
                await observer_with_persistence._create_passive_observation_result(msg)

                # Should have added a task
                assert mock_persistence.add_task.called
                task = mock_persistence.add_task.call_args[0][0]
                assert isinstance(task, Task)
                assert task.priority == 0  # Passive priority
                assert "TestUser" in task.description
                
                # Should have added a thought
                assert mock_persistence.add_thought.called
                thought = mock_persistence.add_thought.call_args[0][0]
                assert isinstance(thought, Thought)
                assert thought.status == ThoughtStatus.PENDING