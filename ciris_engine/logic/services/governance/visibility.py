"""
Visibility Service for CIRIS Trinity Architecture.

Provides TRACES - the "why" of agent behavior through reasoning transparency.

This is one of three observability pillars:
1. TRACES (this service) - Why decisions were made, reasoning chains
2. LOGS (AuditService) - What happened, who did it, when
3. METRICS (TelemetryService/TSDBConsolidation/ResourceMonitor) - Performance data

VisibilityService focuses exclusively on reasoning traces and decision history.
It does NOT provide service health, metrics, or general system status.
"""
from typing import List, Optional, Dict, Any
from datetime import datetime

from ciris_engine.protocols.services import VisibilityServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.protocols.runtime.base import ServiceProtocol
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.visibility import (
    VisibilitySnapshot, ReasoningTrace, TaskDecisionHistory
)
from ciris_engine.schemas.runtime.models import Task, Thought
from ciris_engine.schemas.runtime.enums import TaskStatus, ThoughtStatus
from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.persistence import (
    get_task_by_id,
    get_thoughts_by_task_id,
    get_thoughts_by_status,
    get_tasks_by_status,
    get_thought_by_id
)

class VisibilityService(BaseService, VisibilityServiceProtocol):
    """Service providing agent reasoning transparency."""

    def __init__(self, bus_manager: BusManager, time_service: TimeServiceProtocol, db_path: str) -> None:
        """Initialize with bus manager for querying other services."""
        super().__init__(time_service=time_service)
        self.bus = bus_manager
        self._db_path = db_path

    async def _on_start(self) -> None:
        """Custom startup logic for visibility service."""
        pass

    async def _on_stop(self) -> None:
        """Custom cleanup logic for visibility service."""
        pass

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [
            "get_current_state",
            "get_reasoning_trace",
            "get_decision_history",
            "explain_action"
        ]

    def get_status(self) -> ServiceStatus:
        """Get service status."""
        return ServiceStatus(
            service_name="VisibilityService",
            service_type="visibility_service",
            is_healthy=self._started,
            uptime_seconds=self._calculate_uptime(),
            metrics={},
            last_error=self._last_error,
            last_health_check=self._last_health_check
        )

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.INFRASTRUCTURE_SERVICE
    
    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        return self.bus is not None and self._db_path is not None
    
    def _register_dependencies(self) -> None:
        """Register service dependencies."""
        super()._register_dependencies()
        self._dependencies.add("BusManager")


    async def get_current_state(self) -> VisibilitySnapshot:
        """Get current agent state snapshot."""
        # Get current task from persistence
        # Note: This gets the most recent active task, as the processor's current task
        # is not directly accessible from here
        current_task = None
        active_tasks = get_tasks_by_status(TaskStatus.ACTIVE, db_path=self._db_path)
        if active_tasks:
            current_task = active_tasks[0]

        # Get active thoughts from persistence
        active_thoughts = []
        try:
            # Get recent pending/active thoughts
            pending_thoughts = get_thoughts_by_status(ThoughtStatus.PENDING, db_path=self._db_path)
            active_thoughts = pending_thoughts[:10]  # Limit to 10 most recent
        except Exception:
            pass

        # Get recent decisions from completed thoughts
        recent_decisions: List[Thought] = []
        try:
            completed_thoughts = get_thoughts_by_status(ThoughtStatus.COMPLETED, db_path=self._db_path)
            # Get the most recent thoughts that have final_action (which they all should)
            for thought in completed_thoughts[:10]:  # Get last 10
                if thought.final_action:
                    recent_decisions.append(thought)
        except Exception:
            pass

        # Calculate reasoning depth from active thoughts
        reasoning_depth = 0
        if active_thoughts:
            # Count the depth by checking parent relationships
            max_depth = 0
            for thought in active_thoughts:
                depth = 1
                parent_id = getattr(thought, 'parent_thought_id', None)
                while parent_id:
                    depth += 1
                    # Find parent thought
                    parent_found = False
                    for t in active_thoughts:
                        if t.thought_id == parent_id:
                            parent_id = getattr(t, 'parent_thought_id', None)
                            parent_found = True
                            break
                    if not parent_found:
                        break
                max_depth = max(max_depth, depth)
            reasoning_depth = max_depth

        return VisibilitySnapshot(
            timestamp=self._now(),
            current_task=current_task,
            active_thoughts=active_thoughts,
            recent_decisions=recent_decisions,
            reasoning_depth=reasoning_depth
        )

    async def get_reasoning_trace(self, task_id: str) -> ReasoningTrace:
        """Get reasoning trace for a task."""
        from ciris_engine.schemas.services.visibility import ThoughtStep

        # Get the task from persistence
        task = get_task_by_id(task_id, db_path=self._db_path)
        if not task:
            # Return empty trace if task not found
            return ReasoningTrace(
                task=Task(
                    task_id=task_id,
                    channel_id="system",
                    description="Task not found",
                    created_at=self._now().isoformat(),
                    updated_at=self._now().isoformat(),
                    parent_task_id=None,
                    context=None,
                    outcome=None
                ),
                thought_steps=[],
                total_thoughts=0,
                actions_taken=[],
                processing_time_ms=0.0
            )

        # Get all thoughts for this task from persistence
        thought_steps = []
        actions_taken = []

        try:
            thoughts = get_thoughts_by_task_id(task_id, db_path=self._db_path)

            for thought in thoughts:
                try:

                    # Get conscience results from the thought's final_action
                    conscience_results = None
                    if thought.final_action and thought.final_action.action_type not in ["TASK_COMPLETE", "REJECT"]:
                        # Conscience results are stored in the final_action
                        if hasattr(thought.final_action, 'conscience_results') and thought.final_action.conscience_results:
                            conscience_results = thought.final_action.conscience_results

                    # Handler result is represented by the thought's status and final_action
                    # If thought is COMPLETED, the handler succeeded
                    handler_result = None
                    if thought.status == ThoughtStatus.COMPLETED and thought.final_action:
                        # For now, we don't have HandlerResult objects in persistence
                        # This would require storing handler results separately
                        pass

                    # Get followup thought IDs by checking parent_thought_id
                    followup_thoughts = []
                    for other_thought in thoughts:
                        if hasattr(other_thought, 'parent_thought_id') and other_thought.parent_thought_id == thought.thought_id:
                            followup_thoughts.append(other_thought.thought_id)

                    # Create thought step
                    step = ThoughtStep(
                        thought=thought,
                        conscience_results=conscience_results,
                        handler_result=handler_result,
                        followup_thoughts=followup_thoughts
                    )
                    thought_steps.append(step)

                    # Track actions taken
                    if thought.final_action:
                        actions_taken.append(thought.final_action.action_type)

                except Exception:
                    # Skip malformed thoughts
                    pass
        except Exception:
            pass

        # Calculate processing time
        processing_time_ms = 0.0
        if task and thought_steps:
            try:
                start_time = datetime.fromisoformat(task.created_at)
                last_thought_time = datetime.fromisoformat(thought_steps[-1].thought.updated_at)
                processing_time_ms = (last_thought_time - start_time).total_seconds() * 1000
            except Exception:
                pass

        return ReasoningTrace(
            task=task,
            thought_steps=thought_steps,
            total_thoughts=len(thought_steps),
            actions_taken=actions_taken,
            processing_time_ms=processing_time_ms
        )

    async def get_decision_history(self, task_id: str) -> TaskDecisionHistory:
        """Get decision history for a task."""
        from ciris_engine.schemas.services.visibility import DecisionRecord

        # Get the task from persistence
        task = get_task_by_id(task_id, db_path=self._db_path)
        task_description = "Unknown task"
        created_at = self._now()

        if task:
            task_description = task.description
            created_at = datetime.fromisoformat(task.created_at)

        # Get all decisions (thoughts) for this task
        decisions = []
        successful_decisions = 0

        try:
            thoughts = get_thoughts_by_task_id(task_id, db_path=self._db_path)

            for thought in thoughts:
                try:

                    if thought.final_action:
                        # Check if it was executed based on thought status
                        executed = thought.status == ThoughtStatus.COMPLETED
                        success = executed  # If completed, it was successful
                        result = None

                        if executed:
                            successful_decisions += 1
                            result = f"Action {thought.final_action.action_type} completed successfully"

                        # Get alternatives considered from the thought's DMA results if available
                        alternatives: List[str] = []
                        # The alternatives would be in the thought's processing data if we stored them

                        decision = DecisionRecord(
                            decision_id=f"decision_{thought.thought_id}",
                            timestamp=datetime.fromisoformat(thought.created_at),
                            thought_id=thought.thought_id,
                            action_type=thought.final_action.action_type,
                            parameters=thought.final_action.action_params,
                            rationale=thought.final_action.reasoning,
                            alternatives_considered=list(set(alternatives)),
                            executed=executed,
                            result=result,
                            success=success
                        )
                        decisions.append(decision)

                except Exception:
                        # Skip malformed thoughts
                        pass
        except Exception:
            pass

        # Determine final status
        final_status = "unknown"
        completion_time = None

        if task:
            final_status = task.status.value
            if task.outcome:
                final_status = task.outcome.status
            if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
                completion_time = datetime.fromisoformat(task.updated_at)

        return TaskDecisionHistory(
            task_id=task_id,
            task_description=task_description,
            created_at=created_at,
            decisions=decisions,
            total_decisions=len(decisions),
            successful_decisions=successful_decisions,
            final_status=final_status,
            completion_time=completion_time
        )

    async def explain_action(self, action_id: str) -> str:
        """Explain why an action was taken."""
        # Action ID is typically the thought_id that decided on the action
        try:
            # Get the thought from persistence
            thought = get_thought_by_id(action_id, db_path=self._db_path)

            if thought:
                if thought.final_action:
                    explanation = f"Action: {thought.final_action.action_type}\n"
                    explanation += f"Reasoning: {thought.final_action.reasoning}\n"

                    # Add conscience results if available
                    if hasattr(thought.final_action, 'conscience_results') and thought.final_action.conscience_results:
                        explanation += "\nConscience evaluation: Available"

                    return explanation
                else:
                    return f"Thought {action_id} did not result in an action."
            else:
                return f"No thought found with ID {action_id}"

        except Exception as e:
            return f"Unable to explain action {action_id}: {str(e)}"
