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

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from ciris_engine.logic.buses import BusManager
from ciris_engine.logic.persistence import (
    get_task_by_id,
    get_tasks_by_status,
    get_thought_by_id,
    get_thoughts_by_status,
    get_thoughts_by_task_id,
)
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.protocols.services import VisibilityServiceProtocol
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought
from ciris_engine.schemas.services.visibility import ReasoningTrace, TaskDecisionHistory, VisibilitySnapshot
from ciris_engine.schemas.telemetry.core import ServiceCorrelation


class VisibilityService(BaseService, VisibilityServiceProtocol):
    """Service providing agent reasoning transparency."""

    def __init__(self, bus_manager: BusManager, time_service: TimeServiceProtocol, db_path: str) -> None:
        """Initialize with bus manager for querying other services."""
        super().__init__(time_service=time_service)
        self.bus = bus_manager
        self._db_path = db_path

        # Visibility service tracking variables
        self._dsar_requests = 0
        self._transparency_requests = 0
        self._audit_requests = 0
        self._export_operations = 0
        self._redaction_operations = 0
        self._consent_updates = 0

    async def _on_start(self) -> None:
        """Custom startup logic for visibility service."""
        pass

    async def _on_stop(self) -> None:
        """Custom cleanup logic for visibility service."""
        pass

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return ["get_current_state", "get_reasoning_trace", "get_decision_history", "explain_action"]

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.VISIBILITY

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
                parent_id = getattr(thought, "parent_thought_id", None)
                while parent_id:
                    depth += 1
                    # Find parent thought
                    parent_found = False
                    for t in active_thoughts:
                        if t.thought_id == parent_id:
                            parent_id = getattr(t, "parent_thought_id", None)
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
            reasoning_depth=reasoning_depth,
        )

    async def get_task_history(self, limit: int = 10) -> List[Task]:
        """
        Get recent task history for the agent.

        Args:
            limit: Maximum number of tasks to return (default 10)

        Returns:
            List of recent tasks, ordered by most recent first
        """
        self._transparency_requests += 1

        # Get recent tasks from persistence
        tasks = []

        # First try to get completed tasks
        completed_tasks = get_tasks_by_status(TaskStatus.COMPLETED, db_path=self._db_path)
        if completed_tasks:
            # Sort by updated_at timestamp (most recent first)
            completed_tasks.sort(key=lambda t: t.updated_at if t.updated_at else t.created_at, reverse=True)
            tasks.extend(completed_tasks[:limit])

        # If we need more tasks, add active ones
        if len(tasks) < limit:
            active_tasks = get_tasks_by_status(TaskStatus.ACTIVE, db_path=self._db_path)
            if active_tasks:
                active_tasks.sort(key=lambda t: t.updated_at if t.updated_at else t.created_at, reverse=True)
                remaining = limit - len(tasks)
                tasks.extend(active_tasks[:remaining])

        # If still need more, add failed tasks
        if len(tasks) < limit:
            failed_tasks = get_tasks_by_status(TaskStatus.FAILED, db_path=self._db_path)
            if failed_tasks:
                failed_tasks.sort(key=lambda t: t.updated_at if t.updated_at else t.created_at, reverse=True)
                remaining = limit - len(tasks)
                tasks.extend(failed_tasks[:remaining])

        # If still need more, add pending
        if len(tasks) < limit:
            pending_tasks = get_tasks_by_status(TaskStatus.PENDING, db_path=self._db_path)
            if pending_tasks:
                pending_tasks.sort(key=lambda t: t.updated_at if t.updated_at else t.created_at, reverse=True)
                remaining = limit - len(tasks)
                tasks.extend(pending_tasks[:remaining])

        return tasks

    async def get_reasoning_trace(self, task_id: str) -> ReasoningTrace:
        """Get reasoning trace for a task."""
        self._transparency_requests += 1
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
                    outcome=None,
                ),
                thought_steps=[],
                total_thoughts=0,
                actions_taken=[],
                processing_time_ms=0.0,
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
                        if (
                            hasattr(thought.final_action, "conscience_results")
                            and thought.final_action.conscience_results
                        ):
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
                        if (
                            hasattr(other_thought, "parent_thought_id")
                            and other_thought.parent_thought_id == thought.thought_id
                        ):
                            followup_thoughts.append(other_thought.thought_id)

                    # Create thought step
                    step = ThoughtStep(
                        thought=thought,
                        conscience_results=conscience_results,
                        handler_result=handler_result,
                        followup_thoughts=followup_thoughts,
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
            processing_time_ms=processing_time_ms,
        )

    async def get_decision_history(self, task_id: str) -> TaskDecisionHistory:
        """Get decision history for a task."""
        self._transparency_requests += 1
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
                            success=success,
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
            completion_time=completion_time,
        )

    async def explain_action(self, action_id: str) -> str:
        """Explain why an action was taken."""
        self._transparency_requests += 1
        # Action ID is typically the thought_id that decided on the action
        try:
            # Get the thought from persistence
            thought = get_thought_by_id(action_id, db_path=self._db_path)

            if thought:
                if thought.final_action:
                    explanation = f"Action: {thought.final_action.action_type}\n"
                    explanation += f"Reasoning: {thought.final_action.reasoning}\n"

                    # Add conscience results if available
                    if hasattr(thought.final_action, "conscience_results") and thought.final_action.conscience_results:
                        explanation += "\nConscience evaluation: Available"

                    return explanation
                else:
                    return f"Thought {action_id} did not result in an action."
            else:
                return f"No thought found with ID {action_id}"

        except Exception as e:
            return f"Unable to explain action {action_id}: {str(e)}"

    def apply_redaction(self, content: str, redacted_content: str) -> str:
        """Apply redaction to content and track the operation."""
        self._redaction_operations += 1
        return redacted_content

    async def get_recent_traces(self, limit: int = 100) -> List["ServiceCorrelation"]:
        """
        Get recent trace correlations from the telemetry service.

        Returns ServiceCorrelation objects that represent trace spans,
        always linked to their corresponding tasks/thoughts.

        Only returns traces that haven't been exported yet (timestamp-based filtering).
        """
        try:
            # Try to get traces from in-memory telemetry service
            traces = self._get_traces_from_telemetry_service(limit)
            if traces is not None:
                return traces

            # Fallback to database
            return await self._get_traces_from_database(limit)

        except Exception as e:
            logger.error(f"Failed to get recent traces: {e}")
            return []

    def _get_traces_from_telemetry_service(self, limit: int) -> Optional[List["ServiceCorrelation"]]:
        """
        Get traces from in-memory telemetry service.

        Returns None if telemetry service is not available or doesn't have correlations.
        """
        # Check if runtime and telemetry service are available
        if not hasattr(self, "_runtime") or not self._runtime:
            logger.warning("No _runtime reference on visibility service - cannot get telemetry service")
            return None

        telemetry_service = getattr(self._runtime, "telemetry_service", None)
        if not telemetry_service:
            return None

        if not hasattr(telemetry_service, "_recent_correlations"):
            logger.debug("Telemetry service found but _recent_correlations not available, will query database")
            return None

        # Initialize export timestamp if needed
        self._initialize_trace_export_timestamp(telemetry_service)

        # Filter and return new traces
        return self._filter_and_update_traces(telemetry_service, limit)

    def _initialize_trace_export_timestamp(self, telemetry_service: Any) -> None:
        """Initialize the last export timestamp on telemetry service if not present."""
        if hasattr(telemetry_service, "_last_trace_export_time"):
            return

        from datetime import datetime, timezone

        # Start from "now" so we only export NEW traces going forward
        telemetry_service._last_trace_export_time = datetime.now(timezone.utc)
        logger.info(f"Initialized trace export timestamp filter at {telemetry_service._last_trace_export_time}")

    def _filter_and_update_traces(self, telemetry_service: Any, limit: int) -> List["ServiceCorrelation"]:
        """Filter new traces and update the export timestamp."""
        last_export = telemetry_service._last_trace_export_time
        new_correlations = [c for c in telemetry_service._recent_correlations if c.timestamp > last_export]

        # Return up to limit newest traces
        correlations = new_correlations[-limit:] if new_correlations else []

        # Update last export time to the newest trace we're returning
        if correlations:
            telemetry_service._last_trace_export_time = max(c.timestamp for c in correlations)
            logger.debug(
                f"Retrieved {len(correlations)} NEW traces (after {last_export}), "
                f"updated export time to {telemetry_service._last_trace_export_time}"
            )
        else:
            logger.debug(f"No new traces since last export at {last_export}")

        return list(correlations)

    async def _get_traces_from_database(self, limit: int) -> List["ServiceCorrelation"]:
        """
        Fallback method to get traces from database.

        Returns empty list on error.
        """
        from ciris_engine.logic.persistence.models.correlations import get_recent_correlations

        try:
            # Get recent correlations from database
            correlations = get_recent_correlations(limit=limit)
            # The correlations are already ServiceCorrelation objects from the database
            logger.debug(f"Retrieved {len(correlations)} traces from database")
            return list(correlations)
        except Exception as e:
            # Log the error loudly
            logger.error(f"Failed to get traces from database: {e}", exc_info=True)
            return []

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect visibility service metrics."""
        metrics = super()._collect_custom_metrics()

        # v1.4.3 API visibility metrics - using real values from service state
        metrics.update(
            {
                "visibility_requests_total": float(self._transparency_requests),
                "visibility_explanations_total": float(
                    self._transparency_requests
                ),  # Each transparency request generates explanations
                "visibility_redactions_total": float(self._redaction_operations),
                "visibility_uptime_seconds": self._calculate_uptime(),
            }
        )

        return metrics
