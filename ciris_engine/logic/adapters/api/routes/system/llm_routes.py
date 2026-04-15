"""
LLM system endpoints - Exposes LLMBus runtime management capabilities.

These endpoints allow monitoring and control of the LLM service layer:
- Bus-level status and metrics
- Per-provider status with circuit breaker state
- Distribution strategy management
- Circuit breaker management (reset, config)
"""

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status

from ciris_engine.logic.buses.llm_bus import DistributionStrategy as InternalDistributionStrategy
from ciris_engine.logic.buses.llm_bus import LLMBus
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitState
from ciris_engine.schemas.api.responses import SuccessResponse

from ciris_engine.logic.registries.base import Priority as InternalPriority, get_global_registry
from ciris_engine.logic.persistence.llm_providers import (
    LLMProviderConfig,
    create_provider as persist_create_provider,
    delete_provider as persist_delete_provider,
)
from ciris_engine.schemas.runtime.enums import ServiceType

from .llm_schemas import (
    AddProviderRequest,
    AddProviderResponse,
    CircuitBreakerConfig,
    CircuitBreakerConfigUpdateRequest,
    CircuitBreakerConfigUpdateResponse,
    CircuitBreakerResetRequest,
    CircuitBreakerResetResponse,
    CircuitBreakerState,
    CircuitBreakerStatus,
    DistributionStrategy,
    DistributionStrategyUpdateRequest,
    DistributionStrategyUpdateResponse,
    LLMBusStatusResponse,
    LLMProviderStatus,
    LLMProvidersResponse,
    ProviderDeleteResponse,
    ProviderMetrics,
    ProviderPriority,
    ProviderPriorityUpdateRequest,
    ProviderPriorityUpdateResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/llm", tags=["LLM Management"])


# ============================================================================
# Auth Dependencies - Allow setup mode OR require admin auth
# ============================================================================


def _is_setup_allowed_without_auth() -> bool:
    """Check if we're in first-run setup mode (no auth required)."""
    from ciris_engine.logic.setup.first_run import is_first_run

    return is_first_run()


async def _require_setup_or_admin(request: Request) -> None:
    """Allow access during first-run OR with admin authentication.

    LLM management is admin-only - regular users cannot modify settings.
    """
    if _is_setup_allowed_without_auth():
        return

    from ciris_engine.schemas.api.auth import UserRole

    from ...dependencies.auth import get_auth_context, get_auth_service

    authorization = request.headers.get("Authorization")
    auth_service = get_auth_service(request)
    auth = await get_auth_context(request, authorization, auth_service)
    if auth is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required for LLM management",
        )
    if not auth.role.has_permission(UserRole.ADMIN):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin role required for LLM management",
        )


SetupOrAdminDep = Depends(_require_setup_or_admin)


# ============================================================================
# Helpers
# ============================================================================


def get_llm_bus(request: Request) -> LLMBus:
    """Get LLMBus from runtime, raising HTTPException if not available."""
    runtime = getattr(request.app.state, "runtime", None)
    if not runtime:
        raise HTTPException(status_code=503, detail="Runtime not available")

    bus_manager = getattr(runtime, "bus_manager", None)
    if not bus_manager:
        raise HTTPException(status_code=503, detail="Bus manager not available")

    llm_bus: Optional[LLMBus] = getattr(bus_manager, "llm", None)
    if not llm_bus:
        raise HTTPException(status_code=503, detail="LLM bus not available")

    return llm_bus


def map_circuit_state(state: CircuitState) -> CircuitBreakerState:
    """Map internal CircuitState to API schema CircuitBreakerState."""
    mapping = {
        CircuitState.CLOSED: CircuitBreakerState.CLOSED,
        CircuitState.OPEN: CircuitBreakerState.OPEN,
        CircuitState.HALF_OPEN: CircuitBreakerState.HALF_OPEN,
    }
    return mapping.get(state, CircuitBreakerState.CLOSED)


def map_distribution_strategy(strategy: InternalDistributionStrategy) -> DistributionStrategy:
    """Map internal DistributionStrategy enum to API schema enum."""
    mapping = {
        InternalDistributionStrategy.ROUND_ROBIN: DistributionStrategy.ROUND_ROBIN,
        InternalDistributionStrategy.LATENCY_BASED: DistributionStrategy.LATENCY_BASED,
        InternalDistributionStrategy.RANDOM: DistributionStrategy.RANDOM,
        InternalDistributionStrategy.LEAST_LOADED: DistributionStrategy.LEAST_LOADED,
    }
    return mapping.get(strategy, DistributionStrategy.LATENCY_BASED)


