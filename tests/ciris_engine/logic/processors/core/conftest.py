"""Shared fixtures for core processor tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock

import pytest

from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.schemas.processors.base import ProcessorMetrics
from ciris_engine.schemas.processors.results import (
    DreamResult,
    PlayResult,
    ShutdownResult,
    SolitudeResult,
    WakeupResult,
    WorkResult,
)
from ciris_engine.schemas.processors.states import AgentState


@pytest.fixture
def mock_time_service():
    """Create mock time service."""
    current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    mock_service = Mock()
    mock_service.now.return_value = current_time
    mock_service.now_iso.return_value = current_time.isoformat()
    return mock_service


@pytest.fixture
def mock_config():
    """Create mock config accessor."""
    config = Mock(spec=ConfigAccessor)
    config.get = Mock(
        side_effect=lambda key, default=None: {
            "agent.startup_state": "WAKEUP",
            "agent.max_rounds": 100,
            "agent.round_timeout": 300,
            "agent.state_transition_delay": 1.0,
        }.get(key, default)
    )
    # Add workflow mock for delay calculations
    config.workflow = Mock()
    config.workflow.get_round_delay = Mock(return_value=2.0)
    config.workflow.round_delay_seconds = 1.5
    config.mock_llm = False
    return config


@pytest.fixture
def mock_telemetry_service():
    """Create mock telemetry service for testing."""
    mock_service = Mock()
    mock_service.record_metric = AsyncMock()
    return mock_service


@pytest.fixture
def mock_services(mock_time_service, mock_telemetry_service):
    """Create mock services as ProcessorServices."""
    from ciris_engine.schemas.processors.base import ProcessorServices

    mock_llm = Mock()
    mock_llm.__class__.__name__ = "MockLLMService"

    return ProcessorServices(
        time_service=mock_time_service,
        telemetry_service=mock_telemetry_service,
        memory_service=Mock(
            memorize=AsyncMock(), export_identity_context=AsyncMock(return_value="Test identity context")
        ),
        identity_manager=Mock(get_identity=Mock(return_value={"name": "TestAgent"})),
        resource_monitor=Mock(
            get_current_metrics=Mock(
                return_value={"cpu_percent": 10.0, "memory_percent": 20.0, "disk_usage_percent": 30.0}
            )
        ),
        llm_service=mock_llm,
    )


@pytest.fixture
def mock_processors():
    """Create mock state processors."""
    processors = {}

    # Map states to their specific result types
    result_types = {
        "wakeup": WakeupResult(thoughts_processed=1, wakeup_complete=True, errors=0, duration_seconds=1.0),
        "work": WorkResult(tasks_processed=1, thoughts_processed=1, errors=0, duration_seconds=1.0),
        "play": PlayResult(thoughts_processed=1, errors=0, duration_seconds=1.0),
        "solitude": SolitudeResult(thoughts_processed=1, errors=0, duration_seconds=1.0),
        "dream": DreamResult(thoughts_processed=1, errors=0, duration_seconds=1.0),
        "shutdown": ShutdownResult(tasks_cleaned=1, shutdown_ready=True, errors=0, duration_seconds=1.0),
    }

    for state in ["wakeup", "work", "play", "solitude", "dream", "shutdown"]:
        processor = Mock()
        processor.get_supported_states = Mock(return_value=[getattr(AgentState, state.upper())])
        processor.can_process = Mock(return_value=True)
        processor.initialize = Mock(return_value=True)
        processor.process = AsyncMock(return_value=result_types[state])
        processor.cleanup = Mock(return_value=True)
        processor.get_metrics = Mock(return_value=ProcessorMetrics())
        processors[state] = processor
    return processors


@pytest.fixture
def main_processor(mock_config, mock_services, mock_processors, mock_time_service):
    """Create AgentProcessor instance."""
    # Mock required dependencies
    mock_identity = Mock(agent_id="test_agent", name="TestAgent", purpose="Testing")
    mock_thought_processor = Mock(process_thought=AsyncMock(return_value={"selected_action": "test_action"}))
    mock_action_dispatcher = Mock(dispatch=AsyncMock())

    processor = AgentProcessor(
        app_config=mock_config,
        agent_identity=mock_identity,
        thought_processor=mock_thought_processor,
        action_dispatcher=mock_action_dispatcher,
        services=mock_services,
        startup_channel_id="test_channel",
        time_service=mock_time_service,
        runtime=None,
    )

    # Replace the state processors with our mocks
    processor.wakeup_processor = mock_processors["wakeup"]
    processor.work_processor = mock_processors["work"]
    processor.play_processor = mock_processors["play"]
    processor.solitude_processor = mock_processors["solitude"]
    processor.dream_processor = mock_processors["dream"]
    processor.shutdown_processor = mock_processors["shutdown"]

    # Add required attributes for fallback helper tests
    processor.pipeline_controller = Mock()
    processor.pipeline_controller.get_pipeline_state = Mock()

    return processor


@pytest.fixture
def sample_processing_queue_item():
    """Create a sample ProcessingQueueItem for testing."""
    from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
    from ciris_engine.schemas.runtime.enums import ThoughtType

    content = ThoughtContent(text="Test thought content")
    return ProcessingQueueItem(
        thought_id="test_thought_123",
        source_task_id="test_task_123",
        thought_type=ThoughtType.STANDARD,
        content=content,
        thought_depth=0,
    )


@pytest.fixture
def sample_final_result():
    """Create a sample final result with selected action.

    Mocks a ConscienceApplicationResult which has:
    - final_action: ActionSelectionDMAResult
      - selected_action: HandlerActionType (enum with .value)
    """
    result = Mock()
    # Set up the nested structure: final_action.selected_action.value
    result.final_action = Mock()
    result.final_action.selected_action = Mock()
    result.final_action.selected_action.value = "SPEAK"
    return result


@pytest.fixture
def thought_processor_phase_with_telemetry(mock_telemetry_service, mock_time_service):
    """Create a thought processor phase with telemetry and time service configured."""
    from ciris_engine.logic.processors.core.thought_processor.round_complete import RoundCompletePhase

    phase = RoundCompletePhase()
    phase.telemetry_service = mock_telemetry_service
    phase._time_service = mock_time_service
    phase.current_round_number = 1
    return phase
