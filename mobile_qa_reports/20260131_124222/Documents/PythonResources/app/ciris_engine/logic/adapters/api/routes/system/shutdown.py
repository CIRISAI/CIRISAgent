"""
Shutdown endpoints.

Provides graceful shutdown functionality including local shutdown for mobile apps.
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from starlette.responses import JSONResponse

from ciris_engine.schemas.api.responses import SuccessResponse

from ...dependencies.auth import AuthContext, require_admin
from .helpers import (
    RESUME_TIMEOUT_SECONDS,
    audit_shutdown_request,
    build_shutdown_reason,
    check_shutdown_already_requested,
    execute_shutdown,
    get_server_state,
    get_shutdown_service,
    initiate_force_shutdown,
    is_localhost_request,
    validate_shutdown_request,
)
from .schemas import ShutdownRequest, ShutdownResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/shutdown", response_model=SuccessResponse[ShutdownResponse])
async def shutdown_system(
    body: ShutdownRequest, request: Request, auth: AuthContext = Depends(require_admin)
) -> SuccessResponse[ShutdownResponse]:
    """
    Graceful shutdown.

    Initiates graceful system shutdown. Requires confirmation
    flag to prevent accidental shutdowns.

    Requires ADMIN role.
    """
    try:
        # Validate and get required services
        validate_shutdown_request(body)
        shutdown_service, runtime = get_shutdown_service(request)

        # Check if already shutting down
        check_shutdown_already_requested(shutdown_service)

        # Build and sanitize shutdown reason
        safe_reason = build_shutdown_reason(body.reason, body.force, auth.user_id)

        # Log shutdown request
        logger.warning(f"SHUTDOWN requested: {safe_reason}")

        # Audit shutdown request
        severity = "high" if body.force else "warning"
        await audit_shutdown_request(request, body.force, auth.user_id, auth.role.value, severity, safe_reason)

        # Execute shutdown
        await execute_shutdown(shutdown_service, runtime, body.force, safe_reason)

        # Create response
        response = ShutdownResponse(
            status="initiated",
            message=f"System shutdown initiated: {safe_reason}",
            shutdown_initiated=True,
            timestamp=datetime.now(timezone.utc),
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating shutdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _check_resume_blocking(runtime: object, state_info: Dict[str, Any]) -> Optional[Response]:
    """Check if resume is in progress and should block shutdown.

    Args:
        runtime: The runtime instance
        state_info: Current server state info dict

    Returns:
        JSONResponse if shutdown should be blocked, None if OK to proceed
    """
    resume_in_progress = getattr(runtime, "_resume_in_progress", False)
    if not resume_in_progress:
        return None

    resume_started_at = getattr(runtime, "_resume_started_at", None)
    resume_elapsed = (time.time() - resume_started_at) if resume_started_at else 0

    if resume_elapsed >= RESUME_TIMEOUT_SECONDS:
        # Resume stuck - allow shutdown
        logger.warning(
            f"[LOCAL_SHUTDOWN] Resume exceeded timeout ({resume_elapsed:.1f}s > "
            f"{RESUME_TIMEOUT_SECONDS}s) - treating as stuck, allowing shutdown"
        )
        return None

    # Resume actively happening - ask caller to retry
    remaining = RESUME_TIMEOUT_SECONDS - resume_elapsed
    retry_after_ms = min(2000, int(remaining * 1000))

    logger.warning(
        f"[LOCAL_SHUTDOWN] Rejected (409) - resume in progress for {resume_elapsed:.1f}s, "
        f"retry in {retry_after_ms}ms (timeout at {RESUME_TIMEOUT_SECONDS}s)"
    )
    return JSONResponse(
        status_code=409,
        content={
            "status": "busy",
            "reason": f"Resume from first-run in progress ({resume_elapsed:.1f}s elapsed)",
            "retry_after_ms": retry_after_ms,
            "resume_timeout_seconds": RESUME_TIMEOUT_SECONDS,
            **state_info,
        },
    )


def _check_shutdown_already_in_progress(runtime: object, state_info: Dict[str, Any]) -> Optional[Response]:
    """Check if shutdown is already in progress.

    Args:
        runtime: The runtime instance
        state_info: Current server state info dict

    Returns:
        JSONResponse if shutdown already in progress, None otherwise
    """
    shutdown_service = getattr(runtime, "shutdown_service", None)
    shutdown_in_progress = getattr(runtime, "_shutdown_in_progress", False)

    is_shutting_down = shutdown_in_progress or (shutdown_service and shutdown_service.is_shutdown_requested())

    if not is_shutting_down:
        return None

    existing_reason = shutdown_service.get_shutdown_reason() if shutdown_service else "unknown"
    logger.info(f"[LOCAL_SHUTDOWN] Shutdown already in progress: {existing_reason}")
    return JSONResponse(
        status_code=202,
        content={
            "status": "accepted",
            "reason": f"Shutdown already in progress: {existing_reason}",
            **state_info,
        },
    )


@router.post("/local-shutdown", response_model=SuccessResponse[ShutdownResponse])
async def local_shutdown(request: Request) -> Response:
    """
    Localhost-only shutdown endpoint (no authentication required).

    This endpoint is designed for Android/mobile apps where:
    - App data may be cleared (losing auth tokens)
    - Previous Python process may still be running
    - Need to gracefully shut down before starting new instance

    Security: Only accepts requests from localhost (127.0.0.1, ::1).
    This is safe because only processes on the same device can call it.

    Response codes for SmartStartup negotiation:
    - 200: Shutdown initiated successfully
    - 202: Shutdown already in progress
    - 403: Not localhost (security rejection)
    - 409: Resume in progress, retry later (with retry_after_ms)
    - 503: Server not ready
    """
    # Verify request is from localhost
    client_host = request.client.host if request.client else "unknown"
    if not is_localhost_request(request):
        logger.warning(f"[LOCAL_SHUTDOWN] Rejected from non-local client: {client_host}")
        raise HTTPException(status_code=403, detail="This endpoint only accepts requests from localhost")

    logger.info(f"[LOCAL_SHUTDOWN] Request received from {client_host}")

    # Get runtime
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime:
        logger.warning("[LOCAL_SHUTDOWN] Runtime not available (503)")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "reason": "Runtime not available",
                "retry_after_ms": 1000,
                "server_state": "STARTING",
            },
        )

    state_info = get_server_state(runtime)
    logger.info(f"[LOCAL_SHUTDOWN] Server state: {state_info}")

    # Check if resume is blocking shutdown
    resume_response = _check_resume_blocking(runtime, state_info)
    if resume_response:
        return resume_response

    # Check if already shutting down
    shutdown_response = _check_shutdown_already_in_progress(runtime, state_info)
    if shutdown_response:
        return shutdown_response

    # Verify shutdown service is available
    shutdown_service = getattr(runtime, "shutdown_service", None)
    if not shutdown_service:
        logger.warning("[LOCAL_SHUTDOWN] Shutdown service not available (503)")
        return JSONResponse(
            status_code=503,
            content={
                "status": "error",
                "reason": "Shutdown service not available",
                "retry_after_ms": 1000,
                **state_info,
            },
        )

    # Initiate shutdown
    reason = "Local shutdown requested (Android SmartStartup)"
    logger.warning(f"[LOCAL_SHUTDOWN] Initiating IMMEDIATE shutdown: {reason}")
    initiate_force_shutdown(runtime, reason)

    logger.info("[LOCAL_SHUTDOWN] Shutdown initiated successfully (200)")
    return JSONResponse(
        status_code=200,
        content={
            "status": "accepted",
            "reason": reason,
            **state_info,
        },
    )