def get_internal_strategy(strategy: DistributionStrategy) -> InternalDistributionStrategy:
    """Get internal DistributionStrategy enum from API schema enum."""
    mapping = {
        DistributionStrategy.ROUND_ROBIN: InternalDistributionStrategy.ROUND_ROBIN,
        DistributionStrategy.LATENCY_BASED: InternalDistributionStrategy.LATENCY_BASED,
        DistributionStrategy.RANDOM: InternalDistributionStrategy.RANDOM,
        DistributionStrategy.LEAST_LOADED: InternalDistributionStrategy.LEAST_LOADED,
    }
    return mapping.get(strategy, InternalDistributionStrategy.LATENCY_BASED)




def map_priority_to_api(priority: InternalPriority) -> ProviderPriority:
    """Map internal Priority enum to API schema ProviderPriority."""
    mapping = {
        InternalPriority.CRITICAL: ProviderPriority.CRITICAL,
        InternalPriority.HIGH: ProviderPriority.HIGH,
        InternalPriority.NORMAL: ProviderPriority.NORMAL,
        InternalPriority.LOW: ProviderPriority.LOW,
        InternalPriority.FALLBACK: ProviderPriority.FALLBACK,
    }
    return mapping.get(priority, ProviderPriority.NORMAL)


def get_internal_priority(priority: ProviderPriority) -> InternalPriority:
    """Get internal Priority enum from API schema ProviderPriority."""
    mapping = {
        ProviderPriority.CRITICAL: InternalPriority.CRITICAL,
        ProviderPriority.HIGH: InternalPriority.HIGH,
        ProviderPriority.NORMAL: InternalPriority.NORMAL,
        ProviderPriority.LOW: InternalPriority.LOW,
        ProviderPriority.FALLBACK: InternalPriority.FALLBACK,
    }
    return mapping.get(priority, InternalPriority.NORMAL)


def build_cb_status(cb: CircuitBreaker) -> CircuitBreakerStatus:
    """Build CircuitBreakerStatus from a CircuitBreaker instance."""
    # Calculate success rate
    total: int = cb.total_calls if hasattr(cb, "total_calls") else 0
    successes: int = cb.total_successes if hasattr(cb, "total_successes") else 0
    success_rate = successes / total if total > 0 else 1.0

    # Calculate last failure age
    last_failure_age: Optional[float] = None
    if hasattr(cb, "last_failure_time") and cb.last_failure_time:
        last_failure_age = time.monotonic() - cb.last_failure_time

    # Calculate time in open state
    time_in_open: float = getattr(cb, "time_in_open_state", 0.0)

    return CircuitBreakerStatus(
        state=map_circuit_state(cb.state),
        failure_count=getattr(cb, "failure_count", 0),
        success_count=getattr(cb, "success_count", 0),
        total_calls=total,
        total_failures=getattr(cb, "total_failures", 0),
        total_successes=successes,
        success_rate=success_rate,
        consecutive_failures=getattr(cb, "consecutive_failures", 0),
        recovery_attempts=getattr(cb, "recovery_attempts", 0),
        state_transitions=getattr(cb, "state_transitions", 0),
        time_in_open_state_seconds=time_in_open,
        last_failure_age_seconds=last_failure_age,
        config=CircuitBreakerConfig(
            failure_threshold=cb.config.failure_threshold,
            recovery_timeout_seconds=cb.config.recovery_timeout,
            success_threshold=cb.config.success_threshold,
            timeout_duration_seconds=cb.config.timeout_duration,
        ),
    )


def build_provider_metrics(metrics: Any) -> ProviderMetrics:
    """Build ProviderMetrics from service metrics."""
    return ProviderMetrics(
        total_requests=getattr(metrics, "total_requests", 0),
        failed_requests=getattr(metrics, "failed_requests", 0),
        failure_rate=getattr(metrics, "failure_rate", 0.0),
        average_latency_ms=getattr(metrics, "average_latency_ms", 0.0),
        consecutive_failures=getattr(metrics, "consecutive_failures", 0),
        last_request_time=getattr(metrics, "last_request_time", None),
        last_failure_time=getattr(metrics, "last_failure_time", None),
        is_rate_limited=False,
        rate_limit_cooldown_remaining_seconds=None,
    )


# ============================================================================
# GET /system/llm/status - Bus status and aggregate metrics
# ============================================================================


