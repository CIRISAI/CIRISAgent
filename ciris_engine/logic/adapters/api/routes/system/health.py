"""
System health and time endpoints.

Provides health status and time synchronization information.
"""

import logging
import re
from datetime import datetime, timezone
from typing import Annotated, Optional, Sequence

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from ciris_engine.constants import CIRIS_VERSION
from ciris_engine.logic.utils.localization import get_preferred_language, get_string
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.api.auth import UserRole
from ciris_engine.schemas.api.responses import SuccessResponse
from ciris_engine.schemas.api.telemetry import TimeSyncStatus

from ...constants import ERROR_TIME_SERVICE_NOT_AVAILABLE
from ...dependencies.auth import AuthContext, optional_auth, require_observer
from ...services.auth_service import APIAuthService
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


def _describe_provider_failures(providers: Sequence[object]) -> str:
    """One short clause naming each provider and its own last complaint.

    The provider already told us what is wrong — "Invalid API Key", "The model
    `default` does not exist" — and every layer between there and the user
    replaced it with a generic sentence. This carries it through.

    Best-effort by construction: a provider that exposes no last-error simply
    contributes its name, which is still more than "all providers".
    """
    parts: list[str] = []
    for sp in providers[:3]:
        name = getattr(sp, "name", None) or "provider"
        service = getattr(sp, "instance", sp)
        reason = ""
        for attr in ("last_error", "_last_error", "last_failure_reason"):
            val = getattr(service, attr, None)
            if val:
                reason = str(val).strip().splitlines()[0][:120]
                break
        parts.append(f"{name}: {reason}" if reason else str(name))
    if not parts:
        return ""
    return f"({'; '.join(parts)})."


def _provider_model(service_provider: object) -> str:
    """The model this provider is actually configured to call, if it says."""
    service = getattr(service_provider, "instance", service_provider)
    for path in ("model_name", "model"):
        val = getattr(service, path, None)
        if val:
            return str(val)
    cfg = getattr(service, "openai_config", None) or getattr(service, "config", None)
    for path in ("model_name", "model"):
        val = getattr(cfg, path, None)
        if val:
            return str(val)
    meta = getattr(service_provider, "metadata", None)
    if isinstance(meta, dict) and meta.get("model"):
        return str(meta["model"])
    return "unknown model"


def _breaker_state(service_provider: object) -> str:
    """ "open" / "half_open" / "closed" / "" when the provider exposes no breaker."""
    cb = getattr(service_provider, "circuit_breaker", None)
    state = getattr(cb, "state", None)
    return str(getattr(state, "value", state) or "").lower()


def _provider_last_error(service_provider: object) -> str:
    """The provider's own last complaint, verbatim and first line only."""
    service = getattr(service_provider, "instance", service_provider)
    for attr in ("last_error", "_last_error", "last_failure_reason"):
        val = getattr(service, attr, None)
        if val:
            return str(val).strip().splitlines()[0][:200]
    return ""


def _provider_role(index: int) -> str:
    """Primary / Secondary / Fallback, from registry order.

    The registry sorts by priority, so position IS the role. An operator reading
    "a provider failed" cannot tell whether their main route is down or a spare
    is; naming the role is the difference between "act now" and "note it".
    """
    return {0: "Primary", 1: "Secondary"}.get(index, "Fallback")


def _retry_seconds(service_provider: object) -> int:
    """How long until the breaker lets a call through again."""
    cb = getattr(service_provider, "circuit_breaker", None)
    cfg = getattr(cb, "config", None)
    val = getattr(cfg, "recovery_timeout", None)
    return int(val) if isinstance(val, (int, float)) and val > 0 else 10


def _provider_fault_code(service_provider: object) -> str:
    """The provider's STRUCTURED fault slug, captured where the exception lived."""
    service = getattr(service_provider, "instance", service_provider)
    return str(getattr(service, "last_fault_code", "") or "").strip().lower()


# "HTTP 401", "http/401", "status 401", "code: 401" — a status, not a token count.
_HTTP_401 = re.compile(r"\b(?:http|https|status|code|error)\b[^0-9a-z]{0,4}401\b")


