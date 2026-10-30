"""The node-ownership reader: EVERY NODE IS ALWAYS CLAIMED.

An agent cannot run without a named human for its node. The deployer claims
the node with a valid identity (CIRISManager, the wizard, the QA runner); the
agent only reads whether that has happened, and holds until it has.

ONE reader. The processor start hold (`AgentProcessor.start_processing`), the
act gate (`ActionDispatcher._dispatch_inner`), intake (`routes/agent.py`),
setup completion (`routes/setup/complete.py`) and health all call
`node_owned()` and nothing else.

THE SOURCE is the node's own owner-binding, read in process: the node key is
the one `provision_node_identity` minted at boot (`edge_runtime.get_node_key_id()`,
the key a claim binds: upgrade-owner answers with this same `node_key_id`), and
the persist engine's single-owner resolver answers who owns it (`Engine.owner_of_json`, the resolver the
substrate says consumers MUST use for "who owns this node"). The same binding
the node checks when it refuses peering, consent and erasure on an unowned node.

FAIL CLOSED. No node key yet, no engine, a read error (including the
substrate's ambiguous-owner refusal), a timeout and a JSON ``null`` are all
UNCLAIMED. The reads are synchronous calls into the substrate, so they run off
the event loop and are bounded by a timeout.

FOLD OFF. With ``CIRIS_NODE_FOLD=false`` there is no node in the process, so
there is no owner: the reading is `NO_NODE` and the agent holds, exactly as the
halt latch reads fold-off as halted. There are no deployments without nodes and
no bypass. The unit suite runs fold-off and stubs `_read_from_node` with an
explicit "owned" answer in tests/conftest.py, the way the halt latch is stubbed.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from datetime import datetime, timezone
from typing import Optional

from ciris_engine.schemas.runtime.node_ownership import (
    CLAIM_PIN_FILE_NAME,
    NodeOwnerRecord,
    NodeOwnership,
    NodeOwnershipReading,
)

logger = logging.getLogger(__name__)

#: An in-process read of one row. Slower than this and the substrate is not answering.
NODE_OWNERSHIP_READ_TIMEOUT_SECONDS = 2.0

#: Polling callers (health, intake, the start hold) may reuse a reading this old.
#: Decisions (the act gate, setup completion) always read fresh.
NODE_OWNERSHIP_CACHE_TTL_SECONDS = 2.0

#: How often the held processor re-reads ownership.
NODE_OWNERSHIP_HOLD_TICK_SECONDS = 5.0

_cached: Optional[NodeOwnership] = None
_cached_at: float = 0.0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def claim_pin_file() -> str:
    """`<CIRIS_HOME>/claim_pin`: the node's home is the agent's CIRIS_HOME (see node_fold._resolve_home)."""
    try:
        from ciris_engine.logic.utils.path_resolution import get_ciris_home

        return str(get_ciris_home() / CLAIM_PIN_FILE_NAME)
    except Exception:  # noqa: BLE001 - the message must still be sayable
        return f"<CIRIS_HOME>/{CLAIM_PIN_FILE_NAME}"


def _state(reading: NodeOwnershipReading, **fields: Optional[str]) -> NodeOwnership:
    return NodeOwnership(reading=reading, read_at=_now(), claim_pin_file=claim_pin_file(), **fields)


def _read_owner_sync() -> NodeOwnership:
    """One uncached read of the node's owner-binding. Blocking; never call on the event loop."""
    # NOT `ciris_server.node_identity()`: on the embedded fold its `key_id`
    # stays null for the whole run (seen on 0.5.226), which would hold an owned
    # agent forever.
    from ciris_engine.logic.persistence.models.graph import get_persist_engine
    from ciris_engine.logic.runtime.edge_runtime import get_node_key_id

    node_key_id = get_node_key_id()
    if not node_key_id:
        return _state(NodeOwnershipReading.NO_NODE_KEY, read_error="the node key is not provisioned yet")
    engine = get_persist_engine()
    owner_of_json = getattr(engine, "owner_of_json", None)
    if owner_of_json is None:
        return _state(NodeOwnershipReading.NO_ENGINE, node_key_id=node_key_id, read_error="no persist engine")
    owner = json.loads(owner_of_json(node_key_id))
    if isinstance(owner, str) and owner:
        return _state(NodeOwnershipReading.OWNED, node_key_id=node_key_id, owner_key_id=owner)
    return _state(NodeOwnershipReading.UNOWNED, node_key_id=node_key_id)


