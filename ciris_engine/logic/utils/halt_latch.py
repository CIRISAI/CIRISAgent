"""The constitutional-halt latch reader (CC 4.2.1.1, CIRISAgent#1231).

ONE reader. The act gate (`ActionDispatcher._dispatch_inner`), the round holds
(main loop, wakeup loop, dream loop), the shutdown processor, operator
resume/single-step, the scheduler, the maintenance sweeps and the API all call
`read_halt_latch()` and nothing else. It is a module, not a service: there is
nothing to start, and no service may hold the latch as state.

The node owns the latch. This module reads ``GET /v1/accord/halt-status`` on the
folded node and never writes or clears it, never computes a fuse (it honours only
the node's ``lapsed``), and never ends the process.

FAIL CLOSED. Unreachable, a timeout, a non-200, a body that is not a
halt-status document, ``halted: null``, the boot window before :4243 answers, and
a deployment with no node at all are every one of them HALTED.
"""

from __future__ import annotations

import asyncio
import contextvars
import logging
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from typing import Iterator, Mapping, Optional

import httpx

from ciris_engine.schemas.runtime.accord_halt import (
    ACCORD_HALT_EXEMPT_ACTS,
    AccordHaltExemptAct,
    AccordHaltReading,
    AccordHaltState,
    AccordPauseEpisode,
)
from ciris_engine.schemas.runtime.enums import HandlerActionType
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)

#: The folded node's read-API port (`ciris_engine/logic/runtime/node_fold.py`).
NODE_FOLD_PORT = 4243
HALT_STATUS_URL = f"http://127.0.0.1:{NODE_FOLD_PORT}/v1/accord/halt-status"

#: A loopback read of a file the node already holds in memory. Slower than this
#: and the node is not answering; the act waits for the next read.
HALT_READ_TIMEOUT_SECONDS = 1.0

#: Reads are cached for no longer than the act cadence. Acts are seconds apart,
#: so one second never lets an act run on a reading older than the act before it.
HALT_READ_CACHE_TTL_SECONDS = 1.0

#: How often a held loop re-reads the latch to notice a release or a lapse.
HALT_HOLD_TICK_SECONDS = 5.0

#: How long after a resume the system snapshot carries the pause notice.
ACCORD_PAUSE_NOTICE_WINDOW = timedelta(minutes=10)

#: Handler actions that ARE an exempt act. Derived from the shared list, never
#: extended on its own: an action not mapped here is refused under the latch.
_HANDLER_EXEMPT_ACTS: Mapping[HandlerActionType, AccordHaltExemptAct] = MappingProxyType(
    {HandlerActionType.DEFER: AccordHaltExemptAct.DEFERRAL_WRITE}
)

_cached: Optional[AccordHaltState] = None
_cached_at: float = 0.0
#: The read that first saw the current node-reported halt; None when none stands.
_episode_start: Optional[AccordHaltState] = None
_last_episode: Optional[AccordPauseEpisode] = None

