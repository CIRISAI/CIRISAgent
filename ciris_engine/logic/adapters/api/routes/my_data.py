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
import asyncio
import logging
import os
import threading
from datetime import datetime, timedelta, timezone
from typing import Annotated, Any, Dict, Optional, Tuple

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


class CapacityFactor(BaseModel):
    """A single CIRIS capacity factor from CIRISLens scoring."""

    score: float = Field(..., description="Factor score in [0, 1]")
    components: Dict[str, Any] = Field(default_factory=dict, description="Sub-component values")
    trace_count: int = Field(0, description="Number of traces contributing to this score")
    confidence: str = Field("low", description="Confidence level: low | medium | high")


class CapacityFactors(BaseModel):
    """The five CIRIS acronym factors: Consistency, Integrity, Reliability, Incalibration, Steering."""

    C: CapacityFactor = Field(..., description="Core identity / Consistency")
    I_int: CapacityFactor = Field(..., description="Integrity (signing, chain verification)")
    R: CapacityFactor = Field(..., description="Resilience / Reliability (drift stability)")
    I_inc: CapacityFactor = Field(..., description="Incompleteness / Incalibration (humility, deferral)")
    S: CapacityFactor = Field(..., description="Signalling gratitude / Steering (ethical faculties)")


class CapacityMetadata(BaseModel):
    """Metadata describing the scoring window."""

    window_start: Optional[str] = None
    window_end: Optional[str] = None
    total_traces: int = 0
    non_exempt_traces: int = 0


