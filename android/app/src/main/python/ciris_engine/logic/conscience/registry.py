from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig

from .interface import ConscienceInterface


@dataclass
class conscienceEntry:
    name: str
    conscience: ConscienceInterface
    priority: int = 0
    enabled: bool = True
    circuit_breaker: CircuitBreaker | None = None


class conscienceRegistry:
    """Registry for dynamic conscience management."""

    def __init__(self) -> None:
        self._entries: Dict[str, conscienceEntry] = {}

    def register_conscience(
        self,
        name: str,
        conscience: ConscienceInterface,
        priority: int = 0,
        enabled: bool = True,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
    ) -> None:
        """Register a conscience with priority."""
        cb = CircuitBreaker(name, circuit_breaker_config or CircuitBreakerConfig())
        entry = conscienceEntry(name, conscience, priority, enabled, cb)
        self._entries[name] = entry

    def get_consciences(self) -> List[conscienceEntry]:
        """Return enabled consciences ordered by priority."""
        return sorted(
            [e for e in self._entries.values() if e.enabled],
            key=lambda e: e.priority,
        )

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name in self._entries:
            self._entries[name].enabled = enabled
