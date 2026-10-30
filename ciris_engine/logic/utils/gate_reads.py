"""Gate reads (halt latch, node ownership) off the shared thread pool.

Both gates fail closed, so a read that cannot finish in time refuses work. Under
a burst the default thread pool is full of persistence and handler work, and the
event loop is busy, so a read queued there timed out waiting its turn and the
agent refused every request as halted or unowned (2026-10-29). Reads here wait
only for the node, each with its own timeout.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Callable, TypeVar

T = TypeVar("T")


async def run_gate_read(read: Callable[[], T]) -> T:
    """Run a blocking gate read on its own daemon thread.

    Not the default pool: under a burst it is full and the read waits its turn.
    A thread per read is cheap here because both readers are single-flight (at
    most one halt read and one ownership read in flight), and a daemon thread
    never outlives the process.
    """
    loop = asyncio.get_running_loop()
    future: "asyncio.Future[T]" = loop.create_future()

    def deliver(result: T, error: BaseException | None) -> None:
        if future.done():
            return
        if error is not None:
            future.set_exception(error)
        else:
            future.set_result(result)

    def worker() -> None:
        try:
            value = read()
        except BaseException as exc:  # noqa: BLE001 - handed back to the awaiting caller
            loop.call_soon_threadsafe(deliver, None, exc)  # type: ignore[arg-type]
        else:
            loop.call_soon_threadsafe(deliver, value, None)

    threading.Thread(target=worker, name="ciris-gate-read", daemon=True).start()
    return await future