@router.get(
    "/status",
    responses={
        503: {"description": "LLM bus not available"},
    },
    dependencies=[SetupOrAdminDep],
)
async def get_llm_status(
    request: Request,
) -> SuccessResponse[LLMBusStatusResponse]:
    """
    Get LLMBus status with aggregate metrics.

    Returns distribution strategy, aggregate request/failure counts,
    provider availability, and circuit breaker state summary.
    """
    llm_bus = get_llm_bus(request)

    # Count providers and CB states
    providers_total = len(llm_bus.circuit_breakers)
    providers_available = 0
    providers_rate_limited = 0
    cb_closed = 0
    cb_open = 0
    cb_half_open = 0

    # Aggregate metrics
    total_requests = 0
    failed_requests = 0
    total_latency = 0.0

    for name, cb in llm_bus.circuit_breakers.items():
        # Count CB states
        if cb.state == CircuitState.CLOSED:
            cb_closed += 1
            providers_available += 1
        elif cb.state == CircuitState.OPEN:
            cb_open += 1
        elif cb.state == CircuitState.HALF_OPEN:
            cb_half_open += 1
            providers_available += 1

        # Check rate limiting
        rate_limited_until = llm_bus._rate_limited_until.get(name, 0)
        if rate_limited_until > time.time():
            providers_rate_limited += 1

        # Aggregate metrics from service_metrics
        if name in llm_bus.service_metrics:
            metrics = llm_bus.service_metrics[name]
            total_requests += metrics.total_requests
            failed_requests += metrics.failed_requests
            total_latency += metrics.total_latency_ms

    # Calculate averages
    average_latency = total_latency / total_requests if total_requests > 0 else 0.0
    error_rate = failed_requests / total_requests if total_requests > 0 else 0.0

    # Calculate uptime
    uptime = 0.0
    if hasattr(llm_bus, "_start_time") and llm_bus._start_time:
        now = datetime.now(timezone.utc)
        uptime = (now - llm_bus._start_time).total_seconds()

    return SuccessResponse(
        data=LLMBusStatusResponse(
            distribution_strategy=map_distribution_strategy(llm_bus.distribution_strategy),
            total_requests=total_requests,
            failed_requests=failed_requests,
            average_latency_ms=average_latency,
            error_rate=error_rate,
            providers_total=providers_total,
            providers_available=providers_available,
            providers_rate_limited=providers_rate_limited,
            circuit_breakers_closed=cb_closed,
            circuit_breakers_open=cb_open,
            circuit_breakers_half_open=cb_half_open,
            uptime_seconds=uptime,
            timestamp=datetime.now(timezone.utc),
        )
    )


# ============================================================================
# GET /system/llm/providers - List all providers with status
# ============================================================================


@router.get(
    "/providers",
    responses={
        503: {"description": "LLM bus not available"},
    },
    dependencies=[SetupOrAdminDep],
)
async def get_llm_providers(
    request: Request,
) -> SuccessResponse[LLMProvidersResponse]:
    """
    Get status of all LLM providers.

    Returns each provider's health, metrics, and circuit breaker status.
    Providers are read from ServiceRegistry (not circuit breakers which are lazy).
    """
    llm_bus = get_llm_bus(request)
    registry = get_global_registry()

    providers = []

    # Get all registered LLM providers from registry (not from circuit_breakers which are lazy)
    registered_providers = registry._services.get(ServiceType.LLM, [])

    for provider_info in registered_providers:
        name = provider_info.name

        # Check if circuit breaker exists (created lazily on first use)
        cb = llm_bus.circuit_breakers.get(name)

        # Get service metrics (may not exist until first request)
        metrics = llm_bus.service_metrics.get(name)
        provider_metrics = build_provider_metrics(metrics) if metrics else ProviderMetrics()

        # Check rate limiting
        rate_limited_until = llm_bus._rate_limited_until.get(name, 0)
        current_time = time.time()
        if rate_limited_until > current_time:
            provider_metrics.is_rate_limited = True
            provider_metrics.rate_limit_cooldown_remaining_seconds = rate_limited_until - current_time

        # Determine health: if no CB yet, assume healthy; otherwise check CB state
        if cb is not None:
            healthy = cb.state != CircuitState.OPEN
            cb_status = build_cb_status(cb)
        else:
            healthy = True
            cb_status = CircuitBreakerStatus(
                state="closed",
                failure_count=0,
                success_count=0,
                last_failure_time=None,
            )

        # Get priority from provider_info
        priority = map_priority_to_api(provider_info.priority) if provider_info.priority else ProviderPriority.NORMAL

        providers.append(
            LLMProviderStatus(
                name=name,
                healthy=healthy,
                enabled=True,  # All registered providers are enabled
                priority=priority,
                metrics=provider_metrics,
                circuit_breaker=cb_status,
            )
        )

    return SuccessResponse(
        data=LLMProvidersResponse(
            providers=providers,
            total_count=len(providers),
        )
    )


