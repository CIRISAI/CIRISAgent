"""
System health and time endpoints.

Provides health status and time synchronization information.
"""

import logging
from datetime import datetime, timezone
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from ciris_engine.constants import CIRIS_VERSION
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.api.telemetry import TimeSyncStatus

from ...constants import ERROR_TIME_SERVICE_NOT_AVAILABLE
from ...dependencies.auth import AuthContext, require_observer
from .helpers import (
    check_initialization_status,
    check_processor_health,
    collect_service_health,
    determine_overall_status,
    get_cognitive_state_safe,
    get_current_time,
    get_system_uptime,
)
from .schemas import (
    FederationAddressResponse,
    StartupStatusResponse,
    SystemHealthResponse,
    SystemTimeResponse,
    SystemWarning,
)

logger = logging.getLogger(__name__)

# Type alias for authenticated observer dependency (S8410 compliance)
AuthObserverDep = Annotated[AuthContext, Depends(require_observer)]

router = APIRouter()


async def _check_provider_health(service_provider: object) -> bool:
    """Check if a single LLM provider is healthy.

    Args:
        service_provider: A ServiceProvider wrapper from the registry.

    Returns:
        True if the provider is healthy, False otherwise.
    """
    # Get the actual service instance from the ServiceProvider wrapper
    service = getattr(service_provider, "instance", service_provider)
    provider_name = getattr(service_provider, "name", str(service_provider))

    try:
        if hasattr(service, "is_healthy"):
            return bool(await service.is_healthy())
        if hasattr(service, "healthy"):
            return bool(service.healthy)
    except Exception as e:
        logger.debug(f"Provider '{provider_name}' health check failed: {e}")

    return False


async def check_llm_availability() -> tuple[bool, list[SystemWarning]]:
    """Check LLM provider availability and return (has_working_llm, warnings)."""
    from ciris_engine.logic.registries.base import get_global_registry
    from ciris_engine.schemas.runtime.enums import ServiceType

    registry = get_global_registry()
    llm_providers = registry._services.get(ServiceType.LLM, [])

    if not llm_providers:
        logger.debug("No LLM providers registered - degraded_mode=True")
        return False, [
            SystemWarning(
                code="no_llm_provider",
                message="No LLM provider configured. Add a provider in LLM Settings to enable AI features.",
                severity="error",
                action_url="/settings/llm",
            )
        ]

    # Check if any provider is healthy
    for service_provider in llm_providers:
        if await _check_provider_health(service_provider):
            return True, []

    logger.debug(f"All {len(llm_providers)} providers unhealthy - degraded_mode=True")
    return False, [
        SystemWarning(
            code="llm_providers_unhealthy",
            message="All LLM providers are currently unavailable. Check your provider settings or network connection.",
            severity="warning",
            action_url="/settings/llm",
        )
    ]


async def _adapter_reauth_warnings(request: Request) -> list[SystemWarning]:
    """Warnings for adapters needing re-authentication."""
    adapter_manager = getattr(request.app.state, "adapter_manager", None)
    if not adapter_manager:
        return []
    try:
        adapter_statuses = await adapter_manager.get_all_adapter_status()
    except Exception as e:
        logger.debug(f"Could not check adapter reauth status: {e}")
        return []
    return [
        SystemWarning(
            code="adapter_needs_reauth",
            message=f"Adapter '{status.adapter_id}' needs re-authentication: {status.reauth_reason or 'Token expired'}",
            severity="warning",
            action_url=f"/settings/adapters/{status.adapter_id}",
        )
        for status in adapter_statuses
        if status.needs_reauth
    ]


def _hardware_trust_warnings(request: Request) -> list[SystemWarning]:
    """Hardware-trust degradation (D18 / CIRISAgent#814).

    CIRISVerify produces hardware_trust_degraded on the attestation result
    (e.g. CVE-affected SoC auto-downgrade); the agent only surfaces it.
    Operators previously had to read the verifier advisory list directly.
    """
    auth_service = getattr(request.app.state, "authentication_service", None)
    if auth_service is None or not hasattr(auth_service, "get_cached_attestation"):
        return []
    try:
        attestation = auth_service.get_cached_attestation(allow_stale=True)
        if attestation is not None and getattr(attestation, "hardware_trust_degraded", False):
            return [
                SystemWarning(
                    code="hardware_trust_degraded",
                    message=getattr(attestation, "trust_degradation_reason", None)
                    or "Hardware security trust is degraded",
                    severity="warning",
                    action_url="/settings/trust",
                )
            ]
    except Exception as e:
        logger.debug(f"Could not check hardware trust degradation: {e}")
    return []



