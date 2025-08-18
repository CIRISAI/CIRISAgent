"""
Comprehensive tests for the pipeline single-stepping system.

Tests the ability to pause the agent processor and step through
the processing pipeline one step at a time.
"""

import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.logic.processors.core.main_processor import AgentProcessor
from ciris_engine.logic.services.runtime.control_service import RuntimeControlService
from ciris_engine.protocols.pipeline_control import PipelineController
from ciris_engine.schemas.processors.states import AgentState
from ciris_engine.schemas.runtime.models import Task, TaskStatus, Thought, ThoughtStatus
from ciris_engine.schemas.services.core.runtime import ProcessorControlResponse, ProcessorStatus
from ciris_engine.schemas.services.runtime_control import (
    PipelineState,
    StepDuration,
    StepPoint,
    StepResultActionSelection,
    StepResultBuildContext,
    StepResultFinalizeTasksQueue,
    StepResultPerformASPDMA,
    StepResultPerformDMAs,
    ThoughtInPipeline,
)


class TestAgentProcessorPause:
    """Test pausing and resuming the agent processor."""

    @pytest.fixture
    def mock_services(self):
        """Create mock services for testing."""
        return {
            "time_service": Mock(),
            "memory_service": Mock(),
            "llm_service": Mock(),
            "config_service": Mock(),
        }

    @pytest.fixture
    def agent_processor(self, mock_services):
        """Create an agent processor for testing."""
        mock_config = Mock()
        mock_identity = Mock()
        mock_thought_processor = Mock()
        mock_dispatcher = Mock()
        mock_time_service = Mock()
        mock_time_service.now.return_value = datetime.now(timezone.utc)

        processor = AgentProcessor(
            app_config=mock_config,
            agent_identity=mock_identity,
            thought_processor=mock_thought_processor,
            action_dispatcher=mock_dispatcher,
            services=mock_services,
            startup_channel_id="test_channel",
            time_service=mock_time_service,
        )

        return processor

    @pytest.mark.asyncio
    async def test_pause_processor(self, agent_processor):
        """Test pausing the agent processor."""
        # Initially not paused
        assert not agent_processor.is_paused()

        # Pause the processor
        success = await agent_processor.pause_processing()
        assert success
        assert agent_processor.is_paused()

        # Pausing again should still succeed
        success = await agent_processor.pause_processing()
        assert success
        assert agent_processor.is_paused()

    @pytest.mark.asyncio
    async def test_resume_processor(self, agent_processor):
        """Test resuming the agent processor."""
        # Resume when not paused should fail
        success = await agent_processor.resume_processing()
        assert not success

        # Pause first
        await agent_processor.pause_processing()
        assert agent_processor.is_paused()

        # Now resume
        success = await agent_processor.resume_processing()
        assert success
        assert not agent_processor.is_paused()

    @pytest.mark.asyncio
    async def test_pipeline_controller_created_on_pause(self, agent_processor):
        """Test that pipeline controller is created when pausing."""
        assert agent_processor._pipeline_controller is None

        # Pause creates pipeline controller
        await agent_processor.pause_processing()

        assert agent_processor._pipeline_controller is not None
        assert isinstance(agent_processor._pipeline_controller, PipelineController)
        assert agent_processor._pipeline_controller.is_paused

    @pytest.mark.asyncio
    async def test_single_step_requires_pause(self, agent_processor):
        """Test that single-stepping requires the processor to be paused."""
        # Single-step without pause should fail
        result = await agent_processor.single_step()

        assert not result["success"]
        assert "Cannot single-step unless paused" in result["error"]

        # Pause first
        await agent_processor.pause_processing()

        # Now single-step should work (though no thoughts to process)
        with patch("ciris_engine.logic.persistence.get_thoughts_by_status") as mock_get:
            mock_get.return_value = []

            result = await agent_processor.single_step()

            assert result["success"]
            assert result.get("pipeline_empty")


