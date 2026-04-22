"""
CIRIS Engine Registry System

Provides unified registration and discovery for services, adapters, and tools
with priority-based fallbacks and circuit breaker patterns for resilience.
"""

from .base import Priority, SelectionStrategy, ServiceProvider, ServiceRegistry
from .circuit_breaker import CircuitBreaker
from .typed_registries import (
    CommunicationRegistry,
    LLMRegistry,
    MemoryRegistry,
    RuntimeControlRegistry,
    ToolRegistry,
    TypedServiceRegistry,
    WiseRegistry,
)

__all__ = [
    "ServiceRegistry",
    "Priority",
    "SelectionStrategy",
    "ServiceProvider",
    "CircuitBreaker",
    # Typed registries
    "TypedServiceRegistry",
    "MemoryRegistry",
    "LLMRegistry",
    "CommunicationRegistry",
    "ToolRegistry",
    "RuntimeControlRegistry",
    "WiseRegistry",
]
