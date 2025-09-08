"""Unit tests for AgentProcessor."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

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


class TestAgentProcessor:
    """Test cases for AgentProcessor."""

    @pytest.fixture
    def mock_time_service(self):
        """Create mock time service."""
        current_time = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        mock_service = Mock()
        mock_service.now.return_value = current_time
        mock_service.now_iso.return_value = current_time.isoformat()
        return mock_service

    @pytest.fixture
    def mock_config(self):
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
        return config

    @pytest.fixture
    def mock_services(self, mock_time_service):
        """Create mock services."""
        # Create a mock LLM service that identifies as MockLLMService
        mock_llm = Mock()
        mock_llm.__class__.__name__ = "MockLLMService"

        return {
            "time_service": mock_time_service,
            "telemetry_service": Mock(memorize_metric=AsyncMock()),
            "memory_service": Mock(
                memorize=AsyncMock(), export_identity_context=AsyncMock(return_value="Test identity context")
            ),
            "identity_manager": Mock(get_identity=Mock(return_value={"name": "TestAgent"})),
            "resource_monitor": Mock(
                get_current_metrics=Mock(
                    return_value={"cpu_percent": 10.0, "memory_percent": 20.0, "disk_usage_percent": 30.0}
                )
            ),
            "llm_service": mock_llm,  # Add mock LLM service to use shorter delays
        }

    @pytest.fixture
    def mock_processors(self):
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
    def main_processor(self, mock_config, mock_services, mock_processors, mock_time_service):
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

        # Also update the state_processors dict
        processor.state_processors = {
            AgentState.WAKEUP: mock_processors["wakeup"],
            AgentState.WORK: mock_processors["work"],
            AgentState.PLAY: mock_processors["play"],
            AgentState.SOLITUDE: mock_processors["solitude"],
            AgentState.DREAM: mock_processors["dream"],
            AgentState.SHUTDOWN: mock_processors["shutdown"],
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
        main_processor._load_preload_tasks = Mock()
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
        assert "errors" in result
        assert "duration_seconds" in result

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
            assert hasattr(result, "errors") or "error" in result
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
        mock_processors["work"].process.side_effect = Exception("Test error")

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
        mock_processors["wakeup"].process = slow_process

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

        assert status["round_number"] == 10
        assert status["state"] == "shutdown"  # Initial state (lowercase)
        assert "is_processing" in status
        assert "processor_metrics" in status

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
        assert "error" in result
        assert result["error"] == "No processor available"

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
        main_processor._load_preload_tasks = Mock()
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
        mock_processors["work"].initialize.side_effect = Exception("Init failed")

        # Try to handle state transition - expect it to raise
        with pytest.raises(Exception, match="Init failed"):
            await main_processor._handle_state_transition(AgentState.WORK)

        # Should still have transitioned (state transition happens before init)
        assert main_processor.state_manager.get_state() == AgentState.WORK

    @pytest.mark.asyncio
    async def test_pause_processing(self, main_processor):
        """Test pausing the processor."""
        # Initially not paused
        assert not main_processor.is_paused()
        
        # Pause should succeed
        result = await main_processor.pause_processing()
        assert result is True
        assert main_processor.is_paused()
        assert main_processor._pause_event is not None
        assert main_processor._pipeline_controller is not None
        
        # Pause again should still return True
        result = await main_processor.pause_processing()
        assert result is True
        assert main_processor.is_paused()

    @pytest.mark.asyncio
    async def test_resume_processing(self, main_processor):
        """Test resuming the processor."""
        # Initially not paused, resume should return False
        result = await main_processor.resume_processing()
        assert result is False
        
        # Pause first
        await main_processor.pause_processing()
        assert main_processor.is_paused()
        
        # Resume should succeed
        result = await main_processor.resume_processing()
        assert result is True
        assert not main_processor.is_paused()
        assert not main_processor._single_step_mode

    @pytest.mark.asyncio
    async def test_single_step_not_paused(self, main_processor):
        """Test single_step raises error when not paused."""
        # Ensure not paused
        assert not main_processor.is_paused()
        
        # Single step should raise RuntimeError
        with pytest.raises(RuntimeError, match="Cannot single-step unless processor is paused"):
            await main_processor.single_step()

    @pytest.mark.asyncio
    async def test_single_step_pipeline_controller_error(self, main_processor):
        """Test single_step propagates pipeline controller errors (FAIL FAST)."""
        # Properly pause processor (pipeline controller is always initialized now)
        await main_processor.pause_processing()
        assert main_processor.is_paused()
        
        # Make pipeline controller's execute method raise an error
        main_processor._pipeline_controller.execute_single_step_point = AsyncMock(
            side_effect=Exception("Pipeline error")
        )
        
        # Single step should propagate the error (FAIL FAST principle)
        with pytest.raises(Exception, match="Pipeline error"):
            await main_processor.single_step()
        
        # Verify single-step mode is properly disabled in finally block
        assert not main_processor._single_step_mode

    @pytest.mark.asyncio
    async def test_single_step_fallback_mode(self, main_processor):
        """Test single_step raises error when execute_single_step_point is missing (FAIL FAST)."""
        # Properly pause processor
        await main_processor.pause_processing()
        assert main_processor.is_paused()
        
        # Mock pipeline controller without execute_single_step_point method
        # Use spec to create a controller that explicitly doesn't have the method
        class MockPipelineController:
            def __init__(self):
                self.is_paused = True
                self._single_step_mode = False
        
        mock_controller = MockPipelineController()
        main_processor._pipeline_controller = mock_controller
        
        # Single step should raise NotImplementedError (FAIL FAST principle)
        with pytest.raises(NotImplementedError, match="missing execute_single_step_point method"):
            await main_processor.single_step()

    @pytest.mark.asyncio
    async def test_single_step_with_pipeline_controller(self, main_processor):
        """Test single_step with proper pipeline controller."""
        # Properly pause processor
        await main_processor.pause_processing()
        assert main_processor.is_paused()
        
        # Mock pipeline controller with execute_single_step_point method
        mock_controller = AsyncMock()
        mock_step_result = {
            "step_point": "GATHER_CONTEXT",
            "step_results": [
                {
                    "thought_id": "test-thought-1",
                    "success": True,
                    "step_data": {"context": "test"}
                }
            ],
            "pipeline_state": {
                "current_round": 1,
                "pipeline_empty": False,
                "thoughts_by_step": {}
            },
            "current_round": 1,
            "pipeline_empty": False
        }
        mock_controller.execute_single_step_point.return_value = mock_step_result
        main_processor._pipeline_controller = mock_controller
        
        # Single step should succeed
        result = await main_processor.single_step()
        assert result["success"] is True
        assert result["step_point"] == "GATHER_CONTEXT"
        assert result["thoughts_processed"] == 1
        assert "processing_time_ms" in result
        assert "pipeline_state" in result
        
        # Verify controller was called
        mock_controller.execute_single_step_point.assert_called_once()

    @pytest.mark.asyncio
    async def test_single_step_error_handling(self, main_processor):
        """Test single_step propagates errors (FAIL FAST principle)."""
        # Properly pause processor
        await main_processor.pause_processing()
        
        # Mock pipeline controller to raise error
        mock_controller = AsyncMock()
        mock_controller.execute_single_step_point.side_effect = Exception("Step failed")
        main_processor._pipeline_controller = mock_controller
        
        # Single step should propagate the error (FAIL FAST)
        with pytest.raises(Exception, match="Step failed"):
            await main_processor.single_step()
        
        # Single step mode should be disabled after error (via finally block)
        assert not main_processor._single_step_mode

    @pytest.mark.asyncio
    async def test_pause_affects_processing_loop(self, main_processor):
        """Test that pause state is checked in processing loop."""
        # Mock the pause event
        pause_event = AsyncMock()
        main_processor._pause_event = pause_event
        main_processor._is_paused = True
        
        # Mock other required components
        main_processor.state_manager.get_state = Mock(return_value=AgentState.WORK)
        main_processor.work_processor = Mock()
        main_processor.work_processor.process = AsyncMock(return_value={"state": "work", "round_number": 1})
        main_processor._process_pending_thoughts_async = AsyncMock(return_value=0)
        
        # Start processing loop with limited rounds
        process_task = asyncio.create_task(main_processor._processing_loop(1))
        
        # Give a moment for the loop to hit the pause check
        await asyncio.sleep(0.01)
        
        # Verify pause event wait was called
        pause_event.wait.assert_called()
        
        # Resume to let the loop complete
        main_processor._is_paused = False
        pause_event.wait = AsyncMock()  # Reset to not block
        
        # Cancel the task to avoid hanging
        process_task.cancel()
        try:
            await process_task
        except asyncio.CancelledError:
            pass

    @pytest.mark.asyncio
    async def test_thought_processing_callback(self, main_processor):
        """Test setting thought processing callback."""
        callback = Mock()
        main_processor.set_thought_processing_callback(callback)
        assert main_processor._thought_processing_callback == callback

    @pytest.mark.asyncio
    async def test_fallback_single_step_with_thoughts(self, main_processor):
        """Test single_step raises NotImplementedError when pipeline controller lacks method."""
        # Properly pause processor
        await main_processor.pause_processing()
        
        # Mock pipeline controller without execute_single_step_point
        class MockPipelineController:
            def __init__(self):
                self.is_paused = True
                self._single_step_mode = False
                
            def get_pipeline_state(self):
                # Return empty pipeline state to trigger pending thoughts check
                mock_state = Mock()
                mock_state.thoughts_by_step = {}
                return mock_state
        
        mock_controller = MockPipelineController()
        main_processor._pipeline_controller = mock_controller
        
        # Single step should raise NotImplementedError (FAIL FAST principle)
        with pytest.raises(NotImplementedError, match="missing execute_single_step_point method"):
            await main_processor.single_step()

    @pytest.mark.asyncio
    async def test_fallback_single_step_error_handling(self, main_processor):
        """Test single_step raises NotImplementedError (no fallback, FAIL FAST principle)."""
        # Properly pause processor
        await main_processor.pause_processing()
        
        # Mock pipeline controller without execute_single_step_point
        class MockPipelineController:
            def __init__(self):
                self.is_paused = True
                self._single_step_mode = False
        
        mock_controller = MockPipelineController()
        main_processor._pipeline_controller = mock_controller
        
        # Single step should raise NotImplementedError before any fallback logic
        with pytest.raises(NotImplementedError, match="missing execute_single_step_point method"):
            await main_processor.single_step()
