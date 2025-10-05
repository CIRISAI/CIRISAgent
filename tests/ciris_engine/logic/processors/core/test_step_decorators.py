"""
Unit tests for step_decorators module.

Tests the decorator functionality for H3ERE pipeline step points including:
- Streaming step results to clients
- Pause/resume mechanics for single-step debugging
- Integration with live thought processing
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, PropertyMock, patch

import pytest

from ciris_engine.logic.processors.core.step_decorators import (  # Helper functions for testing
    _add_action_complete_attributes,
    _add_conscience_execution_attributes,
    _add_finalize_action_attributes,
    _add_gather_context_attributes,
    _add_perform_action_attributes,
    _add_perform_aspdma_attributes,
    _add_perform_dmas_attributes,
    _add_typed_step_attributes,
    _build_step_result_data,
    _create_step_result_schema,
    _create_typed_step_data,
    _extract_timing_data,
    _paused_thoughts,
    _single_step_mode,
    disable_single_step_mode,
    enable_single_step_mode,
    execute_all_steps,
    execute_step,
    get_paused_thoughts,
    is_single_step_mode,
    step_point,
    streaming_step,
)
from ciris_engine.logic.processors.support.processing_queue import ProcessingQueueItem, ThoughtContent
from ciris_engine.schemas.runtime.enums import ThoughtType
from ciris_engine.schemas.services.runtime_control import (
    ActionCompleteStepData,
    AllStepsExecutionResult,
    BaseStepData,
    ConscienceExecutionStepData,
    GatherContextStepData,
    PerformASPDMAStepData,
    PerformDMAsStepData,
    SpanAttribute,
    StepDataUnion,
    StepExecutionResult,
    StepPoint,
    StepResultData,
    TraceContext,
)

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
            created_at=datetime.now(timezone.utc),
        )

    @pytest.fixture
    def mock_processor(self, mock_time_service):
        """Mock processor instance with time service."""
        processor = Mock()
        processor._time_service = mock_time_service
        return processor

    @pytest.mark.skip(reason="Tests old _broadcast_step_result - replaced with 5-event reasoning stream")
    @pytest.mark.asyncio
    async def test_streaming_step_decorator_success(self, mock_processor, mock_thought_item):
        """Test streaming step decorator on successful function execution."""

        # Mock the step result streaming
        with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result") as mock_broadcast:
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

            step_data = call_args[0][1]
            assert step_data.thought_id == "test-thought-123"
            assert step_data.success is True
            assert hasattr(step_data, "processing_time_ms")
            assert hasattr(step_data, "timestamp")

    @pytest.mark.skip(reason="Tests old _broadcast_step_result - replaced with 5-event reasoning stream")
    @pytest.mark.asyncio
    async def test_streaming_step_decorator_error(self, mock_processor, mock_thought_item):
        """Test streaming step decorator on function error."""

        # Mock the step result streaming
        with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result") as mock_broadcast:
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
            step_data = call_args[0][1]
            assert step_data.success is False
            assert step_data.error == "Test error message"

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
            created_at=datetime.now(timezone.utc),
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
        async def mock_pause(thought_id):
            # Simulate immediate resume for testing
            pass

        with patch("ciris_engine.logic.processors.core.step_decorators._pause_thought_execution", mock_pause):
            result = await test_step_function(Mock(), mock_thought_item)
            assert result == "after_pause"

    @pytest.mark.asyncio
    async def test_step_point_conditional(self, mock_thought_item):
        """Test conditional step point (recursive steps)."""
        enable_single_step_mode()

        @step_point(StepPoint.RECURSIVE_ASPDMA)
        async def test_conditional_step(self, thought_item):
            return "conditional_result"

        with patch("ciris_engine.logic.processors.core.step_decorators._pause_thought_execution") as mock_pause:
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

        assert result.success is False
        assert "not paused or does not exist" in result.error
        assert result.thought_id == "nonexistent-thought"

    @pytest.mark.asyncio
    async def test_execute_step_success(self):
        """Test successfully executing step for paused thought."""
        thought_id = "paused-thought-123"

        # Simulate a paused thought
        _paused_thoughts[thought_id] = asyncio.Event()

        result = await execute_step(thought_id)

        assert result.success is True
        assert result.thought_id == thought_id
        assert "advanced one step" in result.message

    @pytest.mark.asyncio
    async def test_execute_all_steps_no_thoughts(self):
        """Test executing all steps when no thoughts are paused."""
        result = await execute_all_steps()

        assert result.success is True
        assert result.thoughts_advanced == 0
        assert "No thoughts currently paused" in result.message

    @pytest.mark.asyncio
    async def test_execute_all_steps_success(self):
        """Test successfully executing all paused thoughts."""
        # Simulate multiple paused thoughts
        _paused_thoughts["thought-1"] = asyncio.Event()
        _paused_thoughts["thought-2"] = asyncio.Event()
        _paused_thoughts["thought-3"] = asyncio.Event()

        result = await execute_all_steps()

        assert result.success is True
        assert result.thoughts_advanced == 3
        assert "Advanced 3 thoughts" in result.message

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

    @pytest.mark.skip(reason="Tests old _broadcast_step_result - replaced with 5-event reasoning stream")
    @pytest.mark.asyncio
    async def test_step_specific_data_gather_context(self):
        """Test data extraction for GATHER_CONTEXT step."""

        with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result") as mock_broadcast:

            @streaming_step(StepPoint.GATHER_CONTEXT)
            async def gather_context_step(self, thought_item):
                return {"context": "built", "size": 1024}

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            await gather_context_step(mock_processor, mock_thought)

            # Verify step-specific data was added
            call_args = mock_broadcast.call_args[0][1]
            assert call_args.task_id == "task-456"
            assert call_args.context is not None

    @pytest.mark.skip(reason="Tests old _broadcast_step_result - replaced with 5-event reasoning stream")
    @pytest.mark.asyncio
    async def test_step_specific_data_perform_aspdma(self):
        """Test data extraction for PERFORM_ASPDMA step."""

        with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result") as mock_broadcast:

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

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            await aspdma_step(mock_processor, mock_thought)

            # Verify ASPDMA-specific data was added
            call_args = mock_broadcast.call_args[0][1]
            assert call_args.selected_action == "SPEAK"
            assert call_args.action_rationale == "Test reasoning"

    @pytest.mark.asyncio
    async def test_step_specific_data_perform_aspdma_missing_fields(self):
        """Test PERFORM_ASPDMA with missing selected_action - should fail fast."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.PERFORM_ASPDMA)
            async def aspdma_step(self, thought_item):
                # Return object without selected_action or rationale
                result = Mock(spec=[])  # Empty spec = no attributes
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Should fail fast with AttributeError
            with pytest.raises(AttributeError, match="PERFORM_ASPDMA result missing 'selected_action' attribute"):
                await aspdma_step(mock_processor, mock_thought)

    @pytest.mark.skip(reason="Tests old _broadcast_step_result - replaced with 5-event reasoning stream")
    @pytest.mark.asyncio
    async def test_step_specific_data_action_complete_dict_format(self):
        """Test ACTION_COMPLETE with dispatch_result dict format (new behavior)."""

        with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result") as mock_broadcast:

            @streaming_step(StepPoint.ACTION_COMPLETE)
            async def action_complete_step(self, thought_item):
                # Return dispatch_result dict format
                return {
                    "action_type": "speak",
                    "handler": "SpeakHandler",
                    "success": True,
                    "follow_up_thought_id": "followup-123",
                }

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            await action_complete_step(mock_processor, mock_thought)

            # Verify correct extraction from dict
            call_args = mock_broadcast.call_args[0][1]
            assert call_args.action_executed == "speak"  # Fixed: was "UNKNOWN"
            assert call_args.dispatch_success is True
            assert call_args.handler_completed is True  # handler != "Unknown"
            assert call_args.follow_up_processing_pending is True  # has follow_up_thought_id

    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Tests old _broadcast_step_result - replaced with 5-event reasoning stream")
    async def test_step_specific_data_action_complete_object_format(self):
        """Test ACTION_COMPLETE with object format (fallback behavior)."""

        with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result") as mock_broadcast:

            @streaming_step(StepPoint.ACTION_COMPLETE)
            async def action_complete_step(self, thought_item):
                # Return object format (fallback) - restrict spec to only have the attributes we want
                result = Mock(spec=["selected_action", "success", "completed", "has_follow_up"])
                result.selected_action = "ponder"  # This should be used in fallback
                result.success = False
                result.completed = True
                result.has_follow_up = False
                # action_type is not in spec, so it won't exist
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            await action_complete_step(mock_processor, mock_thought)

            # Verify fallback object extraction
            call_args = mock_broadcast.call_args[0][1]
            assert call_args.action_executed == "ponder"  # Should fall back to selected_action
            assert call_args.dispatch_success is False
            assert call_args.handler_completed is True
            assert call_args.follow_up_processing_pending is False

    @pytest.mark.skip(reason="Tests old _broadcast_step_result - replaced with 5-event reasoning stream")
    @pytest.mark.asyncio
    async def test_step_specific_data_perform_dmas_initial_results(self):
        """Test PERFORM_DMAS with InitialDMAResults object (new behavior)."""

        with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result") as mock_broadcast:

            @streaming_step(StepPoint.PERFORM_DMAS)
            async def perform_dmas_step(self, thought_item):
                # Mock InitialDMAResults object
                result = Mock()
                result.ethical_pdma = "ethical_result"
                result.csdma = "csdma_result"
                result.dsdma = "dsdma_result"
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"
            mock_thought.initial_context = "test_context"

            await perform_dmas_step(mock_processor, mock_thought)

            # Verify DMA results extraction
            call_args = mock_broadcast.call_args[0][1]
            expected_dma = "ethical_pdma: ethical_result; csdma: csdma_result; dsdma: dsdma_result"
            assert call_args.dma_results == expected_dma
            assert call_args.context == "test_context"

    @pytest.mark.skip(reason="Tests old _broadcast_step_result - replaced with 5-event reasoning stream")
    @pytest.mark.asyncio
    async def test_step_specific_data_conscience_execution_overridden(self):
        """Test CONSCIENCE_EXECUTION with ConscienceApplicationResult (new behavior)."""

        with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result") as mock_broadcast:

            @streaming_step(StepPoint.CONSCIENCE_EXECUTION)
            async def conscience_step(self, thought_item):
                # Mock ConscienceApplicationResult with overridden=True
                result = Mock()
                result.overridden = True
                result.override_reason = "Safety violation"
                result.final_action = Mock()
                result.final_action.selected_action = "reject"
                result.action_result = "action_blocked"
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            await conscience_step(mock_processor, mock_thought)

            # Verify conscience result extraction
            call_args = mock_broadcast.call_args[0][1]
            assert call_args.selected_action == "reject"
            assert call_args.conscience_passed is False  # not overridden
            assert call_args.override_reason == "Safety violation"
            assert hasattr(call_args, "action_result")

    @pytest.mark.skip(reason="Tests old _broadcast_step_result - replaced with 5-event reasoning stream")
    @pytest.mark.asyncio
    async def test_step_specific_data_conscience_execution_passed(self):
        """Test CONSCIENCE_EXECUTION with overridden=False (conscience passed)."""

        with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result") as mock_broadcast:

            @streaming_step(StepPoint.CONSCIENCE_EXECUTION)
            async def conscience_step(self, thought_item):
                # Mock ConscienceApplicationResult with overridden=False
                result = Mock()
                result.overridden = False
                result.final_action = Mock()
                result.final_action.selected_action = "speak"
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            await conscience_step(mock_processor, mock_thought)

            # Verify conscience passed
            call_args = mock_broadcast.call_args[0][1]
            assert call_args.selected_action == "speak"
            assert call_args.conscience_passed is True  # not overridden

    @pytest.mark.asyncio
    async def test_step_specific_data_fail_fast_missing_action_type(self):
        """Test ACTION_COMPLETE fails fast when result is not ActionResponse."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.ACTION_COMPLETE)
            async def action_complete_step(self, thought_item):
                # Return dict instead of ActionResponse - should fail fast
                return {
                    "success": True,
                    "handler": "SomeHandler",
                    "action_type": "SPEAK",
                }

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Should fail fast with TypeError - requires ActionResponse not dict
            with pytest.raises(TypeError, match="ACTION_COMPLETE expects ActionResponse"):
                await action_complete_step(mock_processor, mock_thought)

    @pytest.mark.asyncio
    async def test_step_specific_data_fail_fast_conscience_missing_overridden(self):
        """Test CONSCIENCE_EXECUTION fails fast when result missing overridden."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.CONSCIENCE_EXECUTION)
            async def conscience_step(self, thought_item):
                # Return object missing overridden attribute
                result = Mock(spec=["final_action"])  # Missing 'overridden'
                result.final_action = Mock()
                result.final_action.selected_action = "speak"
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Should fail fast with AttributeError
            with pytest.raises(AttributeError, match="CONSCIENCE_EXECUTION result missing 'overridden' attribute"):
                await conscience_step(mock_processor, mock_thought)

    @pytest.mark.asyncio
    async def test_step_specific_data_error_handling(self):
        """Test error handling in step-specific data extraction."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.PERFORM_ASPDMA)
            async def problematic_step(self, thought_item):
                # Return something that will cause an error in data extraction
                result = Mock()
                # Create a property that raises an exception when accessed
                type(result).selected_action = PropertyMock(side_effect=Exception("Test error"))
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Should fail fast with Exception
            with pytest.raises(Exception, match="Test error"):
                await problematic_step(mock_processor, mock_thought)

    @pytest.mark.asyncio
    async def test_step_specific_data_fail_fast_gather_context_none(self):
        """Test GATHER_CONTEXT fails fast when result is None."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.GATHER_CONTEXT)
            async def gather_context_step(self, thought_item):
                return None  # This should trigger fail-fast

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Should fail fast with ValueError
            with pytest.raises(ValueError, match="GATHER_CONTEXT step result is None"):
                await gather_context_step(mock_processor, mock_thought)

    @pytest.mark.asyncio
    async def test_step_specific_data_fail_fast_perform_dmas_none(self):
        """Test PERFORM_DMAS fails fast when result is None."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.PERFORM_DMAS)
            async def perform_dmas_step(self, thought_item):
                return None  # This should trigger fail-fast

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Should fail fast with ValueError
            with pytest.raises(ValueError, match="PERFORM_DMAS step result is None"):
                await perform_dmas_step(mock_processor, mock_thought)

    @pytest.mark.asyncio
    async def test_step_specific_data_fail_fast_perform_dmas_missing_context(self):
        """Test PERFORM_DMAS fails fast when thought_item missing initial_context."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.PERFORM_DMAS)
            async def perform_dmas_step(self, thought_item):
                result = Mock()
                result.ethical_pdma = "test"
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            # Mock thought without initial_context attribute
            mock_thought = Mock(spec=[], thought_id="test-123")  # spec=[] prevents default attributes

            # Should fail fast with AttributeError
            with pytest.raises(AttributeError, match="PERFORM_DMAS thought_item missing 'initial_context' attribute"):
                await perform_dmas_step(mock_processor, mock_thought)

    @pytest.mark.asyncio
    async def test_step_specific_data_fail_fast_recursive_aspdma_missing_args(self):
        """Test RECURSIVE_ASPDMA fails fast when args is empty."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.RECURSIVE_ASPDMA)
            async def recursive_aspdma_step(self, thought_item):
                result = Mock()
                result.selected_action = "test"
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Mock _add_step_specific_data to call our function with empty args
            with patch(
                "ciris_engine.logic.processors.core.step_decorators._create_recursive_aspdma_data"
            ) as mock_add_data:
                mock_add_data.side_effect = ValueError("RECURSIVE_ASPDMA args is empty - retry reason is required")

                # Should fail fast with ValueError
                with pytest.raises(ValueError, match="RECURSIVE_ASPDMA args is empty"):
                    await recursive_aspdma_step(mock_processor, mock_thought)

    @pytest.mark.asyncio
    async def test_step_specific_data_fail_fast_finalize_action_missing_final_action(self):
        """Test FINALIZE_ACTION fails fast when result missing final_action (ConscienceApplicationResult expected)."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.FINALIZE_ACTION)
            async def finalize_action_step(self, thought_item):
                # Mock result without final_action (should be ConscienceApplicationResult)
                result = Mock(spec=["selected_action"])  # Missing final_action
                result.selected_action = "test_action"
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Should fail fast with AttributeError for missing final_action
            with pytest.raises(AttributeError, match="FINALIZE_ACTION result missing 'final_action' attribute"):
                await finalize_action_step(mock_processor, mock_thought)

    @pytest.mark.asyncio
    async def test_step_specific_data_fail_fast_perform_action_no_action(self):
        """Test PERFORM_ACTION fails fast when cannot determine selected_action."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.PERFORM_ACTION)
            async def perform_action_step(self, thought_item):
                # Return result without selected_action
                result = Mock(spec=[])  # No attributes
                return result

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Mock _add_step_specific_data to call our function with empty args
            with patch(
                "ciris_engine.logic.processors.core.step_decorators._create_perform_action_data"
            ) as mock_add_data:
                mock_add_data.side_effect = ValueError(
                    "PERFORM_ACTION cannot determine selected_action - neither result.selected_action nor args[0] available"
                )

                # Should fail fast with ValueError
                with pytest.raises(ValueError, match="PERFORM_ACTION cannot determine selected_action"):
                    await perform_action_step(mock_processor, mock_thought)

    @pytest.mark.asyncio
    async def test_step_specific_data_fail_fast_start_round_empty_args(self):
        """Test START_ROUND fails fast when args is empty."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.START_ROUND)
            async def start_round_step(self, thought_item):
                return "round_started"

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Mock _add_step_specific_data to call our function with empty args
            with patch("ciris_engine.logic.processors.core.step_decorators._create_start_round_data") as mock_add_data:
                mock_add_data.side_effect = ValueError(
                    "START_ROUND args is empty - thought list is required for processing"
                )

                # Should fail fast with ValueError
                with pytest.raises(ValueError, match="START_ROUND args is empty"):
                    await start_round_step(mock_processor, mock_thought)

    @pytest.mark.asyncio
    async def test_step_specific_data_fail_fast_round_complete_empty_args(self):
        """Test ROUND_COMPLETE fails fast when args is empty."""

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"
        ) as mock_broadcast, patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:

            @streaming_step(StepPoint.ROUND_COMPLETE)
            async def round_complete_step(self, thought_item):
                return "round_completed"

            mock_processor = Mock()
            mock_processor._time_service = Mock()
            mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

            mock_thought = Mock()
            mock_thought.thought_id = "test-123"
            mock_thought.source_task_id = "task-456"

            # Mock _add_step_specific_data to call our function with empty args
            with patch(
                "ciris_engine.logic.processors.core.step_decorators._create_round_complete_data"
            ) as mock_add_data:
                mock_add_data.side_effect = ValueError(
                    "ROUND_COMPLETE args is empty - completed thought count is required"
                )

                # Should fail fast with ValueError
                with pytest.raises(ValueError, match="ROUND_COMPLETE args is empty"):
                    await round_complete_step(mock_processor, mock_thought)


