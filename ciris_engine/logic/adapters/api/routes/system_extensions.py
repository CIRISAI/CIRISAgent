"""
System management endpoint extensions for CIRIS API v1.

Adds runtime queue, service management, and processor state endpoints.
"""

import copy
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.api.auth import AuthContext
from ciris_engine.schemas.api.responses import ResponseMetadata, SuccessResponse
from ciris_engine.schemas.services.core.runtime import (
    ProcessorQueueStatus,
    ServiceHealthStatus,
    ServiceSelectionExplanation,
)
from ciris_engine.schemas.services.runtime_control import PipelineState, StepPoint
from ciris_engine.schemas.services.runtime_control import StepResultUnion as StepResult
from ciris_engine.schemas.types import JSONDict

from ..constants import (
    DESC_CURRENT_COGNITIVE_STATE,
    DESC_HUMAN_READABLE_STATUS,
    ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE,
)
from ..dependencies.auth import require_admin, require_observer

router = APIRouter(prefix="/system", tags=["system-extensions"])
logger = logging.getLogger(__name__)


# Runtime Control Extensions


@router.get("/runtime/queue", response_model=SuccessResponse[ProcessorQueueStatus])
async def get_processing_queue_status(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ProcessorQueueStatus]:
    """
    Get processing queue status.

    Returns information about pending thoughts, tasks, and processing metrics.
    """
    # Try main runtime control service first (has all methods), fall back to API runtime control
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        queue_status = await runtime_control.get_processor_queue_status()
        return SuccessResponse(data=queue_status)
    except Exception as e:
        logger.error(f"Error getting queue status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class RuntimeControlResponse(BaseModel):
    """Response to runtime control actions."""

    success: bool = Field(..., description="Whether action succeeded")
    message: str = Field(..., description=DESC_HUMAN_READABLE_STATUS)
    processor_state: str = Field(..., description="Current processor state")
    cognitive_state: Optional[str] = Field(None, description=DESC_CURRENT_COGNITIVE_STATE)
    queue_depth: int = Field(0, description="Number of items in processing queue")


class SingleStepResponse(RuntimeControlResponse):
    """Response for single-step operations with detailed step point data.

    Extends the basic RuntimeControlResponse with comprehensive step point information,
    pipeline state, and demo-ready data for transparent AI operation visibility.
    """

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "success": True,
                "message": "Single step completed: Processed PERFORM_DMAS for thought_001",
                "processor_state": "paused",
                "cognitive_state": "WORK",
                "queue_depth": 3,
                "step_point": "PERFORM_DMAS",
                "step_result": {
                    "step_point": "PERFORM_DMAS",
                    "thought_id": "thought_001",
                    "ethical_dma": {"reasoning": "Analyzed ethical implications", "confidence_level": 0.85},
                    "common_sense_dma": {"reasoning": "Applied common sense principles", "confidence_level": 0.90},
                    "domain_dma": {"reasoning": "Domain expertise applied", "confidence_level": 0.80},
                },
                "pipeline_state": {
                    "is_paused": True,
                    "current_round": 5,
                    "thoughts_by_step": {"BUILD_CONTEXT": [], "PERFORM_DMAS": []},
                },
                "processing_time_ms": 1250.0,
                "tokens_used": 150,
                "demo_data": {
                    "category": "ethical_reasoning",
                    "step_description": "Multi-perspective DMA analysis",
                    "key_insights": {
                        "ethical_confidence": 0.85,
                        "dmas_executed": ["ethical", "common_sense", "domain"],
                    },
                },
            }
        }
    )

    # Step Point Information
    step_point: Optional[StepPoint] = Field(None, description="The step point that was just executed")
    step_result: Optional[JSONDict] = Field(None, description="Complete step result data with full context")

    # Pipeline State
    pipeline_state: Optional[PipelineState] = Field(None, description="Current pipeline state with all thoughts")

    # Performance Metrics
    processing_time_ms: float = Field(0.0, description="Total processing time for this step in milliseconds")
    tokens_used: Optional[int] = Field(None, description="LLM tokens consumed during this step")

    # Transparency Data
    transparency_data: Optional[JSONDict] = Field(
        None, description="Detailed reasoning and system state data for transparency"
    )


