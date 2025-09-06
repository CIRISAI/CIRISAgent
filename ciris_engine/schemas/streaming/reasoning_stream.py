"""
Typed schemas for H3ERE reasoning stream.

Designed for UI/UX team to easily display real-time pipeline visualization
with SVG updates and round-based thought tracking.

Uses existing StepResult schemas from runtime_control for consistency.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from enum import Enum
from pydantic import BaseModel, Field

from ciris_engine.schemas.services.runtime_control import (
    StepPoint,
    StepResultFinalizeTasksQueue,
    StepResultPopulateThoughtQueue,
    StepResultPopulateRound,
    StepResultGatherContext,
    StepResultPerformDMAs,
    StepResultPerformASPDMA,
    StepResultConscienceExecution,
    StepResultRecursiveASPDMA,
    StepResultRecursiveConscienceExecution,
    StepResultFinalizeAction,
    StepResultMultiServiceBus,
    StepResultDeliveryPayload,
    StepResultExecution,
    StepResultFollowUpThought,
    StepResultRoundComplete,
)

# Union of all possible StepResult types for type safety
StepResult = Union[
    StepResultFinalizeTasksQueue,
    StepResultPopulateThoughtQueue, 
    StepResultPopulateRound,
    StepResultGatherContext,
    StepResultPerformDMAs,
    StepResultPerformASPDMA,
    StepResultConscienceExecution,
    StepResultRecursiveASPDMA,
    StepResultRecursiveConscienceExecution,
    StepResultFinalizeAction,
    StepResultMultiServiceBus,
    StepResultDeliveryPayload,
    StepResultExecution,
    StepResultFollowUpThought,
    StepResultRoundComplete,
]


class ThoughtStatus(str, Enum):
    """Current processing status of a thought."""
    QUEUED = "queued"           # Waiting to be processed
    PROCESSING = "processing"   # Currently being processed at a step
    COMPLETED = "completed"     # Successfully completed this step
    FAILED = "failed"          # Failed at this step
    BLOCKED = "blocked"        # Blocked waiting for dependency


class StepCategory(str, Enum):
    """Categories of steps for UI visualization."""
    PREPARATION = "preparation"     # Steps 1-3: Queue management
    ANALYSIS = "analysis"          # Steps 4-7: Context and DMA analysis
    DECISION = "decision"          # Steps 8-10: Action selection and routing
    EXECUTION = "execution"        # Steps 11-13: Delivery and processing
    COMPLETION = "completion"      # Final steps and cleanup


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
    updated_thoughts: List[ThoughtStreamData] = Field(default_factory=list, description="Thoughts updated in this stream")
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


def create_stream_update_from_step_results(
    step_results: List[Dict[str, Any]], 
    stream_sequence: int
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
    updated_thoughts = []
    for raw_result in step_results:
        thought_data = ThoughtStreamData(
            thought_id=raw_result.get("thought_id", ""),
            task_id=raw_result.get("task_id", ""),
            round_number=raw_result.get("round_id", 1),
            current_step=StepPoint(raw_result.get("step_point", StepPoint.FINALIZE_TASKS_QUEUE)),
            step_category=get_step_metadata(StepPoint(raw_result.get("step_point", StepPoint.FINALIZE_TASKS_QUEUE)))["category"],
            status=ThoughtStatus.PROCESSING if raw_result.get("success", True) else ThoughtStatus.FAILED,
            steps_completed=[],
            steps_remaining=get_remaining_steps(StepPoint(raw_result.get("step_point", StepPoint.FINALIZE_TASKS_QUEUE))),
            progress_percentage=calculate_progress_percentage([], StepPoint(raw_result.get("step_point", StepPoint.FINALIZE_TASKS_QUEUE))),
            started_at=datetime.now(),
            current_step_started_at=datetime.now(),
            processing_time_ms=raw_result.get("processing_time_ms", 0.0),
            total_processing_time_ms=raw_result.get("processing_time_ms", 0.0),
            content_preview=str(raw_result.get("step_data", {}).get("thought_content", ""))[:200],
            thought_type=raw_result.get("step_data", {}).get("thought_type", "task_execution"),
            step_result=None,  # TODO: Convert raw step_data to typed StepResult
            last_error=raw_result.get("error") if not raw_result.get("success", True) else None,
        )
        updated_thoughts.append(thought_data)
    
    # Create step summaries for all 15 steps
    step_summaries = []
    for step_point in StepPoint:
        metadata = get_step_metadata(step_point)
        step_results_for_point = [r for r in step_results if r.get("step_point") == step_point.value]
        
        summary = StepPointSummary(
            step_point=step_point,
            step_category=metadata["category"],
            step_name=metadata["name"],
            step_description=metadata["description"],
            total_thoughts=len(step_results_for_point),
            queued_count=0,
            processing_count=len([r for r in step_results_for_point if r.get("success", True)]),
            completed_count=len([r for r in step_results_for_point if r.get("success", True)]),
            failed_count=len([r for r in step_results_for_point if not r.get("success", True)]),
            blocked_count=0,
            average_processing_time_ms=sum(r.get("processing_time_ms", 0) for r in step_results_for_point) / max(len(step_results_for_point), 1),
            throughput_per_minute=0.0,
            svg_position=metadata["svg_position"],
        )
        step_summaries.append(summary)
    
    return ReasoningStreamUpdate(
        stream_sequence=stream_sequence,
        timestamp=datetime.now(),
        update_type="step_complete",
        current_round=max([r.get("round_id", 1) for r in step_results], default=1),
        total_rounds=max([r.get("round_id", 1) for r in step_results], default=1),
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
    StepPoint.FINALIZE_TASKS_QUEUE: {
        "name": "Finalize Tasks Queue",
        "description": "Organizing and prioritizing pending tasks",
        "category": StepCategory.PREPARATION,
        "svg_position": {"x": 50, "y": 100}
    },
    StepPoint.POPULATE_THOUGHT_QUEUE: {
        "name": "Populate Thought Queue", 
        "description": "Creating thoughts for task execution",
        "category": StepCategory.PREPARATION,
        "svg_position": {"x": 150, "y": 100}
    },
    StepPoint.POPULATE_ROUND: {
        "name": "Populate Round",
        "description": "Setting up processing round context",
        "category": StepCategory.PREPARATION,
        "svg_position": {"x": 250, "y": 100}
    },
    StepPoint.GATHER_CONTEXT: {
        "name": "Gather Context",
        "description": "Building comprehensive context for analysis",
        "category": StepCategory.ANALYSIS,
        "svg_position": {"x": 50, "y": 200}
    },
    StepPoint.PERFORM_DMAS: {
        "name": "Perform DMAs",
        "description": "Multi-perspective decision-making analysis",
        "category": StepCategory.ANALYSIS,
        "svg_position": {"x": 150, "y": 200}
    },
    StepPoint.PERFORM_ASPDMA: {
        "name": "Perform ASPDMA",
        "description": "LLM-powered action selection",
        "category": StepCategory.ANALYSIS,
        "svg_position": {"x": 250, "y": 200}
    },
    StepPoint.CONSCIENCE_EXECUTION: {
        "name": "Conscience Execution",
        "description": "Ethical safety and alignment checks",
        "category": StepCategory.ANALYSIS,
        "svg_position": {"x": 350, "y": 200}
    },
    StepPoint.RECURSIVE_ASPDMA: {
        "name": "Recursive ASPDMA",
        "description": "Optional re-analysis if conscience failed",
        "category": StepCategory.ANALYSIS,
        "svg_position": {"x": 250, "y": 250}
    },
    StepPoint.RECURSIVE_CONSCIENCE_EXECUTION: {
        "name": "Recursive Conscience",
        "description": "Optional re-check if conscience failed",
        "category": StepCategory.ANALYSIS,
        "svg_position": {"x": 350, "y": 250}
    },
    StepPoint.FINALIZE_ACTION: {
        "name": "Finalize Action",
        "description": "Final action determination and validation",
        "category": StepCategory.DECISION,
        "svg_position": {"x": 50, "y": 300}
    },
    StepPoint.MULTI_SERVICE_BUS: {
        "name": "Multi-Service Bus",
        "description": "Routing to appropriate service handlers",
        "category": StepCategory.DECISION,
        "svg_position": {"x": 150, "y": 300}
    },
    StepPoint.DELIVERY_PAYLOAD: {
        "name": "Delivery Payload",
        "description": "Preparing action payload for delivery",
        "category": StepCategory.EXECUTION,
        "svg_position": {"x": 250, "y": 300}
    },
    StepPoint.EXECUTION: {
        "name": "Execution",
        "description": "Executing the selected action",
        "category": StepCategory.EXECUTION,
        "svg_position": {"x": 350, "y": 300}
    },
    StepPoint.FOLLOW_UP_THOUGHT: {
        "name": "Follow-up Thought",
        "description": "Processing execution results and follow-ups",
        "category": StepCategory.COMPLETION,
        "svg_position": {"x": 450, "y": 300}
    },
    StepPoint.ROUND_COMPLETE: {
        "name": "Round Complete",
        "description": "Finalizing round and updating metrics",
        "category": StepCategory.COMPLETION,
        "svg_position": {"x": 550, "y": 300}
    }
}


def get_step_metadata(step_point: StepPoint) -> Dict[str, Any]:
    """Get UI metadata for a step point."""
    return STEP_METADATA.get(step_point, {
        "name": step_point.value.replace("_", " ").title(),
        "description": f"Processing {step_point.value}",
        "category": StepCategory.EXECUTION,
        "svg_position": {"x": 0, "y": 0}
    })


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
        return all_steps[current_index + 1:]
    return all_steps