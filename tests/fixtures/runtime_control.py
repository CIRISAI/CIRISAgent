"""Runtime control fixtures for API testing."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock
import inspect

import pytest

from ciris_engine.schemas.services.core.runtime import (
    RuntimeStatusResponse,
    ProcessorControlResponse,
    ProcessorStatus,
    ProcessorQueueStatus,
)


@pytest.fixture
def runtime_status_running():
    """Create a RuntimeStatusResponse for a running system."""
    return RuntimeStatusResponse(
        is_running=True,
        uptime_seconds=100.0,
        processor_count=1,
        adapter_count=1,
        total_messages_processed=50,
        current_load=0.3,
        processor_status=ProcessorStatus.RUNNING,
        cognitive_state="WORK",
        queue_depth=3,
    )


@pytest.fixture
def runtime_status_paused():
    """Create a RuntimeStatusResponse for a paused system."""
    return RuntimeStatusResponse(
        is_running=True,
        uptime_seconds=200.0,
        processor_count=1,
        adapter_count=1,
        total_messages_processed=100,
        current_load=0.1,
        processor_status=ProcessorStatus.PAUSED,
        cognitive_state="PAUSED",
        queue_depth=0,
    )


@pytest.fixture
def runtime_status_dream():
    """Create a RuntimeStatusResponse with DREAM cognitive state."""
    return RuntimeStatusResponse(
        is_running=True,
        uptime_seconds=300.0,
        processor_count=1,
        adapter_count=1,
        total_messages_processed=200,
        current_load=0.2,
        processor_status=ProcessorStatus.PAUSED,
        cognitive_state="DREAM",
        queue_depth=5,
    )


@pytest.fixture
def runtime_status_no_cognitive_state():
    """Create a RuntimeStatusResponse with no cognitive state (None)."""
    return RuntimeStatusResponse(
        is_running=True,
        uptime_seconds=150.0,
        processor_count=1,
        adapter_count=1,
        total_messages_processed=75,
        current_load=0.4,
        processor_status=ProcessorStatus.RUNNING,
        cognitive_state=None,
        queue_depth=1,
    )


@pytest.fixture
def pause_control_response():
    """Create a ProcessorControlResponse for pause operation."""
    return ProcessorControlResponse(
        success=True,
        processor_name="main_processor",
        operation="pause",
        new_status=ProcessorStatus.PAUSED,
    )


@pytest.fixture
def resume_control_response():
    """Create a ProcessorControlResponse for resume operation."""
    return ProcessorControlResponse(
        success=True,
        processor_name="main_processor",
        operation="resume",
        new_status=ProcessorStatus.RUNNING,
    )


@pytest.fixture
def mock_main_runtime_control_service():
    """Create a fully-featured mock main runtime control service with proper schemas."""
    mock = AsyncMock()
    
    # Create proper schema objects directly
    running_status = RuntimeStatusResponse(
        is_running=True,
        uptime_seconds=100.0,
        processor_count=1,
        adapter_count=1,
        total_messages_processed=50,
        current_load=0.3,
        processor_status=ProcessorStatus.RUNNING,
        cognitive_state="WORK",
        queue_depth=3,
    )
    
    pause_response = ProcessorControlResponse(
        success=True,
        processor_name="main_processor",
        operation="pause",
        new_status=ProcessorStatus.PAUSED,
    )
    
    resume_response = ProcessorControlResponse(
        success=True,
        processor_name="main_processor",
        operation="resume",
        new_status=ProcessorStatus.RUNNING,
    )
    
    # Configure mock methods
    mock.get_runtime_status = AsyncMock(return_value=running_status)
    
    # Create AsyncMock with empty signature for main service
    pause_mock = AsyncMock(return_value=pause_response)
    pause_mock.__signature__ = inspect.signature(lambda: None)
    mock.pause_processing = pause_mock
    
    resume_mock = AsyncMock(return_value=resume_response) 
    resume_mock.__signature__ = inspect.signature(lambda: None)
    mock.resume_processing = resume_mock
    
    # Add queue status mock
    queue_status = ProcessorQueueStatus(
        processor_name="main_processor",
        queue_size=5,
        max_size=100,
        processing_rate=10.0,
        average_latency_ms=150.0,
        oldest_message_age_seconds=30.0,
    )
    mock.get_processor_queue_status = AsyncMock(return_value=queue_status)
    
    return mock


@pytest.fixture
def mock_api_runtime_control_service():
    """Create a parameter-based mock API runtime control service with proper schemas."""
    mock = AsyncMock()
    
    # Create paused status directly
    paused_status = RuntimeStatusResponse(
        is_running=True,
        uptime_seconds=200.0,
        processor_count=1,
        adapter_count=1,
        total_messages_processed=100,
        current_load=0.1,
        processor_status=ProcessorStatus.PAUSED,
        cognitive_state="PAUSED",
        queue_depth=0,
    )
    
    # API service uses different interface (takes parameters, returns booleans)
    mock.pause_processing = AsyncMock(return_value=True)
    mock.resume_processing = AsyncMock(return_value=True)
    
    # Status method returns proper schema
    mock.get_runtime_status = AsyncMock(return_value=paused_status)
    
    # Add queue status mock for API service
    api_queue_status = ProcessorQueueStatus(
        processor_name="main_processor",
        queue_size=0,
        max_size=100,
        processing_rate=5.0,
        average_latency_ms=100.0,
        oldest_message_age_seconds=None,
    )
    mock.get_processor_queue_status = AsyncMock(return_value=api_queue_status)
    
    return mock