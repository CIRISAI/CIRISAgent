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
    # Use spec=[] to ensure no parameters are expected
    pause_mock = AsyncMock(return_value=pause_response, spec=[])
    # Explicitly set the signature to ensure parameter detection works
    pause_mock.__signature__ = inspect.Signature([])
    mock.pause_processing = pause_mock
    
    resume_mock = AsyncMock(return_value=resume_response, spec=[])
    resume_mock.__signature__ = inspect.Signature([])
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
    
    # Add queue status mock for API service - realistic queue with thoughts
    api_queue_status = ProcessorQueueStatus(
        processor_name="main_processor",
        queue_size=3,  # Realistic queue depth with pending thoughts
        max_size=100,
        processing_rate=5.0,
        average_latency_ms=100.0,
        oldest_message_age_seconds=45.0,  # Some thoughts have been waiting
    )
    mock.get_processor_queue_status = AsyncMock(return_value=api_queue_status)
    
    # Add single step functionality for single step endpoint tests
    from ciris_engine.schemas.services.runtime_control import StepPoint
    single_step_response = ProcessorControlResponse(
        success=True,
        processor_name="agent",
        operation="single_step",
        new_status=ProcessorStatus.PAUSED,
        error=None,
        step_point=StepPoint.PERFORM_DMAS.value,  # Use enum value
        step_results=[{
            "round_number": 2, 
            "task_id": "task_001", 
            "step_data": {"dmas_executed": ["ethical", "common_sense"]}
        }],
        thoughts_processed=1,
        processing_time_ms=850.0,
        pipeline_state={
            "current_round": 2, 
            "thoughts_in_pipeline": 1, 
            "is_paused": True
        },
        current_round=2,
        pipeline_empty=False,
    )
    mock.single_step = AsyncMock(return_value=single_step_response)
    
    return mock


@pytest.fixture
def single_step_control_response():
    """Create a ProcessorControlResponse for single step operation with H3ERE data."""
    from ciris_engine.schemas.services.runtime_control import StepPoint
    
    return ProcessorControlResponse(
        success=True,
        processor_name="agent",
        operation="single_step",
        new_status=ProcessorStatus.PAUSED,
        error=None,
        # H3ERE step data - use string values as required by schema
        step_point=StepPoint.PERFORM_DMAS.value,  # "perform_dmas"
        step_results=[
            {
                "step_point": StepPoint.PERFORM_DMAS.value,  # Use enum value for consistency
                "thought_id": "test_thought_1",
                "success": True,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "processing_time_ms": 150.0,
                "ethical_dma": {"decision": "PROCEED", "confidence": 0.85},
                "round_number": 1
            }
        ],
        thoughts_processed=1,
        processing_time_ms=150.0,
        pipeline_state={
            "current_round": 1,
            "thoughts_in_flight": 1,
            "total_thoughts_processed": 1,
            "is_paused": True
        },
        current_round=1,
        pipeline_empty=False
    )


@pytest.fixture
def mock_step_result_perform_dmas():
    """Create a mock step result for PERFORM_DMAS step - reusable across tests."""
    from unittest.mock import MagicMock
    from ciris_engine.schemas.services.runtime_control import StepPoint
    
    mock_result = MagicMock()
    mock_result.step_point = StepPoint.PERFORM_DMAS
    mock_result.success = True
    mock_result.thought_id = "thought_001"
    mock_result.timestamp = "2024-01-01T12:00:00Z"
    mock_result.context = "test context"
    mock_result.processing_time_ms = 800.0
    mock_result.error = None
    
    # Add DMA results as mock attributes
    mock_result.ethical_dma = MagicMock()
    mock_result.ethical_dma.decision = "approve"
    mock_result.ethical_dma.reasoning = "Analyzed ethical implications thoroughly"
    
    mock_result.common_sense_dma = MagicMock()
    mock_result.common_sense_dma.plausibility_score = 0.90
    mock_result.common_sense_dma.reasoning = "Applied common sense principles"
    
    mock_result.domain_dma = MagicMock()
    mock_result.domain_dma.domain = "api_development"
    mock_result.domain_dma.reasoning = "Domain expertise applied"
    
    mock_result.dmas_executed = ["ethical", "common_sense", "domain"]
    mock_result.dma_failures = []
    mock_result.longest_dma_time_ms = 300.0
    mock_result.total_time_ms = 800.0
    
    return mock_result


@pytest.fixture
def mock_step_result_gather_context():
    """Create a mock step result for GATHER_CONTEXT step - reusable across tests."""
    from unittest.mock import MagicMock
    from ciris_engine.schemas.services.runtime_control import StepPoint
    
    mock_result = MagicMock()
    mock_result.step_point = StepPoint.GATHER_CONTEXT
    mock_result.success = True
    mock_result.thought_id = "thought_002"
    mock_result.timestamp = "2024-01-01T12:00:00Z"
    mock_result.context = "gather context test"
    mock_result.processing_time_ms = 200.0
    mock_result.error = None
    
    # Context building specific fields
    mock_result.system_snapshot = {"agent_state": "active", "services": 25}
    mock_result.agent_identity = {"agent_id": "test_agent", "role": "assistant"}
    mock_result.thought_context = {"user_id": "test_user", "channel": "test_channel"}
    mock_result.channel_context = {"type": "discord", "permissions": ["read", "write"]}
    mock_result.memory_context = {"relevant_memories": 3}
    mock_result.permitted_actions = ["speak", "observe"]
    mock_result.constraints = ["no_harmful_content"]
    mock_result.context_size_bytes = 2048
    mock_result.memory_queries_performed = 2
    
    return mock_result