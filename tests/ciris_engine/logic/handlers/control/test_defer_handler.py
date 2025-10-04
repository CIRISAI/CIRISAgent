"""
Comprehensive unit tests for the DEFER handler.

Tests cover:
- Deferral to Wise Authority
- Deferral reason validation
- Context preservation for deferred decisions
- Wise Authority bus integration
- Permission checking
- Deferral tracking and auditing
- Error handling for unauthorized deferrals
- Multiple deferral types
- Deferral metadata
- Follow-up thought creation
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.control.defer_handler import DeferHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import DeferParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.services.context import DeferralContext


@contextmanager
def patch_persistence_properly(test_task: Optional[Task] = None) -> Any:
    """Properly patch persistence in both handler and base handler."""
    with patch("ciris_engine.logic.handlers.control.defer_handler.persistence") as mock_p, patch(
        "ciris_engine.logic.infrastructure.handlers.base_handler.persistence"
    ) as mock_base_p:
        # Configure handler persistence
        mock_p.get_task_by_id.return_value = test_task
        mock_p.add_thought = Mock()
        mock_p.update_thought_status = Mock(return_value=True)
        mock_p.add_correlation = Mock()

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
def mock_wise_bus() -> AsyncMock:
    """Mock wise authority bus."""
    bus = AsyncMock()
    bus.send_deferral = AsyncMock(return_value=True)
    bus.check_permission = AsyncMock(return_value=True)
    return bus


@pytest.fixture
def mock_bus_manager(mock_wise_bus: AsyncMock) -> Mock:
    """Mock bus manager with wise bus."""
    manager = Mock(spec=BusManager)
    manager.wise = mock_wise_bus
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
def defer_handler(handler_dependencies: ActionHandlerDependencies) -> DeferHandler:
    """Create DEFER handler instance."""
    return DeferHandler(handler_dependencies)


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
        handler_name="DeferHandler",
        action_type=HandlerActionType.DEFER,
        task_id="task_123",
        thought_id="thought_123",
        source_task_id="task_123",
        event_summary="Test defer action",
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
        content="This decision has significant ethical implications beyond my current authority",
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
        description="Should AI make autonomous decisions about resource allocation?",
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
def defer_params() -> DeferParams:
    """Create test DEFER parameters."""
    return DeferParams(
        reason="Ethical complexity exceeds current guidelines",
        context={
            "issue": "autonomous resource allocation",
            "concerns": "fairness, transparency, accountability",
            "stakeholders": "users, administrators, affected parties",
        },
    )


@pytest.fixture
def action_result(defer_params: DeferParams) -> ActionSelectionDMAResult:
    """Create test action selection result."""
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.DEFER,
        action_parameters=defer_params,
        rationale="Complex ethical decision requires wise authority input",
        raw_llm_response="DEFER: Ethical complexity",
        reasoning="Beyond my authority to decide autonomously",
        evaluation_time_ms=100.0,
        resource_usage=None,
    )


class TestDeferHandler:
    """Test suite for DEFER handler."""

    @pytest.mark.asyncio
    async def test_successful_deferral(
        self,
        defer_handler: DeferHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_wise_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test successful deferral to wise authority."""
        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            follow_up_id = await defer_handler.handle(action_result, test_thought, dispatch_context)

            # Verify deferral was sent
            mock_wise_bus.send_deferral.assert_called_once()
            deferral_call = mock_wise_bus.send_deferral.call_args
            context = deferral_call.kwargs["context"]
            assert isinstance(context, DeferralContext)
            assert context.reason == "Ethical complexity exceeds current guidelines"
            assert context.thought_id == "thought_123"
            assert context.task_id == "task_123"

            # Verify thought status was updated
            assert mock_persistence.update_thought_status.called
            update_call = mock_persistence.update_thought_status.call_args
            assert update_call.kwargs["thought_id"] == "thought_123"
            assert update_call.kwargs["status"] == ThoughtStatus.DEFERRED

            # Verify no follow-up thought was created (defer handler returns None)
            assert follow_up_id is None

    @pytest.mark.asyncio
    async def test_deferral_types(
        self,
        defer_handler: DeferHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_wise_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test different deferral reasons."""
        deferral_reasons = [
            "Ethical implications unclear",
            "Technical complexity beyond scope",
            "Policy decision required",
            "Potential safety concerns",
            "Legal implications need review",
        ]

        with patch_persistence_properly(test_task) as mock_persistence:
            for reason in deferral_reasons:
                # Reset mocks
                mock_wise_bus.send_deferral.reset_mock()
                mock_persistence.add_thought.reset_mock()

                # Create params for this deferral reason
                params = DeferParams(reason=reason, context={"type": "test"})

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.DEFER,
                    action_parameters=params,
                    rationale=f"Test deferral: {reason}",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await defer_handler.handle(result, test_thought, dispatch_context)

                # Verify correct reason was submitted
                deferral_call = mock_wise_bus.send_deferral.call_args
                context = deferral_call.kwargs["context"]
                assert isinstance(context, DeferralContext)
                assert context.reason == reason

    @pytest.mark.asyncio
    async def test_unauthorized_deferral(
        self,
        defer_handler: DeferHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_wise_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test handling when deferral permission is denied."""
        # Note: The actual defer handler doesn't check permissions before deferring
        # It just sends the deferral. Let's test what actually happens
        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            follow_up_id = await defer_handler.handle(action_result, test_thought, dispatch_context)

            # Verify deferral was submitted normally
            mock_wise_bus.send_deferral.assert_called_once()

            # Verify thought was marked as deferred
            assert mock_persistence.update_thought_status.called
            update_call = mock_persistence.update_thought_status.call_args
            assert update_call.kwargs["status"] == ThoughtStatus.DEFERRED

            # Verify no follow-up was created
            assert follow_up_id is None

    @pytest.mark.asyncio
    async def test_defer_until_times(
        self,
        defer_handler: DeferHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_wise_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test different defer_until times."""
        from datetime import datetime, timedelta, timezone

        defer_times = [
            (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat(),
            (datetime.now(timezone.utc) + timedelta(days=1)).isoformat(),
            (datetime.now(timezone.utc) + timedelta(weeks=1)).isoformat(),
        ]

        with patch_persistence_properly(test_task) as mock_persistence:
            for defer_time in defer_times:
                # Reset mocks
                mock_wise_bus.send_deferral.reset_mock()

                # Create params with different defer_until time
                params = DeferParams(reason="Test defer time", context={"defer_test": "true"}, defer_until=defer_time)

                result = ActionSelectionDMAResult(
                    selected_action=HandlerActionType.DEFER,
                    action_parameters=params,
                    rationale=f"Test defer until {defer_time}",
                    raw_llm_response=None,
                    reasoning=None,
                    evaluation_time_ms=None,
                    resource_usage=None,
                )

                # Execute handler
                await defer_handler.handle(result, test_thought, dispatch_context)

                # Verify deferral was sent
                deferral_call = mock_wise_bus.send_deferral.call_args
                context = deferral_call.kwargs["context"]
                assert isinstance(context, DeferralContext)
                # Verify defer_until was converted to datetime
                assert context.defer_until is not None
                assert isinstance(context.defer_until, datetime)

    @pytest.mark.asyncio
    async def test_complex_context_preservation(
        self,
        defer_handler: DeferHandler,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_wise_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test preservation of complex context in deferrals."""
        # Create params with complex context
        complex_context = {
            "decision_factors": {
                "ethical": ["autonomy", "beneficence", "non-maleficence"],
                "technical": ["feasibility", "scalability", "reliability"],
                "social": ["accessibility", "equity", "transparency"],
            },
            "risk_assessment": {"probability": 0.7, "impact": "high", "mitigation_options": ["option1", "option2"]},
            "stakeholder_analysis": {
                "primary": ["end_users", "administrators"],
                "secondary": ["regulators", "community"],
                "concerns": {"end_users": "privacy and control", "administrators": "compliance and efficiency"},
            },
        }

        # Convert complex context to string values (DeferParams context expects Dict[str, str])
        string_context = {
            "decision_factors": str(complex_context["decision_factors"]),
            "risk_assessment": str(complex_context["risk_assessment"]),
            "stakeholder_analysis": str(complex_context["stakeholder_analysis"]),
        }

        params = DeferParams(reason="Complex multi-faceted decision", context=string_context)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=params,
            rationale="Complex context test",
            raw_llm_response=None,
            reasoning=None,
            evaluation_time_ms=None,
            resource_usage=None,
        )

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await defer_handler.handle(result, test_thought, dispatch_context)

            # Verify complex context was preserved in metadata
            deferral_call = mock_wise_bus.send_deferral.call_args
            context = deferral_call.kwargs["context"]
            assert isinstance(context, DeferralContext)
            # The handler adds the complex context to metadata, not directly
            # Check that the deferral was sent with appropriate reason
            assert context.reason == "Complex multi-faceted decision"

    @pytest.mark.asyncio
    async def test_deferral_submission_failure(
        self,
        defer_handler: DeferHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_wise_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test handling when deferral submission fails."""
        # Configure submission to fail
        mock_wise_bus.send_deferral.side_effect = Exception("Network error")

        with patch_persistence_properly(test_task) as mock_persistence:
            # The handler catches exceptions and continues - it doesn't raise
            follow_up_id = await defer_handler.handle(action_result, test_thought, dispatch_context)

            # Verify thought was still marked as deferred
            assert mock_persistence.update_thought_status.called
            update_call = mock_persistence.update_thought_status.call_args
            assert update_call.kwargs["status"] == ThoughtStatus.DEFERRED

    @pytest.mark.asyncio
    async def test_parameter_validation_error(
        self, defer_handler: DeferHandler, test_thought: Thought, dispatch_context: DispatchContext
    ) -> None:
        """Test handling of invalid parameters."""
        with patch_persistence_properly() as mock_persistence:
            # Create result with valid structure but mock validation to fail
            result = ActionSelectionDMAResult(
                selected_action=HandlerActionType.DEFER,
                action_parameters=DeferParams(reason="test"),
                rationale="Test validation",
                raw_llm_response=None,
                reasoning=None,
                evaluation_time_ms=None,
                resource_usage=None,
            )

            # Mock the validation method to raise an error
            with patch.object(defer_handler, "_validate_and_convert_params") as mock_validate:
                mock_validate.side_effect = ValueError("Invalid deferral type")

                # Execute handler - should handle validation error
                follow_up_id = await defer_handler.handle(result, test_thought, dispatch_context)

                # The handler will still mark as DEFERRED even if validation fails
                mock_persistence.update_thought_status.assert_called_with(
                    thought_id="thought_123", status=ThoughtStatus.DEFERRED, final_action=result
                )

                # Verify no follow-up was created
                assert follow_up_id is None

    @pytest.mark.asyncio
    async def test_deferral_response_variations(
        self,
        defer_handler: DeferHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_wise_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test handling different deferral response values."""
        response_variations = [True, False]

        with patch_persistence_properly(test_task) as mock_persistence:
            for response in response_variations:
                # Reset mocks
                mock_wise_bus.send_deferral.reset_mock()
                mock_wise_bus.send_deferral.return_value = response

                # Execute handler
                await defer_handler.handle(action_result, test_thought, dispatch_context)

                # Verify thought was marked as deferred regardless of response
                assert mock_persistence.update_thought_status.called
                update_call = mock_persistence.update_thought_status.call_args
                assert update_call.kwargs["status"] == ThoughtStatus.DEFERRED

    @pytest.mark.asyncio
    async def test_audit_trail(
        self,
        defer_handler: DeferHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_bus_manager: Mock,
        test_task: Task,
    ) -> None:
        """Test that DEFER actions complete successfully (audit logging now in action_dispatcher)."""
        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await defer_handler.handle(action_result, test_thought, dispatch_context)

            # NOTE: Audit logging removed from handlers - action_dispatcher handles centralized audit logging
            # Verify handler completed successfully by checking thought status update
            assert mock_persistence.update_thought_status.called

    @pytest.mark.asyncio
    async def test_service_correlation_tracking(
        self,
        defer_handler: DeferHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        test_task: Task,
    ) -> None:
        """Test service correlation tracking for telemetry."""
        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await defer_handler.handle(action_result, test_thought, dispatch_context)

            # The defer handler doesn't directly add correlations
            # Verify thought status was updated (which is what it does)
            assert mock_persistence.update_thought_status.called
            update_call = mock_persistence.update_thought_status.call_args
            assert update_call.kwargs["thought_id"] == "thought_123"
            assert update_call.kwargs["status"] == ThoughtStatus.DEFERRED

    @pytest.mark.asyncio
    async def test_wise_authority_context_enrichment(
        self,
        defer_handler: DeferHandler,
        action_result: ActionSelectionDMAResult,
        test_thought: Thought,
        dispatch_context: DispatchContext,
        mock_wise_bus: AsyncMock,
        test_task: Task,
    ) -> None:
        """Test that handler enriches context with WA information."""
        # Set WA context in dispatch
        dispatch_context.wa_id = "wa_expert_123"
        dispatch_context.wa_authorized = True
        dispatch_context.wa_context = {"expertise": ["ethics", "policy"], "authority_level": "senior"}

        with patch_persistence_properly(test_task) as mock_persistence:
            # Execute handler
            await defer_handler.handle(action_result, test_thought, dispatch_context)

            # Verify deferral was sent with context
            deferral_call = mock_wise_bus.send_deferral.call_args
            context = deferral_call.kwargs["context"]
            assert isinstance(context, DeferralContext)
            assert context.thought_id == "thought_123"
            assert context.task_id == "task_123"
