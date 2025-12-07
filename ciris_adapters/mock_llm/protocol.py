"""
Protocol definition for MockLLM service.

This demonstrates how modular services define their own protocols
while implementing core CIRIS protocols.
"""

from typing import Protocol, runtime_checkable

# Import core protocol that we implement
from ciris_engine.protocols.services import LLMService


@runtime_checkable
class MockLLMProtocol(LLMService, Protocol):
    """
    MockLLM-specific protocol extensions.

    Inherits from core LLMService protocol and adds mock-specific capabilities.
    """

    # Mock-specific methods
    def set_response_delay(self, delay_ms: int) -> None:  # noqa: ARG002
        """Set simulated response delay."""
        ...

    def set_failure_rate(self, rate: float) -> None:
        """Set probability of simulated failures (0.0-1.0)."""
        ...

    def get_response_count(self) -> int:
        """Get number of responses generated."""
        ...

    def reset_mock_state(self) -> None:
        """Reset all mock state and counters."""
        ...
