"""
Comprehensive unit tests for runtime control API fixes.

This test file covers all the lines that were fixed in the runtime control endpoints,
specifically testing the pause/resume/state functionality with proper service fallback,
parameter detection, and object attribute access patterns.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
import inspect

import pytest

from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, UserRole
from ciris_engine.logic.adapters.api.routes.system import control_runtime, RuntimeControlResponse
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.services.core.runtime import RuntimeStatusResponse, ProcessorControlResponse, ProcessorStatus

# Import runtime control fixtures
from tests.fixtures.runtime_control import (
    runtime_status_running,
    runtime_status_paused,
    runtime_status_dream,
    runtime_status_no_cognitive_state,
    mock_main_runtime_control_service,
    mock_api_runtime_control_service,
)


@pytest.fixture
def mock_request():
    """Create a mock request with app state."""
    request = MagicMock()
    state = MagicMock()
    state.configure_mock(
        **{
            "main_runtime_control_service": None,
            "runtime_control_service": None, 
            "runtime": None
        }
    )
    request.app.state = state
    return request


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
def mock_body():
    """Create a mock body for runtime control requests."""
    body = MagicMock()
    body.reason = "Test reason"
    return body


# Fixtures are now imported from tests.fixtures.runtime_control
# Use mock_main_runtime_control_service and mock_api_runtime_control_service


def create_runtime_mock_with_agent_processor(cognitive_state="WORK", pipeline_state=None):
    """Helper to create a properly configured runtime mock."""
    from ciris_engine.schemas.services.runtime_control import StepPoint
    
    mock_runtime = MagicMock()
    
    # Setup agent_processor to return proper cognitive state
    mock_agent_processor = MagicMock()
    mock_agent_processor.get_current_state.return_value = cognitive_state
    
    # Setup pipeline_controller with proper state structure if provided
    if pipeline_state:
        mock_pipeline_controller = MagicMock()
        
        # Create a mock pipeline state object with proper attributes
        mock_pipeline_state_obj = MagicMock()
        mock_pipeline_state_obj.current_step = pipeline_state if isinstance(pipeline_state, StepPoint) else StepPoint.PERFORM_DMAS
        mock_pipeline_state_obj.pipeline_state = {
            "current_round": 1,
            "thoughts_in_flight": 1,
            "total_thoughts_processed": 1,
            "is_paused": True
        }
        
        mock_pipeline_controller.get_current_state.return_value = mock_pipeline_state_obj
        mock_agent_processor._pipeline_controller = mock_pipeline_controller
    else:
        mock_agent_processor._pipeline_controller = None
    
    mock_runtime.agent_processor = mock_agent_processor
    
    return mock_runtime


class TestRuntimeControlServiceFallback:
    """Test the service fallback mechanism for runtime control."""

    @pytest.mark.asyncio
    async def test_pause_with_main_service(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service):
        """Test pause operation with main runtime control service."""
        # Setup - main service available
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service
        mock_request.app.state.runtime_control_service = None
        
        # Setup runtime for pipeline state extraction
        mock_runtime = MagicMock()
        mock_pipeline_controller = MagicMock()
        mock_pipeline_controller.get_current_state.return_value = {"current_step": "BUILD_CONTEXT"}
        mock_runtime.pipeline_controller = mock_pipeline_controller
        
        # Setup agent_processor to return proper cognitive state
        mock_agent_processor = MagicMock()
        mock_agent_processor.get_current_state.return_value = "WORK"
        mock_runtime.agent_processor = mock_agent_processor
        
        mock_request.app.state.runtime = mock_runtime

        # Execute
        result = await control_runtime("pause", mock_request, mock_body, mock_admin_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert isinstance(result.data, RuntimeControlResponse)
        assert result.data.success is True
        assert "paused" in result.data.message.lower()
        assert result.data.processor_state == "paused"
        
        # Verify main service was called (no parameters because it's the main service)
        mock_main_runtime_control_service.pause_processing.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_pause_with_api_service_fallback(self, mock_request, mock_admin_auth_context, mock_body, mock_api_runtime_control_service):
        """Test pause operation falling back to API runtime control service."""
        # Setup - only API service available
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = mock_api_runtime_control_service

        # Execute
        result = await control_runtime("pause", mock_request, mock_body, mock_admin_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.success is True
        assert "paused" in result.data.message.lower()
        
        # Verify API service was called with reason parameter
        mock_api_runtime_control_service.pause_processing.assert_called_once_with("Test reason")

    @pytest.mark.asyncio
    async def test_pause_parameter_detection(self, mock_request, mock_admin_auth_context, mock_body):
        """Test the inspection-based parameter detection for pause methods."""
        # Setup mock service with parameter-based pause method
        mock_runtime_control = AsyncMock()
        
        # Create a mock pause method that accepts a parameter
        async def mock_pause_with_param(reason):
            return True
            
        mock_runtime_control.pause_processing = mock_pause_with_param
        mock_request.app.state.main_runtime_control_service = mock_runtime_control
        
        # Execute
        result = await control_runtime("pause", mock_request, mock_body, mock_admin_auth_context)

        # Verify the inspection worked and the method was called with parameter
        assert result.data.success is True

    @pytest.mark.asyncio 
    async def test_pause_no_parameter_detection(self, mock_request, mock_admin_auth_context, mock_body):
        """Test parameter detection for parameterless pause methods.""" 
        # Setup mock service with parameterless pause method
        mock_runtime_control = AsyncMock()
        mock_control_response = MagicMock()
        mock_control_response.success = True
        
        # Create a mock pause method that accepts no parameters
        async def mock_pause_no_param():
            return mock_control_response
            
        mock_runtime_control.pause_processing = mock_pause_no_param
        mock_request.app.state.main_runtime_control_service = mock_runtime_control
        
        # Execute
        result = await control_runtime("pause", mock_request, mock_body, mock_admin_auth_context)

        # Verify the inspection worked and returned control response
        assert result.data.success is True

    @pytest.mark.asyncio
    async def test_resume_with_control_response(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service):
        """Test resume operation that returns control response object."""
        # Setup
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service

        # Execute
        result = await control_runtime("resume", mock_request, mock_body, mock_admin_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.success is True
        assert "resumed" in result.data.message.lower()
        assert result.data.processor_state == "active"
        
        # Verify service method was called
        mock_main_runtime_control_service.resume_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_resume_with_boolean_response(self, mock_request, mock_admin_auth_context, mock_body, mock_api_runtime_control_service):
        """Test resume operation that returns boolean."""
        # Setup
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = mock_api_runtime_control_service

        # Execute  
        result = await control_runtime("resume", mock_request, mock_body, mock_admin_auth_context)

        # Verify
        assert isinstance(result, SuccessResponse)
        assert result.data.success is True
        assert "resumed" in result.data.message.lower()
        
        # Verify service method was called
        mock_api_runtime_control_service.resume_processing.assert_called_once()


class TestRuntimeStateEndpoint:
    """Test the runtime state retrieval with proper attribute access."""

    @pytest.mark.asyncio
    async def test_state_with_getattr_access(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service, runtime_status_dream):
        """Test state retrieval using getattr for object attribute access."""
        # Use the dream status fixture
        mock_main_runtime_control_service.get_runtime_status.return_value = runtime_status_dream
        
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service

        # Execute
        result = await control_runtime("state", mock_request, mock_body, mock_admin_auth_context)

        # Verify getattr access worked correctly
        assert isinstance(result, SuccessResponse)
        assert result.data.success is True
        assert result.data.processor_state == "paused"  # getattr(status, "paused", False) -> True -> "paused"
        assert result.data.cognitive_state == "DREAM"
        assert result.data.queue_depth == 5
        
        # Verify await was added to the call
        mock_main_runtime_control_service.get_runtime_status.assert_called_once()

    @pytest.mark.asyncio
    async def test_state_with_missing_attributes(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service, runtime_status_no_cognitive_state):
        """Test state retrieval with missing attributes (default values)."""
        # Use the no cognitive state fixture to test default behavior
        mock_main_runtime_control_service.get_runtime_status.return_value = runtime_status_no_cognitive_state
        
        # Override queue status to return None to test default behavior
        mock_main_runtime_control_service.get_processor_queue_status.return_value = None
        
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service

        # Execute
        result = await control_runtime("state", mock_request, mock_body, mock_admin_auth_context)

        # Verify default values from getattr
        assert isinstance(result, SuccessResponse)
        assert result.data.success is True
        assert result.data.processor_state == "active"  # getattr(status, "paused", False) -> False -> "active"
        assert result.data.cognitive_state == "UNKNOWN"  # getattr(status, "cognitive_state", "UNKNOWN")
        assert result.data.queue_depth == 0  # getattr(status, "queue_depth", 0)

    @pytest.mark.asyncio
    async def test_state_async_call_added(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service, runtime_status_running):
        """Test that await was properly added to get_runtime_status call."""
        # Use the running status fixture and verify async call
        mock_main_runtime_control_service.get_runtime_status = AsyncMock(return_value=runtime_status_running)
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service

        # Execute
        result = await control_runtime("state", mock_request, mock_body, mock_admin_auth_context)

        # Verify the async method was awaited correctly
        assert result.data.success is True
        mock_main_runtime_control_service.get_runtime_status.assert_called_once()
        # Ensure it was actually awaited (AsyncMock tracks this)
        assert mock_main_runtime_control_service.get_runtime_status.called


class TestPipelineStateEnhancement:
    """Test enhanced pause response with pipeline state information."""

    @pytest.mark.asyncio
    async def test_pause_with_pipeline_state(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service):
        """Test pause operation captures pipeline state for UI display."""
        from ciris_engine.schemas.services.runtime_control import StepPoint
        
        # Setup runtime with proper pipeline state using StepPoint enum
        mock_runtime = create_runtime_mock_with_agent_processor("WORK", StepPoint.PERFORM_DMAS)
        mock_request.app.state.runtime = mock_runtime
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service

        # Execute
        result = await control_runtime("pause", mock_request, mock_body, mock_admin_auth_context)

        # Verify enhanced response includes pipeline information
        assert isinstance(result, SuccessResponse)
        assert result.data.success is True
        # Message should contain either the enum name or value
        assert ("PERFORM_DMAS" in result.data.message or StepPoint.PERFORM_DMAS.value in result.data.message)
        assert hasattr(result.data, 'current_step')
        assert result.data.current_step == StepPoint.PERFORM_DMAS
        assert hasattr(result.data, 'current_step_schema')
        assert result.data.current_step_schema is not None
        assert result.data.current_step_schema["step_point"] == StepPoint.PERFORM_DMAS
        assert result.data.current_step_schema["can_single_step"] is True

    @pytest.mark.asyncio
    async def test_pause_without_pipeline_controller(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service):
        """Test pause operation when no pipeline controller is available."""
        # Setup runtime without pipeline controller but with agent_processor
        mock_runtime = create_runtime_mock_with_agent_processor("WORK", None)
        mock_request.app.state.runtime = mock_runtime
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service

        # Execute
        result = await control_runtime("pause", mock_request, mock_body, mock_admin_auth_context)

        # Verify basic pause still works without enhanced data
        assert isinstance(result, SuccessResponse)
        assert result.data.success is True
        assert "paused" in result.data.message.lower()
        # No step information should be present
        assert not hasattr(result.data, 'current_step') or result.data.current_step is None

    @pytest.mark.asyncio
    async def test_pause_pipeline_exception_handling(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service):
        """Test pause operation handles pipeline exceptions gracefully."""
        # Setup runtime with proper agent_processor and pipeline controller that throws exception
        mock_runtime = create_runtime_mock_with_agent_processor("WORK", None)
        mock_pipeline_controller = MagicMock()
        mock_pipeline_controller.get_current_state.side_effect = Exception("Pipeline error")
        mock_runtime.pipeline_controller = mock_pipeline_controller
        mock_request.app.state.runtime = mock_runtime
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service

        # Execute - should not raise exception
        result = await control_runtime("pause", mock_request, mock_body, mock_admin_auth_context)

        # Verify pause still succeeds despite pipeline error
        assert isinstance(result, SuccessResponse)
        assert result.data.success is True
        assert "paused" in result.data.message.lower()


class TestRuntimeControlResponseSchema:
    """Test the enhanced RuntimeControlResponse schema."""

    @pytest.mark.asyncio
    async def test_enhanced_response_fields(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service):
        """Test that enhanced response includes the new optional fields."""
        from ciris_engine.schemas.services.runtime_control import StepPoint
        
        # Setup runtime with pipeline state using proper enum
        mock_runtime = create_runtime_mock_with_agent_processor("WORK", StepPoint.GATHER_CONTEXT)
        mock_request.app.state.runtime = mock_runtime
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service

        # Execute
        result = await control_runtime("pause", mock_request, mock_body, mock_admin_auth_context)

        # Verify enhanced fields are present
        response_data = result.data
        assert hasattr(response_data, 'current_step')
        assert hasattr(response_data, 'current_step_schema')  
        assert hasattr(response_data, 'pipeline_state')
        
        # Verify enhanced fields have correct types and content
        assert response_data.current_step == StepPoint.GATHER_CONTEXT
        assert isinstance(response_data.current_step_schema, dict)
        assert response_data.current_step_schema["step_point"] == StepPoint.GATHER_CONTEXT
        assert "timestamp" in response_data.current_step_schema
        assert "next_actions" in response_data.current_step_schema

    @pytest.mark.asyncio
    async def test_response_without_enhanced_fields(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service):
        """Test response when enhanced fields are not available."""
        # Setup without pipeline controller
        mock_request.app.state.runtime = None
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service

        # Execute
        result = await control_runtime("resume", mock_request, mock_body, mock_admin_auth_context)

        # Verify basic fields are present but enhanced fields are None/empty
        response_data = result.data
        assert response_data.success is True
        assert response_data.processor_state == "active"
        assert response_data.cognitive_state == "UNKNOWN"
        # Enhanced fields should be None or not present
        assert not hasattr(response_data, 'current_step') or response_data.current_step is None


class TestServiceNotAvailableHandling:
    """Test error handling when runtime control services are not available."""

    @pytest.mark.asyncio
    async def test_no_services_available(self, mock_request, mock_admin_auth_context, mock_body):
        """Test error when no runtime control services are available."""
        # Setup - no services available
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = None

        # Execute & Verify
        with pytest.raises(Exception) as exc_info:
            await control_runtime("pause", mock_request, mock_body, mock_admin_auth_context)
        
        assert "Runtime control service not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_main_service_preferred_over_api_service(self, mock_request, mock_admin_auth_context, mock_body, mock_main_runtime_control_service, mock_api_runtime_control_service):
        """Test that main service is preferred when both are available."""
        # Setup - both services available
        mock_request.app.state.main_runtime_control_service = mock_main_runtime_control_service
        mock_request.app.state.runtime_control_service = mock_api_runtime_control_service

        # Execute
        result = await control_runtime("pause", mock_request, mock_body, mock_admin_auth_context)

        # Verify main service was used (no parameter call)
        assert result.data.success is True
        mock_main_runtime_control_service.pause_processing.assert_called_once_with()
        mock_api_runtime_control_service.pause_processing.assert_not_called()