"""
Adapter configuration workflow endpoints.

Provides interactive configuration workflow for adapters including OAuth callbacks.
"""

import html
import logging
import uuid
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response

from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.runtime.enums import ServiceType

from ...dependencies.auth import AuthContext, require_admin, require_observer
from .helpers import get_adapter_config_service
from .schemas import (
    ConfigurationCompleteRequest,
    ConfigurationCompleteResponse,
    ConfigurationSessionResponse,
    ConfigurationStatusResponse,
    StepExecutionRequest,
    StepExecutionResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ============================================================================
# Configuration Session Helpers
# ============================================================================


async def _get_runtime_control_service_for_adapter_load(request: Request) -> Any:
    """Get RuntimeControlService for adapter loading (returns None if unavailable)."""
    runtime_control_service = getattr(request.app.state, "main_runtime_control_service", None)
    if runtime_control_service:
        return runtime_control_service

    runtime_control_service = getattr(request.app.state, "runtime_control_service", None)
    if runtime_control_service:
        return runtime_control_service

    service_registry = getattr(request.app.state, "service_registry", None)
    if service_registry:
        return await service_registry.get_service(handler="api", service_type=ServiceType.RUNTIME_CONTROL)

    return None


async def _load_adapter_after_config(request: Request, session: Any, persist: bool = False) -> str:
    """Load adapter after configuration and return status message.

    Args:
        request: FastAPI request object
        session: Configuration session with collected_config
        persist: Whether to persist the adapter config for auto-load on restart
    """
    runtime_control_service = await _get_runtime_control_service_for_adapter_load(request)
    if not runtime_control_service:
        logger.warning("[COMPLETE_CONFIG] RuntimeControlService not available, adapter not loaded")
        return " - runtime control service unavailable"

    logger.info("[COMPLETE_CONFIG] Loading adapter via RuntimeControlService.load_adapter")
    adapter_config = dict(session.collected_config)
    # Include persist flag in config so RuntimeAdapterManager handles persistence
    adapter_config["persist"] = persist
    adapter_id = f"{session.adapter_type}_{uuid.uuid4().hex[:8]}"

    load_result = await runtime_control_service.load_adapter(
        adapter_type=session.adapter_type,
        adapter_id=adapter_id,
        config=adapter_config,
    )

    if load_result.success:
        logger.info(f"[COMPLETE_CONFIG] Adapter loaded successfully: {adapter_id}")
        return f" - adapter '{adapter_id}' loaded and started"
    else:
        logger.error(f"[COMPLETE_CONFIG] Adapter load failed: {load_result.error}")
        return f" - adapter load failed: {load_result.error}"


# ============================================================================
# Endpoints
# ============================================================================


@router.post("/adapters/{adapter_type}/configure/start", response_model=SuccessResponse[ConfigurationSessionResponse])
async def start_adapter_configuration(
    adapter_type: str,
    request: Request,
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[ConfigurationSessionResponse]:
    """
    Start interactive configuration session for an adapter.

    Creates a new configuration session and returns the session ID along with
    information about the first step in the workflow.

    Requires ADMIN role.
    """
    try:
        config_service = get_adapter_config_service(request)

        # Start the session
        session = await config_service.start_session(adapter_type=adapter_type, user_id=auth.user_id)

        # Get manifest to access steps
        manifest = config_service._adapter_manifests.get(adapter_type)
        if not manifest:
            raise HTTPException(status_code=404, detail=f"Adapter '{adapter_type}' not found")

        # Get current step
        current_step = manifest.steps[0] if manifest.steps else None

        response = ConfigurationSessionResponse(
            session_id=session.session_id,
            adapter_type=session.adapter_type,
            status=session.status.value,
            current_step_index=session.current_step_index,
            current_step=current_step,
            total_steps=len(manifest.steps),
            created_at=session.created_at,
        )

        return SuccessResponse(data=response)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting configuration session: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/configure/{session_id}", response_model=SuccessResponse[ConfigurationStatusResponse])
async def get_configuration_status(
    session_id: str,
    request: Request,
    auth: AuthContext = Depends(require_observer),
) -> SuccessResponse[ConfigurationStatusResponse]:
    """
    Get current status of a configuration session.

    Returns complete session state including current step, collected configuration,
    and session status.

    Requires OBSERVER role.
    """
    try:
        config_service = get_adapter_config_service(request)
        session = config_service.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

        # Get manifest to access steps
        manifest = config_service._adapter_manifests.get(session.adapter_type)
        if not manifest:
            raise HTTPException(status_code=500, detail=f"Manifest for '{session.adapter_type}' not found")

        # Get current step
        current_step = None
        if session.current_step_index < len(manifest.steps):
            current_step = manifest.steps[session.current_step_index]

        response = ConfigurationStatusResponse(
            session_id=session.session_id,
            adapter_type=session.adapter_type,
            status=session.status.value,
            current_step_index=session.current_step_index,
            current_step=current_step,
            total_steps=len(manifest.steps),
            collected_config=session.collected_config,
            created_at=session.created_at,
            updated_at=session.updated_at,
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting configuration status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/adapters/configure/{session_id}/step", response_model=SuccessResponse[StepExecutionResponse])
async def execute_configuration_step(
    session_id: str,
    request: Request,
    body: StepExecutionRequest = Body(...),
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[StepExecutionResponse]:
    """
    Execute the current configuration step.

    The body contains step-specific data such as user selections, input values,
    or OAuth callback data. The step type determines what data is expected.

    Requires ADMIN role.
    """
    try:
        config_service = get_adapter_config_service(request)

        # Execute the step
        result = await config_service.execute_step(session_id, body.step_data)

        response = StepExecutionResponse(
            step_id=result.step_id,
            success=result.success,
            data=result.data,
            next_step_index=result.next_step_index,
            error=result.error,
            awaiting_callback=result.awaiting_callback,
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing configuration step: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/configure/{session_id}/status")
async def get_session_status(
    session_id: str,
    request: Request,
) -> SuccessResponse[ConfigurationSessionResponse]:
    """
    Get the current status of a configuration session.

    Useful for polling after OAuth callback to check if authentication completed.
    """
    try:
        config_service = get_adapter_config_service(request)
        session = config_service.get_session(session_id)

        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        # Get adapter steps from the adapter manifest (InteractiveConfiguration)
        current_step = None
        total_steps = 0
        manifest = config_service._adapter_manifests.get(session.adapter_type)
        if manifest and manifest.steps:
            steps = manifest.steps
            total_steps = len(steps)
            if session.current_step_index < len(steps):
                # Use the ConfigurationStep directly from the manifest
                current_step = steps[session.current_step_index]

        response = ConfigurationSessionResponse(
            session_id=session.session_id,
            adapter_type=session.adapter_type,
            status=session.status.value,
            current_step_index=session.current_step_index,
            current_step=current_step,
            total_steps=total_steps,
            created_at=session.created_at,
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting session status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/configure/{session_id}/oauth/callback")
async def oauth_callback(
    session_id: str,
    code: str,
    state: str,
    request: Request,
) -> Response:
    """
    Handle OAuth callback from external service.

    This endpoint is called by OAuth providers after user authorization.
    It processes the authorization code and advances the configuration workflow.
    Returns HTML that redirects back to the app or shows success message.

    No authentication required (OAuth state validation provides security).
    """
    logger.info("=" * 60)
    logger.info("[OAUTH CALLBACK] *** CALLBACK RECEIVED ***")
    logger.info(f"[OAUTH CALLBACK] Full URL: {request.url}")
    logger.info(f"[OAUTH CALLBACK] Path: {request.url.path}")
    logger.info(f"[OAUTH CALLBACK] session_id: {session_id}")
    logger.info(f"[OAUTH CALLBACK] state: {state}")
    logger.info(f"[OAUTH CALLBACK] code length: {len(code)}")
    logger.info(
        f"[OAUTH CALLBACK] code preview: {code[:20]}..." if len(code) > 20 else f"[OAUTH CALLBACK] code: {code}"
    )
    logger.info(f"[OAUTH CALLBACK] Headers: {dict(request.headers)}")
    logger.info("=" * 60)
    try:
        config_service = get_adapter_config_service(request)

        # Verify session exists and state matches
        session = config_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        if state != session_id:
            raise HTTPException(status_code=400, detail="Invalid OAuth state")

        # Execute the OAuth callback step
        result = await config_service.execute_step(session_id, {"code": code, "state": state})

        if not result.success:
            error_html = f"""<!DOCTYPE html>
<html>
<head><title>OAuth Failed</title></head>
<body style="font-family: sans-serif; text-align: center; padding: 50px;">
    <h1 style="color: #d32f2f;">Authentication Failed</h1>
    <p>{html.escape(result.error or "OAuth callback failed")}</p>
    <p>Please close this window and try again in the app.</p>
</body>
</html>"""
            return Response(content=error_html, media_type="text/html")

        # Return HTML that tells user to go back to app
        success_html = f"""<!DOCTYPE html>
<html>
<head>
    <title>OAuth Success</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="font-family: sans-serif; text-align: center; padding: 50px; background: #f5f5f5;">
    <div style="background: white; padding: 40px; border-radius: 10px; max-width: 400px; margin: 0 auto; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
        <h1 style="color: #4caf50; margin-bottom: 20px;">Connected!</h1>
        <p style="color: #666; font-size: 18px;">Authentication successful.</p>
        <p style="color: #888; margin-top: 20px;">You can close this window and return to the CIRIS app.</p>
        <p style="color: #aaa; font-size: 12px; margin-top: 30px;">Session: {html.escape(session_id[:8])}...</p>
    </div>
</body>
</html>"""
        return Response(content=success_html, media_type="text/html")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error handling OAuth callback: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/adapters/oauth/callback")
async def oauth_deeplink_callback(
    code: str,
    state: str,
    request: Request,
    provider: Optional[str] = None,
    source: Optional[str] = None,
) -> SuccessResponse[Dict[str, Any]]:
    """
    Handle OAuth callback forwarded from Android deep link (ciris://oauth/callback).

    This endpoint receives OAuth callbacks that were forwarded from OAuthCallbackActivity
    on Android. The Android app uses a deep link (ciris://oauth/callback) to receive
    the OAuth redirect from the system browser, then forwards to this endpoint.

    This is a generic endpoint that works for any OAuth2 provider (Home Assistant,
    Discord, Google, Microsoft, Reddit, etc.) - the state parameter contains the
    session_id which identifies the configuration session.
    """
    logger.info("=" * 60)
    logger.info("[OAUTH DEEPLINK CALLBACK] *** FORWARDED CALLBACK RECEIVED ***")
    logger.info(f"[OAUTH DEEPLINK CALLBACK] Full URL: {request.url}")
    logger.info(f"[OAUTH DEEPLINK CALLBACK] state (session_id): {state}")
    logger.info(f"[OAUTH DEEPLINK CALLBACK] provider: {provider}")
    logger.info(f"[OAUTH DEEPLINK CALLBACK] source: {source}")
    logger.info(f"[OAUTH DEEPLINK CALLBACK] code length: {len(code)}")
    logger.info("=" * 60)

    try:
        config_service = get_adapter_config_service(request)

        # The state parameter IS the session_id
        session_id = state

        # Handle provider-prefixed state (e.g., "ha:actual_session_id")
        if ":" in state:
            parts = state.split(":", 1)
            if len(parts) == 2 and len(parts[0]) < 20:
                # Looks like "provider:session_id"
                provider = provider or parts[0]
                session_id = parts[1]
                logger.info(f"[OAUTH DEEPLINK CALLBACK] Extracted provider={provider}, session_id={session_id}")

        # Verify session exists
        session = config_service.get_session(session_id)
        if not session:
            logger.error(f"[OAUTH DEEPLINK CALLBACK] Session not found: {session_id}")
            raise HTTPException(status_code=404, detail=f"Session not found: {session_id}")

        # Execute the OAuth callback step
        result = await config_service.execute_step(session_id, {"code": code, "state": state})

        if not result.success:
            logger.error(f"[OAUTH DEEPLINK CALLBACK] OAuth step failed: {result.error}")
            raise HTTPException(status_code=400, detail=result.error or "OAuth callback failed")

        logger.info(f"[OAUTH DEEPLINK CALLBACK] Successfully processed OAuth callback for session {session_id}")

        return SuccessResponse(
            data={
                "session_id": session_id,
                "success": True,
                "message": "OAuth callback processed successfully",
                "next_step": result.next_step_index,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[OAUTH DEEPLINK CALLBACK] Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/adapters/configure/{session_id}/complete", response_model=SuccessResponse[ConfigurationCompleteResponse])
async def complete_configuration(
    session_id: str,
    request: Request,
    body: ConfigurationCompleteRequest = Body(default=ConfigurationCompleteRequest()),
    auth: AuthContext = Depends(require_admin),
) -> SuccessResponse[ConfigurationCompleteResponse]:
    """
    Finalize and apply the configuration.

    Validates the collected configuration and applies it to the adapter.
    Once completed, the adapter should be ready to use with the new configuration.

    If `persist` is True, the configuration will be saved for automatic loading
    on startup, allowing the adapter to be automatically configured when the
    system restarts.

    Requires ADMIN role.
    """
    try:
        adapter_config_service = get_adapter_config_service(request)

        session = adapter_config_service.get_session(session_id)
        if not session:
            raise HTTPException(status_code=404, detail=f"Session '{session_id}' not found")

        success = await adapter_config_service.complete_session(session_id)
        persisted = False
        message = ""

        if success:
            message = f"Configuration applied successfully for {session.adapter_type}"
            logger.info(f"[COMPLETE_CONFIG] Config applied, attempting to start adapter for {session.adapter_type}")

            try:
                # Pass persist flag so RuntimeAdapterManager handles persistence
                message += await _load_adapter_after_config(request, session, persist=body.persist)
                persisted = body.persist  # Persistence is handled by RuntimeAdapterManager
                if persisted:
                    message += " and persisted for startup"
            except Exception as e:
                logger.error(f"Error loading adapter after config: {e}", exc_info=True)
                message += f" - adapter load error: {e}"
        else:
            message = f"Configuration validation or application failed for {session.adapter_type}"

        response = ConfigurationCompleteResponse(
            success=success,
            adapter_type=session.adapter_type,
            message=message,
            applied_config=session.collected_config if success else {},
            persisted=persisted,
        )

        return SuccessResponse(data=response)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error completing configuration: {e}")
        raise HTTPException(status_code=500, detail=str(e))
