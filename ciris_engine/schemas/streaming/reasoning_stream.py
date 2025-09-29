"""
Typed schemas for H3ERE reasoning stream.

Designed for UI/UX team to easily display real-time pipeline visualization
with SVG updates and round-based thought tracking.

Uses existing StepResult schemas from runtime_control for consistency.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Field

from ciris_engine.schemas.services.runtime_control import (
    StepPoint,
    StepResultActionComplete,
    StepResultConscienceExecution,
    StepResultData,
    StepResultFinalizeAction,
    StepResultGatherContext,
    StepResultPerformAction,
    StepResultPerformASPDMA,
    StepResultPerformDMAs,
    StepResultRecursiveASPDMA,
    StepResultRecursiveConscience,
    StepResultRoundComplete,
    StepResultStartRound,
)

# Union of all possible StepResult types for type safety
StepResult = Union[
    StepResultStartRound,
    StepResultGatherContext,
    StepResultPerformDMAs,
    StepResultPerformASPDMA,
    StepResultConscienceExecution,
    StepResultRecursiveASPDMA,
    StepResultRecursiveConscience,
    StepResultFinalizeAction,
    StepResultPerformAction,
    StepResultActionComplete,
    StepResultRoundComplete,
]

STEP_RESULT_MAP = {
    StepPoint.START_ROUND: StepResultStartRound,
    StepPoint.GATHER_CONTEXT: StepResultGatherContext,
    StepPoint.PERFORM_DMAS: StepResultPerformDMAs,
    StepPoint.PERFORM_ASPDMA: StepResultPerformASPDMA,
    StepPoint.CONSCIENCE_EXECUTION: StepResultConscienceExecution,
    StepPoint.RECURSIVE_ASPDMA: StepResultRecursiveASPDMA,
    StepPoint.RECURSIVE_CONSCIENCE: StepResultRecursiveConscience,
    StepPoint.FINALIZE_ACTION: StepResultFinalizeAction,
    StepPoint.PERFORM_ACTION: StepResultPerformAction,
    StepPoint.ACTION_COMPLETE: StepResultActionComplete,
    StepPoint.ROUND_COMPLETE: StepResultRoundComplete,
}


class ThoughtStatus(str, Enum):
    """Current processing status of a thought."""

    QUEUED = "queued"  # Waiting to be processed
    PROCESSING = "processing"  # Currently being processed at a step
    COMPLETED = "completed"  # Successfully completed this step
    FAILED = "failed"  # Failed at this step
    BLOCKED = "blocked"  # Blocked waiting for dependency


class StepCategory(str, Enum):
    """Categories of steps for UI visualization."""

    PREPARATION = "preparation"  # Steps 1-3: Queue management
    ANALYSIS = "analysis"  # Steps 4-7: Context and DMA analysis
    DECISION = "decision"  # Steps 8-10: Action selection and routing
    EXECUTION = "execution"  # Steps 11-13: Delivery and processing
    COMPLETION = "completion"  # Final steps and cleanup


class StepMetadata(BaseModel):
    """UI metadata for a step point."""

    name: str = Field(..., description="Human-readable step name")
    description: str = Field(..., description="Step description for tooltips")
    category: StepCategory = Field(..., description="Step category for UI grouping")
    svg_position: Dict[str, float] = Field(..., description="X,Y coordinates for SVG visualization")


class ThoughtStreamData(BaseModel):
    """Individual thought's current state in the pipeline."""

    thought_id: str = Field(..., description="Unique thought identifier")
    task_id: str = Field(..., description="Parent task identifier")
    round_number: int = Field(..., description="Processing round number")

    # Current state
    current_step: StepPoint = Field(..., description="Current step point")
    step_category: StepCategory = Field(..., description="Step category for UI grouping")
    status: ThoughtStatus = Field(..., description="Current processing status")

    # Progress tracking
    steps_completed: List[StepPoint] = Field(default_factory=list, description="Steps already completed")
    steps_remaining: List[StepPoint] = Field(default_factory=list, description="Steps remaining")
    progress_percentage: float = Field(..., ge=0, le=100, description="Overall progress percentage")

    # Timing data
    started_at: datetime = Field(..., description="When processing started")
    current_step_started_at: datetime = Field(..., description="When current step started")
    processing_time_ms: float = Field(..., description="Time spent on current step")
    total_processing_time_ms: float = Field(..., description="Total processing time")
    estimated_completion_ms: Optional[float] = Field(None, description="Estimated time to completion")

    # Content preview for UI
    content_preview: str = Field(..., max_length=200, description="Truncated content for display")
    thought_type: str = Field(..., description="Type of thought (task_execution, reflection, etc.)")

    # Step-specific result data (uses existing StepResult schemas)
    step_result: Optional[StepResult] = Field(None, description="Current step execution result")
    last_error: Optional[str] = Field(None, description="Last error message if failed")