class TestPipelineController:
    """Test the pipeline controller functionality."""

    @pytest.fixture
    def pipeline_controller(self):
        """Create a pipeline controller for testing."""
        return PipelineController(is_paused=True)

    def test_initial_state(self, pipeline_controller):
        """Test initial state of pipeline controller."""
        assert pipeline_controller.is_paused
        assert len(pipeline_controller._paused_thoughts) == 0
        assert len(pipeline_controller._resume_events) == 0
        assert not pipeline_controller._single_step_mode

        # All step points enabled by default
        assert len(pipeline_controller._enabled_step_points) == len(StepPoint)

    @pytest.mark.asyncio
    async def test_should_pause_at_step_point(self, pipeline_controller):
        """Test logic for determining whether to pause at a step point."""
        thought_id = "test_thought_1"

        # Not paused - should not pause at any step
        pipeline_controller.is_paused = False
        assert not await pipeline_controller.should_pause_at(StepPoint.BUILD_CONTEXT, thought_id)

        # Paused but step point not enabled
        pipeline_controller.is_paused = True
        pipeline_controller._enabled_step_points = set()
        assert not await pipeline_controller.should_pause_at(StepPoint.BUILD_CONTEXT, thought_id)

        # Paused and step point enabled in single-step mode
        pipeline_controller._enabled_step_points = {StepPoint.BUILD_CONTEXT}
        pipeline_controller._single_step_mode = True
        assert await pipeline_controller.should_pause_at(StepPoint.BUILD_CONTEXT, thought_id)

    def test_drain_pipeline_step(self, pipeline_controller):
        """Test draining pipeline processes later steps first."""
        # Add thoughts at different steps
        thought1 = ThoughtInPipeline(
            thought_id="thought_1",
            task_id="task_1",
            thought_type="standard",
            current_step=StepPoint.BUILD_CONTEXT,
            entered_step_at=datetime.now(timezone.utc),
        )

        thought2 = ThoughtInPipeline(
            thought_id="thought_2",
            task_id="task_1",
            thought_type="standard",
            current_step=StepPoint.HANDLER_COMPLETE,
            entered_step_at=datetime.now(timezone.utc),
        )

        thought3 = ThoughtInPipeline(
            thought_id="thought_3",
            task_id="task_2",
            thought_type="standard",
            current_step=StepPoint.ACTION_SELECTION,
            entered_step_at=datetime.now(timezone.utc),
        )

        # Add to pipeline state
        pipeline_controller.pipeline_state.thoughts_by_step[StepPoint.BUILD_CONTEXT.value] = [thought1]
        pipeline_controller.pipeline_state.thoughts_by_step[StepPoint.HANDLER_COMPLETE.value] = [thought2]
        pipeline_controller.pipeline_state.thoughts_by_step[StepPoint.ACTION_SELECTION.value] = [thought3]

        # Drain should return thought2 first (HANDLER_COMPLETE is latest)
        next_thought = pipeline_controller.drain_pipeline_step()
        assert next_thought == "thought_2"

    @pytest.mark.asyncio
    async def test_pause_and_resume_thought(self, pipeline_controller):
        """Test pausing and resuming individual thoughts."""
        thought_id = "test_thought_1"

        # Create resume event
        pipeline_controller._resume_events[thought_id] = asyncio.Event()

        # Start waiting (will block)
        wait_task = asyncio.create_task(pipeline_controller.wait_for_resume(thought_id))

        # Give it a moment to start waiting
        await asyncio.sleep(0.01)

        # Should still be waiting
        assert not wait_task.done()

        # Resume the thought
        pipeline_controller.resume_thought(thought_id)

        # Wait should complete
        await wait_task
        assert wait_task.done()

    def test_abort_thought(self, pipeline_controller):
        """Test aborting a thought."""
        thought_id = "test_thought_1"

        # Initially not aborted
        assert not pipeline_controller.should_abort(thought_id)

        # Mark for abortion
        pipeline_controller.abort_thought(thought_id)

        # Should now be aborted
        assert pipeline_controller.should_abort(thought_id)


