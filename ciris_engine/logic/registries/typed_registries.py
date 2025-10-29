"""
Specialized Typed Registries for CIRIS Services

This module provides type-safe registry wrappers for each service type in CIRIS.
These specialized registries eliminate the need for cast() calls and provide
proper type inference throughout the codebase.

Architecture:
- Each registry is specialized for ONE service protocol type using Generic[T]
- Type safety is enforced at compile time via TypeVar
- All service lookups return properly typed instances
- Zero cast() calls or type: ignore needed at usage sites

Usage:
    # Create specialized registry
    memory_registry = MemoryRegistry()

    # Register with type safety
    service = MemoryService(...)
    memory_registry.register("memory", service)

    # Get with proper return type (no cast needed!)
    service = await memory_registry.get("memory")  # Returns Optional[MemoryServiceProtocol]
"""

from typing import TYPE_CHECKING, Generic, List, Optional, TypeVar, cast

from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from .base import Priority, SelectionStrategy, ServiceRegistry
from .circuit_breaker import CircuitBreakerConfig

if TYPE_CHECKING:
    from ciris_engine.protocols.services.governance.communication import CommunicationServiceProtocol
    from ciris_engine.protocols.services.governance.wise_authority import WiseAuthorityServiceProtocol
    from ciris_engine.protocols.services.graph.memory import MemoryServiceProtocol
    from ciris_engine.protocols.services.runtime.llm import LLMServiceProtocol
    from ciris_engine.protocols.services.runtime.runtime_control import RuntimeControlServiceProtocol
    from ciris_engine.protocols.services.runtime.tool import ToolServiceProtocol


T_Service = TypeVar("T_Service")


class TypedServiceRegistry(Generic[T_Service]):
    """
    Base class for typed service registries using Generic[T].

    Provides type-safe wrappers around ServiceRegistry for a specific service type.
    Uses composition instead of inheritance to avoid Liskov substitution issues.
    """

    def __init__(self, service_type: ServiceType, registry: Optional[ServiceRegistry] = None) -> None:
        """
        Initialize typed registry.

        Args:
            service_type: The service type this registry manages
            registry: Optional existing ServiceRegistry instance (creates new if None)
        """
        self._service_type = service_type
        self._registry = registry if registry is not None else ServiceRegistry()

    def register(
        self,
        name: str,
        provider: T_Service,
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[JSONDict] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """
        Register a service provider with type safety.

        Args:
            name: Logical name for this registration (ignored, auto-generated)
            provider: Service instance (must match protocol type)
            priority: Service priority for fallback ordering
            capabilities: List of capabilities this service provides
            circuit_breaker_config: Optional circuit breaker configuration
            metadata: Additional metadata
            priority_group: Priority group for grouping providers
            strategy: Selection strategy within priority group

        Returns:
            str: Unique provider name for later reference
        """
        return self._registry.register_service(
            service_type=self._service_type,
            provider=provider,
            priority=priority,
            capabilities=capabilities,
            circuit_breaker_config=circuit_breaker_config,
            metadata=metadata,
            priority_group=priority_group,
            strategy=strategy,
        )

    async def get(
        self, handler: str = "default", required_capabilities: Optional[List[str]] = None
    ) -> Optional[T_Service]:
        """
        Get the best available service with type safety.

        Args:
            handler: Handler requesting the service
            required_capabilities: Required capabilities

        Returns:
            Service instance matching protocol type, or None if unavailable
        """
        result = await self._registry.get_service(
            handler=handler, service_type=self._service_type, required_capabilities=required_capabilities
        )
        return cast(Optional[T_Service], result)

    def get_all(
        self, required_capabilities: Optional[List[str]] = None, limit: Optional[int] = None
    ) -> List[T_Service]:
        """
        Get multiple services with type safety.

        Args:
            required_capabilities: Required capabilities
            limit: Maximum number of services to return

        Returns:
            List of service instances matching protocol type
        """
        result = self._registry.get_services(
            service_type=self._service_type, required_capabilities=required_capabilities, limit=limit
        )
        return cast(List[T_Service], result)


if TYPE_CHECKING:
    # Type aliases for concrete registries (provides better IDE support)
    MemoryRegistry = TypedServiceRegistry["MemoryServiceProtocol"]
    LLMRegistry = TypedServiceRegistry["LLMServiceProtocol"]
    CommunicationRegistry = TypedServiceRegistry["CommunicationServiceProtocol"]
    ToolRegistry = TypedServiceRegistry["ToolServiceProtocol"]
    RuntimeControlRegistry = TypedServiceRegistry["RuntimeControlServiceProtocol"]
    WiseRegistry = TypedServiceRegistry["WiseAuthorityServiceProtocol"]
else:
    # Runtime: Create concrete class wrappers for convenience
    class MemoryRegistry(TypedServiceRegistry["MemoryServiceProtocol"]):
        """Type-safe registry for memory services."""

        def __init__(self, registry: Optional[ServiceRegistry] = None) -> None:
            super().__init__(ServiceType.MEMORY, registry)

    class LLMRegistry(TypedServiceRegistry["LLMServiceProtocol"]):
        """Type-safe registry for LLM services."""

        def __init__(self, registry: Optional[ServiceRegistry] = None) -> None:
            super().__init__(ServiceType.LLM, registry)

    class CommunicationRegistry(TypedServiceRegistry["CommunicationServiceProtocol"]):
        """Type-safe registry for communication services (adapter-provided)."""

        def __init__(self, registry: Optional[ServiceRegistry] = None) -> None:
            super().__init__(ServiceType.COMMUNICATION, registry)

    class ToolRegistry(TypedServiceRegistry["ToolServiceProtocol"]):
        """Type-safe registry for tool services (adapter-provided)."""

        def __init__(self, registry: Optional[ServiceRegistry] = None) -> None:
            super().__init__(ServiceType.TOOL, registry)

    class RuntimeControlRegistry(TypedServiceRegistry["RuntimeControlServiceProtocol"]):
        """Type-safe registry for runtime control services (adapter-provided)."""

        def __init__(self, registry: Optional[ServiceRegistry] = None) -> None:
            super().__init__(ServiceType.RUNTIME_CONTROL, registry)

    class WiseRegistry(TypedServiceRegistry["WiseAuthorityServiceProtocol"]):
        """Type-safe registry for wise authority services."""

        def __init__(self, registry: Optional[ServiceRegistry] = None) -> None:
            super().__init__(ServiceType.WISE_AUTHORITY, registry)
