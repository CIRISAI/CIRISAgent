"""Unit tests for AgentProcessor helper methods created during complexity refactoring."""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.config import ConfigAccessor
from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.schemas.processors.states import AgentState


class TestAgentProcessorHelpers:
    """Test cases for AgentProcessor helper methods."""

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
        # Add workflow mock for delay calculations
        config.workflow = Mock()
        config.workflow.get_round_delay = Mock(return_value=2.0)
        config.workflow.round_delay_seconds = 1.5
        config.mock_llm = False
        return config

    @pytest.fixture
    def mock_services(self, mock_time_service):
        """Create mock services."""
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
            "llm_service": mock_llm,
        }

    @pytest.fixture
    def mock_processors(self):
        """Create mock state processors."""
        processors = {}
        
        for state in ["wakeup", "work", "play", "solitude", "dream", "shutdown"]:
            processor = Mock()
            processor.process = AsyncMock(return_value={"state": state, "success": True})
            processors[state] = processor
        return processors

    @pytest.fixture
    def main_processor(self, mock_config, mock_services, mock_processors, mock_time_service):
        """Create AgentProcessor instance."""
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

    # Tests for _check_pause_state
    @pytest.mark.asyncio
    async def test_check_pause_state_not_paused(self, main_processor):
        """Test _check_pause_state when not paused."""
        main_processor._is_paused = False
        result = await main_processor._check_pause_state()
        assert result is True

    @pytest.mark.asyncio
    async def test_check_pause_state_paused_with_event(self, main_processor):
        """Test _check_pause_state when paused with event."""
        main_processor._is_paused = True
        main_processor._pause_event = AsyncMock()
        
        # Mock the event to resolve immediately
        main_processor._pause_event.wait = AsyncMock()
        main_processor._pause_event.clear = Mock()
        
        result = await main_processor._check_pause_state()
        
        assert result is True
        main_processor._pause_event.wait.assert_called_once()
        main_processor._pause_event.clear.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_pause_state_paused_no_event(self, main_processor):
        """Test _check_pause_state when paused without event (fallback)."""
        main_processor._is_paused = True
        main_processor._pause_event = None
        
        with patch('asyncio.sleep') as mock_sleep:
            mock_sleep.return_value = None  # Make sleep non-blocking
            result = await main_processor._check_pause_state()
            
        assert result is False
        mock_sleep.assert_called_once_with(0.1)

    # Tests for _handle_shutdown_transitions
    @pytest.mark.asyncio
    async def test_handle_shutdown_transitions_already_shutdown(self, main_processor):
        """Test _handle_shutdown_transitions when already in SHUTDOWN."""
        result = await main_processor._handle_shutdown_transitions(AgentState.SHUTDOWN)
        assert result is True

    @pytest.mark.asyncio
    async def test_handle_shutdown_transitions_shutdown_requested(self, main_processor):
        """Test _handle_shutdown_transitions when shutdown is requested."""
        with patch('ciris_engine.logic.processors.core.main_processor.is_global_shutdown_requested', return_value=True), \
             patch('ciris_engine.logic.processors.core.main_processor.get_global_shutdown_reason', return_value="Test reason"):
            
            main_processor.state_manager.can_transition_to = Mock(return_value=True)
            main_processor._handle_state_transition = AsyncMock()
            
            result = await main_processor._handle_shutdown_transitions(AgentState.WORK)
            
            assert result is True
            main_processor._handle_state_transition.assert_called_once_with(AgentState.SHUTDOWN)

    @pytest.mark.asyncio
    async def test_handle_shutdown_transitions_cannot_transition(self, main_processor):
        """Test _handle_shutdown_transitions when transition to SHUTDOWN fails."""
        with patch('ciris_engine.logic.processors.core.main_processor.is_global_shutdown_requested', return_value=True), \
             patch('ciris_engine.logic.processors.core.main_processor.get_global_shutdown_reason', return_value="Test reason"):
            
            main_processor.state_manager.can_transition_to = Mock(return_value=False)
            
            result = await main_processor._handle_shutdown_transitions(AgentState.WORK)
            
            assert result is False

    @pytest.mark.asyncio
    async def test_handle_shutdown_transitions_auto_transition(self, main_processor):
        """Test _handle_shutdown_transitions with auto transition."""
        with patch('ciris_engine.logic.processors.core.main_processor.is_global_shutdown_requested', return_value=False):
            
            main_processor.state_manager.should_auto_transition = Mock(return_value=AgentState.PLAY)
            main_processor._handle_state_transition = AsyncMock()
            
            result = await main_processor._handle_shutdown_transitions(AgentState.WORK)
            
            assert result is True
            main_processor._handle_state_transition.assert_called_once_with(AgentState.PLAY)

    # Tests for _process_regular_state
    @pytest.mark.asyncio
    async def test_process_regular_state_success(self, main_processor, mock_processors):
        """Test _process_regular_state successful processing."""
        processor = mock_processors["work"]
        processor.process.return_value = {"success": True}
        main_processor._check_scheduled_dream = AsyncMock(return_value=False)
        
        round_increment, consecutive_errors, should_break = await main_processor._process_regular_state(
            processor, AgentState.WORK, 0, 5
        )
        
        assert round_increment == 1
        assert consecutive_errors == 0
        assert should_break is False
        processor.process.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_regular_state_work_with_dream_transition(self, main_processor, mock_processors):
        """Test _process_regular_state in WORK state triggering dream transition."""
        processor = mock_processors["work"]
        processor.process.return_value = {"success": True}
        main_processor._check_scheduled_dream = AsyncMock(return_value=True)
        main_processor._handle_state_transition = AsyncMock()
        
        round_increment, consecutive_errors, should_break = await main_processor._process_regular_state(
            processor, AgentState.WORK, 0, 5
        )
        
        assert round_increment == 1
        assert consecutive_errors == 0
        assert should_break is False
        main_processor._handle_state_transition.assert_called_once_with(AgentState.DREAM)

    @pytest.mark.asyncio
    async def test_process_regular_state_solitude_with_exit(self, main_processor, mock_processors):
        """Test _process_regular_state in SOLITUDE state with exit condition."""
        processor = mock_processors["solitude"]
        result_mock = Mock()
        result_mock.should_exit_solitude = True
        result_mock.exit_reason = "Test reason"
        processor.process.return_value = result_mock
        main_processor.solitude_processor = processor  # Set the reference for comparison
        main_processor._handle_state_transition = AsyncMock()
        
        round_increment, consecutive_errors, should_break = await main_processor._process_regular_state(
            processor, AgentState.SOLITUDE, 0, 5
        )
        
        assert round_increment == 1
        assert consecutive_errors == 0
        assert should_break is False
        main_processor._handle_state_transition.assert_called_once_with(AgentState.WORK)

    @pytest.mark.asyncio
    async def test_process_regular_state_error_handling(self, main_processor, mock_processors):
        """Test _process_regular_state error handling."""
        processor = mock_processors["work"]
        processor.process.side_effect = Exception("Test error")
        
        with patch('asyncio.sleep') as mock_sleep:
            round_increment, consecutive_errors, should_break = await main_processor._process_regular_state(
                processor, AgentState.WORK, 0, 5
            )
        
        assert round_increment == 0
        assert consecutive_errors == 1
        assert should_break is False
        mock_sleep.assert_called_once_with(2)  # min(1 * 2, 30)

    @pytest.mark.asyncio
    async def test_process_regular_state_max_errors(self, main_processor, mock_processors):
        """Test _process_regular_state with max consecutive errors."""
        processor = mock_processors["work"]
        processor.process.side_effect = Exception("Test error")
        
        with patch('ciris_engine.logic.processors.core.main_processor.request_global_shutdown') as mock_shutdown:
            round_increment, consecutive_errors, should_break = await main_processor._process_regular_state(
                processor, AgentState.WORK, 4, 5  # One more error will trigger shutdown
            )
        
        assert round_increment == 0
        assert consecutive_errors == 5
        assert should_break is True
        mock_shutdown.assert_called_once()

    # Tests for _process_dream_state
    @pytest.mark.asyncio
    async def test_process_dream_state_dream_complete(self, main_processor):
        """Test _process_dream_state when dream is complete."""
        # Mock dream processor with completed task
        main_processor.dream_processor._dream_task = Mock()
        main_processor.dream_processor._dream_task.done.return_value = True
        main_processor._handle_state_transition = AsyncMock()
        
        result = await main_processor._process_dream_state()
        
        assert result is True
        main_processor._handle_state_transition.assert_called_once_with(AgentState.WORK)

    @pytest.mark.asyncio
    async def test_process_dream_state_dream_running(self, main_processor):
        """Test _process_dream_state when dream is still running."""
        # Mock dream processor with running task
        main_processor.dream_processor._dream_task = Mock()
        main_processor.dream_processor._dream_task.done.return_value = False
        
        with patch('asyncio.sleep') as mock_sleep:
            result = await main_processor._process_dream_state()
        
        assert result is True
        mock_sleep.assert_called_once_with(5)

    @pytest.mark.asyncio
    async def test_process_dream_state_no_dream_task(self, main_processor):
        """Test _process_dream_state with no dream task."""
        # Mock dream processor without task
        main_processor.dream_processor._dream_task = None
        main_processor._handle_state_transition = AsyncMock()
        
        result = await main_processor._process_dream_state()
        
        assert result is True
        main_processor._handle_state_transition.assert_called_once_with(AgentState.WORK)

    # Tests for _process_shutdown_state
    @pytest.mark.asyncio
    async def test_process_shutdown_state_no_processor(self, main_processor):
        """Test _process_shutdown_state without processor."""
        round_increment, consecutive_errors, should_break = await main_processor._process_shutdown_state(
            None, 0
        )
        
        assert round_increment == 0
        assert consecutive_errors == 0
        assert should_break is True

    @pytest.mark.asyncio
    async def test_process_shutdown_state_shutdown_ready(self, main_processor, mock_processors):
        """Test _process_shutdown_state with shutdown ready."""
        processor = mock_processors["shutdown"]
        result_mock = Mock()
        result_mock.shutdown_ready = True
        processor.process.return_value = result_mock
        
        round_increment, consecutive_errors, should_break = await main_processor._process_shutdown_state(
            processor, 0
        )
        
        assert round_increment == 1
        assert consecutive_errors == 0
        assert should_break is True

    @pytest.mark.asyncio
    async def test_process_shutdown_state_processor_complete(self, main_processor, mock_processors):
        """Test _process_shutdown_state with processor.shutdown_complete."""
        processor = mock_processors["shutdown"]
        processor.shutdown_complete = True
        result_mock = Mock()
        result_mock.shutdown_ready = False  # Test processor attribute takes precedence
        processor.process.return_value = result_mock
        
        round_increment, consecutive_errors, should_break = await main_processor._process_shutdown_state(
            processor, 0
        )
        
        assert round_increment == 1
        assert consecutive_errors == 0
        assert should_break is True

    @pytest.mark.asyncio
    async def test_process_shutdown_state_error(self, main_processor, mock_processors):
        """Test _process_shutdown_state error handling."""
        processor = mock_processors["shutdown"]
        processor.process.side_effect = Exception("Shutdown error")
        
        round_increment, consecutive_errors, should_break = await main_processor._process_shutdown_state(
            processor, 0
        )
        
        assert round_increment == 0
        assert consecutive_errors == 1
        assert should_break is True

    # Tests for _calculate_round_delay
    def test_calculate_round_delay_default(self, main_processor, mock_config):
        """Test _calculate_round_delay with default values."""
        # Remove workflow to test default
        delattr(mock_config, 'workflow')
        
        delay = main_processor._calculate_round_delay(AgentState.PLAY)
        assert delay == 1.0

    def test_calculate_round_delay_from_config(self, main_processor, mock_config):
        """Test _calculate_round_delay from config workflow."""
        delay = main_processor._calculate_round_delay(AgentState.PLAY)
        assert delay == 2.0  # From get_round_delay

    def test_calculate_round_delay_work_state(self, main_processor, mock_config):
        """Test _calculate_round_delay for WORK state override."""
        delay = main_processor._calculate_round_delay(AgentState.WORK)
        assert delay == 3.0  # State-specific override

    def test_calculate_round_delay_solitude_state(self, main_processor, mock_config):
        """Test _calculate_round_delay for SOLITUDE state override."""
        delay = main_processor._calculate_round_delay(AgentState.SOLITUDE)
        assert delay == 10.0  # State-specific override

    def test_calculate_round_delay_dream_state(self, main_processor, mock_config):
        """Test _calculate_round_delay for DREAM state override."""
        delay = main_processor._calculate_round_delay(AgentState.DREAM)
        assert delay == 5.0  # State-specific override

    def test_calculate_round_delay_mock_llm(self, main_processor, mock_config):
        """Test _calculate_round_delay with mock LLM (no state overrides)."""
        mock_config.mock_llm = True
        
        delay = main_processor._calculate_round_delay(AgentState.WORK)
        assert delay == 2.0  # Config value, no state override

    # Tests for _handle_delay_with_stop_check
    @pytest.mark.asyncio
    async def test_handle_delay_with_stop_check_no_delay(self, main_processor):
        """Test _handle_delay_with_stop_check with zero delay."""
        result = await main_processor._handle_delay_with_stop_check(0)
        assert result is True

    @pytest.mark.asyncio
    async def test_handle_delay_with_stop_check_stop_set(self, main_processor):
        """Test _handle_delay_with_stop_check with stop event set."""
        main_processor._stop_event = Mock()
        main_processor._stop_event.is_set.return_value = True
        
        result = await main_processor._handle_delay_with_stop_check(1.0)
        assert result is True  # No delay when stop is set

    @pytest.mark.asyncio
    async def test_handle_delay_with_stop_check_with_event(self, main_processor):
        """Test _handle_delay_with_stop_check with stop event that gets set during wait."""
        main_processor._stop_event = Mock()
        main_processor._stop_event.is_set.return_value = False
        
        # Mock wait_for to resolve immediately (simulating stop event being set)
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.return_value = None  # Event was set
            
            result = await main_processor._handle_delay_with_stop_check(1.0)
            
        assert result is False  # Should break when stop event is set
        mock_wait_for.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_delay_with_stop_check_timeout(self, main_processor):
        """Test _handle_delay_with_stop_check with timeout (normal case)."""
        main_processor._stop_event = Mock()
        main_processor._stop_event.is_set.return_value = False
        
        # Mock wait_for to timeout
        with patch('asyncio.wait_for') as mock_wait_for:
            mock_wait_for.side_effect = asyncio.TimeoutError()
            
            result = await main_processor._handle_delay_with_stop_check(1.0)
            
        assert result is True  # Should continue when timeout occurs
        mock_wait_for.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_delay_with_stop_check_no_event(self, main_processor):
        """Test _handle_delay_with_stop_check without stop event."""
        main_processor._stop_event = None
        
        with patch('asyncio.sleep') as mock_sleep:
            result = await main_processor._handle_delay_with_stop_check(1.0)
            
        assert result is True
        mock_sleep.assert_called_once_with(1.0)

    # Tests for _process_single_round (integration test of helpers)
    @pytest.mark.asyncio
    async def test_process_single_round_max_rounds_reached(self, main_processor):
        """Test _process_single_round when max rounds reached."""
        with patch('ciris_engine.logic.processors.core.main_processor.request_global_shutdown') as mock_shutdown:
            round_count, consecutive_errors, should_break = await main_processor._process_single_round(
                5, 0, 5, 5  # round_count == num_rounds
            )
            
        assert round_count == 5
        assert consecutive_errors == 0
        assert should_break is True
        mock_shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_single_round_pause_skip(self, main_processor):
        """Test _process_single_round when paused (skip round)."""
        main_processor._check_pause_state = AsyncMock(return_value=False)
        
        round_count, consecutive_errors, should_break = await main_processor._process_single_round(
            3, 0, 5, 10
        )
        
        assert round_count == 3  # No change
        assert consecutive_errors == 0
        assert should_break is False

    @pytest.mark.asyncio
    async def test_process_single_round_full_cycle(self, main_processor, mock_processors):
        """Test _process_single_round full successful cycle."""
        # Mock all the helper methods
        main_processor._check_pause_state = AsyncMock(return_value=True)
        main_processor._handle_shutdown_transitions = AsyncMock(return_value=True)
        main_processor._process_regular_state = AsyncMock(return_value=(1, 0, False))
        main_processor._calculate_round_delay = Mock(return_value=1.0)
        main_processor._handle_delay_with_stop_check = AsyncMock(return_value=True)
        
        # Mock state manager
        main_processor.state_manager.get_state = Mock(return_value=AgentState.WORK)
        
        round_count, consecutive_errors, should_break = await main_processor._process_single_round(
            3, 0, 5, 10
        )
        
        assert round_count == 4  # Incremented by 1
        assert consecutive_errors == 0
        assert should_break is False
        
        # Verify all helpers were called
        main_processor._check_pause_state.assert_called_once()
        main_processor._handle_shutdown_transitions.assert_called_once()
        main_processor._process_regular_state.assert_called_once()
        main_processor._calculate_round_delay.assert_called_once()
        main_processor._handle_delay_with_stop_check.assert_called_once()