# ============================================================================
# PUT /system/llm/distribution - Update distribution strategy
# ============================================================================


@router.put(
    "/distribution",
    responses={
        503: {"description": "LLM bus not available"},
    },
    dependencies=[SetupOrAdminDep],
)
async def update_distribution_strategy(
    request: Request,
    body: DistributionStrategyUpdateRequest,
) -> SuccessResponse[DistributionStrategyUpdateResponse]:
    """
    Update the LLMBus distribution strategy.

    Changes how requests are distributed among providers:
    - round_robin: Cycle through providers sequentially
    - latency_based: Prefer lower-latency providers
    - random: Random selection
    - least_loaded: Prefer providers with fewer active requests
    """
    llm_bus = get_llm_bus(request)

    previous_strategy = map_distribution_strategy(llm_bus.distribution_strategy)
    new_internal_strategy = get_internal_strategy(body.strategy)

    llm_bus.distribution_strategy = new_internal_strategy

    logger.info(f"Distribution strategy changed from {previous_strategy} to {body.strategy}")

    return SuccessResponse(
        data=DistributionStrategyUpdateResponse(
            success=True,
            previous_strategy=previous_strategy,
            new_strategy=body.strategy,
            message=f"Distribution strategy updated to {body.strategy.value}",
        )
    )


# ============================================================================
# POST /system/llm/providers/{name}/circuit-breaker/reset - Reset CB
# ============================================================================


@router.post(
    "/providers/{name}/circuit-breaker/reset",
    responses={
        404: {"description": "Provider not found"},
        503: {"description": "LLM bus not available"},
    },
    dependencies=[SetupOrAdminDep],
)
async def reset_circuit_breaker(
    request: Request,
    name: str,
    body: Optional[CircuitBreakerResetRequest] = None,
) -> SuccessResponse[CircuitBreakerResetResponse]:
    """
    Reset a provider's circuit breaker.

    By default, only resets if CB is OPEN or HALF_OPEN.
    Use force=true to reset even if already CLOSED.
    """
    llm_bus = get_llm_bus(request)

    if name not in llm_bus.circuit_breakers:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    cb = llm_bus.circuit_breakers[name]
    previous_state = map_circuit_state(cb.state)
    force = body.force if body else False

    # Check if reset is needed
    if cb.state == CircuitState.CLOSED and not force:
        return SuccessResponse(
            data=CircuitBreakerResetResponse(
                success=True,
                provider_name=name,
                previous_state=previous_state,
                new_state=CircuitBreakerState.CLOSED,
                message="Circuit breaker already closed",
            )
        )

    # Perform reset
    cb.reset()
    new_state = map_circuit_state(cb.state)

    logger.info(f"Circuit breaker for '{name}' reset: {previous_state} -> {new_state}")

    return SuccessResponse(
        data=CircuitBreakerResetResponse(
            success=True,
            provider_name=name,
            previous_state=previous_state,
            new_state=new_state,
            message=f"Circuit breaker reset from {previous_state.value} to {new_state.value}",
        )
    )


# ============================================================================
# PUT /system/llm/providers/{name}/circuit-breaker/config - Update CB config
# ============================================================================


