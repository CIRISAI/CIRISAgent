from typing import Optional, Protocol, runtime_checkable


@runtime_checkable
class RuntimeInterface(Protocol):
    """
    Protocol for CIRIS runtimes.

    Note: Do not inherit from this Protocol. Instead, implement the methods
    and use isinstance() checks with @runtime_checkable to verify compliance.
    """

    async def initialize(self) -> None:
        """Initialize runtime and all services."""
        ...

    async def run(self, num_rounds: Optional[int] = None) -> None:
        """Run the agent processing loop."""
        ...

    async def shutdown(self) -> None:
        """Gracefully shutdown all services."""
        ...