def _adapter_load_failure_warnings(request: Request) -> list[SystemWarning]:
    """Configured adapters that never loaded (CIRISAgent#1057).

    SELF-DIAGNOSING FOR CIRISMANAGER. Manager GENERATES the adapter config, so
    it is the component that can fix a stale name — but it had no way to learn
    the name was stale. A fleet ran for several releases with `sync` and
    `ciris_covenant_metrics` (renamed to ciris_accord_metrics) failing to import
    on EVERY agent, one agent serving with none of its configured adapters, and
    every health check reporting `healthy`. The only evidence was a log line
    inside the container.

    Two distinct codes, because they need two different fixes:

      adapters_config_stale  — the module does not exist. The config names an
                               adapter that was renamed or removed. Manager can
                               reconcile this itself.
      adapters_failed_to_load — the adapter exists but blew up starting. A code
                               or credentials problem; a human looks at it.

    Severity escalates to `error` when NOTHING a config asked for is running,
    which is the state that must never again read as healthy.
    """
    runtime = getattr(request.app.state, "runtime", None)
    failures = list(getattr(runtime, "adapter_load_failures", []) or []) if runtime else []
    if not failures:
        return []

    live = len(getattr(runtime, "adapters", []) or [])
    # Communication adapters the operator asked for, ignoring the internal ones
    # (ciris_verify / wallet / ciris_accord_metrics) that always auto-load — an
    # agent with only those is not talking to anyone.
    _INTERNAL = {"ciris_verify", "wallet", "ciris_accord_metrics"}
    external_live = len(
        [a for a in (getattr(runtime, "adapters", []) or []) if getattr(a, "adapter_type", "") not in _INTERNAL]
    )
    severity = "error" if external_live == 0 else "warning"

    out: list[SystemWarning] = []
    stale = [f for f in failures if getattr(f, "is_missing_module", False)]
    broken = [f for f in failures if not getattr(f, "is_missing_module", False)]

    if stale:
        names = ", ".join(sorted({f.adapter_type for f in stale}))
        out.append(
            SystemWarning(
                code="adapters_config_stale",
                message=(
                    f"Configured adapter(s) do not exist and were skipped: {names}. "
                    f"{external_live} of {external_live + len(failures)} configured adapters are running. "
                    "The config names an adapter that was renamed or removed — regenerate it."
                ),
                severity=severity,
                action_url="/settings/adapters",
            )
        )
    if broken:
        names = ", ".join(sorted({f"{f.adapter_type} ({f.error_type})" for f in broken}))
        out.append(
            SystemWarning(
                code="adapters_failed_to_load",
                message=f"Configured adapter(s) failed to start: {names}",
                severity=severity,
                action_url="/settings/adapters",
            )
        )
    return out


def _occurrence_warnings(request: Request) -> list[SystemWarning]:
    """Report the occurrence identity this process actually resolved (#1048).

    scout2 ran as occurrence 002 while declaring itself single-occurrence, and
    nothing outside the container could see the contradiction. Manager assigns
    the occurrence id, so it is exactly who needs to know when the agent
    disagrees about what it was assigned.

    Emitted at `info` when consistent — this is a STATE REPORT, not only an
    alarm. Manager can reconcile what it assigned against what the agent
    resolved without waiting for something to break.
    """
    try:
        from ciris_engine.logic.utils.occurrence_utils import (
            DEFAULT_OCCURRENCE_ID,
            get_current_occurrence_id,
            is_multi_occurrence_deployment,
        )

        occ = get_current_occurrence_id()
        multi = is_multi_occurrence_deployment()
    except Exception as e:  # pragma: no cover - defensive
        logger.debug(f"Could not resolve occurrence info: {e}")
        return []

    if occ == DEFAULT_OCCURRENCE_ID and not multi:
        return []
    return [
        SystemWarning(
            code="occurrence_identity",
            message=f"occurrence_id={occ} multi_occurrence={multi}",
            severity="info",
            action_url=None,
        )
    ]