class TestRuntimeControlServiceSingleStep:
    """Test RuntimeControlService single-step functionality."""

    @pytest.fixture
    def mock_runtime(self):
        """Create mock runtime with agent processor."""
        mock_runtime = Mock()
        mock_processor = AsyncMock()
        mock_processor.is_paused.return_value = True
        mock_processor.single_step.return_value = {
            "success": True,
            "thought_id": "test_thought",
            "processing_time_ms": 150.0,
            "current_step": "build_context",
        }
        mock_runtime.agent_processor = mock_processor
        return mock_runtime

    @pytest.fixture
    def control_service(self, mock_runtime):
        """Create runtime control service for testing."""
        service = RuntimeControlService()
        service.runtime = mock_runtime
        return service

    @pytest.mark.asyncio
    async def test_single_step_requires_paused_processor(self, control_service):
        """Test single-step requires processor to be paused."""
        # Processor not paused
        control_service.runtime.agent_processor.is_paused.return_value = False

        response = await control_service.single_step()

        assert not response.success
        assert "Cannot single-step unless processor is paused" in response.error

    @pytest.mark.asyncio
    async def test_single_step_tracks_thought_time(self, control_service):
        """Test single-step tracks thought processing time."""
        # Initial state
        assert len(control_service._thought_times) == 0
        assert control_service._thoughts_processed == 0

        # Execute single step
        response = await control_service.single_step()

        assert response.success

        # Should track the thought time
        assert len(control_service._thought_times) == 1
        assert control_service._thought_times[0] == 150.0
        assert control_service._thoughts_processed == 1
        assert control_service._average_thought_time_ms == 150.0

    @pytest.mark.asyncio
    async def test_thought_times_list_trimmed(self, control_service):
        """Test thought times list is trimmed to max history."""
        control_service._max_thought_history = 3

        # Add several thought times
        for i in range(5):
            control_service.runtime.agent_processor.single_step.return_value = {
                "success": True,
                "processing_time_ms": float(100 + i * 10),
            }
            await control_service.single_step()

        # Should only keep last 3
        assert len(control_service._thought_times) == 3
        assert control_service._thought_times == [120.0, 130.0, 140.0]

        # Average should be of last 3
        assert control_service._average_thought_time_ms == 130.0


class TestPipelineStateTracking:
    """Test tracking thoughts through the pipeline."""

    @pytest.fixture
    def pipeline_state(self):
        """Create pipeline state for testing."""
        return PipelineState()

    def test_initial_pipeline_state(self, pipeline_state):
        """Test initial pipeline state."""
        assert not pipeline_state.is_paused
        assert pipeline_state.current_round == 0
        assert pipeline_state.total_thoughts_processed == 0
        assert pipeline_state.total_thoughts_in_flight == 0

        # All step points should have empty lists
        for step in StepPoint:
            assert len(pipeline_state.get_thoughts_at_step(step)) == 0

    def test_move_thought_between_steps(self, pipeline_state):
        """Test moving a thought between step points."""
        # Add a thought at BUILD_CONTEXT
        thought = ThoughtInPipeline(
            thought_id="test_thought",
            task_id="test_task",
            thought_type="standard",
            current_step=StepPoint.BUILD_CONTEXT,
            entered_step_at=datetime.now(timezone.utc),
        )

        pipeline_state.thoughts_by_step[StepPoint.BUILD_CONTEXT.value] = [thought]

        # Move to PERFORM_DMAS
        success = pipeline_state.move_thought("test_thought", StepPoint.BUILD_CONTEXT, StepPoint.PERFORM_DMAS)

        assert success
        assert len(pipeline_state.get_thoughts_at_step(StepPoint.BUILD_CONTEXT)) == 0
        assert len(pipeline_state.get_thoughts_at_step(StepPoint.PERFORM_DMAS)) == 1

        moved_thought = pipeline_state.get_thoughts_at_step(StepPoint.PERFORM_DMAS)[0]
        assert moved_thought.thought_id == "test_thought"
        assert moved_thought.current_step == StepPoint.PERFORM_DMAS

    def test_get_next_step(self, pipeline_state):
        """Test getting the next step in the pipeline."""
        # Get next step for various points
        next_step = pipeline_state.get_next_step(StepPoint.FINALIZE_TASKS_QUEUE)
        assert next_step == StepPoint.POPULATE_THOUGHT_QUEUE

        next_step = pipeline_state.get_next_step(StepPoint.BUILD_CONTEXT)
        assert next_step == StepPoint.PERFORM_DMAS

        next_step = pipeline_state.get_next_step(StepPoint.ACTION_SELECTION)
        assert next_step == StepPoint.HANDLER_START

        # Last step has no next
        next_step = pipeline_state.get_next_step(StepPoint.HANDLER_COMPLETE)
        assert next_step is None


