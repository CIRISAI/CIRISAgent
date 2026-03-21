"""
My Data endpoints for DSAR self-service.

Allows authenticated users to:
1. View their hashed agent ID (lens identifier) so they know which traces are theirs
2. View current accord metrics consent/settings status
3. Request deletion of their traces from CIRISLens
4. Update accord metrics settings (trace level, consent)

These endpoints enable GDPR Article 17 (Right to Erasure) self-service
for data sent to the CIRISLens repository via the accord metrics adapter.
"""

import hashlib
import logging
from datetime import datetime, timezone
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..auth import get_current_user
from ..models import StandardResponse, TokenData

logger = logging.getLogger(__name__)

CurrentUserDep = Annotated[TokenData, Depends(get_current_user)]

router = APIRouter(prefix="/my-data", tags=["My Data"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class LensIdentifierResponse(BaseModel):
    """Response containing the user's lens identifier and accord metrics status."""

    agent_id_hash: str = Field(
        ..., description="SHA-256 hash (first 16 hex chars) of agent ID used in CIRISLens traces"
    )
    agent_id: str = Field(..., description="Raw agent ID (so user can verify the hash)")
    consent_given: bool = Field(..., description="Whether accord metrics consent is currently active")
    consent_timestamp: Optional[str] = Field(None, description="When consent was last granted/revoked")
    trace_level: Optional[str] = Field(None, description="Current trace detail level (generic/detailed/full_traces)")
    traces_sent: int = Field(0, description="Approximate number of trace events sent this session")
    endpoint_url: Optional[str] = Field(None, description="CIRISLens endpoint traces are sent to")


class LensDeletionRequest(BaseModel):
    """Request to delete traces from CIRISLens."""

    confirm: bool = Field(
        ...,
        description="Must be true to confirm deletion. This action is irreversible.",
    )
    reason: Optional[str] = Field(
        None,
        description="Optional reason for deletion request",
        max_length=500,
    )


class LensDeletionResponse(BaseModel):
    """Response for a lens trace deletion request."""

    agent_id_hash: str = Field(..., description="The hashed agent ID whose traces were requested for deletion")
    status: str = Field(..., description="Status of the deletion request")
    message: str = Field(..., description="Human-readable status message")
    lens_request_accepted: bool = Field(
        False,
        description="Whether CIRISLens accepted the deletion request",
    )
    local_consent_revoked: bool = Field(
        False,
        description="Whether local accord metrics consent was also revoked",
    )


class AccordSettingsUpdate(BaseModel):
    """Request to update accord metrics settings."""

    trace_level: Optional[str] = Field(
        None,
        description="Trace detail level: generic, detailed, or full_traces",
        pattern="^(generic|detailed|full_traces)$",
    )
    consent_given: Optional[bool] = Field(
        None,
        description="Update consent state. Setting to false stops all trace collection.",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_agent_id_hash(agent_id: str) -> str:
    """Compute the same hash used by AccordMetricsService._anonymize_agent_id.

    Must stay in sync with ciris_adapters/ciris_accord_metrics/services.py.
    """
    return hashlib.sha256(agent_id.encode()).hexdigest()[:16]


def _get_accord_adapter(request: Request) -> Any:
    """Get the accord metrics adapter from app state, or None if not loaded.

    RuntimeAdapterManager stores adapters in loaded_adapters: Dict[str, AdapterInstance]
    where AdapterInstance.adapter is the actual adapter object.

    Note: We check multiple locations since adapter_manager may be stored differently
    depending on how the runtime was initialized.
    """
    adapter_manager = None

    # Try main_runtime_control_service first (matches /v1/adapters endpoint)
    main_runtime_control = getattr(request.app.state, "main_runtime_control_service", None)
    if main_runtime_control:
        adapter_manager = getattr(main_runtime_control, "adapter_manager", None)

    # Fallback to runtime_control_service
    if not adapter_manager:
        runtime_control = getattr(request.app.state, "runtime_control_service", None)
        if runtime_control:
            adapter_manager = getattr(runtime_control, "adapter_manager", None)

    # Fallback to runtime.adapter_manager (legacy path)
    if not adapter_manager:
        runtime = getattr(request.app.state, "runtime", None)
        if runtime:
            adapter_manager = getattr(runtime, "adapter_manager", None)

    if not adapter_manager:
        logger.debug("_get_accord_adapter: No adapter_manager found in any location")
        return None

    # RuntimeAdapterManager.loaded_adapters is Dict[str, AdapterInstance]
    loaded = getattr(adapter_manager, "loaded_adapters", {})
    logger.debug(f"_get_accord_adapter: Found {len(loaded)} loaded adapters: {list(loaded.keys())}")

    for adapter_id, instance in loaded.items():
        # AdapterInstance wraps the actual adapter in .adapter
        adapter = getattr(instance, "adapter", instance)
        type_name = type(adapter).__name__

        # Match by class name or adapter ID
        if "AccordMetrics" in type_name or "accord_metrics" in adapter_id:
            logger.debug(f"_get_accord_adapter: Found AccordMetrics adapter: {adapter_id} (type={type_name})")
            return adapter

    logger.debug(
        f"_get_accord_adapter: No AccordMetrics adapter found among: "
        f"{[(aid, type(getattr(inst, 'adapter', inst)).__name__) for aid, inst in loaded.items()]}"
    )
    return None


def _get_agent_id(request: Request) -> Optional[str]:
    """Get the current agent ID from runtime.

    Checks multiple paths since identity may be populated at different stages.
    """
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime:
        logger.debug("_get_agent_id: No runtime in app.state")
        return None

    # Primary path: runtime.agent_identity.agent_id
    identity = getattr(runtime, "agent_identity", None)
    if identity and hasattr(identity, "agent_id"):
        agent_id = identity.agent_id
        if agent_id is not None:
            return str(agent_id)

    # Fallback: identity_manager.agent_identity
    identity_mgr = getattr(runtime, "identity_manager", None)
    if identity_mgr:
        mgr_identity = getattr(identity_mgr, "agent_identity", None)
        if mgr_identity and hasattr(mgr_identity, "agent_id") and mgr_identity.agent_id:
            return str(mgr_identity.agent_id)

    # Fallback: essential_config.agent_name (always set)
    essential = getattr(runtime, "essential_config", None)
    if essential:
        agent_name = getattr(essential, "agent_name", None)
        if agent_name:
            logger.debug(f"_get_agent_id: Using essential_config.agent_name={agent_name}")
            return agent_name

    # Legacy fallback
    legacy = getattr(runtime, "agent_id", None)
    if legacy:
        return str(legacy)

    logger.warning(
        "_get_agent_id: Could not determine agent_id. "
        f"runtime={type(runtime).__name__}, "
        f"has_identity={identity is not None}, "
        f"has_identity_mgr={identity_mgr is not None}, "
        f"has_essential={essential is not None}"
    )
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/lens-identifier",
    responses={
        404: {"description": "Accord metrics adapter not loaded or agent ID unavailable"},
    },
)
async def get_lens_identifier(
    current_user: CurrentUserDep,
    request: Request,
) -> StandardResponse:
    """
    Get your CIRISLens trace identifier.

    Returns the hashed agent ID that your traces are stored under in CIRISLens,
    along with current consent status and trace settings. Use this identifier
    if you need to request deletion of your traces.

    This is a self-service endpoint — no admin approval needed.
    """
    agent_id = _get_agent_id(request)
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent identity not available. The agent may not be fully initialized.",
        )

    agent_id_hash = _compute_agent_id_hash(agent_id)

    # Get accord metrics adapter status if available
    adapter = _get_accord_adapter(request)
    consent_given = False
    consent_timestamp = None
    trace_level = None
    traces_sent = 0
    endpoint_url = None

    if adapter and hasattr(adapter, "metrics_service"):
        svc = adapter.metrics_service
        metrics = svc.get_metrics()
        consent_given = metrics.get("consent_given", False)
        trace_level = metrics.get("trace_level")
        traces_sent = metrics.get("events_sent", 0)
        consent_timestamp = getattr(adapter, "_consent_timestamp", None)
        endpoint_url = getattr(svc, "_endpoint_url", None)
    elif adapter:
        consent_given = getattr(adapter, "_consent_given", False)
        consent_timestamp = getattr(adapter, "_consent_timestamp", None)

    data = LensIdentifierResponse(
        agent_id_hash=agent_id_hash,
        agent_id=agent_id,
        consent_given=consent_given,
        consent_timestamp=consent_timestamp,
        trace_level=trace_level,
        traces_sent=traces_sent,
        endpoint_url=endpoint_url,
    )

    return StandardResponse(
        success=True,
        data=data.model_dump(),
        message=(
            f"Your traces in CIRISLens are stored under agent_id_hash: {agent_id_hash}. "
            "Use DELETE /v1/my-data/lens-traces to request deletion."
        ),
        metadata={"timestamp": datetime.now(timezone.utc).isoformat()},
    )


@router.delete(
    "/lens-traces",
    responses={
        400: {"description": "Confirmation not provided"},
        404: {"description": "Agent identity or accord adapter not available"},
        502: {"description": "CIRISLens API rejected the deletion request"},
    },
)
async def delete_lens_traces(
    deletion: LensDeletionRequest,
    current_user: CurrentUserDep,
    request: Request,
) -> StandardResponse:
    """
    Request deletion of your traces from CIRISLens.

    This endpoint:
    1. Computes your agent_id_hash from your authenticated identity
    2. Sends a signed deletion request to the CIRISLens API
    3. Revokes local accord metrics consent (stops future trace collection)
    4. Records the request in the audit trail

    The deletion is irreversible. CIRISLens will remove all traces
    associated with your agent_id_hash.

    You must set confirm=true to proceed.
    """
    if not deletion.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must set confirm=true to request trace deletion. This action is irreversible.",
        )

    agent_id = _get_agent_id(request)
    if not agent_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent identity not available.",
        )

    agent_id_hash = _compute_agent_id_hash(agent_id)
    adapter = _get_accord_adapter(request)

    # Step 1: Send deletion request to CIRISLens
    lens_accepted = False
    lens_message = "Accord metrics adapter not loaded — no traces to delete."

    if adapter and hasattr(adapter, "metrics_service"):
        svc = adapter.metrics_service
        lens_accepted, lens_message = await _send_lens_deletion_request(svc, agent_id_hash, deletion.reason)

    # Step 2: Revoke local consent (stops future collection)
    # If the direct lens API call failed, use request_lens_deletion=True so the
    # deletion event is queued in the event buffer and retried on the next flush.
    local_revoked = False
    if adapter:
        adapter.update_consent(False, request_lens_deletion=not lens_accepted)
        local_revoked = True
        logger.info(f"Local accord consent revoked for agent {agent_id_hash} via DSAR self-service")

    # Step 3: Audit trail
    logger.info(
        "DSAR lens deletion requested",
        extra={
            "agent_id_hash": agent_id_hash,
            "reason": deletion.reason or "not provided",
            "lens_accepted": lens_accepted,
            "local_revoked": local_revoked,
            "username": current_user.username,
        },
    )

    data = LensDeletionResponse(
        agent_id_hash=agent_id_hash,
        status="accepted" if lens_accepted else "local_only",
        message=lens_message,
        lens_request_accepted=lens_accepted,
        local_consent_revoked=local_revoked,
    )

    return StandardResponse(
        success=True,
        data=data.model_dump(),
        message=(
            "Deletion request processed. "
            + ("CIRISLens accepted the request. " if lens_accepted else "")
            + ("Local consent revoked — no further traces will be sent." if local_revoked else "")
        ),
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id_hash": agent_id_hash,
        },
    )


