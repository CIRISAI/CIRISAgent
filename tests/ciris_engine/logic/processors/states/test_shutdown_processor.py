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
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_create_shutdown_task_normal(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
        sample_task,
    ):
        """Test creating a normal (non-emergency) shutdown task"""
        # Mock shared task not completed yet
        mock_is_completed.return_value = False

        # Mock claiming the shared task
        mock_try_claim.return_value = (sample_task, True)

        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test shutdown"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Execute
        await shutdown_processor._create_shutdown_task()

        # Verify
        assert shutdown_processor.shutdown_task is not None
        assert shutdown_processor.shutdown_task == sample_task
        assert shutdown_processor.shutdown_task.priority == 10

        # Verify try_claim was called
        mock_try_claim.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_create_shutdown_task_emergency_with_root_auth(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
        sample_task,
    ):
        """Test creating emergency shutdown with ROOT authorization"""
        # Mock shared task not completed
        mock_is_completed.return_value = False

        # Mock claiming shared task
        emergency_task = Task(
            task_id="shutdown_emergency_123",
            channel_id="test_channel",
            description="EMERGENCY shutdown requested: Emergency shutdown",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
        )
        mock_try_claim.return_value = (emergency_task, True)

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
        assert shutdown_processor.runtime.current_shutdown_context is not None
        assert shutdown_processor.runtime.current_shutdown_context.is_terminal is True
        assert shutdown_processor.runtime.current_shutdown_context.allow_deferral is False

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_create_shutdown_task_emergency_with_authority_auth(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test creating emergency shutdown with AUTHORITY authorization"""
        # Mock shared task not completed
        mock_is_completed.return_value = False

        # Mock claiming shared task
        emergency_task = Task(
            task_id="shutdown_emergency_authority_123",
            channel_id="test_channel",
            description="EMERGENCY shutdown requested: Emergency shutdown",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
        )
        mock_try_claim.return_value = (emergency_task, True)

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
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_create_shutdown_task_with_channel_from_comm_bus(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test getting channel ID from communication bus when not on runtime"""
        # Mock shared task not completed
        mock_is_completed.return_value = False

        # Setup
        shutdown_processor.runtime.startup_channel_id = None
        shutdown_processor.runtime.get_primary_channel_id = None

        mock_comm_bus = Mock()
        mock_comm_bus.get_default_channel = AsyncMock(return_value="comm_channel_456")
        # Update the communication_bus in the ProcessorServices object
        shutdown_processor.services.communication_bus = mock_comm_bus

        # Mock claiming shared task with correct channel
        task_with_channel = Task(
            task_id="shutdown_comm_bus_123",
            channel_id="comm_channel_456",
            description="System shutdown requested: Test",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
        )
        mock_try_claim.return_value = (task_with_channel, True)

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
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_activates_pending_task(
        self,
        mock_persistence,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
        sample_task,
    ):
        """Test that PENDING task is activated"""
        # Setup
        sample_task.status = TaskStatus.PENDING
        shutdown_processor.shutdown_task = None

        # Mock shared task functions
        mock_is_completed.return_value = False
        mock_try_claim.return_value = (sample_task, True)

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

        # Verify - called twice: once in _create_shutdown_task with "__shared__", once in _ensure_task_activated with "default"
        assert mock_persistence.update_task_status.call_count >= 1
        assert result.shutdown_ready is False  # Still in progress

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_generates_seed_thought(
        self,
        mock_persistence,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
        sample_task,
    ):
        """Test that seed thought is generated for ACTIVE task with no thoughts"""
        # Mock shared task functions
        mock_is_completed.return_value = False
        mock_try_claim.return_value = (sample_task, True)

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
        shutdown_processor.is_claiming_occurrence = True  # Simulate claiming occurrence
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
        shutdown_processor.is_claiming_occurrence = True  # Simulate claiming occurrence
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
        shutdown_processor.is_claiming_occurrence = True  # Simulate claiming occurrence
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


# ============================================================================
# ADDITIONAL COVERAGE TESTS - Target 95%+
# ============================================================================


class TestValidationErrors:
    """Tests for validation error paths"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_validate_shutdown_task_none_after_creation(
        self,
        mock_persistence,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test validation error when task is None (lines 103-104)"""
        # Setup
        mock_is_completed.return_value = False
        sample_task = Task(
            task_id="test_123",
            channel_id="test_channel",
            description="Test",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
        )
        mock_try_claim.return_value = (sample_task, True)

        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # First call returns task, but then we'll set shutdown_task to None
        mock_persistence.get_task_by_id.return_value = sample_task

        # Execute - create task first
        await shutdown_processor._create_shutdown_task()

        # Now manually set to None to trigger validation error
        shutdown_processor.shutdown_task = None

        # Call validate directly
        result = shutdown_processor._validate_shutdown_task()

        # Verify
        assert result is None  # Should return None when shutdown_task is None

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_validate_shutdown_task_disappeared(
        self,
        mock_persistence,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test validation error when task disappears from DB (lines 108-109)"""
        # Setup
        mock_is_completed.return_value = False
        sample_task = Task(
            task_id="test_123",
            channel_id="test_channel",
            description="Test",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="default",
        )
        mock_try_claim.return_value = (sample_task, True)

        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Execute - create task first
        await shutdown_processor._create_shutdown_task()

        # Now make get_task_by_id return None (task disappeared)
        mock_persistence.get_task_by_id.return_value = None

        # Call validate directly
        result = shutdown_processor._validate_shutdown_task()

        # Verify
        assert result is None  # Should return None when task disappeared

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_validate_task_fails(
        self,
        mock_persistence,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test process returns error when validate fails (line 200)"""
        # Setup
        mock_is_completed.return_value = False
        sample_task = Task(
            task_id="test_123",
            channel_id="test_channel",
            description="Test",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="default",
        )
        mock_try_claim.return_value = (sample_task, True)

        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Make get_task_by_id return None after task creation
        mock_persistence.get_task_by_id.return_value = None

        # Execute
        result = await shutdown_processor.process(round_number=1)

        # Verify
        assert result.status == "error"
        assert "validate" in result.message.lower()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_current_task_none_after_refetch(
        self,
        mock_persistence,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test process returns error when current_task is None after refetch (lines 216-217)"""
        # Setup
        mock_is_completed.return_value = False
        sample_task = Task(
            task_id="test_123",
            channel_id="test_channel",
            description="Test",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="default",
        )
        mock_try_claim.return_value = (sample_task, True)

        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # First call returns task for validation, second returns None after processing
        mock_persistence.get_task_by_id.side_effect = [sample_task, None]
        mock_persistence.get_thoughts_by_task_id.return_value = []

        # Execute
        result = await shutdown_processor.process(round_number=1)

        # Verify
        assert result.status == "error"
        assert "not found" in result.message.lower()


class TestAlreadyCompletedBranch:
    """Tests for already-completed shutdown task branch"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_handle_completed_task_already_reported(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
    ):
        """Test handling when shutdown is already complete (lines 172-175)"""
        # Setup
        sample_task.status = TaskStatus.COMPLETED
        shutdown_processor.shutdown_task = sample_task
        shutdown_processor.shutdown_complete = True  # Already marked complete
        shutdown_processor.shutdown_result = ShutdownResult(
            status="completed",
            action="shutdown_accepted",
            message="Agent acknowledged shutdown",
            shutdown_ready=True,
            duration_seconds=0.0,
        )
        mock_persistence.get_task_by_id.return_value = sample_task

        # Execute
        result = await shutdown_processor.process(round_number=2)

        # Verify - should still return the result
        assert result.shutdown_ready is True
        assert result.status in ["completed", "shutdown_complete"]


class TestThoughtOwnershipTransfer:
    """Tests for thought ownership transfer during seed thought generation"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.persistence.models.thoughts.transfer_thought_ownership")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_seed_thought_ownership_transfer(
        self,
        mock_persistence,
        mock_transfer,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test thought ownership transfer from __shared__ to occurrence (line 145)"""
        # Setup
        mock_is_completed.return_value = False
        sample_task = Task(
            task_id="test_123",
            channel_id="test_channel",
            description="Test",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_try_claim.return_value = (sample_task, True)

        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Mock shared thoughts created by thought manager
        shared_thought = Mock()
        shared_thought.thought_id = "shared_thought_123"
        shared_thought.source_task_id = "test_123"

        # First call: get_task_by_id returns the task
        # Second call: get_thoughts returns empty (before generation)
        # Third call: get_thoughts returns empty (for local thoughts check)
        # Fourth call: get_thoughts returns shared thought (after generation)
        # Fifth call: get_task_by_id returns task again (for refetch)
        # Sixth call: get_thoughts returns empty (final status check)
        mock_persistence.get_task_by_id.return_value = sample_task
        mock_persistence.get_thoughts_by_task_id.side_effect = [
            [],  # Shared thoughts check (before generation)
            [],  # Local thoughts check (before generation)
            [shared_thought],  # Shared thoughts after generation
            [],  # Final status check (thoughts moved to local occurrence)
        ]

        # Mock thought manager to generate 1 thought
        shutdown_processor.thought_manager.generate_seed_thoughts = Mock(return_value=1)

        # Execute
        await shutdown_processor.process(round_number=1)

        # Verify transfer was called
        mock_transfer.assert_called_once_with(
            thought_id="shared_thought_123",
            from_occurrence_id="__shared__",
            to_occurrence_id="default",
            time_service=shutdown_processor._time_service,
            audit_service=shutdown_processor.audit_service,
        )


class TestMultiOccurrenceScenarios:
    """Tests for multi-occurrence coordination scenarios"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.get_latest_shared_task")
    async def test_shutdown_already_decided_by_another_occurrence(
        self,
        mock_get_latest,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test when another occurrence already decided shutdown (lines 289-296)"""
        # Setup
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Another occurrence already completed shutdown
        mock_is_completed.return_value = True

        existing_task = Task(
            task_id="existing_shutdown_123",
            channel_id="test_channel",
            description="Shutdown decided by another occurrence",
            priority=10,
            status=TaskStatus.COMPLETED,
            created_at="2025-10-07T11:00:00+00:00",
            updated_at="2025-10-07T11:30:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_get_latest.return_value = existing_task

        # Execute
        await shutdown_processor._create_shutdown_task()

        # Verify
        assert shutdown_processor.shutdown_task == existing_task
        assert shutdown_processor.shutdown_task.task_id == "existing_shutdown_123"

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_monitoring_occurrence_watches_claimed_task(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """Test monitoring occurrence scenario - MULTI-OCCURRENCE agent"""
        # CRITICAL: Use multi-occurrence ID (not "default") to test monitoring behavior
        shutdown_processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="occurrence-2",  # Multi-occurrence, not "default"
        )
        
        # Setup
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        mock_is_completed.return_value = False

        # Another occurrence already claimed it (was_created=False)
        claimed_task = Task(
            task_id="claimed_shutdown_123",
            channel_id="test_channel",
            description="Shutdown claimed by another occurrence",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_try_claim.return_value = (claimed_task, False)  # was_created=False

        # Execute
        await shutdown_processor._create_shutdown_task()

        # Verify
        assert shutdown_processor.shutdown_task == claimed_task
        assert shutdown_processor.is_claiming_occurrence is False  # Monitoring only

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_monitoring_occurrence_skips_thought_processing(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
    ):
        """Test that monitoring occurrence doesn't process thoughts"""
        # Setup - this is a monitoring occurrence
        shutdown_processor.shutdown_task = sample_task
        shutdown_processor.is_claiming_occurrence = False  # Monitoring occurrence

        # Execute
        await shutdown_processor._process_shutdown_thoughts()

        # Verify - should not call get_thoughts or process anything
        mock_persistence.get_thoughts_by_task_id.assert_not_called()


class TestChannelIdResolution:
    """Tests for channel ID resolution from multiple sources"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_channel_id_from_get_primary_channel_id(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test getting channel ID from runtime.get_primary_channel_id (lines 302-303)"""
        # Setup
        mock_is_completed.return_value = False
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # CRITICAL: Delete startup_channel_id so hasattr returns False,
        # then add get_primary_channel_id
        delattr(shutdown_processor.runtime, "startup_channel_id")
        shutdown_processor.runtime.get_primary_channel_id = Mock(return_value="primary_channel_789")

        # Also remove communication_bus to ensure runtime method is tried
        shutdown_processor.services.communication_bus = None

        task_with_channel = Task(
            task_id="test_primary_123",
            channel_id="primary_channel_789",
            description="Test",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
        )
        mock_try_claim.return_value = (task_with_channel, True)

        # Execute
        await shutdown_processor._create_shutdown_task()

        # Verify
        shutdown_processor.runtime.get_primary_channel_id.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_channel_id_comm_bus_exception(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test handling exception from communication bus (lines 318-319)"""
        # Setup
        mock_is_completed.return_value = False
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Remove runtime channel sources
        shutdown_processor.runtime.startup_channel_id = None
        shutdown_processor.runtime.get_primary_channel_id = None

        # Make communication bus raise exception
        mock_comm_bus = Mock()
        mock_comm_bus.get_default_channel = AsyncMock(side_effect=Exception("Bus error"))
        shutdown_processor.services.communication_bus = mock_comm_bus

        task_with_empty_channel = Task(
            task_id="test_empty_123",
            channel_id="",
            description="Test",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
        )
        mock_try_claim.return_value = (task_with_empty_channel, True)

        # Execute - should not raise
        await shutdown_processor._create_shutdown_task()

        # Verify - should succeed with empty channel
        assert shutdown_processor.shutdown_task is not None

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_channel_id_empty_fallback(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test empty string fallback when no channel available (lines 323-324)"""
        # Setup
        mock_is_completed.return_value = False
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Remove all channel sources
        shutdown_processor.runtime.startup_channel_id = None
        shutdown_processor.runtime.get_primary_channel_id = None
        shutdown_processor.services.communication_bus = None

        task_with_empty_channel = Task(
            task_id="test_empty_fallback_123",
            channel_id="",
            description="Test",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
        )
        mock_try_claim.return_value = (task_with_empty_channel, True)

        # Execute
        await shutdown_processor._create_shutdown_task()

        # Verify
        assert shutdown_processor.shutdown_task is not None


class TestEmergencyShutdownWarnings:
    """Tests for emergency shutdown edge cases"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_emergency_shutdown_without_requester_id(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test emergency shutdown without requester ID (line 284)"""
        # Setup
        mock_is_completed.return_value = False
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Emergency"
        shutdown_manager.is_force_shutdown.return_value = True
        shutdown_manager.get_requester_wa_id.return_value = None  # No requester ID
        mock_get_shutdown_manager.return_value = shutdown_manager

        emergency_task = Task(
            task_id="emergency_no_requester_123",
            channel_id="test_channel",
            description="EMERGENCY shutdown",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
        )
        mock_try_claim.return_value = (emergency_task, True)

        # Execute - should succeed with warning
        await shutdown_processor._create_shutdown_task()

        # Verify
        assert shutdown_processor.shutdown_task is not None


class TestSystemWASigning:
    """Tests for system WA signing success path"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_system_wa_signing_success(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test successful system WA signing (lines 388-394)"""
        # Setup
        mock_is_completed.return_value = False
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        task = Task(
            task_id="signed_task_123",
            channel_id="test_channel",
            description="Test",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
        )
        mock_try_claim.return_value = (task, True)

        # Mock successful system WA signing
        shutdown_processor.auth_service.get_system_wa_id = AsyncMock(return_value="system_wa_123")
        shutdown_processor.auth_service.sign_task = AsyncMock(
            return_value=("signature_abc", "2025-10-07T12:00:00+00:00")
        )

        # Execute
        await shutdown_processor._create_shutdown_task()

        # Verify
        shutdown_processor.auth_service.get_system_wa_id.assert_called_once()
        shutdown_processor.auth_service.sign_task.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_system_wa_signing_no_system_wa(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        shutdown_processor,
    ):
        """Test warning when no system WA available (line 394)"""
        # Setup
        mock_is_completed.return_value = False
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Test"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        task = Task(
            task_id="unsigned_task_123",
            channel_id="test_channel",
            description="Test",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
        )
        mock_try_claim.return_value = (task, True)

        # Mock system WA not available (returns None)
        shutdown_processor.auth_service.get_system_wa_id = AsyncMock(return_value=None)

        # Execute - should succeed with warning
        await shutdown_processor._create_shutdown_task()

        # Verify
        shutdown_processor.auth_service.get_system_wa_id.assert_called_once()
        # sign_task should NOT be called when system_wa_id is None
        shutdown_processor.auth_service.sign_task.assert_not_called()


class TestRejectionReasonExtraction:
    """Tests for rejection reason extraction edge cases"""

    def test_extract_rejection_reason_non_dict_params(
        self,
        shutdown_processor,
    ):
        """Test extraction when action_params is not a dict (line 422)"""
        # Setup
        action = Mock()
        action.action_params = "not a dict"  # Non-dict params

        # Execute
        result = shutdown_processor._extract_rejection_reason(action)

        # Verify
        assert result == "No reason provided"

    def test_extract_rejection_reason_none_value(
        self,
        shutdown_processor,
    ):
        """Test extraction when reason is None (line 422)"""
        # Setup
        action = Mock()
        action.action_params = {"reason": None}

        # Execute
        result = shutdown_processor._extract_rejection_reason(action)

        # Verify
        assert result == "No reason provided"


class TestThoughtProcessingNoResult:
    """Tests for thought processing when no result returned"""

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_process_shutdown_thought_no_result(
        self,
        mock_persistence,
        shutdown_processor,
        sample_task,
        sample_thought,
    ):
        """Test handling when process_thought_item returns None (line 526)"""
        # Setup
        shutdown_processor.shutdown_task = sample_task
        shutdown_processor.is_claiming_occurrence = True
        sample_thought.status = ThoughtStatus.PENDING

        mock_persistence.get_thoughts_by_task_id.return_value = [sample_thought]
        mock_persistence.get_task_by_id.return_value = sample_task

        # Mock process_thought_item to return None
        shutdown_processor.process_thought_item = AsyncMock(return_value=None)

        # Execute
        await shutdown_processor._process_shutdown_thoughts()

        # Verify - should handle gracefully without crashing
        shutdown_processor.process_thought_item.assert_called_once()
        # Dispatch should NOT be called when result is None
        shutdown_processor.action_dispatcher.dispatch.assert_not_called()


# ============================================================================
# COMPREHENSIVE DEPLOYMENT SCENARIO TESTS
# ============================================================================


class TestDeploymentScenarios:
    """
    Comprehensive tests for all 4 deployment scenarios:
    1. Single-occurrence SQLite (e.g., Sage)
    2. Single-occurrence PostgreSQL
    3. Multi-occurrence SQLite (claiming)
    4. Multi-occurrence SQLite (monitoring)
    5. Multi-occurrence PostgreSQL (claiming)
    6. Multi-occurrence PostgreSQL (monitoring)
    
    Tests the critical P0 fix for single-occurrence shutdown loop bug.
    """

    # ------------------------------------------------------------------------
    # Single-Occurrence Scenarios
    # ------------------------------------------------------------------------

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.persistence.models.tasks.update_task_context_and_signing")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_single_occurrence_sqlite_first_run(
        self,
        mock_persistence,
        mock_update_context,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """
        Scenario 1A: Single-occurrence SQLite agent (Sage) - First run
        
        This is the normal case where Sage creates a shutdown task for the first time.
        """
        # Setup processor for single-occurrence
        processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="default",  # Single-occurrence identifier
        )

        # Setup mocks
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "CD update"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # First run - no existing completed task
        mock_is_completed.return_value = False

        new_task = Task(
            task_id="SHUTDOWN_SHARED_abc123",
            channel_id="test_channel",
            description="System shutdown requested: CD update",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_try_claim.return_value = (new_task, True)  # Created new task
        mock_persistence.update_task_status.return_value = None

        # Execute
        await processor._create_shutdown_task()

        # Verify
        assert processor.shutdown_task is not None
        assert processor.shutdown_task.task_id == "SHUTDOWN_SHARED_abc123"
        assert processor.is_claiming_occurrence is True
        mock_is_completed.assert_called_once_with("shutdown", within_hours=1)
        mock_try_claim.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.get_latest_shared_task")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_single_occurrence_sqlite_prevents_loop(
        self,
        mock_persistence,
        mock_get_latest,
        mock_is_completed,
        mock_get_shutdown_manager,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """
        Scenario 1B: Single-occurrence SQLite agent (Sage) - Second run
        
        CRITICAL TEST: This tests the P0 fix for the shutdown loop bug.
        
        Before fix: Agent would find its own completed task and return early,
                   causing infinite loop.
        After fix: _process_shutdown() checks `if not self.shutdown_task` before
                   calling _create_shutdown_task(), preventing the check entirely.
        """
        # Setup processor for single-occurrence
        processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="default",
        )

        # Simulate first run already created task
        existing_task = Task(
            task_id="SHUTDOWN_SHARED_abc123",
            channel_id="test_channel",
            description="System shutdown requested: CD update",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:05:00+00:00",
            agent_occurrence_id="__shared__",
        )
        processor.shutdown_task = existing_task  # Already set from first run
        
        # Mock persistence calls
        mock_persistence.get_task_by_id.return_value = existing_task
        mock_persistence.get_thoughts_by_task_id.return_value = []

        # Setup shutdown manager
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "CD update"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Mock that task is completed (should not be checked)
        mock_is_completed.return_value = True
        mock_get_latest.return_value = existing_task

        # Execute - Call the full process method, not _create_shutdown_task directly
        # This properly tests the fix at line 194: `if not self.shutdown_task:`
        result = await processor.process(round_number=2)

        # Verify - P0 FIX: Should NOT call is_shared_task_completed or _create_shutdown_task
        # because _process_shutdown checks `if not self.shutdown_task` first (line 194)
        mock_is_completed.assert_not_called()
        mock_get_latest.assert_not_called()
        
        # Should still process normally without creating new task
        assert result is not None

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.persistence.models.tasks.update_task_context_and_signing")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_single_occurrence_postgresql(
        self,
        mock_persistence,
        mock_update_context,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """
        Scenario 2: Single-occurrence PostgreSQL agent
        
        Same behavior as SQLite - should not loop when finding own completed task.
        """
        # Setup processor for single-occurrence PostgreSQL
        processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="default",  # Single-occurrence
        )

        # Setup mocks
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Maintenance"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        mock_is_completed.return_value = False

        new_task = Task(
            task_id="SHUTDOWN_SHARED_xyz789",
            channel_id="test_channel",
            description="System shutdown requested: Maintenance",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_try_claim.return_value = (new_task, True)
        mock_persistence.update_task_status.return_value = None

        # Execute
        await processor._create_shutdown_task()

        # Verify
        assert processor.shutdown_task is not None
        assert processor.is_claiming_occurrence is True
        mock_try_claim.assert_called_once()

    # ------------------------------------------------------------------------
    # Multi-Occurrence Claiming Scenarios
    # ------------------------------------------------------------------------

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.persistence.models.tasks.update_task_context_and_signing")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_multi_occurrence_sqlite_claiming(
        self,
        mock_persistence,
        mock_update_context,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """
        Scenario 3: Multi-occurrence SQLite agent - Claiming occurrence
        
        First occurrence to request shutdown claims the shared task.
        """
        # Setup processor for multi-occurrence
        processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="occurrence-1",  # Multi-occurrence identifier
        )

        # Setup mocks
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Rolling restart"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # No existing completed task
        mock_is_completed.return_value = False

        # This occurrence claims the task
        new_task = Task(
            task_id="SHUTDOWN_SHARED_multi123",
            channel_id="test_channel",
            description="System shutdown requested: Rolling restart",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_try_claim.return_value = (new_task, True)  # was_created=True
        mock_persistence.update_task_status.return_value = None

        # Execute
        await processor._create_shutdown_task()

        # Verify
        assert processor.shutdown_task is not None
        assert processor.is_claiming_occurrence is True  # This occurrence claimed it
        mock_try_claim.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_multi_occurrence_sqlite_monitoring(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """
        Scenario 4: Multi-occurrence SQLite agent - Monitoring occurrence
        
        Second occurrence arrives after first has claimed, becomes monitoring occurrence.
        """
        # Setup processor for multi-occurrence
        processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="occurrence-2",  # Different occurrence
        )

        # Setup mocks
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Rolling restart"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # No existing completed task
        mock_is_completed.return_value = False

        # Another occurrence already claimed it
        claimed_task = Task(
            task_id="SHUTDOWN_SHARED_multi123",
            channel_id="test_channel",
            description="System shutdown requested: Rolling restart",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_try_claim.return_value = (claimed_task, False)  # was_created=False

        # Execute
        await processor._create_shutdown_task()

        # Verify
        assert processor.shutdown_task is not None
        assert processor.is_claiming_occurrence is False  # Monitoring occurrence
        mock_try_claim.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.persistence.models.tasks.update_task_context_and_signing")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_multi_occurrence_postgresql_claiming(
        self,
        mock_persistence,
        mock_update_context,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """
        Scenario 5: Multi-occurrence PostgreSQL agent (Scout) - Claiming occurrence
        
        Production scenario: Scout occurrence claims shared task in PostgreSQL.
        """
        # Setup processor for multi-occurrence PostgreSQL
        processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="scout-001",  # Scout occurrence
        )

        # Setup mocks
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "CD update to 1.5.0"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        mock_is_completed.return_value = False

        # Scout-001 claims the task
        new_task = Task(
            task_id="SHUTDOWN_SHARED_scout456",
            channel_id="test_channel",
            description="System shutdown requested: CD update to 1.5.0",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_try_claim.return_value = (new_task, True)
        mock_persistence.update_task_status.return_value = None

        # Execute
        await processor._create_shutdown_task()

        # Verify
        assert processor.shutdown_task is not None
        assert processor.is_claiming_occurrence is True
        mock_try_claim.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    async def test_multi_occurrence_postgresql_monitoring(
        self,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """
        Scenario 6: Multi-occurrence PostgreSQL agent (Scout) - Monitoring occurrence
        
        Production scenario: Scout-002 and Scout-003 monitor Scout-001's decision.
        """
        # Setup processor for multi-occurrence PostgreSQL
        processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="scout-002",  # Monitoring occurrence
        )

        # Setup mocks
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "CD update to 1.5.0"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        mock_is_completed.return_value = False

        # Scout-001 already claimed it
        claimed_task = Task(
            task_id="SHUTDOWN_SHARED_scout456",
            channel_id="test_channel",
            description="System shutdown requested: CD update to 1.5.0",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_try_claim.return_value = (claimed_task, False)  # was_created=False

        # Execute
        await processor._create_shutdown_task()

        # Verify
        assert processor.shutdown_task is not None
        assert processor.is_claiming_occurrence is False  # Monitoring only
        mock_try_claim.assert_called_once()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.get_latest_shared_task")
    async def test_multi_occurrence_finds_existing_decision(
        self,
        mock_get_latest,
        mock_is_completed,
        mock_get_shutdown_manager,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """
        Scenario 7: Multi-occurrence agent finds existing completed decision
        
        Late-arriving occurrence finds that another occurrence already completed
        the shutdown decision.
        """
        # Setup processor for multi-occurrence
        processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="occurrence-3",
        )

        # Setup mocks
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "Update"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # Another occurrence already completed shutdown
        mock_is_completed.return_value = True

        existing_task = Task(
            task_id="SHUTDOWN_SHARED_completed",
            channel_id="test_channel",
            description="System shutdown requested: Update",
            priority=10,
            status=TaskStatus.COMPLETED,
            created_at="2025-10-07T11:50:00+00:00",
            updated_at="2025-10-07T11:55:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_get_latest.return_value = existing_task

        # Execute
        await processor._create_shutdown_task()

        # Verify
        assert processor.shutdown_task == existing_task
        mock_is_completed.assert_called_once_with("shutdown", within_hours=1)
        mock_get_latest.assert_called_once_with("shutdown", within_hours=1)

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_monitoring_occurrence_does_not_process_thoughts(
        self,
        mock_persistence,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """
        Scenario 8: Monitoring occurrence skips thought processing
        
        Only the claiming occurrence should process thoughts. Monitoring occurrences
        should only watch the task status.
        """
        # Setup processor as monitoring occurrence
        processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="occurrence-2",
        )

        # Set up as monitoring occurrence
        processor.shutdown_task = Task(
            task_id="SHUTDOWN_SHARED_test",
            channel_id="test_channel",
            description="Test",
            priority=10,
            status=TaskStatus.ACTIVE,
            created_at="2025-10-07T12:00:00+00:00",
            updated_at="2025-10-07T12:00:00+00:00",
            agent_occurrence_id="__shared__",
        )
        processor.is_claiming_occurrence = False

        # Execute
        await processor._process_shutdown_thoughts()

        # Verify - should not call get_thoughts_by_task_id
        mock_persistence.get_thoughts_by_task_id.assert_not_called()

    @pytest.mark.asyncio
    @patch("ciris_engine.logic.processors.states.shutdown_processor.get_shutdown_manager")
    @patch("ciris_engine.logic.persistence.models.tasks.is_shared_task_completed")
    @patch("ciris_engine.logic.persistence.models.tasks.try_claim_shared_task")
    @patch("ciris_engine.logic.persistence.models.tasks.update_task_context_and_signing")
    @patch("ciris_engine.logic.processors.states.shutdown_processor.persistence")
    async def test_single_occurrence_claims_existing_task(
        self,
        mock_persistence,
        mock_update_context,
        mock_try_claim,
        mock_is_completed,
        mock_get_shutdown_manager,
        mock_config_accessor,
        mock_thought_processor,
        mock_action_dispatcher,
        mock_services,
        mock_time_service,
        mock_runtime,
        mock_auth_service,
    ):
        """
        CRITICAL P0 FIX TEST: Single-occurrence agent claims existing task
        
        This tests the ACTUAL bug that caused Sage's 7-hour shutdown loop:
        - Task already exists in database (from previous run/restart)
        - try_claim_shared_task returns was_created=False
        - Single-occurrence agent MUST still claim and process (not monitor)
        
        Before fix: Agent would set is_claiming_occurrence=False and loop forever
        After fix: Agent recognizes it's single-occurrence and claims anyway
        """
        # Setup processor for single-occurrence
        processor = ShutdownProcessor(
            config_accessor=mock_config_accessor,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            time_service=mock_time_service,
            runtime=mock_runtime,
            auth_service=mock_auth_service,
            agent_occurrence_id="default",  # Single-occurrence identifier
        )

        # Setup mocks
        shutdown_manager = Mock()
        shutdown_manager.get_shutdown_reason.return_value = "CD update"
        shutdown_manager.is_force_shutdown.return_value = False
        mock_get_shutdown_manager.return_value = shutdown_manager

        # No existing completed task
        mock_is_completed.return_value = False

        # CRITICAL: Task already exists (was_created=False)
        # This simulates the bug condition: task persisted from previous run
        existing_task = Task(
            task_id="SHUTDOWN_SHARED_20251029",
            channel_id="test_channel",
            description="System shutdown requested: CD update",
            priority=10,
            status=TaskStatus.PENDING,
            created_at="2025-10-29T17:00:00+00:00",
            updated_at="2025-10-29T17:00:00+00:00",
            agent_occurrence_id="__shared__",
        )
        mock_try_claim.return_value = (existing_task, False)  # was_created=False!
        mock_persistence.update_task_status.return_value = None

        # Execute
        await processor._create_shutdown_task()

        # Verify - P0 FIX: Single-occurrence MUST claim even though was_created=False
        assert processor.shutdown_task is not None
        assert processor.shutdown_task.task_id == "SHUTDOWN_SHARED_20251029"
        assert processor.is_claiming_occurrence is True  # CRITICAL: Must be claiming, not monitoring!
        
        # Should still process normally (not return early)
        mock_try_claim.assert_called_once()
        mock_update_context.assert_called_once()  # Should update context and sign
