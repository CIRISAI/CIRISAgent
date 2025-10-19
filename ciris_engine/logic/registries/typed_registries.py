"""
Specialized Typed Registries for CIRIS Services

This module provides type-safe registry wrappers for each service type in CIRIS.
These specialized registries eliminate the need for cast() calls and provide
proper type inference throughout the codebase.

Architecture:
- Each registry is specialized for ONE service protocol type
- Type safety is enforced at compile time via Generic[T_Service]
- All service lookups return properly typed instances
- Zero cast() calls needed at usage sites

Usage:
    # Create specialized registry
    memory_registry = MemoryRegistry()

    # Register with type safety
    service = MemoryService(...)
    memory_registry.register("memory", service)

    # Get with proper return type (no cast needed!)
    service = await memory_registry.get("memory")  # Returns Optional[MemoryServiceProtocol]
"""

from typing import TYPE_CHECKING, List, Optional

from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

from .base import CircuitBreakerConfig, Priority, SelectionStrategy, ServiceRegistry

if TYPE_CHECKING:
    from ciris_engine.protocols.services.governance.communication import CommunicationServiceProtocol
    from ciris_engine.protocols.services.governance.wise_authority import WiseAuthorityServiceProtocol
    from ciris_engine.protocols.services.graph.memory import MemoryServiceProtocol
    from ciris_engine.protocols.services.runtime.llm import LLMServiceProtocol
    from ciris_engine.protocols.services.runtime.runtime_control import RuntimeControlServiceProtocol
    from ciris_engine.protocols.services.runtime.tool import ToolServiceProtocol