class TestIntegrationFlow:
    """Test complete integration flow with decorators."""

    def setup_method(self):
        disable_single_step_mode()
        _paused_thoughts.clear()

    @pytest.mark.skip(reason="Tests old _broadcast_step_result - replaced with 5-event reasoning stream")
    @pytest.mark.asyncio
    async def test_complete_step_flow_normal_mode(self):
        """Test complete step execution in normal mode."""

        execution_log = []

        with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result") as mock_broadcast:

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

            mock_thought = Mock()
            mock_thought.thought_id = "flow-test"
            mock_thought.source_task_id = "task-123"
            mock_thought.initial_context = "test_initial_context"

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
            async def mock_pause(thought_id):
                execution_log.append(f"paused_at_perform_aspdma")
                # Immediate resume for testing

            with patch("ciris_engine.logic.processors.core.step_decorators._broadcast_step_result"):
                with patch("ciris_engine.logic.processors.core.step_decorators._pause_thought_execution", mock_pause):

                    @streaming_step(StepPoint.PERFORM_ASPDMA)
                    @step_point(StepPoint.PERFORM_ASPDMA)
                    async def step_with_pause(self, thought_item):
                        execution_log.append("step_executed")
                        result = Mock()
                        result.selected_action = "test_action"
                        result.rationale = "test rationale"
                        return result

                    mock_processor = Mock()
                    mock_processor._time_service = Mock()
                    mock_processor._time_service.now.return_value = datetime.now(timezone.utc)

                    mock_thought = Mock()
                    mock_thought.thought_id = "pause-test"
                    mock_thought.source_task_id = "task-123"

                    result = await step_with_pause(mock_processor, mock_thought)

                    # Verify pause occurred before execution
                    assert execution_log == ["paused_at_perform_aspdma", "step_executed"]
                    assert result.selected_action == "test_action"
        finally:
            # CRITICAL: Always disable single-step mode to prevent test order dependencies
            disable_single_step_mode()
            _paused_thoughts.clear()