# Helper functions for single-step processor


def _extract_cognitive_state(runtime: Any) -> Optional[str]:
    """Extract cognitive state from runtime safely."""
    try:
        if runtime and hasattr(runtime, "agent_processor") and runtime.agent_processor:
            if hasattr(runtime.agent_processor, "state_manager") and runtime.agent_processor.state_manager:
                current_state = runtime.agent_processor.state_manager.get_state()
                return str(current_state) if current_state else None
    except Exception as e:
        logger.debug(f"Could not extract cognitive state: {e}")
    return None


async def _get_queue_depth(runtime_control: Any) -> int:
    """Get queue depth safely."""
    try:
        queue_status = await runtime_control.get_processor_queue_status()
        return queue_status.queue_size if queue_status else 0
    except Exception as e:
        logger.debug(f"Could not get queue depth: {e}")
        return 0


def _get_pipeline_controller(runtime: Any) -> Any:
    """Safely extract pipeline controller from runtime."""
    if not runtime:
        return None
    if not hasattr(runtime, "pipeline_controller"):
        return None
    return runtime.pipeline_controller


def _get_pipeline_state(pipeline_controller: Any) -> Optional[Any]:
    """Get current pipeline state, returning None on error."""
    if not pipeline_controller:
        return None
    try:
        return pipeline_controller.get_current_state()
    except Exception as e:
        logger.debug(f"Could not get pipeline state: {e}")
        return None


def _get_latest_step_data(pipeline_controller: Any) -> tuple[Optional[Any], Optional[JSONDict]]:
    """Extract step point and result from pipeline controller."""
    if not pipeline_controller:
        return None, None

    try:
        latest_step_result = pipeline_controller.get_latest_step_result()
        if not latest_step_result:
            return None, None

        step_point = latest_step_result.step_point
        step_result = (
            latest_step_result.model_dump() if hasattr(latest_step_result, "model_dump") else dict(latest_step_result)
        )
        return step_point, step_result
    except Exception as e:
        logger.debug(f"Could not get step result: {e}")
        return None, None


def _get_processing_metrics(pipeline_controller: Any) -> tuple[float, Optional[int]]:
    """Extract processing time and token usage from metrics."""
    if not pipeline_controller:
        return 0.0, None

    try:
        metrics = pipeline_controller.get_processing_metrics()
        if not metrics:
            return 0.0, None

        processing_time_ms = metrics.get("total_processing_time_ms", 0.0)
        tokens_used = metrics.get("tokens_used")
        return processing_time_ms, tokens_used
    except Exception as e:
        logger.debug(f"Could not get processing metrics: {e}")
        return 0.0, None


def _extract_pipeline_data(
    runtime: Any,
) -> tuple[Optional[Any], Optional[JSONDict], Optional[Any], float, Optional[int], Optional[JSONDict]]:
    """Extract pipeline state, step result, and processing metrics."""
    try:
        pipeline_controller = _get_pipeline_controller(runtime)
        pipeline_state = _get_pipeline_state(pipeline_controller)
        step_point, step_result = _get_latest_step_data(pipeline_controller)
        processing_time_ms, tokens_used = _get_processing_metrics(pipeline_controller)
        demo_data = None  # Demo data removed - using transparency_data from real step results

        return step_point, step_result, pipeline_state, processing_time_ms, tokens_used, demo_data
    except Exception as e:
        logger.debug(f"Could not extract enhanced data: {e}")
        return None, None, None, 0.0, None, None


def _get_runtime_control_service_for_step(request: Request) -> Any:
    """Get runtime control service for single step operations."""
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)
    return runtime_control


def _create_basic_response_data(result: Any, cognitive_state: Optional[str], queue_depth: int) -> JSONDict:
    """Create basic response data for single step."""
    return {
        "success": result.success,
        "message": f"Single step {'completed' if result.success else 'failed'}: {result.error or 'No additional info'}",
        "processor_state": result.new_status.value if hasattr(result.new_status, "value") else str(result.new_status),
        "cognitive_state": cognitive_state,
        "queue_depth": queue_depth,
    }