_exempt_scope: contextvars.ContextVar[Optional[AccordHaltState]] = contextvars.ContextVar(
    "accord_halt_exempt_scope", default=None
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _closed(reading: AccordHaltReading, error: str) -> AccordHaltState:
    return AccordHaltState(halted=True, reading=reading, read_error=error, read_at=_now())


def _opt_str(value: object) -> Optional[str]:
    return None if value is None else str(value)


def parse_halt_status(body: JSONDict) -> AccordHaltState:
    """Map one ``/v1/accord/halt-status`` document onto the typed state.

    ``halted`` is tri-state on the node: ``true``, ``false`` or ``null`` (the
    latch is present but unreadable). Only a literal ``false`` lets the agent
    act. ``lapsed`` is honoured only alongside ``halted: false``: a document
    claiming both is read as halted.
    """
    halted = body.get("halted")
    raw_halt = body.get("halt")
    halt: JSONDict = raw_halt if isinstance(raw_halt, dict) else {}
    signers = halt.get("valid_signers")
    fuse = halt.get("fuse_secs")
    confirmed = halt.get("confirmed")
    details = {
        "invocation_id": _opt_str(halt.get("invocation_id")),
        "received_at": _opt_str(halt.get("received_at")),
        "fuse_secs": fuse if isinstance(fuse, int) and not isinstance(fuse, bool) else None,
        "lapses_at": _opt_str(halt.get("lapses_at")),
        "lapsed_at": _opt_str(halt.get("lapsed_at")),
        "confirmed": confirmed if isinstance(confirmed, bool) else None,
        "valid_signers": [str(s) for s in signers] if isinstance(signers, list) else [],
    }

    if halted is True:
        return AccordHaltState(halted=True, reading=AccordHaltReading.IN_EFFECT, read_at=_now(), **details)
    if halted is False:
        reading = AccordHaltReading.LAPSED if body.get("lapsed") is True else AccordHaltReading.NOT_HALTED
        return AccordHaltState(halted=False, reading=reading, read_at=_now(), **details)
    if halted is None and "halted" in body:
        error = body.get("error")
        return AccordHaltState(
            halted=True,
            reading=AccordHaltReading.LATCH_UNREADABLE,
            read_error=str(error) if error else "node reported halted: null",
            read_at=_now(),
            **details,
        )
    return _closed(AccordHaltReading.NODE_ERROR, f"halt-status carried no usable 'halted' field: {halted!r}")


async def _read_from_node() -> AccordHaltState:
    """One uncached read of the node. Every failure is a halted state, never an exception."""
    # Imported here: the runtime package pulls in the whole runtime, and the
    # dispatcher and processors that import this module are part of it.
    from ciris_engine.logic.runtime.node_fold import fold_status

    if fold_status() is None:
        return _closed(AccordHaltReading.NO_NODE, "no node in this deployment (CIRIS_NODE_FOLD=false)")
    try:
        async with httpx.AsyncClient(timeout=HALT_READ_TIMEOUT_SECONDS) as client:
            response = await client.get(HALT_STATUS_URL)
    except httpx.TimeoutException as e:
        return _closed(AccordHaltReading.NODE_TIMEOUT, f"{type(e).__name__}: {e}")
    except Exception as e:  # noqa: BLE001 - any failure to read is a halted read
        return _closed(AccordHaltReading.NODE_UNREACHABLE, f"{type(e).__name__}: {e}")
    if response.status_code != 200:
        return _closed(AccordHaltReading.NODE_ERROR, f"halt-status answered HTTP {response.status_code}")
    try:
        body = response.json()
    except Exception as e:  # noqa: BLE001
        return _closed(AccordHaltReading.NODE_ERROR, f"halt-status body is not JSON: {type(e).__name__}")
    if not isinstance(body, dict):
        return _closed(AccordHaltReading.NODE_ERROR, "halt-status body is not an object")
    return parse_halt_status(body)


def _observe(state: AccordHaltState) -> None:
    """Log edges, not reads, and remember a node-reported halt once it ends."""
    global _episode_start, _last_episode
    previous = _cached
    if previous is None or previous.halted != state.halted or previous.reading != state.reading:
        if state.halted:
            logger.warning(
                "Constitutional halt: agent acts are paused (%s, invocation %s%s)",
                state.reading.value,
                state.invocation_id or "-",
                f", {state.read_error}" if state.read_error else "",
            )
        else:
            logger.warning("Constitutional halt: no halt stands (%s) — agent acts may proceed", state.reading.value)

    if state.reading == AccordHaltReading.IN_EFFECT:
        if _episode_start is None or _episode_start.invocation_id != state.invocation_id:
            _episode_start = state
    elif not state.halted and _episode_start is not None:
        _last_episode = AccordPauseEpisode(
            invocation_id=_episode_start.invocation_id,
            started_at=_episode_start.read_at,
            ended_at=state.read_at,
            ended_by=state.reading,
        )
        _episode_start = None


async def read_halt_latch() -> AccordHaltState:
    """THE reader. Cached for at most `HALT_READ_CACHE_TTL_SECONDS`."""
    global _cached, _cached_at
    cached = _cached
    if cached is not None and time.monotonic() - _cached_at < HALT_READ_CACHE_TTL_SECONDS:
        return cached
    state = await _read_from_node()
    _observe(state)
    _cached = state
    _cached_at = time.monotonic()
    return state


def invalidate_halt_cache() -> None:
    """Force the next `read_halt_latch()` to ask the node."""
    global _cached_at
    _cached_at = 0.0


def exempt_act_for(action: HandlerActionType) -> Optional[AccordHaltExemptAct]:
    """The exempt act a handler action performs, or None when it is refused under the latch."""
    act = _HANDLER_EXEMPT_ACTS.get(action)
    return act if act in ACCORD_HALT_EXEMPT_ACTS else None


@contextmanager
def exempt_act_scope(state: Optional[AccordHaltState]) -> Iterator[None]:
    """Mark an exempt act running under a standing halt, for the code it calls.

    The deferral write runs under the latch, but the channel notice the defer
    handler sends alongside it is a SPEAK in all but name and must not.
    """
    token = _exempt_scope.set(state)
    try:
        yield
    finally:
        _exempt_scope.reset(token)


def running_exempt_under_halt() -> Optional[AccordHaltState]:
    """The halt an exempt act is running under, or None outside one."""
    return _exempt_scope.get()


async def hold_tick(stop_event: Optional[asyncio.Event] = None) -> None:
    """One wait of a held loop: `HALT_HOLD_TICK_SECONDS`, cut short by `stop_event`."""
    if stop_event is None:
        await asyncio.sleep(HALT_HOLD_TICK_SECONDS)
        return
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=HALT_HOLD_TICK_SECONDS)
    except asyncio.TimeoutError:
        pass


def last_pause_episode() -> Optional[AccordPauseEpisode]:
    """The most recent node-reported halt that has ended, if any."""
    return _last_episode


def accord_pause_notice(now: Optional[datetime] = None) -> Optional[str]:
    """The one informational snapshot line after a resume, or None.

    Facts only, and no action asked for: the same rule as the resource-pressure
    vocabulary. Shown for `ACCORD_PAUSE_NOTICE_WINDOW` after the halt ends.
    """
    episode = _last_episode
    if episode is None:
        return None
    if (now or _now()) - episode.ended_at > ACCORD_PAUSE_NOTICE_WINDOW:
        return None
    how = "lapsed after its fuse" if episode.ended_by == AccordHaltReading.LAPSED else "was released by the holders"
    return (
        f"ACCORD PAUSE (informational): your effectful acts were paused from "
        f"{episode.started_at.isoformat()} to {episode.ended_at.isoformat()} under a constitutional halt "
        f"({episode.invocation_id or 'unidentified'}), which {how}. Your tasks and memory are as you "
        f"left them. No action is requested."
    )


__all__ = [
    "HALT_HOLD_TICK_SECONDS",
    "HALT_READ_CACHE_TTL_SECONDS",
    "HALT_STATUS_URL",
    "accord_pause_notice",
    "exempt_act_for",
    "exempt_act_scope",
    "hold_tick",
    "invalidate_halt_cache",
    "last_pause_episode",
    "parse_halt_status",
    "read_halt_latch",
    "running_exempt_under_halt",
]