def _claim_persistence_warnings(request: Request) -> list[SystemWarning]:
    """Shared-task claims that reported success but left no row (#1057).

    THE ONE THAT COST THE MOST TO FIND. datum logged a successful claim on every
    boot while its store had no such row, span in WAKEUP to round 66 finding no
    thoughts, and reported healthy throughout. Detecting it required someone to
    inventory the database by hand.

    try_claim_shared_task now reads the row back and records a failure here when
    it is absent, so the condition announces itself to CIRISManager instead of
    waiting to be discovered.
    """
    try:
        from ciris_engine.logic.persistence.models.tasks import get_shared_claim_failures

        failures = get_shared_claim_failures()
    except Exception as e:
        logger.debug(f"Could not read shared claim failures: {e}")
        return []
    if not failures:
        return []
    ids = ", ".join(sorted({str(f.get("task_id")) for f in failures})[:5])
    return [
        SystemWarning(
            code="shared_claim_not_persisted",
            message=(
                f"{len(failures)} shared-task claim(s) reported success but no row is present: {ids}. "
                "The agent cannot obtain work and will spin. Verify it reads the same database it writes."
            ),
            severity="error",
            action_url="/settings/tasks",
        )
    ]


def _stale_shared_task_warnings(request: Request) -> list[SystemWarning]:
    """A shared task stuck ACTIVE across days (#1018, seen again in #1057).

    datum booted with SHUTDOWN_SHARED_20260731 still ACTIVE 17 days later,
    `updated_at` never moved from `created_at`, and it was the newest row in the
    store. Nothing surfaced that. A shared task is claimed by one occurrence on
    behalf of all of them, so one that never settles is a fleet-level fact and
    belongs in the fleet-level health surface.
    """
    try:
        from ciris_engine.logic.persistence.models.tasks import get_all_tasks

        tasks = get_all_tasks(occurrence_id="__shared__") or []
    except Exception as e:
        logger.debug(f"Could not check shared tasks: {e}")
        return []

    now = datetime.now(timezone.utc)
    stale = []
    for task in tasks:
        status = getattr(task, "status", None)
        status_val = getattr(status, "value", status)
        if status_val not in ("active", "pending", "processing"):
            continue
        updated = getattr(task, "updated_at", None) or getattr(task, "created_at", None)
        if not updated:
            continue
        try:
            ts = datetime.fromisoformat(str(updated).replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        age_hours = (now - ts).total_seconds() / 3600.0
        if age_hours >= 24:
            stale.append((getattr(task, "task_id", "?"), age_hours))

    if not stale:
        return []
    worst = max(h for _, h in stale)
    names = ", ".join(sorted(tid for tid, _ in stale)[:5])
    return [
        SystemWarning(
            code="shared_task_stranded",
            message=(
                f"{len(stale)} shared task(s) unsettled for over 24h (oldest {worst / 24:.1f} days): {names}. "
                "A shared task is claimed on behalf of every occurrence; one that never settles blocks them all."
            ),
            severity="error",
            action_url="/settings/tasks",
        )
    ]


async def collect_system_warnings(request: Request) -> tuple[bool, list[SystemWarning]]:
    """Collect system-level warnings and check degraded mode.

    Returns (degraded_mode, warnings) tuple. degraded_mode is True when NO
    working LLM is available.
    """
    has_working_llm, llm_warnings = await check_llm_availability()
    warnings = llm_warnings.copy()
    warnings.extend(await _adapter_reauth_warnings(request))
    warnings.extend(_hardware_trust_warnings(request))
    # #1057 — fleet conditions that previously lived only in container logs.
    # Manager polls this endpoint; anything it must act on has to be here.
    warnings.extend(_adapter_load_failure_warnings(request))
    warnings.extend(_occurrence_warnings(request))
    warnings.extend(_stale_shared_task_warnings(request))
    warnings.extend(_claim_persistence_warnings(request))
    return not has_working_llm, warnings


@router.get("/health")
async def get_system_health(request: Request) -> SuccessResponse[SystemHealthResponse]:
    """
    Overall system health.

    Returns comprehensive system health including service status,
    initialization state, current cognitive state, and system warnings.
    """
    # Get basic system info
    uptime_seconds = get_system_uptime(request)
    current_time = get_current_time(request)
    cognitive_state = get_cognitive_state_safe(request)
    init_complete = check_initialization_status(request)

    # Collect service health data
    services = await collect_service_health(request)
    processor_healthy = await check_processor_health(request)

    # Collect system warnings and check degraded mode
    degraded_mode, warnings = await collect_system_warnings(request)

    # Determine overall system status
    status = determine_overall_status(init_complete, processor_healthy, services)

    response = SystemHealthResponse(
        status=status,
        version=CIRIS_VERSION,
        uptime_seconds=uptime_seconds,
        services=services,
        initialization_complete=init_complete,
        cognitive_state=cognitive_state,
        timestamp=current_time,
        warnings=warnings,
        degraded_mode=degraded_mode,
    )

    return SuccessResponse(data=response)


@router.get("/federation")
async def get_federation_address(_auth: AuthObserverDep) -> SuccessResponse[FederationAddressResponse]:
    """
    Local agent's federation address (CIRISEdge signer_key_id).

    Returned to operator-facing UI so the user knows which key_id to share
    with peers seeding `federation_keys` rows for them. When Edge runtime
    is disabled (CIRIS_EDGE_DISABLED=true) or not yet initialized, returns
    `available=false` with null key_id.
    """
    from ciris_engine.logic.runtime import edge_runtime

    if not edge_runtime.is_available():
        return SuccessResponse(
            data=FederationAddressResponse(available=False, key_id=None, edge_version=None)
        )

    key_id = edge_runtime.get_federation_address()
    edge_version: Optional[str] = None
    try:
        edge = edge_runtime.get_edge()
        edge_version = edge.crate_version()
    except Exception as e:
        logger.debug("Edge crate_version() unavailable: %s", e)

    return SuccessResponse(
        data=FederationAddressResponse(
            available=key_id is not None,
            key_id=key_id,
            edge_version=edge_version,
        )
    )


@router.get("/startup-status")
async def get_startup_status() -> SuccessResponse[StartupStatusResponse]:
    """
    Startup progress for desktop client polling.

    Returns service initialization count and phase.
    Unauthenticated - available during boot before auth is ready.
    """
    from ciris_engine.logic.runtime.startup_logging import (
        SERVICE_NAMES,
        TOTAL_CORE_SERVICES,
        get_api_status,
        get_api_status_history,
        get_current_phase,
        get_services_started,
    )

    services_started = get_services_started()
    started_names = [SERVICE_NAMES[i - 1] for i in sorted(services_started) if 1 <= i <= len(SERVICE_NAMES)]

    return SuccessResponse(
        data=StartupStatusResponse(
            phase=get_current_phase(),
            services_online=len(services_started),
            services_total=TOTAL_CORE_SERVICES,
            service_names=started_names,
            api_status=get_api_status(),
            api_status_history=get_api_status_history(),
        )
    )


@router.get(
    "/time",
    responses={
        500: {"description": "Failed to get time information"},
        503: {"description": "Time service not available"},
    },
)
async def get_system_time(
    request: Request,
    auth: AuthObserverDep,
) -> SuccessResponse[SystemTimeResponse]:
    """
    System time information.

    Returns both system time (host OS) and agent time (TimeService),
    along with synchronization status.
    """
    # Get time service
    time_service: Optional[TimeServiceProtocol] = getattr(request.app.state, "time_service", None)
    if not time_service:
        raise HTTPException(status_code=503, detail=ERROR_TIME_SERVICE_NOT_AVAILABLE)

    try:
        # Get system time (actual OS time)
        system_time = datetime.now(timezone.utc)

        # Get agent time (from TimeService)
        agent_time = time_service.now()

        # Calculate uptime
        start_time = getattr(time_service, "_start_time", None)
        if not start_time:
            start_time = agent_time
            uptime_seconds = 0.0
        else:
            uptime_seconds = (agent_time - start_time).total_seconds()

        # Calculate time sync status
        is_mocked = getattr(time_service, "_mock_time", None) is not None
        time_diff_ms = (agent_time - system_time).total_seconds() * 1000

        time_sync = TimeSyncStatus(
            synchronized=not is_mocked and abs(time_diff_ms) < 1000,  # Within 1 second
            drift_ms=time_diff_ms,
            last_sync=getattr(time_service, "_last_sync", agent_time),
            sync_source="mock" if is_mocked else "system",
        )

        response = SystemTimeResponse(
            system_time=system_time, agent_time=agent_time, uptime_seconds=uptime_seconds, time_sync=time_sync
        )

        return SuccessResponse(data=response)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get time information: {str(e)}")
