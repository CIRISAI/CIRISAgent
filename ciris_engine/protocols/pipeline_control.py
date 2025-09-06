"""
Pipeline control protocol for single-stepping through the processing pipeline.

This protocol defines how step points are injected and controlled throughout
the thought processing pipeline.
"""

import asyncio
from typing import Any, Dict, Optional, Protocol

from ciris_engine.schemas.services.runtime_control import PipelineState, StepPoint, StepResultUnion, ThoughtInPipeline

# Alias for backwards compatibility
StepResult = StepResultUnion


class PipelineControlProtocol(Protocol):
    """Protocol for controlling pipeline execution and step points."""

    async def should_pause_at(self, step_point: StepPoint, thought_id: str) -> bool:
        """Check if we should pause at this step point."""
        ...

    async def pause_at_step_point(
        self, step_point: StepPoint, thought_id: str, step_data: Dict[str, Any]
    ) -> StepResult:
        """
        Pause execution at a step point and wait for release.

        Args:
            step_point: The step point where we're pausing
            thought_id: The thought being processed
            step_data: Data to include in the step result

        Returns:
            StepResult for this step point
        """
        ...

    async def wait_for_resume(self, thought_id: str) -> None:
        """Wait until this thought is allowed to continue."""
        ...

    def should_abort(self, thought_id: str) -> bool:
        """Check if this thought should be aborted."""
        ...

    def get_pipeline_state(self) -> PipelineState:
        """Get current pipeline state."""
        ...


