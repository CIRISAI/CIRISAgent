"""Initialization Service Protocol."""

from abc import abstractmethod
from typing import Awaitable, Callable, Optional, Protocol

from ciris_engine.schemas.services.lifecycle.initialization import InitializationStatus, InitializationVerification
from ciris_engine.schemas.services.operations import InitializationPhase

from ...runtime.base import ServiceProtocol


class InitializationServiceProtocol(ServiceProtocol, Protocol):
    """Protocol for initialization service."""

    @abstractmethod
    def register_step(
        self,
        phase: InitializationPhase,
        name: str,
        handler: Callable[[], Awaitable[None]],
        verifier: Optional[Callable[[], Awaitable[bool]]] = None,
        critical: bool = True,
        timeout: float = 30.0,
    ) -> None:
        """Register an initialization step."""
        ...

    @abstractmethod
    async def initialize(self) -> bool:
        """Initialize the entire system."""
        ...

    @abstractmethod
    async def verify_initialization(self) -> InitializationVerification:
        """Verify all components are initialized."""
        ...

    @abstractmethod
    async def get_initialization_status(self) -> InitializationStatus:
        """Get detailed initialization status."""
        ...
