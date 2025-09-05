"""
Pipeline control protocol for single-stepping through the processing pipeline.

This protocol defines how step points are injected and controlled throughout
the thought processing pipeline.
"""

import asyncio
from typing import Any, Dict, Optional, Protocol

from ciris_engine.schemas.services.runtime_control import PipelineState, StepPoint, StepResult, ThoughtInPipeline


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

        # Step point control
        self._enabled_step_points = set(StepPoint)  # All enabled by default
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
        return step_point in [StepPoint.POPULATE_ROUND, StepPoint.ACTION_SELECTION]

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
        if step_point == StepPoint.BUILD_CONTEXT:
            thought.context_built = step_data.get("context")
        elif step_point == StepPoint.PERFORM_DMAS:
            thought.dma_results = step_data.get("dma_results")
        elif step_point == StepPoint.PERFORM_ASPDMA:
            thought.aspdma_result = step_data.get("aspdma_result")
        elif step_point == StepPoint.CONSCIENCE_EXECUTION:
            thought.conscience_results = step_data.get("conscience_results")
        elif step_point == StepPoint.ACTION_SELECTION:
            thought.selected_action = step_data.get("selected_action")
        elif step_point == StepPoint.HANDLER_COMPLETE:
            thought.handler_result = step_data.get("handler_result")
            thought.bus_operations = step_data.get("bus_operations")

    def _create_step_result(self, step_point: StepPoint, thought_id: str, step_data: Dict[str, Any]) -> StepResult:
        """Create appropriate StepResult based on step point."""
        # Import here to avoid circular dependency
        from ciris_engine.schemas.services.runtime_control import (
            StepResultActionSelection,
            StepResultBuildContext,
            StepResultBusInbound,
            StepResultBusOutbound,
            StepResultConscienceExecution,
            StepResultFinalizeTasksQueue,
            StepResultHandlerComplete,
            StepResultHandlerStart,
            StepResultPackageHandling,
            StepResultPerformASPDMA,
            StepResultPerformDMAs,
            StepResultPopulateRound,
            StepResultPopulateThoughtQueue,
            StepResultRecursiveASPDMA,
            StepResultRecursiveConscience,
        )

        # Create appropriate result based on step point with proper typed objects
        current_time = step_data.get("processing_time_ms", 0.0)
        round_number = step_data.get("round_number", 1)
        
        if step_point == StepPoint.FINALIZE_TASKS_QUEUE:
            return StepResultFinalizeTasksQueue(
                success=True,
                round_number=round_number,
                active_tasks=step_data.get("active_tasks", []),
                finalized_tasks=step_data.get("finalized_tasks", []),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.POPULATE_THOUGHT_QUEUE:
            return StepResultPopulateThoughtQueue(
                success=True,
                round_number=round_number,
                tasks_processed=step_data.get("tasks_processed", []),
                thoughts_generated=step_data.get("thoughts_generated", []),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.POPULATE_ROUND:
            return StepResultPopulateRound(
                success=True,
                round_number=round_number,
                available_thoughts=step_data.get("available_thoughts", []),
                selected_thoughts=step_data.get("selected_thoughts", []),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.BUILD_CONTEXT:
            return StepResultBuildContext(
                success=True,
                thought_id=thought_id,
                system_snapshot=step_data.get("system_snapshot", {}),
                agent_identity=step_data.get("agent_identity", {}),
                thought_context=step_data.get("context", {}),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.PERFORM_DMAS:
            return StepResultPerformDMAs(
                success=True,
                thought_id=thought_id,
                ethical_dma_result=step_data.get("ethical_dma_result"),
                common_sense_dma_result=step_data.get("common_sense_dma_result"),
                domain_dma_result=step_data.get("domain_dma_result"),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.PERFORM_ASPDMA:
            return StepResultPerformASPDMA(
                success=True,
                thought_id=thought_id,
                aspdma_result=step_data.get("aspdma_result"),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.CONSCIENCE_EXECUTION:
            return StepResultConscienceExecution(
                success=True,
                thought_id=thought_id,
                conscience_results=step_data.get("conscience_results", []),
                passed=step_data.get("conscience_passed", True),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.RECURSIVE_ASPDMA:
            return StepResultRecursiveASPDMA(
                success=True,
                thought_id=thought_id,
                retry_reason=step_data.get("retry_reason", ""),
                recursive_aspdma_result=step_data.get("recursive_aspdma_result"),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.RECURSIVE_CONSCIENCE:
            return StepResultRecursiveConscience(
                success=True,
                thought_id=thought_id,
                recursive_conscience_results=step_data.get("recursive_conscience_results", []),
                final_pass=step_data.get("final_conscience_pass", True),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.ACTION_SELECTION:
            return StepResultActionSelection(
                success=True,
                thought_id=thought_id,
                selected_action=step_data.get("selected_action"),
                selection_reasoning=step_data.get("selection_reasoning", ""),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.HANDLER_START:
            return StepResultHandlerStart(
                success=True,
                thought_id=thought_id,
                handler_name=step_data.get("handler_name", ""),
                action_parameters=step_data.get("action_parameters", {}),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.BUS_OUTBOUND:
            return StepResultBusOutbound(
                success=True,
                thought_id=thought_id,
                outbound_messages=step_data.get("outbound_messages", []),
                bus_operations=step_data.get("bus_operations", []),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.PACKAGE_HANDLING:
            return StepResultPackageHandling(
                success=True,
                thought_id=thought_id,
                adapter_name=step_data.get("adapter_name", ""),
                package_type=step_data.get("package_type", ""),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.BUS_INBOUND:
            return StepResultBusInbound(
                success=True,
                thought_id=thought_id,
                inbound_messages=step_data.get("inbound_messages", []),
                bus_responses=step_data.get("bus_responses", []),
                processing_time_ms=current_time,
            )
        elif step_point == StepPoint.HANDLER_COMPLETE:
            return StepResultHandlerComplete(
                success=True,
                thought_id=thought_id,
                handler_result=step_data.get("handler_result"),
                final_output=step_data.get("final_output"),
                processing_time_ms=current_time,
            )
        
        # Should never reach here with valid step points, but provide fallback
        raise ValueError(f"Unknown step point: {step_point}")