@router.put(
    "/providers/{name}/circuit-breaker/config",
    responses={
        404: {"description": "Provider not found"},
        503: {"description": "LLM bus not available"},
    },
    dependencies=[SetupOrAdminDep],
)
async def update_circuit_breaker_config(
    request: Request,
    name: str,
    body: CircuitBreakerConfigUpdateRequest,
) -> SuccessResponse[CircuitBreakerConfigUpdateResponse]:
    """
    Update a provider's circuit breaker configuration.

    Only provided fields are updated; null fields are ignored.
    Changes take effect immediately.
    """
    llm_bus = get_llm_bus(request)

    if name not in llm_bus.circuit_breakers:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    cb = llm_bus.circuit_breakers[name]

    # Capture previous config
    previous_config = CircuitBreakerConfig(
        failure_threshold=cb.config.failure_threshold,
        recovery_timeout_seconds=cb.config.recovery_timeout,
        success_threshold=cb.config.success_threshold,
        timeout_duration_seconds=cb.config.timeout_duration,
    )

    # Update config fields that were provided
    if body.failure_threshold is not None:
        cb.config.failure_threshold = body.failure_threshold
    if body.recovery_timeout_seconds is not None:
        cb.config.recovery_timeout = body.recovery_timeout_seconds
    if body.success_threshold is not None:
        cb.config.success_threshold = body.success_threshold
    if body.timeout_duration_seconds is not None:
        cb.config.timeout_duration = body.timeout_duration_seconds

    # Build new config response
    new_config = CircuitBreakerConfig(
        failure_threshold=cb.config.failure_threshold,
        recovery_timeout_seconds=cb.config.recovery_timeout,
        success_threshold=cb.config.success_threshold,
        timeout_duration_seconds=cb.config.timeout_duration,
    )

    logger.info(f"Circuit breaker config for '{name}' updated")

    return SuccessResponse(
        data=CircuitBreakerConfigUpdateResponse(
            success=True,
            provider_name=name,
            previous_config=previous_config,
            new_config=new_config,
            message="Circuit breaker configuration updated",
        )
    )


# ============================================================================
# PUT /system/llm/providers/{name}/priority - Update provider priority
# ============================================================================


@router.put(
    "/providers/{name}/priority",
    responses={
        404: {"description": "Provider not found"},
        503: {"description": "Service registry not available"},
    },
    dependencies=[SetupOrAdminDep],
)
async def update_provider_priority(
    request: Request,
    name: str,
    body: ProviderPriorityUpdateRequest,
) -> SuccessResponse[ProviderPriorityUpdateResponse]:
    """
    Update a provider's priority level.

    Changes where this provider falls in the selection order:
    - critical: Always try first
    - high: Primary providers
    - normal: Standard providers
    - low: Use when others unavailable
    - fallback: Last resort
    """
    registry = get_global_registry()

    # Find the provider to get current priority
    provider = registry.get_provider_by_name(name, ServiceType.LLM)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    previous_priority = map_priority_to_api(provider.priority)
    new_internal_priority = get_internal_priority(body.priority)

    # Update the priority
    success = registry.set_provider_priority(name, new_internal_priority, ServiceType.LLM)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to update priority for '{name}'")

    logger.info(f"Provider '{name}' priority changed from {previous_priority} to {body.priority}")

    return SuccessResponse(
        data=ProviderPriorityUpdateResponse(
            success=True,
            provider_name=name,
            previous_priority=previous_priority,
            new_priority=body.priority,
            message=f"Priority updated from {previous_priority.value} to {body.priority.value}",
        )
    )


# ============================================================================
# DELETE /system/llm/providers/{name} - Unregister a provider
# ============================================================================


@router.delete(
    "/providers/{name}",
    responses={
        404: {"description": "Provider not found"},
        503: {"description": "Service registry not available"},
    },
    dependencies=[SetupOrAdminDep],
)
async def delete_provider(
    request: Request,
    name: str,
) -> SuccessResponse[ProviderDeleteResponse]:
    """
    Unregister an LLM provider.

    Removes the provider from the registry. This is typically used when:
    - A local inference server is no longer available
    - Removing a provider added during setup
    """
    registry = get_global_registry()

    # Check if provider exists
    provider = registry.get_provider_by_name(name, ServiceType.LLM)
    if not provider:
        raise HTTPException(status_code=404, detail=f"Provider '{name}' not found")

    # Unregister
    success = registry.unregister(name)
    if not success:
        raise HTTPException(status_code=500, detail=f"Failed to unregister '{name}'")

    logger.info(f"Provider '{name}' unregistered")

    # Remove from persisted config (both graph AND .env)
    config_service = getattr(request.app.state, "config_service", None)
    persist_result = await persist_delete_provider(name=name, config_service=config_service)

    if persist_result.success:
        logger.info(
            f"Removed provider '{name}' from persisted config "
            f"(graph={persist_result.graph_persisted}, env={persist_result.env_persisted})"
        )
    elif persist_result.error and "not found" not in persist_result.error:
        # Only warn if it's not a "not found" error (provider might not have been persisted)
        logger.warning(f"Failed to remove provider '{name}' from persisted config: {persist_result.error}")

    return SuccessResponse(
        data=ProviderDeleteResponse(
            success=True,
            provider_name=name,
            message=f"Provider '{name}' has been unregistered",
        )
    )