@router.get(
    "/accord-settings",
    responses={
        404: {"description": "Accord metrics adapter not loaded"},
    },
)
async def get_accord_settings(
    current_user: CurrentUserDep,
    request: Request,
) -> StandardResponse:
    """
    Get current accord metrics adapter settings.

    Shows consent status, trace detail level, event counters,
    and signing key information.
    """
    adapter = _get_accord_adapter(request)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Accord metrics adapter is not loaded. Load it with --adapter ciris_accord_metrics.",
        )

    agent_id = _get_agent_id(request)
    agent_id_hash = _compute_agent_id_hash(agent_id) if agent_id else "unknown"

    settings: dict[str, Any] = {
        "agent_id_hash": agent_id_hash,
    }

    if hasattr(adapter, "metrics_service"):
        metrics = adapter.metrics_service.get_metrics()
        settings.update(metrics)
        settings["endpoint_url"] = getattr(adapter.metrics_service, "_endpoint_url", None)

    settings["consent_given"] = getattr(adapter, "_consent_given", False)
    settings["consent_timestamp"] = getattr(adapter, "_consent_timestamp", None)

    return StandardResponse(
        success=True,
        data=settings,
        message="Accord metrics settings",
        metadata={"timestamp": datetime.now(timezone.utc).isoformat()},
    )


