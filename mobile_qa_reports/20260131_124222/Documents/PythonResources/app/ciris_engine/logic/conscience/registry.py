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
    bypass_exemption: bool = False  # If True, runs even for exempt actions like TASK_COMPLETE


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
        bypass_exemption: bool = False,
    ) -> None:
        """Register a conscience with priority.

        Args:
            name: Unique name for this conscience
            conscience: The conscience implementation
            priority: Lower runs first (negative = before exemption check)
            enabled: Whether this conscience is active
            circuit_breaker_config: Circuit breaker settings
            bypass_exemption: If True, runs even for exempt actions (TASK_COMPLETE, etc.)
        """
        cb = CircuitBreaker(name, circuit_breaker_config or CircuitBreakerConfig())
        entry = conscienceEntry(name, conscience, priority, enabled, cb, bypass_exemption)
        self._entries[name] = entry

    def get_consciences(self) -> List[conscienceEntry]:
        """Return enabled consciences ordered by priority."""
        return sorted(
            [e for e in self._entries.values() if e.enabled],
            key=lambda e: e.priority,
        )

    def get_bypass_consciences(self) -> List[conscienceEntry]:
        """Return enabled consciences that bypass exemption checks, ordered by priority.

        These run even for exempt actions like TASK_COMPLETE, DEFER, REJECT.
        """
        return sorted(
            [e for e in self._entries.values() if e.enabled and e.bypass_exemption],
            key=lambda e: e.priority,
        )

    def get_normal_consciences(self) -> List[conscienceEntry]:
        """Return enabled consciences that respect exemption checks, ordered by priority."""
        return sorted(
            [e for e in self._entries.values() if e.enabled and not e.bypass_exemption],
            key=lambda e: e.priority,
        )

    def set_enabled(self, name: str, enabled: bool) -> None:
        if name in self._entries:
            self._entries[name].enabled = enabled
