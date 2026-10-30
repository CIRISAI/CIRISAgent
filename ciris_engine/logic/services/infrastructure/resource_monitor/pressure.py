"""Resource pressure: the ladder, and the subscriber that makes it act.

Until this existed the monitor's signals reached one handler -- the monitor's
own, which counted them and released memory. No component changed what it did.

Vocabulary. This is the runtime protecting itself; none of these words is an
H3ERE action and none is ever offered to the model as a choice.

    PressureLevel  NORMAL -> ELEVATED -> HIGH -> CRITICAL   (per resource, hysteresis)
    ResourceAction RECLAIM, THROTTLE, SHED, DRAIN           (LOG / WARN are non-acting)

    ELEVATED -> RECLAIM    memory only (elevated_action): the monitor releases memory via
                           release_memory. Other resources: non-acting WARN at ELEVATED.
    HIGH     -> THROTTLE   AgentProcessor adds a delay between rounds sized to bring the
                           resource back under its lift point (bounded) -- only for
                           resources THROTTLE relieves (`ResourceLimit.throttle_relieves`):
                           CPU, where yielding between rounds frees the CPU. Not for
                           thoughts_active: only the work loop drains active thoughts, so
                           slowing it prolongs the overload; its HIGH rung is non-acting.
    CRITICAL -> SHED       WorkProcessor activates no new tasks; BaseObserver refuses new
                           inbound work with a typed status (API: 503 + Retry-After).
                           In-flight thoughts finish.

Admission against thoughts_active is live, per message, not only the latch.
Every admitted message creates a thought, so the gate keeps an estimate of
active thoughts (the monitor's last sample + intakes since) and admits while it
is below a ceiling one under the CRITICAL threshold: only the excess is refused,
and admitted work alone never takes the resource CRITICAL. Admission reopens
the moment the estimate falls below the ceiling -- no hysteresis band holds it
shut after capacity frees. Task activation in the work loop takes the same
headroom. A refusal's Retry-After is the time the measured drain rate needs to
clear the excess, bounded to [MIN_RETRY_AFTER_SECONDS, SHED_RETRY_AFTER_SECONDS].
SHED held by any other resource (memory) still closes admission outright.
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
import math
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Dict, List, Optional, Set, Tuple

from ciris_engine.schemas.services.resources_core import (
    AdmissionState,
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

#: Lower bound on it while THROTTLE is in force (a token rest, never zero).
MIN_THROTTLE_EXTRA_SECONDS = 0.25

#: Upper bound on a refusal's Retry-After, and the hint when SHED is held by a
#: resource with no drain measure (memory).
SHED_RETRY_AFTER_SECONDS = 30

#: Lower bound on a refusal's Retry-After.
MIN_RETRY_AFTER_SECONDS = 1

#: Retry-After for a thoughts_active refusal before any work round has been
#: measured (the first rounds of a burst finish within seconds).
UNMEASURED_RETRY_AFTER_SECONDS = 5

#: Weight of the newest round in the drain-rate average.
DRAIN_EWMA_ALPHA = 0.3

#: The resource admission is measured against (each admitted message creates one).
ADMISSION_RESOURCE = "thoughts_active"

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
    thought counts and costs CPU). Acting otherwise starts at THROTTLE, unless
    THROTTLE does not relieve the resource (`throttle_relieves=False`): then
    HIGH is non-acting and the first acting rung is SHED.
    """
    high = ResourceAction.THROTTLE if config.throttle_relieves else ResourceAction.WARN
    return (
        (PressureLevel.ELEVATED, config.elevated_action),
        (PressureLevel.HIGH, high),
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


@dataclass(frozen=True)
class AdmissionDecision:
    """Whether one inbound message is admitted, and if not, when to retry."""

    admitted: bool
    shed_resources: List[str] = field(default_factory=list)
    retry_after_seconds: Optional[int] = None


class ThoughtAdmission:
    """Live per-message admission against the active-thought ceiling.

    estimate = the monitor's last sample + intakes that created a thought since
    + intakes in flight. The sample is taken synchronously on the loop, so it
    already holds every thought created before it; intakes settling after it
    are carried until the next sample. Errs high for at most one tick, which
    can only refuse slightly early, never admit past the ceiling.
    """

    def __init__(self) -> None:
        self.sampled: Optional[int] = None
        self.ceiling: Optional[int] = None
        self._since_sample = 0
        self._inflight = 0
        self.drain_per_second: Optional[float] = None
        self._last_round_end: Optional[float] = None
        self.admitted_total = 0
        self.refused_total = 0
        self.closed = False  # last decision refused (for transition logging)

    def observe(self, value: int, config: ResourceLimit) -> None:
        self.sampled = value
        self._since_sample = 0
        self.ceiling = max(1, config.limit - 1)

    @property
    def estimate(self) -> int:
        return (self.sampled or 0) + self._since_sample + self._inflight

    def headroom(self) -> Optional[int]:
        """Thoughts that may still be added below the ceiling; None before the first sample."""
        if self.ceiling is None:
            return None
        return self.ceiling - self.estimate

    def reserve(self) -> None:
        self._inflight += 1
        self.admitted_total += 1

    def settle(self, created: bool) -> None:
        self._inflight = max(0, self._inflight - 1)
        if created:
            self._since_sample += 1

    def note_round(self, thoughts_completed: int, now: Optional[float] = None) -> None:
        """A work round finished; the time since the previous one is its drain period."""
        now = time.monotonic() if now is None else now
        last, self._last_round_end = self._last_round_end, now
        if last is None or thoughts_completed <= 0 or now <= last:
            return
        rate = thoughts_completed / (now - last)
        self.drain_per_second = (
            rate if self.drain_per_second is None else DRAIN_EWMA_ALPHA * rate + (1 - DRAIN_EWMA_ALPHA) * self.drain_per_second
        )

    def retry_after(self) -> int:
        """Seconds for the measured drain to clear the excess over the ceiling, bounded."""
        if not self.drain_per_second:
            return UNMEASURED_RETRY_AFTER_SECONDS
        excess = max(1, self.estimate - (self.ceiling or 0) + 1)
        seconds = math.ceil(excess / self.drain_per_second)
        return max(MIN_RETRY_AFTER_SECONDS, min(SHED_RETRY_AFTER_SECONDS, seconds))

    def state(self) -> Optional[AdmissionState]:
        if self.ceiling is None:
            return None
        return AdmissionState(
            active_estimate=self.estimate,
            ceiling=self.ceiling,
            drain_per_second=self.drain_per_second,
            retry_after_seconds=self.retry_after(),
            admitted_total=self.admitted_total,
            refused_total=self.refused_total,
        )


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
        self.admission = ThoughtAdmission()
        # Latest (value, lift threshold) per resource and the last busy round's
        # length: what sizes a proportional THROTTLE delay.
        self._readings: Dict[str, Tuple[float, float]] = {}
        self._last_round_seconds: Optional[float] = None
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

    def note_reading(self, resource: str, value: float, lift_threshold: float) -> None:
        """The monitor's latest reading of a resource and the value its HIGH level lifts below."""
        self._readings[resource] = (value, lift_threshold)

    def note_round(self, thoughts_completed: int, round_seconds: float, now: Optional[float] = None) -> None:
        """A work round finished: feeds the drain rate and sizes the next THROTTLE delay."""
        self.admission.note_round(thoughts_completed, now)
        if thoughts_completed > 0 and round_seconds > 0:
            self._last_round_seconds = round_seconds

    def throttle_extra_delay(self, base_delay: float) -> float:
        """Extra seconds to add to a round under THROTTLE (0.0 when lifted).

        Only as much as brings the throttling resource back under the value
        its HIGH level lifts below: a round that ran busy for T seconds with
        the resource at `value` gets T * (value / lift - 1) of rest, so its
        duty cycle drops by that ratio. Bounded to
        [MIN_THROTTLE_EXTRA_SECONDS, MAX_THROTTLE_EXTRA_SECONDS]. Before a
        round has been measured (or with no reading) it falls back to doubling
        the round delay, at least one second. Counts the round when it applies.
        """
        holders = self.resources(ResourceAction.THROTTLE)
        if not holders:
            return 0.0
        self._throttled_rounds += 1
        ratios = [
            value / lift
            for value, lift in (self._readings.get(name, (0.0, 0.0)) for name in holders)
            if lift > 0 and value > 0
        ]
        if self._last_round_seconds is None or not ratios:
            return min(max(base_delay, 1.0), MAX_THROTTLE_EXTRA_SECONDS)
        extra = self._last_round_seconds * (max(ratios) - 1.0)
        return min(MAX_THROTTLE_EXTRA_SECONDS, max(MIN_THROTTLE_EXTRA_SECONDS, extra))

    def note_shed_round(self) -> None:
        self._shed_rounds += 1

    def note_shed_refusal(self) -> None:
        self._shed_refusals += 1

    def _closed_by_others(self) -> List[str]:
        return [r for r in self.resources(ResourceAction.SHED) if r != ADMISSION_RESOURCE]

    def admit_intake(self) -> AdmissionDecision:
        """Decide one inbound message. An admitted message holds a reservation
        until `settle_intake` says whether it created a thought."""
        others = self._closed_by_others()
        if others:
            self._refuse(others, SHED_RETRY_AFTER_SECONDS, "SHED held by " + ", ".join(others))
            return AdmissionDecision(False, others, SHED_RETRY_AFTER_SECONDS)
        adm = self.admission
        headroom = adm.headroom()
        if headroom is None:
            # Not sampled yet: only the latch can say anything.
            if self.is_active(ResourceAction.SHED):
                self._refuse([ADMISSION_RESOURCE], SHED_RETRY_AFTER_SECONDS, "SHED latched before the first sample")
                return AdmissionDecision(False, [ADMISSION_RESOURCE], SHED_RETRY_AFTER_SECONDS)
        elif headroom <= 0:
            retry = adm.retry_after()
            adm.refused_total += 1
            self._refuse([ADMISSION_RESOURCE], retry, None)
            return AdmissionDecision(False, [ADMISSION_RESOURCE], retry)
        if adm.closed:
            adm.closed = False
            logger.info(
                "Admission: OPEN again -- thoughts_active %s/%s live (drain %s)",
                adm.estimate,
                adm.ceiling,
                _rate(adm.drain_per_second),
            )
        adm.reserve()
        return AdmissionDecision(True)

    def settle_intake(self, created_thought: bool) -> None:
        self.admission.settle(created_thought)

    def _refuse(self, holders: List[str], retry_after: int, why: Optional[str]) -> None:
        self._shed_refusals += 1
        adm = self.admission
        if adm.closed:
            return  # logged at the transition; the round line carries the counts
        adm.closed = True
        logger.warning(
            "Admission: SHED -- refusing the excess: thoughts_active %s/%s live (ceiling = CRITICAL %s - 1), "
            "drain %s, Retry-After %ss%s",
            adm.estimate,
            adm.ceiling if adm.ceiling is not None else "?",
            (adm.ceiling + 1) if adm.ceiling is not None else "?",
            _rate(adm.drain_per_second),
            retry_after,
            f" ({why})" if why else "",
        )

    def activation_headroom(self) -> Optional[int]:
        """Tasks the work loop may activate this round: 0 when closed, None = unbounded."""
        if self._closed_by_others():
            return 0
        headroom = self.admission.headroom()
        if headroom is None:
            return 0 if self.is_active(ResourceAction.SHED) else None
        return max(0, headroom)

    def get_state(self, levels: Optional[Dict[str, PressureLevel]] = None) -> ResourcePressureState:
        return ResourcePressureState(
            levels=dict(levels or {}),
            throttle=self.resources(ResourceAction.THROTTLE),
            shed=self.resources(ResourceAction.SHED),
            drain_requested=self._drain_reason,
            throttled_rounds_total=self._throttled_rounds,
            shed_rounds_total=self._shed_rounds,
            shed_refusals_total=self._shed_refusals,
            admission=self.admission.state(),
        )

    def collect_metrics(self) -> Dict[str, float]:
        metrics = {
            f"resource_pressure_{action.value}_active": float(len(self._held[action])) for action in LATCHED_ACTIONS
        }
        metrics["resource_pressure_drain_requested"] = 1.0 if self._drain_reason else 0.0
        metrics["resource_pressure_throttled_rounds_total"] = float(self._throttled_rounds)
        metrics["resource_pressure_shed_rounds_total"] = float(self._shed_rounds)
        metrics["resource_pressure_shed_refusals_total"] = float(self._shed_refusals)
        metrics["resource_admission_admitted_total"] = float(self.admission.admitted_total)
        metrics["resource_admission_refused_total"] = float(self.admission.refused_total)
        metrics["resource_admission_drain_per_second"] = float(self.admission.drain_per_second or 0.0)
        return metrics


def _rate(per_second: Optional[float]) -> str:
    return "unmeasured" if not per_second else f"{per_second:.2f} thoughts/s"


def pressure_gate_of(resource_monitor: object) -> Optional[ResourcePressureGate]:
    """The gate a resource monitor carries, or None.

    The isinstance check matters: processors and observers are built with test
    doubles and partial monitors, and a Mock's auto-attribute would otherwise
    read as "every action in force".
    """
    gate = getattr(resource_monitor, "pressure", None)
    return gate if isinstance(gate, ResourcePressureGate) else None