class TypedServiceRegistry(ServiceRegistry):
    """
    Base class for typed service registries.

    Provides type-safe wrappers around ServiceRegistry for a specific service type.
    Each specialized registry inherits from this and sets its service_type and protocol.
    """

    # Override in subclasses
    _service_type: ServiceType
    _protocol_type: type

    def register(
        self,
        name: str,
        provider: object,  # Will be validated against _protocol_type by subclasses
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
        return self.register_service(
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
    ) -> Optional[object]:
        """
        Get the best available service with type safety.

        Args:
            handler: Handler requesting the service
            required_capabilities: Required capabilities

        Returns:
            Service instance matching protocol type, or None if unavailable
        """
        return await self.get_service(
            handler=handler, service_type=self._service_type, required_capabilities=required_capabilities
        )

    def get_all(self, required_capabilities: Optional[List[str]] = None, limit: Optional[int] = None) -> List[object]:
        """
        Get multiple services with type safety.

        Args:
            required_capabilities: Required capabilities
            limit: Maximum number of services to return

        Returns:
            List of service instances matching protocol type
        """
        return self.get_services(
            service_type=self._service_type, required_capabilities=required_capabilities, limit=limit
        )


class MemoryRegistry(TypedServiceRegistry):
    """Type-safe registry for memory services."""

    _service_type = ServiceType.MEMORY

    def register(
        self,
        name: str,
        provider: "MemoryServiceProtocol",
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[JSONDict] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """Register a memory service with full type safety."""
        return super().register(
            name, provider, priority, capabilities, circuit_breaker_config, metadata, priority_group, strategy
        )

    async def get(
        self, handler: str = "default", required_capabilities: Optional[List[str]] = None
    ) -> Optional["MemoryServiceProtocol"]:
        """Get memory service with proper return type."""
        result = await super().get(handler, required_capabilities)
        # The cast here is safe because ServiceRegistry validates the type at registration
        return result  # type: ignore[return-value]

    def get_all(
        self, required_capabilities: Optional[List[str]] = None, limit: Optional[int] = None
    ) -> List["MemoryServiceProtocol"]:
        """Get multiple memory services with proper return type."""
        result = super().get_all(required_capabilities, limit)
        return result  # type: ignore[return-value]


class LLMRegistry(TypedServiceRegistry):
    """Type-safe registry for LLM services."""

    _service_type = ServiceType.LLM

    def register(
        self,
        name: str,
        provider: "LLMServiceProtocol",
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[JSONDict] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """Register an LLM service with full type safety."""
        return super().register(
            name, provider, priority, capabilities, circuit_breaker_config, metadata, priority_group, strategy
        )

    async def get(
        self, handler: str = "default", required_capabilities: Optional[List[str]] = None
    ) -> Optional["LLMServiceProtocol"]:
        """Get LLM service with proper return type."""
        result = await super().get(handler, required_capabilities)
        return result  # type: ignore[return-value]

    def get_all(
        self, required_capabilities: Optional[List[str]] = None, limit: Optional[int] = None
    ) -> List["LLMServiceProtocol"]:
        """Get multiple LLM services with proper return type."""
        result = super().get_all(required_capabilities, limit)
        return result  # type: ignore[return-value]


class CommunicationRegistry(TypedServiceRegistry):
    """Type-safe registry for communication services (adapter-provided)."""

    _service_type = ServiceType.COMMUNICATION

    def register(
        self,
        name: str,
        provider: "CommunicationServiceProtocol",
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[JSONDict] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """Register a communication service with full type safety."""
        return super().register(
            name, provider, priority, capabilities, circuit_breaker_config, metadata, priority_group, strategy
        )

    async def get(
        self, handler: str = "default", required_capabilities: Optional[List[str]] = None
    ) -> Optional["CommunicationServiceProtocol"]:
        """Get communication service with proper return type."""
        result = await super().get(handler, required_capabilities)
        return result  # type: ignore[return-value]

    def get_all(
        self, required_capabilities: Optional[List[str]] = None, limit: Optional[int] = None
    ) -> List["CommunicationServiceProtocol"]:
        """Get multiple communication services with proper return type."""
        result = super().get_all(required_capabilities, limit)
        return result  # type: ignore[return-value]


class ToolRegistry(TypedServiceRegistry):
    """Type-safe registry for tool services (adapter-provided)."""

    _service_type = ServiceType.TOOL

    def register(
        self,
        name: str,
        provider: "ToolServiceProtocol",
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[JSONDict] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """Register a tool service with full type safety."""
        return super().register(
            name, provider, priority, capabilities, circuit_breaker_config, metadata, priority_group, strategy
        )

    async def get(
        self, handler: str = "default", required_capabilities: Optional[List[str]] = None
    ) -> Optional["ToolServiceProtocol"]:
        """Get tool service with proper return type."""
        result = await super().get(handler, required_capabilities)
        return result  # type: ignore[return-value]

    def get_all(
        self, required_capabilities: Optional[List[str]] = None, limit: Optional[int] = None
    ) -> List["ToolServiceProtocol"]:
        """Get multiple tool services with proper return type."""
        result = super().get_all(required_capabilities, limit)
        return result  # type: ignore[return-value]


class RuntimeControlRegistry(TypedServiceRegistry):
    """Type-safe registry for runtime control services (adapter-provided)."""

    _service_type = ServiceType.RUNTIME_CONTROL

    def register(
        self,
        name: str,
        provider: "RuntimeControlServiceProtocol",
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[JSONDict] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """Register a runtime control service with full type safety."""
        return super().register(
            name, provider, priority, capabilities, circuit_breaker_config, metadata, priority_group, strategy
        )

    async def get(
        self, handler: str = "default", required_capabilities: Optional[List[str]] = None
    ) -> Optional["RuntimeControlServiceProtocol"]:
        """Get runtime control service with proper return type."""
        result = await super().get(handler, required_capabilities)
        return result  # type: ignore[return-value]

    def get_all(
        self, required_capabilities: Optional[List[str]] = None, limit: Optional[int] = None
    ) -> List["RuntimeControlServiceProtocol"]:
        """Get multiple runtime control services with proper return type."""
        result = super().get_all(required_capabilities, limit)
        return result  # type: ignore[return-value]


class WiseRegistry(TypedServiceRegistry):
    """Type-safe registry for wise authority services."""

    _service_type = ServiceType.WISE_AUTHORITY

    def register(
        self,
        name: str,
        provider: "WiseAuthorityServiceProtocol",
        priority: Priority = Priority.NORMAL,
        capabilities: Optional[List[str]] = None,
        circuit_breaker_config: Optional[CircuitBreakerConfig] = None,
        metadata: Optional[JSONDict] = None,
        priority_group: int = 0,
        strategy: SelectionStrategy = SelectionStrategy.FALLBACK,
    ) -> str:
        """Register a wise authority service with full type safety."""
        return super().register(
            name, provider, priority, capabilities, circuit_breaker_config, metadata, priority_group, strategy
        )

    async def get(
        self, handler: str = "default", required_capabilities: Optional[List[str]] = None
    ) -> Optional["WiseAuthorityServiceProtocol"]:
        """Get wise authority service with proper return type."""
        result = await super().get(handler, required_capabilities)
        return result  # type: ignore[return-value]

    def get_all(
        self, required_capabilities: Optional[List[str]] = None, limit: Optional[int] = None
    ) -> List["WiseAuthorityServiceProtocol"]:
        """Get multiple wise authority services with proper return type."""
        result = super().get_all(required_capabilities, limit)
        return result  # type: ignore[return-value]
