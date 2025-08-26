"""
Unit tests for base observer numeric ID handling.
Tests that the observer properly includes numeric IDs in task descriptions and thought content.
"""

from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.base_observer import BaseObserver
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.runtime.messages import DiscordMessage
from ciris_engine.schemas.services.filters_core import FilterResult, FilterPriority


class ConcreteObserver(BaseObserver[DiscordMessage]):
    """Concrete implementation for testing."""

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass


class TestBaseObserverNumericIds:
    """Test base observer properly handles numeric IDs."""

    @pytest.fixture
    def time_service(self):
        """Create a time service."""
        return TimeService()

    @pytest.fixture
    def mock_memory_service(self):
        """Create mock memory service."""
        memory = AsyncMock()
        memory.recall = AsyncMock(return_value=[])
        return memory

    @pytest.fixture
    def mock_bus_manager(self):
        """Create mock bus manager."""
        bus_manager = Mock()
        bus_manager.communication = AsyncMock()
        return bus_manager

    @pytest.fixture
    def observer(self, time_service, mock_memory_service, mock_bus_manager):
        """Create observer instance."""
        return ConcreteObserver(
            on_observe=AsyncMock(),
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            time_service=time_service,
            origin_service="test",
        )

    @pytest.mark.asyncio
    async def test_passive_observation_includes_numeric_id(self, observer, time_service):
        """Test that passive observations include numeric user IDs in descriptions."""
        # Create a test message with numeric ID
        test_msg = DiscordMessage(
            message_id="msg123",
            author_id="537080239679864862",  # Numeric Discord ID
            author_name="SomeComputerGuy",
            content="Hello, do you remember me?",
            channel_id="1234567890",
            is_bot=False,
        )

        # Mock persistence to capture the task
        captured_task = None
        captured_thought = None

        def capture_task(task):
            nonlocal captured_task
            captured_task = task

        def capture_thought(thought):
            nonlocal captured_thought
            captured_thought = thought

        # Patch persistence and database calls
        with patch("ciris_engine.logic.persistence.add_task", side_effect=capture_task):
            with patch("ciris_engine.logic.persistence.add_thought", side_effect=capture_thought):
                with patch("ciris_engine.logic.persistence.get_correlations_by_channel", return_value=[]):
                    await observer._create_passive_observation_result(test_msg)

        # Verify task was created with numeric ID in description
        assert captured_task is not None
        assert "SomeComputerGuy (ID: 537080239679864862)" in captured_task.description
        assert captured_task.context.user_id == "537080239679864862"

        # Verify thought content includes numeric ID
        assert captured_thought is not None
        assert "SomeComputerGuy (ID: 537080239679864862)" in captured_thought.content

    @pytest.mark.asyncio
    async def test_conversation_history_includes_numeric_ids(self, observer, time_service):
        """Test that conversation history includes numeric IDs for all messages."""
        # Mock conversation history from correlations
        mock_history = [
            {
                "author": "User1",
                "author_id": "111111111111111111",
                "content": "First message",
                "timestamp": "2024-01-01T00:00:00Z",
            },
            {
                "author": "User2",
                "author_id": "222222222222222222",
                "content": "Second message",
                "timestamp": "2024-01-01T00:01:00Z",
            },
        ]

        # Current message
        current_msg = DiscordMessage(
            message_id="msg3",
            author_id="333333333333333333",
            author_name="User3",
            content="Current message",
            channel_id="1234567890",
            is_bot=False,
        )

        captured_thought = None

        def capture_thought(thought):
            nonlocal captured_thought
            captured_thought = thought

        # Patch persistence and correlation history
        with patch("ciris_engine.logic.persistence.add_task"):
            with patch("ciris_engine.logic.persistence.add_thought", side_effect=capture_thought):
                with patch.object(observer, "_get_correlation_history", return_value=mock_history):
                    await observer._create_passive_observation_result(current_msg)

        # Verify all messages in history have numeric IDs
        assert captured_thought is not None
        thought_content = captured_thought.content

        # Check each user appears with their numeric ID
        assert "User1 (ID: 111111111111111111)" in thought_content
        assert "User2 (ID: 222222222222222222)" in thought_content
        assert "User3 (ID: 333333333333333333)" in thought_content

    @pytest.mark.asyncio
    async def test_priority_observation_includes_numeric_id(self, observer, time_service):
        """Test that priority observations include numeric user IDs."""
        test_msg = DiscordMessage(
            message_id="urgent123",
            author_id="999888777666555444",
            author_name="UrgentUser",
            content="URGENT: Please help immediately!",
            channel_id="1234567890",
            is_bot=False,
        )

        # Mock filter result
        filter_result = Mock()
        filter_result.priority = Mock(value="high")
        filter_result.reasoning = "Urgent keyword detected"
        filter_result.triggered_filters = ["urgent_keyword"]  # Add the missing attribute

        captured_task = None
        captured_thought = None

        def capture_task(task):
            nonlocal captured_task
            captured_task = task

        def capture_thought(thought):
            nonlocal captured_thought
            captured_thought = thought

        # Patch persistence
        with patch("ciris_engine.logic.persistence.add_task", side_effect=capture_task):
            with patch("ciris_engine.logic.persistence.add_thought", side_effect=capture_thought):
                await observer._create_priority_observation_result(test_msg, filter_result)

        # Verify priority task includes numeric ID
        assert captured_task is not None
        assert "UrgentUser (ID: 999888777666555444)" in captured_task.description
        assert captured_task.context.user_id == "999888777666555444"

        # Verify priority thought includes numeric ID
        assert captured_thought is not None
        assert "UrgentUser (ID: 999888777666555444)" in captured_thought.content


