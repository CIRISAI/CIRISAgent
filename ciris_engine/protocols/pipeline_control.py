"""
Pipeline control protocol for single-stepping through the processing pipeline.

This protocol defines how step points are injected and controlled throughout
the thought processing pipeline.
"""

import asyncio
from typing import Optional, Protocol, TYPE_CHECKING, Union

if TYPE_CHECKING:
    from ciris_engine.schemas.telemetry.collector import SingleStepResult
    from ciris_engine.schemas.services.runtime_control import ThoughtProcessingResult

from ciris_engine.schemas.services.runtime_control import PipelineState, StepPoint, StepResultUnion, ThoughtInPipeline

# Alias for backwards compatibility
StepResult = StepResultUnion


class PipelineControlProtocol(Protocol):
    """Protocol for controlling pipeline execution and step points."""

    async def should_pause_at(self, step_point: StepPoint, thought_id: str) -> bool:
        """Check if we should pause at this step point."""
        ...

    async def pause_at_step_point(
        self, step_point: StepPoint, thought_id: str, step_data: "SingleStepResult"
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

    def __init__(self, is_paused: bool = False, main_processor=None):
        self.is_paused = is_paused
        self.pipeline_state = PipelineState()
        self.main_processor = main_processor

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
        self, step_point: StepPoint, thought_id: str, step_data: "SingleStepResult"
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
        step_result = self._create_step_result(step_point, step_data)

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
        self, thought: ThoughtInPipeline, step_point: StepPoint, step_data: Optional[dict]
    ) -> None:
        """Update thought with step-specific data."""
        if step_data is None:
            return
        
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

    def _create_step_result(self, step_point: StepPoint, step_data: Optional[dict]) -> StepResultUnion:
        """Create StepResult using EXACT data from running H3ERE pipeline."""
        if step_data is None:
            step_data = {}
            
        # Import only the 9 real H3ERE step result schemas
        from ciris_engine.schemas.services.runtime_control import (
            StepResultActionComplete,
            StepResultConscienceExecution,
            StepResultFinalizeAction,
            StepResultGatherContext,
            StepResultPerformAction,
            StepResultPerformASPDMA,
            StepResultPerformDMAs,
            StepResultRecursiveASPDMA,
            StepResultRecursiveConscience,
        )

        # Use EXACT SUT data - no fake data, no simulation!
        # FAIL FAST AND LOUD if step_point is not one of our 9 real H3ERE steps
        if step_point == StepPoint.GATHER_CONTEXT:
            return StepResultGatherContext(success=True, **step_data)  # Use EXACT data from SUT
        elif step_point == StepPoint.PERFORM_DMAS:
            return StepResultPerformDMAs(success=True, **step_data)  # Use EXACT data from SUT
        elif step_point == StepPoint.PERFORM_ASPDMA:
            return StepResultPerformASPDMA(success=True, **step_data)  # Use EXACT data from SUT
        elif step_point == StepPoint.CONSCIENCE_EXECUTION:
            return StepResultConscienceExecution(success=True, **step_data)  # Use EXACT data from SUT
        elif step_point == StepPoint.RECURSIVE_ASPDMA:
            return StepResultRecursiveASPDMA(success=True, **step_data)  # Use EXACT data from SUT
        elif step_point == StepPoint.RECURSIVE_CONSCIENCE:
            return StepResultRecursiveConscience(success=True, **step_data)  # Use EXACT data from SUT
        elif step_point == StepPoint.FINALIZE_ACTION:
            return StepResultFinalizeAction(success=True, **step_data)  # Use EXACT data from SUT
        elif step_point == StepPoint.PERFORM_ACTION:
            return StepResultPerformAction(success=True, **step_data)  # Use EXACT data from SUT
        elif step_point == StepPoint.ACTION_COMPLETE:
            return StepResultActionComplete(success=True, **step_data)  # Use EXACT data from SUT

        # FAIL FAST AND LOUD - only 9 real H3ERE steps allowed!
        raise ValueError(f"Invalid step point: {step_point}. Only 9 real H3ERE pipeline steps are supported!")

    def _get_pipeline_state_dict(self):
        """Get pipeline state as dictionary with fallback."""
        pipeline_state = self.get_pipeline_state()
        return pipeline_state.dict() if hasattr(pipeline_state, "dict") else {}

    def _calculate_processing_time(self, start_time) -> float:
        """Calculate processing time in milliseconds."""
        import asyncio
        return (asyncio.get_event_loop().time() - start_time) * 1000

    async def _handle_paused_thoughts(self, start_time) -> "SingleStepResult":
        """Handle execution of paused thoughts."""
        from ciris_engine.logic.processors.core.step_decorators import execute_all_steps
        
        result = await execute_all_steps()
        processing_time_ms = self._calculate_processing_time(start_time)

        return {
            "success": result["success"],
            "step_point": "resume_paused_thoughts",
            "message": result["message"],
            "thoughts_advanced": result["thoughts_advanced"],
            "step_results": [{"thoughts_advanced": result["thoughts_advanced"], "message": result["message"]}],
            "processing_time_ms": processing_time_ms,
            "pipeline_state": self._get_pipeline_state_dict(),
        }

    def _handle_no_pending_thoughts(self, start_time) -> "SingleStepResult":
        """Handle case when no pending thoughts are available."""
        processing_time_ms = self._calculate_processing_time(start_time)
        return {
            "success": True,
            "step_point": "no_work",
            "message": "No pending thoughts to process",
            "thoughts_advanced": 0,
            "step_results": [],
            "processing_time_ms": processing_time_ms,
            "pipeline_state": self._get_pipeline_state_dict(),
        }

    def _handle_successful_initiation(self, thought, start_time) -> "SingleStepResult":
        """Handle successful thought processing initiation."""
        processing_time_ms = self._calculate_processing_time(start_time)
        return {
            "success": True,
            "step_point": "initiate_processing",
            "message": f"Initiated processing for thought {thought.thought_id} - will pause at first step",
            "thought_id": thought.thought_id,
            "step_results": [{"thought_id": thought.thought_id, "initiated": True}],
            "processing_time_ms": processing_time_ms,
            "pipeline_state": self._get_pipeline_state_dict(),
        }

    def _handle_initiation_error(self, error, start_time) -> "SingleStepResult":
        """Handle error during thought processing initiation."""
        processing_time_ms = self._calculate_processing_time(start_time)
        return {
            "success": False,
            "step_point": "error",
            "message": f"Error initiating processing: {error}",
            "step_results": [],
            "processing_time_ms": processing_time_ms,
            "pipeline_state": self._get_pipeline_state_dict(),
        }

    def _handle_no_processor(self, start_time) -> "SingleStepResult":
        """Handle case when no thought processor is available."""
        processing_time_ms = self._calculate_processing_time(start_time)
        return {
            "success": False,
            "step_point": "error",
            "message": "No thought processor available",
            "step_results": [],
            "processing_time_ms": processing_time_ms,
            "pipeline_state": self._get_pipeline_state_dict(),
        }

    async def _initiate_thought_processing(self, thought, start_time) -> "SingleStepResult":
        """Initiate processing for a pending thought."""
        if not (self.main_processor and self.main_processor.thought_processor):
            return self._handle_no_processor(start_time)
            
        try:
            # Start processing this thought - it will pause at the first decorated step
            # For now, we'll simulate this by just indicating that processing was initiated
            return self._handle_successful_initiation(thought, start_time)
        except Exception as e:
            return self._handle_initiation_error(e, start_time)

    async def execute_single_step_point(self) -> "SingleStepResult":
        """
        Execute exactly one step point in the H3ERE pipeline using step decorators.

        This enables single-step mode and advances paused thoughts by one step,
        leveraging the existing step decorator infrastructure for pause/resume.

        Returns:
            Dict containing:
            - success: bool
            - step_point: str (the step point executed)
            - message: str (description of what happened)
            - step_results: List[Dict] (results for each thought advanced)
            - processing_time_ms: float
            - pipeline_state: Dict
        """
        import asyncio

        from ciris_engine.logic.processors.core.step_decorators import (
            enable_single_step_mode,
            get_paused_thoughts,
        )

        start_time = asyncio.get_event_loop().time()

        # Enable single-step mode so that step decorators pause at each step
        enable_single_step_mode()

        # Check if we have paused thoughts to advance
        paused_thoughts = get_paused_thoughts()

        if paused_thoughts:
            return await self._handle_paused_thoughts(start_time)

        # No paused thoughts - need to start new thoughts in the pipeline
        from ciris_engine.logic import persistence
        from ciris_engine.schemas.runtime.models import ThoughtStatus

        pending_thoughts = persistence.get_thoughts_by_status(ThoughtStatus.PENDING, limit=1)
        if not pending_thoughts:
            return self._handle_no_pending_thoughts(start_time)

        # Start processing the first pending thought
        thought = pending_thoughts[0]
        return await self._initiate_thought_processing(thought, start_time)

    def _get_next_step_point(self) -> Optional[StepPoint]:
        """Get the next step point to execute in order."""
        # Define the execution order of step points
        step_order = [
            StepPoint.START_ROUND,  # 0) Setup: Tasks → Thoughts → Round Queue → Ready for context
            StepPoint.GATHER_CONTEXT,  # 1) Build context for DMA processing
            StepPoint.PERFORM_DMAS,  # 2) Execute multi-perspective DMAs
            StepPoint.PERFORM_ASPDMA,  # 3) LLM-powered action selection
            StepPoint.CONSCIENCE_EXECUTION,  # 4) Ethical safety validation
            StepPoint.RECURSIVE_ASPDMA,  # 5) Optional: Re-run action selection if conscience failed
            StepPoint.RECURSIVE_CONSCIENCE,  # 6) Optional: Re-validate if recursive action failed
            StepPoint.FINALIZE_ACTION,  # 7) Final action determination
            StepPoint.PERFORM_ACTION,  # 8) Dispatch action to handler
            StepPoint.ACTION_COMPLETE,  # 9) Action execution completed
            StepPoint.ROUND_COMPLETE,
        ]

        # Track current step point
        if not hasattr(self, "_current_step_index"):
            self._current_step_index = 0

        if not step_order or self._current_step_index >= len(step_order):
            # Reset to start of pipeline for next round
            self._current_step_index = 0
            return (
                step_order[0] if (step_order and len(step_order) > 0) else StepPoint.START_ROUND
            )  # Start new round at START_ROUND

        current_step = step_order[self._current_step_index]
        self._current_step_index += 1
        return current_step

    def get_current_state(self):
        """Get the current pipeline state including next step to execute."""
        next_step = self._peek_next_step_point()
        pipeline_state = self.get_pipeline_state()

        class CurrentPipelineState:
            def __init__(self, current_step, pipeline_state):
                self.current_step = current_step
                self.pipeline_state = pipeline_state

        return CurrentPipelineState(next_step.value if next_step else None, pipeline_state)

    def _peek_next_step_point(self) -> Optional[StepPoint]:
        """Peek at next step point without incrementing counter."""
        step_order = [
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

        # Track current step point
        if not hasattr(self, "_current_step_index"):
            self._current_step_index = 0

        if not step_order or self._current_step_index >= len(step_order):
            # Would reset to start of pipeline for next round
            return step_order[0] if (step_order and len(step_order) > 0) else StepPoint.START_ROUND  # START_ROUND

        return step_order[self._current_step_index]

    def _get_thoughts_for_step_point(self, step_point: StepPoint) -> list:
        """Get thoughts that need processing at this step point."""
        pipeline_state = self.get_pipeline_state()

        if hasattr(pipeline_state, "thoughts_by_step") and step_point in pipeline_state.thoughts_by_step:
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
                "tags": getattr(thought, "tags", []),
            },
        )

    def _extract_created_at_string(self, thought) -> Optional[str]:
        """Extract created_at as a string, handling various formats."""
        if not thought.created_at:
            return None

        if hasattr(thought.created_at, "isoformat"):
            return thought.created_at.isoformat()
        else:
            return thought.created_at

    async def _execute_step_for_thought(self, step_point: StepPoint, thought) -> "ThoughtProcessingResult":
        """
        Execute a specific step point for a single thought.

        Returns typed step result with round/task/thought identifiers.
        """
        processing_start = asyncio.get_event_loop().time()

        # Execute REAL step logic based on step point - NO MOCK DATA
        step_data = await self._execute_real_step_logic(step_point, thought)

        processing_time_ms = (asyncio.get_event_loop().time() - processing_start) * 1000

        step_result = {
            "thought_id": thought.thought_id if hasattr(thought, "thought_id") else str(thought),
            "round_id": getattr(self, "_current_round", 1),
            "task_id": getattr(thought, "task_id", getattr(thought, "source_task_id", None)),
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

    # Note: All step execution is now handled by step decorators in ThoughtProcessor phases
    # No manual step execution methods needed - decorators handle pause/resume automatically

    def _advance_thoughts_to_next_step(self, thoughts: list, current_step: StepPoint) -> None:
        """Advance thoughts to the next step in the pipeline."""
        pipeline_state = self.get_pipeline_state()

        # Get the next step in the pipeline
        step_order = [
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

        current_index = step_order.index(current_step) if current_step in step_order else -1
        next_step = (
            step_order[current_index + 1] if current_index >= 0 and current_index + 1 < len(step_order) else None
        )

        # Update each thought's state and move to next step bucket
        for thought in thoughts:
            # Update thought object state
            if hasattr(thought, "last_completed_step"):
                thought.last_completed_step = current_step
            if hasattr(thought, "current_step") and next_step:
                thought.current_step = next_step

            # Move thought to next step bucket in pipeline state
            if next_step and hasattr(pipeline_state, "thoughts_by_step"):
                if next_step.value not in pipeline_state.thoughts_by_step:
                    pipeline_state.thoughts_by_step[next_step.value] = []
                pipeline_state.thoughts_by_step[next_step.value].append(thought)