class StepPointSummary(BaseModel):
    """Summary of all thoughts at a specific step point."""

    step_point: StepPoint = Field(..., description="Step point identifier")
    step_category: StepCategory = Field(..., description="Step category for UI grouping")
    step_name: str = Field(..., description="Human-readable step name")
    step_description: str = Field(..., description="Step description for tooltips")

    # Counts by status
    total_thoughts: int = Field(..., ge=0, description="Total thoughts at this step")
    queued_count: int = Field(..., ge=0, description="Thoughts queued for this step")
    processing_count: int = Field(..., ge=0, description="Thoughts currently processing")
    completed_count: int = Field(..., ge=0, description="Thoughts completed this step")
    failed_count: int = Field(..., ge=0, description="Thoughts failed at this step")
    blocked_count: int = Field(..., ge=0, description="Thoughts blocked at this step")

    # Performance metrics
    average_processing_time_ms: float = Field(..., description="Average time to complete this step")
    throughput_per_minute: float = Field(..., description="Thoughts completed per minute")

    # UI positioning for SVG
    svg_position: Dict[str, float] = Field(default_factory=dict, description="X,Y coordinates for SVG visualization")


class RoundSummary(BaseModel):
    """Summary of all activity in a processing round."""

    round_number: int = Field(..., description="Round number")
    started_at: datetime = Field(..., description="When round started")

    # Task breakdown
    active_tasks: List[str] = Field(default_factory=list, description="Task IDs active in this round")
    task_count: int = Field(..., ge=0, description="Number of active tasks")

    # Thought breakdown
    total_thoughts: int = Field(..., ge=0, description="Total thoughts in this round")
    thoughts_by_status: Dict[ThoughtStatus, int] = Field(default_factory=dict, description="Thought counts by status")
    thoughts_by_step: Dict[StepPoint, int] = Field(default_factory=dict, description="Thought counts by step")

    # Round performance
    round_duration_ms: Optional[float] = Field(None, description="Total round duration if completed")
    thoughts_completed_this_round: int = Field(..., ge=0, description="Thoughts completed in this round")
    round_throughput: float = Field(..., description="Thoughts per second in this round")

    # Health indicators
    error_rate: float = Field(..., ge=0, le=100, description="Percentage of thoughts that failed")
    bottleneck_step: Optional[StepPoint] = Field(None, description="Step with most queued thoughts")


class ReasoningStreamUpdate(BaseModel):
    """Complete reasoning stream update for real-time UI updates."""

    # Stream metadata
    stream_sequence: int = Field(..., description="Sequential stream update number")
    timestamp: datetime = Field(..., description="When this update was generated")
    update_type: str = Field(..., description="Type of update (step_complete, new_round, error, etc.)")

    # Current pipeline state
    current_round: int = Field(..., description="Current processing round")
    total_rounds: int = Field(..., description="Total rounds processed")
    pipeline_active: bool = Field(..., description="Whether pipeline is actively processing")

    # Raw step results (uses existing StepResult schemas)
    step_results: List[StepResult] = Field(default_factory=list, description="Raw step results from pipeline")

    # Individual thoughts (only changed/new ones in this update)
    updated_thoughts: List[ThoughtStreamData] = Field(
        default_factory=list, description="Thoughts updated in this stream"
    )
    new_thoughts: List[ThoughtStreamData] = Field(default_factory=list, description="New thoughts added to pipeline")
    completed_thoughts: List[str] = Field(default_factory=list, description="Thought IDs that completed")
    failed_thoughts: List[str] = Field(default_factory=list, description="Thought IDs that failed")

    # Step summaries (all steps, for SVG visualization)
    step_summaries: List[StepPointSummary] = Field(default_factory=list, description="Current state of all 15 steps")

    # Round summaries (recent rounds)
    current_round_summary: Optional[RoundSummary] = Field(None, description="Summary of current round")
    recent_rounds: List[RoundSummary] = Field(default_factory=list, description="Last 5 completed rounds")

    # Performance metrics
    overall_throughput: float = Field(0.0, description="Overall thoughts per second")
    pipeline_health_score: float = Field(100.0, ge=0, le=100, description="Overall pipeline health percentage")
    bottlenecks: List[StepPoint] = Field(default_factory=list, description="Current bottleneck steps")

    # UI hints
    svg_updates_required: List[str] = Field(default_factory=list, description="SVG elements that need updating")
    notification_messages: List[str] = Field(default_factory=list, description="User-facing status messages")


