import asyncio
from unittest.mock import patch, MagicMock, AsyncMock

import pytest

# Import the module we are testing
from ciris_engine.logic.utils import initialization_manager

# Since the module uses a global variable, we need to reset it for each test
@pytest.fixture(autouse=True)
def reset_global_service():
    """Ensures the global service instance is reset before each test."""
    initialization_manager._global_initialization_service = None
    yield
    initialization_manager._global_initialization_service = None


@patch('ciris_engine.logic.utils.initialization_manager.InitializationService')
@patch('ciris_engine.logic.services.lifecycle.time.TimeService') # Corrected path
def test_get_initialization_manager_creates_once(mock_time_service, mock_init_service):
    """Test that get_initialization_manager creates the service only on the first call."""

    # Arrange
    mock_instance = MagicMock()
    mock_init_service.return_value = mock_instance

    # Act
    first_call_result = initialization_manager.get_initialization_manager()
    second_call_result = initialization_manager.get_initialization_manager()

    # Assert
    mock_time_service.assert_called_once()
    mock_init_service.assert_called_once()
    assert first_call_result is mock_instance
    assert second_call_result is mock_instance


def test_register_initialization_callback_logs_warning(caplog):
    """Test that the deprecated callback function logs a warning."""
    # Act
    initialization_manager.register_initialization_callback(lambda: None)

    # Assert
    assert len(caplog.records) == 1
    assert caplog.records[0].levelname == "WARNING"
    assert "register_initialization_callback is deprecated" in caplog.text


@pytest.mark.asyncio
@patch('ciris_engine.logic.utils.initialization_manager.InitializationService')
async def test_initialize_components_calls_service(mock_init_service):
    """Test that initialize_components awaits the service's initialize method."""
    # Arrange
    mock_service_instance = MagicMock()
    mock_service_instance.initialize = AsyncMock()
    mock_init_service.return_value = mock_service_instance

    # Act
    await initialization_manager.initialize_components()

    # Assert
    mock_service_instance.initialize.assert_awaited_once()


@patch('ciris_engine.logic.utils.initialization_manager.InitializationService')
def test_is_initialized_checks_service_attribute(mock_init_service):
    """Test that is_initialized returns the correct state from the service."""
    # Arrange
    mock_service_instance = MagicMock()
    mock_init_service.return_value = mock_service_instance

    # Test case 1: Not initialized
    mock_service_instance._initialization_complete = False
    assert not initialization_manager.is_initialized()

    # Test case 2: Initialized
    mock_service_instance._initialization_complete = True
    assert initialization_manager.is_initialized()


@patch('ciris_engine.logic.utils.initialization_manager.InitializationService')
def test_reset_initialization_resets_service_state(mock_init_service):
    """Test that reset_initialization correctly resets the service's internal state."""
    # Arrange
    mock_service_instance = MagicMock()
    mock_init_service.return_value = mock_service_instance

    # Set a "dirty" state
    mock_service_instance._initialization_complete = True
    mock_service_instance._completed_steps = ["step1"]
    mock_service_instance._error = "An error"

    # Act
    initialization_manager.reset_initialization()

    # Assert
    assert not mock_service_instance._initialization_complete
    assert mock_service_instance._completed_steps == []
    assert mock_service_instance._error is None