class CapacityResponse(BaseModel):
    """User-facing CIRIS capacity reading for the current agent's template.

    Driven by CIRISLens fleet scoring (composite_score/factors/category) and
    — optionally — a **local** score computed from this occurrence's live
    signals. Presented to the user via the cell visualization; intentionally
    NOT exposed to the agent's own reasoning context to avoid score-chasing
    / self-monitoring anxiety.
    """

    agent_name: str = Field(..., description="Template name this score is for (e.g. Ally, Scout)")
    composite_score: float = Field(..., description="Aggregate fleet CIRIS score in [0, 1]")
    fragility_index: float = Field(..., description="Higher = more fragile; unbounded")
    category: str = Field(..., description="Fleet: high_capacity | healthy | moderate | high_fragility")
    factors: CapacityFactors = Field(..., description="Fleet per-factor breakdown")
    metadata: CapacityMetadata = Field(default_factory=CapacityMetadata)
    cached: bool = Field(False, description="True if served from local cache rather than live lens fetch")
    # Local score — populated when the request uses ?scope=local|both.
    # Null when scope=fleet (default) so the existing client contract is
    # unchanged. The local computation is a CCA approximation
    # (J = k_eff · (1 − ρ) · λ · σ) over fast-to-read runtime signals.
    local_score: Optional[float] = Field(
        None, description="This occurrence's own capacity score in [0, 1]; null when scope=fleet."
    )
    local_category: Optional[str] = Field(
        None, description="This occurrence's category; null when scope=fleet."
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _compute_agent_id_hash_from_signer() -> str:
    """Compute agent_id_hash from the unified signing key.

    This hash is unique per agent instance (based on signing key),
    not per template name. This ensures multiple instances of the same
    template (e.g., 30 "Ally" agents) have distinct hashes.

    Must stay in sync with ciris_adapters/ciris_accord_metrics/services.py.
    """
    try:
        from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

        unified_key = get_unified_signing_key()
        pubkey_bytes = unified_key.public_key_bytes
        return hashlib.sha256(pubkey_bytes).hexdigest()[:16]
    except Exception as e:
        logger.warning(f"Could not compute agent_id_hash from signing key: {e}")
        return "unknown"


def _compute_agent_id_hash(agent_id: str) -> str:
    """DEPRECATED: Legacy hash from agent name.

    New code should use _compute_agent_id_hash_from_signer() or get
    agent_id_hash from the metrics service.

    This is kept for backward compatibility in tests.
    """
    return hashlib.sha256(agent_id.encode()).hexdigest()[:16]


def _get_accord_adapter(request: Request) -> Any:
    """Get the accord metrics adapter from app state, or None if not loaded.

    Searches multiple locations:
    1. adapter_manager.loaded_adapters (dynamically loaded adapters)
    2. runtime.adapters (bootstrap adapters loaded at startup)
    """
    # 1. Check adapter_manager.loaded_adapters (dynamically loaded)
    adapter_manager = None
    for attr in ("main_runtime_control_service", "runtime_control_service"):
        svc = getattr(request.app.state, attr, None)
        if svc:
            adapter_manager = getattr(svc, "adapter_manager", None)
            if adapter_manager:
                break

    if not adapter_manager:
        runtime = getattr(request.app.state, "runtime", None)
        if runtime:
            adapter_manager = getattr(runtime, "adapter_manager", None)

    if adapter_manager:
        loaded = getattr(adapter_manager, "loaded_adapters", {})
        for adapter_id, instance in loaded.items():
            adapter = getattr(instance, "adapter", instance)
            type_name = type(adapter).__name__
            if "AccordMetrics" in type_name or "accord_metrics" in adapter_id:
                logger.debug(f"_get_accord_adapter: Found in adapter_manager: {adapter_id}")
                return adapter

    # 2. Check runtime.adapters (bootstrap adapters)
    runtime = getattr(request.app.state, "runtime", None)
    if runtime:
        for adapter in getattr(runtime, "adapters", []):
            type_name = type(adapter).__name__
            if "AccordMetrics" in type_name:
                logger.debug(f"_get_accord_adapter: Found in runtime.adapters: {type_name}")
                return adapter

    logger.debug("_get_accord_adapter: No AccordMetrics adapter found")
    return None


def _get_agent_id(request: Request) -> Optional[str]:
    """Get the current agent ID from runtime.

    Checks multiple paths since identity may be populated at different stages.
    The signing key (via CIRISVerify) is always available and provides a
    deterministic agent identifier, so this function should never return None.
    """
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime:
        logger.error(
            "_get_agent_id: runtime MISSING from app.state! "
            f"app.state attrs: {[a for a in dir(request.app.state) if not a.startswith('_')]}"
        )
        return None

    # Primary path: runtime.agent_identity.agent_id
    identity = getattr(runtime, "agent_identity", None)
    if identity and hasattr(identity, "agent_id"):
        agent_id = identity.agent_id
        if agent_id is not None:
            logger.debug(f"_get_agent_id: Found via runtime.agent_identity: {agent_id}")
            return str(agent_id)
        else:
            logger.debug("_get_agent_id: runtime.agent_identity exists but agent_id is None")
    else:
        logger.debug(
            f"_get_agent_id: runtime.agent_identity not available "
            f"(identity={identity}, type={type(identity).__name__ if identity else 'None'})"
        )

    # Fallback: identity_manager.agent_identity
    identity_mgr = getattr(runtime, "identity_manager", None)
    if identity_mgr:
        mgr_identity = getattr(identity_mgr, "agent_identity", None)
        if mgr_identity and hasattr(mgr_identity, "agent_id") and mgr_identity.agent_id:
            logger.debug(f"_get_agent_id: Found via identity_manager: {mgr_identity.agent_id}")
            return str(mgr_identity.agent_id)
        else:
            logger.debug(
                f"_get_agent_id: identity_manager exists but no agent_id (mgr_identity={mgr_identity is not None})"
            )

    # Fallback: essential_config.agent_name (always set)
    essential = getattr(runtime, "essential_config", None)
    if essential:
        agent_name = getattr(essential, "agent_name", None)
        if agent_name:
            logger.info(f"_get_agent_id: Using essential_config.agent_name={agent_name}")
            return str(agent_name)
        else:
            logger.debug("_get_agent_id: essential_config exists but agent_name is None/empty")
    else:
        logger.debug("_get_agent_id: no essential_config on runtime")

    # Legacy fallback
    legacy = getattr(runtime, "agent_id", None)
    if legacy:
        logger.debug(f"_get_agent_id: Using legacy runtime.agent_id={legacy}")
        return str(legacy)

    # Signing key fallback: key_id is always available (deterministic from Ed25519 pubkey)
    try:
        from ciris_engine.logic.audit.signing_protocol import get_unified_signing_key

        unified_key = get_unified_signing_key()
        if unified_key.has_key:
            key_id = unified_key.key_id
            logger.info(f"_get_agent_id: Using signing key key_id={key_id}")
            return key_id
        else:
            logger.warning("_get_agent_id: Signing key exists but has_key=False")
    except Exception as e:
        logger.error(f"_get_agent_id: Signing key fallback FAILED: {e}", exc_info=True)

    logger.error(
        "_get_agent_id: ALL fallbacks exhausted! Could not determine agent_id. "
        f"runtime={type(runtime).__name__}, "
        f"has_identity={identity is not None}, "
        f"has_identity_mgr={identity_mgr is not None}, "
        f"has_essential={essential is not None}, "
        f"runtime_attrs={[a for a in dir(runtime) if not a.startswith('_') and 'agent' in a.lower()]}"
    )
    return None


def _update_env_consent(consent_given: bool) -> None:
    """Update CIRIS_ACCORD_METRICS_CONSENT in the .env file.

    This persists consent changes so they survive app restarts.

    Args:
        consent_given: New consent state to persist
    """
    import os
    import re
    from pathlib import Path

    # Find the .env file (same logic as setup wizard)
    config_dir = Path(os.environ.get("CIRIS_CONFIG_DIR", "."))
    env_path = config_dir / ".env"

    if not env_path.exists():
        logger.warning(f"Cannot persist consent: .env file not found at {env_path}")
        return

    # Read current contents
    with open(env_path) as f:
        content = f.read()

    consent_value = "true" if consent_given else "false"
    timestamp = datetime.now(timezone.utc).isoformat()

    # Update CIRIS_ACCORD_METRICS_CONSENT
    if "CIRIS_ACCORD_METRICS_CONSENT=" in content:
        content = re.sub(r"CIRIS_ACCORD_METRICS_CONSENT=\w+", f"CIRIS_ACCORD_METRICS_CONSENT={consent_value}", content)
    else:
        # Add if not present
        content += f"\nCIRIS_ACCORD_METRICS_CONSENT={consent_value}\n"

    # Update CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP
    if "CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP=" in content:
        content = re.sub(
            r"CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP=[^\n]+",
            f"CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP={timestamp}",
            content,
        )
    else:
        content += f"CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP={timestamp}\n"

    # Write back
    with open(env_path, "w") as f:
        f.write(content)

    # Also update the current process environment
    os.environ["CIRIS_ACCORD_METRICS_CONSENT"] = consent_value
    os.environ["CIRIS_ACCORD_METRICS_CONSENT_TIMESTAMP"] = timestamp

    logger.info(f"Updated .env: CIRIS_ACCORD_METRICS_CONSENT={consent_value}")


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
    logger.info("[lens-identifier] Request received, resolving agent_id...")
    agent_id = _get_agent_id(request)
    if not agent_id:
        logger.error(
            "[lens-identifier] agent_id could not be resolved! "
            "This should never happen — the signing key is always available."
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent identity not available. The agent may not be fully initialized.",
        )

    # Get accord metrics adapter status if available
    adapter = _get_accord_adapter(request)
    consent_given = False
    consent_timestamp = None
    trace_level = None
    traces_sent = 0
    endpoint_url = None
    agent_id_hash = None

    if adapter and hasattr(adapter, "metrics_service"):
        svc = adapter.metrics_service
        metrics = svc.get_metrics()
        consent_given = metrics.get("consent_given", False)
        trace_level = metrics.get("trace_level")
        traces_sent = metrics.get("events_sent", 0)
        # Get unique instance hash from metrics service (signing key based)
        agent_id_hash = metrics.get("agent_id_hash")
        consent_timestamp = getattr(adapter, "_consent_timestamp", None)
        endpoint_url = getattr(svc, "_endpoint_url", None)
    elif adapter:
        consent_given = getattr(adapter, "_consent_given", False)
        consent_timestamp = getattr(adapter, "_consent_timestamp", None)

    # Fallback: compute hash directly from signing key if not available from adapter
    if not agent_id_hash:
        agent_id_hash = _compute_agent_id_hash_from_signer()

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

    adapter = _get_accord_adapter(request)

    # Get unique instance hash from metrics service (signing key based)
    agent_id_hash = None
    if adapter and hasattr(adapter, "metrics_service"):
        metrics = adapter.metrics_service.get_metrics()
        agent_id_hash = metrics.get("agent_id_hash")

    # Fallback: compute hash directly from signing key
    if not agent_id_hash:
        agent_id_hash = _compute_agent_id_hash_from_signer()

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

    settings: dict[str, Any] = {
        "agent_name": agent_id,  # Template name for display
    }

    # Get metrics and unique instance hash from metrics service (signing key based)
    if hasattr(adapter, "metrics_service"):
        metrics = adapter.metrics_service.get_metrics()
        settings["agent_id_hash"] = metrics.get("agent_id_hash", "unknown")
        settings.update(metrics)
        settings["endpoint_url"] = getattr(adapter.metrics_service, "_endpoint_url", None)
        # Check if adapter is actually started (has active session)
        svc = adapter.metrics_service
        settings["adapter_started"] = getattr(svc, "_started", False)
        settings["session_active"] = (
            svc._session is not None and not svc._session.closed if hasattr(svc, "_session") else False
        )
    else:
        # Fallback: compute hash directly from signing key
        settings["agent_id_hash"] = _compute_agent_id_hash_from_signer()

    settings["consent_given"] = getattr(adapter, "_consent_given", False)
    settings["consent_timestamp"] = getattr(adapter, "_consent_timestamp", None)

    # Check if services were registered (only happens when consent is given)
    services_registered = (
        len(adapter.get_services_to_register()) > 0 if hasattr(adapter, "get_services_to_register") else False
    )
    settings["services_registered"] = services_registered

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

        # CRITICAL: Persist consent change to .env file so it survives restart
        try:
            _update_env_consent(settings.consent_given)
            logger.info(f"Persisted consent={settings.consent_given} to .env file")
        except Exception as e:
            logger.warning(f"Failed to persist consent to .env: {e}")

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

    # Log only field names (not values) to prevent log injection (CWE-117)
    # The 'changes' list contains strings like "consent_given=true" - extract only the field names
    safe_field_names = [c.split("=")[0] for c in changes if "=" in c]
    logger.info(f"Accord settings updated (role={current_user.role}): {', '.join(safe_field_names)}")

    return StandardResponse(
        success=True,
        data={"changes": changes},
        message=f"Settings updated: {', '.join(changes)}",
        metadata={"timestamp": datetime.now(timezone.utc).isoformat()},
    )


# ---------------------------------------------------------------------------
# CIRIS capacity (ratchet) proxy
# ---------------------------------------------------------------------------
#
# Cache discipline: this route uses its OWN module-level TTL dict rather
# than the shared `ContextEnrichmentCache`. The enrichment cache is tied
# into the agent's context pipeline AND exposed via /v1/system/environment
# (the "Context Enrichment" screen in the UI), so entries there implicitly
# count as "things the agent sees about itself". Capacity is explicitly
# user-facing only — the agent must never read its own score (Goodhart /
# self-monitoring). Isolating to a local cache keeps the anti-Goodhart
# gate structural, not incidental.
#
# Pattern mirrors `CirisBillingProvider._cache` (dict[str, tuple[value,
# expiry]] + manual expiry check) — the standard local-TTL idiom in this
# repo.


_CAPACITY_CACHE_TTL_SECONDS = 900.0  # 15 min — matches the 7-day lens scoring window cadence
_CAPACITY_CACHE: Dict[str, Tuple[Dict[str, Any], datetime]] = {}
_CAPACITY_CACHE_LOCK = threading.Lock()


def _capacity_cache_get(template: str) -> Optional[Dict[str, Any]]:
    """Return the cached lens payload for `template` if still fresh, else None.

    Thread-safe and side-effect-free except for evicting expired entries.
    """
    now = datetime.now(timezone.utc)
    with _CAPACITY_CACHE_LOCK:
        hit = _CAPACITY_CACHE.get(template)
        if hit is None:
            return None
        payload, expiry = hit
        if now >= expiry:
            # Evict expired entry so the dict doesn't grow unbounded over
            # long-running deployments (one per template, but still).
            _CAPACITY_CACHE.pop(template, None)
            return None
        return payload


def _capacity_cache_set(template: str, payload: Dict[str, Any]) -> None:
    """Store `payload` for `template` with a TTL-based expiry."""
    from datetime import timedelta

    expiry = datetime.now(timezone.utc) + timedelta(seconds=_CAPACITY_CACHE_TTL_SECONDS)
    with _CAPACITY_CACHE_LOCK:
        _CAPACITY_CACHE[template] = (payload, expiry)


def _capacity_cache_clear() -> None:
    """Clear the capacity cache — used by tests to get clean starts."""
    with _CAPACITY_CACHE_LOCK:
        _CAPACITY_CACHE.clear()


def _capacity_base_url() -> str:
    """Base URL for CIRISLens capacity scoring endpoints.

    Defaults to the public production lens. Same env var as the accord metrics
    adapter so operators have a single knob to redirect both streams.
    """
    return os.getenv(
        "CIRIS_ACCORD_METRICS_ENDPOINT",
        "https://lens.ciris-services-1.ai/lens-api/api/v1",
    ).rstrip("/")


async def _compute_local_capacity(request: Request) -> Tuple[float, str]:
    """Compute this occurrence's local CIRIS capacity as a score in [0, 1].

    Implements the CCA formula (Coherence Collapse Analysis, Moore 2026):

        J = k_eff · (1 − ρ) · λ · σ

    with runtime signals for each term:

      * ``k_eff`` = fraction of healthy services from the service registry
        (the 22-service microarchitecture is the ρ↓ intervention per
        Table 5, so we approximate k directly rather than track ρ).
      * ``(1 − ρ)`` = 1.0 constant. Modular services are architecturally
        independent; refining this requires cross-service covariance
        tracking which we don't have yet.
      * ``λ`` = strictness — 1.0 if conscience + wise_authority are both
        present AND healthy, else 0.7. Tracks whether the ethical
        faculties are actively enforcing constraints.
      * ``σ`` = sustainability, now grounded in ``handler_action_task_complete``
        audit records in the last hour. Each successful task completion
        is a "positive moment" per the Accord; emission rate above the
        target threshold = σ at full; silence = σ at floor. Matches the
        "gratitude token system" per Table 5 (CIRIS Agent mapping).

    Returns (score_in_unit_interval, category_label). Async because the
    audit service's ``query_audit_trail`` is async; the whole call is
    still ~ms-scale (one bounded-row query + an in-memory registry walk).

    Anti-Goodhart guardrail unchanged: never fed to the agent's own
    context, never cached in ``ContextEnrichmentCache``.
    """
    try:
        svc_registry = getattr(request.app.state, "service_registry", None)
        if svc_registry is None:
            return 1.0, "healthy"

        # --- k_eff + λ probes (service registry walk) ----------------------
        services = svc_registry.get_all_services() if hasattr(svc_registry, "get_all_services") else []
        total = max(1, len(services))

        async def _probe_healthy(s: Any) -> bool:
            try:
                is_healthy = getattr(s, "is_healthy", None)
                if callable(is_healthy):
                    result = is_healthy()
                    if hasattr(result, "__await__"):
                        return bool(await result)
                    return bool(result)
                return bool(getattr(s, "healthy", True))
            except Exception:
                return False

        health_results = await asyncio.gather(
            *(_probe_healthy(s) for s in services), return_exceptions=False
        )
        healthy = sum(1 for h in health_results if h)
        k_eff_frac = healthy / total

        # λ: strictness is active when the Wise Authority service is
        # healthy. The H3ERE Conscience Module is baked into the thought
        # processor itself (not a standalone service), so "agent running"
        # implies conscience is on — we only need to verify WA is
        # present + healthy for the deferral channel.
        lam = 0.7
        for s, h in zip(services, health_results):
            if not h:
                continue
            class_name = type(s).__name__.lower()
            svc_name = getattr(s, "service_name", "").lower()
            if "wiseauthority" in class_name or "wise_authority" in svc_name:
                lam = 1.0
                break

        # --- σ from recent task_complete positive moments ------------------
        sigma = await _sigma_from_positive_moments(request)

        rho_complement = 1.0  # 22-service microarchitecture; no ρ measurement yet
        j = k_eff_frac * rho_complement * lam * sigma
        j = max(0.0, min(1.0, j))

        category = (
            "high_capacity" if j >= 0.90 else "healthy" if j >= 0.75 else "moderate" if j >= 0.55 else "high_fragility"
        )
        return j, category
    except Exception as e:
        logger.debug(f"[capacity] local compute failed, returning neutral: {type(e).__name__}: {e}")
        return 1.0, "healthy"


def _count_recent_task_completes_sqlite(hours: int = 1) -> int:
    """Count ``task_complete`` events in the audit SQLite DB over the last
    ``hours`` hours. Synchronous; called via run_in_executor.

    The graph-memory audit store (``audit_service.query_audit_trail``) does
    not receive handler-action events — those land in the signed audit log
    at ``data/ciris_audit.db`` (``/v1/audit/entries`` queries all three
    sources and merges). For σ we only need the cheap rate signal, so we
    query SQLite directly with a COUNT.
    """
    import sqlite3

    try:
        from ciris_engine.logic.utils.path_resolution import get_data_dir

        db_path = str(get_data_dir() / "ciris_audit.db")
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2.0) as conn:
            cur = conn.execute(
                "SELECT COUNT(*) FROM audit_log WHERE event_type = ? AND event_timestamp >= ?",
                ("task_complete", since),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
    except Exception as e:
        logger.debug(f"[capacity.sigma] SQLite audit count failed: {type(e).__name__}: {e}")
        return 0


async def _sigma_from_positive_moments(request: Request) -> float:
    """σ (sustainability) proxied by the ``task_complete`` rate.

    The Accord models task completion as a *positive moment* — the system
    closed a loop cleanly, which is the CIRIS "gratitude token" signal
    and the closest cheap proxy we have for the CCA σ term (maintenance
    capacity / sustainable operation).

    Mapping over the last hour:
      * 0 completions   → σ = 0.30 (floor — idle is not fragile)
      * 1 completion    → σ ≈ 0.53
      * ≥ 3 completions → σ = 1.00 (target rate)

    Linear ramp. One bounded COUNT on the audit SQLite DB, ~ms, run in
    the default executor so we never block the event loop. Degrades to
    the floor on any error.
    """
    try:
        loop = asyncio.get_event_loop()
        successes = await loop.run_in_executor(None, _count_recent_task_completes_sqlite, 1)
        logger.debug(f"[capacity.sigma] {successes} task_complete(s) in last 1h")
        floor = 0.30
        target = 3
        return max(floor, min(1.0, floor + (1.0 - floor) * (successes / target)))
    except Exception as e:
        logger.debug(f"[capacity.sigma] probe failed, returning floor: {type(e).__name__}: {e}")
        return 0.30


async def _fetch_capacity_from_lens(template: str) -> Dict[str, Any]:
    """Call CIRISLens for a template's capacity record. Raises on non-200."""
    import aiohttp

    url = f"{_capacity_base_url()}/scoring/capacity/{template}"
    timeout = aiohttp.ClientTimeout(total=10.0)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                body = await resp.text()
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail=f"CIRISLens returned {resp.status} for capacity/{template}: {body[:200]}",
                )
            return await resp.json()  # type: ignore[no-any-return]


