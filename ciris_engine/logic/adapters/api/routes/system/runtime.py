"""
Runtime control endpoints.

Provides control over agent runtime behavior and cognitive state transitions.
"""

import asyncio
import json
import logging
from typing import Annotated, Dict, Optional, Tuple

from fastapi import APIRouter, Body, Depends, HTTPException, Request

from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.services.resources_core import MemoryReleaseResult

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
    CanonicalReceipt,
    RuntimeAction,
    RuntimeControlResponse,
    StateTransitionRequest,
    StateTransitionResponse,
    TraceDeliveryReceipt,
)

logger = logging.getLogger(__name__)

# Type aliases for dependency injection (S8410 compliance)
AuthAdminDep = Annotated[AuthContext, Depends(require_admin)]
RuntimeActionDep = Annotated[RuntimeAction, Body(...)]
StateTransitionRequestDep = Annotated[StateTransitionRequest, Body(...)]

router = APIRouter()

# Valid cognitive states for transition
VALID_COGNITIVE_STATES = {"WORK", "DREAM", "PLAY", "SOLITUDE"}


# THE ACCESSOR'S SPELLING IS NOT OURS TO PIN. `delivery_receipt` is a Rust
# accessor in a wheel we depend on but do not build, its payload has no schema
# we can import, and the one canonical we can reach is two releases behind and
# 404s the route — so the field names cannot be confirmed against a live
# response. Reading a single guessed key would project `null` for every
# canonical while the signed answer sat right there in the payload, and the
# gate would report "unknown" forever with nothing to show for it.
#
# So: accept the spellings upstream is known to use, take the first one
# actually present, and keep `raw_json` verbatim beside the projection. If all
# of these are wrong, the raw payload in the response and in the gate log is
# the evidence that says so — a projection that can be checked, rather than one
# that fails silently.
_HOLD_KEYS = ("newest_authored_held", "holds_trace", "holds_newest")
_URL_SOURCE_KEYS = ("url_source", "url_from", "source")


def _first_bool(*sources_and_keys: object) -> Optional[bool]:
    """First real bool for any of `keys`, scanning `sources` in order.

    Called as _first_bool(row, canonical, keys): the per-agent row wins over the
    canonical-level aggregate, because the row is about us and the aggregate is
    about everyone.
    """
    *sources, keys = sources_and_keys
    assert isinstance(keys, tuple)
    for src in sources:
        if not isinstance(src, dict):
            continue
        for k in keys:
            v = src.get(k)
            if isinstance(v, bool):
                return v
    return None


def _first_str(source: object, keys: Tuple[str, ...]) -> Optional[str]:
    if not isinstance(source, dict):
        return None
    for k in keys:
        v = source.get(k)
        if isinstance(v, str) and v:
            return v
    return None