async def _identify_caller(
    request: Request, authorization: Optional[str] = Header(None)
) -> Optional[AuthContext]:
    """Identify the caller if possible, and NEVER fail if not.

    Deliberately not ``OptionalAuthDep``. That resolves ``optional_auth``,
    whose nested ``Depends(get_auth_service)`` raises 500 when
    ``app.state.auth_service`` is missing — and the supported standalone path
    in app.py calls ``create_app()`` with no runtime, which skips
    ``_initialize_app_state`` entirely. Using it here would make
    /v1/system/health 500 before the handler ran, in precisely the
    uninitialized state the endpoint exists to REPORT, and would fail the
    container healthcheck that probes it.

    "Optional" has to mean optional all the way down: an unidentified caller
    is an observer, never an error.
    """
    auth_service = getattr(request.app.state, "auth_service", None)
    if not isinstance(auth_service, APIAuthService):
        return None
    try:
        return await optional_auth(request, authorization, auth_service)
    except Exception:  # pragma: no cover - health must answer regardless
        return None


def _is_first_run_setup() -> bool:
    """Is this a first-run boot, where LLM settings are open without auth?

    Mirrors the gate the LLM routes themselves use, so the health warning and
    the route it links to cannot disagree about who may act.
    """
    try:
        from ciris_engine.logic.setup.first_run import is_first_run

        return bool(is_first_run())
    except Exception:  # pragma: no cover - never fail health on this
        return False


def _fault_warning(
    lang: str, role: str, name: str, model: str, err: str, fault: str = "", can_manage: bool = True
) -> Optional[SystemWarning]:
    """Turn the provider's OWN words into the one instruction that fixes it.

    A wrong model and a rejected key are both "the provider refused us", and they
    need opposite actions — pick a different model, or paste a different key.
    Reporting them identically makes the user guess, and this is exactly the
    surface where guessing costs them the whole agent (CIRISAgent#1078).

    ONE CONSTRUCTOR FOR BOTH DETECTION PATHS. The structured signal and the text
    fallback used to build their SystemWarning separately, and the first change
    that touched only one of them (role-awareness) silently shipped an admin-only
    instruction to observers down the fallback path. Detection may differ;
    the message must not.

    DO NOT HAND SOMEONE AN INSTRUCTION THEY CANNOT CARRY OUT. LLM management is
    admin-only (`_require_setup_or_admin`: "regular users cannot modify
    settings"), but /v1/system/health is observer-gated — so an ordinary user
    sees these warnings too. Telling them to "Open LLM Settings" points them at a
    screen the API will refuse, which reads as the product being broken twice.
    The FACT is the same for everyone and they are entitled to it; only the
    REMEDY changes, and an observer gets no action_url — a link to a control you
    do not have is not a courtesy.

    Only faults whose remedy we are SURE of get their own message. Anything else
    returns None and falls through to the generic provider-failed line rather
    than inventing an instruction that might send the reader somewhere wrong.
    """

    def _warn(code: str, key: str) -> SystemWarning:
        return SystemWarning(
            code=code,
            message=get_string(
                lang,
                f"status.{key}" if can_manage else f"status.{key}_observer",
                provider=name,
                model=model,
            ),
            severity="error",
            action_url="/settings/llm" if can_manage else None,
        )

    # PREFER THE PROVIDER'S OWN CODE. `fault` is captured at the LLM service,
    # where the openai APIStatusError still exists and `body.error.code` is
    # readable. Falling back to substrings makes every vendor's wording, in every
    # locale, load-bearing — and the first one to say "unknown model" instead of
    # "does not exist" silently stops being diagnosed.
    if fault == "model_not_found":
        return _warn("llm_model_not_found", "llm_model_not_found")
    if fault == "invalid_api_key":
        return _warn("llm_key_rejected", "llm_key_rejected")
    if fault:
        # Structured, but not one we have an instruction for. Say nothing
        # specific rather than guess — the generic line still fires.
        return None

    # Text fallback, for providers that return no structured code. Second, never
    # first, and it builds through the SAME constructor above.
    low = err.lower()
    if "does not exist" in low or "model_not_found" in low or "unknown model" in low:
        return _warn("llm_model_not_found", "llm_model_not_found")
    # A bare "401" ANYWHERE is not evidence of a rejected key: a provider
    # reporting `HTTP 400 ... 401 tokens` would send the user to replace a
    # credential that is fine, while the real fault goes unnamed. Require either
    # authentication-specific wording or a 401 that reads as a status code.
    if (
        "invalid api key" in low
        or "unauthorized" in low
        or "authentication" in low
        or _HTTP_401.search(low) is not None
    ):
        return _warn("llm_key_rejected", "llm_key_rejected")
    return None