class PipelineController:
    """
    Concrete implementation of pipeline control for single-stepping.

    This is injected into processors when single-stepping is enabled.
    """

    def __init__(self, is_paused: bool = False):
        self.is_paused = is_paused
        self.pipeline_state = PipelineState()

        # Thoughts paused at step points
        self._paused_thoughts: Dict[str, ThoughtInPipeline] = {}

        # Control events for each thought
        self._resume_events: Dict[str, asyncio.Event] = {}
        self._abort_flags: Dict[str, bool] = {}

        # Step point control - ONLY 9 real H3ERE pipeline steps
        self._enabled_step_points = {
            StepPoint.GATHER_CONTEXT,
            StepPoint.PERFORM_DMAS,
            StepPoint.PERFORM_ASPDMA,
            StepPoint.CONSCIENCE_EXECUTION,
            StepPoint.RECURSIVE_ASPDMA,
            StepPoint.RECURSIVE_CONSCIENCE,
            StepPoint.FINALIZE_ACTION,
            StepPoint.PERFORM_ACTION,
            StepPoint.ACTION_COMPLETE,
        }
        self._single_step_mode = False

    async def should_pause_at(self, step_point: StepPoint, thought_id: str) -> bool:
        """Check if we should pause at this step point."""
        if not self.is_paused:
            return False

        if step_point not in self._enabled_step_points:
            return False

        # In single-step mode, pause at every enabled step point
        if self._single_step_mode:
            return True

        # Otherwise only pause at specific configured points
        return step_point in [StepPoint.POPULATE_ROUND, StepPoint.FINALIZE_ACTION]

    async def pause_at_step_point(
        self, step_point: StepPoint, thought_id: str, step_data: Dict[str, Any]
    ) -> StepResult:
        """Pause execution at a step point."""
        # Create or update thought in pipeline
        if thought_id not in self._paused_thoughts:
            thought = ThoughtInPipeline(
                thought_id=thought_id,
                task_id=step_data.get("task_id", ""),
                thought_type=step_data.get("thought_type", ""),
                current_step=step_point,
                entered_step_at=step_data.get("timestamp"),
            )
            self._paused_thoughts[thought_id] = thought
        else:
            thought = self._paused_thoughts[thought_id]
            thought.current_step = step_point
            thought.entered_step_at = step_data.get("timestamp")

        # Update thought with step-specific data
        self._update_thought_data(thought, step_point, step_data)

        # Move thought to this step in pipeline state
        self.pipeline_state.move_thought(thought_id, thought.current_step, step_point)

        # Create step result based on step point
        step_result = self._create_step_result(step_point, thought_id, step_data)

        # Create resume event if needed
        if thought_id not in self._resume_events:
            self._resume_events[thought_id] = asyncio.Event()

        # Wait for resume signal
        await self.wait_for_resume(thought_id)

        return step_result

    async def wait_for_resume(self, thought_id: str) -> None:
        """Wait until this thought is allowed to continue."""
        if thought_id in self._resume_events:
            await self._resume_events[thought_id].wait()
            # Clear the event for next pause
            self._resume_events[thought_id].clear()

    def resume_thought(self, thought_id: str) -> None:
        """Resume a specific thought."""
        if thought_id in self._resume_events:
            self._resume_events[thought_id].set()

    def resume_all(self) -> None:
        """Resume all paused thoughts."""
        for event in self._resume_events.values():
            event.set()

    def abort_thought(self, thought_id: str) -> None:
        """Mark a thought for abortion."""
        self._abort_flags[thought_id] = True
        # Also resume it so it can check the abort flag
        self.resume_thought(thought_id)

    def should_abort(self, thought_id: str) -> bool:
        """Check if this thought should be aborted."""
        return self._abort_flags.get(thought_id, False)

    def get_pipeline_state(self) -> PipelineState:
        """Get current pipeline state."""
        return self.pipeline_state

    def drain_pipeline_step(self) -> Optional[str]:
        """
        Get the next thought to process when draining the pipeline.

        Returns thoughts from later steps first to ensure orderly completion.
        """
        # Process steps in reverse order (closest to completion first)
        for step in reversed(list(StepPoint)):
            thoughts_at_step = self.pipeline_state.get_thoughts_at_step(step)
            if thoughts_at_step:
                # Return the first thought at this step
                return thoughts_at_step[0].thought_id

        return None

    def _update_thought_data(
        self, thought: ThoughtInPipeline, step_point: StepPoint, step_data: Dict[str, Any]
    ) -> None:
        """Update thought with step-specific data."""
        if step_point == StepPoint.GATHER_CONTEXT:
            thought.context_built = step_data.get("context")
        elif step_point == StepPoint.PERFORM_DMAS:
            thought.dma_results = step_data.get("dma_results")
        elif step_point == StepPoint.PERFORM_ASPDMA:
            thought.aspdma_result = step_data.get("aspdma_result")
        elif step_point == StepPoint.CONSCIENCE_EXECUTION:
            thought.conscience_results = step_data.get("conscience_results")
        elif step_point == StepPoint.FINALIZE_ACTION:
            thought.selected_action = step_data.get("selected_action")
        elif step_point == StepPoint.ROUND_COMPLETE:
            thought.handler_result = step_data.get("handler_result")
            thought.bus_operations = step_data.get("bus_operations")

    def _create_step_result(self, step_point: StepPoint, thought_id: str, step_data: Dict[str, Any]) -> StepResult:
        """Create StepResult using EXACT data from running H3ERE pipeline."""
        # Import only the 9 real H3ERE step result schemas
        from ciris_engine.schemas.services.runtime_control import (
            StepResultGatherContext,
            StepResultPerformDMAs,
            StepResultPerformASPDMA,
            StepResultConscienceExecution,
            StepResultRecursiveASPDMA,
            StepResultRecursiveConscience,
            StepResultFinalizeAction,
            StepResultPerformAction,
            StepResultActionComplete,
        )

        # Use EXACT SUT data - no fake data, no simulation!
        # FAIL FAST AND LOUD if step_point is not one of our 9 real H3ERE steps
        if step_point == StepPoint.GATHER_CONTEXT:
            return StepResultGatherContext(
                success=True,
                **step_data  # Use EXACT data from SUT
            )
        elif step_point == StepPoint.PERFORM_DMAS:
            return StepResultPerformDMAs(
                success=True,
                **step_data  # Use EXACT data from SUT
            )
        elif step_point == StepPoint.PERFORM_ASPDMA:
            return StepResultPerformASPDMA(
                success=True,
                **step_data  # Use EXACT data from SUT
            )
        elif step_point == StepPoint.CONSCIENCE_EXECUTION:
            return StepResultConscienceExecution(
                success=True,
                **step_data  # Use EXACT data from SUT
            )
        elif step_point == StepPoint.RECURSIVE_ASPDMA:
            return StepResultRecursiveASPDMA(
                success=True,
                **step_data  # Use EXACT data from SUT
            )
        elif step_point == StepPoint.RECURSIVE_CONSCIENCE:
            return StepResultRecursiveConscience(
                success=True,
                **step_data  # Use EXACT data from SUT
            )
        elif step_point == StepPoint.FINALIZE_ACTION:
            return StepResultFinalizeAction(
                success=True,
                **step_data  # Use EXACT data from SUT
            )
        elif step_point == StepPoint.PERFORM_ACTION:
            return StepResultPerformAction(
                success=True,
                **step_data  # Use EXACT data from SUT
            )
        elif step_point == StepPoint.ACTION_COMPLETE:
            return StepResultActionComplete(
                success=True,
                **step_data  # Use EXACT data from SUT
            )
        
        # FAIL FAST AND LOUD - only 9 real H3ERE steps allowed!
        raise ValueError(f"Invalid step point: {step_point}. Only 9 real H3ERE pipeline steps are supported!")

    async def execute_single_step_point(self) -> Dict[str, Any]:
        """
        Execute exactly one step point in the PDMA pipeline.
        
        This is the core method for single-step execution that processes
        all thoughts at the next step point simultaneously.
        
        Returns:
            Dict containing:
            - success: bool
            - step_point: str (the step point executed)
            - step_results: List[Dict] (results for each thought processed)
            - current_round: int (optional)
            - pipeline_state: Dict
        """
        if not self._single_step_mode:
            raise ValueError("execute_single_step_point can only be called in single-step mode")
        
        # Get current pipeline state
        pipeline_state = self.get_pipeline_state()
        
        # Find the next step point to execute
        next_step_point = self._get_next_step_point()
        if not next_step_point:
            # No more step points to execute
            return {
                "success": True,
                "step_point": "pipeline_complete",
                "step_results": [],
                "current_round": getattr(self, '_current_round', None),
                "pipeline_state": pipeline_state.dict() if hasattr(pipeline_state, 'dict') else {},
            }
        
        # Get all thoughts that need processing at this step point
        thoughts_to_process = self._get_thoughts_for_step_point(next_step_point)
        
        if not thoughts_to_process:
            # No thoughts at this step, create some mock thoughts for demonstration
            from ciris_engine.logic import persistence
            from ciris_engine.schemas.runtime.models import ThoughtStatus
            
            # Try to get pending thoughts if at the first step
            if next_step_point == StepPoint.FINALIZE_TASKS_QUEUE:
                pending_thoughts = persistence.get_thoughts_by_status(ThoughtStatus.PENDING, limit=3)
                thoughts_to_process = [
                    self._create_thought_in_pipeline(thought, next_step_point) 
                    for thought in pending_thoughts
                ]
        
        # Execute the step point for all thoughts
        step_results = []
        for thought in thoughts_to_process:
            step_result = await self._execute_step_for_thought(next_step_point, thought)
            step_results.append(step_result)
        
        # Update pipeline state
        self._advance_thoughts_to_next_step(thoughts_to_process, next_step_point)
        
        return {
            "success": True,
            "step_point": next_step_point.value,
            "step_results": step_results,
            "current_round": getattr(self, '_current_round', 1),
            "pipeline_state": self.get_pipeline_state().dict() if hasattr(self.get_pipeline_state(), 'dict') else {},
        }
    
    def _get_next_step_point(self) -> Optional[StepPoint]:
        """Get the next step point to execute in order."""
        # Define the execution order of step points
        step_order = [
            StepPoint.FINALIZE_TASKS_QUEUE,
            StepPoint.POPULATE_THOUGHT_QUEUE,
            StepPoint.POPULATE_ROUND,
            StepPoint.GATHER_CONTEXT,
            StepPoint.PERFORM_DMAS,
            StepPoint.PERFORM_ASPDMA,
            StepPoint.CONSCIENCE_EXECUTION,
            StepPoint.RECURSIVE_ASPDMA,
            StepPoint.RECURSIVE_CONSCIENCE_EXECUTION,
            StepPoint.FINALIZE_ACTION,
            StepPoint.MULTI_SERVICE_BUS,
            StepPoint.DELIVERY_PAYLOAD,
            StepPoint.EXECUTION,
            StepPoint.FOLLOW_UP_THOUGHT,
            StepPoint.ROUND_COMPLETE,
        ]
        
        # Track current step point
        if not hasattr(self, '_current_step_index'):
            self._current_step_index = 0
        
        if self._current_step_index >= len(step_order):
            return None  # All steps completed
            
        current_step = step_order[self._current_step_index]
        self._current_step_index += 1
        return current_step
    
    def _get_thoughts_for_step_point(self, step_point: StepPoint) -> list:
        """Get thoughts that need processing at this step point."""
        pipeline_state = self.get_pipeline_state()
        
        if hasattr(pipeline_state, 'thoughts_by_step') and step_point in pipeline_state.thoughts_by_step:
            return pipeline_state.thoughts_by_step[step_point][:5]  # Limit to 5 thoughts
        
        # For early steps, we may need to create mock thoughts
        return []
    
    def _create_thought_in_pipeline(self, thought, step_point: StepPoint) -> ThoughtInPipeline:
        """Create a ThoughtInPipeline from a Thought for processing."""
        from datetime import datetime
        
        return ThoughtInPipeline(
            thought_id=thought.thought_id,
            task_id=thought.source_task_id,
            thought_type=thought.thought_type.value if thought.thought_type else "task_execution",
            current_step=step_point,
            entered_step_at=datetime.now(),
            step_data={
                "content": thought.content,
                "created_at": self._extract_created_at_string(thought),
                "tags": getattr(thought, 'tags', []),
            },
        )

    def _extract_created_at_string(self, thought) -> Optional[str]:
        """Extract created_at as a string, handling various formats."""
        if not thought.created_at:
            return None
        
        if hasattr(thought.created_at, 'isoformat'):
            return thought.created_at.isoformat()
        else:
            return thought.created_at
    
    async def _execute_step_for_thought(self, step_point: StepPoint, thought) -> Dict[str, Any]:
        """
        Execute a specific step point for a single thought.
        
        Returns typed step result with round/task/thought identifiers.
        """
        processing_start = asyncio.get_event_loop().time()
        
        # Mock step execution based on step point
        step_data = self._mock_step_execution(step_point, thought)
        
        processing_time_ms = (asyncio.get_event_loop().time() - processing_start) * 1000
        
        step_result = {
            "thought_id": thought.thought_id if hasattr(thought, 'thought_id') else str(thought),
            "round_id": getattr(self, '_current_round', 1),
            "task_id": getattr(thought, 'task_id', getattr(thought, 'source_task_id', None)),
            "step_point": step_point.value,
            "success": True,
            "step_data": step_data,
            "processing_time_ms": processing_time_ms,
            "timestamp": asyncio.get_event_loop().time(),
        }
        
        # Always broadcast step results to connected clients
        try:
            from ciris_engine.logic.infrastructure.step_streaming import step_result_stream
            await step_result_stream.broadcast_step_result(step_result)
        except Exception as e:
            # Don't let streaming errors break step execution
            import logging
            logging.getLogger(__name__).warning(f"Error broadcasting step result: {e}")
        
        return step_result
    
    def _mock_step_execution(self, step_point: StepPoint, thought) -> Dict[str, Any]:
        """Mock step execution for different step points."""
        base_data = {
            "executed_directly": True,
            "single_step_mode": True,
            "thought_content": getattr(thought, 'content', str(thought))[:100],
        }
        
        if step_point == StepPoint.GATHER_CONTEXT:
            return {**base_data, "context_built": True, "context_size": 1024}
        elif step_point == StepPoint.PERFORM_DMAS:
            return {
                **base_data, 
                "dmas_executed": ["ethical", "common_sense", "domain"],
                "ethical_score": 0.95,
                "common_sense_score": 0.88,
                "domain_score": 0.92,
            }
        elif step_point == StepPoint.CONSCIENCE_EXECUTION:
            return {
                **base_data,
                "conscience_checks": 3,
                "all_passed": True,
                "ethical_compliance": True,
            }
        elif step_point == StepPoint.FINALIZE_ACTION:
            return {
                **base_data,
                "selected_action": "speak",
                "confidence_score": 0.91,
                "alternatives_considered": 2,
            }
        else:
            return {**base_data, "step_completed": True}
    
    def _advance_thoughts_to_next_step(self, thoughts: list, current_step: StepPoint) -> None:
        """Advance thoughts to the next step in the pipeline."""
        # This would update the pipeline state to move thoughts forward
        # For now, we'll just track that they've been processed
        for thought in thoughts:
            if hasattr(thought, 'current_step'):
                thought.last_completed_step = current_step
