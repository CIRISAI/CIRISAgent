"""
Comprehensive unit tests for the REJECT handler.

Tests cover:
- Request rejection with various reasons
- Ethical rejection scenarios
- Safety rejection scenarios
- Policy violation rejections
- Rejection reason documentation
- Task status updates after rejection
- Follow-up thought creation
- Error handling for invalid rejections
- Rejection metadata and context
- Audit trail for rejections
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.control.reject_handler import RejectHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import RejectParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext


@contextmanager
def patch_persistence_properly(test_task: Optional[Task] = None) -> Any:
    """Properly patch persistence in both handler and base handler."""
    # Create a single persistence mock instance
    mock_persistence = Mock()
    mock_persistence.get_task_by_id.return_value = test_task
    mock_persistence.add_thought = Mock()
    mock_persistence.update_thought_status = Mock(return_value=True)
    mock_persistence.add_correlation = Mock()
    mock_persistence.update_task_status = Mock(return_value=True)

    with patch("ciris_engine.logic.handlers.control.reject_handler.persistence", mock_persistence), patch(
        "ciris_engine.logic.infrastructure.handlers.base_handler.persistence", mock_persistence
    ):
        yield mock_persistence


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
def reject_handler(handler_dependencies: ActionHandlerDependencies) -> RejectHandler:
    """Create REJECT handler instance."""
    return RejectHandler(handler_dependencies)


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
        handler_name="RejectHandler",
        action_type=HandlerActionType.REJECT,
        task_id="task_123",
        thought_id="thought_123",
        source_task_id="task_123",
        event_summary="Test reject action",
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
        content="Request to perform potentially harmful action",
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
        description="Generate harmful content",
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
def reject_params() -> RejectParams:
    """Create test REJECT parameters."""
    return RejectParams(
        reason="Request violates ethical guidelines",
        create_filter=True,
        filter_pattern="harmful|unethical|dangerous",
        filter_type="regex",
        filter_priority="high",
    )


@pytest.fixture
def action_result(reject_params: RejectParams) -> ActionSelectionDMAResult:
    """Create test action selection result."""
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.REJECT,
        action_parameters=reject_params,
        rationale="Request violates core ethical principles",
        raw_llm_response="REJECT: Harmful content request",
        reasoning="Cannot comply with requests for harmful content",
        evaluation_time_ms=100.0,
        resource_usage=None,
    )


class TestRejectHandler:
    """Test suite for REJECT handler."""

    @pytest.mark.asyncio
    async def test_successful_rejection_without_notification(
        self,
        reject_handler: RejectHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test successful rejection (notifications removed by design)."""
        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            follow_up_id = await reject_handler.handle(action_result, test_thought, dispatch_context)

            # Verify NO user notification is sent (removed by design)
            mock_communication_bus.send_message.assert_not_called()

            # Verify thought status was updated to FAILED (reject marks as failed)
            assert mock_persistence.update_thought_status.called
            update_call = mock_persistence.update_thought_status.call_args
            assert update_call.kwargs["thought_id"] == "thought_123"
            assert update_call.kwargs["status"] == ThoughtStatus.FAILED

            # Verify task was marked as rejected
            mock_persistence.update_task_status.assert_called_once()

            # REJECT is a terminal action - no follow-up thought should be created
            assert follow_up_id is None
            mock_persistence.add_thought.assert_not_called()

    @pytest.mark.asyncio
    async def test_rejection_without_filter(
        self,
        reject_handler: RejectHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test rejection without creating filter."""
        # Create params without filter creation
        params = RejectParams(reason="Internal policy violation", create_filter=False)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.REJECT,
            action_parameters=params,
            rationale="Policy violation",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await reject_handler.handle(result, test_thought, dispatch_context)

            # Verify NO user notification (removed by design)
            mock_communication_bus.send_message.assert_not_called()

            # Task should still be marked as rejected
            mock_persistence.update_task_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_rejection_reasons(
        self,
        reject_handler: RejectHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test different rejection reasons."""
        rejection_scenarios = [
            ("Violates beneficence principle", True, "harmful"),
            ("Could cause physical harm", True, "dangerous|harmful"),
            ("Against platform policies", False, None),
            ("Potentially illegal content", True, "illegal|prohibited"),
            ("Beyond system capabilities", False, None),
            ("Contains offensive material", True, "offensive|inappropriate"),
        ]

        with patch_persistence_properly(test_task) as mock_persistence:
            for reason, create_filter, filter_pattern in rejection_scenarios:
                # Reset mocks
                mock_persistence.update_thought_status.reset_mock()
                mock_communication_bus.send_message.reset_mock()

                # Create params for this rejection
                params = RejectParams(
                    reason=reason,
                    create_filter=create_filter,
                    filter_pattern=filter_pattern if create_filter else None,
                    filter_type="regex" if create_filter else None,
                    filter_priority="high" if create_filter else None,
                )

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.REJECT,
                    action_parameters=params,
                    rationale=f"Test: {reason}",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await reject_handler.handle(result, test_thought, dispatch_context)

                # Verify NO notification (removed by design)
                mock_communication_bus.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_filter_priorities(
        self, reject_handler: RejectHandler, test_thought: Thought, dispatch_context: DispatchContext, test_task: Task
    ) -> None:
        """Test different filter priorities."""
        priorities = ["critical", "high", "medium"]

        with patch_persistence_properly(test_task) as mock_persistence:
            for priority in priorities:
                # Reset mocks
                mock_persistence.update_thought_status.reset_mock()

                # Create params with different filter priority
                params = RejectParams(
                    reason=f"Test rejection with {priority} priority",
                    create_filter=True,
                    filter_pattern="test_pattern",
                    filter_type="regex",
                    filter_priority=priority,
                )

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.REJECT,
                    action_parameters=params,
                    rationale=f"Test {priority} priority",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await reject_handler.handle(result, test_thought, dispatch_context)

                # Verify thought was marked as failed
                assert mock_persistence.update_thought_status.called

    @pytest.mark.asyncio
    async def test_detailed_reason_included(
        self,
        reject_handler: RejectHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test that detailed reasons are included in responses."""
        detailed_reason = """This request cannot be fulfilled for the following reasons:
        1. It violates the principle of non-maleficence
        2. It could lead to harmful consequences for individuals
        3. It goes against established ethical guidelines"""

        params = RejectParams(
            reason=detailed_reason,
            create_filter=True,
            filter_pattern="harmful|unethical|dangerous",
            filter_type="regex",
            filter_priority="critical",
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.REJECT,
            action_parameters=params,
            rationale="Detailed rejection",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await reject_handler.handle(result, test_thought, dispatch_context)

            # Verify NO notification (removed by design)
            mock_communication_bus.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_task_already_rejected(
        self,
        reject_handler: RejectHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        test_task: Task,
    ) -> None:
        """Test handling when task is already rejected."""
        # Set task to already rejected
        test_task.status = TaskStatus.REJECTED

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await reject_handler.handle(action_result, test_thought, dispatch_context)

            # Handler should still update thought status
            assert mock_persistence.update_thought_status.called
            # And attempt to update task status
            assert mock_persistence.update_task_status.called

    @pytest.mark.asyncio
    async def test_parameter_validation_error(
        self, reject_handler: RejectHandler, test_thought: Thought, dispatch_context: DispatchContext
    ) -> None:
        """Test handling of invalid parameters."""
        with patch_persistence_properly() as mock_persistence:
            # Create result with valid structure but mock validation to fail
            result = ActionSelectionDMAResult(
                selected_action=HandlerActionType.REJECT,
                action_parameters=RejectParams(reason="test"),
                rationale="Test validation",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

            # Mock the validation method to raise an error
            with patch.object(reject_handler, "_validate_and_convert_params") as mock_validate:
                mock_validate.side_effect = ValueError("Invalid rejection type")

                # Execute handler - should handle validation error
                follow_up_id = await reject_handler.handle(result, test_thought, dispatch_context)

                # Verify thought was marked as failed
                mock_persistence.update_thought_status.assert_called_with(
                    thought_id="thought_123", status=ThoughtStatus.FAILED, final_action=result
                )

                # REJECT is terminal - no follow-up even on error
                assert follow_up_id is None

    @pytest.mark.asyncio
    async def test_communication_failure_during_notification(
        self,
        reject_handler: RejectHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test handling when user notification fails."""
        # Configure communication to fail
        mock_communication_bus.send_message.side_effect = Exception("Communication error")

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            follow_up_id = await reject_handler.handle(action_result, test_thought, dispatch_context)

            # Task should still be marked as rejected despite communication failure
            mock_persistence.update_task_status.assert_called_once()

            # REJECT is terminal - no follow-up even on communication failure
            assert follow_up_id is None

    @pytest.mark.asyncio
    async def test_rejection_with_filter_types(
        self,
        reject_handler: RejectHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test rejection with different filter types."""
        filter_types = ["regex", "semantic", "keyword"]

        with patch_persistence_properly(test_task) as mock_persistence:
            for filter_type in filter_types:
                # Reset mocks
                mock_persistence.update_thought_status.reset_mock()
                mock_communication_bus.send_message.reset_mock()

                params = RejectParams(
                    reason=f"Testing {filter_type} filter",
                    create_filter=True,
                    filter_pattern=f"pattern_for_{filter_type}",
                    filter_type=filter_type,
                    filter_priority="medium",
                )

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.REJECT,
                    action_parameters=params,
                    rationale=f"Test {filter_type} filter",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await reject_handler.handle(result, test_thought, dispatch_context)

                # Verify NO notification (removed by design)
                mock_communication_bus.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_audit_trail(
        self,
        reject_handler: RejectHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_bus_manager: Mock,
        test_task: Task,
    ) -> None:
        """Test audit logging for REJECT actions."""
        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await reject_handler.handle(action_result, test_thought, dispatch_context)

            # Verify audit logs were created
            audit_calls = mock_bus_manager.audit_service.log_event.call_args_list
            assert len(audit_calls) >= 2  # Start and completion

            # Reject handler calls audit twice (start and success)
            if len(audit_calls) >= 2:
                # Check start audit
                start_call = audit_calls[0]
                assert "handler_action_reject" in str(start_call[1]["event_type"]).lower()
                assert start_call[1]["event_data"]["outcome"] == "start"

                # Check completion audit
                end_call = audit_calls[-1]
                assert end_call[1]["event_data"]["outcome"] == "success"
            else:
                # At minimum, check we have a success audit
                audit_call = audit_calls[0]
                assert "handler_action_reject" in str(audit_call[1]["event_type"]).lower()

    @pytest.mark.asyncio
    async def test_handler_completes_properly(
        self,
        reject_handler: RejectHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        test_task: Task,
    ) -> None:
        """Test that reject handler completes properly."""
        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            follow_up_id = await reject_handler.handle(action_result, test_thought, dispatch_context)

            # Verify no follow-up was created (REJECT is terminal)
            assert follow_up_id is None

            # Verify thought was marked as failed
            mock_persistence.update_thought_status.assert_called_once()
            status_call = mock_persistence.update_thought_status.call_args
            assert status_call.kwargs["status"] == ThoughtStatus.FAILED

            # Verify task was updated
            mock_persistence.update_task_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_complex_filter_patterns(
        self,
        reject_handler: RejectHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_communication_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test rejection with complex filter patterns."""
        params = RejectParams(
            reason="Multiple violations: ethical, safety, and legal concerns",
            create_filter=True,
            filter_pattern="(ethical|safety|legal).*(violation|concern|issue)",
            filter_type="regex",
            filter_priority="critical",
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.REJECT,
            action_parameters=params,
            rationale="Multiple violations",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await reject_handler.handle(result, test_thought, dispatch_context)

            # Verify NO notification (removed by design)
            mock_communication_bus.send_message.assert_not_called()