@router.get(
    "/capacity",
    responses={
        404: {"description": "Agent template unavailable"},
        502: {"description": "CIRISLens unreachable or returned an error"},
    },
)
async def get_capacity(
    current_user: CurrentUserDep,
    request: Request,
    scope: str = "fleet",
) -> StandardResponse:
    """
    Get the current CIRIS capacity (C/I_int/R/I_inc/S) for this agent's template.

    Query parameters:
      * ``scope=fleet`` (default) — template-aggregate score from CIRISLens.
        This is the "Ally-everywhere" score across all instances of the
        same agent template. Existing behaviour, unchanged contract.
      * ``scope=local`` — this occurrence's own score, computed from live
        runtime signals using a minimal CCA approximation
        (J = k_eff · (1 − ρ) · λ · σ, Moore 2026). No lens call.
      * ``scope=both`` — returns both; ``composite_score`` is fleet,
        ``local_score`` is this occurrence. Preferred for the cell-viz
        CapacityBadge so the user sees ``● 0.92 · 0.90``.

    Data flows:
        CIRISLens fleet scoring
            -> proxy fetch here (cached 15 min in a route-local TTL dict)
            -> KMP client /v1/my-data/capacity
            -> cell visualization ambient state (user-facing)

    Anti-Goodhart guardrails (structural, not incidental):
      - NOT registered as a context enrichment tool.
      - NOT stored in the shared ContextEnrichmentCache — that cache is
        also surfaced via /v1/system/environment ("Context Enrichment"
        screen), which would leak the agent's own score into its own
        view of its environment. Uses a module-local TTL dict instead.
      - Local score is ALSO never written anywhere the agent can read.

    The signed audit history is the real coherence ratchet; this is just
    the viewing angle for the human.
    """
    scope_norm = (scope or "fleet").strip().lower()
    if scope_norm not in {"fleet", "local", "both"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="scope must be one of: fleet, local, both",
        )

    template = _get_agent_id(request)
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Agent template unavailable — runtime not fully initialized.",
        )

    # --- Local-only: skip the lens hop entirely -----------------------------
    if scope_norm == "local":
        local_j, local_cat = await _compute_local_capacity(request)
        neutral_factor = CapacityFactor(score=local_j, components={}, trace_count=0, confidence="low")
        parsed = CapacityResponse(
            agent_name=template,
            composite_score=local_j,
            fragility_index=0.0,
            category=local_cat,
            factors=CapacityFactors(
                C=neutral_factor, I_int=neutral_factor, R=neutral_factor, I_inc=neutral_factor, S=neutral_factor
            ),
            metadata=CapacityMetadata(),
            cached=False,
            local_score=local_j,
            local_category=local_cat,
        )
        return StandardResponse(
            success=True,
            data=parsed.model_dump(),
            message=f"Local CIRIS capacity: {local_cat} (score={local_j:.3f})",
            metadata={"timestamp": datetime.now(timezone.utc).isoformat(), "cached": False, "scope": "local"},
        )

    # --- Fleet or both: fetch lens payload (cached) -------------------------
    served_from_cache = True
    payload = _capacity_cache_get(template)
    if payload is None:
        served_from_cache = False
        try:
            payload = await _fetch_capacity_from_lens(template)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"[capacity] Lens fetch failed for template={template}: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Could not reach CIRISLens: {type(e).__name__}",
            )
        _capacity_cache_set(template, payload)

    local_score: Optional[float] = None
    local_cat: Optional[str] = None
    if scope_norm == "both":
        local_score, local_cat = await _compute_local_capacity(request)

    try:
        parsed = CapacityResponse(
            agent_name=payload.get("agent_name", template),
            composite_score=float(payload.get("composite_score", 0.0)),
            fragility_index=float(payload.get("fragility_index", 0.0)),
            category=str(payload.get("category", "moderate")),
            factors=CapacityFactors(**payload["factors"]),
            metadata=CapacityMetadata(**payload.get("metadata", {})),
            cached=served_from_cache,
            local_score=local_score,
            local_category=local_cat,
        )
    except Exception as e:
        logger.error(f"[capacity] Could not parse lens payload for {template}: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"CIRISLens returned an unexpected shape: {type(e).__name__}",
        )

    return StandardResponse(
        success=True,
        data=parsed.model_dump(),
        message=f"CIRIS capacity for template {template}: {parsed.category} (score={parsed.composite_score:.3f})",
        metadata={
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cached": served_from_cache,
            "scope": scope_norm,
        },
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

    requested_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "agent_id_hash": agent_id_hash,
        "request_type": "delete_all_traces",
        "reason": reason or "User DSAR self-service request",
        "requested_at": requested_at,
    }

    # Sign the request if signer is available
    # Signature must be over canonical JSON of: {agent_id_hash, request_type, requested_at}
    if signer and hasattr(signer, "has_signing_key") and signer.has_signing_key:
        try:
            # Build canonical payload for signing (only required fields, alphabetically sorted)
            canonical_payload = {
                "agent_id_hash": agent_id_hash,
                "request_type": "delete_all_traces",
                "requested_at": requested_at,
            }
            content_bytes = json.dumps(canonical_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

            # Use the unified signing key from the signer
            unified_key = getattr(signer, "_unified_key", None)
            if unified_key is None:
                # Try to load it
                signer._ensure_unified_key()
                unified_key = getattr(signer, "_unified_key", None)

            if unified_key and hasattr(unified_key, "sign_base64"):
                payload["signature"] = unified_key.sign_base64(content_bytes)
                payload["signature_key_id"] = signer.key_id
                logger.info(f"Signed deletion request with key {signer.key_id}")
            else:
                logger.warning("Could not sign deletion request: unified key not available")
        except Exception as e:
            logger.warning(f"Could not sign deletion request: {e}")

    url = f"{endpoint_url}/accord/dsar/delete"

    try:
        async with session.post(url, json=payload) as response:
            if response.status == 200:
                logger.info(f"CIRISLens deletion request ACCEPTED (200) for agent {agent_id_hash}")
                return True, "CIRISLens accepted the deletion request. Traces will be removed."
            elif response.status == 202:
                logger.info(f"CIRISLens deletion request QUEUED (202) for agent {agent_id_hash}")
                return True, "CIRISLens queued the deletion request for processing."
            elif response.status == 404:
                logger.info(f"CIRISLens deletion request: no traces found (404) for agent {agent_id_hash}")
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