class TestFilterErrorHandling:
    """Test filter error handling in base observer."""

    @pytest.fixture
    def time_service(self):
        """Create a time service."""
        return TimeService()

    @pytest.fixture
    def mock_memory_service(self):
        """Create mock memory service."""
        memory = AsyncMock()
        memory.recall = AsyncMock(return_value=[])
        return memory

    @pytest.fixture
    def mock_bus_manager(self):
        """Create mock bus manager."""
        bus_manager = Mock()
        bus_manager.communication = AsyncMock()
        return bus_manager

    @pytest.fixture
    def mock_filter_service(self):
        """Create mock filter service."""
        filter_service = AsyncMock()
        return filter_service

    @pytest.fixture
    def observer_with_filter(self, time_service, mock_memory_service, mock_bus_manager, mock_filter_service):
        """Create observer with filter service."""
        observer = ConcreteObserver(
            on_observe=AsyncMock(),
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            time_service=time_service,
            origin_service="test",
        )
        observer.filter_service = mock_filter_service
        return observer

    @pytest.mark.asyncio
    async def test_filter_triggered_filters_logged(self, observer_with_filter, mock_filter_service):
        """Test that triggered filters are logged in debug mode."""
        test_msg = DiscordMessage(
            message_id="filter_test_123",
            author_id="123456789",
            author_name="TestUser",
            content="Test message",
            channel_id="1234567890",
            is_bot=False,
        )

        # Mock filter result with triggered filters
        mock_filter_result = FilterResult(
            message_id="filter_test_123",
            priority=FilterPriority.HIGH,
            triggered_filters=["spam_filter", "content_filter"],
            should_process=False,
            reasoning="Message contains spam"
        )
        mock_filter_service.filter_message.return_value = mock_filter_result

        # Call the filter method
        result = await observer_with_filter._apply_message_filtering(test_msg, "test")

        # Verify filter was called
        mock_filter_service.filter_message.assert_called_once()
        
        # Verify result matches
        assert result == mock_filter_result
        assert result.triggered_filters == ["spam_filter", "content_filter"]

    @pytest.mark.asyncio
    async def test_filter_exception_returns_default(self, observer_with_filter, mock_filter_service):
        """Test that filter exceptions return a default FilterResult."""
        test_msg = DiscordMessage(
            message_id="error_test_456",
            author_id="987654321",
            author_name="ErrorUser",
            content="Error test message",
            channel_id="1234567890",
            is_bot=False,
        )

        # Mock filter service to raise exception
        mock_filter_service.filter_message.side_effect = RuntimeError("Filter service crashed")

        # Call the filter method
        result = await observer_with_filter._apply_message_filtering(test_msg, "test")

        # Verify default filter result is returned
        assert isinstance(result, FilterResult)
        assert result.message_id == "error_test_456"
        assert result.priority == FilterPriority.MEDIUM
        assert result.triggered_filters == []
        assert result.should_process is True
        assert "Filter error, processing normally" in result.reasoning
        assert "Filter service crashed" in result.reasoning


