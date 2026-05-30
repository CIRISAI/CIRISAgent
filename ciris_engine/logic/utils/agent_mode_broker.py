"""
AgentModeBroker — lightweight pub/sub for global AgentMode transitions.

Not a service. The broker is a singleton utility (module-level instance) that
holds the in-memory current mode, persists mode changes via the graph
ConfigService when available, and broadcasts an ``AgentModeChangedEvent`` to
registered subscribers.

Reference invocation pattern (config persistence) — see
``ciris_engine/logic/services/governance/adaptive_filter/service.py`` for the
canonical ``GraphConfigService.set_config`` call shape.

Threading model:
- All public methods acquire a ``threading.Lock`` before touching state.
- Subscribers are invoked **outside** the lock to avoid re-entrancy deadlocks
  if a callback re-enters the broker.
- Each subscriber callback is shielded; a raising callback is logged and
  skipped so one bad subscriber cannot poison the broadcast.
"""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Callable, List, Optional

from ciris_engine.schemas.runtime.agent_mode import AgentMode, AgentModeChangedEvent

if TYPE_CHECKING:
    from ciris_engine.protocols.services.graph.config import GraphConfigServiceProtocol

logger = logging.getLogger(__name__)

# Key under which the broker persists the current mode.
AGENT_MODE_CONFIG_KEY = "agent.mode"

# Updated-by tag for set_config writes (matches existing convention — see
# adaptive_filter/service.py).
AGENT_MODE_UPDATER = "AgentModeBroker"

Subscriber = Callable[[AgentModeChangedEvent], None]


class AgentModeBroker:
    """In-memory broker for global AgentMode with persistence + pub/sub."""

    def __init__(self, initial_mode: AgentMode = AgentMode.PROXY) -> None:
        self._lock = threading.Lock()
        self._mode: AgentMode = initial_mode
        self._subscribers: List[Subscriber] = []
        self._config_service: Optional["GraphConfigServiceProtocol"] = None

    # ------------------------------------------------------------------ #
    # Wiring
    # ------------------------------------------------------------------ #

    def attach_config_service(self, config_service: "GraphConfigServiceProtocol") -> None:
        """Attach a GraphConfigService for persistence.

        Optional. If not attached, ``set_mode`` still updates in-memory state
        and broadcasts to subscribers but skips persistence.
        """
        with self._lock:
            self._config_service = config_service

    # ------------------------------------------------------------------ #
    # State accessors
    # ------------------------------------------------------------------ #

    def current_mode(self) -> AgentMode:
        """Return the currently active mode."""
        with self._lock:
            return self._mode

    # ------------------------------------------------------------------ #
    # Subscription
    # ------------------------------------------------------------------ #

    def subscribe(self, callback: Subscriber) -> None:
        """Register a subscriber.

        The callback is invoked synchronously on every successful mode
        transition. Callbacks must be cheap and non-blocking; long work
        should be deferred to a task.
        """
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Subscriber) -> None:
        """Unregister a previously-registered subscriber (no-op if absent)."""
        with self._lock:
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

    # ------------------------------------------------------------------ #
    # State mutation
    # ------------------------------------------------------------------ #

    async def set_mode(self, mode: AgentMode) -> AgentModeChangedEvent:
        """Transition to ``mode`` and broadcast the change.

        Persists the new value via ``GraphConfigService.set_config`` when a
        config service has been attached. Persistence failures are logged but
        do not abort the in-memory transition — callers that need strong
        durability should check the config service is attached first.

        Returns the broadcast event so callers can include it in audit/log
        without re-reading state.
        """
        # 1) Capture transition under lock.
        with self._lock:
            previous_mode = self._mode
            self._mode = mode
            subscribers_snapshot = list(self._subscribers)
            config_service = self._config_service

        event = AgentModeChangedEvent(
            previous_mode=previous_mode,
            new_mode=mode,
            timestamp=datetime.now(timezone.utc),
        )

        # 2) Persist outside the lock. set_config is async.
        if config_service is not None:
            try:
                await config_service.set_config(
                    key=AGENT_MODE_CONFIG_KEY,
                    value=mode.value,
                    updated_by=AGENT_MODE_UPDATER,
                )
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "AgentModeBroker: failed to persist mode transition " "%s -> %s: %s",
                    previous_mode.value,
                    mode.value,
                    exc,
                )

        # 3) Broadcast outside the lock. A raising subscriber must not block
        #    the others.
        for subscriber in subscribers_snapshot:
            try:
                subscriber(event)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "AgentModeBroker: subscriber %r raised on %s -> %s: %s",
                    subscriber,
                    previous_mode.value,
                    mode.value,
                    exc,
                )

        return event

    def set_mode_sync(self, mode: AgentMode) -> AgentModeChangedEvent:
        """Boot-time synchronous mode setter (no persistence).

        Mirrors :meth:`set_mode` but skips the async ``GraphConfigService``
        persistence step. Intended for use at runtime startup — BEFORE
        ConfigService is constructed — so the broker can be seeded from
        :class:`EssentialConfig.agent_mode` (which honors the ``AGENT_MODE``
        env var) and Edge can read the correct value via
        ``current_mode()`` during ``init_edge_runtime``.

        Updates in-memory state under the lock and broadcasts to
        subscribers outside the lock, identical to the async path. A
        raising subscriber is logged and skipped.

        Returns the broadcast event.
        """
        # 1) Capture transition under lock.
        with self._lock:
            previous_mode = self._mode
            self._mode = mode
            subscribers_snapshot = list(self._subscribers)

        event = AgentModeChangedEvent(
            previous_mode=previous_mode,
            new_mode=mode,
            timestamp=datetime.now(timezone.utc),
        )

        # 2) Broadcast outside the lock. A raising subscriber must not block
        #    the others. Persistence is intentionally skipped — ConfigService
        #    is not yet wired at boot.
        for subscriber in subscribers_snapshot:
            try:
                subscriber(event)
            except Exception as exc:  # pragma: no cover - defensive
                logger.error(
                    "AgentModeBroker: subscriber %r raised on %s -> %s: %s",
                    subscriber,
                    previous_mode.value,
                    mode.value,
                    exc,
                )

        return event

    # ------------------------------------------------------------------ #
    # Test / boot helpers
    # ------------------------------------------------------------------ #

    def reset_for_tests(self, mode: AgentMode = AgentMode.PROXY) -> None:
        """Reset internal state. Test-only — not a public API."""
        with self._lock:
            self._mode = mode
            self._subscribers.clear()
            self._config_service = None


# Module-level singleton. Import as
#   from ciris_engine.logic.utils.agent_mode_broker import agent_mode_broker
agent_mode_broker = AgentModeBroker()


def get_agent_mode_broker() -> AgentModeBroker:
    """Return the singleton ``AgentModeBroker``."""
    return agent_mode_broker