async def _read_from_node() -> NodeOwnership:
    """One uncached read. Every failure is an unclaimed state, never an exception."""
    from ciris_engine.logic.runtime.node_fold import fold_status

    if fold_status() is None:
        return _state(NodeOwnershipReading.NO_NODE, read_error="no node in this deployment (CIRIS_NODE_FOLD=false)")
    try:
        return await asyncio.wait_for(asyncio.to_thread(_read_owner_sync), timeout=NODE_OWNERSHIP_READ_TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        return _state(
            NodeOwnershipReading.READ_TIMEOUT, read_error=f"no answer in {NODE_OWNERSHIP_READ_TIMEOUT_SECONDS}s"
        )
    except Exception as e:  # noqa: BLE001 - can't tell means unowned
        return _state(NodeOwnershipReading.READ_ERROR, read_error=f"{type(e).__name__}: {e}")


def _observe(state: NodeOwnership) -> None:
    """Log the edge into and out of unclaimed once, not every read."""
    previous = _cached
    if previous is not None and previous.unclaimed == state.unclaimed:
        return
    if state.unclaimed:
        logger.warning("Node ownership: the agent is held. %s", state.unclaimed_message())
    else:
        logger.info("Node ownership: node %s is owned by %s; the agent may run", state.node_key_id, state.owner_key_id)


#: Readings that say the read failed, not that the node has no owner.
_FAILED_READS = frozenset({NodeOwnershipReading.READ_TIMEOUT, NodeOwnershipReading.READ_ERROR})

_inflight: Optional["asyncio.Task[NodeOwnership]"] = None
#: The last OWNED reading a failed read may keep; cleared by invalidation.
_last_owned: Optional[NodeOwnership] = None


async def _shared_read() -> NodeOwnership:
    """One ownership read, shared by every caller that arrives while it is in flight.

    Without it a burst of requests, each finding the cache expired, queued one
    read apiece on the thread pool; they timed out together and the agent told
    every caller the node had no owner (a DoS, 2026-10-29).
    """
    global _inflight
    loop = asyncio.get_running_loop()
    task = _inflight
    if task is None or task.done() or task.get_loop() is not loop:
        task = loop.create_task(_read_from_node())
        _inflight = task
    return await asyncio.shield(task)


async def node_owned(*, fresh: bool = False) -> NodeOwnership:
    """THE reader. Cached for `NODE_OWNERSHIP_CACHE_TTL_SECONDS`; `fresh` always asks the node.

    Ownership changes only by an explicit act (claim, release, transfer), and a
    read that answers is always taken. A read that FAILS (timeout or error) after
    the node was read as OWNED keeps the OWNED reading: a slow read is not the
    owner going away. Before the first OWNED reading a failed read still holds
    the agent (an unclaimed node never runs).
    """
    global _cached, _cached_at, _last_owned
    cached = _cached
    if not fresh and cached is not None and time.monotonic() - _cached_at < NODE_OWNERSHIP_CACHE_TTL_SECONDS:
        return cached
    state = await _shared_read()
    if state.reading in _FAILED_READS and _last_owned is not None:
        logger.debug("Node ownership read failed (%s); keeping the owned reading", state.read_error)
        return _last_owned
    _last_owned = state if state.reading == NodeOwnershipReading.OWNED else None
    _observe(state)
    _cached = state
    _cached_at = time.monotonic()
    return state


async def hold_until_node_owned(stop_event: Optional[asyncio.Event] = None) -> bool:
    """Hold until the node is owned. False when `stop_event` is set or shutdown is requested first."""
    from ciris_engine.logic.utils.shutdown_manager import is_global_shutdown_requested

    while True:
        if not (await node_owned()).unclaimed:
            return True
        if is_global_shutdown_requested() or (stop_event is not None and stop_event.is_set()):
            return False
        if stop_event is None:
            await asyncio.sleep(NODE_OWNERSHIP_HOLD_TICK_SECONDS)
            continue
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=NODE_OWNERSHIP_HOLD_TICK_SECONDS)
        except asyncio.TimeoutError:
            pass


def _read_owner_record_sync() -> Optional[NodeOwnerRecord]:
    """One read of `ciris_server.owner_record()`. Blocking; never call on the event loop.

    None: no substrate, a substrate older than 0.5.234 (no `owner_record`), or
    the node has no ROOT. An exception (the call raised, or it answered
    something that is not an owner record) means the record could NOT be read,
    which a caller must not report as "no such user". Fold off (CIRIS_NODE_FOLD=false)
    is no node in this process, so no owner: None, as `_read_from_node` reads it.
    """
    from ciris_engine.logic.runtime.node_fold import fold_status

    if fold_status() is None:
        return None
    try:
        import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]
    except ImportError:
        return None
    owner_record = getattr(ciris_server, "owner_record", None)
    if owner_record is None:
        return None
    raw = owner_record()
    if raw is None:
        return None
    return NodeOwnerRecord.model_validate_json(raw)


async def read_owner_record() -> Optional[NodeOwnerRecord]:
    """The node-claimed owner's record, read off the event loop. Raises when it could not be read."""
    return await asyncio.wait_for(
        asyncio.to_thread(_read_owner_record_sync), timeout=NODE_OWNERSHIP_READ_TIMEOUT_SECONDS
    )


def invalidate_node_ownership_cache() -> None:
    """Force the next read to ask the node; a failed read then holds the agent."""
    global _cached_at, _last_owned
    _cached_at = 0.0
    _last_owned = None


__all__ = [
    "NODE_OWNERSHIP_CACHE_TTL_SECONDS",
    "NODE_OWNERSHIP_HOLD_TICK_SECONDS",
    "NODE_OWNERSHIP_READ_TIMEOUT_SECONDS",
    "claim_pin_file",
    "hold_until_node_owned",
    "invalidate_node_ownership_cache",
    "node_owned",
    "read_owner_record",
]