class TestRefactoredHelperFunctions:
    """Test the refactored helper functions for cognitive complexity reduction."""

    def test_create_step_result_schema_gather_context(self):
        """Test _create_step_result_schema for GATHER_CONTEXT step."""
        step_data = GatherContextStepData(
            thought_id="test-123",
            task_id="task-456",
            success=True,
            timestamp="2025-01-15T12:00:00Z",
            processing_time_ms=100,
            context="test_context_data",
        )

        result = _create_step_result_schema(StepPoint.GATHER_CONTEXT, step_data)

        assert result is not None
        assert result.thought_id == "test-123"
        assert result.task_id == "task-456"
        assert result.success is True
        assert result.timestamp == "2025-01-15T12:00:00Z"
        assert result.processing_time_ms == 100

    def test_create_step_result_schema_perform_dmas(self):
        """Test _create_step_result_schema for PERFORM_DMAS step."""
        step_data = PerformDMAsStepData(
            thought_id="test-123",
            task_id="task-456",
            success=True,
            timestamp="2025-01-15T12:00:00Z",
            processing_time_ms=150,
            context="test_context",
            dma_results="ethical_pdma: test",
        )

        result = _create_step_result_schema(StepPoint.PERFORM_DMAS, step_data)

        assert result is not None
        assert result.thought_id == "test-123"
        assert result.context == "test_context"
        assert result.success is True

    def test_create_step_result_schema_unsupported_step(self):
        """Test _create_step_result_schema returns None for unsupported step types."""
        step_data = {"thought_id": "test-123"}

        # Create a mock StepPoint that's not in the map
        fake_step = Mock()
        fake_step.name = "FAKE_STEP"

        result = _create_step_result_schema(fake_step, step_data)

        assert result is None

    def test_extract_timing_data_with_timestamp(self):
        """Test _extract_timing_data extracts timing from timestamp."""
        step_data = BaseStepData(timestamp="2025-01-15T12:00:00Z", thought_id="test-123", processing_time_ms=100.0)

        start_time, end_time = _extract_timing_data(step_data)

        # Should parse the timestamp
        assert start_time.year == 2025
        assert start_time.month == 1
        assert start_time.day == 15
        assert start_time.hour == 12
        # end_time should be current time
        assert end_time is not None

    def test_extract_timing_data_with_timezone(self):
        """Test _extract_timing_data handles timezone offsets."""
        step_data = BaseStepData(timestamp="2025-01-15T12:00:00+00:00", thought_id="test-123", processing_time_ms=100.0)

        start_time, end_time = _extract_timing_data(step_data)

        # Should handle timezone properly
        assert start_time.tzinfo is not None
        assert end_time.tzinfo is not None

    def test_extract_timing_data_missing_timestamp(self):
        """Test _extract_timing_data uses current time when timestamp missing."""
        step_data = BaseStepData(
            thought_id="test-123", processing_time_ms=100.0, timestamp=""  # Empty timestamp to test fallback
        )

        start_time, end_time = _extract_timing_data(step_data)

        # Should use current time
        assert start_time is not None
        assert end_time is not None

    def test_build_step_result_data_complete(self):
        """Test _build_step_result_data builds complete result data structure."""
        step = StepPoint.GATHER_CONTEXT
        step_data = GatherContextStepData(
            thought_id="test-123",
            success=True,
            processing_time_ms=100.0,
            task_id="task-456",
            timestamp="2023-01-01T00:00:00",
            context="test context",
        )
        step_result = Mock()
        step_result.model_dump.return_value = {"serialized": "data"}

        trace_context = TraceContext(
            trace_id="trace-123",
            span_id="span-456",
            span_name="test",
            operation_name="test",
            start_time_ns=1000,
            end_time_ns=2000,
            duration_ns=1000,
        )
        span_attributes = [SpanAttribute(key="test_key", value={"stringValue": "test_value"})]

        result = _build_step_result_data(step, step_data, trace_context, span_attributes)

        assert result.step_point == "gather_context"
        assert result.thought_id == "test-123"
        assert result.success is True
        assert result.processing_time_ms == 100.0
        assert result.task_id == "task-456"
        assert result.step_data == step_data
        assert result.trace_context == trace_context
        assert result.span_attributes == span_attributes
        assert result.otlp_compatible is True

    def test_build_step_result_data_missing_fields(self):
        """Test _build_step_result_data handles missing optional fields."""
        step = StepPoint.PERFORM_DMAS
        step_data = PerformDMAsStepData(
            thought_id="",
            success=True,
            processing_time_ms=0.0,
            timestamp="2023-01-01T00:00:00",
            dma_results="test results",
            context="test context",
        )
        step_result = Mock()
        step_result.model_dump.return_value = {"some": "data"}

        trace_context = TraceContext(
            trace_id="trace-123",
            span_id="span-456",
            span_name="test",
            operation_name="test",
            start_time_ns=1000,
            end_time_ns=2000,
            duration_ns=1000,
        )

        result = _build_step_result_data(step, step_data, trace_context, [])

        assert result.step_point == "perform_dmas"
        assert result.thought_id == ""  # Default empty string
        assert result.task_id == ""  # Default empty string
        assert result.success is True  # Default True
        assert result.processing_time_ms == 0.0  # Default 0.0
        assert result.step_data == step_data

    def test_add_gather_context_attributes_success(self):
        """Test _add_gather_context_attributes adds context data."""
        attributes = []
        result_data = {"context": "test_context_data"}

        _add_gather_context_attributes(attributes, result_data)

        expected_attrs = [
            SpanAttribute(key="context.size_bytes", value={"intValue": len("test_context_data")}),
            SpanAttribute(key="context.available", value={"boolValue": True}),
        ]
        assert attributes == expected_attrs

    def test_add_gather_context_attributes_no_context(self):
        """Test _add_gather_context_attributes handles missing context gracefully."""
        attributes = []
        result_data = {"source_task_id": "task-789"}  # Missing context

        _add_gather_context_attributes(attributes, result_data)

        # Should not add any attributes when context is missing
        assert attributes == []

    def test_add_gather_context_attributes_empty_context(self):
        """Test _add_gather_context_attributes handles empty context."""
        attributes = []
        result_data = {"context": ""}  # Empty context

        _add_gather_context_attributes(attributes, result_data)

        # Should not add attributes for empty context
        assert attributes == []

    def test_add_perform_dmas_attributes_success(self):
        """Test _add_perform_dmas_attributes adds DMA results and context."""
        attributes = []
        result_data = {"dma_results": "ethical_pdma: result1; csdma: result2", "context": "initial_context_data"}

        _add_perform_dmas_attributes(attributes, result_data)

        expected_attrs = [
            SpanAttribute(key="dma.results_available", value={"boolValue": True}),
            SpanAttribute(key="dma.results_size", value={"intValue": len("ethical_pdma: result1; csdma: result2")}),
            SpanAttribute(key="dma.context_provided", value={"boolValue": True}),
        ]
        assert attributes == expected_attrs

    def test_add_perform_dmas_attributes_missing_dma_results(self):
        """Test _add_perform_dmas_attributes handles missing DMA results gracefully."""
        attributes = []
        result_data = {"context": "test_context"}  # Missing dma_results

        _add_perform_dmas_attributes(attributes, result_data)

        # Should only add context attribute
        expected_attrs = [SpanAttribute(key="dma.context_provided", value={"boolValue": True})]
        assert attributes == expected_attrs

    def test_add_perform_aspdma_attributes_success(self):
        """Test _add_perform_aspdma_attributes adds selected action."""
        attributes = []
        result_data = {"selected_action": "speak_with_confidence"}

        _add_perform_aspdma_attributes(attributes, result_data)

        expected_attrs = [SpanAttribute(key="action.selected", value={"stringValue": "speak_with_confidence"})]
        assert attributes == expected_attrs

    def test_add_conscience_execution_attributes_success(self):
        """Test _add_conscience_execution_attributes adds conscience data."""
        attributes = []
        result_data = {"selected_action": "reject", "conscience_passed": False}

        _add_conscience_execution_attributes(attributes, result_data)

        expected_attrs = [
            SpanAttribute(key="conscience.passed", value={"boolValue": False}),
            SpanAttribute(key="conscience.action", value={"stringValue": "reject"}),
        ]
        assert attributes == expected_attrs

    def test_add_finalize_action_attributes_success(self):
        """Test _add_finalize_action_attributes adds action and reasoning."""
        attributes = []
        result_data = {"selected_action": "speak", "selection_reasoning": "User needs helpful response"}

        _add_finalize_action_attributes(attributes, result_data)

        expected_attrs = [
            SpanAttribute(key="finalized.action", value={"stringValue": "speak"}),
            SpanAttribute(key="finalized.has_reasoning", value={"boolValue": True}),
        ]
        assert attributes == expected_attrs

    def test_add_perform_action_attributes_success(self):
        """Test _add_perform_action_attributes adds action data."""
        attributes = []
        result_data = {"action_executed": "respond_helpfully", "dispatch_success": True}

        _add_perform_action_attributes(attributes, result_data)

        expected_attrs = [
            SpanAttribute(key="action.executed", value={"stringValue": "respond_helpfully"}),
            SpanAttribute(key="action.dispatch_success", value={"boolValue": True}),
        ]
        assert attributes == expected_attrs

    def test_add_action_complete_attributes_success(self):
        """Test _add_action_complete_attributes adds completion data."""
        attributes = []
        result_data = {"handler_completed": True, "execution_time_ms": 150.5}

        _add_action_complete_attributes(attributes, result_data)

        expected_attrs = [
            SpanAttribute(key="action.handler_completed", value={"boolValue": True}),
            SpanAttribute(key="action.execution_time_ms", value={"doubleValue": 150.5}),
        ]
        assert attributes == expected_attrs

    def test_add_typed_step_attributes_gather_context(self):
        """Test _add_typed_step_attributes dispatches to correct handler."""
        attributes = []
        result_data = {"context": "test_context"}

        _add_typed_step_attributes(attributes, StepPoint.GATHER_CONTEXT, result_data)

        # Should have called _add_gather_context_attributes
        expected_attrs = [
            SpanAttribute(key="context.size_bytes", value={"intValue": len("test_context")}),
            SpanAttribute(key="context.available", value={"boolValue": True}),
        ]
        assert attributes == expected_attrs

    def test_add_typed_step_attributes_perform_dmas(self):
        """Test _add_typed_step_attributes dispatches to PERFORM_DMAS handler."""
        attributes = []
        result_data = {"dma_results": "ethical_pdma: safe; csdma: clear", "context": "test_context"}

        _add_typed_step_attributes(attributes, StepPoint.PERFORM_DMAS, result_data)

        # Should have called _add_perform_dmas_attributes
        expected_attrs = [
            SpanAttribute(key="dma.results_available", value={"boolValue": True}),
            SpanAttribute(key="dma.results_size", value={"intValue": len("ethical_pdma: safe; csdma: clear")}),
            SpanAttribute(key="dma.context_provided", value={"boolValue": True}),
        ]
        assert attributes == expected_attrs

    def test_add_typed_step_attributes_conscience_execution(self):
        """Test _add_typed_step_attributes dispatches to CONSCIENCE_EXECUTION handler."""
        attributes = []
        result_data = {"selected_action": "speak", "conscience_passed": True}

        _add_typed_step_attributes(attributes, StepPoint.CONSCIENCE_EXECUTION, result_data)

        # Should have called _add_conscience_execution_attributes
        expected_attrs = [
            SpanAttribute(key="conscience.passed", value={"boolValue": True}),
            SpanAttribute(key="conscience.action", value={"stringValue": "speak"}),
        ]
        assert attributes == expected_attrs

    def test_add_typed_step_attributes_finalize_action(self):
        """Test _add_typed_step_attributes dispatches to FINALIZE_ACTION handler."""
        attributes = []
        result_data = {"selected_action": "listen"}

        _add_typed_step_attributes(attributes, StepPoint.FINALIZE_ACTION, result_data)

        # Should have called _add_finalize_action_attributes
        expected_attrs = [SpanAttribute(key="finalized.action", value={"stringValue": "listen"})]
        assert attributes == expected_attrs

    def test_add_typed_step_attributes_perform_action(self):
        """Test _add_typed_step_attributes dispatches to PERFORM_ACTION handler."""
        attributes = []
        result_data = {"action_executed": "provide_information", "dispatch_success": False}

        _add_typed_step_attributes(attributes, StepPoint.PERFORM_ACTION, result_data)

        # Should have called _add_perform_action_attributes
        expected_attrs = [
            SpanAttribute(key="action.executed", value={"stringValue": "provide_information"}),
            SpanAttribute(key="action.dispatch_success", value={"boolValue": False}),
        ]
        assert attributes == expected_attrs

    def test_add_typed_step_attributes_action_complete(self):
        """Test _add_typed_step_attributes dispatches to ACTION_COMPLETE handler."""
        attributes = []
        result_data = {"handler_completed": True}

        _add_typed_step_attributes(attributes, StepPoint.ACTION_COMPLETE, result_data)

        # Should have called _add_action_complete_attributes
        expected_attrs = [SpanAttribute(key="action.handler_completed", value={"boolValue": True})]
        assert attributes == expected_attrs

    def test_add_typed_step_attributes_perform_aspdma(self):
        """Test _add_typed_step_attributes dispatches to PERFORM_ASPDMA handler."""
        attributes = []
        result_data = {"selected_action": "analyze_deeply"}

        _add_typed_step_attributes(attributes, StepPoint.PERFORM_ASPDMA, result_data)

        # Should have called _add_perform_aspdma_attributes
        expected_attrs = [SpanAttribute(key="action.selected", value={"stringValue": "analyze_deeply"})]
        assert attributes == expected_attrs

    def test_add_typed_step_attributes_unsupported_step(self):
        """Test _add_typed_step_attributes handles unsupported step types gracefully."""
        attributes = []
        result_data = {"some_data": "test"}

        # Use a step type not in the dispatch map
        fake_step = Mock()
        fake_step.name = "FAKE_STEP_TYPE"

        # Should not raise exception, should just not add any attributes
        _add_typed_step_attributes(attributes, fake_step, result_data)

        # No attributes should be added
        assert attributes == []

    def test_add_typed_step_attributes_handler_no_match(self):
        """Test _add_typed_step_attributes handles empty result data gracefully."""
        attributes = []
        result_data = {}  # Empty result_data should not match any conditions

        # Should not add any attributes when no data matches
        _add_typed_step_attributes(attributes, StepPoint.GATHER_CONTEXT, result_data)

        # No attributes should be added
        assert attributes == []