def _llm_breaker_warnings(providers: Sequence[object], can_manage: bool = True) -> list[SystemWarning]:
    """Escalate from "here is the fix" to "nothing works, here is when it retries".

    One failed call is noise. A named fault with a known remedy is a to-do. A
    breaker opening is a route lost. Every breaker open is an outage. Those are
    four different sentences and four different responses, and the health surface
    used to collapse them into "all providers unavailable" — which named neither
    the model nor the provider, so it pointed the reader at nothing they could
    change.

    Every level names the PROVIDER and the MODEL, because that pair is what the
    user edits, and links to the card that edits it. The outage level also says
    when the system will retry by itself, so nobody sits refreshing a dead screen
    wondering whether it is on them.
    """
    lang = get_preferred_language()
    warnings: list[SystemWarning] = []
    open_ones: list[tuple[int, object]] = []

    for i, sp in enumerate(providers):
        name = getattr(sp, "name", None) or "provider"
        model = _provider_model(sp)
        role = _provider_role(i)
        err = _provider_last_error(sp)
        state = _breaker_state(sp)

        # The actionable fault, if we can name the remedy with confidence.
        fault_code = _provider_fault_code(sp)
        fault = _fault_warning(lang, role, name, model, err, fault_code, can_manage) if (err or fault_code) else None
        if fault:
            warnings.append(fault)

        if state == "open":
            open_ones.append((i, sp))
            # A breaker open is a lost route, and worth saying even when the
            # fault above already told them what to fix — the fault explains
            # WHY, this explains that the agent has stopped trying.
            warnings.append(
                SystemWarning(
                    code="llm_provider_circuit_open",
                    message=get_string(
                        lang,
                        "status.llm_provider_circuit_open",
                        role=role,
                        provider=name,
                        model=model,
                    ),
                    severity="warning",
                    action_url="/settings/llm" if can_manage else None,
                )
            )
        elif err and not fault:
            # Failing, breaker still closed, and we could not name the remedy.
            # Say the provider failed and repeat its own words rather than
            # inventing an instruction.
            warnings.append(
                SystemWarning(
                    code="llm_provider_failed",
                    message=get_string(
                        lang,
                        "status.llm_provider_failed",
                        role=role,
                        provider=name,
                        model=model,
                        detail=err,
                    ),
                    severity="warning",
                    action_url="/settings/llm" if can_manage else None,
                )
            )

    # Nothing left. This is the one the user acts on, so it carries the retry
    # interval: an outage you know self-heals in 10s is a wait, and one you do
    # not know about is a support ticket.
    if providers and len(open_ones) == len(providers):
        retry = _retry_seconds(open_ones[0][1])
        warnings.append(
            SystemWarning(
                code="llm_all_providers_failed",
                message=get_string(
                    lang,
                    "status.llm_all_providers_failed" if can_manage else "status.llm_all_providers_failed_observer",
                    seconds=retry,
                ),
                severity="error",
                action_url="/settings/llm" if can_manage else None,
            )
        )
    return warnings


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