@router.put(
    "/accord-settings",
    responses={
        400: {"description": "Invalid settings"},
        404: {"description": "Accord metrics adapter not loaded"},
    },
)
async def update_accord_settings(
    settings: AccordSettingsUpdate,
    current_user: CurrentUserDep,
    request: Request,
) -> StandardResponse:
    """
    Update accord metrics adapter settings.

    Allows changing:
    - consent_given: Enable/disable trace collection
    - trace_level: Change detail level (generic/detailed/full_traces)

    Changes take effect immediately for new traces.
    """
    adapter = _get_accord_adapter(request)
    if not adapter:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Accord metrics adapter is not loaded.",
        )

    changes: list[str] = []

    if settings.consent_given is not None:
        adapter.update_consent(settings.consent_given)
        changes.append(f"consent_given={settings.consent_given}")

    if settings.trace_level is not None and hasattr(adapter, "metrics_service"):
        svc = adapter.metrics_service
        from ciris_adapters.ciris_accord_metrics.services import TraceDetailLevel

        try:
            svc._trace_level = TraceDetailLevel(settings.trace_level)
            changes.append(f"trace_level={settings.trace_level}")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid trace_level: {settings.trace_level}",
            )

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No settings provided to update.",
        )

    # Log role instead of username to avoid logging user-controlled data
    logger.info(f"Accord settings updated (role={current_user.role}): {', '.join(changes)}")

    return StandardResponse(
        success=True,
        data={"changes": changes},
        message=f"Settings updated: {', '.join(changes)}",
        metadata={"timestamp": datetime.now(timezone.utc).isoformat()},
    )