class TestTaskSigning:
    """Test task signing functionality in base observer."""

    @pytest.fixture
    def time_service(self):
        """Create a time service."""
        return TimeService()

    @pytest.fixture
    def mock_memory_service(self):
        """Create mock memory service."""
        memory = AsyncMock()
        memory.recall = AsyncMock(return_value=[])
        return memory

    @pytest.fixture
    def mock_bus_manager(self):
        """Create mock bus manager."""
        bus_manager = Mock()
        bus_manager.communication = AsyncMock()
        return bus_manager

    @pytest.fixture
    def mock_auth_service(self):
        """Create mock auth service."""
        auth_service = AsyncMock()
        auth_service.sign_task = AsyncMock(return_value=("signature_abc123", "2025-01-01T12:00:00"))
        return auth_service

    @pytest.fixture
    def observer_with_auth(self, time_service, mock_memory_service, mock_bus_manager, mock_auth_service):
        """Create observer with auth service and WA ID."""
        observer = ConcreteObserver(
            on_observe=AsyncMock(),
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            time_service=time_service,
            origin_service="test",
        )
        observer.auth_service = mock_auth_service
        observer.observer_wa_id = "observer_wa_001"
        return observer

    @pytest.mark.asyncio
    async def test_task_signing_success(self, observer_with_auth, mock_auth_service):
        """Test successful task signing with WA certificate."""
        # Create a mock task
        mock_task = Mock()
        mock_task.task_id = "task_to_sign_123"

        # Patch persistence.add_task
        with patch("ciris_engine.logic.persistence.add_task") as mock_add_task:
            await observer_with_auth._sign_and_add_task(mock_task)

        # Verify auth service was called
        mock_auth_service.sign_task.assert_called_once_with(mock_task, "observer_wa_001")

        # Verify task was signed
        assert mock_task.signed_by == "observer_wa_001"
        assert mock_task.signature == "signature_abc123"
        assert mock_task.signed_at == "2025-01-01T12:00:00"

        # Verify task was added to persistence
        mock_add_task.assert_called_once_with(mock_task)

    @pytest.mark.asyncio
    async def test_task_signing_failure_continues(self, observer_with_auth, mock_auth_service):
        """Test that task signing failure doesn't prevent task addition."""
        # Create a mock task
        mock_task = Mock()
        mock_task.task_id = "task_fail_sign_456"

        # Make auth service raise exception
        mock_auth_service.sign_task.side_effect = RuntimeError("Certificate expired")

        # Patch persistence.add_task
        with patch("ciris_engine.logic.persistence.add_task") as mock_add_task:
            await observer_with_auth._sign_and_add_task(mock_task)

        # Verify auth service was called
        mock_auth_service.sign_task.assert_called_once_with(mock_task, "observer_wa_001")

        # Verify task was NOT signed (attributes not set)
        assert not hasattr(mock_task, "signed_by") or mock_task.signed_by != "observer_wa_001"
        assert not hasattr(mock_task, "signature") or mock_task.signature != "signature_abc123"

        # Verify task was still added to persistence despite signing failure
        mock_add_task.assert_called_once_with(mock_task)

    @pytest.mark.asyncio
    async def test_task_without_auth_service(self, time_service, mock_memory_service, mock_bus_manager):
        """Test task addition when auth service is not available."""
        # Create observer without auth service
        observer = ConcreteObserver(
            on_observe=AsyncMock(),
            bus_manager=mock_bus_manager,
            memory_service=mock_memory_service,
            time_service=time_service,
            origin_service="test",
        )
        # No auth_service or observer_wa_id set

        # Create a mock task with spec to control attributes
        from ciris_engine.schemas.runtime.models import Task
        mock_task = Mock(spec=Task)
        mock_task.task_id = "unsigned_task_789"

        # Patch persistence.add_task
        with patch("ciris_engine.logic.persistence.add_task") as mock_add_task:
            await observer._sign_and_add_task(mock_task)

        # Verify task was not modified (no auth service means no signing)
        # The code only sets these attributes if auth_service and observer_wa_id exist
        # Since they don't exist, the attributes should not be set
        mock_add_task.assert_called_once_with(mock_task)
        
        # Verify the task passed to persistence is the same mock_task
        # without any signing attributes set on it
        assert mock_add_task.call_args[0][0] == mock_task
