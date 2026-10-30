"""A burst of traffic must not read as a halt or as an unowned node (2026-10-29).

The memory benchmark's 1000-message burst showed the denial of service: every
request read the halt latch and the ownership row on its own, the reads timed out
together, and both gates fail closed, so the agent refused everyone as "halted"
or "node unclaimed". Concurrent reads are now shared, and a read that FAILS keeps
the last answer (ownership: until invalidated; halt: briefly). A read that
ANSWERS is always taken at once, so a real halt or release still stops the agent.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Generic, List, TypeVar

import pytest

from ciris_engine.logic.runtime import node_fold
from ciris_engine.logic.utils import halt_latch, node_ownership
from ciris_engine.schemas.runtime.accord_halt import AccordHaltReading, AccordHaltState
from ciris_engine.schemas.runtime.node_ownership import NodeOwnership, NodeOwnershipReading

pytestmark = [pytest.mark.real_halt_latch, pytest.mark.real_node_ownership]


def _halt(reading: AccordHaltReading) -> AccordHaltState:
    halted = reading not in (AccordHaltReading.NOT_HALTED, AccordHaltReading.LAPSED)
    return AccordHaltState(halted=halted, reading=reading, read_at=datetime.now(timezone.utc))


def _own(reading: NodeOwnershipReading) -> NodeOwnership:
    return node_ownership._state(reading, node_key_id="ciris-node-x", owner_key_id="owner" if reading == NodeOwnershipReading.OWNED else None)


R = TypeVar("R")


@dataclass
class Reads(Generic[R]):
    """What the node will answer, in order, and what it was asked."""

    script: List[R] = field(default_factory=list)
    calls: List[R] = field(default_factory=list)


@pytest.fixture
def halt_reads(monkeypatch: pytest.MonkeyPatch) -> Reads[AccordHaltReading]:
    reads: Reads[AccordHaltReading] = Reads()
    monkeypatch.setattr(node_fold, "fold_status", lambda: {"folded": True})

    async def read() -> AccordHaltState:
        await asyncio.sleep(0.01)
        reading = reads.script.pop(0) if reads.script else AccordHaltReading.NOT_HALTED
        reads.calls.append(reading)
        return _halt(reading)

    monkeypatch.setattr(halt_latch, "_read_from_node", read)
    return reads


@pytest.mark.asyncio
async def test_a_burst_of_fresh_halt_reads_is_one_node_read(halt_reads: Reads[AccordHaltReading]) -> None:
    states = await asyncio.gather(*(halt_latch.read_halt_latch(fresh=True) for _ in range(200)))
    assert all(not s.halted for s in states)
    assert len(halt_reads.calls) == 1, "200 concurrent fresh reads must share one node read"


@pytest.mark.asyncio
async def test_a_timeout_after_a_good_read_keeps_it_briefly_then_fails_closed(
    halt_reads: Reads[AccordHaltReading], monkeypatch: pytest.MonkeyPatch
) -> None:
    halt_reads.script.extend([AccordHaltReading.NOT_HALTED, AccordHaltReading.NODE_TIMEOUT, AccordHaltReading.NODE_TIMEOUT])
    assert not (await halt_latch.read_halt_latch(fresh=True)).halted
    await asyncio.sleep(0.3)  # past the join window: a new read
    assert not (await halt_latch.read_halt_latch(fresh=True)).halted, "a slow read under load is not a halt"
    monkeypatch.setattr(halt_latch, "_last_good_at", time.monotonic() - halt_latch.HALT_TRANSIENT_GRACE_SECONDS - 1)
    await asyncio.sleep(0.3)
    assert (await halt_latch.read_halt_latch(fresh=True)).halted, "past the grace a failed read fails closed"


@pytest.mark.asyncio
async def test_an_answered_halt_takes_effect_at_once(halt_reads: Reads[AccordHaltReading]) -> None:
    halt_reads.script.extend([AccordHaltReading.NOT_HALTED, AccordHaltReading.IN_EFFECT])
    assert not (await halt_latch.read_halt_latch(fresh=True)).halted
    await asyncio.sleep(0.3)
    state = await halt_latch.read_halt_latch(fresh=True)
    assert state.halted and state.reading == AccordHaltReading.IN_EFFECT


@pytest.mark.asyncio
async def test_boot_and_invalidation_fail_closed_on_a_timeout(halt_reads: Reads[AccordHaltReading]) -> None:
    halt_reads.script.extend([AccordHaltReading.NODE_TIMEOUT, AccordHaltReading.NOT_HALTED, AccordHaltReading.NODE_TIMEOUT])
    assert (await halt_latch.read_halt_latch(fresh=True)).halted, "no good read yet: boot fails closed"
    await asyncio.sleep(0.3)
    assert not (await halt_latch.read_halt_latch(fresh=True)).halted
    halt_latch.invalidate_halt_cache()  # an invocation just arrived
    await asyncio.sleep(0.3)
    assert (await halt_latch.read_halt_latch(fresh=True)).halted, "after invalidation a failed read is not excused"


@pytest.fixture
def owner_reads(monkeypatch: pytest.MonkeyPatch) -> Reads[NodeOwnershipReading]:
    reads: Reads[NodeOwnershipReading] = Reads()

    async def read() -> NodeOwnership:
        await asyncio.sleep(0.01)
        reading = reads.script.pop(0) if reads.script else NodeOwnershipReading.OWNED
        reads.calls.append(reading)
        return _own(reading)

    monkeypatch.setattr(node_ownership, "_read_from_node", read)
    return reads


@pytest.mark.asyncio
async def test_a_burst_of_ownership_reads_is_one_read(owner_reads: Reads[NodeOwnershipReading]) -> None:
    states = await asyncio.gather(*(node_ownership.node_owned(fresh=True) for _ in range(200)))
    assert all(not s.unclaimed for s in states)
    assert len(owner_reads.calls) == 1, "200 concurrent reads must share one ownership read"


@pytest.mark.asyncio
async def test_an_owned_node_stays_owned_through_a_failed_read(owner_reads: Reads[NodeOwnershipReading]) -> None:
    owner_reads.script.extend([NodeOwnershipReading.OWNED, NodeOwnershipReading.READ_TIMEOUT, NodeOwnershipReading.UNOWNED])
    assert not (await node_ownership.node_owned(fresh=True)).unclaimed
    assert not (await node_ownership.node_owned(fresh=True)).unclaimed, "a slow read is not the owner leaving"
    assert (await node_ownership.node_owned(fresh=True)).unclaimed, "an answered UNOWNED is taken at once"


@pytest.mark.asyncio
async def test_before_the_first_owned_read_and_after_invalidation_a_failed_read_holds(
    owner_reads: Reads[NodeOwnershipReading],
) -> None:
    owner_reads.script.extend([NodeOwnershipReading.READ_TIMEOUT, NodeOwnershipReading.OWNED, NodeOwnershipReading.READ_TIMEOUT])
    assert (await node_ownership.node_owned(fresh=True)).unclaimed, "an unclaimed node never runs"
    assert not (await node_ownership.node_owned(fresh=True)).unclaimed
    node_ownership.invalidate_node_ownership_cache()
    assert (await node_ownership.node_owned(fresh=True)).unclaimed




@pytest.mark.asyncio
async def test_an_ownership_read_answers_while_the_default_pool_is_full(monkeypatch: pytest.MonkeyPatch) -> None:
    """Under a burst the default thread pool is busy; the gate read must not queue behind it."""
    import os

    monkeypatch.setattr(node_ownership, "_read_owner_sync", lambda: _own(NodeOwnershipReading.OWNED))
    monkeypatch.setattr(node_ownership, "NODE_OWNERSHIP_READ_TIMEOUT_SECONDS", 0.3)
    monkeypatch.setattr(node_fold, "fold_status", lambda: {"folded": True})
    loop = asyncio.get_running_loop()
    workers = min(32, (os.cpu_count() or 1) + 4)  # ThreadPoolExecutor's default size
    blockers = [loop.run_in_executor(None, time.sleep, 0.8) for _ in range(2 * workers)]
    try:
        state = await node_ownership.node_owned(fresh=True)
        assert state.reading == NodeOwnershipReading.OWNED, "the read queued behind the default pool and timed out"
    finally:
        await asyncio.gather(*blockers)
        await loop.shutdown_default_executor()