class TestStepResultSchemas:
    """Test that step result schemas work correctly."""

    def test_step_result_finalize_tasks_queue(self):
        """Test StepResultFinalizeTasksQueue schema."""
        from ciris_engine.schemas.services.runtime_control import QueuedTask

        task = QueuedTask(
            task_id="task_1",
            description="Test task",
            status="pending",
            channel_id="test_channel",
            created_at=datetime.now(timezone.utc),
            thoughts_generated=0,
        )

        result = StepResultFinalizeTasksQueue(
            success=True,
            round_number=1,
            current_state=AgentState.WORK,
            tasks_to_process=[task],
            tasks_deferred=[],
            selection_criteria={"priority": "high"},
            total_pending_tasks=5,
            total_active_tasks=2,
            tasks_selected_count=1,
            processing_time_ms=50.0,
        )

        assert result.step_point == StepPoint.FINALIZE_TASKS_QUEUE
        assert result.success
        assert len(result.tasks_to_process) == 1
        assert result.tasks_to_process[0].task_id == "task_1"

    def test_step_result_build_context(self):
        """Test StepResultBuildContext schema."""
        result = StepResultBuildContext(
            success=True,
            thought_id="thought_1",
            system_snapshot={"memory_usage": 1024},
            agent_identity={"name": "test_agent"},
            thought_context={"task_id": "task_1"},
            permitted_actions=["OBSERVE", "SPEAK"],
            context_size_bytes=2048,
            memory_queries_performed=3,
            processing_time_ms=100.0,
        )

        assert result.step_point == StepPoint.BUILD_CONTEXT
        assert result.success
        assert result.thought_id == "thought_1"
        assert "OBSERVE" in result.permitted_actions

    def test_step_result_perform_dmas(self):
        """Test StepResultPerformDMAs schema."""
        result = StepResultPerformDMAs(
            success=True,
            thought_id="thought_1",
            ethical_dma={"decision": "approve"},
            common_sense_dma={"plausibility": 0.9},
            domain_dma={"domain": "general"},
            dmas_executed=["ethical", "common_sense", "domain"],
            dma_failures=[],
            longest_dma_time_ms=150.0,
            total_time_ms=160.0,
        )

        assert result.step_point == StepPoint.PERFORM_DMAS
        assert result.success
        assert len(result.dmas_executed) == 3
        assert result.ethical_dma["decision"] == "approve"


class TestEndToEndPipelineStepping:
    """Test complete pipeline stepping flow."""

    @pytest.mark.asyncio
    async def test_complete_stepping_flow(self):
        """Test stepping through complete pipeline."""
        # This would be an integration test with all components
        # For now, just verify the concept

        controller = PipelineController(is_paused=True)
        controller._single_step_mode = True

        # Simulate thought at different steps
        thought_id = "test_thought"

        # Step 1: Build context
        step_data = {
            "task_id": "task_1",
            "thought_type": "standard",
            "timestamp": datetime.now(timezone.utc),
            "context": {"test": "data"},
        }

        # Would pause at BUILD_CONTEXT
        should_pause = await controller.should_pause_at(StepPoint.BUILD_CONTEXT, thought_id)
        assert should_pause

        # Create the thought in pipeline
        thought = ThoughtInPipeline(
            thought_id=thought_id,
            task_id="task_1",
            thought_type="standard",
            current_step=StepPoint.BUILD_CONTEXT,
            entered_step_at=datetime.now(timezone.utc),
            context_built={"test": "data"},
        )

        controller._paused_thoughts[thought_id] = thought

        # Verify we can track it through the pipeline
        assert thought.current_step == StepPoint.BUILD_CONTEXT
        assert thought.context_built == {"test": "data"}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