class TestProcessSingleRoundHelpers:
    """Test helper methods for _process_single_round functionality."""

    def test_should_stop_after_target_rounds_reached(self, main_processor):
        """Test _should_stop_after_target_rounds when target is reached."""
        with patch('ciris_engine.logic.processors.core.main_processor.request_global_shutdown') as mock_shutdown:
            result = main_processor._should_stop_after_target_rounds(round_count=5, num_rounds=5)
            
            assert result is True
            mock_shutdown.assert_called_once_with("Processing completed after 5 rounds")

    def test_should_stop_after_target_rounds_not_reached(self, main_processor):
        """Test _should_stop_after_target_rounds when target not reached."""
        result = main_processor._should_stop_after_target_rounds(round_count=3, num_rounds=5)
        assert result is False

    def test_should_stop_after_target_rounds_no_limit(self, main_processor):
        """Test _should_stop_after_target_rounds with no round limit."""
        result = main_processor._should_stop_after_target_rounds(round_count=100, num_rounds=None)
        assert result is False

    @pytest.mark.asyncio
    async def test_process_current_state_regular_state(self, main_processor, mock_processors):
        """Test _process_current_state with regular state."""
        main_processor.state_processors = mock_processors
        main_processor._handle_regular_state_processing = AsyncMock(return_value=(1, 0, False))
        
        result = await main_processor._process_current_state(0, 0, 5, AgentState.WORK)
        
        assert result == (1, 0, False)
        main_processor._handle_regular_state_processing.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_current_state_dream_state(self, main_processor):
        """Test _process_current_state with dream state."""
        # Ensure DREAM state doesn't have a processor to trigger the elif branch
        main_processor.state_processors = {state: Mock() for state in ["work", "play", "shutdown"]}
        
        # Mock the helper method that actually gets called
        with patch.object(main_processor, '_handle_dream_state_processing', return_value=(1, 0, False)) as mock_handler:
            result = await main_processor._process_current_state(0, 0, 5, AgentState.DREAM)
            
            assert result == (1, 0, False)
            mock_handler.assert_called_once_with(0, 0)

    @pytest.mark.asyncio
    async def test_process_current_state_shutdown_state(self, main_processor):
        """Test _process_current_state with shutdown state."""
        main_processor._handle_shutdown_state_processing = AsyncMock(return_value=(1, 0, True))
        
        result = await main_processor._process_current_state(0, 0, 5, AgentState.SHUTDOWN)
        
        assert result == (1, 0, True)
        main_processor._handle_shutdown_state_processing.assert_called_once_with(0, 0)

    @pytest.mark.asyncio
    async def test_process_current_state_unknown_state(self, main_processor):
        """Test _process_current_state with unknown state."""
        main_processor._handle_unknown_state = AsyncMock(return_value=(0, 0, False))
        
        # Use a state that doesn't have a processor
        main_processor.state_processors = {}
        
        result = await main_processor._process_current_state(0, 0, 5, AgentState.PLAY)
        
        assert result == (0, 0, False)
        main_processor._handle_unknown_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_regular_state_processing(self, main_processor, mock_processors):
        """Test _handle_regular_state_processing helper method."""
        processor = mock_processors["work"]
        main_processor._process_regular_state = AsyncMock(return_value=(1, 0, False))
        
        result = await main_processor._handle_regular_state_processing(
            processor, AgentState.WORK, 0, 5, 3
        )
        
        assert result == (4, 0, False)  # round_count incremented
        main_processor._process_regular_state.assert_called_once_with(
            processor, AgentState.WORK, 0, 5
        )

    @pytest.mark.asyncio
    async def test_handle_dream_state_processing_success(self, main_processor):
        """Test _handle_dream_state_processing when dream processing succeeds."""
        main_processor._process_dream_state = AsyncMock(return_value=True)
        
        result = await main_processor._handle_dream_state_processing(5, 2)
        
        assert result == (5, 2, False)  # Continue processing
        main_processor._process_dream_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_dream_state_processing_failure(self, main_processor):
        """Test _handle_dream_state_processing when dream processing fails."""
        main_processor._process_dream_state = AsyncMock(return_value=False)
        
        result = await main_processor._handle_dream_state_processing(5, 2)
        
        assert result == (5, 2, True)  # Should break

    @pytest.mark.asyncio
    async def test_handle_shutdown_state_processing(self, main_processor, mock_processors):
        """Test _handle_shutdown_state_processing helper method."""
        main_processor.state_processors = mock_processors
        main_processor._process_shutdown_state = AsyncMock(return_value=(1, 1, True))
        
        result = await main_processor._handle_shutdown_state_processing(0, 4)
        
        assert result == (5, 1, True)  # round_count incremented
        main_processor._process_shutdown_state.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_unknown_state(self, main_processor):
        """Test _handle_unknown_state helper method."""
        with patch('asyncio.sleep') as mock_sleep:
            result = await main_processor._handle_unknown_state(3, 1, AgentState.PLAY)
            
            assert result == (3, 1, False)  # No changes, continue processing
            mock_sleep.assert_called_once_with(1)

    @pytest.mark.asyncio
    async def test_handle_round_delay(self, main_processor):
        """Test _handle_round_delay helper method."""
        main_processor._calculate_round_delay = Mock(return_value=2.0)
        main_processor._handle_delay_with_stop_check = AsyncMock(return_value=True)
        
        result = await main_processor._handle_round_delay(AgentState.WORK)
        
        assert result is True
        main_processor._calculate_round_delay.assert_called_once_with(AgentState.WORK)
        main_processor._handle_delay_with_stop_check.assert_called_once_with(2.0)


# TestFallbackSingleStepHelpers class removed - violates FAIL FAST principle
# The AgentProcessor correctly fails fast without any fallbacks, mocking, or fake data generation