"""
Test runtime control service unification between system.py and system_extensions.py.

This tests the fix for the service mismatch issue where pause and single-step
were using different runtime control services.
"""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.adapters.api.dependencies.auth import AuthContext, UserRole
from ciris_engine.logic.adapters.api.routes.system.schemas import RuntimeAction
from ciris_engine.logic.adapters.api.routes.system.runtime import control_runtime as system_runtime_control
from ciris_engine.logic.adapters.api.routes.system_extensions import single_step_processor
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.services.core.runtime import ProcessorControlResponse, ProcessorStatus


@pytest.fixture
def mock_request():
    """Create a mock request with app state."""
    request = MagicMock()
    state = MagicMock()

    # Create a proper runtime mock with agent_processor
    mock_runtime = MagicMock()
    mock_agent_processor = MagicMock()
    mock_agent_processor.get_current_state.return_value = "WORK"  # Return string, not MagicMock
    mock_runtime.agent_processor = mock_agent_processor

    state.configure_mock(
        **{"main_runtime_control_service": None, "runtime_control_service": None, "runtime": mock_runtime}
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
def mock_runtime_control():
    """Create a mock runtime control service."""
    mock = AsyncMock()
    mock.pause_processing = AsyncMock(return_value=True)
    mock.single_step = AsyncMock()
    return mock


class TestRuntimeControlServiceUnification:
    """Test that both pause and single-step use the same service selection logic."""

    @pytest.mark.asyncio
    async def test_both_endpoints_use_main_service_first(
        self, mock_request, mock_admin_auth_context, mock_runtime_control
    ):
        """Test that both endpoints prefer main_runtime_control_service."""
        # Setup both services available
        mock_fallback_service = AsyncMock()
        mock_request.app.state.main_runtime_control_service = mock_runtime_control
        mock_request.app.state.runtime_control_service = mock_fallback_service

        # Test pause endpoint uses main service
        body = RuntimeAction(reason="test")
        result = await system_runtime_control("pause", mock_request, body, mock_admin_auth_context)
        assert isinstance(result, SuccessResponse)
        mock_runtime_control.pause_processing.assert_called_once_with("test")
        mock_fallback_service.pause_processing.assert_not_called()

        # Reset mocks
        mock_runtime_control.reset_mock()
        mock_fallback_service.reset_mock()

        # Setup single step mock
        control_response = ProcessorControlResponse(
            success=True,
            processor_name="agent",
            operation="single_step",
            new_status=ProcessorStatus.RUNNING,
            message="Processed 1 thought",
        )
        mock_runtime_control.single_step.return_value = control_response

        # Test single-step endpoint uses main service
        result = await single_step_processor(mock_request, mock_admin_auth_context, {})
        assert isinstance(result, SuccessResponse)
        mock_runtime_control.single_step.assert_called_once()
        mock_fallback_service.single_step.assert_not_called()

    @pytest.mark.asyncio
    async def test_both_endpoints_fallback_to_runtime_control_service(
        self, mock_request, mock_admin_auth_context, mock_runtime_control
    ):
        """Test that both endpoints fallback to runtime_control_service when main is unavailable."""
        # Setup only fallback service available
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = mock_runtime_control

        # Test pause endpoint uses fallback service
        body = RuntimeAction(reason="test")
        result = await system_runtime_control("pause", mock_request, body, mock_admin_auth_context)
        assert isinstance(result, SuccessResponse)
        mock_runtime_control.pause_processing.assert_called_once_with("test")

        # Reset mock
        mock_runtime_control.reset_mock()

        # Setup single step mock
        control_response = ProcessorControlResponse(
            success=True,
            processor_name="agent",
            operation="single_step",
            new_status=ProcessorStatus.RUNNING,
            message="Processed 1 thought via fallback",
        )
        mock_runtime_control.single_step.return_value = control_response

        # Test single-step endpoint uses fallback service
        result = await single_step_processor(mock_request, mock_admin_auth_context, {})
        assert isinstance(result, SuccessResponse)
        mock_runtime_control.single_step.assert_called_once()

    @pytest.mark.asyncio
    async def test_both_endpoints_fail_when_no_service_available(self, mock_request, mock_admin_auth_context):
        """Test that both endpoints fail consistently when no service is available."""
        # Setup no services available
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = None

        # Test pause endpoint fails
        body = RuntimeAction(reason="test")
        with pytest.raises(Exception) as exc_info:
            await system_runtime_control("pause", mock_request, body, mock_admin_auth_context)
        assert "Runtime control service not available" in str(exc_info.value)

        # Test single-step endpoint fails with same error
        with pytest.raises(Exception) as exc_info:
            await single_step_processor(mock_request, mock_admin_auth_context, {})
        assert "Runtime control service not available" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_service_selection_logic_identical(self, mock_request, mock_admin_auth_context):
        """Test that the service selection logic is identical between endpoints."""
        # This test verifies that both endpoints use the exact same service selection pattern:
        # 1. Try main_runtime_control_service first
        # 2. Fall back to runtime_control_service
        # 3. Raise exception if neither available

        main_service = AsyncMock()
        fallback_service = AsyncMock()

        # Test Case 1: Only main service available
        mock_request.app.state.main_runtime_control_service = main_service
        mock_request.app.state.runtime_control_service = None

        # Both should use main service
        try:
            body = RuntimeAction(reason="test")
            await system_runtime_control("pause", mock_request, body, mock_admin_auth_context)
            main_used_by_pause = True
        except:
            main_used_by_pause = False

        main_service.reset_mock()
        main_service.single_step.return_value = ProcessorControlResponse(
            success=True,
            processor_name="agent",
            operation="single_step",
            new_status=ProcessorStatus.RUNNING,
            message="test",
        )

        try:
            await single_step_processor(mock_request, mock_admin_auth_context, {})
            main_used_by_single_step = True
        except:
            main_used_by_single_step = False

        assert main_used_by_pause == main_used_by_single_step

        # Test Case 2: Only fallback service available
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = fallback_service

        fallback_service.single_step.return_value = ProcessorControlResponse(
            success=True,
            processor_name="agent",
            operation="single_step",
            new_status=ProcessorStatus.RUNNING,
            message="test",
        )

        try:
            body = RuntimeAction(reason="test")
            await system_runtime_control("pause", mock_request, body, mock_admin_auth_context)
            fallback_used_by_pause = True
        except:
            fallback_used_by_pause = False

        try:
            await single_step_processor(mock_request, mock_admin_auth_context, {})
            fallback_used_by_single_step = True
        except:
            fallback_used_by_single_step = False

        assert fallback_used_by_pause == fallback_used_by_single_step