class TestNewHelperFunctions:
    """Test newly created helper functions from refactoring for reduced complexity."""

    def test_validate_conscience_execution_result_valid(self):
        """Test _validate_conscience_execution_result with valid result."""
        # Import the function
        from ciris_engine.logic.processors.core.step_decorators import _validate_conscience_execution_result

        # Create mock result with required attributes
        mock_result = Mock()
        mock_result.overridden = False
        mock_result.final_action = Mock()
        mock_result.final_action.selected_action = "proceed"

        # Should not raise any exception
        _validate_conscience_execution_result(mock_result)

    def test_validate_conscience_execution_result_none_result(self):
        """Test _validate_conscience_execution_result with None result."""
        from ciris_engine.logic.processors.core.step_decorators import _validate_conscience_execution_result

        with pytest.raises(ValueError, match="CONSCIENCE_EXECUTION step result is None"):
            _validate_conscience_execution_result(None)

    def test_validate_conscience_execution_result_missing_overridden(self):
        """Test _validate_conscience_execution_result with missing overridden attribute."""
        from ciris_engine.logic.processors.core.step_decorators import _validate_conscience_execution_result

        mock_result = Mock(spec=[])  # Empty spec to prevent auto attribute creation

        with pytest.raises(AttributeError, match="missing 'overridden' attribute"):
            _validate_conscience_execution_result(mock_result)

    def test_validate_conscience_execution_result_missing_final_action(self):
        """Test _validate_conscience_execution_result with missing final_action attribute."""
        from ciris_engine.logic.processors.core.step_decorators import _validate_conscience_execution_result

        # Use an object without final_action instead of Mock
        class MockResult:
            overridden = False

        mock_result = MockResult()

        with pytest.raises(AttributeError, match="missing 'final_action' attribute"):
            _validate_conscience_execution_result(mock_result)

    def test_validate_conscience_execution_result_missing_selected_action(self):
        """Test _validate_conscience_execution_result with missing selected_action attribute."""
        from ciris_engine.logic.processors.core.step_decorators import _validate_conscience_execution_result

        mock_result = Mock()
        mock_result.overridden = False
        mock_result.final_action = Mock(spec=[])  # Empty spec

        with pytest.raises(AttributeError, match="missing 'selected_action' attribute"):
            _validate_conscience_execution_result(mock_result)

    def test_validate_conscience_execution_result_overridden_missing_reason(self):
        """Test _validate_conscience_execution_result with overridden but missing override_reason."""
        from ciris_engine.logic.processors.core.step_decorators import _validate_conscience_execution_result

        # Use an object without override_reason instead of Mock
        class MockResult:
            overridden = True

            class MockFinalAction:
                selected_action = "abort"

            final_action = MockFinalAction()

        mock_result = MockResult()

        with pytest.raises(AttributeError, match="overridden but missing 'override_reason'"):
            _validate_conscience_execution_result(mock_result)

    def test_validate_conscience_execution_result_overridden_with_reason(self):
        """Test _validate_conscience_execution_result with overridden and override_reason."""
        from ciris_engine.logic.processors.core.step_decorators import _validate_conscience_execution_result

        mock_result = Mock()
        mock_result.overridden = True
        mock_result.final_action = Mock()
        mock_result.final_action.selected_action = "abort"
        mock_result.override_reason = "safety_violation"

        # Should not raise any exception
        _validate_conscience_execution_result(mock_result)

    def test_extract_conscience_execution_values_not_overridden(self):
        """Test _extract_conscience_execution_values for non-overridden result."""
        from ciris_engine.logic.processors.core.step_decorators import _extract_conscience_execution_values

        mock_result = Mock()
        mock_result.overridden = False
        mock_result.final_action = Mock()
        mock_result.final_action.selected_action = "proceed"
        mock_result.final_action.__str__ = Mock(return_value="final_action_result")

        selected_action, conscience_passed, action_result, override_reason = _extract_conscience_execution_values(
            mock_result
        )

        assert selected_action == "proceed"
        assert conscience_passed is True  # not overridden
        assert action_result == "final_action_result"
        assert override_reason is None

    def test_extract_conscience_execution_values_overridden(self):
        """Test _extract_conscience_execution_values for overridden result."""
        from ciris_engine.logic.processors.core.step_decorators import _extract_conscience_execution_values

        mock_result = Mock()
        mock_result.overridden = True
        mock_result.final_action = Mock()
        mock_result.final_action.selected_action = "abort"
        mock_result.final_action.__str__ = Mock(return_value="aborted_action")
        mock_result.override_reason = "safety_concern"

        selected_action, conscience_passed, action_result, override_reason = _extract_conscience_execution_values(
            mock_result
        )

        assert selected_action == "abort"
        assert conscience_passed is False  # overridden
        assert action_result == "aborted_action"
        assert override_reason == "safety_concern"

    def test_build_conscience_result_from_check_passed(self):
        """Test _build_conscience_result_from_check for passed conscience check."""
        from ciris_engine.logic.processors.core.step_decorators import _build_conscience_result_from_check

        # Create mock conscience check result
        mock_check_result = Mock()
        mock_check_result.passed = True
        mock_check_result.reason = "All checks passed"
        mock_check_result.status = Mock()
        mock_check_result.status.value = "PASSED"

        # Mock the nested check results
        mock_check_result.entropy_check = Mock()
        mock_check_result.entropy_check.passed = True

        mock_check_result.coherence_check = Mock()
        mock_check_result.coherence_check.passed = True

        mock_check_result.optimization_veto_check = Mock()
        mock_check_result.optimization_veto_check.decision = "proceed"

        mock_check_result.epistemic_humility_check = Mock()
        mock_check_result.epistemic_humility_check.epistemic_certainty = 0.7

        conscience_result = _build_conscience_result_from_check(mock_check_result, None)

        assert conscience_result.conscience_name == "conscience_execution"
        assert conscience_result.passed is True
        assert conscience_result.severity == "info"  # Passed check
        assert conscience_result.message == "All checks passed"
        assert conscience_result.override_action is None
        assert conscience_result.details["status"] == "PASSED"
        assert conscience_result.details["entropy_passed"] is True
        assert conscience_result.details["coherence_passed"] is True
        assert conscience_result.details["optimization_veto"] == "proceed"
        assert conscience_result.details["epistemic_humility"] == 0.7

    def test_build_conscience_result_from_check_failed(self):
        """Test _build_conscience_result_from_check for failed conscience check."""
        from ciris_engine.logic.processors.core.step_decorators import _build_conscience_result_from_check

        # Create mock conscience check result
        mock_check_result = Mock()
        mock_check_result.passed = False
        mock_check_result.reason = "Safety violation detected"
        mock_check_result.status = Mock()
        mock_check_result.status.value = "FAILED"

        # Mock the nested check results
        mock_check_result.entropy_check = Mock()
        mock_check_result.entropy_check.passed = False

        mock_check_result.coherence_check = Mock()
        mock_check_result.coherence_check.passed = False

        mock_check_result.optimization_veto_check = Mock()
        mock_check_result.optimization_veto_check.decision = "abort"

        mock_check_result.epistemic_humility_check = Mock()
        mock_check_result.epistemic_humility_check.epistemic_certainty = 0.9

        conscience_result = _build_conscience_result_from_check(mock_check_result, "safety_override")

        assert conscience_result.conscience_name == "conscience_execution"
        assert conscience_result.passed is False
        assert conscience_result.severity == "critical"  # Failed check
        assert conscience_result.message == "Safety violation detected"
        assert conscience_result.override_action == "safety_override"
        assert conscience_result.details["status"] == "FAILED"
        assert conscience_result.details["entropy_passed"] is False
        assert conscience_result.details["coherence_passed"] is False
        assert conscience_result.details["optimization_veto"] == "abort"
        assert conscience_result.details["epistemic_humility"] == 0.9

    def test_build_conscience_result_from_check_no_reason(self):
        """Test _build_conscience_result_from_check with no reason provided."""
        from ciris_engine.logic.processors.core.step_decorators import _build_conscience_result_from_check

        mock_check_result = Mock()
        mock_check_result.passed = True
        mock_check_result.reason = None  # No specific reason
        mock_check_result.status = None
        mock_check_result.entropy_check = None
        mock_check_result.coherence_check = None
        mock_check_result.optimization_veto_check = None
        mock_check_result.epistemic_humility_check = None

        conscience_result = _build_conscience_result_from_check(mock_check_result, None)

        assert conscience_result.conscience_name == "conscience_execution"
        assert conscience_result.passed is True
        assert conscience_result.severity == "info"  # Passed check
        assert conscience_result.message == "Conscience check completed"  # Default message
        assert conscience_result.override_action is None
        assert conscience_result.details["status"] == "unknown"  # No status
        # None values are excluded from details dict
        assert "entropy_passed" not in conscience_result.details
        assert "coherence_passed" not in conscience_result.details
        assert "optimization_veto" not in conscience_result.details
        assert "epistemic_humility" not in conscience_result.details

    def test_get_step_data_creators_contains_all_steps(self):
        """Test _get_step_data_creators returns creators for all step points."""
        from ciris_engine.logic.processors.core.step_decorators import _get_step_data_creators
        from ciris_engine.schemas.services.runtime_control import StepPoint

        creators = _get_step_data_creators()

        # Check all step points are covered
        expected_steps = [
            StepPoint.START_ROUND,
            StepPoint.GATHER_CONTEXT,
            StepPoint.PERFORM_DMAS,
            StepPoint.PERFORM_ASPDMA,
            StepPoint.CONSCIENCE_EXECUTION,
            StepPoint.RECURSIVE_ASPDMA,
            StepPoint.RECURSIVE_CONSCIENCE,
            StepPoint.FINALIZE_ACTION,
            StepPoint.PERFORM_ACTION,
            StepPoint.ACTION_COMPLETE,
            StepPoint.ROUND_COMPLETE,
        ]

        for step in expected_steps:
            assert step in creators, f"Missing creator for {step}"
            assert callable(creators[step]), f"Creator for {step} is not callable"

    def test_get_step_data_creators_callable_signature(self):
        """Test _get_step_data_creators returns callables with correct signature."""
        from ciris_engine.logic.processors.core.step_decorators import _get_step_data_creators
        from ciris_engine.schemas.services.runtime_control import StepPoint

        creators = _get_step_data_creators()

        # Test one creator to verify signature (they all have same lambda signature)
        creator = creators[StepPoint.GATHER_CONTEXT]

        # Mock parameters
        base_data = Mock()
        result = Mock()
        args = ()
        kwargs = {}
        thought_item = Mock()

        # Should be callable with expected parameters (though it may fail due to mocked data)
        try:
            creator(base_data, result, args, kwargs, thought_item)
        except Exception:
            # Expected to fail with mocked data, but should be callable
            pass

    def test_prepare_base_data_with_task_id_with_task_id(self):
        """Test _prepare_base_data_with_task_id when thought_item has source_task_id."""
        from ciris_engine.logic.processors.core.step_decorators import _prepare_base_data_with_task_id

        # Mock base data and thought item
        mock_base_data = Mock()
        mock_base_data.model_copy = Mock(return_value="updated_base_data")

        mock_thought_item = Mock()
        mock_thought_item.source_task_id = "test-task-456"

        result = _prepare_base_data_with_task_id(mock_base_data, mock_thought_item)

        mock_base_data.model_copy.assert_called_once_with(update={"task_id": "test-task-456"})
        assert result == "updated_base_data"

    def test_prepare_base_data_with_task_id_no_task_id(self):
        """Test _prepare_base_data_with_task_id when thought_item has no source_task_id."""
        from ciris_engine.logic.processors.core.step_decorators import _prepare_base_data_with_task_id

        # Mock base data and thought item
        mock_base_data = Mock()
        mock_base_data.model_copy = Mock(return_value="updated_base_data")

        mock_thought_item = Mock(spec=[])  # No source_task_id attribute

        result = _prepare_base_data_with_task_id(mock_base_data, mock_thought_item)

        mock_base_data.model_copy.assert_called_once_with(update={"task_id": None})
        assert result == "updated_base_data"

    def test_log_step_debug_info_with_task_id(self):
        """Test _log_step_debug_info logs correctly when task_id is present."""
        from ciris_engine.logic.processors.core.step_decorators import _log_step_debug_info
        from ciris_engine.schemas.services.runtime_control import StepPoint

        with patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:
            # Mock data
            step = StepPoint.GATHER_CONTEXT
            mock_base_data = Mock()
            mock_base_data.task_id = "test-task-456"
            mock_base_data.thought_id = "test-thought-123"

            mock_thought_item = Mock()

            _log_step_debug_info(step, mock_base_data, mock_thought_item)

            # Should log debug message - check it was called
            mock_logger.debug.assert_called_once()
            # Should not log warning since task_id exists
            mock_logger.warning.assert_not_called()

    def test_log_step_debug_info_no_task_id(self):
        """Test _log_step_debug_info logs warning when task_id is missing."""
        from ciris_engine.logic.processors.core.step_decorators import _log_step_debug_info
        from ciris_engine.schemas.services.runtime_control import StepPoint

        with patch("ciris_engine.logic.processors.core.step_decorators.logger") as mock_logger:
            # Mock data
            step = StepPoint.PERFORM_DMAS
            mock_base_data = Mock()
            mock_base_data.task_id = None  # Missing task_id
            mock_base_data.thought_id = "test-thought-789"

            mock_thought_item = Mock()

            _log_step_debug_info(step, mock_base_data, mock_thought_item)

            # Should log debug message
            mock_logger.debug.assert_called_once()
            # Should log warning when task_id is None
            mock_logger.warning.assert_called_once()

    def test_create_typed_step_data_dispatch_success(self):
        """Test _create_typed_step_data uses dispatch pattern correctly."""
        from ciris_engine.logic.processors.core.step_decorators import _create_typed_step_data
        from ciris_engine.schemas.services.runtime_control import StepPoint

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._prepare_base_data_with_task_id"
        ) as mock_prepare, patch(
            "ciris_engine.logic.processors.core.step_decorators._log_step_debug_info"
        ) as mock_log, patch(
            "ciris_engine.logic.processors.core.step_decorators._get_step_data_creators"
        ) as mock_get_creators:

            # Mock prepared base data
            mock_prepared_base_data = Mock()
            mock_prepare.return_value = mock_prepared_base_data

            # Mock creator function
            mock_creator = Mock(return_value="step_data_result")
            mock_creators = {StepPoint.GATHER_CONTEXT: mock_creator}
            mock_get_creators.return_value = mock_creators

            # Test data
            step = StepPoint.GATHER_CONTEXT
            mock_base_data = Mock()
            mock_thought_item = Mock()
            result = "test_result"
            args = ("arg1",)
            kwargs = {"key": "value"}

            # Execute
            output = _create_typed_step_data(step, mock_base_data, mock_thought_item, result, args, kwargs)

            # Verify
            mock_prepare.assert_called_once_with(mock_base_data, mock_thought_item)
            mock_log.assert_called_once_with(step, mock_prepared_base_data, mock_thought_item)
            mock_creator.assert_called_once_with(mock_prepared_base_data, result, args, kwargs, mock_thought_item)
            assert output == "step_data_result"

    def test_create_typed_step_data_unknown_step(self):
        """Test _create_typed_step_data fails fast for unknown step."""
        from ciris_engine.logic.processors.core.step_decorators import _create_typed_step_data

        with patch(
            "ciris_engine.logic.processors.core.step_decorators._prepare_base_data_with_task_id"
        ) as mock_prepare, patch(
            "ciris_engine.logic.processors.core.step_decorators._log_step_debug_info"
        ) as mock_log, patch(
            "ciris_engine.logic.processors.core.step_decorators._get_step_data_creators"
        ) as mock_get_creators:

            mock_prepare.return_value = Mock()
            mock_get_creators.return_value = {}  # Empty creators dict

            # Create a mock unknown step
            unknown_step = Mock()
            unknown_step.value = "UNKNOWN_STEP"

            with pytest.raises(ValueError, match="Unknown step point: UNKNOWN_STEP"):
                _create_typed_step_data(unknown_step, Mock(), Mock(), None, (), {})

    def test_create_typed_step_data_integration_end_to_end(self):
        """Test _create_typed_step_data integration with actual helper functions."""
        from datetime import datetime, timezone

        from ciris_engine.logic.processors.core.step_decorators import _create_typed_step_data
        from ciris_engine.schemas.services.runtime_control import BaseStepData, StepPoint

        # Create real base data with all required fields
        base_data = BaseStepData(
            timestamp=datetime.now(timezone.utc).isoformat(),
            thought_id="test-thought-123",
            processing_time_ms=100,
            success=True,
        )

        # Mock thought item
        mock_thought_item = Mock()
        mock_thought_item.source_task_id = "test-task-456"

        # Mock result for GATHER_CONTEXT
        mock_result = Mock()
        mock_result.context_count = 5

        # This should work with real dispatch pattern (though may fail on actual step creation)
        try:
            result = _create_typed_step_data(
                StepPoint.GATHER_CONTEXT, base_data, mock_thought_item, mock_result, (), {}
            )
            # If it doesn't throw an exception, the dispatch pattern worked
        except Exception as e:
            # Expected to fail due to mock result, but should get past dispatch logic
            assert "Unknown step point" not in str(e), f"Dispatch failed: {e}"
