"""
Base Registry System

Provides unified registration and discovery for services, adapters, and tools
with priority-based fallbacks and circuit breaker patterns for resilience.
"""

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, Protocol, TypeVar, Union, cast

if TYPE_CHECKING:
    from ciris_engine.protocols.infrastructure.base import ServiceRegistryProtocol

from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitState

logger = logging.getLogger(__name__)


class Priority(Enum):
    """Service priority levels for fallback ordering"""

    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    FALLBACK = 9


class SelectionStrategy(Enum):
    """Provider selection strategy within a priority group."""

    FALLBACK = "fallback"  # First available
    ROUND_ROBIN = "round_robin"  # Rotate providers


T_Service = TypeVar("T_Service")


@dataclass
class ServiceProvider(Generic[T_Service]):
    """Represents a registered service provider with metadata"""

    name: str
    priority: Priority
    instance: T_Service
    capabilities: List[str]
    circuit_breaker: Optional[CircuitBreaker] = None
    metadata: JSONDict = field(default_factory=dict)  # ServiceMetadata.model_dump() result
    priority_group: int = 0
    strategy: SelectionStrategy = SelectionStrategy.FALLBACK


class HealthCheckProtocol(Protocol):
    """Protocol for services that support health checking"""

    async def is_healthy(self) -> bool:
        """Check if the service is healthy and ready to handle requests"""
        ...


if TYPE_CHECKING:
    _Base = ServiceRegistryProtocol
else:
    _Base = object