def _convert_step_point(result: Any) -> Optional[Any]:
    """Convert step_point string to enum if needed."""
    from ciris_engine.schemas.services.runtime_control import StepPoint

    if not result.step_point:
        return None

    try:
        return StepPoint(result.step_point.lower()) if isinstance(result.step_point, str) else result.step_point
    except (ValueError, AttributeError):
        return None


def _consolidate_step_results(result: Any) -> Optional[JSONDict]:
    """Convert step_results list to consolidated step_result dict for API response."""
    if not (result.step_results and isinstance(result.step_results, list)):
        return None

    # Group step results by round number (from parent current_round)
    results_by_round = {}
    current_round = getattr(result, "current_round", None)

    if current_round is not None:
        # Create a round entry with the step results
        round_data = {
            "round_number": current_round,
            "step_data": result.step_results[0].model_dump() if result.step_results else {},
        }
        # Add task_id from first step result if available
        if result.step_results and hasattr(result.step_results[0], "task_id"):
            round_data["task_id"] = result.step_results[0].task_id

        results_by_round[str(current_round)] = round_data

    return {
        "steps_processed": len(result.step_results),
        "results_by_round": results_by_round,
        "summary": result.step_results[0].model_dump() if result.step_results else None,
    }


@router.post("/runtime/step", response_model=SuccessResponse[SingleStepResponse])
async def single_step_processor(
    request: Request, auth: AuthContext = Depends(require_admin), body: JSONDict = Body(default={})
) -> SuccessResponse[SingleStepResponse]:
    """
    Execute a single processing step.

    Useful for debugging and demonstrations. Processes one item from the queue.
    Always returns detailed H3ERE step data for transparency.
    Requires ADMIN role.
    """
    runtime_control = _get_runtime_control_service_for_step(request)

    try:
        result = await runtime_control.single_step()

        # Get basic runtime data
        runtime = getattr(request.app.state, "runtime", None)
        cognitive_state = _extract_cognitive_state(runtime)
        queue_depth = await _get_queue_depth(runtime_control)

        # Create response components
        basic_response_data = _create_basic_response_data(result, cognitive_state, queue_depth)
        safe_step_point = _convert_step_point(result)
        safe_step_result = _consolidate_step_results(result)

        # Extract other safe data
        safe_pipeline_state = result.pipeline_state
        safe_processing_time = result.processing_time_ms or 0.0
        safe_tokens_used = None  # Not yet implemented in ProcessorControlResponse
        safe_transparency_data = None  # Real transparency data from step results

        single_step_response = SingleStepResponse(
            **basic_response_data,
            step_point=safe_step_point,
            step_result=safe_step_result,
            pipeline_state=safe_pipeline_state,
            processing_time_ms=safe_processing_time,
            tokens_used=safe_tokens_used,
            transparency_data=safe_transparency_data,
        )

        return SuccessResponse(data=single_step_response)

    except Exception as e:
        logger.error(f"Error in single step: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Service Management Extensions


class ServicePriorityUpdateRequest(BaseModel):
    """Request to update service priority."""

    priority: str = Field(..., description="New priority level (CRITICAL, HIGH, NORMAL, LOW, FALLBACK)")
    priority_group: Optional[int] = Field(None, description="Priority group (0, 1, 2...)")
    strategy: Optional[str] = Field(None, description="Selection strategy (FALLBACK, ROUND_ROBIN)")


@router.get("/services/health", response_model=SuccessResponse[ServiceHealthStatus])
async def get_service_health_details(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ServiceHealthStatus]:
    """
    Get detailed service health status.

    Returns comprehensive health information including circuit breaker states,
    error rates, and recommendations.
    """
    # Try main runtime control service first (has all methods), fall back to API runtime control
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        health_status = await runtime_control.get_service_health_status()
        return SuccessResponse(data=health_status)
    except Exception as e:
        logger.error(f"Error getting service health: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ServicePriorityUpdateResponse(BaseModel):
    """Response from service priority update."""

    provider_name: str = Field(..., description="Provider name that was updated")
    old_priority: str = Field(..., description="Previous priority level")
    new_priority: str = Field(..., description="New priority level")
    old_priority_group: Optional[int] = Field(None, description="Previous priority group")
    new_priority_group: Optional[int] = Field(None, description="New priority group")
    old_strategy: Optional[str] = Field(None, description="Previous selection strategy")
    new_strategy: Optional[str] = Field(None, description="New selection strategy")
    message: str = Field(..., description="Status message")


@router.put("/services/{provider_name}/priority", response_model=SuccessResponse[ServicePriorityUpdateResponse])
async def update_service_priority(
    provider_name: str, body: ServicePriorityUpdateRequest, request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[ServicePriorityUpdateResponse]:
    """
    Update service provider priority.

    Changes the priority, priority group, and/or selection strategy for a service provider.
    Requires ADMIN role.
    """
    # Try main runtime control service first (has all methods), fall back to API runtime control
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        result = await runtime_control.update_service_priority(
            provider_name=provider_name,
            new_priority=body.priority,
            new_priority_group=body.priority_group,
            new_strategy=body.strategy,
        )
        # Convert the result dict to our typed response
        response = ServicePriorityUpdateResponse(
            provider_name=result.get("provider_name", provider_name),
            old_priority=result.get("old_priority", "NORMAL"),
            new_priority=result.get("new_priority", body.priority),
            old_priority_group=result.get("old_priority_group"),
            new_priority_group=result.get("new_priority_group"),
            old_strategy=result.get("old_strategy"),
            new_strategy=result.get("new_strategy"),
            message=result.get("message", "Priority updated successfully"),
        )
        return SuccessResponse(data=response)
    except Exception as e:
        logger.error(f"Error updating service priority: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class CircuitBreakerResetRequest(BaseModel):
    """Request to reset circuit breakers."""

    service_type: Optional[str] = Field(None, description="Specific service type to reset, or all if not specified")


class CircuitBreakerResetResponse(BaseModel):
    """Response from circuit breaker reset."""

    service_type: Optional[str] = Field(None, description="Service type that was reset")
    reset_count: int = Field(..., description="Number of circuit breakers reset")
    services_affected: List[str] = Field(default_factory=list, description="List of affected services")
    message: str = Field(..., description="Status message")


@router.post("/services/circuit-breakers/reset", response_model=SuccessResponse[CircuitBreakerResetResponse])
async def reset_service_circuit_breakers(
    body: CircuitBreakerResetRequest, request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[CircuitBreakerResetResponse]:
    """
    Reset circuit breakers.

    Resets circuit breakers for specified service type or all services.
    Useful for recovering from transient failures.
    Requires ADMIN role.
    """
    # Try main runtime control service first (has all methods), fall back to API runtime control
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        result = await runtime_control.reset_circuit_breakers(body.service_type)
        # Convert the result dict to our typed response
        response = CircuitBreakerResetResponse(
            service_type=body.service_type,
            reset_count=result.get("reset_count", 0),
            services_affected=result.get("services_affected", []),
            message=result.get("message", "Circuit breakers reset successfully"),
        )
        return SuccessResponse(data=response)
    except Exception as e:
        logger.error(f"Error resetting circuit breakers: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/services/selection-logic", response_model=SuccessResponse[ServiceSelectionExplanation])
async def get_service_selection_explanation(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[ServiceSelectionExplanation]:
    """
    Get service selection logic explanation.

    Returns detailed explanation of how services are selected, including
    priority groups, priorities, strategies, and circuit breaker behavior.
    """
    # Try main runtime control service first (has all methods), fall back to API runtime control
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    try:
        explanation = await runtime_control.get_service_selection_explanation()
        return SuccessResponse(data=explanation)
    except Exception as e:
        logger.error(f"Error getting service selection explanation: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Processor State Information


class ProcessorStateInfo(BaseModel):
    """Information about a processor state."""

    name: str = Field(..., description="State name (WAKEUP, WORK, DREAM, etc.)")
    is_active: bool = Field(..., description="Whether this state is currently active")
    description: str = Field(..., description="State description")
    capabilities: List[str] = Field(default_factory=list, description="What this state can do")


def _get_current_state_name(runtime: Any) -> Optional[str]:
    """Extract current state name from runtime."""
    if not hasattr(runtime.agent_processor, "state_manager") or not runtime.agent_processor.state_manager:
        return None

    current_state = runtime.agent_processor.state_manager.get_state()
    if not current_state:
        return None

    # Handle both enum objects and string representations like "AgentState.WORK"
    current_state_str = str(current_state)
    return current_state_str.split(".")[-1] if "." in current_state_str else current_state_str


def _create_processor_state(
    name: str, description: str, capabilities: List[str], is_active: bool
) -> ProcessorStateInfo:
    """Create a ProcessorStateInfo object."""
    return ProcessorStateInfo(
        name=name,
        is_active=is_active,
        description=description,
        capabilities=capabilities,
    )


def _get_processor_state_definitions(current_state_name: Optional[str]) -> List[ProcessorStateInfo]:
    """Get all processor state definitions."""
    states = [
        (
            "WAKEUP",
            "Initial state for identity confirmation and system initialization",
            ["identity_confirmation", "system_checks", "initial_setup"],
        ),
        (
            "WORK",
            "Normal task processing and interaction state",
            ["task_processing", "user_interaction", "tool_usage", "memory_operations"],
        ),
        (
            "DREAM",
            "Deep introspection and memory consolidation state",
            ["memory_consolidation", "pattern_analysis", "self_reflection"],
        ),
        (
            "PLAY",
            "Creative exploration and experimentation state",
            ["creative_tasks", "exploration", "learning", "experimentation"],
        ),
        (
            "SOLITUDE",
            "Quiet reflection and planning state",
            ["planning", "reflection", "goal_setting", "strategy_development"],
        ),
        (
            "SHUTDOWN",
            "Graceful shutdown and cleanup state",
            ["cleanup", "final_messages", "state_persistence", "resource_release"],
        ),
    ]

    return [
        _create_processor_state(name, description, capabilities, current_state_name == name)
        for name, description, capabilities in states
    ]


@router.get("/processors", response_model=SuccessResponse[List[ProcessorStateInfo]])
async def get_processor_states(
    request: Request, auth: AuthContext = Depends(require_observer)
) -> SuccessResponse[List[ProcessorStateInfo]]:
    """
    Get information about all processor states.

    Returns the list of available processor states (WAKEUP, WORK, DREAM, PLAY,
    SOLITUDE, SHUTDOWN) and which one is currently active.
    """
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime or not hasattr(runtime, "agent_processor"):
        raise HTTPException(status_code=503, detail="Agent processor not available")

    try:
        current_state_name = _get_current_state_name(runtime)
        processor_states = _get_processor_state_definitions(current_state_name)
        return SuccessResponse(data=processor_states)

    except Exception as e:
        logger.error(f"Error getting processor states: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _determine_user_role(current_user: JSONDict) -> Any:
    """Determine user role from current_user dict."""
    from ciris_engine.schemas.api.auth import UserRole

    user_role = current_user.get("role", UserRole.OBSERVER)
    if isinstance(user_role, str):
        try:
            user_role = UserRole(user_role)
        except ValueError:
            user_role = UserRole.OBSERVER
    return user_role


async def _get_user_allowed_channel_ids(auth_service: Any, user_id: str) -> set[str]:
    """Get set of channel IDs user is allowed to see (user_id + OAuth links + API-prefixed versions)."""
    import sqlite3

    allowed_channel_ids = {user_id}
    # BUGFIX: API adapter prefixes channel_id with "api_"
    # See agent.py:221: channel_id = f"api_{auth.user_id}"
    allowed_channel_ids.add(f"api_{user_id}")

    try:
        # Use database abstraction layer to support both SQLite and PostgreSQL
        from ciris_engine.logic.persistence.db.core import get_db_connection

        db_path = auth_service.db_path
        query = """
            SELECT oauth_provider, oauth_external_id
            FROM wa_cert
            WHERE wa_id = ? AND oauth_provider IS NOT NULL AND oauth_external_id IS NOT NULL AND active = 1
        """
        with get_db_connection(db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, (user_id,))
            rows = cursor.fetchall()
            for row in rows:
                # Handle both SQLite Row and PostgreSQL RealDictRow
                if hasattr(row, "keys"):
                    oauth_provider, oauth_external_id = row["oauth_provider"], row["oauth_external_id"]
                else:
                    oauth_provider, oauth_external_id = row
                # Add OAuth channel ID formats
                oauth_channel = f"{oauth_provider}:{oauth_external_id}"
                allowed_channel_ids.add(oauth_channel)
                allowed_channel_ids.add(oauth_external_id)
                # BUGFIX: Also add API-prefixed versions for SSE filtering
                allowed_channel_ids.add(f"api_{oauth_channel}")
                allowed_channel_ids.add(f"api_{oauth_external_id}")
    except Exception as e:
        logger.error(f"Error fetching OAuth links for user {user_id}: {e}", exc_info=True)

    return allowed_channel_ids


async def _batch_fetch_task_channel_ids(task_ids: List[str]) -> Dict[str, str]:
    """Batch fetch channel_ids for multiple task_ids from main database."""
    task_channel_map: Dict[str, str] = {}
    if not task_ids:
        return task_channel_map

    try:
        # Tasks are stored in the main database
        # Use the proper database path helper which gets config from ServiceRegistry
        from ciris_engine.logic.persistence import get_sqlite_db_full_path
        from ciris_engine.logic.persistence.db.core import get_db_connection
        from ciris_engine.logic.persistence.db.dialect import get_adapter

        main_db_path = get_sqlite_db_full_path()  # Gets main DB path from config via registry
        logger.debug(f"SSE Filter: Fetching from main_db_path={main_db_path}")

        # Get database adapter for proper placeholder handling
        adapter = get_adapter()
        placeholder = "%s" if adapter.is_postgresql() else "?"
        placeholders = ",".join([placeholder] * len(task_ids))
        query = f"SELECT task_id, channel_id FROM tasks WHERE task_id IN ({placeholders})"

        with get_db_connection(main_db_path) as conn:
            cursor = conn.cursor()
            cursor.execute(query, task_ids)
            rows = cursor.fetchall()
            logger.debug(f"SSE Filter: Query returned {len(rows)} rows")
            for row in rows:
                # Handle both SQLite Row (tuple) and PostgreSQL RealDictRow (dict)
                if hasattr(row, "keys"):
                    tid, cid = row["task_id"], row["channel_id"]
                else:
                    tid, cid = row
                task_channel_map[tid] = cid
                logger.debug(f"SSE Filter: Found task_id={tid} -> channel_id={cid}")
    except Exception as e:
        logger.error(f"Error batch fetching task channel_ids: {e}", exc_info=True)

    return task_channel_map


def _filter_events_by_channel_access(
    events: List[Any], allowed_channel_ids: set[str], task_channel_cache: Dict[str, str]
) -> List[Any]:
    """Filter events to only those the user can access based on channel_id whitelist."""
    filtered_events = []
    for event in events:
        task_id = event.get("task_id")
        event_type = event.get("event_type", "unknown")

        if not task_id:
            # No task_id means system event - skip for non-admin users
            logger.debug(f"SSE Filter: Skipping event {event_type} - no task_id")
            continue

        channel_id = task_channel_cache.get(task_id)
        if not channel_id:
            logger.warning(f"SSE Filter: No channel_id found for task_id={task_id}, event_type={event_type}")
            continue

        if channel_id in allowed_channel_ids:
            logger.debug(f"SSE Filter: ALLOWED event {event_type} - task_id={task_id}, channel_id={channel_id}")
            filtered_events.append(event)
        else:
            logger.warning(
                f"SSE Filter: BLOCKED event {event_type} - task_id={task_id}, "
                f"channel_id={channel_id} not in allowed_channel_ids={allowed_channel_ids}"
            )

    return filtered_events


def _is_snapshot_event(event: Any) -> bool:
    """Check if event is a snapshot_and_context event that needs redaction."""
    return bool(event.get("event_type") == "snapshot_and_context")


def _remove_task_summaries(system_snapshot: JSONDict) -> None:
    """Remove sensitive task summaries from system snapshot."""
    system_snapshot["recently_completed_tasks_summary"] = []
    system_snapshot["top_pending_tasks_summary"] = []


def _filter_user_profiles(user_profiles: Any, allowed_user_ids: set[str]) -> Any:
    """Filter user profiles to only allowed user IDs."""
    if isinstance(user_profiles, list):
        return [
            profile
            for profile in user_profiles
            if isinstance(profile, dict) and profile.get("user_id") in allowed_user_ids
        ]
    elif isinstance(user_profiles, dict):
        return {user_id: profile for user_id, profile in user_profiles.items() if user_id in allowed_user_ids}
    return user_profiles


def _redact_system_snapshot(system_snapshot: JSONDict, allowed_user_ids: set[str]) -> None:
    """Redact sensitive data from system snapshot in-place."""
    _remove_task_summaries(system_snapshot)

    if "user_profiles" in system_snapshot and system_snapshot["user_profiles"]:
        system_snapshot["user_profiles"] = _filter_user_profiles(system_snapshot["user_profiles"], allowed_user_ids)


def _redact_observer_sensitive_data(events: List[Any], allowed_user_ids: set[str]) -> List[Any]:
    """Redact sensitive task and user information from events for OBSERVER users.

    Removes:
    - recently_completed_tasks_summary
    - top_pending_tasks_summary

    Filters:
    - user_profiles (only shows user's OWN profile based on allowed_user_ids)

    from system_snapshot in SNAPSHOT_AND_CONTEXT events.

    Args:
        events: List of events to redact
        allowed_user_ids: Set of user IDs the user is allowed to see (self + OAuth links)
    """
    redacted_events = []
    for event in events:
        if _is_snapshot_event(event):
            event = copy.deepcopy(event)
            if "system_snapshot" in event and event["system_snapshot"]:
                _redact_system_snapshot(event["system_snapshot"], allowed_user_ids)

        redacted_events.append(event)

    return redacted_events


@router.get("/runtime/reasoning-stream")
async def reasoning_stream(request: Request, auth: AuthContext = Depends(require_observer)) -> Any:
    """
    Stream live H3ERE reasoning steps as they occur.

    Provides real-time streaming of step-by-step reasoning for live UI generation.
    Returns Server-Sent Events (SSE) with step data as processing happens.
    Requires OBSERVER role or higher.
    """
    import asyncio
    import json

    from fastapi.responses import StreamingResponse

    from ciris_engine.schemas.api.auth import UserRole

    # Get runtime control service
    runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if not runtime_control:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
    if not runtime_control:
        raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

    # Get authentication service for OAuth lookup
    auth_service = getattr(request.app.state, "authentication_service", None)
    if not auth_service:
        raise HTTPException(status_code=503, detail="Authentication service not available")

    # SECURITY: Determine if user can see all events (ADMIN or higher)
    user_role = auth.role
    can_see_all = user_role in (UserRole.ADMIN, UserRole.SYSTEM_ADMIN, UserRole.AUTHORITY)

    # SECURITY: Get user's allowed channel IDs (user_id + linked OAuth accounts)
    allowed_channel_ids: set[str] = set()
    allowed_user_ids: set[str] = set()  # User IDs for profile filtering
    task_channel_cache: dict[str, str] = {}  # Cache task_id -> channel_id lookups

    if not can_see_all:
        user_id = auth.user_id
        if not user_id:
            raise HTTPException(status_code=401, detail="User ID not found in token")

        allowed_channel_ids = await _get_user_allowed_channel_ids(auth_service, user_id)
        allowed_user_ids = {user_id}  # User can only see their own profile

        # DEBUG: Log allowed channel IDs for OBSERVER users
        logger.info(f"SSE Filter: OBSERVER user_id={user_id}, allowed_channel_ids={allowed_channel_ids}")

    async def stream_reasoning_steps() -> Any:
        """Generate Server-Sent Events for live reasoning steps."""
        try:
            # Subscribe to the global reasoning event stream
            from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream

            # Create a queue for this client
            stream_queue: asyncio.Queue[Any] = asyncio.Queue(maxsize=100)
            reasoning_event_stream.subscribe(stream_queue)

            logger.debug(
                f" SSE stream connected - user_id={auth.user_id}, role={user_role}, can_see_all={can_see_all}, allowed_channel_ids={allowed_channel_ids}"
            )

            try:
                # Send initial connection event
                yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'timestamp': datetime.now().isoformat()})}\n\n"

                # Stream live step results as they occur
                while True:
                    try:
                        # Wait for step results with timeout to send keepalive
                        step_update = await asyncio.wait_for(stream_queue.get(), timeout=30.0)

                        logger.debug(
                            f" SSE received update from queue - events_count={len(step_update.get('events', []))}, can_see_all={can_see_all}"
                        )

                        # SECURITY: Filter events for OBSERVER users
                        # ADMIN+ users bypass filtering and see all events
                        if not can_see_all:
                            events = step_update.get("events", [])
                            if not events:
                                logger.debug(" SSE no events in update, skipping")
                                continue

                            # Batch lookup uncached task IDs
                            uncached_task_ids = [
                                event.get("task_id")
                                for event in events
                                if event.get("task_id") and event.get("task_id") not in task_channel_cache
                            ]

                            # SECURITY: Batch fetch channel_ids for efficiency
                            if uncached_task_ids:
                                logger.info(f"SSE Filter: Fetching channel_ids for uncached tasks: {uncached_task_ids}")
                                new_mappings = await _batch_fetch_task_channel_ids(uncached_task_ids)
                                logger.info(f"SSE Filter: Fetched task->channel mappings: {new_mappings}")
                                task_channel_cache.update(new_mappings)

                            # DEBUG: Log event task_ids before filtering
                            event_task_ids = [event.get("task_id") for event in events if event.get("task_id")]
                            logger.info(f"SSE Filter: Processing {len(events)} events with task_ids: {event_task_ids}")
                            logger.info(f"SSE Filter: Current task_channel_cache: {task_channel_cache}")

                            # Filter events based on channel_id whitelist
                            filtered_events = _filter_events_by_channel_access(
                                events, allowed_channel_ids, task_channel_cache
                            )

                            # DEBUG: Log filtering results
                            logger.info(f"SSE Filter: Filtered to {len(filtered_events)}/{len(events)} events")

                            # SECURITY: Redact sensitive task information for OBSERVER users
                            # This removes recently_completed_tasks and pending_tasks from snapshots
                            # and filters user_profiles to only show user's OWN profile
                            if filtered_events and user_role == UserRole.OBSERVER:
                                filtered_events = _redact_observer_sensitive_data(filtered_events, allowed_user_ids)

                            # Replace events with filtered list
                            if filtered_events:
                                step_update = {"events": filtered_events}
                                logger.debug(f" SSE sending {len(filtered_events)} events to client")
                            else:
                                # No events for this user, skip this update silently
                                logger.debug(" SSE all events filtered out, skipping update")
                                continue

                        # Stream the step update
                        yield f"event: step_update\ndata: {json.dumps(step_update, default=str)}\n\n"

                    except asyncio.TimeoutError:
                        # Send keepalive every 30 seconds
                        yield f"event: keepalive\ndata: {json.dumps({'timestamp': datetime.now().isoformat()})}\n\n"

                    except Exception as step_error:
                        logger.error(f"Error processing step result in stream: {step_error}")
                        yield f"event: error\ndata: {json.dumps({'error': str(step_error)})}\n\n"
                        break

            finally:
                # Clean up subscription
                reasoning_event_stream.unsubscribe(stream_queue)

        except Exception as e:
            logger.error(f"Error in reasoning stream: {e}")
            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        stream_reasoning_steps(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Cache-Control",
        },
    )