def _create_typed_step_result(raw_result: StepResultData, step_point: StepPoint):
    """Create typed step result from raw data with intelligent field mapping for rich analysis."""
    import logging

    logger = logging.getLogger(__name__)

    step_result_model = STEP_RESULT_MAP.get(step_point)
    if not step_result_model or not raw_result:
        return None

    try:
        combined_data = {
            "step_point": step_point,
            "success": raw_result.success,
            "timestamp": datetime.now().isoformat(),
            "thought_id": raw_result.thought_id,
            "task_id": raw_result.task_id,
            "processing_time_ms": raw_result.processing_time_ms,
            "error": getattr(raw_result, "error", None) if not raw_result.success else None,
            **raw_result.step_data.model_dump(),
        }

        # Intelligent field mapping for rich debugging and analysis
        if step_point == StepPoint.GATHER_CONTEXT:
            # Transform context data for StepResultGatherContext
            context_data = getattr(raw_result.step_data, "context", "")
            if "summary" not in combined_data and context_data:
                combined_data["summary"] = context_data[:200] + "..." if len(context_data) > 200 else context_data
            if "context_size" not in combined_data:
                # Calculate meaningful context size (word count, item count, etc.)
                combined_data["context_size"] = len(context_data.split()) if context_data else 0

        elif step_point == StepPoint.PERFORM_DMAS:
            # Enrich DMA results with analysis metadata
            dma_results = getattr(raw_result.step_data, "dma_results", "")
            if "result_count" not in combined_data and dma_results:
                # Count decision points, approvals, rejections for debugging
                combined_data["result_count"] = len(
                    [r for r in dma_results.split() if r in ["approve", "reject", "defer"]]
                )

        elif step_point == StepPoint.CONSCIENCE_EXECUTION:
            # Enhance conscience data with debugging metadata
            if hasattr(raw_result.step_data, "conscience_result"):
                conscience_result = raw_result.step_data.conscience_result
                if hasattr(conscience_result, "severity"):
                    combined_data["severity_level"] = conscience_result.severity
                if hasattr(conscience_result, "details") and isinstance(conscience_result.details, dict):
                    combined_data["details_count"] = len(conscience_result.details)

        return step_result_model(**combined_data)
    except Exception as e:
        logger.warning(
            f"Could not create typed step result for {step_point.value}: {e}. " f"Raw data: {raw_result.step_data}"
        )
        return None


def _create_thought_stream_data(raw_result: StepResultData) -> ThoughtStreamData:
    """Create ThoughtStreamData from raw result."""
    import logging

    logger = logging.getLogger(__name__)

    logger.debug(
        f"Stream update for step {raw_result.step_point}: task_id={raw_result.task_id}, thought_id={raw_result.thought_id}"
    )

    step_point = StepPoint(raw_result.step_point)
    # step_data is already typed in StepResultData
    typed_step_result = _create_typed_step_result(raw_result, step_point)

    return ThoughtStreamData(
        thought_id=raw_result.thought_id,
        task_id=raw_result.task_id,
        round_number=1,  # Default since round_id not in StepResultData
        current_step=step_point,
        step_category=get_step_metadata(step_point).category,
        status=ThoughtStatus.PROCESSING if raw_result.success else ThoughtStatus.FAILED,
        steps_completed=[],
        steps_remaining=get_remaining_steps(step_point),
        progress_percentage=calculate_progress_percentage([], step_point),
        started_at=datetime.now(),
        current_step_started_at=datetime.now(),
        processing_time_ms=raw_result.processing_time_ms,
        total_processing_time_ms=raw_result.processing_time_ms,
        content_preview=str(getattr(raw_result.step_data, "thought_content", ""))[:200],
        thought_type=getattr(raw_result.step_data, "thought_type", "task_execution"),
        step_result=typed_step_result,
        last_error=getattr(raw_result, "error", None) if not raw_result.success else None,
    )


def _create_step_summary(step_point: StepPoint, step_results: List[StepResultData]) -> StepPointSummary:
    """Create step summary for a specific step point."""
    metadata = get_step_metadata(step_point)
    step_results_for_point = [r for r in step_results if r.step_point == step_point.value]

    return StepPointSummary(
        step_point=step_point,
        step_category=metadata.category,
        step_name=metadata.name,
        step_description=metadata.description,
        total_thoughts=len(step_results_for_point),
        queued_count=0,
        processing_count=len([r for r in step_results_for_point if r.success]),
        completed_count=len([r for r in step_results_for_point if r.success]),
        failed_count=len([r for r in step_results_for_point if not r.success]),
        blocked_count=0,
        average_processing_time_ms=sum(r.processing_time_ms for r in step_results_for_point)
        / max(len(step_results_for_point), 1),
        throughput_per_minute=0.0,
        svg_position=metadata.svg_position,
    )


