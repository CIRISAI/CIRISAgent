"""Fixtures for WakeupProcessor tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.processors.states.wakeup_processor import WakeupProcessor
from ciris_engine.schemas.processors.base import ProcessorServices
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought


@pytest.fixture
def mock_time_service():
    """Create mock time service."""
    current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_service = Mock()
    mock_service.now.return_value = current_time
    mock_service.now_iso.return_value = current_time.isoformat()
    return mock_service


@pytest.fixture
def mock_communication_bus():
    """Mock communication bus with default channel."""
    bus = Mock()
    bus.get_default_channel = AsyncMock(return_value="test_channel_123")
    return bus


@pytest.fixture
def mock_auth_service():
    """Mock authentication service."""
    return Mock()


@pytest.fixture
def mock_services(mock_time_service, mock_communication_bus):
    """Create minimal mock services for WakeupProcessor."""
    return ProcessorServices(
        time_service=mock_time_service,
        communication_bus=mock_communication_bus,
        telemetry_service=Mock(record_metric=AsyncMock()),
        memory_service=Mock(),
        identity_manager=Mock(),
        resource_monitor=Mock(),
        llm_service=Mock(),
    )


@pytest.fixture
def wakeup_processor(mock_time_service, mock_services, mock_auth_service):
    """Create WakeupProcessor instance with mocked dependencies."""
    # Create required base processor dependencies
    mock_config = Mock()
    mock_thought_processor = Mock()
    mock_action_dispatcher = Mock()

    processor = WakeupProcessor(
        config_accessor=mock_config,
        thought_processor=mock_thought_processor,
        action_dispatcher=mock_action_dispatcher,
        services=mock_services,
        startup_channel_id="test_channel",
        time_service=mock_time_service,
        auth_service=mock_auth_service,
    )
    return processor


@pytest.fixture
def sample_task():
    """Create a sample Task for testing."""
    return Task(
        task_id="TEST_TASK_123",
        channel_id="test_channel",
        description="Test task description",
        status=TaskStatus.ACTIVE,
        priority=1,
        created_at="2024-01-01T12:00:00Z",
        updated_at="2024-01-01T12:00:00Z",
    )


@pytest.fixture
def sample_thought():
    """Create a sample Thought for testing."""
    return Thought(
        thought_id="th_test_123",
        source_task_id="TEST_TASK_123",
        content="Test thought content",
        round_number=1,
        status=ThoughtStatus.PENDING,
        created_at="2024-01-01T12:00:00Z",
        updated_at="2024-01-01T12:00:00Z",
    )


@pytest.fixture
def wakeup_task_sequence():
    """Create a sequence of wakeup tasks (root + 3 steps)."""
    root_task = Task(
        task_id="WAKEUP_ROOT_123",
        channel_id="test_channel",
        description="Wakeup sequence root",
        status=TaskStatus.ACTIVE,
        priority=1,
        created_at="2024-01-01T12:00:00Z",
        updated_at="2024-01-01T12:00:00Z",
    )

    step1 = Task(
        task_id="IDENTITY_STEP1",
        channel_id="test_channel",
        description="Identity verification",
        status=TaskStatus.ACTIVE,
        priority=1,
        created_at="2024-01-01T12:00:01Z",
        updated_at="2024-01-01T12:00:01Z",
    )

    step2 = Task(
        task_id="CAPABILITY_STEP2",
        channel_id="test_channel",
        description="Capability check",
        status=TaskStatus.ACTIVE,
        priority=1,
        created_at="2024-01-01T12:00:02Z",
        updated_at="2024-01-01T12:00:02Z",
    )

    step3 = Task(
        task_id="READY_STEP3",
        channel_id="test_channel",
        description="Ready announcement",
        status=TaskStatus.ACTIVE,
        priority=1,
        created_at="2024-01-01T12:00:03Z",
        updated_at="2024-01-01T12:00:03Z",
    )

    return [root_task, step1, step2, step3]


@pytest.fixture
def completed_task():
    """Create a completed Task."""
    return Task(
        task_id="COMPLETED_TASK_123",
        channel_id="test_channel",
        description="Completed task",
        status=TaskStatus.COMPLETED,
        priority=1,
        created_at="2024-01-01T12:00:00Z",
        updated_at="2024-01-01T12:05:00Z",
    )


@pytest.fixture
def failed_task():
    """Create a failed Task."""
    return Task(
        task_id="FAILED_TASK_123",
        channel_id="test_channel",
        description="Failed task",
        status=TaskStatus.FAILED,
        priority=1,
        created_at="2024-01-01T12:00:00Z",
        updated_at="2024-01-01T12:03:00Z",
    )


@pytest.fixture
def thought_list_mixed_status():
    """Create a list of thoughts with mixed statuses."""
    return [
        Thought(
            thought_id="th_pending_1",
            source_task_id="TEST_TASK_123",
            content="Pending thought 1",
            round_number=1,
            status=ThoughtStatus.PENDING,
            created_at="2024-01-01T12:00:00Z",
            updated_at="2024-01-01T12:00:00Z",
        ),
        Thought(
            thought_id="th_processing_2",
            source_task_id="TEST_TASK_123",
            content="Processing thought 2",
            round_number=1,
            status=ThoughtStatus.PROCESSING,
            created_at="2024-01-01T12:00:01Z",
            updated_at="2024-01-01T12:00:01Z",
        ),
        Thought(
            thought_id="th_completed_3",
            source_task_id="TEST_TASK_123",
            content="Completed thought 3",
            round_number=1,
            status=ThoughtStatus.COMPLETED,
            created_at="2024-01-01T12:00:02Z",
            updated_at="2024-01-01T12:00:02Z",
        ),
    ]


@pytest.fixture
def thought_list_all_completed():
    """Create a list of all completed thoughts."""
    return [
        Thought(
            thought_id=f"th_completed_{i}",
            source_task_id="TEST_TASK_123",
            content=f"Completed thought {i}",
            round_number=1,
            status=ThoughtStatus.COMPLETED,
            created_at="2024-01-01T12:00:00Z",
            updated_at="2024-01-01T12:00:00Z",
        )
        for i in range(3)
    ]
