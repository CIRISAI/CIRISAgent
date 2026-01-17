"""
Runtime control endpoints.

Provides control over agent runtime behavior and cognitive state transitions.
"""

import logging

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from ciris_engine.schemas.api.responses import SuccessResponse

from ...constants import ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE
from ...dependencies.auth import AuthContext, require_admin
from .helpers import (
    create_final_response,
    create_pause_response,
    execute_pause_action,
    execute_resume_action,
    execute_state_action,
    extract_pipeline_state_info,
    get_cognitive_state,
    get_runtime_control_service,
    validate_runtime_action,
)
from .schemas import (
    RuntimeAction,
    RuntimeControlResponse,
    StateTransitionRequest,
    StateTransitionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()

# Valid cognitive states for transition
VALID_COGNITIVE_STATES = {"WORK", "DREAM", "PLAY", "SOLITUDE"}


@router.post("/runtime/{action}", response_model=SuccessResponse[RuntimeControlResponse])
async def control_runtime(
    action: str, request: Request, body: RuntimeAction = Body(...), auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[RuntimeControlResponse]:
    """
    Runtime control actions.

    Control agent runtime behavior. Valid actions:
    - pause: Pause message processing
    - resume: Resume message processing
    - state: Get current runtime state

    Requires ADMIN role.
    """
    try:
        runtime_control = get_runtime_control_service(request)
        validate_runtime_action(action)

        # Execute action
        if action == "pause":
            success = await execute_pause_action(runtime_control, body.reason)
            current_step, current_step_schema, pipeline_state = extract_pipeline_state_info(request)
            result = create_pause_response(success, current_step, current_step_schema, pipeline_state)
        elif action == "resume":
            result = await execute_resume_action(runtime_control)
        elif action == "state":
            result = await execute_state_action(runtime_control)
            return SuccessResponse(data=result)

        # Get cognitive state and create final response
        cognitive_state = get_cognitive_state(request)
        response = create_final_response(result, cognitive_state)

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/state/transition", response_model=SuccessResponse[StateTransitionResponse])
async def transition_cognitive_state(
    request: Request,
    body: StateTransitionRequest = Body(...),
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[StateTransitionResponse]:
    """
    Request a cognitive state transition.

    Transitions the agent to a different cognitive state (WORK, DREAM, PLAY, SOLITUDE).
    Valid transitions depend on the current state:
    - From WORK: Can transition to DREAM, PLAY, or SOLITUDE
    - From PLAY: Can transition to WORK or SOLITUDE
    - From SOLITUDE: Can transition to WORK
    - From DREAM: Typically transitions back to WORK when complete

    Requires ADMIN role.
    """
    try:
        target_state = body.target_state.upper()
        logger.info(f"[STATE_TRANSITION] Request received: target_state={target_state}, reason={body.reason}")

        # Validate target state
        if target_state not in VALID_COGNITIVE_STATES:
            logger.error(f"[STATE_TRANSITION] FAIL: Invalid target state '{target_state}'")
            raise HTTPException(
                status_code=400,
                detail=f"Invalid target state '{target_state}'. Must be one of: {', '.join(sorted(VALID_COGNITIVE_STATES))}",
            )

        # Get current state
        previous_state = get_cognitive_state(request)
        logger.info(f"[STATE_TRANSITION] Current state: {previous_state}")

        # Get runtime control service - FAIL FAST with detailed logging
        runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
        if not runtime_control:
            runtime_control = getattr(request.app.state, "runtime_control_service", None)

        if not runtime_control:
            logger.error("[STATE_TRANSITION] FAIL: No runtime control service available in app.state")
            logger.error(f"[STATE_TRANSITION] Available app.state attrs: {dir(request.app.state)}")
            raise HTTPException(status_code=503, detail=ERROR_RUNTIME_CONTROL_SERVICE_NOT_AVAILABLE)

        # Log service type for debugging
        service_type = type(runtime_control).__name__
        service_module = type(runtime_control).__module__
        logger.info(f"[STATE_TRANSITION] Runtime control service: {service_type} from {service_module}")

        # Check if request_state_transition is available - FAIL LOUD
        has_method = hasattr(runtime_control, "request_state_transition")
        logger.info(f"[STATE_TRANSITION] Has request_state_transition method: {has_method}")

        if not has_method:
            available_methods = [m for m in dir(runtime_control) if not m.startswith("_")]
            logger.error(f"[STATE_TRANSITION] FAIL: Service {service_type} missing request_state_transition")
            logger.error(f"[STATE_TRANSITION] Available methods: {available_methods}")
            raise HTTPException(
                status_code=503,
                detail=f"State transition not supported by {service_type}. Missing request_state_transition method.",
            )

        # Request the transition
        reason = body.reason or f"Requested via API from {previous_state or 'UNKNOWN'}"
        logger.info(f"[STATE_TRANSITION] Calling request_state_transition({target_state}, {reason})")
        success = await runtime_control.request_state_transition(target_state, reason)
        logger.info(f"[STATE_TRANSITION] Transition result: success={success}")

        # Get current state after transition attempt
        current_state = get_cognitive_state(request) or target_state
        logger.info(f"[STATE_TRANSITION] Post-transition state: {current_state}")

        if success:
            message = f"Transition to {target_state} initiated successfully"
        else:
            message = f"Transition to {target_state} could not be initiated"

        return SuccessResponse(
            data=StateTransitionResponse(
                success=success,
                message=message,
                previous_state=previous_state,
                current_state=current_state,
            )
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[STATE_TRANSITION] FAIL: Unexpected error: {type(e).__name__}: {e}")
        import traceback

        logger.error(f"[STATE_TRANSITION] Traceback:\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))