# ---------------------------------------------------------------------------
# CIRISLens deletion request sender
# ---------------------------------------------------------------------------


async def _send_lens_deletion_request(
    metrics_service: Any,
    agent_id_hash: str,
    reason: Optional[str],
) -> tuple[bool, str]:
    """Send a deletion request to the CIRISLens API.

    Args:
        metrics_service: The AccordMetricsService instance (has HTTP session + signer)
        agent_id_hash: The hashed agent ID to delete traces for
        reason: Optional reason for deletion

    Returns:
        Tuple of (accepted: bool, message: str)
    """
    import aiohttp

    endpoint_url = getattr(metrics_service, "_endpoint_url", None)
    if not endpoint_url:
        return False, "No CIRISLens endpoint configured."

    session = getattr(metrics_service, "_session", None)
    if not session or session.closed:
        return False, "CIRISLens HTTP session not available. Adapter may not be started."

    signer = getattr(metrics_service, "_signer", None)

    # Build deletion payload
    import json

    payload = {
        "agent_id_hash": agent_id_hash,
        "request_type": "delete_all_traces",
        "reason": reason or "User DSAR self-service request",
        "requested_at": datetime.now(timezone.utc).isoformat(),
    }

    # Sign the request if signer is available
    if signer and hasattr(signer, "has_signing_key") and signer.has_signing_key:
        content_bytes = json.dumps(payload, sort_keys=True).encode()
        try:
            import base64

            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

            private_key = getattr(signer, "_private_key", None)
            if private_key:
                signature = private_key.sign(content_bytes)
                payload["signature"] = base64.b64encode(signature).decode()
                payload["signature_key_id"] = signer.key_id
        except Exception as e:
            logger.warning(f"Could not sign deletion request: {e}")

    url = f"{endpoint_url}/accord/dsar/delete"

    try:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                return True, "CIRISLens accepted the deletion request. Traces will be removed."
            elif response.status == 202:
                return True, "CIRISLens queued the deletion request for processing."
            elif response.status == 404:
                return True, "No traces found for this agent_id_hash in CIRISLens (nothing to delete)."
            else:
                error_text = await response.text()
                logger.error(f"CIRISLens deletion request failed: {response.status} - {error_text}")
                return False, f"CIRISLens returned status {response.status}. Request logged locally for retry."
    except aiohttp.ClientConnectorError:
        return False, "Could not connect to CIRISLens. Deletion request saved locally for retry."
    except Exception as e:
        logger.error(f"Error sending deletion request to CIRISLens: {e}")
        return False, f"Error contacting CIRISLens: {type(e).__name__}. Request saved locally for retry."
