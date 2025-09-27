"""
Unit tests for system management API endpoint extensions.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, UserRole
from ciris_engine.logic.adapters.api.routes.system_extensions import (
    CircuitBreakerResetRequest,
    ServicePriorityUpdateRequest,
    SingleStepResponse,
    _extract_cognitive_state,
    _get_queue_depth,
    get_processing_queue_status,
    get_processor_states,
    get_service_health_details,
    get_service_selection_explanation,
    reset_service_circuit_breakers,
    single_step_processor,
    update_service_priority,
)
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.services.core.runtime import (
    ProcessorControlResponse,
    ProcessorQueueStatus,
    ProcessorStatus,
    ServiceHealthStatus,
    ServiceSelectionExplanation,
)
from ciris_engine.schemas.services.runtime_control import PipelineState, StepPoint


@pytest.fixture
def mock_request():
    """Create a mock request with app state."""
    request = MagicMock()
    # Create a mock state that returns None for undefined attributes
    state = MagicMock()
    state.configure_mock(
        **{"main_runtime_control_service": None, "runtime_control_service": None, "service_registry": None}
    )
    request.app.state = state
    return request


@pytest.fixture
def mock_auth_context():
    """Create a mock auth context."""
    from ciris_engine.schemas.api.auth import ROLE_PERMISSIONS

    return AuthContext(
        user_id="test_user",
        role=UserRole.OBSERVER,
        permissions=ROLE_PERMISSIONS.get(UserRole.OBSERVER, set()),
        api_key_id="test_key",
        authenticated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_admin_auth_context():
    """Create a mock admin auth context."""
    from ciris_engine.schemas.api.auth import ROLE_PERMISSIONS

    return AuthContext(
        user_id="admin_user",
        role=UserRole.ADMIN,
        permissions=ROLE_PERMISSIONS.get(UserRole.ADMIN, set()),
        api_key_id="admin_key",
        authenticated_at=datetime.now(timezone.utc),
    )


@pytest.fixture
def mock_runtime_control():
    """Create a mock runtime control service."""
    mock = AsyncMock()
    mock.get_processor_queue_status = AsyncMock()
    mock.single_step = AsyncMock()
    mock.get_service_health_status = AsyncMock()
    mock.update_service_priority = AsyncMock()
    mock.reset_circuit_breakers = AsyncMock()
    mock.get_service_selection_explanation = AsyncMock()
    return mock


class TestProcessingQueueEndpoint:
    """Test the processing queue status endpoint."""

    @pytest.mark.asyncio
    async def test_get_queue_status_success(self, mock_request, mock_auth_context, mock_runtime_control):
        """Test successful retrieval of queue status."""
        # Setup
        expected_status = ProcessorQueueStatus(
            processor_name="agent",
            queue_size=5,
            max_size=1000,
            processing_rate=1.5,
            average_latency_ms=100.0,
            oldest_message_age_seconds=30.0,
        )
        mock_runtime_control.get_processor_queue_status.return_value = expected_status
        mock_request.app.state.main_runtime_control_service = mock_runtime_control

        # Execute
        result = await get_processing_queue_status(mock_request, mock_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data == expected_status
        mock_runtime_control.get_processor_queue_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_queue_status_fallback_service(self, mock_request, mock_auth_context, mock_runtime_control):
        """Test fallback to runtime_control_service when main_runtime_control_service is not available."""
        # Setup
        expected_status = ProcessorQueueStatus(
            processor_name="agent",
            queue_size=3,
            max_size=1000,
            processing_rate=1.0,
            average_latency_ms=150.0,
            oldest_message_age_seconds=45.0,
        )
        mock_runtime_control.get_processor_queue_status.return_value = expected_status
        mock_request.app.state.main_runtime_control_service = None  # Not available
        mock_request.app.state.runtime_control_service = mock_runtime_control  # Use fallback

        # Execute
        result = await get_processing_queue_status(mock_request, mock_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data == expected_status
        mock_runtime_control.get_processor_queue_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_queue_status_no_service(self, mock_request, mock_auth_context):
        """Test when no runtime control service is available."""
        # Setup
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = None

        # Execute & Verify
        with pytest.raises(Exception) as exc_info:
            await get_processing_queue_status(mock_request, mock_auth_context)
        assert "Runtime control service not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_queue_status_service_error(self, mock_request, mock_auth_context, mock_runtime_control):
        """Test handling of service errors."""
        # Setup
        mock_runtime_control.get_processor_queue_status.side_effect = Exception("Service error")
        mock_request.app.state.main_runtime_control_service = mock_runtime_control

        # Execute & Verify
        with pytest.raises(Exception) as exc_info:
            await get_processing_queue_status(mock_request, mock_auth_context)
        assert "Service error" in str(exc_info.value)


class TestSingleStepEndpoint:
    """Test the single step processor endpoint."""

    @pytest.mark.asyncio
    async def test_single_step_success(self, mock_request, mock_admin_auth_context, mock_runtime_control):
        """Test successful single step execution."""
        # Setup
        control_response = ProcessorControlResponse(
            success=True,
            processor_name="agent",
            operation="single_step",
            new_status=ProcessorStatus.RUNNING,
            message="Processed 1 thought",
        )
        mock_runtime_control.single_step.return_value = control_response
        mock_request.app.state.main_runtime_control_service = mock_runtime_control

        # Execute
        result = await single_step_processor(mock_request, mock_admin_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.success is True
        assert "completed" in result.data.message
        assert result.data.processor_state == "running"
        mock_runtime_control.single_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_step_fallback_service(self, mock_request, mock_admin_auth_context, mock_runtime_control):
        """Test single step with fallback to runtime_control_service."""
        # Setup
        control_response = ProcessorControlResponse(
            success=True,
            processor_name="agent",
            operation="single_step",
            new_status=ProcessorStatus.RUNNING,
            message="Processed 1 thought via fallback",
        )
        mock_runtime_control.single_step.return_value = control_response
        mock_request.app.state.main_runtime_control_service = None  # Not available
        mock_request.app.state.runtime_control_service = mock_runtime_control  # Use fallback

        # Execute
        result = await single_step_processor(mock_request, mock_admin_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.success is True
        assert "completed" in result.data.message
        mock_runtime_control.single_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_step_failure(self, mock_request, mock_admin_auth_context, mock_runtime_control):
        """Test handling of single step failure."""
        # Setup
        control_response = ProcessorControlResponse(
            success=False,
            processor_name="agent",
            operation="single_step",
            new_status=ProcessorStatus.ERROR,
            error="No thoughts to process",
        )
        mock_runtime_control.single_step.return_value = control_response
        mock_request.app.state.main_runtime_control_service = mock_runtime_control

        # Execute
        result = await single_step_processor(mock_request, mock_admin_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.success is False
        assert "failed" in result.data.message

    @pytest.mark.asyncio
    async def test_single_step_enhanced_response(
        self, mock_request, mock_admin_auth_context, mock_runtime_control, single_step_control_response
    ):
        """Test single step with enhanced response including details."""
        # Setup with existing fixture data
        mock_runtime_control.single_step.return_value = single_step_control_response
        mock_runtime_control.get_processor_queue_status.return_value = ProcessorQueueStatus(
            processor_name="agent",
            is_paused=True,
            queue_size=2,
            max_size=1000,
            processing_rate=0.0,
            average_latency_ms=0.0,
            oldest_message_age_seconds=0.0,
        )

        # Minimal runtime mock for cognitive state extraction
        mock_runtime = MagicMock()
        mock_agent_processor = MagicMock()
        mock_state_manager = MagicMock()
        mock_state_manager.get_state.return_value = StepPoint.PERFORM_DMAS
        mock_agent_processor.state_manager = mock_state_manager
        mock_runtime.agent_processor = mock_agent_processor

        mock_request.app.state.main_runtime_control_service = mock_runtime_control
        mock_request.app.state.runtime = mock_runtime

        # Execute with details (always included now)
        result = await single_step_processor(mock_request, mock_admin_auth_context, {})

        # Verify enhanced response with fixture data
        assert isinstance(result, SuccessResponse)
        assert isinstance(result.data, SingleStepResponse)
        assert result.data.success is True
        assert result.data.step_point == StepPoint.PERFORM_DMAS  # From fixture step_point
        assert result.data.step_result is not None  # From fixture step_results
        assert result.data.pipeline_state is not None  # From fixture pipeline_state
        assert result.data.processing_time_ms == 150.0  # From fixture
        assert result.data.tokens_used is None  # Not implemented yet per comment in API
        # Transparency data will be None - we use real transparency data from step results
        assert result.data.transparency_data is None

        # Verify runtime control service was called
        mock_runtime_control.single_step.assert_called_once()
        mock_runtime_control.get_processor_queue_status.assert_called_once()


class TestHelperFunctions:
    """Test helper functions for system extensions."""

    def test_extract_cognitive_state_success(self):
        """Test successful cognitive state extraction."""
        # Setup runtime with valid state manager
        mock_runtime = MagicMock()
        mock_agent_processor = MagicMock()
        mock_state_manager = MagicMock()
        mock_state_manager.get_state.return_value = AgentState.WORK
        mock_agent_processor.state_manager = mock_state_manager
        mock_runtime.agent_processor = mock_agent_processor

        # Execute
        result = _extract_cognitive_state(mock_runtime)

        # Verify
        assert result == str(AgentState.WORK)

    def test_extract_cognitive_state_no_runtime(self):
        """Test cognitive state extraction with no runtime."""
        result = _extract_cognitive_state(None)
        assert result is None

    def test_extract_cognitive_state_no_processor(self):
        """Test cognitive state extraction with no agent processor."""
        mock_runtime = MagicMock()
        mock_runtime.agent_processor = None

        result = _extract_cognitive_state(mock_runtime)
        assert result is None

    def test_extract_cognitive_state_no_state_manager(self):
        """Test cognitive state extraction with no state manager."""
        mock_runtime = MagicMock()
        mock_agent_processor = MagicMock()
        mock_agent_processor.state_manager = None
        mock_runtime.agent_processor = mock_agent_processor

        result = _extract_cognitive_state(mock_runtime)
        assert result is None

    def test_extract_cognitive_state_exception_handling(self):
        """Test cognitive state extraction handles exceptions gracefully."""
        mock_runtime = MagicMock()
        mock_agent_processor = MagicMock()
        mock_state_manager = MagicMock()
        mock_state_manager.get_state.side_effect = Exception("State error")
        mock_agent_processor.state_manager = mock_state_manager
        mock_runtime.agent_processor = mock_agent_processor

        result = _extract_cognitive_state(mock_runtime)
        assert result is None

    @pytest.mark.asyncio
    async def test_get_queue_depth_success(self):
        """Test successful queue depth retrieval."""
        mock_runtime_control = AsyncMock()
        mock_queue_status = ProcessorQueueStatus(
            processor_name="agent",
            is_paused=False,
            queue_size=5,
            max_size=1000,
            processing_rate=1.2,
            average_latency_ms=100.0,
            oldest_message_age_seconds=30.0,
        )
        mock_runtime_control.get_processor_queue_status.return_value = mock_queue_status

        result = await _get_queue_depth(mock_runtime_control)

        assert result == 5
        mock_runtime_control.get_processor_queue_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_queue_depth_no_status(self):
        """Test queue depth retrieval when no status returned."""
        mock_runtime_control = AsyncMock()
        mock_runtime_control.get_processor_queue_status.return_value = None

        result = await _get_queue_depth(mock_runtime_control)

        assert result == 0

    @pytest.mark.asyncio
    async def test_get_queue_depth_exception(self):
        """Test queue depth retrieval handles exceptions."""
        mock_runtime_control = AsyncMock()
        mock_runtime_control.get_processor_queue_status.side_effect = Exception("Queue error")

        result = await _get_queue_depth(mock_runtime_control)

        assert result == 0


# Demo data tests removed - we never show fake or mock data, only real transparency data


class TestProcessorStatesEndpoint:
    """Test processor states endpoint with cognitive state parsing fixes."""

    @pytest.mark.asyncio
    async def test_get_processor_states_work_active(self, mock_request, mock_auth_context):
        """Test processor states when WORK state is active."""
        # Setup runtime with WORK state using enum representation "AgentState.WORK"
        mock_runtime = MagicMock()
        mock_agent_processor = MagicMock()
        mock_state_manager = MagicMock()

        # Mock enum-like object that returns "AgentState.WORK" when converted to string
        mock_state = MagicMock()
        mock_state.__str__ = lambda self: "AgentState.WORK"
        mock_state_manager.get_state.return_value = mock_state

        mock_agent_processor.state_manager = mock_state_manager
        mock_runtime.agent_processor = mock_agent_processor
        mock_request.app.state.runtime = mock_runtime

        # Execute
        result = await get_processor_states(mock_request, mock_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        processor_states = result.data

        # Find WORK state and verify it's active
        work_state = next((state for state in processor_states if state.name == "WORK"), None)
        assert work_state is not None
        assert work_state.is_active is True

        # Verify other states are inactive
        for state in processor_states:
            if state.name != "WORK":
                assert state.is_active is False

    @pytest.mark.asyncio
    async def test_get_processor_states_dream_active(self, mock_request, mock_auth_context):
        """Test processor states when DREAM state is active."""
        # Setup runtime with DREAM state using enum representation "AgentState.DREAM"
        mock_runtime = MagicMock()
        mock_agent_processor = MagicMock()
        mock_state_manager = MagicMock()

        # Mock enum-like object that returns "AgentState.DREAM" when converted to string
        mock_state = MagicMock()
        mock_state.__str__ = lambda self: "AgentState.DREAM"
        mock_state_manager.get_state.return_value = mock_state

        mock_agent_processor.state_manager = mock_state_manager
        mock_runtime.agent_processor = mock_agent_processor
        mock_request.app.state.runtime = mock_runtime

        # Execute
        result = await get_processor_states(mock_request, mock_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        processor_states = result.data

        # Find DREAM state and verify it's active
        dream_state = next((state for state in processor_states if state.name == "DREAM"), None)
        assert dream_state is not None
        assert dream_state.is_active is True

        # Verify other states are inactive
        for state in processor_states:
            if state.name != "DREAM":
                assert state.is_active is False

    @pytest.mark.asyncio
    async def test_get_processor_states_plain_string(self, mock_request, mock_auth_context):
        """Test processor states when state is returned as plain string."""
        # Setup runtime with plain string state (no enum prefix)
        mock_runtime = MagicMock()
        mock_agent_processor = MagicMock()
        mock_state_manager = MagicMock()
        mock_state_manager.get_state.return_value = "PLAY"  # Plain string

        mock_agent_processor.state_manager = mock_state_manager
        mock_runtime.agent_processor = mock_agent_processor
        mock_request.app.state.runtime = mock_runtime

        # Execute
        result = await get_processor_states(mock_request, mock_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        processor_states = result.data

        # Find PLAY state and verify it's active
        play_state = next((state for state in processor_states if state.name == "PLAY"), None)
        assert play_state is not None
        assert play_state.is_active is True

    @pytest.mark.asyncio
    async def test_get_processor_states_no_current_state(self, mock_request, mock_auth_context):
        """Test processor states when no current state is available."""
        # Setup runtime with no current state
        mock_runtime = MagicMock()
        mock_agent_processor = MagicMock()
        mock_state_manager = MagicMock()
        mock_state_manager.get_state.return_value = None

        mock_agent_processor.state_manager = mock_state_manager
        mock_runtime.agent_processor = mock_agent_processor
        mock_request.app.state.runtime = mock_runtime

        # Execute
        result = await get_processor_states(mock_request, mock_auth_context)

        # Verify all states are inactive
        assert isinstance(result, SuccessResponse)
        processor_states = result.data

        for state in processor_states:
            assert state.is_active is False


class TestServiceHealthEndpoint:
    """Test the service health details endpoint."""

    @pytest.mark.asyncio
    async def test_get_service_health_success(self, mock_request, mock_auth_context, mock_runtime_control):
        """Test successful retrieval of service health."""
        # Setup
        health_status = ServiceHealthStatus(
            overall_health="healthy",
            healthy_services=2,
            unhealthy_services=0,
            service_details={
                "llm": {"status": "healthy", "circuit_breaker": "closed"},
                "memory": {"status": "healthy", "circuit_breaker": "closed"},
            },
            recommendations=[],
        )
        mock_runtime_control.get_service_health_status.return_value = health_status
        mock_request.app.state.main_runtime_control_service = mock_runtime_control

        # Execute
        result = await get_service_health_details(mock_request, mock_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.overall_health == "healthy"
        assert result.data.healthy_services == 2
        mock_runtime_control.get_service_health_status.assert_called_once()


class TestServicePriorityEndpoint:
    """Test the service priority update endpoint."""

    @pytest.mark.asyncio
    async def test_update_priority_success(self, mock_request, mock_admin_auth_context, mock_runtime_control):
        """Test successful priority update."""
        # Setup
        update_request = ServicePriorityUpdateRequest(priority="HIGH", priority_group=0, strategy="ROUND_ROBIN")
        mock_runtime_control.update_service_priority.return_value = {
            "provider_name": "TestService",
            "old_priority": "NORMAL",
            "new_priority": "HIGH",
            "old_priority_group": 1,
            "new_priority_group": 0,
            "old_strategy": "FALLBACK",
            "new_strategy": "ROUND_ROBIN",
            "message": "Priority updated successfully",
        }
        mock_request.app.state.main_runtime_control_service = mock_runtime_control

        # Execute
        result = await update_service_priority("TestService", update_request, mock_request, mock_admin_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.new_priority == "HIGH"
        assert result.data.provider_name == "TestService"
        mock_runtime_control.update_service_priority.assert_called_once_with(
            provider_name="TestService", new_priority="HIGH", new_priority_group=0, new_strategy="ROUND_ROBIN"
        )

    @pytest.mark.asyncio
    async def test_update_priority_invalid(self, mock_request, mock_admin_auth_context, mock_runtime_control):
        """Test handling of invalid priority."""
        # Setup
        update_request = ServicePriorityUpdateRequest(priority="HIGH", priority_group=0)
        mock_runtime_control.update_service_priority.side_effect = Exception("Invalid priority 'INVALID'")
        mock_request.app.state.main_runtime_control_service = mock_runtime_control

        # Execute & Verify
        with pytest.raises(Exception) as exc_info:
            await update_service_priority("TestService", update_request, mock_request, mock_admin_auth_context)
        assert "Invalid priority" in str(exc_info.value)


class TestCircuitBreakerEndpoint:
    """Test the circuit breaker reset endpoint."""

    @pytest.mark.asyncio
    async def test_reset_circuit_breakers_all(self, mock_request, mock_admin_auth_context, mock_runtime_control):
        """Test resetting all circuit breakers."""
        # Setup
        reset_request = CircuitBreakerResetRequest()
        mock_runtime_control.reset_circuit_breakers.return_value = {
            "service_type": None,
            "reset_count": 5,
            "services_affected": [
                "llm_service1",
                "llm_service2",
                "memory_service1",
                "memory_service2",
                "memory_service3",
            ],
            "message": "Circuit breakers reset successfully",
        }
        mock_request.app.state.main_runtime_control_service = mock_runtime_control

        # Execute
        result = await reset_service_circuit_breakers(reset_request, mock_request, mock_admin_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.reset_count == 5
        assert result.data.service_type is None
        assert len(result.data.services_affected) == 5
        mock_runtime_control.reset_circuit_breakers.assert_called_once_with(None)

    @pytest.mark.asyncio
    async def test_reset_circuit_breakers_specific(self, mock_request, mock_admin_auth_context, mock_runtime_control):
        """Test resetting specific service type circuit breakers."""
        # Setup
        reset_request = CircuitBreakerResetRequest(service_type="llm")
        mock_runtime_control.reset_circuit_breakers.return_value = {
            "service_type": "llm",
            "reset_count": 2,
            "services_affected": ["llm_service1", "llm_service2"],
            "message": "Circuit breakers reset successfully",
        }
        mock_request.app.state.main_runtime_control_service = mock_runtime_control

        # Execute
        result = await reset_service_circuit_breakers(reset_request, mock_request, mock_admin_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.reset_count == 2
        assert result.data.service_type == "llm"
        assert len(result.data.services_affected) == 2
        mock_runtime_control.reset_circuit_breakers.assert_called_once_with("llm")


class TestServiceSelectionExplanationEndpoint:
    """Test the service selection explanation endpoint."""

    @pytest.mark.asyncio
    async def test_get_selection_explanation(self, mock_request, mock_auth_context, mock_runtime_control):
        """Test getting service selection explanation."""
        # Setup
        explanation = ServiceSelectionExplanation(
            overview="Service selection system",
            priority_groups={0: "Primary", 1: "Backup"},
            selection_strategies={"FALLBACK": "First available"},
            examples=[{"scenario": "Example 1", "description": "Test example"}],
            configuration_tips=["Tip 1", "Tip 2"],
        )
        mock_runtime_control.get_service_selection_explanation.return_value = explanation
        mock_request.app.state.main_runtime_control_service = mock_runtime_control

        # Execute
        result = await get_service_selection_explanation(mock_request, mock_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.overview == "Service selection system"
        assert 0 in result.data.priority_groups  # Check priority group 0 exists
        mock_runtime_control.get_service_selection_explanation.assert_called_once()


class TestProcessorStatesEndpoint:
    """Test the processor states endpoint."""

    @pytest.mark.asyncio
    async def test_get_processor_states(self, mock_request, mock_auth_context):
        """Test getting processor states information."""
        # Setup
        mock_runtime = MagicMock()
        mock_agent_processor = MagicMock()
        mock_state_manager = MagicMock()
        mock_state_manager.get_state.return_value = "WORK"
        mock_agent_processor.state_manager = mock_state_manager
        mock_runtime.agent_processor = mock_agent_processor
        mock_request.app.state.runtime = mock_runtime

        # Execute
        result = await get_processor_states(mock_request, mock_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert len(result.data) == 6  # Should have 6 states

        # Check that WORK is active and others are not
        for state in result.data:
            if state.name == "WORK":
                assert state.is_active is True
            else:
                assert state.is_active is False

        # Verify state details
        work_state = next(s for s in result.data if s.name == "WORK")
        assert "task_processing" in work_state.capabilities
        assert "Normal task processing" in work_state.description

    @pytest.mark.asyncio
    async def test_get_processor_states_no_runtime(self, mock_request, mock_auth_context):
        """Test when runtime is not available."""
        # Setup
        mock_request.app.state.runtime = None

        # Execute & Verify
        with pytest.raises(Exception) as exc_info:
            await get_processor_states(mock_request, mock_auth_context)
        assert "Agent processor not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_processor_states_no_state_manager(self, mock_request, mock_auth_context):
        """Test when state manager is not available."""
        # Setup
        mock_runtime = MagicMock()
        mock_agent_processor = MagicMock()
        mock_agent_processor.state_manager = None
        mock_runtime.agent_processor = mock_agent_processor
        mock_request.app.state.runtime = mock_runtime

        # Execute
        result = await get_processor_states(mock_request, mock_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert len(result.data) == 6
        # All states should be inactive
        for state in result.data:
            assert state.is_active is False