def create_stream_update_from_step_results(
    step_results: List[StepResultData], stream_sequence: int
) -> ReasoningStreamUpdate:
    """
    Create a ReasoningStreamUpdate from raw pipeline step results.

    This function converts the raw step result dictionaries into typed
    UI-friendly stream updates for the reasoning visualization.

    Args:
        step_results: Raw step results from pipeline execution
        stream_sequence: Sequential stream update number

    Returns:
        Typed stream update for UI consumption
    """
    # Convert raw results to ThoughtStreamData
    updated_thoughts = [_create_thought_stream_data(raw_result) for raw_result in step_results]

    # Create step summaries for all 15 steps
    step_summaries = [_create_step_summary(step_point, step_results) for step_point in StepPoint]

    return ReasoningStreamUpdate(
        stream_sequence=stream_sequence,
        timestamp=datetime.now(),
        update_type="step_complete",
        current_round=1,  # Default since round_id not in StepResultData
        total_rounds=1,  # Default since round_id not in StepResultData
        pipeline_active=True,
        step_results=[],  # TODO: Convert to typed StepResults
        updated_thoughts=updated_thoughts,
        new_thoughts=[],
        completed_thoughts=[],
        failed_thoughts=[],
        step_summaries=step_summaries,
        current_round_summary=None,
        recent_rounds=[],
        overall_throughput=0.0,
        pipeline_health_score=100.0,
        bottlenecks=[],
        svg_updates_required=[],
        notification_messages=[],
    )


# Step metadata for UI display
STEP_METADATA = {
    StepPoint.START_ROUND: StepMetadata(
        name="Start Round",
        description="Initialize processing round",
        category=StepCategory.PREPARATION,
        svg_position={"x": 50, "y": 100},
    ),
    StepPoint.GATHER_CONTEXT: StepMetadata(
        name="Gather Context",
        description="Building comprehensive context for analysis",
        category=StepCategory.ANALYSIS,
        svg_position={"x": 150, "y": 100},
    ),
    StepPoint.PERFORM_DMAS: StepMetadata(
        name="Perform DMAs",
        description="Multi-perspective decision-making analysis",
        category=StepCategory.ANALYSIS,
        svg_position={"x": 250, "y": 100},
    ),
    StepPoint.PERFORM_ASPDMA: StepMetadata(
        name="Perform ASPDMA",
        description="LLM-powered action selection",
        category=StepCategory.ANALYSIS,
        svg_position={"x": 350, "y": 100},
    ),
    StepPoint.CONSCIENCE_EXECUTION: StepMetadata(
        name="Conscience Execution",
        description="Ethical safety and alignment checks",
        category=StepCategory.ANALYSIS,
        svg_position={"x": 450, "y": 100},
    ),
    StepPoint.RECURSIVE_ASPDMA: StepMetadata(
        name="Recursive ASPDMA",
        description="Optional re-analysis if conscience failed",
        category=StepCategory.ANALYSIS,
        svg_position={"x": 250, "y": 200},
    ),
    StepPoint.RECURSIVE_CONSCIENCE: StepMetadata(
        name="Recursive Conscience",
        description="Optional re-check if conscience failed",
        category=StepCategory.ANALYSIS,
        svg_position={"x": 350, "y": 200},
    ),
    StepPoint.FINALIZE_ACTION: StepMetadata(
        name="Finalize Action",
        description="Final action determination and validation",
        category=StepCategory.DECISION,
        svg_position={"x": 50, "y": 300},
    ),
    StepPoint.PERFORM_ACTION: StepMetadata(
        name="Perform Action",
        description="Execute the selected action",
        category=StepCategory.EXECUTION,
        svg_position={"x": 150, "y": 300},
    ),
    StepPoint.ACTION_COMPLETE: StepMetadata(
        name="Action Complete",
        description="Action execution completed",
        category=StepCategory.COMPLETION,
        svg_position={"x": 250, "y": 300},
    ),
    StepPoint.ROUND_COMPLETE: StepMetadata(
        name="Round Complete",
        description="Finalizing round and updating metrics",
        category=StepCategory.COMPLETION,
        svg_position={"x": 350, "y": 300},
    ),
}


def get_step_metadata(step_point: StepPoint) -> StepMetadata:
    """Get UI metadata for a step point."""
    return STEP_METADATA.get(
        step_point,
        StepMetadata(
            name=step_point.value.replace("_", " ").title(),
            description=f"Processing {step_point.value}",
            category=StepCategory.EXECUTION,
            svg_position={"x": 0, "y": 0},
        ),
    )


def calculate_progress_percentage(completed_steps: List[StepPoint], current_step: StepPoint) -> float:
    """Calculate progress percentage for a thought."""
    all_steps = list(StepPoint)
    if current_step in all_steps:
        current_index = all_steps.index(current_step)
        return (current_index / len(all_steps)) * 100
    return 0.0


def get_remaining_steps(current_step: StepPoint) -> List[StepPoint]:
    """Get remaining steps after current step."""
    all_steps = list(StepPoint)
    if current_step in all_steps:
        current_index = all_steps.index(current_step)
        return all_steps[current_index + 1 :]
    return all_steps
