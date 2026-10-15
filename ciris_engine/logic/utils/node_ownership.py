"""The node-ownership reader: EVERY NODE IS ALWAYS CLAIMED.

An agent cannot run without a named human for its node. The deployer claims
the node with a valid identity (CIRISManager, the wizard, the QA runner); the
agent only reads whether that has happened, and holds until it has.

ONE reader. The processor start hold (`AgentProcessor.start_processing`), the
act gate (`ActionDispatcher._dispatch_inner`), intake (`routes/agent.py`),
setup completion (`routes/setup/complete.py`) and health all call
`node_owned()` and nothing else.

THE SOURCE is the node's own owner-binding, read in process: the node names its
key (`ciris_server.node_identity()`), and the persist engine's single-owner
resolver answers who owns it (`Engine.owner_of_json`, the resolver the
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

from ciris_engine.schemas.runtime.node_ownership import CLAIM_PIN_FILE_NAME, NodeOwnership, NodeOwnershipReading

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
    import ciris_server  # type: ignore[import-not-found, import-untyped, unused-ignore]

    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    identity = json.loads(ciris_server.node_identity())
    node_key_id = identity.get("key_id") if isinstance(identity, dict) else None
    if not node_key_id:
        return _state(NodeOwnershipReading.NO_NODE_KEY, read_error="the node has not named its key yet")
    node_key_id = str(node_key_id)
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


async def node_owned(*, fresh: bool = False) -> NodeOwnership:
    """THE reader. Cached for `NODE_OWNERSHIP_CACHE_TTL_SECONDS`; `fresh` always asks the node."""
    global _cached, _cached_at
    cached = _cached
    if not fresh and cached is not None and time.monotonic() - _cached_at < NODE_OWNERSHIP_CACHE_TTL_SECONDS:
        return cached
    state = await _read_from_node()
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


def invalidate_node_ownership_cache() -> None:
    """Force the next read to ask the node."""
    global _cached_at
    _cached_at = 0.0


__all__ = [
    "NODE_OWNERSHIP_CACHE_TTL_SECONDS",
    "NODE_OWNERSHIP_HOLD_TICK_SECONDS",
    "NODE_OWNERSHIP_READ_TIMEOUT_SECONDS",
    "claim_pin_file",
    "hold_until_node_owned",
    "invalidate_node_ownership_cache",
    "node_owned",
]
