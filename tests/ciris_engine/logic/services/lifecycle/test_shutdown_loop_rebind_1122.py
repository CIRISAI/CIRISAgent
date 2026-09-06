"""An in-process runtime restart must not wedge on a shutdown Event from the old loop.

CIRISAgent#1122: the mobile client restarts the runtime in the same process
(new `asyncio.run`, same module globals). The ShutdownService's Event was
bound to the dead loop, so the restarted runtime raised `RuntimeError: ... is
bound to a different event loop` in ShutdownService and never came back; and
the module-level shutdown service still said "shutdown requested" from the
run that had just ended.
"""

from __future__ import annotations

import asyncio

from ciris_engine.logic.services.lifecycle.shutdown import ShutdownService
from ciris_engine.logic.utils import shutdown_manager


def _bind_in_a_loop(service: ShutdownService) -> None:
    """Wait on the event under one loop, then let that loop die."""

    async def _run() -> None:
        await service.start()
        waiter = asyncio.ensure_future(service.wait_for_shutdown_async())
        await asyncio.sleep(0)  # the Event binds to THIS loop on first wait
        waiter.cancel()
        try:
            await waiter
        except asyncio.CancelledError:
            pass

    asyncio.run(_run())


def test_wait_after_a_loop_swap_does_not_raise_and_still_observes_the_request() -> None:
    service = ShutdownService()
    _bind_in_a_loop(service)
    assert service._event_loop is not None and service._event_loop.is_closed()

    async def _second_loop() -> None:
        waiter = asyncio.ensure_future(service.wait_for_shutdown_async())
        await asyncio.sleep(0)
        await service.request_shutdown("restart test")
        await asyncio.wait_for(waiter, timeout=2.0)

    asyncio.run(_second_loop())  # used to raise "bound to a different event loop"
    assert service.is_shutdown_requested()


def test_a_request_made_before_the_swap_is_carried_into_the_new_loop() -> None:
    service = ShutdownService()
    _bind_in_a_loop(service)
    service._request_shutdown_sync("requested on the old loop")

    async def _second_loop() -> None:
        await asyncio.wait_for(service.wait_for_shutdown_async(), timeout=2.0)

    asyncio.run(_second_loop())


def test_stale_global_service_is_reset_only_when_it_belongs_to_a_dead_loop() -> None:
    shutdown_manager.reset_global_shutdown_service()
    assert asyncio.run(_call_reset()) is False, "no global service -> nothing to reset"

    service = shutdown_manager._get_shutdown_service()
    _bind_in_a_loop(service)
    shutdown_manager.request_global_shutdown("the previous run ended")
    assert shutdown_manager.is_global_shutdown_requested()

    assert asyncio.run(_call_reset()) is True
    assert not shutdown_manager.is_global_shutdown_requested(), "the restarted runtime must not exit at birth"

    # Same loop, freshly bound: not stale, not reset.
    async def _same_loop() -> bool:
        svc = shutdown_manager._get_shutdown_service()
        await svc.start()
        return shutdown_manager.reset_global_shutdown_service_if_stale()

    assert asyncio.run(_same_loop()) is False
    shutdown_manager.reset_global_shutdown_service()


async def _call_reset() -> bool:
    return shutdown_manager.reset_global_shutdown_service_if_stale()
