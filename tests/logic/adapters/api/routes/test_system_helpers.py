"""Tests for system.py helper methods extracted for cognitive complexity reduction."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from ciris_engine.logic.adapters.api.routes.system.helpers import (
    check_health_via_runtime_control,
    check_processor_via_runtime,
    get_runtime_control_from_app,
)


@pytest.fixture
def mock_request():
    """Create a mock FastAPI Request."""
    request = MagicMock()
    request.app = MagicMock()
    request.app.state = MagicMock()
    return request


@pytest.fixture
def mock_runtime_running():
    """Create a mock runtime with running processor."""
    runtime = MagicMock()
    runtime.agent_processor = MagicMock()
    runtime.agent_processor._running = True
    return runtime


@pytest.fixture
def mock_runtime_stopped():
    """Create a mock runtime with stopped processor."""
    runtime = MagicMock()
    runtime.agent_processor = MagicMock()
    runtime.agent_processor._running = False
    runtime._agent_task = None
    return runtime


@pytest.fixture
def mock_runtime_task_running():
    """Create a mock runtime with agent task still running."""
    runtime = MagicMock()
    runtime.agent_processor = MagicMock()
    runtime.agent_processor._running = False
    runtime._agent_task = MagicMock()
    runtime._agent_task.done.return_value = False
    return runtime


@pytest.fixture
def mock_runtime_no_processor():
    """Create a mock runtime without agent processor."""
    runtime = MagicMock()
    runtime.agent_processor = None
    return runtime


class TestCheckProcessorViaRuntime:
    """Tests for check_processor_via_runtime helper."""

    def test_returns_none_when_no_runtime(self):
        """Returns None when runtime is None."""
        result = check_processor_via_runtime(None)
        assert result is None

    def test_returns_none_when_no_agent_processor(self, mock_runtime_no_processor):
        """Returns None when runtime has no agent_processor."""
        result = check_processor_via_runtime(mock_runtime_no_processor)
        assert result is None

    def test_returns_true_when_processor_running(self, mock_runtime_running):
        """Returns True when processor._running is True."""
        result = check_processor_via_runtime(mock_runtime_running)
        assert result is True

    def test_returns_true_when_agent_task_running(self, mock_runtime_task_running):
        """Returns True when _agent_task is not done."""
        result = check_processor_via_runtime(mock_runtime_task_running)
        assert result is True

    def test_returns_none_when_processor_stopped_no_task(self, mock_runtime_stopped):
        """Returns None when processor stopped and no active task."""
        result = check_processor_via_runtime(mock_runtime_stopped)
        assert result is None


class TestGetRuntimeControlFromApp:
    """Tests for get_runtime_control_from_app helper."""

    def test_returns_main_runtime_control(self, mock_request):
        """Returns main_runtime_control_service when available."""
        mock_control = MagicMock()
        mock_request.app.state.main_runtime_control_service = mock_control
        mock_request.app.state.runtime_control_service = None

        result = get_runtime_control_from_app(mock_request)
        assert result is mock_control

    def test_falls_back_to_runtime_control(self, mock_request):
        """Falls back to runtime_control_service when main is None."""
        mock_control = MagicMock()
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = mock_control

        result = get_runtime_control_from_app(mock_request)
        assert result is mock_control

    def test_returns_none_when_no_services(self, mock_request):
        """Returns None when no runtime control services exist."""
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = None

        result = get_runtime_control_from_app(mock_request)
        assert result is None


class TestCheckHealthViaRuntimeControl:
    """Tests for check_health_via_runtime_control helper."""

    @pytest.mark.asyncio
    async def test_returns_none_when_no_service(self):
        """Returns None when runtime_control is None."""
        result = await check_health_via_runtime_control(None)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_service_not_running(self):
        """Returns None when service has is_running=False."""
        mock_control = MagicMock()
        mock_control.is_running = False

        result = await check_health_via_runtime_control(mock_control)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_no_agent_processor_ref(self):
        """Returns None when service lacks agent_processor_ref."""
        mock_control = MagicMock()
        mock_control.is_running = True
        mock_control.agent_processor_ref = None

        result = await check_health_via_runtime_control(mock_control)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_processor_ref_invalid(self):
        """Returns None when agent_processor_ref returns None."""
        mock_control = MagicMock()
        mock_control.is_running = True
        mock_control.agent_processor_ref = MagicMock(return_value=None)

        result = await check_health_via_runtime_control(mock_control)
        assert result is None

    @pytest.mark.asyncio
    async def test_returns_none_when_processor_not_running(self):
        """Returns None when processor._running is False."""
        mock_control = MagicMock()
        mock_control.is_running = True
        mock_processor = MagicMock()
        mock_processor._running = False
        mock_control.agent_processor_ref = MagicMock(return_value=mock_processor)

        result = await check_health_via_runtime_control(mock_control)
        assert result is None

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self):
        """Returns None when exception occurs."""
        mock_control = MagicMock()
        mock_control.is_running = True
        mock_control.agent_processor_ref = MagicMock(side_effect=Exception("Test error"))

        result = await check_health_via_runtime_control(mock_control)
        assert result is None


class TestIntegration:
    """Integration tests combining multiple helpers."""

    def test_processor_check_chain(self, mock_request, mock_runtime_running):
        """Test chaining processor and runtime control checks."""
        # First try via runtime
        result = check_processor_via_runtime(mock_runtime_running)
        assert result is True

        # Then get runtime control
        mock_request.app.state.main_runtime_control_service = None
        mock_request.app.state.runtime_control_service = None
        runtime_control = get_runtime_control_from_app(mock_request)
        assert runtime_control is None

    @pytest.mark.asyncio
    async def test_fallback_chain(self, mock_request, mock_runtime_stopped):
        """Test fallback when runtime check fails - get_runtime_control_from_app is called."""
        # Runtime check returns None
        result = check_processor_via_runtime(mock_runtime_stopped)
        assert result is None

        # Set up runtime control as fallback
        mock_control = MagicMock()
        mock_control.is_running = True
        mock_request.app.state.main_runtime_control_service = mock_control

        runtime_control = get_runtime_control_from_app(mock_request)
        assert runtime_control is mock_control
        assert runtime_control.is_running is True