# ============================================================================
# POST /system/llm/providers - Add a new provider
# ============================================================================


@router.post(
    "/providers",
    responses={
        400: {"description": "Invalid provider configuration"},
        503: {"description": "Required services not available"},
    },
    dependencies=[SetupOrAdminDep],
)
async def add_provider(
    request: Request,
    body: AddProviderRequest,
) -> SuccessResponse[AddProviderResponse]:
    """
    Add a new LLM provider to the bus.

    This endpoint allows registering discovered local inference servers
    or additional cloud providers at runtime. The provider will be
    immediately available for use.

    For local inference servers (Ollama, llama.cpp, vLLM, etc.):
    - api_key can be empty or omitted
    - base_url should point to the server (e.g., http://192.168.1.100:11434/v1)

    For cloud providers:
    - api_key is required
    - base_url is optional (uses provider defaults)
    """
    from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient, OpenAIConfig
    from ciris_engine.schemas.services.capabilities import LLMCapabilities

    registry = get_global_registry()

    # Get required services from app state
    telemetry_service = getattr(request.app.state, "telemetry_service", None)
    time_service = getattr(request.app.state, "time_service", None)

    if not telemetry_service or not time_service:
        raise HTTPException(
            status_code=503,
            detail="Required services (telemetry, time) not available"
        )

    # Generate provider name if not provided
    provider_name = body.name
    if not provider_name:
        # Generate from provider_id and base_url
        url_part = body.base_url.replace("http://", "").replace("https://", "").replace("/", "_").replace(":", "_")
        provider_name = f"{body.provider_id}_{url_part}"

    # Check if provider already exists
    existing = registry.get_provider_by_name(provider_name, ServiceType.LLM)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Provider '{provider_name}' already exists"
        )

    # Map API priority to internal priority
    priority_mapping = {
        ProviderPriority.CRITICAL: InternalPriority.CRITICAL,
        ProviderPriority.HIGH: InternalPriority.HIGH,
        ProviderPriority.NORMAL: InternalPriority.NORMAL,
        ProviderPriority.LOW: InternalPriority.LOW,
        ProviderPriority.FALLBACK: InternalPriority.FALLBACK,
    }
    internal_priority = priority_mapping.get(body.priority, InternalPriority.FALLBACK)

    try:
        # For local servers, use "local" as the API key (convention for local inference)
        api_key = body.api_key
        if not api_key and body.provider_id == "local":
            api_key = "local"

        # Create config
        llm_config = OpenAIConfig(
            base_url=body.base_url,
            model_name=body.model or "default",
            api_key=api_key or "",
            instructor_mode="JSON",
            timeout_seconds=30,
            max_retries=2,
        )

        # Create and start service
        service = OpenAICompatibleClient(
            config=llm_config,
            telemetry_service=telemetry_service,
            time_service=time_service,
            service_name=provider_name,
        )
        await service.start()

        # Register with registry
        registry.register_service(
            service_type=ServiceType.LLM,
            provider=service,
            priority=internal_priority,
            capabilities=[LLMCapabilities.CALL_LLM_STRUCTURED],
            metadata={
                "provider": body.provider_id,
                "model": body.model or "default",
                "base_url": body.base_url,
                "added_at_runtime": True,
            },
        )

        logger.info(f"Added LLM provider '{provider_name}' with priority {body.priority.value}")

        # Persist provider configuration for restart survival (both graph AND .env)
        provider_config = LLMProviderConfig(
            provider_id=body.provider_id,
            base_url=body.base_url,
            model=body.model or "default",
            api_key=body.api_key or "",
            priority=body.priority.value,
        )

        config_service = getattr(request.app.state, "config_service", None)
        persist_result = await persist_create_provider(
            name=provider_name,
            config=provider_config,
            config_service=config_service,
        )

        if persist_result.success:
            logger.info(
                f"Persisted LLM provider '{provider_name}' "
                f"(graph={persist_result.graph_persisted}, env={persist_result.env_persisted})"
            )
        else:
            logger.warning(f"Failed to persist provider '{provider_name}': {persist_result.error}")

        return SuccessResponse(
            data=AddProviderResponse(
                success=True,
                provider_name=provider_name,
                provider_id=body.provider_id,
                base_url=body.base_url,
                priority=body.priority,
                message=f"Provider '{provider_name}' added successfully",
            )
        )

    except Exception as e:
        logger.error(f"Failed to add provider '{provider_name}': {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to add provider: {str(e)}"
        )
