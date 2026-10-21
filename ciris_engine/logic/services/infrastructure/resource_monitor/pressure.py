"""Resource pressure: the ladder, and the subscriber that makes it act.

Until this existed the monitor's signals reached one handler -- the monitor's
own, which counted them and released memory. No component changed what it did.

Vocabulary. This is the runtime protecting itself; none of these words is an
H3ERE action and none is ever offered to the model as a choice.

    PressureLevel  NORMAL -> ELEVATED -> HIGH -> CRITICAL   (per resource, hysteresis)
    ResourceAction RECLAIM, THROTTLE, SHED, DRAIN           (LOG / WARN are non-acting)

    ELEVATED -> RECLAIM    memory only (elevated_action): the monitor releases memory via
                           release_memory. Other resources: non-acting WARN at ELEVATED.
    HIGH     -> THROTTLE   AgentProcessor adds a bounded delay between rounds
    CRITICAL -> SHED       WorkProcessor activates no new tasks; BaseObserver refuses new
                           inbound work with a typed status (API: 503 + Retry-After).
                           In-flight thoughts finish.
    CRITICAL -> DRAIN      only when a resource's cap is DRAIN (no default is): the global
                           ShutdownService is asked for the runtime's normal graceful
                           shutdown. Never os._exit, never execv, never a signal -- on
                           embedded runtimes the host cannot restart the interpreter.

Actions are cumulative up the ladder and capped per resource by
`ResourceLimit.action`.

The gate does not know where the numbers come from. Any producer on the
`ResourceSignalBus` -- today the monitor sampling RSS itself, later the
substrate host's memory gauges -- drives it with one contract: emit an
action's signal when the action comes into force for a resource, and that
action's `lifted_signal()` when it goes out of force.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Set, Tuple

from ciris_engine.schemas.services.resources_core import (
    PressureLevel,
    ResourceAction,
    ResourceLimit,
    ResourcePressureState,
)

if TYPE_CHECKING:
    from .service import ResourceSignalBus

logger = logging.getLogger(__name__)

#: Mildest to strongest; the cap comparison uses this order.
_ACTION_ORDER: Tuple[ResourceAction, ...] = (
    ResourceAction.LOG,
    ResourceAction.WARN,
    ResourceAction.RECLAIM,
    ResourceAction.THROTTLE,
    ResourceAction.SHED,
    ResourceAction.DRAIN,
)

LEVEL_ORDER: Tuple[PressureLevel, ...] = (
    PressureLevel.NORMAL,
    PressureLevel.ELEVATED,
    PressureLevel.HIGH,
    PressureLevel.CRITICAL,
)

#: Actions that do something (LOG and WARN only log).
_ACTING: Tuple[ResourceAction, ...] = (
    ResourceAction.RECLAIM,
    ResourceAction.THROTTLE,
    ResourceAction.SHED,
    ResourceAction.DRAIN,
)

#: Actions that stay in force until lifted. RECLAIM is per-emit; DRAIN is one-shot.
LATCHED_ACTIONS: Tuple[ResourceAction, ...] = (ResourceAction.THROTTLE, ResourceAction.SHED)

#: Upper bound on the extra delay THROTTLE adds to one processing round.
MAX_THROTTLE_EXTRA_SECONDS = 10.0

#: Retry-After hint returned to callers refused under SHED.
SHED_RETRY_AFTER_SECONDS = 30

_CONSEQUENCE = {
    ResourceAction.THROTTLE: "work loop slowed (bounded extra delay between rounds)",
    ResourceAction.SHED: "admission closed: no new tasks activated, new inbound work refused (503); in-flight thoughts finish",
}


def lifted_signal(action: ResourceAction) -> str:
    """Bus key announcing that ``action`` is no longer in force for a resource."""
    return f"{action.value}_lifted"


def _rank(action: ResourceAction) -> int:
    return _ACTION_ORDER.index(action)


def level_rank(level: PressureLevel) -> int:
    return LEVEL_ORDER.index(level)


def escalation_ladder(config: ResourceLimit) -> Tuple[Tuple[PressureLevel, ResourceAction], ...]:
    """The action each level adds for one resource.

    ELEVATED is the resource's own `elevated_action`: RECLAIM for memory, a
    non-acting LOG/WARN everywhere else (releasing heap does nothing for CPU or
    thought counts and costs CPU). Acting otherwise starts at THROTTLE.
    """
    return (
        (PressureLevel.ELEVATED, config.elevated_action),
        (PressureLevel.HIGH, ResourceAction.THROTTLE),
        (PressureLevel.CRITICAL, ResourceAction.SHED),
    )


def actions_for_level(level: PressureLevel, config: ResourceLimit) -> List[ResourceAction]:
    """Acting actions in force at ``level`` for one resource.

    Cumulative and mildest first, each capped by ``config.action``. DRAIN joins
    at CRITICAL only when the cap is DRAIN itself; with a LOG or WARN cap the
    list is empty (logging only).
    """
    cap = config.action
    actions = [
        action
        for rung_level, action in escalation_ladder(config)
        if action in _ACTING and level_rank(level) >= level_rank(rung_level) and _rank(action) <= _rank(cap)
    ]
    if level == PressureLevel.CRITICAL and cap == ResourceAction.DRAIN:
        actions.append(ResourceAction.DRAIN)
    return actions


def _default_drain_requester(reason: str) -> None:
    from ciris_engine.logic.utils.shutdown_manager import request_global_shutdown

    request_global_shutdown(reason)


class ResourcePressureGate:
    """Latches THROTTLE/SHED from the signal bus until lifted; forwards DRAIN once."""

    def __init__(
        self,
        signal_bus: "ResourceSignalBus",
        request_drain: Optional[Callable[[str], None]] = None,
    ) -> None:
        self._held: Dict[ResourceAction, Set[str]] = {action: set() for action in LATCHED_ACTIONS}
        self._request_drain = request_drain or _default_drain_requester
        self._drain_reason: Optional[str] = None
        self._throttled_rounds = 0
        self._shed_rounds = 0
        self._shed_refusals = 0
        for action in LATCHED_ACTIONS:
            signal_bus.register(action.value, self._on_engaged)
            signal_bus.register(lifted_signal(action), self._on_lifted)
        signal_bus.register(ResourceAction.DRAIN.value, self._on_drain)

    async def _on_engaged(self, signal: str, resource: str) -> None:
        action = ResourceAction(signal)
        holders = self._held[action]
        if resource not in holders:
            holders.add(resource)
            logger.warning("Resource pressure: %s ENGAGED by %s -- %s", action.value, resource, _CONSEQUENCE[action])

    async def _on_lifted(self, signal: str, resource: str) -> None:
        action = ResourceAction(signal[: -len("_lifted")])
        holders = self._held[action]
        if resource in holders:
            holders.discard(resource)
            logger.info("Resource pressure: %s LIFTED for %s", action.value, resource)

    async def _on_drain(self, signal: str, resource: str) -> None:
        if self._drain_reason is not None:
            return
        reason = f"Resource drain: {resource} reached CRITICAL pressure (configured cap: drain)"
        self._drain_reason = reason
        logger.critical("Resource pressure: requesting GRACEFUL runtime shutdown -- %s", reason)
        self._request_drain(reason)

    def resources(self, action: ResourceAction) -> List[str]:
        """Resources currently holding ``action``, sorted; empty when lifted."""
        return sorted(self._held.get(action, set()))

    def is_active(self, action: ResourceAction) -> bool:
        return bool(self._held.get(action))

    def throttle_extra_delay(self, base_delay: float) -> float:
        """Extra seconds to add to a round under THROTTLE (0.0 when lifted).

        Doubles the round delay, at least one second, never more than
        MAX_THROTTLE_EXTRA_SECONDS. Counts the round when it applies.
        """
        if not self.is_active(ResourceAction.THROTTLE):
            return 0.0
        self._throttled_rounds += 1
        return min(max(base_delay, 1.0), MAX_THROTTLE_EXTRA_SECONDS)

    def note_shed_round(self) -> None:
        self._shed_rounds += 1

    def note_shed_refusal(self) -> None:
        self._shed_refusals += 1

    def get_state(self, levels: Optional[Dict[str, PressureLevel]] = None) -> ResourcePressureState:
        return ResourcePressureState(
            levels=dict(levels or {}),
            throttle=self.resources(ResourceAction.THROTTLE),
            shed=self.resources(ResourceAction.SHED),
            drain_requested=self._drain_reason,
            throttled_rounds_total=self._throttled_rounds,
            shed_rounds_total=self._shed_rounds,
            shed_refusals_total=self._shed_refusals,
        )

    def collect_metrics(self) -> Dict[str, float]:
        metrics = {
            f"resource_pressure_{action.value}_active": float(len(self._held[action])) for action in LATCHED_ACTIONS
        }
        metrics["resource_pressure_drain_requested"] = 1.0 if self._drain_reason else 0.0
        metrics["resource_pressure_throttled_rounds_total"] = float(self._throttled_rounds)
        metrics["resource_pressure_shed_rounds_total"] = float(self._shed_rounds)
        metrics["resource_pressure_shed_refusals_total"] = float(self._shed_refusals)
        return metrics


def pressure_gate_of(resource_monitor: object) -> Optional[ResourcePressureGate]:
    """The gate a resource monitor carries, or None.

    The isinstance check matters: processors and observers are built with test
    doubles and partial monitors, and a Mock's auto-attribute would otherwise
    read as "every action in force".
    """
    gate = getattr(resource_monitor, "pressure", None)
    return gate if isinstance(gate, ResourcePressureGate) else None
