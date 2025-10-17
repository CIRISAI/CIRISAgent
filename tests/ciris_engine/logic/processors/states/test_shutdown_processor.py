"""
Comprehensive tests for shutdown_processor.py

Tests the ShutdownProcessor class which handles graceful agent shutdown
through normal cognitive flow.

Target: 80%+ coverage (currently 32.4%)
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.processors.states.shutdown_processor import ShutdownProcessor
from ciris_engine.schemas.processors.base import ProcessorServices
from ciris_engine.schemas.processors.results import ShutdownResult
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, TaskContext

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def mock_time_service():
    """Mock time service"""
    service = Mock()
    service.now.return_value = datetime(2025, 10, 7, 12, 0, 0, tzinfo=timezone.utc)
    service.now_iso.return_value = "2025-10-07T12:00:00+00:00"
    return service


@pytest.fixture
def mock_config_accessor():
    """Mock config accessor"""
    config = Mock()
    config.get.return_value = None
    return config


@pytest.fixture
def mock_thought_processor():
    """Mock thought processor"""
    processor = Mock()
    processor.process_thought_item = AsyncMock(return_value=None)
    return processor


@pytest.fixture
def mock_action_dispatcher():
    """Mock action dispatcher"""
    dispatcher = Mock()
    dispatcher.dispatch = AsyncMock()
    return dispatcher


@pytest.fixture
def mock_services(mock_time_service):
    """Mock services using ProcessorServices schema"""
    mock_resource_monitor = Mock()
    mock_communication_bus = Mock()
    mock_communication_bus.get_default_channel = AsyncMock(return_value="default_channel_123")

    return ProcessorServices(
        time_service=mock_time_service,
        resource_monitor=mock_resource_monitor,
        communication_bus=mock_communication_bus,
        discord_service=None,
        memory_service=None,
        audit_service=None,
        telemetry_service=None,
        service_registry=None,
        identity_manager=None,
        secrets_service=None,
        graphql_provider=None,
        app_config=None,
        runtime=None,
        llm_service=None,
    )


@pytest.fixture
def mock_runtime():
    """Mock runtime"""
    runtime = Mock()
    runtime.startup_channel_id = "test_channel_123"
    runtime.current_shutdown_context = None
    return runtime


@pytest.fixture
def mock_auth_service():
    """Mock auth service"""
    service = Mock()
    service.get_wa = AsyncMock(return_value=None)
    return service


@pytest.fixture
def shutdown_processor(
    mock_config_accessor,
    mock_thought_processor,
    mock_action_dispatcher,
    mock_services,
    mock_time_service,
    mock_runtime,
    mock_auth_service,
):
    """Create a ShutdownProcessor instance"""
    return ShutdownProcessor(
        config_accessor=mock_config_accessor,
        thought_processor=mock_thought_processor,
        action_dispatcher=mock_action_dispatcher,
        services=mock_services,
        time_service=mock_time_service,
        runtime=mock_runtime,
        auth_service=mock_auth_service,
    )


@pytest.fixture
def sample_task():
    """Create a sample shutdown task"""
    now = datetime(2025, 10, 7, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    context = TaskContext(
        channel_id="test_channel",
        user_id="system",
        correlation_id="shutdown_abc123",
        parent_task_id=None,
    )
    return Task(
        task_id="shutdown_test_123",
        channel_id="test_channel",
        description="System shutdown requested: test shutdown",
        priority=10,
        status=TaskStatus.ACTIVE,
        created_at=now,
        updated_at=now,
        context=context,
        parent_task_id=None,
    )


@pytest.fixture
def sample_thought():
    """Create a sample thought"""
    thought = Mock()
    thought.thought_id = "thought_123"
    thought.source_task_id = "shutdown_test_123"
    thought.status = ThoughtStatus.PENDING
    thought.thought_type = "standard"  # Required for ProcessingQueueItem
    thought.context = {}  # Required for ProcessingQueueItem
    thought.ponder_notes = []  # Required for ProcessingQueueItem
    # Add content structure for ProcessingQueueItem.from_thought
    # ThoughtContent requires 'text' field
    thought.content = {
        "text": "Shutdown request",
        "context": {},
    }
    # No final_action for PENDING thoughts - they haven't been processed yet
    thought.final_action = None
    return thought


# ============================================================================
# BASIC INITIALIZATION TESTS
# ============================================================================


class TestInitialization:
    """Tests for ShutdownProcessor initialization"""

    def test_init_creates_instance(self, shutdown_processor):
        """Test that ShutdownProcessor initializes correctly"""
        assert shutdown_processor is not None
        assert shutdown_processor.shutdown_task is None
        assert shutdown_processor.shutdown_complete is False
        assert shutdown_processor.shutdown_result is None
        assert shutdown_processor.thought_manager is not None

    def test_get_supported_states(self, shutdown_processor):
        """Test that only SHUTDOWN state is supported"""
        states = shutdown_processor.get_supported_states()
        assert states == [AgentState.SHUTDOWN]

    @pytest.mark.asyncio
    async def test_can_process_shutdown_state(self, shutdown_processor):
        """Test that can_process returns True for SHUTDOWN state"""
        result = await shutdown_processor.can_process(AgentState.SHUTDOWN)
        assert result is True

    @pytest.mark.asyncio
    async def test_can_process_other_states(self, shutdown_processor):
        """Test that can_process returns False for non-SHUTDOWN states"""
        result = await shutdown_processor.can_process(AgentState.WORK)
        assert result is False


# ============================================================================
# TASK CREATION TESTS
# ============================================================================


class TestTaskCreation:
    """Tests for shutdown task creation"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.add_task")
    async def test_create_shutdown_task_normal(
        self,
        mock_add_task,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test creating a normal (non-emergency) shutdown task"""
        # Mock add_task to return task_id
        mock_add_task.return_value = "shutdown_test_123"

        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test shutdown"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Execute
        await shutdown_processor._create_shutdown_task()

        # Verify
        assert shutdown_processor.shutdown_task is not None
        assert "shutdown_" in shutdown_processor.shutdown_task.task_id
        assert "Test shutdown" in shutdown_processor.shutdown_task.description
        assert shutdown_processor.shutdown_task.priority == 10

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.add_task")
    async def test_create_shutdown_task_emergency_with_root_auth(
        self,
        mock_add_task,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test creating emergency shutdown with ROOT authorization"""
        # Mock add_task to return task_id
        mock_add_task.return_value = "shutdown_emergency_123"

        # Setup
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Emergency shutdown"
        shutdown_manager.is_force_shutdown.return_value = True
        shutdown_manager.get_requester_wa_id.return_value = "wa_root_123"
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Mock WA with ROOT role
        from ciris_engine.schemas.services.authority_core import WARole

        mock_wa = Mock()
        mock_wa.role = WARole.ROOT
        shutdown_processor.auth_service.get_wa = AsyncMock(return_value=mock_wa)

        # Execute
        await shutdown_processor._create_shutdown_task()

        # Verify
        assert shutdown_processor.shutdown_task is not None
        assert "EMERGENCY" in shutdown_processor.shutdown_task.description
        assert shutdown_processor.runtime.current_shutdown_context is not None
        assert shutdown_processor.runtime.current_shutdown_context.is_terminal is True
        assert shutdown_processor.runtime.current_shutdown_context.allow_deferral is False

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.add_task")
    async def test_create_shutdown_task_emergency_with_authority_auth(
        self,
        mock_add_task,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test creating emergency shutdown with AUTHORITY authorization"""
        # Mock add_task to return task_id
        mock_add_task.return_value = "shutdown_emergency_authority_123"

        # Setup
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Emergency shutdown"
        shutdown_manager.is_force_shutdown.return_value = True
        shutdown_manager.get_requester_wa_id.return_value = "wa_authority_123"
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Mock WA with AUTHORITY role
        from ciris_engine.schemas.services.authority_core import WARole

        mock_wa = Mock()
        mock_wa.role = WARole.AUTHORITY
        shutdown_processor.auth_service.get_wa = AsyncMock(return_value=mock_wa)

        # Execute
        await shutdown_processor._create_shutdown_task()

        # Verify - AUTHORITY should be accepted
        assert shutdown_processor.shutdown_task is not None

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    async def test_create_shutdown_task_emergency_insufficient_role(
        self,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test that emergency shutdown fails with insufficient role"""
        # Setup
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Emergency shutdown"
        shutdown_manager.is_force_shutdown.return_value = True
        shutdown_manager.get_requester_wa_id.return_value = "wa_observer_123"
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Mock WA with OBSERVER role (insufficient)
        from ciris_engine.schemas.services.authority_core import WARole

        mock_wa = Mock()
        mock_wa.role = WARole.OBSERVER
        shutdown_processor.auth_service.get_wa = AsyncMock(return_value=mock_wa)

        # Execute and verify exception
        with pytest.raises(ValueError, match="Emergency shutdown requires ROOT or AUTHORITY"):
            await shutdown_processor._create_shutdown_task()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    async def test_create_shutdown_task_emergency_wa_not_found(
        self,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test that emergency shutdown fails when WA not found"""
        # Setup
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Emergency shutdown"
        shutdown_manager.is_force_shutdown.return_value = True
        shutdown_manager.get_requester_wa_id.return_value = "wa_missing_123"
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Mock WA not found
        shutdown_processor.auth_service.get_wa = AsyncMock(return_value=None)

        # Execute and verify exception
        with pytest.raises(ValueError, match="Emergency shutdown requester not found"):
            await shutdown_processor._create_shutdown_task()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.add_task")
    async def test_create_shutdown_task_with_channel_from_comm_bus(
        self,
        mock_add_task,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test getting channel ID from communication bus when not on runtime"""
        # Mock add_task to return task_id
        mock_add_task.return_value = "shutdown_comm_bus_123"

        # Setup
        shutdown_processor.runtime.startup_channel_id = None
        shutdown_processor.runtime.get_primary_channel_id = None

        mock_comm_bus = Mock()
        mock_comm_bus.get_default_channel = AsyncMock(return_value="comm_channel_456")
        # Update the communication_bus in the ProcessorServices object
        shutdown_processor.services.communication_bus = mock_comm_bus

        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Execute
        await shutdown_processor._create_shutdown_task()

        # Verify
        assert shutdown_processor.shutdown_task.channel_id == "comm_channel_456"


# ============================================================================
# SHUTDOWN PROCESSING TESTS
# ============================================================================


class TestShutdownProcessing:
    """Tests for shutdown processing flow"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_shutdown_completed_task(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
    ):
        """Test processing when task is already completed"""
        # Setup
        sample_task.status = TaskStatus.COMPLETED
        shutdown_processor.shutdown_task = sample_task
        mock_persistence.get_task_by_id.return_value = sample_task

        # Execute
        result = await shutdown_processor.process(round_number=1)

        # Verify
        assert isinstance(result, ShutdownResult)
        assert result.shutdown_ready is True
        assert shutdown_processor.shutdown_complete is True

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_shutdown_failed_task_rejected(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
        sample_thought,
    ):
        """Test processing when task failed due to REJECT"""
        # Setup
        sample_task.status = TaskStatus.FAILED
        shutdown_processor.shutdown_task = sample_task
        mock_persistence.get_task_by_id.return_value = sample_task

        # Mock final action as REJECT
        action = Mock()
        action.action_type = "REJECT"
        action.action_params = {"reason": "Not ready to shutdown"}
        sample_thought.final_action = action

        mock_persistence.get_thoughts_by_task_id.return_value = [sample_thought]

        # Execute
        result = await shutdown_processor.process(round_number=1)

        # Verify
        assert isinstance(result, ShutdownResult)
        assert result.shutdown_ready is False  # Rejected, not ready
        assert shutdown_processor.shutdown_complete is True
        assert shutdown_processor.shutdown_result.status == "rejected"

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.add_task")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_activates_pending_task(
        self,
        mock_persistence,
        mock_add_task,
        mock_get_shutdown_manager,
        shutdown_processor,
        sample_task,
    ):
        """Test that PENDING task is activated"""
        # Setup
        sample_task.status = TaskStatus.PENDING
        shutdown_processor.shutdown_task = None

        # Mock add_task for task creation
        mock_add_task.return_value = "shutdown_test_123"

        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # First call returns PENDING, second returns ACTIVE
        mock_persistence.get_task_by_id.side_effect = [
            sample_task,
            Task(**{**sample_task.model_dump(), "status": TaskStatus.ACTIVE}),
        ]
        mock_persistence.get_thoughts_by_task_id.return_value = []

        # Execute
        result = await shutdown_processor.process(round_number=1)

        # Verify
        mock_persistence.update_task_status.assert_called_once()
        assert result.shutdown_ready is False  # Still in progress

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.add_task")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_generates_seed_thought(
        self,
        mock_persistence,
        mock_add_task,
        mock_get_shutdown_manager,
        shutdown_processor,
        sample_task,
    ):
        """Test that seed thought is generated for ACTIVE task with no thoughts"""
        # Mock add_task for task creation
        mock_add_task.return_value = "shutdown_test_123"

        # Setup
        sample_task.status = TaskStatus.ACTIVE
        shutdown_processor.shutdown_task = None

        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        mock_persistence.get_task_by_id.return_value = sample_task
        mock_persistence.get_thoughts_by_task_id.return_value = []  # No existing thoughts

        # Mock thought manager
        shutdown_processor.thought_manager.generate_seed_thoughts = Mock(return_value=1)

        # Execute
        await shutdown_processor.process(round_number=1)

        # Verify
        shutdown_processor.thought_manager.generate_seed_thoughts.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_error_handling(
        self,
        mock_persistence,
        shutdown_processor,
    ):
        """Test error handling in process method"""
        # Setup - make persistence raise exception
        mock_persistence.get_task_by_id.side_effect = Exception("Database error")
        shutdown_processor.shutdown_task = Mock(task_id="test_123")

        # Execute
        result = await shutdown_processor.process(round_number=1)

        # Verify
        assert isinstance(result, ShutdownResult)
        assert result.errors == 1
        assert result.shutdown_ready is False


# ============================================================================
# THOUGHT PROCESSING TESTS
# ============================================================================


class TestThoughtProcessing:
    """Tests for thought processing during shutdown"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_shutdown_thoughts_no_task(
        self,
        mock_persistence,
        shutdown_processor,
    ):
        """Test that processing returns early when no shutdown task"""
        shutdown_processor.shutdown_task = None

        await shutdown_processor._process_shutdown_thoughts()

        # Should return early without calling persistence
        mock_persistence.get_thoughts_by_task_id.assert_not_called()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_shutdown_thoughts_no_pending(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
    ):
        """Test that processing returns early when no pending thoughts"""
        shutdown_processor.shutdown_task = sample_task
        mock_persistence.get_thoughts_by_task_id.return_value = []

        await shutdown_processor._process_shutdown_thoughts()

        # Should call get_thoughts but not update any
        mock_persistence.get_thoughts_by_task_id.assert_called_once()
        mock_persistence.update_thought_status.assert_not_called()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_shutdown_thoughts_processes_pending(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
        sample_thought,
    ):
        """Test that pending thoughts are processed"""
        # Setup
        shutdown_processor.shutdown_task = sample_task
        sample_thought.status = ThoughtStatus.PENDING

        mock_persistence.get_thoughts_by_task_id.return_value = [sample_thought]
        mock_persistence.get_task_by_id.return_value = sample_task

        # Mock process_thought_item to return a result
        from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
        from ciris_engine.schemas.runtime.enums import HandlerActionType

        mock_action = Mock()
        mock_action.selected_action = HandlerActionType.SPEAK
        mock_action.final_action = None  # Important: prevent Mock from auto-creating this attribute
        shutdown_processor.process_thought_item = AsyncMock(return_value=mock_action)

        # Execute
        await shutdown_processor._process_shutdown_thoughts()

        # Verify
        mock_persistence.update_thought_status.assert_called()
        shutdown_processor.process_thought_item.assert_called_once()
        shutdown_processor.action_dispatcher.dispatch.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_shutdown_thoughts_handles_errors(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
        sample_thought,
    ):
        """Test that thought processing errors are handled gracefully"""
        # Setup
        shutdown_processor.shutdown_task = sample_task
        sample_thought.status = ThoughtStatus.PENDING

        mock_persistence.get_thoughts_by_task_id.return_value = [sample_thought]
        shutdown_processor.process_thought_item = AsyncMock(side_effect=Exception("Processing error"))

        # Execute - should not raise
        await shutdown_processor._process_shutdown_thoughts()

        # Verify error was logged and thought marked as failed
        assert mock_persistence.update_thought_status.call_count >= 1


# ============================================================================
# FAILURE REASON TESTS
# ============================================================================


class TestFailureReason:
    """Tests for _check_failure_reason method"""

    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    def test_check_failure_reason_reject_action(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
        sample_thought,
    ):
        """Test checking failure reason when action is REJECT"""
        # Setup
        action = Mock()
        action.action_type = "REJECT"
        action.action_params = {"reason": "I'm not ready"}
        sample_thought.final_action = action

        mock_persistence.get_thoughts_by_task_id.return_value = [sample_thought]

        # Execute
        result = shutdown_processor._check_failure_reason(sample_task)

        # Verify
        assert isinstance(result, ShutdownResult)
        assert result.status == "rejected"
        assert result.action == "shutdown_rejected"
        assert "not ready" in result.reason

    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    def test_check_failure_reason_no_thoughts(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
    ):
        """Test checking failure reason when no thoughts exist"""
        mock_persistence.get_thoughts_by_task_id.return_value = []

        # Execute
        result = shutdown_processor._check_failure_reason(sample_task)

        # Verify
        assert isinstance(result, ShutdownResult)
        assert result.status == "error"
        assert result.action == "shutdown_error"

    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    def test_check_failure_reason_no_final_action(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
        sample_thought,
    ):
        """Test checking failure reason when thought has no final action"""
        sample_thought.final_action = None
        mock_persistence.get_thoughts_by_task_id.return_value = [sample_thought]

        # Execute
        result = shutdown_processor._check_failure_reason(sample_task)

        # Verify
        assert isinstance(result, ShutdownResult)
        assert result.status == "error"


# ============================================================================
# CLEANUP TESTS
# ============================================================================


class TestCleanup:
    """Tests for cleanup method"""

    def test_cleanup_clears_runtime_context(self, shutdown_processor):
        """Test that cleanup clears runtime shutdown context"""
        # Setup
        shutdown_processor.runtime.current_shutdown_context = Mock()

        # Execute
        result = shutdown_processor.cleanup()

        # Verify
        assert result is True
        assert shutdown_processor.runtime.current_shutdown_context is None

    def test_cleanup_without_runtime(self, shutdown_processor):
        """Test that cleanup works when runtime has no context attribute"""
        # Setup
        shutdown_processor.runtime = Mock(spec=[])  # No attributes

        # Execute
        result = shutdown_processor.cleanup()

        # Verify
        assert result is True  # Should succeed gracefully