async def check_llm_availability(can_manage: bool = True) -> tuple[bool, list[SystemWarning]]:
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
                message=get_string(
                    get_preferred_language(),
                    "status.no_llm_provider" if can_manage else "status.no_llm_provider_observer",
                ),
                severity="error",
                action_url="/settings/llm" if can_manage else None,
            )
        ]

    # Check if any provider is healthy
    for service_provider in llm_providers:
        if await _check_provider_health(service_provider):
            return True, []

    logger.debug(f"All {len(llm_providers)} providers unhealthy - degraded_mode=True")

    # SAY WHICH PROVIDER, AND WHAT IT ACTUALLY SAID.
    #
    # This used to read "All LLM providers are currently unavailable. Check your
    # provider settings or network connection." A user whose Groq key had been
    # revoked was pointed at his network. His real faults, both visible in the
    # provider's own replies, were:
    #
    #   ciris_primary  model=gpt-4o-mini  -> HTTP 401 Invalid API Key
    #   groq_byok      model=default      -> "The model `default` does not exist"
    #
    # Those need opposite responses — rotate a credential vs pick a model — and
    # a message that names neither sends the reader to a third thing entirely.
    # Breaker state first: it says WHY the provider stopped answering, and
    # whether anything is left. If it produced a verdict, that verdict is the
    # message — appending the generic "no provider is answering" underneath
    # would restate it less precisely.
    breaker = _llm_breaker_warnings(llm_providers, can_manage)
    if breaker:
        return False, breaker

    # Same role rule as the ladder above: an observer is told what is wrong and
    # who fixes it, never handed a link to a control the settings API will
    # refuse them. This branch and the no-provider branch above are the two
    # most common states — first boot, and a provider failing with no recorded
    # error — so getting the role wrong here is what a non-admin user would
    # actually hit.
    lang = get_preferred_language()
    detail = _describe_provider_failures(llm_providers)
    if detail:
        key = (
            "status.llm_providers_unhealthy_detail" if can_manage else "status.llm_providers_unhealthy_detail_observer"
        )
        message = get_string(lang, key, detail=detail)
    else:
        key = "status.llm_providers_unhealthy" if can_manage else "status.llm_providers_unhealthy_observer"
        message = get_string(lang, key)
    return False, [
        SystemWarning(
            code="llm_providers_unhealthy",
            message=message,
            severity="warning",
            action_url="/settings/llm" if can_manage else None,
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


def _rejected_wakeup_warnings(request: Request) -> list[SystemWarning]:
    """A REJECTED wakeup step is terminal, and the agent must not pass it.

    Reported from production (#1069 / #1077): all three wakeup step tasks were
    REJECTED, `ciris_persist` refused to record `rejected` as a task status
    though `TaskStatus.REJECTED` is valid in the Python enum, and the agent spun
    one empty WAKEUP round every ~5s for its entire 22-hour uptime. A step that
    is rejected but cannot be RECORDED as rejected is neither complete nor
    terminal, which is exactly the spin.

    The wakeup processor already refuses to reach WORK — `_check_all_steps_complete`
    demands COMPLETED and a rejected step never gets there — but it refuses by
    ACCIDENT, as "not yet complete", which is indistinguishable from a boot still
    in progress. The health surface said `cognitive_state: WAKEUP` and
    `status: healthy` throughout, which is the same absence-reads-as-success
    shape #943 fixed one level up.

    Rejection is a DECISION, not a delay. An agent that declined to affirm its
    own identity has not failed to finish waking up; it has finished, and the
    answer was no. That has to be visible as its own condition rather than
    inferred from a round counter nobody is watching.
    """
    try:
        from ciris_engine.logic.persistence.models.tasks import get_all_tasks
        from ciris_engine.logic.services.lifecycle.scheduler.service import WAKEUP_STEP_PREFIXES
        from ciris_engine.logic.utils.occurrence_utils import get_current_occurrence_id

        tasks = get_all_tasks(occurrence_id=get_current_occurrence_id()) or []
    except Exception as e:  # pragma: no cover - a health probe must never raise
        logger.debug(f"Could not check wakeup steps: {e}")
        return []

    rejected = []
    for task in tasks:
        task_id = str(getattr(task, "task_id", "") or "")
        if not task_id.startswith(WAKEUP_STEP_PREFIXES):
            continue
        status = getattr(task, "status", None)
        if str(getattr(status, "value", status)).lower() != "rejected":
            continue
        rejected.append(task_id.split("_")[0])

    if not rejected:
        return []

    steps = ", ".join(sorted(set(rejected)))
    logger.error(
        "WAKEUP STEP REJECTED: %s. The agent will not enter WORK and is reporting "
        "cognitive_state=WAKEUP_ERROR. This is a decision, not a delay — it does not "
        "resolve by waiting. See CIRISAgent#1069 / #1077.",
        steps,
    )
    return [
        SystemWarning(
            code="wakeup_step_rejected",
            message=(
                f"The agent rejected a wakeup step ({steps}) and will not enter WORK. "
                "This does not resolve by waiting — a rejected step is terminal."
            ),
            severity="error",
            action_url="/system",
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


async def collect_system_warnings(request: Request, can_manage: bool = True) -> tuple[bool, list[SystemWarning]]:
    """Collect system-level warnings and check degraded mode.

    Returns (degraded_mode, warnings) tuple. degraded_mode is True when NO
    working LLM is available.
    """
    has_working_llm, llm_warnings = await check_llm_availability(can_manage)
    warnings = llm_warnings.copy()
    warnings.extend(await _adapter_reauth_warnings(request))
    warnings.extend(_hardware_trust_warnings(request))
    # #1057 — fleet conditions that previously lived only in container logs.
    # Manager polls this endpoint; anything it must act on has to be here.
    warnings.extend(_adapter_load_failure_warnings(request))
    warnings.extend(_occurrence_warnings(request))
    warnings.extend(_stale_shared_task_warnings(request))
    warnings.extend(_rejected_wakeup_warnings(request))
    warnings.extend(_claim_persistence_warnings(request))
    return not has_working_llm, warnings


@router.get("/health")
async def get_system_health(
    request: Request, auth: Optional[AuthContext] = Depends(_identify_caller)
) -> SuccessResponse[SystemHealthResponse]:
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
    # LLM management is admin-only, so an observer must not be handed an
    # instruction (or a link) they cannot act on. Derived from the CALLER's role,
    # never assumed.
    # First-run setup is intentionally unauthenticated, and BOTH LLM
    # configuration routes allow it: _require_setup_or_admin returns early
    # while is_first_run(). So the setup user may configure a provider even
    # though `auth` is None — telling them "an administrator needs to do this"
    # and hiding the link would strand them in exactly the state (fresh boot,
    # no provider) where this warning fires most.
    _can_manage = _is_first_run_setup() or getattr(auth, "role", None) in (
        UserRole.ADMIN,
        UserRole.AUTHORITY,
        UserRole.SYSTEM_ADMIN,
    )
    degraded_mode, warnings = await collect_system_warnings(request, _can_manage)

    # Determine overall system status
    status = determine_overall_status(init_complete, processor_healthy, services)

    # A REJECTED WAKEUP STEP IS ITS OWN COGNITIVE STATE (#1069 / #1077).
    #
    # The processor stays in WAKEUP and never reaches WORK, which is correct —
    # but it reports plain `WAKEUP`, identical to a boot still in progress. In
    # production that read as normal for 22 hours while the agent span one empty
    # round every ~5s. The distinction matters because the two need opposite
    # responses: a boot resolves by waiting, and a rejection never does.
    #
    # So the state says so. `degraded_mode` is set alongside it because the agent
    # is running without having completed the sequence that authorises it to
    # work — the same "not doing the job it says it is" that flag already means.
    if any(w.code == "wakeup_step_rejected" for w in warnings):
        cognitive_state = "WAKEUP_ERROR"
        degraded_mode = True

    # AN AGENT WITH NO WAY TO TALK TO ANYONE IS NOT HEALTHY (#1057).
    #
    # determine_overall_status() weighs init, the processor and the service
    # registry — none of which know whether a single COMMUNICATION adapter
    # loaded. So scout1 ran 0 of 4 configured adapters and still reported
    # `status: healthy`, and that is the line every dashboard and every operator
    # reads first. 2.9.23 surfaced the condition as a warning, which was
    # necessary and not sufficient: a warning buried in an array under a green
    # status is still a green status.
    #
    # This is the gap that went unnoticed across six releases, so the top-level
    # field has to carry it. `critical` rather than `degraded`: an agent that
    # cannot receive or send is not doing a reduced job, it is doing none of it.
    if any(w.code in ("adapters_config_stale", "adapters_failed_to_load") and w.severity == "error" for w in warnings):
        if status != "critical":
            logger.error(
                "Reporting status=critical: configured adapters failed to load and none are running "
                "(was %s). See the adapters_* warning for which ones.",
                status,
            )
        status = "critical"

    response = SystemHealthResponse(
        status=status,
        # We are the brain. Say so — never make a client infer it.
        role="agent",
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
        return SuccessResponse(data=FederationAddressResponse(available=False, key_id=None, edge_version=None))

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