@router.get(
    "/runtime/delivery-receipt",
    responses={
        503: {"description": "This build has no delivery_receipt accessor (ciris-server < 0.5.208)"},
    },
)
async def delivery_receipt(
    request: Request,
    auth: AuthAdminDep,
) -> SuccessResponse[TraceDeliveryReceipt]:
    """Did our traces actually land? Ask the canonicals, not ourselves.

    `/v1/telemetry/*` and the node's `delivery_status()` report the PRODUCER's
    preconditions — rooted, KEX present, envelopes sent. All three can be green
    while nothing was stored at the far end, and that gap is why the
    five-platform gate's trace rung was keyed on a counter the node did not
    expose over HTTP (CIRISServer#487). This returns the RECEIVER's answer:
    each canonical signs its receipt, and our node verifies it against its own
    directory, checks the key's standing at the instant of the ask, and accepts
    only a receipt bound to exactly what it asked.

    Read it ONCE, at the end of a run — it costs an HTTP round-trip per
    canonical. GET is still right: it takes nothing and changes nothing here;
    the cost is why it is not folded into a status poll.

    Requires ADMIN role.
    """
    from ciris_engine.logic.runtime.edge_runtime import read_delivery_receipt

    agent_hash: Optional[str] = None
    try:
        from ciris_engine.logic.adapters.api.routes.my_data import _compute_agent_id_hash_from_signer

        computed = _compute_agent_id_hash_from_signer()
        # The helper answers "unknown" rather than raising when the engine is not
        # wired; passing that through as a hash would ask about an agent that
        # does not exist, so drop back to discovery instead.
        agent_hash = computed if computed and computed != "unknown" else None
    except Exception:  # noqa: BLE001 — discovery is the documented fallback
        agent_hash = None

    # OFF THE EVENT LOOP. The accessor makes a synchronous HTTP round-trip per
    # canonical, and a slow or unreachable one would otherwise park the whole
    # FastAPI loop thread for the cumulative timeout — a diagnostic that stalls
    # the API it is diagnosing. asyncio.to_thread keeps the async boundary the
    # adapter promises.
    raw = await asyncio.to_thread(read_delivery_receipt, agent_id_hash=agent_hash)
    if raw is None:
        raise HTTPException(
            status_code=503,
            detail="delivery_receipt unavailable — ciris-server < 0.5.208 or the node is not folded in this process",
        )

    try:
        payload = json.loads(raw)
    except Exception:  # noqa: BLE001
        payload = {}

    verdict = payload.get("verdict") or {}
    canonicals = []
    for c in payload.get("canonicals") or []:
        if not isinstance(c, dict):
            continue

        # WHICH AGENT'S ROW? A canonical serves many agents. When we know our
        # own hash, take the row that names it. When we do NOT, only a SOLE row
        # can be about us — picking the first of several would make the
        # behind-vs-never-landed diagnosis depend on upstream list ordering,
        # which is a coin flip wearing a boolean's clothes. Several rows and no
        # hash is genuinely unknown, and says so.
        agent_row: Optional[Dict[str, object]] = None
        agents = [a for a in (c.get("agents") or []) if isinstance(a, dict)]
        if agent_hash is not None:
            agent_row = next((a for a in agents if a.get("agent_id_hash") == agent_hash), None)
        elif len(agents) == 1:
            agent_row = agents[0]

        canonicals.append(
            CanonicalReceipt(
                key_id=c.get("key_id"),
                holds_newest=_first_bool(agent_row, c, _HOLD_KEYS),
                shipped_any=_first_bool(agent_row, c, ("shipped_any",)),
                url=c.get("url"),
                url_source=_first_str(c, _URL_SOURCE_KEYS),
                error=c.get("error"),
            )
        )

    return SuccessResponse(
        data=TraceDeliveryReceipt(
            available=True,
            held_by_every_answering_canonical=verdict.get("newest_authored_held_by_every_answering_canonical"),
            agent_id_hash=agent_hash,
            canonicals_unreachable=verdict.get("canonicals_unreachable"),
            canonicals_unverified=verdict.get("canonicals_unverified"),
            canonicals_partial=verdict.get("canonicals_partial"),
            canonicals_answered=verdict.get("canonicals_answered"),
            discovery_incomplete=verdict.get("discovery_incomplete"),
            identity_unavailable=verdict.get("identity_unavailable"),
            canonicals=canonicals,
            error=payload.get("error"),
            raw_json=raw,
        )
    )


@router.post(
    "/runtime/memory/release",
    responses={
        500: {"description": "Memory release failed"},
        503: {"description": "Resource monitor not available"},
    },
)
async def release_memory(
    request: Request,
    auth: AuthAdminDep,
) -> SuccessResponse[MemoryReleaseResult]:
    """
    Hand freed memory back to the operating system, now.

    The same path the resource monitor takes when it crosses its own memory
    threshold, and the path the phones take on an OS memory warning -- exposed
    so an operator can trigger it and so the five-platform gate can prove the
    chain works on every platform, not just the one it was measured on.

    Requires ADMIN role.
    """
    monitor = getattr(request.app.state, "resource_monitor", None)
    if monitor is None:
        runtime = getattr(request.app.state, "runtime", None)
        monitor = getattr(runtime, "resource_monitor_service", None)
    if monitor is None:
        raise HTTPException(status_code=503, detail="Resource monitor not available")
    try:
        result = await monitor.release_memory(trigger="api:admin")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return SuccessResponse(data=result)


@router.post(
    "/runtime/{action}",
    responses={
        400: {"description": "Invalid runtime action"},
        500: {"description": "Runtime control operation failed"},
        503: {"description": "Runtime control service not available"},
    },
)
async def control_runtime(
    action: str,
    request: Request,
    body: RuntimeActionDep,
    auth: AuthAdminDep,
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


@router.post(
    "/state/transition",
    responses={
        400: {"description": "Invalid target state"},
        500: {"description": "State transition failed"},
        503: {"description": "Runtime control service not available or state transition not supported"},
    },
)
async def transition_cognitive_state(
    request: Request,
    body: StateTransitionRequestDep,
    auth: AuthAdminDep,
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
