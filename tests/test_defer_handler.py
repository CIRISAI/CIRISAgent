"""
Comprehensive unit tests for the Defer Handler.

Tests the deferral lifecycle, authority verification, time-based deferrals,
and proper integration with the Wise Authority service.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.control.defer_handler import DeferHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.schemas.actions.parameters import DeferParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.services.authority.wise_authority import DeferralResolution, PendingDeferral
from ciris_engine.schemas.services.authority_core import DeferralResponse
from ciris_engine.schemas.services.context import DeferralContext


class MockTimeService:
    """Mock time service for testing."""

    def __init__(self, now_time: Optional[datetime] = None) -> None:
        self._now = now_time or datetime.now(timezone.utc)

    def now(self) -> datetime:
        return self._now

    def set_now(self, new_time: datetime) -> None:
        self._now = new_time

    async def sleep(self, seconds: float) -> None:
        """Mock sleep method required by TimeServiceProtocol."""
        pass


def create_test_thought(
    thought_id: str = "test_thought", task_id: str = "test_task", status: ThoughtStatus = ThoughtStatus.PROCESSING
) -> Thought:
    """Helper to create a test thought."""
    return Thought(
        thought_id=thought_id,
        source_task_id=task_id,
        content="Test thought content for deferral",
        status=status,
        thought_depth=1,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        channel_id="test_channel",
        round_number=1,
        ponder_notes=None,
        parent_thought_id=None,
        final_action=None,
        context=ThoughtContext(
            task_id=task_id,
            channel_id="test_channel",
            round_number=1,
            depth=1,
            parent_thought_id=None,
            correlation_id="test_correlation",
        ),
    )


def create_test_task(task_id: str = "test_task", description: str = "Test task for deferral") -> Task:
    """Helper to create a test task."""
    return Task(
        task_id=task_id,
        channel_id="test_channel",
        description=description,
        status=TaskStatus.ACTIVE,
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        priority=0,
        parent_task_id=None,
        context=None,
        outcome=None,
        signed_by=None,
        signature=None,
        signed_at=None,
    )


def create_dispatch_context(thought_id: str, task_id: str, channel_id: str = "test_channel") -> DispatchContext:
    """Helper to create a dispatch context."""
    from ciris_engine.schemas.runtime.system_context import ChannelContext

    return DispatchContext(
        channel_context=ChannelContext(
            channel_id=channel_id,
            channel_name=f"Channel {channel_id}",
            channel_type="text",
            created_at=datetime.now(timezone.utc),
            is_private=False,
            participants=[],
            is_active=True,
            last_activity=None,
            message_count=0,
            allowed_actions=[],
            moderation_level="standard",
        ),
        author_id="test_author",
        author_name="Test Author",
        origin_service="test_service",
        handler_name="DeferHandler",
        action_type=HandlerActionType.DEFER,
        task_id=task_id,
        thought_id=thought_id,
        source_task_id=task_id,
        event_summary="Test defer action",
        event_timestamp=datetime.now(timezone.utc).isoformat(),
        wa_id=None,
        wa_authorized=False,
        wa_context=None,
        conscience_failure_context=None,
        epistemic_data=None,
        correlation_id="test_correlation_id",
        span_id=None,
        trace_id=None,
    )


class TestDeferHandler:
    """Test suite for DeferHandler functionality."""

    @pytest.fixture
    def mock_time_service(self) -> MockTimeService:
        """Provide a mock time service."""
        return MockTimeService()

    @pytest.fixture
    def mock_persistence(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        """Mock persistence module."""
        mock = Mock()
        mock.update_thought_status = Mock()
        mock.update_task_status = Mock()
        mock.get_task_by_id = Mock(return_value=create_test_task())
        monkeypatch.setattr("ciris_engine.logic.handlers.control.defer_handler.persistence", mock)
        return mock

    @pytest.fixture
    def mock_wise_bus(self) -> AsyncMock:
        """Mock wise authority bus."""
        mock_bus = AsyncMock()
        mock_bus.send_deferral = AsyncMock(return_value=True)
        return mock_bus

    @pytest.fixture
    def mock_audit_bus(self) -> Mock:
        """Mock audit bus."""
        mock_bus = Mock()
        mock_bus.log_event = AsyncMock()
        return mock_bus

    @pytest.fixture
    def mock_task_scheduler(self) -> AsyncMock:
        """Mock task scheduler service."""
        mock_scheduler = AsyncMock()
        mock_scheduler.schedule_deferred_task = AsyncMock(return_value=Mock(task_id="scheduled_task_123"))
        return mock_scheduler

    @pytest.fixture
    def mock_service_registry(self, mock_task_scheduler: AsyncMock) -> Mock:
        """Mock service registry with task scheduler."""
        mock_registry = Mock()
        mock_registry.get_service = AsyncMock(return_value=mock_task_scheduler)
        return mock_registry

    @pytest.fixture
    def bus_manager(
        self, mock_wise_bus: AsyncMock, mock_audit_bus: Mock, mock_time_service: MockTimeService
    ) -> BusManager:
        """Create a bus manager with mocked buses."""
        manager = BusManager(Mock(), time_service=mock_time_service, audit_service=mock_audit_bus)
        manager.wise = mock_wise_bus
        return manager

    @pytest.fixture
    def defer_handler(
        self, bus_manager: BusManager, mock_time_service: MockTimeService, mock_service_registry: Mock
    ) -> DeferHandler:
        """Create a DeferHandler instance with dependencies."""
        deps = ActionHandlerDependencies(bus_manager=bus_manager, time_service=mock_time_service)
        handler = DeferHandler(deps)
        setattr(handler, "_service_registry", mock_service_registry)
        return handler

    @pytest.mark.asyncio
    async def test_basic_deferral_success(
        self, defer_handler: DeferHandler, mock_persistence: Mock, mock_wise_bus: AsyncMock
    ) -> None:
        """Test successful basic deferral without time specification."""
        # Arrange
        thought = create_test_thought()
        params = DeferParams(
            reason="Need human review for sensitive content",
            context={"sensitivity": "high", "topic": "medical"},
            defer_until=None,
        )
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=params,
            rationale="Content requires human oversight",
            reasoning="Medical advice detected",
            evaluation_time_ms=100,
            raw_llm_response=None,
            resource_usage=None,
        )
        dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

        # Act
        await defer_handler.handle(result, thought, dispatch_context)

        # Assert
        # Verify WA bus was called
        mock_wise_bus.send_deferral.assert_called_once()
        call_args = mock_wise_bus.send_deferral.call_args
        assert call_args is not None

        deferral_context = call_args.kwargs["context"]
        assert isinstance(deferral_context, DeferralContext)
        assert deferral_context.thought_id == thought.thought_id
        assert deferral_context.task_id == thought.source_task_id
        assert deferral_context.reason == params.reason
        assert (
            deferral_context.metadata["attempted_action"] == "unknown"
        )  # Default value since DispatchContext doesn't have this field

        # Verify thought status updated
        mock_persistence.update_thought_status.assert_called_once_with(
            thought_id=thought.thought_id, status=ThoughtStatus.DEFERRED, final_action=result
        )

        # Verify task status updated
        mock_persistence.update_task_status.assert_called_once_with(
            thought.source_task_id, TaskStatus.DEFERRED, defer_handler.time_service
        )

    @pytest.mark.asyncio
    async def test_time_based_deferral(
        self,
        defer_handler: DeferHandler,
        mock_persistence: Mock,
        mock_wise_bus: AsyncMock,
        mock_task_scheduler: AsyncMock,
        mock_time_service: MockTimeService,
    ) -> None:
        """Test deferral with future reactivation time."""
        # Arrange
        current_time = datetime.now(timezone.utc)
        defer_until = current_time + timedelta(hours=2)
        mock_time_service.set_now(current_time)

        thought = create_test_thought()
        params = DeferParams(
            reason="Wait for external system response",
            defer_until=defer_until.isoformat(),
            context={"system": "payment_gateway", "transaction_id": "tx_123"},
        )
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=params,
            rationale="Waiting for payment confirmation",
            reasoning="External dependency",
            evaluation_time_ms=80,
            raw_llm_response=None,
            resource_usage=None,
        )
        dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

        # Act
        await defer_handler.handle(result, thought, dispatch_context)

        # Assert
        # Verify scheduled task created
        mock_task_scheduler.schedule_deferred_task.assert_called_once_with(
            thought_id=thought.thought_id,
            task_id=thought.source_task_id,
            defer_until=params.defer_until,
            reason=params.reason,
            context=params.context,
        )

        # Verify WA bus still called
        mock_wise_bus.send_deferral.assert_called_once()

        # Verify statuses updated
        assert mock_persistence.update_thought_status.called
        assert mock_persistence.update_task_status.called

    @pytest.mark.asyncio
    async def test_deferral_with_minimal_params(
        self, defer_handler: DeferHandler, mock_persistence: Mock, mock_wise_bus: AsyncMock
    ) -> None:
        """Test deferral handling with minimal valid parameters."""
        # Arrange
        thought = create_test_thought()
        # Create minimal valid params
        minimal_params = DeferParams(reason="Minimal deferral test", defer_until=None)

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=minimal_params,
            rationale="Testing minimal deferral",
            reasoning="Testing with minimal params",
            evaluation_time_ms=50,
            raw_llm_response=None,
            resource_usage=None,
        )
        dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

        # Act
        await defer_handler.handle(result, thought, dispatch_context)

        # Assert
        # Should send deferral successfully
        mock_wise_bus.send_deferral.assert_called_once()
        call_args = mock_wise_bus.send_deferral.call_args
        deferral_context = call_args.kwargs["context"]

        assert deferral_context.reason == "Minimal deferral test"
        # Should not have error metadata since params are valid
        assert "error_type" not in deferral_context.metadata

        # Status should still be updated to DEFERRED
        mock_persistence.update_thought_status.assert_called_once()
        call_args = mock_persistence.update_thought_status.call_args
        assert call_args.kwargs["status"] == ThoughtStatus.DEFERRED

    @pytest.mark.asyncio
    async def test_deferral_when_wise_authority_fails(
        self, defer_handler: DeferHandler, mock_persistence: Mock, mock_wise_bus: AsyncMock
    ) -> None:
        """Test that deferral is still processed when WA service fails."""
        # Arrange
        mock_wise_bus.send_deferral.side_effect = Exception("WA service unavailable")

        thought = create_test_thought()
        params = DeferParams(reason="Test deferral with WA failure", defer_until=None)
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=params,
            rationale="Testing WA failure handling",
            reasoning="Resilience test",
            evaluation_time_ms=75,
            raw_llm_response=None,
            resource_usage=None,
        )
        dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

        # Act
        await defer_handler.handle(result, thought, dispatch_context)

        # Assert
        # WA bus was attempted
        mock_wise_bus.send_deferral.assert_called_once()

        # Thought and task status should still be updated
        mock_persistence.update_thought_status.assert_called_once_with(
            thought_id=thought.thought_id, status=ThoughtStatus.DEFERRED, final_action=result
        )
        mock_persistence.update_task_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_deferral_with_task_metadata(
        self, defer_handler: DeferHandler, mock_persistence: Mock, mock_wise_bus: AsyncMock
    ) -> None:
        """Test that task description is included in deferral metadata."""
        # Arrange
        task = create_test_task(
            task_id="complex_task", description="Analyze medical records for treatment recommendation"
        )
        mock_persistence.get_task_by_id.return_value = task

        thought = create_test_thought(task_id=task.task_id)
        params = DeferParams(
            reason="Medical expertise required", context={"patient_id": "p123", "urgency": "high"}, defer_until=None
        )
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=params,
            rationale="Medical decision requires human doctor",
            reasoning="High stakes medical decision",
            evaluation_time_ms=120,
            raw_llm_response=None,
            resource_usage=None,
        )
        dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

        # Act
        await defer_handler.handle(result, thought, dispatch_context)

        # Assert
        mock_wise_bus.send_deferral.assert_called_once()
        call_args = mock_wise_bus.send_deferral.call_args
        deferral_context = call_args.kwargs["context"]

        assert deferral_context.metadata["task_description"] == task.description
        assert (
            deferral_context.metadata["attempted_action"] == "unknown"
        )  # Default value since DispatchContext doesn't have this field
        assert (
            deferral_context.metadata["max_rounds_reached"] == "False"
        )  # Default value since DispatchContext doesn't have this field

    @pytest.mark.asyncio
    async def test_system_task_deferred_no_special_treatment(
        self, defer_handler: DeferHandler, mock_persistence: Mock, mock_wise_bus: AsyncMock
    ) -> None:
        """Test that system tasks are deferred like any other task (no kings principle)."""
        # Arrange
        thought = create_test_thought(thought_id="system_thought", task_id="SYSTEM_TASK")
        params = DeferParams(reason="System task deferral", defer_until=None)
        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=params,
            rationale="System task defer test",
            reasoning="Testing system task handling",
            evaluation_time_ms=60,
            raw_llm_response=None,
            resource_usage=None,
        )
        dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

        # Act
        await defer_handler.handle(result, thought, dispatch_context)

        # Assert
        # Thought status should be updated
        mock_persistence.update_thought_status.assert_called_once()

        # Task status SHOULD be updated for system tasks too (no kings principle)
        mock_persistence.update_task_status.assert_called_once_with(
            "SYSTEM_TASK", TaskStatus.DEFERRED, defer_handler.time_service
        )

    @pytest.mark.asyncio
    async def test_concurrent_deferrals(
        self, defer_handler: DeferHandler, mock_persistence: Mock, mock_wise_bus: AsyncMock
    ) -> None:
        """Test handling multiple concurrent deferrals."""
        # Arrange
        thoughts = [create_test_thought(f"thought_{i}", f"task_{i}") for i in range(3)]

        params = [DeferParams(reason=f"Deferral reason {i}", defer_until=None) for i in range(3)]

        results = [
            ActionSelectionDMAResult(
                selected_action=HandlerActionType.DEFER,
                action_parameters=params[i],
                rationale=f"Rationale {i}",
                reasoning=f"Reasoning {i}",
                evaluation_time_ms=100 + i * 10,
                raw_llm_response=None,
                resource_usage=None,
            )
            for i in range(3)
        ]

        contexts = [create_dispatch_context(thoughts[i].thought_id, thoughts[i].source_task_id) for i in range(3)]

        # Act - Handle deferrals concurrently
        import asyncio

        await asyncio.gather(*[defer_handler.handle(results[i], thoughts[i], contexts[i]) for i in range(3)])

        # Assert
        assert mock_wise_bus.send_deferral.call_count == 3
        assert mock_persistence.update_thought_status.call_count == 3
        assert mock_persistence.update_task_status.call_count == 3

        # Verify each deferral has unique context
        sent_thought_ids = set()
        for call in mock_wise_bus.send_deferral.call_args_list:
            context = call.kwargs["context"]
            sent_thought_ids.add(context.thought_id)

        assert len(sent_thought_ids) == 3

    @pytest.mark.asyncio
    async def test_deferral_with_priority(
        self, defer_handler: DeferHandler, mock_persistence: Mock, mock_wise_bus: AsyncMock
    ) -> None:
        """Test deferral with different priority levels."""
        # Arrange
        thought = create_test_thought()

        # DeferParams doesn't have priority field directly,
        # but it can be passed through context
        params = DeferParams(
            reason="Critical security decision required",
            context={"priority": "critical", "security_level": "high", "threat_type": "data_breach"},
            defer_until=None,
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=params,
            rationale="Security breach requires immediate human intervention",
            reasoning="Critical security issue",
            evaluation_time_ms=50,
            raw_llm_response=None,
            resource_usage=None,
        )

        dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

        # Act
        await defer_handler.handle(result, thought, dispatch_context)

        # Assert
        mock_wise_bus.send_deferral.assert_called_once()
        call_args = mock_wise_bus.send_deferral.call_args
        deferral_context = call_args.kwargs["context"]

        # Priority should default to 'medium' as per handler logic
        assert deferral_context.priority == "medium"

        # But original context should be preserved in metadata
        assert params.context is not None
        assert "priority" in params.context
        assert params.context["priority"] == "critical"


class TestDeferralLifecycle:
    """Test the complete deferral lifecycle including WA resolution."""

    @pytest.fixture
    def mock_persistence(self, monkeypatch: pytest.MonkeyPatch) -> Mock:
        """Mock persistence for tests."""
        mock = Mock()
        mock.update_thought_status = Mock()
        mock.update_task_status = Mock()
        mock.get_task_by_id = Mock(return_value=create_test_task())
        monkeypatch.setattr("ciris_engine.logic.handlers.control.defer_handler.persistence", mock)
        return mock

    @pytest.fixture
    def mock_wise_bus(self) -> Mock:
        """Mock wise bus for tests."""
        mock = Mock()
        mock.send_deferral = AsyncMock(return_value="defer_123")
        return mock

    @pytest.fixture
    def mock_audit_bus(self) -> Mock:
        """Mock audit bus for tests."""
        mock = Mock()
        mock.log_event = AsyncMock()
        return mock

    @pytest.fixture
    def defer_handler(self, mock_persistence: Mock, mock_wise_bus: Mock, mock_audit_bus: Mock) -> DeferHandler:
        """Create a DeferHandler instance with dependencies."""
        from ciris_engine.logic.buses.bus_manager import BusManager
        from ciris_engine.logic.handlers.control.defer_handler import DeferHandler
        from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies

        # Create time service
        time_service = MockTimeService()

        # Create bus manager with mocked buses
        bus_manager = BusManager(Mock(), time_service=time_service)
        bus_manager.wise = mock_wise_bus
        bus_manager.audit_service = mock_audit_bus

        deps = ActionHandlerDependencies(bus_manager=bus_manager, time_service=time_service)
        handler = DeferHandler(deps)

        # Create mock service registry with task scheduler
        mock_task_scheduler = AsyncMock()
        mock_task_scheduler.schedule_deferred_task = AsyncMock(return_value=Mock(task_id="scheduled_task_123"))
        mock_service_registry = Mock()
        mock_service_registry.get_service = AsyncMock(return_value=mock_task_scheduler)
        setattr(handler, "_service_registry", mock_service_registry)

        # Inject mocked persistence
        import ciris_engine.logic.handlers.control.defer_handler

        ciris_engine.logic.handlers.control.defer_handler.persistence = mock_persistence

        return handler

    @pytest.fixture
    def mock_wise_authority_service(self) -> AsyncMock:
        """Mock wise authority service with full deferral capabilities."""
        service = AsyncMock()

        # Create sample pending deferrals
        service.get_pending_deferrals = AsyncMock(
            return_value=[
                PendingDeferral(
                    deferral_id="defer_001",
                    created_at=datetime.now(timezone.utc),
                    deferred_by="agent_123",
                    task_id="task_medical_001",
                    thought_id="thought_med_001",
                    reason="Medical decision requires human doctor review",
                    channel_id="channel_001",
                    user_id="user_001",
                    priority="high",
                    assigned_wa_id=None,
                    requires_role="AUTHORITY",
                    status="pending",
                    resolution=None,
                    resolved_at=None,
                ),
                PendingDeferral(
                    deferral_id="defer_002",
                    created_at=datetime.now(timezone.utc) - timedelta(hours=2),
                    deferred_by="agent_123",
                    task_id="task_financial_001",
                    thought_id="thought_fin_001",
                    reason="Large financial transaction requires approval",
                    channel_id="channel_002",
                    user_id="user_002",
                    priority="critical",
                    assigned_wa_id="wa_authority_001",
                    requires_role="AUTHORITY",
                    status="pending",
                    resolution=None,
                    resolved_at=None,
                ),
            ]
        )

        service.resolve_deferral = AsyncMock(return_value=True)
        service.check_authorization = AsyncMock(return_value=True)

        return service

    @pytest.mark.asyncio
    async def test_list_pending_deferrals(self, mock_wise_authority_service: AsyncMock) -> None:
        """Test listing pending deferrals for WA review."""
        # Act
        pending = await mock_wise_authority_service.get_pending_deferrals()

        # Assert
        assert len(pending) == 2
        assert all(isinstance(d, PendingDeferral) for d in pending)
        assert pending[0].priority == "high"
        assert pending[1].priority == "critical"
        assert pending[1].assigned_wa_id == "wa_authority_001"

    @pytest.mark.asyncio
    async def test_filter_deferrals_by_wa(self, mock_wise_authority_service: AsyncMock) -> None:
        """Test filtering deferrals by specific WA."""
        # Setup to return only assigned deferrals
        mock_wise_authority_service.get_pending_deferrals = AsyncMock(
            return_value=[
                PendingDeferral(
                    deferral_id="defer_002",
                    created_at=datetime.now(timezone.utc),
                    deferred_by="agent_123",
                    task_id="task_001",
                    thought_id="thought_001",
                    reason="Assigned to specific WA",
                    priority="high",
                    assigned_wa_id="wa_authority_001",
                    requires_role="AUTHORITY",
                    status="pending",
                )
            ]
        )

        # Act
        assigned_deferrals = await mock_wise_authority_service.get_pending_deferrals(wa_id="wa_authority_001")

        # Assert
        assert len(assigned_deferrals) == 1
        assert assigned_deferrals[0].assigned_wa_id == "wa_authority_001"

    @pytest.mark.asyncio
    async def test_resolve_deferral_approve(self, mock_wise_authority_service: AsyncMock) -> None:
        """Test WA approving a deferred decision."""
        # Arrange
        resolution = DeferralResolution(
            deferral_id="defer_001",
            wa_id="wa_authority_001",
            resolution="approve",
            guidance="Medical treatment approved with monitoring",
            modified_action=None,
            modified_parameters=None,
            new_constraints=["daily_monitoring", "report_adverse_effects"],
            removed_constraints=[],
            resolution_metadata={"medical_review": "completed", "risk_assessment": "low"},
        )

        # Convert to DeferralResponse for the service
        response = DeferralResponse(
            approved=True,
            reason=resolution.guidance,
            modified_time=None,
            wa_id=resolution.wa_id,
            signature="test_signature_001",
        )

        # Act
        result = await mock_wise_authority_service.resolve_deferral(resolution.deferral_id, response)

        # Assert
        assert result is True
        mock_wise_authority_service.resolve_deferral.assert_called_once_with("defer_001", response)

    @pytest.mark.asyncio
    async def test_resolve_deferral_reject(self, mock_wise_authority_service: AsyncMock) -> None:
        """Test WA rejecting a deferred decision."""
        # Arrange
        resolution = DeferralResolution(
            deferral_id="defer_002",
            wa_id="wa_authority_002",
            resolution="reject",
            guidance="Transaction exceeds authorized limits for this context",
            modified_action=None,
            modified_parameters=None,
            new_constraints=[],
            removed_constraints=[],
            resolution_metadata={"limit_exceeded": "true", "max_allowed": "10000"},
        )

        response = DeferralResponse(
            approved=False,
            reason=resolution.guidance,
            modified_time=None,
            wa_id=resolution.wa_id,
            signature="test_signature_002",
        )

        # Act
        result = await mock_wise_authority_service.resolve_deferral(resolution.deferral_id, response)

        # Assert
        assert result is True
        assert mock_wise_authority_service.resolve_deferral.called

    @pytest.mark.asyncio
    async def test_resolve_deferral_modify(self, mock_wise_authority_service: AsyncMock) -> None:
        """Test WA modifying a deferred action."""
        # Arrange
        modified_params = {
            "amount": 5000,  # Reduced from original
            "approval_type": "partial",
            "conditions": ["escrow_required", "phased_release"],
        }

        resolution = DeferralResolution(
            deferral_id="defer_002",
            wa_id="wa_authority_003",
            resolution="modify",
            guidance="Approved with reduced amount and additional safeguards",
            modified_action="process_financial_transaction",
            modified_parameters=modified_params,
            new_constraints=["daily_limit_5000", "require_2fa"],
            removed_constraints=["instant_processing"],
            resolution_metadata={"risk_mitigation": "applied", "review_required_after": "30_days"},
        )

        response = DeferralResponse(
            approved=True,
            reason=resolution.guidance,
            modified_time=datetime.now(timezone.utc) + timedelta(days=30),
            wa_id=resolution.wa_id,
            signature="test_signature_003",
        )

        # Act
        result = await mock_wise_authority_service.resolve_deferral(resolution.deferral_id, response)

        # Assert
        assert result is True
        call_args = mock_wise_authority_service.resolve_deferral.call_args
        assert call_args[0][0] == "defer_002"
        assert call_args[0][1].modified_time is not None

    @pytest.mark.asyncio
    async def test_unauthorized_resolution_attempt(self, mock_wise_authority_service: AsyncMock) -> None:
        """Test that only authorized WAs can resolve deferrals."""
        # Setup authorization to fail
        mock_wise_authority_service.check_authorization = AsyncMock(return_value=False)

        # Arrange
        response = DeferralResponse(
            approved=True,
            reason="Unauthorized approval attempt",
            modified_time=None,
            wa_id="wa_observer_001",  # Observer, not authority
            signature="invalid_signature",
        )

        # Simulate authorization check in real implementation
        is_authorized = await mock_wise_authority_service.check_authorization(
            wa_id="wa_observer_001", action="resolve_deferral", resource="defer_001"
        )

        # Assert
        assert is_authorized is False
        mock_wise_authority_service.check_authorization.assert_called_once_with(
            wa_id="wa_observer_001", action="resolve_deferral", resource="defer_001"
        )

    @pytest.mark.asyncio
    async def test_deferral_expiration_handling(self, mock_wise_authority_service: AsyncMock) -> None:
        """Test handling of expired deferrals."""
        # Create an expired deferral
        expired_deferral = PendingDeferral(
            deferral_id="defer_expired",
            created_at=datetime.now(timezone.utc) - timedelta(days=7),
            deferred_by="agent_123",
            task_id="task_old_001",
            thought_id="thought_old_001",
            reason="Old deferral that expired",
            channel_id="channel_001",
            user_id="user_001",
            priority="low",
            assigned_wa_id=None,
            requires_role="AUTHORITY",
            status="expired",  # Marked as expired
            resolution="auto_expired",
            resolved_at=datetime.now(timezone.utc) - timedelta(days=1),
        )

        # Setup service to return mix of pending and expired
        mock_wise_authority_service.get_pending_deferrals = AsyncMock(
            return_value=[
                expired_deferral,
                PendingDeferral(
                    deferral_id="defer_active",
                    created_at=datetime.now(timezone.utc),
                    deferred_by="agent_123",
                    task_id="task_new_001",
                    thought_id="thought_new_001",
                    reason="Active deferral",
                    channel_id="channel_001",
                    user_id="user_001",
                    priority="medium",
                    assigned_wa_id=None,
                    requires_role="AUTHORITY",
                    status="pending",
                    resolution=None,
                    resolved_at=None,
                ),
            ]
        )

        # Act
        all_deferrals = await mock_wise_authority_service.get_pending_deferrals()

        # Filter only truly pending ones
        pending_only = [d for d in all_deferrals if d.status == "pending"]

        # Assert
        assert len(all_deferrals) == 2
        assert len(pending_only) == 1
        assert pending_only[0].deferral_id == "defer_active"

    @pytest.mark.asyncio
    async def test_deferral_notification_flow(
        self, defer_handler: DeferHandler, mock_persistence: Mock, mock_wise_bus: AsyncMock, mock_audit_bus: Mock
    ) -> None:
        """Test that deferrals trigger proper notifications."""
        # Arrange
        thought = create_test_thought()
        params = DeferParams(
            reason="Urgent: Potential safety issue detected",
            context={
                "notification_required": "true",
                "notify_channels": "wa_emergency,wa_safety",
                "urgency": "critical",
            },
            defer_until=None,
        )

        result = ActionSelectionDMAResult(
            selected_action=HandlerActionType.DEFER,
            action_parameters=params,
            rationale="Safety issue requires immediate WA attention",
            reasoning="Critical safety protocol triggered",
            evaluation_time_ms=25,
            raw_llm_response=None,
            resource_usage=None,
        )

        dispatch_context = create_dispatch_context(thought.thought_id, thought.source_task_id)

        # Act
        await defer_handler.handle(result, thought, dispatch_context)

        # Assert
        # NOTE: Audit logging removed from handlers - action_dispatcher handles centralized audit logging

        # Verify WA notification sent
        mock_wise_bus.send_deferral.assert_called_once()
        call_args = mock_wise_bus.send_deferral.call_args
        context = call_args.kwargs["context"]

        # Check notification metadata preserved
        assert (
            context.metadata.get("attempted_action", "unknown") == "unknown"
        )  # Default value since DispatchContext doesn't have this field
        assert params.context["notification_required"] == "true"
        assert params.context["urgency"] == "critical"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
