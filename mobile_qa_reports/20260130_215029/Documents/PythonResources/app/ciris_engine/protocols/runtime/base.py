"""
Base protocols that all CIRIS components inherit from.

These form the foundation of the Protocol-Module-Schema architecture.
Every component in CIRIS must implement one of these base protocols.
"""

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Protocol

if TYPE_CHECKING:
    from ciris_engine.schemas.dma.core import DMAContext, DMADecision
    from ciris_engine.schemas.handlers.schemas import HandlerContext, HandlerResult
    from ciris_engine.schemas.runtime.adapter_management import AdapterConfig, RuntimeAdapterStatus
    from ciris_engine.schemas.runtime.enums import ServiceType
    from ciris_engine.schemas.runtime.models import Task, Thought
    from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
    from ciris_engine.schemas.services.graph_core import GraphNode
    from ciris_engine.schemas.services.operations import MemoryQuery
    from ciris_engine.schemas.services.visibility import VisibilitySnapshot


class ServiceProtocol(Protocol):
    """Root protocol for ALL services in CIRIS."""

    @abstractmethod
    async def start(self) -> None:
        """Start the service."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the service."""
        ...

    @abstractmethod
    def get_capabilities(self) -> "ServiceCapabilities":
        """Get service capabilities."""
        ...

    @abstractmethod
    def get_status(self) -> "ServiceStatus":
        """Get current service status."""
        ...

    @abstractmethod
    async def is_healthy(self) -> bool:
        """Check if service is healthy.

        Used by buses and registries for quick health checks.

        Returns:
            True if service is healthy and available
        """
        ...

    @abstractmethod
    def get_service_type(self) -> "ServiceType":
        """Get the type of this service.

        Returns:
            ServiceType enum indicating the service category
        """
        ...


class GraphServiceProtocol(ServiceProtocol, Protocol):
    """Base for services that store everything in the graph."""

    @abstractmethod
    async def store_in_graph(self, node: "GraphNode") -> str:
        """Store a node in the graph."""
        ...

    @abstractmethod
    async def query_graph(self, query: "MemoryQuery") -> List["GraphNode"]:
        """Query the graph."""
        ...

    @abstractmethod
    def get_node_type(self) -> str:
        """Get the type of nodes this service manages."""
        ...


class CoreServiceProtocol(ServiceProtocol, Protocol):
    """Base for services that cannot be stored in the graph."""

    @abstractmethod
    def get_resource_limits(self) -> Dict[str, int]:
        """Get resource limits for this service."""
        ...


class VisibilityServiceProtocol(ServiceProtocol, Protocol):
    """Base for services that provide transparency and compliance."""

    @abstractmethod
    async def get_visibility_data(self) -> "VisibilitySnapshot":  # Service-specific visibility data
        """Get visibility/transparency data."""
        ...


class BaseHandlerProtocol(Protocol):
    """Root protocol for all action handlers."""

    @abstractmethod
    async def handle(self, task: "Task", thought: "Thought", context: "HandlerContext") -> "HandlerResult":
        """Handle an action."""
        ...

    @abstractmethod
    def get_action_type(self) -> str:
        """Get the action type this handler processes."""
        ...


class BaseAdapterProtocol(Protocol):
    """Root protocol for all platform adapters."""

    @abstractmethod
    async def start(self) -> None:
        """Start the adapter."""
        ...

    @abstractmethod
    async def stop(self) -> None:
        """Stop the adapter."""
        ...

    @abstractmethod
    def get_config(self) -> "AdapterConfig":
        """Get adapter configuration."""
        ...

    @abstractmethod
    def get_status(self) -> "RuntimeAdapterStatus":
        """Get adapter status."""
        ...

    @abstractmethod
    def get_services_to_register(self) -> List[Any]:
        """Get list of services this adapter provides."""
        ...

    @abstractmethod
    async def run_lifecycle(self, agent_task: Any) -> None:
        """Run the adapter lifecycle."""
        ...


class BaseDMAProtocol(Protocol):
    """Root protocol for Decision Making Algorithms."""

    @abstractmethod
    async def evaluate(self, context: "DMAContext") -> "DMADecision":
        """Evaluate a decision context."""
        ...

    @abstractmethod
    def get_algorithm_type(self) -> str:
        """Get the type of decision making algorithm."""
        ...
