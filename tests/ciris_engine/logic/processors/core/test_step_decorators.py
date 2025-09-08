"""
Unit tests for step_decorators module.

Tests the decorator functionality for H3ERE pipeline step points including:
- Streaming step results to clients
- Pause/resume mechanics for single-step debugging
- Integration with live thought processing
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime, timezone

from ciris_engine.logic.processors.core.step_decorators import (
    streaming_step,
    step_point,
    enable_single_step_mode,
    disable_single_step_mode,
    is_single_step_mode,
    execute_step,
    execute_all_steps,
    get_paused_thoughts,
    _paused_thoughts,
    _single_step_mode,
)
from ciris_engine.schemas.services.runtime_control import StepPoint
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.runtime.enums import ThoughtType

# Import existing fixtures
from tests.fixtures.mocks import create_mock_thought


class TestStreamingStepDecorator:
    """Test the @streaming_step decorator."""

    @pytest.fixture
    def mock_time_service(self):
        """Mock time service for testing."""
        mock = Mock()
        mock.now.return_value = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
        return mock

    @pytest.fixture
    def mock_thought_item(self):
        """Mock ProcessingQueueItem for testing using existing patterns."""
        return ProcessingQueueItem(
            thought_id="test-thought-123",
            source_task_id="test-task-456", 
            thought_type=ThoughtType.STANDARD,
            content=ThoughtContent(text="test input"),
            raw_input_string="test input",
            priority=1,
            created_at=datetime.now(timezone.utc)
        )

    @pytest.fixture
    def mock_processor(self, mock_time_service):
        """Mock processor instance with time service."""
        processor = Mock()
        processor._time_service = mock_time_service
        return processor

    @pytest.mark.asyncio
    async def test_streaming_step_decorator_success(self, mock_processor, mock_thought_item):
        """Test streaming step decorator on successful function execution."""
        
        # Mock the step result streaming
        with patch('ciris_engine.logic.processors.core.step_decorators._broadcast_step_result') as mock_broadcast:
            mock_broadcast.return_value = None
            
            @streaming_step(StepPoint.GATHER_CONTEXT)
            async def test_step_function(self, thought_item):
                """Test step function."""
                return {"context": "test_context_data"}
            
            # Execute the decorated function
            result = await test_step_function(mock_processor, mock_thought_item)
            
            # Verify result is returned unchanged
            assert result == {"context": "test_context_data"}
            
            # Verify streaming was called
            mock_broadcast.assert_called_once()
            call_args = mock_broadcast.call_args
            assert call_args[0][0] == StepPoint.GATHER_CONTEXT
            assert call_args[0][1] == "test-thought-123"
            
            step_data = call_args[0][2]
            assert step_data["thought_id"] == "test-thought-123"
            assert step_data["success"] is True
            assert "processing_time_ms" in step_data
            assert "timestamp" in step_data

    @pytest.mark.asyncio
    async def test_streaming_step_decorator_error(self, mock_processor, mock_thought_item):
        """Test streaming step decorator on function error."""
        
        # Mock the step result streaming
        with patch('ciris_engine.logic.processors.core.step_decorators._broadcast_step_result') as mock_broadcast:
            mock_broadcast.return_value = None
            
            @streaming_step(StepPoint.PERFORM_DMAS)
            async def test_step_function_error(self, thought_item):
                """Test step function that raises error."""
                raise ValueError("Test error message")
            
            # Execute the decorated function and expect error
            with pytest.raises(ValueError, match="Test error message"):
                await test_step_function_error(mock_processor, mock_thought_item)
            
            # Verify error streaming was called
            mock_broadcast.assert_called_once()
            call_args = mock_broadcast.call_args
            step_data = call_args[0][2]
            assert step_data["success"] is False
            assert step_data["error"] == "Test error message"

    @pytest.mark.asyncio
    async def test_streaming_step_no_time_service(self, mock_thought_item):
        """Test streaming step decorator fails loudly without time service."""
        
        # Create a processor that explicitly doesn't have time service
        class ProcessorWithoutTimeService:
            pass
        
        processor_no_time = ProcessorWithoutTimeService()
        
        @streaming_step(StepPoint.FINALIZE_ACTION)
        async def test_step_function(self, thought_item):
            return "success"
        
        # Should raise RuntimeError for missing time service
        with pytest.raises(RuntimeError, match="Critical error: No time service available"):
            await test_step_function(processor_no_time, mock_thought_item)


class TestStepPointDecorator:
    """Test the @step_point decorator."""

    def setup_method(self):
        """Reset single-step mode before each test."""
        disable_single_step_mode()
        _paused_thoughts.clear()

    @pytest.fixture
    def mock_thought_item(self):
        """Mock ProcessingQueueItem for testing using existing patterns."""
        return ProcessingQueueItem(
            thought_id="test-thought-pause",
            source_task_id="test-task-789",
            thought_type=ThoughtType.STANDARD,
            content=ThoughtContent(text="pause test input"),
            raw_input_string="pause test input",
            priority=1,
            created_at=datetime.now(timezone.utc)
        )

    @pytest.mark.asyncio
    async def test_step_point_normal_mode(self, mock_thought_item):
        """Test step point decorator in normal (non-single-step) mode."""
        
        @step_point(StepPoint.CONSCIENCE_EXECUTION)
        async def test_step_function(self, thought_item):
            return "normal_execution"
        
        # Should execute normally without pausing
        result = await test_step_function(Mock(), mock_thought_item)
        assert result == "normal_execution"
        assert len(_paused_thoughts) == 0

    @pytest.mark.asyncio
    async def test_step_point_single_step_mode(self, mock_thought_item):
        """Test step point decorator in single-step mode."""
        enable_single_step_mode()
        
        @step_point(StepPoint.PERFORM_ASPDMA)
        async def test_step_function(self, thought_item):
            return "after_pause"
        
        # Mock the pause mechanism
        async def mock_pause(thought_id, step):
            # Simulate immediate resume for testing
            pass
            
        with patch('ciris_engine.logic.processors.core.step_decorators._pause_thought_execution', mock_pause):
            result = await test_step_function(Mock(), mock_thought_item)
            assert result == "after_pause"

    @pytest.mark.asyncio
    async def test_step_point_conditional(self, mock_thought_item):
        """Test conditional step point (recursive steps)."""
        enable_single_step_mode()
        
        @step_point(StepPoint.RECURSIVE_ASPDMA)
        async def test_conditional_step(self, thought_item):
            return "conditional_result"
        
        with patch('ciris_engine.logic.processors.core.step_decorators._pause_thought_execution') as mock_pause:
            result = await test_conditional_step(Mock(), mock_thought_item)
            assert result == "conditional_result"
            # Should still pause even if conditional
            mock_pause.assert_called_once()


class TestStepControlAPI:
    """Test the step control API functions."""

    def setup_method(self):
        """Reset state before each test."""
        disable_single_step_mode()
        _paused_thoughts.clear()

    def test_single_step_mode_control(self):
        """Test enabling/disabling single-step mode."""
        assert not is_single_step_mode()
        
        enable_single_step_mode()
        assert is_single_step_mode()
        
        disable_single_step_mode()
        assert not is_single_step_mode()

    @pytest.mark.asyncio
    async def test_execute_step_no_paused_thought(self):
        """Test executing step when thought is not paused."""
        result = await execute_step("nonexistent-thought")
        
        assert result["success"] is False
        assert "not paused or does not exist" in result["error"]
        assert result["thought_id"] == "nonexistent-thought"

    @pytest.mark.asyncio
    async def test_execute_step_success(self):
        """Test successfully executing step for paused thought."""
        thought_id = "paused-thought-123"
        
        # Simulate a paused thought
        _paused_thoughts[thought_id] = asyncio.Event()
        
        result = await execute_step(thought_id)
        
        assert result["success"] is True
        assert result["thought_id"] == thought_id
        assert "advanced one step" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_all_steps_no_thoughts(self):
        """Test executing all steps when no thoughts are paused."""
        result = await execute_all_steps()
        
        assert result["success"] is True
        assert result["thoughts_advanced"] == 0
        assert "No thoughts currently paused" in result["message"]

    @pytest.mark.asyncio
    async def test_execute_all_steps_success(self):
        """Test successfully executing all paused thoughts."""
        # Simulate multiple paused thoughts
        _paused_thoughts["thought-1"] = asyncio.Event()
        _paused_thoughts["thought-2"] = asyncio.Event() 
        _paused_thoughts["thought-3"] = asyncio.Event()
        
        result = await execute_all_steps()
        
        assert result["success"] is True
        assert result["thoughts_advanced"] == 3
        assert "Advanced 3 thoughts" in result["message"]

    def test_get_paused_thoughts(self):
        """Test getting list of paused thoughts."""
        assert get_paused_thoughts() == {}
        
        # Add some paused thoughts
        _paused_thoughts["thought-a"] = asyncio.Event()
        _paused_thoughts["thought-b"] = asyncio.Event()
        
        paused = get_paused_thoughts()
        assert len(paused) == 2
        assert paused["thought-a"] == "paused_awaiting_resume"
        assert paused["thought-b"] == "paused_awaiting_resume"


class TestStepDataExtraction:
    """Test step-specific data extraction."""

    @pytest.mark.asyncio
    async def test_step_specific_data_gather_context(self):
        """Test data extraction for GATHER_CONTEXT step."""
        
        with patch('ciris_engine.logic.processors.core.step_decorators._broadcast_step_result') as mock_broadcast:
            
            @streaming_step(StepPoint.GATHER_CONTEXT)
            async def gather_context_step(self, thought_item):
                return {"context": "built", "size": 1024}
            
            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)
            
            mock_thought = Mock(thought_id="test-123", source_task_id="task-456")
            
            await gather_context_step(mock_processor, mock_thought)
            
            # Verify step-specific data was added
            call_args = mock_broadcast.call_args[0][2]
            assert call_args["task_id"] == "task-456"
            assert call_args["context"] is not None

    @pytest.mark.asyncio
    async def test_step_specific_data_perform_aspdma(self):
        """Test data extraction for PERFORM_ASPDMA step."""
        
        with patch('ciris_engine.logic.processors.core.step_decorators._broadcast_step_result') as mock_broadcast:
            
            @streaming_step(StepPoint.PERFORM_ASPDMA)
            async def aspdma_step(self, thought_item):
                # Mock ActionSelectionDMAResult
                result = Mock()
                result.selected_action = "SPEAK"
                result.rationale = "Test reasoning"
                return result
            
            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)
            
            mock_thought = Mock(thought_id="test-123")
            
            await aspdma_step(mock_processor, mock_thought)
            
            # Verify ASPDMA-specific data was added
            call_args = mock_broadcast.call_args[0][2]
            assert call_args["selected_action"] == "SPEAK"
            assert call_args["action_rationale"] == "Test reasoning"


class TestIntegrationFlow:
    """Test complete integration flow with decorators."""

    def setup_method(self):
        disable_single_step_mode()
        _paused_thoughts.clear()

    @pytest.mark.asyncio
    async def test_complete_step_flow_normal_mode(self):
        """Test complete step execution in normal mode."""
        
        execution_log = []
        
        with patch('ciris_engine.logic.processors.core.step_decorators._broadcast_step_result') as mock_broadcast:
            
            @streaming_step(StepPoint.GATHER_CONTEXT)
            @step_point(StepPoint.GATHER_CONTEXT)
            async def step1(self, thought_item):
                execution_log.append("step1_executed")
                return "context"
            
            @streaming_step(StepPoint.PERFORM_DMAS)
            @step_point(StepPoint.PERFORM_DMAS)
            async def step2(self, thought_item, context):
                execution_log.append("step2_executed")
                return "dmas"
            
            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)
            
            mock_thought = Mock(thought_id="flow-test")
            
            # Execute steps in sequence
            result1 = await step1(mock_processor, mock_thought)
            result2 = await step2(mock_processor, mock_thought, result1)
            
            # Verify execution
            assert execution_log == ["step1_executed", "step2_executed"]
            assert result1 == "context"
            assert result2 == "dmas"
            
            # Verify both steps were streamed
            assert mock_broadcast.call_count == 2

    @pytest.mark.asyncio
    async def test_complete_step_flow_single_step_mode(self):
        """Test step execution with pause/resume in single-step mode."""
        enable_single_step_mode()
        
        try:
            execution_log = []
            
            # Mock pause to simulate single-step behavior
            async def mock_pause(thought_id, step):
                execution_log.append(f"paused_at_{step.value}")
                # Immediate resume for testing
            
            with patch('ciris_engine.logic.processors.core.step_decorators._broadcast_step_result'):
                with patch('ciris_engine.logic.processors.core.step_decorators._pause_thought_execution', mock_pause):
                    
                    @streaming_step(StepPoint.PERFORM_ASPDMA)
                    @step_point(StepPoint.PERFORM_ASPDMA)
                    async def step_with_pause(self, thought_item):
                        execution_log.append("step_executed")
                        return "result"
                    
                    mock_processor = Mock()
                    mock_processor._time_service = Mock()
                    mock_processor._time_service.now.return_value = datetime.now(timezone.utc)
                    
                    mock_thought = Mock(thought_id="pause-test")
                    
                    result = await step_with_pause(mock_processor, mock_thought)
                    
                    # Verify pause occurred before execution
                    assert execution_log == ["paused_at_perform_aspdma", "step_executed"]
                    assert result == "result"
        finally:
            # CRITICAL: Always disable single-step mode to prevent test order dependencies
            disable_single_step_mode()
            _paused_thoughts.clear()