class ServiceRegistry(_Base):
    """
    Central registry for all services with priority/fallback support.

    Manages service registration, discovery, and health monitoring with
    circuit breaker patterns for resilience.

    Implements ServiceRegistryProtocol for type safety.
    """

    def __init__(self, required_services: Optional[List[ServiceType]] = None) -> None:
        # Only global services now - no handler-specific registration
        # Note: Using Any here because we store multiple service types in one dict
        # Individual access methods will return properly typed results
        self._services: Dict[ServiceType, List[ServiceProvider[Any]]] = {}
        self._shutdown_mode: bool = False  # Flag to skip health checks during shutdown
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._rr_state: Dict[str, int] = {}
        self._required_service_types: List[ServiceType] = required_services or [
            ServiceType.COMMUNICATION,
            ServiceType.MEMORY,
            ServiceType.AUDIT,
            ServiceType.LLM,
        ]

        # Metrics tracking
        self._service_lookups = 0
        self._service_hits = 0
        self._service_misses = 0
        self._health_check_failures = 0
        self._circuit_breaker_opens = 0
        self._registrations_total = 0
        self._deregistrations_total = 0

    def register_service(
        self,
        service_type: ServiceType,
        provider: T_Service,
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[JSONDict] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """
        Register a service provider globally.

        Args:
            service_type: Type of service (e.g., 'llm', 'memory', 'audit')
            provider: Service instance
            priority: Service priority for fallback ordering
            capabilities: List of capabilities this service provides
            circuit_breaker_config: Optional custom circuit breaker config
            metadata: Additional metadata for the service

        Returns:
            str: Unique provider name for later reference
        """
        # Initialize service type list if needed
        if service_type not in self._services:
            self._services[service_type] = []

        provider_name = f"{provider.__class__.__name__}_{id(provider)}"

        # Validate LLM service mixing (extracted to helper)
        if service_type == ServiceType.LLM:
            self._validate_llm_service_mixing(provider, provider_name, metadata)

        # Create service provider
        sp = self._create_service_provider(
            service_type,
            provider_name,
            provider,
            priority,
            capabilities,
            circuit_breaker_config,
            metadata,
            priority_group,
            strategy,
        )

        # Register and track
        self._register_and_sort(service_type, sp, provider_name, priority, capabilities)

        return provider_name

    def _validate_llm_service_mixing(self, provider: Any, provider_name: str, metadata: Optional[JSONDict]) -> None:
        """Validate that mock and real LLM services are not mixed."""
        existing_providers = self._services[ServiceType.LLM]
        is_mock = self._is_mock_service(provider, metadata)

        for existing in existing_providers:
            existing_is_mock = self._is_mock_service_provider(existing)
            if is_mock != existing_is_mock:
                error_msg = self._build_llm_mixing_error(is_mock, existing_is_mock, existing.name, provider_name)
                logger.error(error_msg)
                raise RuntimeError(error_msg)

    def _is_mock_service(self, provider: Any, metadata: Optional[JSONDict]) -> bool:
        """Check if a service is a mock service."""
        return "Mock" in provider.__class__.__name__ or (metadata is not None and metadata.get("provider") == "mock")

    def _is_mock_service_provider(self, provider: ServiceProvider[Any]) -> bool:
        """Check if a service provider wraps a mock service."""
        has_mock_in_name = "Mock" in provider.name
        has_mock_metadata = provider.metadata.get("provider") == "mock" if provider.metadata else False
        return has_mock_in_name or has_mock_metadata

    def _build_llm_mixing_error(
        self, is_mock: bool, existing_is_mock: bool, existing_name: str, provider_name: str
    ) -> str:
        """Build error message for LLM service mixing."""
        return (
            f"SECURITY VIOLATION: Attempting to register {'mock' if is_mock else 'real'} "
            f"LLM service when {'mock' if existing_is_mock else 'real'} service already exists! "
            f"Existing: {existing_name}, New: {provider_name}"
        )

    def _create_service_provider(
        self,
        service_type: ServiceType,
        name: str,
        instance: T_Service,
        priority: Priority,
        capabilities: Optional[List[str]],
        circuit_breaker_config: Optional[CircuitBreakerConfig],
        metadata: Optional[JSONDict],
        priority_group: int,
        strategy: SelectionStrategy,
    ) -> ServiceProvider[T_Service]:
        """Create a service provider with circuit breaker."""
        cb_config = circuit_breaker_config or CircuitBreakerConfig()
        circuit_breaker = CircuitBreaker(f"{service_type}_{name}", cb_config)
        self._circuit_breakers[name] = circuit_breaker

        return ServiceProvider(
            name=name,
            priority=priority,
            instance=instance,
            capabilities=capabilities or [],
            circuit_breaker=circuit_breaker,
            metadata=metadata or {},
            priority_group=priority_group,
            strategy=strategy,
        )

    def _register_and_sort(
        self,
        service_type: ServiceType,
        sp: ServiceProvider[Any],
        provider_name: str,
        priority: Priority,
        capabilities: Optional[List[str]],
    ) -> None:
        """Register service provider and track metrics."""
        self._services[service_type].append(sp)
        self._services[service_type].sort(key=lambda x: x.priority.value)
        self._registrations_total += 1

        logger.info(
            f"Registered {service_type} service '{provider_name}' "
            f"with priority {priority.name} and capabilities {capabilities}"
        )

    # register_global removed - all services are global now, use register_service()

    async def get_service(
        self, handler: str, service_type: ServiceType, required_capabilities: Optional[List[str]] = None
    ) -> Optional[Any]:
        """
        Get the best available service.

        Args:
            handler: Handler requesting the service
            service_type: Type of service needed
            required_capabilities: Required capabilities

        Returns:
            Service instance or None if no suitable service available
        """
        self._service_lookups += 1

        logger.debug(
            f"ServiceRegistry.get_service: service_type='{service_type}' "
            f"({service_type.value if hasattr(service_type, 'value') else service_type}), "
            f"capabilities={required_capabilities}"
        )

        # All services are global now
        # Debug: log all keys in _services
        logger.debug(f"ServiceRegistry._services keys: {list(self._services.keys())}")
        providers = self._services.get(service_type, [])
        logger.debug(
            f"ServiceRegistry: Looking for {service_type} (type: {type(service_type)}), found {len(providers)} providers"
        )

        if service_type in self._services:
            for provider in self._services[service_type]:
                logger.debug(f"  - Provider: {provider.name}, capabilities: {provider.capabilities}")

        service = await self._get_service_from_providers(providers, required_capabilities)

        if service is not None:
            self._service_hits += 1
            logger.debug(f"Using {service_type} service: {type(service).__name__}")
            return service

        self._service_misses += 1
        logger.warning(f"No available {service_type.value} service found " f"with capabilities {required_capabilities}")
        return None

    async def _get_service_from_providers(
        self, providers: List[ServiceProvider[Any]], required_capabilities: Optional[List[str]] = None
    ) -> Optional[Any]:
        """Get service from a list of providers with health checking and priority groups."""

        grouped: Dict[int, List[ServiceProvider[Any]]] = {}
        for p in providers:
            grouped.setdefault(p.priority_group, []).append(p)

        for group in sorted(grouped.keys(), key=lambda x: (x is None, x)):
            group_providers = sorted(grouped[group], key=lambda x: x.priority.value)
            if not group_providers:
                continue

            strategy = group_providers[0].strategy

            if strategy == SelectionStrategy.ROUND_ROBIN:
                key = f"{group}:{group_providers[0].instance.__class__.__name__}"
                idx = self._rr_state.get(key, 0)
                for _ in range(len(group_providers)):
                    provider = group_providers[idx]
                    svc = await self._validate_provider(provider, required_capabilities)
                    if svc is not None:
                        self._rr_state[key] = (idx + 1) % len(group_providers)
                        return svc
                    idx = (idx + 1) % len(group_providers)
            else:  # Fallback/first
                for provider in group_providers:
                    svc = await self._validate_provider(provider, required_capabilities)
                    if svc is not None:
                        return svc

        return None

    async def _validate_provider(
        self,
        provider: ServiceProvider[Any],
        required_capabilities: Optional[List[str]] = None,
    ) -> Optional[Any]:
        """Validate provider availability and return instance if usable."""
        if required_capabilities:
            logger.debug(
                f"Checking provider '{provider.name}' - has capabilities: {provider.capabilities}, needs: {required_capabilities}"
            )
            if not all(cap in provider.capabilities for cap in required_capabilities):
                logger.debug(
                    f"Provider '{provider.name}' missing capabilities: "
                    f"{set(required_capabilities) - set(provider.capabilities)}"
                )
                return None

        if provider.circuit_breaker and not provider.circuit_breaker.is_available():
            logger.debug(f"Provider '{provider.name}' circuit breaker is open")
            return None

        try:
            # Skip health checks during shutdown to prevent false failures
            if hasattr(self, "_shutdown_mode") and self._shutdown_mode:
                logger.debug(f"Skipping health check for '{provider.name}' during shutdown")
            elif hasattr(provider.instance, "is_healthy"):
                try:
                    is_healthy_result = await provider.instance.is_healthy()
                    if not is_healthy_result:
                        self._health_check_failures += 1
                        logger.debug(f"Provider '{provider.name}' failed health check (returned {is_healthy_result})")
                        if provider.circuit_breaker:
                            provider.circuit_breaker.record_failure()
                        return None
                except Exception as health_error:
                    logger.warning(f"Provider '{provider.name}' health check raised exception: {health_error}")
                    if provider.circuit_breaker:
                        provider.circuit_breaker.record_failure()
                    return None

            if provider.circuit_breaker:
                provider.circuit_breaker.record_success()
            logger.debug(f"Selected provider '{provider.name}' with priority {provider.priority.name}")
            return provider.instance

        except Exception as e:  # noqa: BLE001
            logger.warning(f"Error checking provider '{provider.name}': {e}")
            if provider.circuit_breaker:
                provider.circuit_breaker.record_failure()
            return None

    def get_circuit_breaker_details(self) -> JSONDict:
        """Get detailed circuit breaker information for all services."""
        cb_details = {}

        # Iterate through all services and their providers
        for service_type, providers in self._services.items():
            for provider in providers:
                if provider.circuit_breaker:
                    cb_name = f"{service_type.value}.{provider.name}"
                    cb_details[cb_name] = {
                        "state": provider.circuit_breaker.state.value,
                        "failure_count": provider.circuit_breaker.failure_count,
                        "success_count": provider.circuit_breaker.success_count,
                        "last_failure_time": provider.circuit_breaker.last_failure_time,
                        "consecutive_failures": provider.circuit_breaker.consecutive_failures,
                        "stats": provider.circuit_breaker.get_stats(),
                    }

        return cast(JSONDict, cb_details)

    def get_provider_info(self, handler: Optional[str] = None, service_type: Optional[str] = None) -> dict[str, Any]:
        """
        Get information about registered providers.

        Args:
            handler: Optional handler filter (kept for compatibility, ignored)
            service_type: Optional service type filter

        Returns:
            Dictionary containing provider information
        """
        info: dict[str, Any] = {"services": {}, "circuit_breaker_stats": {}, "circuit_breakers": {}}

        # All services are global now
        for st, providers in self._services.items():
            if service_type and st != service_type:
                continue
            info["services"][st] = [
                {
                    "name": p.name,
                    "priority": p.priority.name,
                    "priority_group": p.priority_group,
                    "strategy": p.strategy.value,
                    "capabilities": p.capabilities,
                    "metadata": p.metadata,
                    "circuit_breaker_state": p.circuit_breaker.state.value if p.circuit_breaker else None,
                }
                for p in providers
            ]

        # Circuit breaker stats
        for name, cb in self._circuit_breakers.items():
            info["circuit_breaker_stats"][name] = cb.get_stats()

        # Add detailed circuit breaker information
        info["circuit_breakers"] = self.get_circuit_breaker_details()

        return info

    def unregister(self, provider_name: str) -> bool:
        """
        Unregister a service provider.

        Args:
            provider_name: Name returned from register_service() call

        Returns:
            True if provider was found and removed
        """
        # Remove from services
        for service_type, providers in self._services.items():
            for i, provider in enumerate(providers):
                if provider.name == provider_name:
                    providers.pop(i)

                    # Track deregistration metric
                    self._deregistrations_total += 1

                    logger.info(f"Unregistered {service_type} provider '{provider_name}'")

                    # Remove circuit breaker
                    if provider_name in self._circuit_breakers:
                        del self._circuit_breakers[provider_name]
                    return True

        return False

    def get_services(
        self,
        service_type: ServiceType,
        required_capabilities: Optional[List[str]] = None,
        limit: Optional[int] = None,
    ) -> List[Any]:
        """
        Return multiple healthy providers matching capabilities.

        Args:
            service_type: Type of service to retrieve
            required_capabilities: Optional list of required capabilities
            limit: Maximum number of services to return

        Returns:
            List of service instances matching criteria
        """
        providers = self._services.get(service_type, [])
        results = []

        for p in sorted(providers, key=lambda x: (x.priority_group, x.priority.value)):
            # Check if provider is healthy
            if p.circuit_breaker and not p.circuit_breaker.is_available():
                continue

            # Check capabilities if specified
            if required_capabilities:
                if not p.capabilities:
                    continue
                if not all(cap in p.capabilities for cap in required_capabilities):
                    continue

            results.append(p.instance)
            if limit and len(results) >= limit:
                break

        return results

    def get_services_by_type(self, service_type: Union[str, ServiceType]) -> List[Any]:
        """
        Get ALL services of a given type (for broadcasting/aggregation).

        Args:
            service_type: Type of service as string (e.g., 'audit', 'tool') or ServiceType enum

        Returns:
            List of all service instances of that type
        """
        # Ensure we have a ServiceType enum
        if isinstance(service_type, str):
            try:
                resolved_type = ServiceType(service_type)
            except ValueError:
                logger.warning(f"Unknown service type: {service_type}")
                return []
        else:
            # mypy doesn't understand the Union narrowing here, but this is safe
            resolved_type = cast(ServiceType, service_type)

        all_services = []

        # Collect from global registrations
        if resolved_type in self._services:
            for provider in self._services[resolved_type]:
                # Only include healthy services
                # Include if no circuit breaker OR circuit breaker is available
                if not provider.circuit_breaker or provider.circuit_breaker.is_available():
                    if provider.instance not in all_services:
                        all_services.append(provider.instance)

        logger.debug(f"Found {len(all_services)} healthy {service_type} services for broadcasting/aggregation")
        return all_services

    def reset_circuit_breakers(self) -> None:
        """Reset all circuit breakers to closed state"""
        for cb in self._circuit_breakers.values():
            cb.reset()
        logger.info("Reset all circuit breakers")

    def get_all_services(self) -> List[Any]:
        """Get all registered services across all types."""
        all_services = []
        seen = set()  # Track service IDs to avoid duplicates

        for service_type, providers in self._services.items():
            for provider in providers:
                service_id = id(provider.instance)
                if service_id not in seen:
                    seen.add(service_id)
                    all_services.append(provider.instance)

        logger.debug(f"Found {len(all_services)} total registered services")
        return all_services

    def clear_all(self) -> None:
        """Clear all registered services and circuit breakers"""
        self._services.clear()
        self._circuit_breakers.clear()
        logger.info("Cleared all services from registry")

    async def wait_ready(
        self,
        timeout: float = 30.0,
        service_types: Optional[List[ServiceType]] = None,
    ) -> bool:
        """Wait for required services to be registered.

        Args:
            timeout: Maximum seconds to wait.
            service_types: Optional override of required service types.

        Returns:
            True if all required services are present, False if timeout expired.
        """
        required = set(service_types or self._required_service_types)
        if not required:
            return True

        start = asyncio.get_event_loop().time()
        while True:
            missing = {svc for svc in required if not self._has_service_type(svc)}
            if not missing:
                logger.info("Service registry ready: all services registered")
                return True

            if asyncio.get_event_loop().time() - start >= timeout:
                logger.error(
                    "Service registry readiness timeout. Missing services: %s",
                    ", ".join(sorted(missing)),
                )
                return False

            await asyncio.sleep(0.1)

    def _has_service_type(self, service_type: ServiceType) -> bool:
        """Check if any provider exists for the given service type."""
        return bool(self._services.get(service_type))

    def get_metrics(self) -> Dict[str, float]:
        """Get all service registry metrics including detailed stats."""
        # Calculate total services registered
        total_services = sum(len(providers) for providers in self._services.values())

        # Calculate service types count
        service_types = len(self._services)

        # Count circuit breakers
        circuit_breakers = 0
        open_breakers = 0
        for service_type, providers in self._services.items():
            for provider in providers:
                if provider.circuit_breaker:
                    circuit_breakers += 1
                    if provider.circuit_breaker.state == CircuitState.OPEN:
                        open_breakers += 1

        # Track max open breakers
        if open_breakers > self._circuit_breaker_opens:
            self._circuit_breaker_opens = open_breakers

        # Calculate hit rate
        hit_rate = 0.0
        if self._service_lookups > 0:
            hit_rate = self._service_hits / self._service_lookups

        return {
            # Required for telemetry health detection
            "healthy": True,
            # Registry doesn't track uptime - that's processor's job
            # Test-expected metric names
            "registry_total_services": float(total_services),
            "registry_service_types": float(service_types),
            "registry_circuit_breakers": float(circuit_breakers),
            "registry_open_breakers": float(open_breakers),
            "registry_service_lookups": float(self._service_lookups),
            "registry_service_hits": float(self._service_hits),
            "registry_service_misses": float(self._service_misses),
            "registry_hit_rate": hit_rate,
            "registry_health_check_failures": float(self._health_check_failures),
            "registry_max_open_breakers": float(self._circuit_breaker_opens),  # Track max opens as proxy
            # Also include v1.4.3 metrics
            "registry_services_registered": float(total_services),
            "registry_lookups_total": float(self._service_lookups),
            "registry_registrations_total": float(self._registrations_total),
            "registry_deregistrations_total": float(self._deregistrations_total),
        }


_global_registry: Optional[ServiceRegistry] = None


def get_global_registry() -> ServiceRegistry:
    """Get or create the global service registry instance"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ServiceRegistry()
    return _global_registry
