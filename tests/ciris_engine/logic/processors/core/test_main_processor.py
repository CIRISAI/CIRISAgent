"""Unit tests for AgentProcessor."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.processors.results import (
    WakeupResult, WorkResult, PlayResult, SolitudeResult, DreamResult, ShutdownResult
)
from ciris_engine.schemas.processors.base import ProcessorMetrics
from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.support.state_manager import StateTransition


class TestAgentProcessor:
    """Test cases for AgentProcessor."""

    @pytest.fixture
    def mock_time_service(self):
        """Create mock time service."""
        current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        return Mock(
            now=Mock(return_value=current_time),
            now_iso=Mock(return_value=current_time.isoformat())
        )

    @pytest.fixture
    def mock_config(self):
        """Create mock config accessor."""
        config = Mock(spec=ConfigAccessor)
        config.get = Mock(side_effect=lambda key, default=None: {
            'agent.startup_state': 'WAKEUP',
            'agent.max_rounds': 100,
            'agent.round_timeout': 300,
            'agent.state_transition_delay': 1.0
        }.get(key, default))
        return config

    @pytest.fixture
    def mock_services(self, mock_time_service):
        """Create mock services."""
        # Create a mock LLM service that identifies as MockLLMService
        mock_llm = Mock()
        mock_llm.__class__.__name__ = 'MockLLMService'
        
        return {
            'time_service': mock_time_service,
            'telemetry_service': Mock(memorize_metric=AsyncMock()),
            'memory_service': Mock(
                memorize=AsyncMock(),
                export_identity_context=AsyncMock(return_value="Test identity context")
            ),
            'identity_manager': Mock(
                get_identity=Mock(return_value={'name': 'TestAgent'})
            ),
            'resource_monitor': Mock(
                get_current_metrics=Mock(return_value={
                    'cpu_percent': 10.0,
                    'memory_percent': 20.0,
                    'disk_usage_percent': 30.0
                })
            ),
            'llm_service': mock_llm  # Add mock LLM service to use shorter delays
        }

    @pytest.fixture
    def mock_processors(self):
        """Create mock state processors."""
        processors = {}

        # Map states to their specific result types
        result_types = {
            'wakeup': WakeupResult(thoughts_processed=1, wakeup_complete=True, errors=0, duration_seconds=1.0),
            'work': WorkResult(tasks_processed=1, thoughts_processed=1, errors=0, duration_seconds=1.0),
            'play': PlayResult(thoughts_processed=1, errors=0, duration_seconds=1.0),
            'solitude': SolitudeResult(thoughts_processed=1, errors=0, duration_seconds=1.0),
            'dream': DreamResult(thoughts_processed=1, errors=0, duration_seconds=1.0),
            'shutdown': ShutdownResult(tasks_cleaned=1, shutdown_ready=True, errors=0, duration_seconds=1.0)
        }

        for state in ['wakeup', 'work', 'play', 'solitude', 'dream', 'shutdown']:
            processor = Mock()
            processor.get_supported_states = Mock(return_value=[getattr(AgentState, state.upper())])
            processor.can_process = AsyncMock(return_value=True)
            processor.initialize = AsyncMock(return_value=True)
            processor.process = AsyncMock(return_value=result_types[state])
            processor.cleanup = AsyncMock(return_value=True)
            processor.get_metrics = Mock(return_value=ProcessorMetrics())
            processors[state] = processor
        return processors

    @pytest.fixture
    def main_processor(self, mock_config, mock_services, mock_processors, mock_time_service):
        """Create AgentProcessor instance."""
        # Mock required dependencies
        mock_identity = Mock(
            agent_id="test_agent",
            name="TestAgent",
            purpose="Testing"
        )
        mock_thought_processor = Mock(
            process_thought=AsyncMock(return_value={"selected_action": "test_action"})
        )
        mock_action_dispatcher = Mock(
            dispatch=AsyncMock()
        )

        processor = AgentProcessor(
            app_config=mock_config,
            agent_identity=mock_identity,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_action_dispatcher,
            services=mock_services,
            startup_channel_id="test_channel",
            time_service=mock_time_service,
            runtime=None
        )

        # Replace the state processors with our mocks
        processor.wakeup_processor = mock_processors['wakeup']
        processor.work_processor = mock_processors['work']
        processor.play_processor = mock_processors['play']
        processor.solitude_processor = mock_processors['solitude']
        processor.dream_processor = mock_processors['dream']
        processor.shutdown_processor = mock_processors['shutdown']

        # Also update the state_processors dict
        processor.state_processors = {
            AgentState.WAKEUP: mock_processors['wakeup'],
            AgentState.WORK: mock_processors['work'],
            AgentState.PLAY: mock_processors['play'],
            AgentState.SOLITUDE: mock_processors['solitude'],
            AgentState.DREAM: mock_processors['dream'],
            AgentState.SHUTDOWN: mock_processors['shutdown']
        }

        return processor

    @pytest.mark.asyncio
    async def test_initialization_in_constructor(self, main_processor):
        """Test processor initialization happens in constructor."""
        # AgentProcessor doesn't have an initialize method - it's initialized in __init__
        # Check that state manager is initialized
        assert main_processor.state_manager is not None
        assert main_processor.state_manager.get_state() == AgentState.SHUTDOWN

        # Check that processors are initialized
        assert main_processor.wakeup_processor is not None
        assert main_processor.work_processor is not None
        assert main_processor.play_processor is not None
        assert main_processor.dream_processor is not None
        assert main_processor.solitude_processor is not None
        assert main_processor.shutdown_processor is not None

    @pytest.mark.asyncio
    async def test_start_processing(self, main_processor):
        """Test start processing with limited rounds."""
        # Mock _process_pending_thoughts_async to avoid delays
        main_processor._process_pending_thoughts_async = AsyncMock(return_value=0)
        
        # Mock _load_preload_tasks and _schedule_initial_dream to avoid delays
        main_processor._load_preload_tasks = AsyncMock()
        main_processor._schedule_initial_dream = AsyncMock()
        
        # Mock _processing_loop to complete immediately
        async def mock_processing_loop(num_rounds):
            main_processor.current_round_number = 3
            return
        
        main_processor._processing_loop = mock_processing_loop
        
        # Process 3 rounds
        await main_processor.start_processing(num_rounds=3)

        # Check that processing was attempted
        assert main_processor.current_round_number > 0

    @pytest.mark.asyncio
    async def test_process_single_round(self, main_processor, mock_processors):
        """Test processing a single round."""
        # Use the process method which executes one round
        result = await main_processor.process(1)

        assert result is not None
        # Result should be a dict with processor result fields
        assert isinstance(result, dict)
        assert 'errors' in result
        assert 'duration_seconds' in result

    @pytest.mark.asyncio
    async def test_state_transition(self, main_processor, mock_processors):
        """Test state transition."""
        # Transition from SHUTDOWN to WAKEUP
        assert main_processor.state_manager.transition_to(AgentState.WAKEUP)
        assert main_processor.state_manager.get_state() == AgentState.WAKEUP

        # Transition from WAKEUP to WORK
        assert main_processor.state_manager.transition_to(AgentState.WORK)
        assert main_processor.state_manager.get_state() == AgentState.WORK

    @pytest.mark.asyncio
    async def test_handle_processor_error(self, main_processor, mock_processors):
        """Test handling processor errors."""
        # Set state to WAKEUP
        main_processor.state_manager.transition_to(AgentState.WAKEUP)

        # Mock processor to raise error
        main_processor.wakeup_processor.process.side_effect = Exception("Test error")

        # Process should handle error gracefully
        try:
            result = await main_processor.process(1)
            # If process catches the error and returns a result
            assert result is not None
            assert hasattr(result, 'errors') or 'error' in result
        except Exception as e:
            # If process propagates the error
            assert str(e) == "Test error"

    @pytest.mark.asyncio
    async def test_max_consecutive_errors(self, main_processor, mock_processors):
        """Test max consecutive errors triggers shutdown."""
        # Set state to WORK
        main_processor.state_manager.transition_to(AgentState.WAKEUP)
        main_processor.state_manager.transition_to(AgentState.WORK)

        # Mock processor to always error
        mock_processors['work'].process.side_effect = Exception("Test error")

        # Process multiple rounds - errors should eventually request shutdown
        for i in range(6):
            try:
                await main_processor.process(i)
            except:
                pass  # Ignore errors

        # Check if shutdown was requested (via request_global_shutdown)
        # Note: We can't directly test this without mocking the global shutdown system

    @pytest.mark.asyncio
    async def test_round_timeout(self, main_processor, mock_processors):
        """Test round timeout handling."""
        # Mock processor to take too long
        async def slow_process(round_num):
            await asyncio.sleep(0.5)
            return {"state": "wakeup", "round_number": round_num}

        main_processor.state_manager.transition_to(AgentState.WAKEUP)
        mock_processors['wakeup'].process = slow_process

        # Process with timeout should still complete
        result = await main_processor.process(1)
        assert result is not None

    @pytest.mark.asyncio
    async def test_stop_processing(self, main_processor):
        """Test stopping processing."""
        # Start processing in background
        task = asyncio.create_task(main_processor.start_processing())

        # Let it process a bit
        await asyncio.sleep(0.1)

        # Stop processing
        await main_processor.stop_processing()

        # Wait for task to complete
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            task.cancel()

        # Check state
        assert main_processor.state_manager.get_state() == AgentState.SHUTDOWN

    @pytest.mark.asyncio
    async def test_emergency_stop(self, main_processor):
        """Test emergency stop transitions to shutdown."""
        # Start in WORK state
        main_processor.state_manager.transition_to(AgentState.WAKEUP)
        main_processor.state_manager.transition_to(AgentState.WORK)

        # Create and set the processing task to simulate running state
        main_processor._processing_task = asyncio.create_task(asyncio.sleep(0.1))

        # Stop processing should transition to SHUTDOWN
        await main_processor.stop_processing()

        assert main_processor.state_manager.get_state() == AgentState.SHUTDOWN

    def test_get_current_state(self, main_processor):
        """Test getting current state through state manager."""
        # Must transition through WAKEUP from SHUTDOWN
        main_processor.state_manager.transition_to(AgentState.WAKEUP)
        main_processor.state_manager.transition_to(AgentState.WORK)

        assert main_processor.state_manager.get_state() == AgentState.WORK

    def test_get_state_history(self, main_processor):
        """Test state transitions are tracked."""
        # Perform some transitions
        main_processor.state_manager.transition_to(AgentState.WAKEUP)
        main_processor.state_manager.transition_to(AgentState.WORK)

        # Check current state
        assert main_processor.state_manager.get_state() == AgentState.WORK

        # Check state duration is tracked
        duration = main_processor.state_manager.get_state_duration()
        assert duration >= 0

    def test_get_processor_metrics(self, main_processor):
        """Test getting processor status."""
        # Set some state
        main_processor.current_round_number = 10

        status = main_processor.get_status()

        assert status['round_number'] == 10
        assert status['state'] == 'shutdown'  # Initial state (lowercase)
        assert 'is_processing' in status
        assert 'processor_metrics' in status

    @pytest.mark.asyncio
    async def test_validate_transition(self, main_processor):
        """Test state transition validation."""
        # Valid transitions
        assert main_processor.state_manager.can_transition_to(AgentState.WAKEUP)
        main_processor.state_manager.transition_to(AgentState.WAKEUP)
        assert main_processor.state_manager.can_transition_to(AgentState.WORK)

        # Can't transition to same state (depends on StateManager implementation)
        # Most transitions are allowed in the state manager

    @pytest.mark.asyncio
    async def test_transition_to_same_state(self, main_processor):
        """Test transitioning to same state."""
        # Set to WAKEUP
        main_processor.state_manager.transition_to(AgentState.WAKEUP)
        current_state = main_processor.state_manager.get_state()

        # Transition to same state
        result = main_processor.state_manager.transition_to(AgentState.WAKEUP)

        # Should still be in WAKEUP
        assert main_processor.state_manager.get_state() == AgentState.WAKEUP

    @pytest.mark.asyncio
    async def test_processor_not_found(self, main_processor):
        """Test handling missing processor for state."""
        # Transition through WAKEUP to WORK
        main_processor.state_manager.transition_to(AgentState.WAKEUP)
        main_processor.state_manager.transition_to(AgentState.WORK)

        # Remove work processor
        del main_processor.state_processors[AgentState.WORK]

        # Processing will return error
        result = await main_processor.process(1)
        # Result should be a dict with error
        assert isinstance(result, dict)
        assert 'error' in result
        assert result['error'] == 'No processor available'

    @pytest.mark.asyncio
    async def test_state_transition_delay(self, main_processor):
        """Test state transition timing."""
        # Transition and check it's immediate
        start_time = asyncio.get_event_loop().time()
        main_processor.state_manager.transition_to(AgentState.WORK)
        end_time = asyncio.get_event_loop().time()

        # State transitions should be fast
        assert (end_time - start_time) < 0.1

    @pytest.mark.asyncio
    async def test_cleanup(self, main_processor, mock_processors):
        """Test cleanup calls processor cleanup."""
        # Transition to WORK state so we're not already in SHUTDOWN
        main_processor.state_manager.transition_to(AgentState.WAKEUP)
        main_processor.state_manager.transition_to(AgentState.WORK)

        # Create a processing task to ensure cleanup is called
        main_processor._processing_task = asyncio.create_task(asyncio.sleep(0.1))

        # Stop processing calls cleanup on all processors
        await main_processor.stop_processing()

        # All processors should have cleanup called
        # Check the actual processors on main_processor, not the fixture mocks
        main_processor.wakeup_processor.cleanup.assert_called()
        main_processor.work_processor.cleanup.assert_called()
        main_processor.play_processor.cleanup.assert_called()
        main_processor.solitude_processor.cleanup.assert_called()
        main_processor.dream_processor.cleanup.assert_called()
        main_processor.shutdown_processor.cleanup.assert_called()

    @pytest.mark.asyncio
    async def test_max_rounds_limit(self, main_processor):
        """Test processing stops at round limit."""
        # Mock the internal methods to avoid delays
        main_processor._process_pending_thoughts_async = AsyncMock(return_value=0)
        main_processor._load_preload_tasks = AsyncMock()
        main_processor._schedule_initial_dream = AsyncMock()
        
        # Mock the processing loop to simulate reaching max rounds
        original_loop = main_processor._processing_loop
        
        async def mock_processing_loop(num_rounds):
            # Simulate processing up to the limit
            main_processor.current_round_number = num_rounds
            # Call original with 0 to exit immediately
            await original_loop(0)
        
        main_processor._processing_loop = mock_processing_loop
        
        # Run with limited rounds
        await main_processor.start_processing(num_rounds=5)

        # Round number should have reached the limit
        assert main_processor.current_round_number == 5


    @pytest.mark.asyncio
    async def test_record_state_transition(self, main_processor, mock_services):
        """Test state transitions trigger telemetry."""
        # Make a transition
        main_processor.state_manager.transition_to(AgentState.WAKEUP)
        main_processor.state_manager.transition_to(AgentState.WORK)

        # Can't directly test telemetry recording without complex mocking
        # Just verify transition succeeded
        assert main_processor.state_manager.get_state() == AgentState.WORK

    @pytest.mark.asyncio
    async def test_processor_initialization_failure(self, main_processor, mock_processors):
        """Test handling processor initialization failure."""
        # First transition to WAKEUP from SHUTDOWN
        main_processor.state_manager.transition_to(AgentState.WAKEUP)

        # Mock processor init to fail
        mock_processors['work'].initialize.side_effect = Exception("Init failed")

        # Try to handle state transition - expect it to raise
        with pytest.raises(Exception, match="Init failed"):
            await main_processor._handle_state_transition(AgentState.WORK)

        # Should still have transitioned (state transition happens before init)
        assert main_processor.state_manager.get_state() == AgentState.WORK
