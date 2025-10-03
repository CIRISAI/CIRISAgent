"""
Tests for base observer adaptive filter integration.

Tests the complete message handling flow including adaptive filter evaluation
and how filter results affect task creation.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.adapters.base_observer import BaseObserver
from ciris_engine.schemas.runtime.messages import IncomingMessage, MessageHandlingResult, MessageHandlingStatus
from ciris_engine.schemas.services.filters_core import FilterPriority, FilterResult


class ConcreteObserver(BaseObserver[IncomingMessage]):
    """Concrete observer implementation for testing."""

    async def start(self) -> None:
        """Start the observer (required abstract method)."""
        pass

    async def stop(self) -> None:
        """Stop the observer (required abstract method)."""
        pass


@pytest.fixture
def observer():
    """Create test observer instance."""
    obs = ConcreteObserver(
        on_observe=AsyncMock(),
        bus_manager=Mock(),
        memory_service=AsyncMock(),
        time_service=Mock(),
        origin_service="test",
    )
    # Mock required services
    obs.time_service.now.return_value = datetime.now(timezone.utc)
    obs.time_service.now_iso.return_value = datetime.now(timezone.utc).isoformat()
    obs.resource_monitor = Mock()
    obs.communication_service = AsyncMock()
    obs.memory_bus = AsyncMock()
    obs.memory_bus.search = AsyncMock(return_value=[])
    obs.secrets_service = AsyncMock()
    obs.secrets_service.process_message_secrets = AsyncMock(side_effect=lambda msg: msg)
    return obs


@pytest.fixture
def sample_message():
    """Create sample incoming message."""
    return IncomingMessage(
        message_id="msg-123",
        author_id="user-456",
        author_name="Test User",
        content="Hello agent!",
        destination_id="test-channel",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@pytest.fixture
def filter_result_allow():
    """Create filter result that allows processing."""
    return FilterResult(
        message_id="msg-123",
        priority=FilterPriority.MEDIUM,
        triggered_filters=[],
        should_process=True,
        reasoning="Normal message, should process",
    )


@pytest.fixture
def filter_result_filtered():
    """Create filter result that blocks processing."""
    return FilterResult(
        message_id="msg-123",
        priority=FilterPriority.IGNORE,
        triggered_filters=["spam_filter", "rate_limit"],
        should_process=False,
        reasoning="Message contains spam keywords and exceeds rate limit",
    )


@pytest.fixture
def filter_result_high_priority():
    """Create filter result with high priority."""
    return FilterResult(
        message_id="msg-123",
        priority=FilterPriority.HIGH,
        triggered_filters=["new_user_detector"],
        should_process=True,
        reasoning="New user first message",
    )


@pytest.fixture
def filter_result_critical():
    """Create filter result with critical priority."""
    return FilterResult(
        message_id="msg-123",
        priority=FilterPriority.CRITICAL,
        triggered_filters=["direct_mention", "dm_detector"],
        should_process=True,
        reasoning="Direct mention in DM",
    )


class TestAdaptiveFilterIntegration:
    """Tests for adaptive filter integration in message handling."""

    @pytest.mark.asyncio
    async def test_message_allowed_by_filter_creates_task(self, observer, sample_message, filter_result_allow):
        """Test that messages allowed by filter result in task creation."""
        # Mock filter service
        observer.filter_service = AsyncMock()
        observer.filter_service.filter_message = AsyncMock(return_value=filter_result_allow)

        # Mock task creation
        with patch.object(observer, "_create_passive_observation_result") as mock_create:
            from ciris_engine.schemas.runtime.messages import PassiveObservationResult

            mock_create.return_value = PassiveObservationResult(
                task_id="task-789",
                task_created=True,
                thought_id="thought-101",
                existing_task_updated=False,
            )

            result = await observer.handle_incoming_message(sample_message)

            # Verify task was created
            assert result.status == MessageHandlingStatus.TASK_CREATED
            assert result.task_id == "task-789"
            assert result.filtered is False
            mock_create.assert_called_once()

    @pytest.mark.asyncio
    async def test_message_filtered_out_no_task_created(self, observer, sample_message, filter_result_filtered):
        """Test that filtered messages do not create tasks."""
        # Mock filter service
        observer.filter_service = AsyncMock()
        observer.filter_service.filter_message = AsyncMock(return_value=filter_result_filtered)

        # Mock task creation (should NOT be called)
        with patch.object(observer, "_create_passive_observation_result") as mock_create:
            result = await observer.handle_incoming_message(sample_message)

            # Verify no task was created
            assert result.status == MessageHandlingStatus.FILTERED_OUT
            assert result.task_id is None
            assert result.filtered is True
            assert "spam" in result.filter_reasoning.lower()
            assert "rate limit" in result.filter_reasoning.lower()
            mock_create.assert_not_called()

    @pytest.mark.asyncio
    async def test_high_priority_filter_creates_priority_task(
        self, observer, sample_message, filter_result_high_priority
    ):
        """Test that high priority filter results create high priority tasks."""
        # Mock filter service
        observer.filter_service = AsyncMock()
        observer.filter_service.filter_message = AsyncMock(return_value=filter_result_high_priority)

        # Mock priority task creation
        with patch.object(observer, "_create_priority_observation_result") as mock_create_priority:
            from ciris_engine.schemas.runtime.messages import PassiveObservationResult

            mock_create_priority.return_value = PassiveObservationResult(
                task_id="priority-task-999",
                task_created=True,
                thought_id="thought-202",
                existing_task_updated=False,
            )

            result = await observer.handle_incoming_message(sample_message)

            # Verify priority task was created
            assert result.status == MessageHandlingStatus.TASK_CREATED
            assert result.task_id == "priority-task-999"
            assert result.task_priority == 5  # High priority
            mock_create_priority.assert_called_once()

    @pytest.mark.asyncio
    async def test_critical_priority_filter_creates_critical_task(
        self, observer, sample_message, filter_result_critical
    ):
        """Test that critical priority filter results create critical priority tasks."""
        # Mock filter service
        observer.filter_service = AsyncMock()
        observer.filter_service.filter_message = AsyncMock(return_value=filter_result_critical)

        # Mock priority task creation
        with patch.object(observer, "_create_priority_observation_result") as mock_create_priority:
            from ciris_engine.schemas.runtime.messages import PassiveObservationResult

            mock_create_priority.return_value = PassiveObservationResult(
                task_id="critical-task-888",
                task_created=True,
                thought_id="thought-303",
                existing_task_updated=False,
            )

            result = await observer.handle_incoming_message(sample_message)

            # Verify critical task was created
            assert result.status == MessageHandlingStatus.TASK_CREATED
            assert result.task_id == "critical-task-888"
            assert result.task_priority == 10  # Critical priority
            mock_create_priority.assert_called_once()

    @pytest.mark.asyncio
    async def test_filter_reasoning_included_in_result(self, observer, sample_message, filter_result_filtered):
        """Test that filter reasoning is included in the result."""
        observer.filter_service = AsyncMock()
        observer.filter_service.filter_message = AsyncMock(return_value=filter_result_filtered)

        result = await observer.handle_incoming_message(sample_message)

        # Verify reasoning is present
        assert result.filter_reasoning == "Message contains spam keywords and exceeds rate limit"
        assert result.filtered is True

    @pytest.mark.asyncio
    async def test_triggered_filters_tracked(self, observer, sample_message, filter_result_filtered):
        """Test that triggered filters are tracked in filter result."""
        observer.filter_service = AsyncMock()
        observer.filter_service.filter_message = AsyncMock(return_value=filter_result_filtered)

        result = await observer.handle_incoming_message(sample_message)

        # Verify filter was triggered
        assert result.filtered is True
        # The triggered filters are in the filter_result, not directly in MessageHandlingResult
        # but the reasoning should mention them
        assert "spam" in result.filter_reasoning.lower() or "rate" in result.filter_reasoning.lower()

    @pytest.mark.asyncio
    async def test_no_filter_service_allows_all_messages(self, observer, sample_message):
        """Test that messages are allowed when no filter service is configured."""
        # No filter service configured
        observer.filter_service = None

        with patch.object(observer, "_create_passive_observation_result") as mock_create:
            from ciris_engine.schemas.runtime.messages import PassiveObservationResult

            mock_create.return_value = PassiveObservationResult(
                task_id="task-default-111",
                task_created=True,
                thought_id="thought-404",
                existing_task_updated=False,
            )

            result = await observer.handle_incoming_message(sample_message)

            # Verify message was processed (no filtering)
            assert result.status == MessageHandlingStatus.TASK_CREATED
            assert result.task_id == "task-default-111"
            assert result.filtered is False


class TestFilterPriorityMapping:
    """Tests for mapping filter priorities to task priorities."""

    @pytest.mark.asyncio
    async def test_low_priority_maps_to_passive(self, observer, sample_message):
        """Test that LOW filter priority creates passive (0) priority task."""
        filter_result = FilterResult(
            message_id="msg-123",
            priority=FilterPriority.LOW,
            triggered_filters=[],
            should_process=True,
            reasoning="Low priority message",
        )

        observer.filter_service = AsyncMock()
        observer.filter_service.filter_message = AsyncMock(return_value=filter_result)

        with patch.object(observer, "_create_passive_observation_result") as mock_create:
            from ciris_engine.schemas.runtime.messages import PassiveObservationResult

            mock_create.return_value = PassiveObservationResult(
                task_id="task-low-222",
                task_created=True,
                existing_task_updated=False,
            )

            result = await observer.handle_incoming_message(sample_message)

            assert result.task_priority == 0  # Passive

    @pytest.mark.asyncio
    async def test_medium_priority_maps_to_passive(self, observer, sample_message):
        """Test that MEDIUM filter priority creates passive (0) priority task."""
        filter_result = FilterResult(
            message_id="msg-123",
            priority=FilterPriority.MEDIUM,
            triggered_filters=[],
            should_process=True,
            reasoning="Medium priority message",
        )

        observer.filter_service = AsyncMock()
        observer.filter_service.filter_message = AsyncMock(return_value=filter_result)

        with patch.object(observer, "_create_passive_observation_result") as mock_create:
            from ciris_engine.schemas.runtime.messages import PassiveObservationResult

            mock_create.return_value = PassiveObservationResult(
                task_id="task-med-333",
                task_created=True,
                existing_task_updated=False,
            )

            result = await observer.handle_incoming_message(sample_message)

            assert result.task_priority == 0  # Still passive

    @pytest.mark.asyncio
    async def test_ignore_priority_blocks_message(self, observer, sample_message):
        """Test that IGNORE filter priority blocks message processing."""
        filter_result = FilterResult(
            message_id="msg-123",
            priority=FilterPriority.IGNORE,
            triggered_filters=["ignore_bot"],
            should_process=False,
            reasoning="Bot message ignored",
        )

        observer.filter_service = AsyncMock()
        observer.filter_service.filter_message = AsyncMock(return_value=filter_result)

        result = await observer.handle_incoming_message(sample_message)

        assert result.status == MessageHandlingStatus.FILTERED_OUT
        assert result.task_id is None
        assert result.filtered is True


class TestFilterIntegrationEdgeCases:
    """Tests for edge cases in filter integration."""

    @pytest.mark.asyncio
    async def test_filter_service_exception_allows_message(self, observer, sample_message):
        """Test that filter service exceptions don't block messages."""
        # Mock filter service that raises exception
        observer.filter_service = AsyncMock()
        observer.filter_service.filter_message = AsyncMock(side_effect=Exception("Filter service error"))

        with patch.object(observer, "_create_passive_observation_result") as mock_create:
            from ciris_engine.schemas.runtime.messages import PassiveObservationResult

            mock_create.return_value = PassiveObservationResult(
                task_id="task-error-555",
                task_created=True,
                existing_task_updated=False,
            )

            # Should not raise, should process message
            result = await observer.handle_incoming_message(sample_message)

            # Message should still be processed (fail-open)
            assert result.status == MessageHandlingStatus.TASK_CREATED
            assert result.task_id == "task-error-555"
