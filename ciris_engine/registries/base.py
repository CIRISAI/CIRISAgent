"""
Base Registry System

Provides unified registration and discovery for services, adapters, and tools
with priority-based fallbacks and circuit breaker patterns for resilience.
"""

from typing import Dict, List, Any, Optional, Protocol, Union
from dataclasses import dataclass
from enum import Enum
import logging
import asyncio

from .circuit_breaker import CircuitBreaker, CircuitBreakerConfig
from ciris_engine.schemas.foundational_schemas_v1 import ServiceType

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

@dataclass
class ServiceProvider:
    """Represents a registered service provider with metadata"""
    name: str
    priority: Priority
    instance: Any
    capabilities: List[str]
    circuit_breaker: Optional[CircuitBreaker] = None
    metadata: Optional[Dict[str, Any]] = None
    priority_group: int = 0
    strategy: SelectionStrategy = SelectionStrategy.FALLBACK

class HealthCheckProtocol(Protocol):
    """Protocol for services that support health checking"""
    async def is_healthy(self) -> bool:
        """Check if the service is healthy and ready to handle requests"""
        ...

class ServiceRegistry:
    """
    Central registry for all services with priority/fallback support.
    
    Manages service registration, discovery, and health monitoring with
    circuit breaker patterns for resilience.
    """
    
    def __init__(self, required_services: Optional[List[ServiceType]] = None) -> None:
        self._providers: Dict[str, Dict[ServiceType, List[ServiceProvider]]] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._global_services: Dict[ServiceType, List[ServiceProvider]] = {}
        self._rr_state: Dict[str, int] = {}
        self._required_service_types: List[ServiceType] = required_services or [
            ServiceType.COMMUNICATION,
            ServiceType.MEMORY,
            ServiceType.AUDIT,
            ServiceType.LLM,
        ]
    
    def register(
        self,
        handler: str,
        service_type: ServiceType,
        provider: Any,
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[Dict[str, Any]] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """
        Register a service provider for a specific handler.
        
        Args:
            handler: Handler name that will use this service
            service_type: Type of service (e.g., 'llm', 'memory', 'audit')
            provider: Service instance
            priority: Service priority for fallback ordering
            capabilities: List of capabilities this service provides
            circuit_breaker_config: Optional custom circuit breaker config
            metadata: Additional metadata for the service
            
        Returns:
            str: Unique provider name for later reference
        """
        if handler not in self._providers:
            self._providers[handler] = {}
        if service_type not in self._providers[handler]:
            self._providers[handler][service_type] = []
        
        provider_name = f"{provider.__class__.__name__}_{id(provider)}"
        
        cb_config = circuit_breaker_config or CircuitBreakerConfig()
        circuit_breaker = CircuitBreaker(f"{handler}_{service_type}_{provider_name}", cb_config)
        self._circuit_breakers[provider_name] = circuit_breaker
        
        sp = ServiceProvider(
            name=provider_name,
            priority=priority,
            instance=provider,
            capabilities=capabilities or [],
            circuit_breaker=circuit_breaker,
            metadata=metadata or {},
            priority_group=priority_group,
            strategy=strategy,
        )
        
        self._providers[handler][service_type].append(sp)
        self._providers[handler][service_type].sort(key=lambda x: x.priority.value)
        
        logger.info(f"Registered {service_type} service '{provider_name}' for handler '{handler}' "
                   f"with priority {priority.name} and capabilities {capabilities}")
        
        logger.debug(f"ServiceRegistry: Handler '{handler}' now has {len(self._providers[handler][service_type])} "
                    f"{service_type} providers: {[p.name for p in self._providers[handler][service_type]]}")
        
        return provider_name
    
    def register_global(
        self,
        service_type: ServiceType,
        provider: Any,
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[Dict[str, Any]] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """
        Register a global service provider available to all handlers.
        
        Args:
            service_type: Type of service
            provider: Service instance
            priority: Service priority
            capabilities: List of capabilities
            circuit_breaker_config: Optional circuit breaker config
            metadata: Additional metadata
            
        Returns:
            str: Unique provider name
        """
        if service_type not in self._global_services:
            self._global_services[service_type] = []
        
        provider_name = f"global_{provider.__class__.__name__}_{id(provider)}"
        
        cb_config = circuit_breaker_config or CircuitBreakerConfig()
        circuit_breaker = CircuitBreaker(f"global_{service_type}_{provider_name}", cb_config)
        self._circuit_breakers[provider_name] = circuit_breaker
        
        sp = ServiceProvider(
            name=provider_name,
            priority=priority,
            instance=provider,
            capabilities=capabilities or [],
            circuit_breaker=circuit_breaker,
            metadata=metadata or {},
            priority_group=priority_group,
            strategy=strategy,
        )
        
        self._global_services[service_type].append(sp)
        self._global_services[service_type].sort(key=lambda x: x.priority.value)
        
        logger.info(f"Registered global {service_type} service '{provider_name}' "
                   f"with priority {priority.name}")
        
        return provider_name
    
    async def get_service(
        self, 
        handler: str, 
        service_type: ServiceType,
        required_capabilities: Optional[List[str]] = None,
        fallback_to_global: bool = True
    ) -> Optional[Any]:
        """
        Get the best available service with fallback support.
        
        Args:
            handler: Handler requesting the service
            service_type: Type of service needed
            required_capabilities: Required capabilities
            fallback_to_global: Whether to fallback to global services
            
        Returns:
            Service instance or None if no suitable service available
        """
        logger.debug(f"ServiceRegistry.get_service: handler='{handler}', service_type='{service_type}' "
                    f"({service_type.value if hasattr(service_type, 'value') else service_type}), "
                    f"capabilities={required_capabilities}")
        
        handler_providers = self._providers.get(handler, {}).get(service_type, [])
        logger.debug(f"ServiceRegistry: Found {len(handler_providers)} handler-specific providers for {handler}.{service_type.value if hasattr(service_type, 'value') else service_type}")
        
        service = await self._get_service_from_providers(
            handler_providers,
            required_capabilities
        )
        
        if service is not None:
            logger.debug(f"ServiceRegistry: Using handler-specific {service_type} service for '{handler}': {type(service).__name__}")
            return service
        
        if fallback_to_global:
            global_providers = self._global_services.get(service_type, [])
            logger.debug(f"ServiceRegistry: Found {len(global_providers)} global providers for {service_type}")
            
            service = await self._get_service_from_providers(
                global_providers,
                required_capabilities
            )
            
            if service is not None:
                logger.debug(f"Using global {service_type} service for handler '{handler}': {type(service).__name__}")
                return service
        
        logger.warning(f"No available {service_type.value} service found for handler '{handler}' "
                      f"with capabilities {required_capabilities}")
        return None
    
    async def _get_service_from_providers(
        self,
        providers: List[ServiceProvider],
        required_capabilities: Optional[List[str]] = None
    ) -> Optional[Any]:
        """Get service from a list of providers with health checking and priority groups."""

        grouped: Dict[int, List[ServiceProvider]] = {}
        for p in providers:
            grouped.setdefault(p.priority_group, []).append(p)

        for group in sorted(grouped.keys()):
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
        provider: ServiceProvider,
        required_capabilities: Optional[List[str]] = None,
    ) -> Optional[Any]:
        """Validate provider availability and return instance if usable."""
        if required_capabilities:
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
            if hasattr(provider.instance, "is_healthy"):
                if not await provider.instance.is_healthy():
                    logger.debug(f"Provider '{provider.name}' failed health check")
                    if provider.circuit_breaker:
                        provider.circuit_breaker.record_failure()
                    return None

            if provider.circuit_breaker:
                provider.circuit_breaker.record_success()
            logger.debug(
                f"Selected provider '{provider.name}' with priority {provider.priority.name}"
            )
            return provider.instance

        except Exception as e:  # noqa: BLE001
            logger.warning(f"Error checking provider '{provider.name}': {e}")
            if provider.circuit_breaker:
                provider.circuit_breaker.record_failure()
            return None
    
    def get_provider_info(self, handler: Optional[str] = None, service_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Get information about registered providers.
        
        Args:
            handler: Optional handler filter
            service_type: Optional service type filter
            
        Returns:
            Dictionary containing provider information
        """
        info: Dict[str, Any] = {
            "handlers": {},
            "global_services": {},
            "circuit_breaker_stats": {}
        }
        
        # Handler-specific services
        for h, services in self._providers.items():
            if handler and h != handler:
                continue
            info["handlers"][h] = {}
            
            for st, providers in services.items():
                if service_type and st != service_type:
                    continue
                info["handlers"][h][st] = [
                    {
                        "name": p.name,
                        "priority": p.priority.name,
                        "priority_group": p.priority_group,
                        "strategy": p.strategy.value,
                        "capabilities": p.capabilities,
                        "metadata": p.metadata,
                        "circuit_breaker_state": p.circuit_breaker.state.value if p.circuit_breaker else None
                    }
                    for p in providers
                ]
        
        # Global services
        for st, providers in self._global_services.items():
            if service_type and st != service_type:
                continue
            info["global_services"][st] = [
                {
                    "name": p.name,
                    "priority": p.priority.name,
                    "priority_group": p.priority_group,
                    "strategy": p.strategy.value,
                    "capabilities": p.capabilities,
                    "metadata": p.metadata,
                    "circuit_breaker_state": p.circuit_breaker.state.value if p.circuit_breaker else None
                }
                for p in providers
            ]
        
        # Circuit breaker stats
        for name, cb in self._circuit_breakers.items():
            info["circuit_breaker_stats"][name] = cb.get_stats()
        
        return info
    
    def unregister(self, provider_name: str) -> bool:
        """
        Unregister a service provider.
        
        Args:
            provider_name: Name returned from register() call
            
        Returns:
            True if provider was found and removed
        """
        # Remove from handler-specific services
        for handler, services in self._providers.items():
            for service_type, providers in services.items():
                for i, provider in enumerate(providers):
                    if provider.name == provider_name:
                        providers.pop(i)
                        logger.info(f"Unregistered {service_type} provider '{provider_name}' "
                                  f"from handler '{handler}'")
                        break
        
        # Remove from global services
        for service_type, providers in self._global_services.items():
            for i, provider in enumerate(providers):
                if provider.name == provider_name:
                    providers.pop(i)
                    logger.info(f"Unregistered global {service_type} provider '{provider_name}'")
                    break
        
        # Remove circuit breaker
        if provider_name in self._circuit_breakers:
            del self._circuit_breakers[provider_name]
            return True
        
        return False
    
    def get_services_by_type(self, service_type: Union[str, ServiceType]) -> List[Any]:
        """
        Get ALL services of a given type (for broadcasting/aggregation).
        
        Args:
            service_type: Type of service as string (e.g., 'audit', 'tool')
            
        Returns:
            List of all service instances of that type
        """
        # Convert string to ServiceType enum if needed
        service_type_enum: ServiceType
        if isinstance(service_type, str):
            try:
                service_type_enum = ServiceType(service_type)
            except ValueError:
                logger.warning(f"Unknown service type: {service_type}")
                return []
        else:
            service_type_enum = service_type  # type: ignore[unreachable]
        
        all_services = []
        
        # Collect from handler-specific registrations
        for handler, services in self._providers.items():
            if service_type_enum in services:
                for provider in services[service_type_enum]:
                    # Only include healthy services
                    if provider.circuit_breaker and provider.circuit_breaker.is_available():
                        if provider.instance not in all_services:
                            all_services.append(provider.instance)
        
        # Collect from global registrations
        if service_type_enum in self._global_services:
            for provider in self._global_services[service_type_enum]:
                # Only include healthy services
                if provider.circuit_breaker and provider.circuit_breaker.is_available():
                    if provider.instance not in all_services:
                        all_services.append(provider.instance)
        
        logger.debug(f"Found {len(all_services)} healthy {service_type} services for broadcasting/aggregation")
        return all_services
    
    def reset_circuit_breakers(self) -> None:
        """Reset all circuit breakers to closed state"""
        for cb in self._circuit_breakers.values():
            cb.reset()
        logger.info("Reset all circuit breakers")
    
    def clear_all(self) -> None:
        """Clear all registered services and circuit breakers"""
        self._providers.clear()
        self._global_services.clear()
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
        if self._global_services.get(service_type):
            return True
        for services in self._providers.values():
            if services.get(service_type):
                return True
        return False

_global_registry: Optional[ServiceRegistry] = None

def get_global_registry() -> ServiceRegistry:
    """Get or create the global service registry instance"""
    global _global_registry
    if _global_registry is None:
        _global_registry = ServiceRegistry()
    return _global_registry
