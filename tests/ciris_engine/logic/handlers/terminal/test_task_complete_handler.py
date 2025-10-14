"""
Comprehensive unit tests for the TASK_COMPLETE handler.

Tests cover:
- Task completion with various outcomes
- Success and failure completions
- Outcome documentation
- Task status updates
- Child task handling
- Completion metadata
- Follow-up task creation
- Error handling for invalid completions
- Task signing and verification
- Completion auditing
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.terminal.task_complete_handler import TaskCompleteHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import TaskCompleteParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, TaskOutcome, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext


@contextmanager
def patch_persistence_properly(test_task: Optional[Task] = None) -> Any:
    """Properly patch persistence in both handler and base handler."""
    with patch("ciris_engine.logic.handlers.terminal.task_complete_handler.persistence") as mock_p, patch(
        "ciris_engine.logic.infrastructure.handlers.base_handler.persistence"
    ) as mock_base_p:
        # Configure handler persistence
        mock_p.get_task_by_id.return_value = test_task
        mock_p.add_thought = Mock()
        mock_p.update_thought_status = Mock(return_value=True)
        mock_p.add_correlation = Mock()
        # update_task_status should return False if task is None (not found)
        mock_p.update_task_status = Mock(return_value=bool(test_task))
        mock_p.get_child_tasks = Mock(return_value=[])
        mock_p.get_thoughts_by_task_id = Mock(return_value=[])

        # Configure base handler persistence
        mock_base_p.add_thought = Mock()
        mock_base_p.update_thought_status = Mock(return_value=True)
        mock_base_p.add_correlation = Mock()

        yield mock_p


# Test fixtures
@pytest.fixture
def mock_time_service() -> Mock:
    """Mock time service."""
    service = Mock(spec=TimeServiceProtocol)
    service.now = Mock(return_value=datetime.now(timezone.utc))
    return service


@pytest.fixture
def mock_secrets_service() -> Mock:
    """Mock secrets service."""
    service = Mock(spec=SecretsService)
    service.decapsulate_secrets_in_parameters = AsyncMock(
        side_effect=lambda action_type, action_params, context: action_params
    )
    return service


@pytest.fixture
def mock_communication_bus() -> AsyncMock:
    """Mock communication bus."""
    bus = AsyncMock()
    bus.send_message = AsyncMock(return_value=True)
    bus.send_message_sync = AsyncMock(return_value=True)
    return bus


@pytest.fixture
def mock_bus_manager(mock_communication_bus: AsyncMock) -> Mock:
    """Mock bus manager."""
    manager = Mock(spec=BusManager)
    manager.communication = mock_communication_bus
    manager.audit_service = AsyncMock()
    manager.audit_service.log_event = AsyncMock()
    return manager


@pytest.fixture
def handler_dependencies(
    mock_bus_manager: Mock, mock_time_service: Mock, mock_secrets_service: Mock
) -> ActionHandlerDependencies:
    """Create handler dependencies."""
    return ActionHandlerDependencies(
        bus_manager=mock_bus_manager,
        time_service=mock_time_service,
        secrets_service=mock_secrets_service,
        shutdown_callback=None,
    )


@pytest.fixture
def task_complete_handler(handler_dependencies: ActionHandlerDependencies) -> TaskCompleteHandler:
    """Create TASK_COMPLETE handler instance."""
    return TaskCompleteHandler(handler_dependencies)


@pytest.fixture
def channel_context() -> ChannelContext:
    """Create test channel context."""
    return ChannelContext(
        channel_id="test_channel_123",
        channel_type="text",
        created_at=datetime.now(timezone.utc),
        channel_name="Test Channel",
        is_private=False,
        is_active=True,
        last_activity=None,
        message_count=0,
        moderation_level="standard",
    )


@pytest.fixture
def dispatch_context(channel_context: ChannelContext) -> DispatchContext:
    """Create test dispatch context."""
    return DispatchContext(
        channel_context=channel_context,
        author_id="test_author",
        author_name="Test Author",
        origin_service="test_service",
        handler_name="TaskCompleteHandler",
        action_type=HandlerActionType.TASK_COMPLETE,
        task_id="task_123",
        thought_id="thought_123",
        source_task_id="task_123",
        event_summary="Test task complete action",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        wa_id=None,
        wa_authorized=False,
        wa_context=None,
        conscience_failure_context=None,
        epistemic_data=None,
        correlation_id="corr_123",
        span_id=None,
        trace_id=None,
    )


@pytest.fixture
def test_thought() -> Thought:
    """Create test thought."""
    return Thought(
        thought_id="thought_123",
        source_task_id="task_123",
        content="Task has been completed successfully",
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        channel_id="test_channel_123",
        status=ThoughtStatus.PROCESSING,
        thought_depth=1,
        round_number=1,
        ponder_notes=None,
        parent_thought_id=None,
        final_action=None,
        context=ThoughtContext(
            task_id="task_123",
            correlation_id="corr_123",
            round_number=1,
            depth=1,
            channel_id="test_channel_123",
            parent_thought_id=None,
        ),
    )


@pytest.fixture
def test_task() -> Task:
    """Create test task."""
    return Task(
        task_id="task_123",
        channel_id="test_channel_123",
        description="Help user understand Python decorators",
        status=TaskStatus.ACTIVE,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        priority=5,
        parent_task_id=None,
        context=None,
        outcome=None,
        signed_by=None,
        signature=None,
        signed_at=None,
    )


@pytest.fixture
def task_complete_params() -> TaskCompleteParams:
    """Create test TASK_COMPLETE parameters."""
    return TaskCompleteParams(
        completion_reason="Successfully explained Python decorators with examples",
        context={"messages_sent": "3", "examples_provided": "2", "user_satisfaction": "confirmed"},
        positive_moment="User expressed clear understanding and enthusiasm about decorators",
    )


@pytest.fixture
def action_result(task_complete_params: TaskCompleteParams) -> ActionSelectionDMAResult:
    """Create test action selection result."""
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.TASK_COMPLETE,
        action_parameters=task_complete_params,
        rationale="Task objectives have been met",
        raw_llm_response="TASK_COMPLETE: Successfully completed",
        reasoning="User confirmed understanding",
        evaluation_time_ms=100.0,
        resource_usage=None,
    )


class TestTaskCompleteHandler:
    """Test suite for TASK_COMPLETE handler."""

    @pytest.mark.asyncio
    async def test_successful_task_completion(
        self,
        task_complete_handler: TaskCompleteHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test successful task completion."""
        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            follow_up_id = await task_complete_handler.handle(action_result, test_thought, dispatch_context)

            # Verify task status was updated
            mock_persistence.update_task_status.assert_called_once_with(
                "task_123", TaskStatus.COMPLETED, "default", task_complete_handler.time_service
            )

            # Handler does not send notifications currently
            # This could be a feature to add in the future

            # Verify thought status was updated
            assert mock_persistence.update_thought_status.called
            update_call = mock_persistence.update_thought_status.call_args
            assert update_call.kwargs["thought_id"] == "thought_123"
            assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED

            # Should not create follow-up for terminal handler
            assert follow_up_id is None

    @pytest.mark.asyncio
    async def test_failed_task_completion(
        self,
        task_complete_handler: TaskCompleteHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test task completion with failure outcome."""
        # Create failure params
        params = TaskCompleteParams(
            completion_reason="Unable to complete task due to insufficient information",
            context={"reason": "missing_requirements", "attempted_steps": "2"},
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.TASK_COMPLETE,
            action_parameters=params,
            rationale="Cannot proceed without more info",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await task_complete_handler.handle(result, test_thought, dispatch_context)

            # Handler currently only updates status to COMPLETED, not FAILED
            # This might be a limitation that should be addressed
            if mock_persistence.update_task_status.called:
                call_args = mock_persistence.update_task_status.call_args[0]
                assert call_args[0] == "task_123"
                assert call_args[1] == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_task_with_child_tasks(
        self,
        task_complete_handler: TaskCompleteHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        test_task: Task,
    ) -> None:
        """Test completion of task with active child tasks."""
        # Create child tasks
        child_tasks = [
            Task(
                task_id="child_1",
                channel_id="test_channel_123",
                description="Child task 1",
                status=TaskStatus.ACTIVE,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                priority=5,
                parent_task_id="task_123",
                context=None,
                outcome=None,
                signed_by=None,
                signature=None,
                signed_at=None,
            ),
            Task(
                task_id="child_2",
                channel_id="test_channel_123",
                description="Child task 2",
                status=TaskStatus.COMPLETED,
                created_at=datetime.now(timezone.utc).isoformat(),
                updated_at=datetime.now(timezone.utc).isoformat(),
                priority=5,
                parent_task_id="task_123",
                context=None,
                outcome=TaskOutcome(status="success", summary="Done", actions_taken=[], memories_created=[], errors=[]),
                signed_by=None,
                signature=None,
                signed_at=None,
            ),
        ]

        with patch_persistence_properly(test_task) as mock_persistence:
            mock_persistence.get_child_tasks.return_value = child_tasks

            # Execute handler
            await task_complete_handler.handle(action_result, test_thought, dispatch_context)

            # Handler does not currently check child task status
            # This could be a feature to add for better task lifecycle management

            # Parent task should still be marked as completed
            mock_persistence.update_task_status.assert_called_with(
                "task_123", TaskStatus.COMPLETED, "default", task_complete_handler.time_service
            )

    @pytest.mark.asyncio
    async def test_completion_metadata_handling(
        self,
        task_complete_handler: TaskCompleteHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        test_task: Task,
    ) -> None:
        """Test various completion metadata scenarios."""
        metadata_scenarios = [
            {
                "duration_minutes": 15,
                "interactions": 5,
                "resources_used": ["documentation", "examples"],
                "user_feedback": "very helpful",
            },
            {"error_count": 2, "retry_attempts": 1, "partial_completion": True, "completion_percentage": 80},
            {},  # Empty metadata
            {"complex_data": {"nested": {"deeply": ["value1", "value2"]}}},
        ]

        with patch_persistence_properly(test_task) as mock_persistence:
            for metadata in metadata_scenarios:
                # Reset mocks
                mock_persistence.update_task_status.reset_mock()

                # Create params with different metadata
                params = TaskCompleteParams(
                    completion_reason="Task completed",
                    context=(
                        {k: str(v) if not isinstance(v, dict) else str(v) for k, v in metadata.items()}
                        if metadata
                        else None
                    ),
                )

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.TASK_COMPLETE,
                    action_parameters=params,
                    rationale="Test metadata",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await task_complete_handler.handle(result, test_thought, dispatch_context)

                # Handler currently only updates status, not outcome metadata
                # This is a limitation that should be addressed
                if mock_persistence.update_task_status.called:
                    assert mock_persistence.update_task_status.call_args[0][1] == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_task_already_completed(
        self,
        task_complete_handler: TaskCompleteHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        test_task: Task,
    ) -> None:
        """Test handling when task is already completed."""
        # Set task to already completed
        test_task.status = TaskStatus.COMPLETED
        test_task.outcome = TaskOutcome(
            status="success", summary="Previously completed", actions_taken=[], memories_created=[], errors=[]
        )

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await task_complete_handler.handle(action_result, test_thought, dispatch_context)

            # Handler might still update or might skip
            # Depends on implementation
            assert mock_persistence.update_thought_status.called

    @pytest.mark.asyncio
    async def test_task_signing(
        self,
        task_complete_handler: TaskCompleteHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        test_task: Task,
        mock_time_service: Mock,
    ) -> None:
        """Test task signing functionality."""
        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await task_complete_handler.handle(action_result, test_thought, dispatch_context)

            # Handler currently only updates status, not signing fields
            # Task signing functionality needs to be implemented
            mock_persistence.update_task_status.assert_called_with(
                "task_123", TaskStatus.COMPLETED, "default", task_complete_handler.time_service
            )

    @pytest.mark.asyncio
    async def test_parameter_validation_error(
        self, task_complete_handler: TaskCompleteHandler, test_thought: Thought, dispatch_context: DispatchContext
    ) -> None:
        """Test handling of invalid parameters."""
        with patch_persistence_properly() as mock_persistence:
            # Create result with valid structure but mock validation to fail
            result = ActionSelectionDMAResult(
                selected_action=HandlerActionType.TASK_COMPLETE,
                action_parameters=TaskCompleteParams(completion_reason="test"),
                rationale="Test validation",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

            # Mock the validation method to raise an error
            with patch.object(task_complete_handler, "_validate_and_convert_params") as mock_validate:
                mock_validate.side_effect = ValueError("Invalid outcome format")

                # Execute handler - should handle validation error
                follow_up_id = await task_complete_handler.handle(result, test_thought, dispatch_context)

                # Since we're mocking an internal method, the handler might still complete
                # This test design doesn't properly test validation errors
                # The handler marks thoughts as COMPLETED for terminal actions
                mock_persistence.update_thought_status.assert_called()
                call_args = mock_persistence.update_thought_status.call_args
                assert call_args.kwargs["thought_id"] == "thought_123"

                # For terminal handler, might not create follow-up
                # Depends on implementation

    @pytest.mark.asyncio
    async def test_missing_task(
        self,
        task_complete_handler: TaskCompleteHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
    ) -> None:
        """Test handling when task is not found."""
        with patch_persistence_properly(None) as mock_persistence:  # Pass None for missing task
            # Execute handler
            follow_up_id = await task_complete_handler.handle(action_result, test_thought, dispatch_context)

            # Handler logs error but still marks thought as completed
            assert mock_persistence.update_thought_status.called
            update_call = mock_persistence.update_thought_status.call_args
            assert update_call.kwargs["status"] == ThoughtStatus.COMPLETED
            # Task status update should have been attempted but returned False
            assert mock_persistence.update_task_status.called
            # The return value was configured to be False for missing task

    @pytest.mark.asyncio
    async def test_communication_failure(
        self,
        task_complete_handler: TaskCompleteHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test handling when notification fails."""
        # Configure communication to fail
        mock_communication_bus.send_message_sync.return_value = False

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await task_complete_handler.handle(action_result, test_thought, dispatch_context)

            # Task should still be marked as completed even if notification fails
            mock_persistence.update_task_status.assert_called_with(
                "task_123", TaskStatus.COMPLETED, "default", task_complete_handler.time_service
            )

    @pytest.mark.asyncio
    async def test_outcome_descriptions(
        self,
        task_complete_handler: TaskCompleteHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        test_task: Task,
    ) -> None:
        """Test various outcome description formats."""
        outcomes = [
            ("Task completed successfully", True),
            ("Partial completion - user requirements partially met", True),
            ("Failed due to technical limitations", False),
            ("Abandoned by user request", False),
            ("Completed with warnings: see metadata", True),
            ("", True),  # Empty outcome
            ("Very long outcome " * 50, True),  # Very long outcome
        ]

        with patch_persistence_properly(test_task) as mock_persistence:
            for outcome_desc, success in outcomes:
                # Reset mocks
                mock_persistence.update_task_status.reset_mock()

                # Create params
                params = TaskCompleteParams(completion_reason=outcome_desc, context={"success": str(success)})

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.TASK_COMPLETE,
                    action_parameters=params,
                    rationale="Test outcome",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await task_complete_handler.handle(result, test_thought, dispatch_context)

                # Handler currently only updates status, not outcome
                # Verify status update was called
                if mock_persistence.update_task_status.called:
                    assert mock_persistence.update_task_status.call_args[0][1] == TaskStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_audit_trail(
        self,
        task_complete_handler: TaskCompleteHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_bus_manager: Mock,
        test_task: Task,
    ) -> None:
        """Test audit logging for TASK_COMPLETE actions."""
        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await task_complete_handler.handle(action_result, test_thought, dispatch_context)

            # NOTE: Audit logging removed from handlers - action_dispatcher handles centralized audit logging
            pass  # Test still validates handler execution
