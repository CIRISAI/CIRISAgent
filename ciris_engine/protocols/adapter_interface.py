import asyncio
import dataclasses
from typing import Any, List, Protocol, runtime_checkable

from ciris_engine.registries.base import Priority, SelectionStrategy
from ciris_engine.adapters.base import Service
from ciris_engine.schemas.foundational_schemas_v1 import ServiceType

class RuntimeInterface(Protocol):
    """Protocol for the CIRIS runtime interface."""
    pass

@dataclasses.dataclass(frozen=True)
class ServiceRegistration:
    """A schema-aligned descriptor for a service provided by an adapter."""
    service_type: ServiceType
    provider: Service
    priority: Priority = Priority.NORMAL
    handlers: List[str] = dataclasses.field(default_factory=list)
    capabilities: List[str] = dataclasses.field(default_factory=list)
    priority_group: int = 0
    strategy: SelectionStrategy = SelectionStrategy.FALLBACK

@runtime_checkable
class PlatformAdapter(Protocol):
    """
    The unified, schema-aligned protocol for all modular adapters,
    responsible for both inbound (listening) and outbound (acting) logic.
    """

    def __init__(self, runtime: "RuntimeInterface", **kwargs: Any) -> None:
        """Initializes the adapter with a reference to the core runtime."""
        ...

    def get_services_to_register(self) -> List[ServiceRegistration]:
        """Returns a list of all services this adapter provides."""
        ...

    async def start(self) -> None:
        """Starts any inbound listeners and performs async setup."""
        ...

    async def run_lifecycle(self, agent_run_task: asyncio.Task[Any]) -> None:
        """Manages the platform's main event loop concurrently with the agent task."""
        ...

    async def stop(self) -> None:
        """Performs graceful shutdown of all adapter-specific components."""
        ...
