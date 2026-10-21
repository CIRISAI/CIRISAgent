"""
Shutdown manager compatibility module.

This module provides backwards compatibility for code that imports from
the old shutdown_manager location. The functionality is now provided by
the ShutdownService.
"""

import asyncio
import logging
from typing import Any, Callable, Optional

from ciris_engine.logic.services.lifecycle.shutdown import ShutdownService

logger = logging.getLogger(__name__)

# Global instance for compatibility
_global_shutdown_service: Optional[ShutdownService] = None


def reset_global_shutdown_service() -> None:
    """
    Reset the global shutdown service.

    This MUST be called before restarting the asyncio event loop (e.g., in iOS
    app restart scenarios) to avoid "bound to a different event loop" errors.
    """
    global _global_shutdown_service
    if _global_shutdown_service is not None:
        # Clear any asyncio.Event that's bound to the old loop
        _global_shutdown_service._shutdown_event = None
        _global_shutdown_service._shutdown_requested = False
        _global_shutdown_service._shutdown_reason = None
        _global_shutdown_service._emergency_mode = False
        logger.info("Global shutdown service reset for new event loop")
    _global_shutdown_service = None


def reset_global_shutdown_service_if_stale() -> bool:
    """Reset the global service when it belongs to a PREVIOUS event loop (#1122).

    An in-process runtime restart (mobile resume, the `.restart_signal` path)
    starts a new loop in the same process. The module-level service survives
    with `_shutdown_requested=True` from the run that just ended and an Event
    bound to the dead loop, so the restarted runtime either sees "shutdown
    requested" at birth and exits, or raises `bound to a different event loop`
    when it waits. Called from `CIRISRuntime.initialize()`; a no-op when there
    is no global service or it already belongs to the running loop. Returns
    True when a reset happened. Must be called from a running loop.
    """
    global _global_shutdown_service
    service = _global_shutdown_service
    if service is None:
        return False
    loop = asyncio.get_running_loop()
    bound = getattr(service, "_event_loop", None)
    if bound is None or bound is loop:
        return False
    logger.warning(
        "Global shutdown service belongs to a previous event loop (requested=%s, reason=%r) -- "
        "resetting for the restarted runtime (CIRISAgent#1122)",
        getattr(service, "_shutdown_requested", None),
        getattr(service, "_shutdown_reason", None),
    )
    reset_global_shutdown_service()
    return True


# Keep original function definition for type hints
def _get_shutdown_service() -> ShutdownService:
    """Get or create the global shutdown service instance."""
    global _global_shutdown_service
    if _global_shutdown_service is None:
        _global_shutdown_service = ShutdownService()
    return _global_shutdown_service


def is_global_shutdown_requested() -> bool:
    """Check if shutdown has been requested."""
    service = _get_shutdown_service()
    return service.is_shutdown_requested()


def get_global_shutdown_reason() -> Optional[str]:
    """Get the reason for shutdown if any."""
    service = _get_shutdown_service()
    return service.get_shutdown_reason()


def request_global_shutdown(reason: str = "Shutdown requested") -> None:
    """Request a global shutdown."""
    service = _get_shutdown_service()
    # Use the sync version to avoid async/await issues
    service._request_shutdown_sync(reason)


def register_global_shutdown_handler(handler: Callable[[], None]) -> None:
    """Register a shutdown handler."""
    service = _get_shutdown_service()
    service.register_shutdown_handler(handler)


def wait_for_global_shutdown() -> None:
    """Wait for shutdown to be requested (blocking)."""
    service = _get_shutdown_service()
    service.wait_for_shutdown()


async def wait_for_global_shutdown_async() -> None:
    """Wait for shutdown to be requested (async)."""
    service = _get_shutdown_service()
    await service.wait_for_shutdown_async()


async def execute_async_handlers() -> None:
    """Execute all registered async shutdown handlers."""
    service = _get_shutdown_service()
    if hasattr(service, "_execute_async_handlers"):
        await service._execute_async_handlers()


# Add attribute to shutdown service instance for compatibility
class ShutdownManagerWrapper:
    """Wrapper to provide compatibility methods."""

    def __init__(self, service: ShutdownService) -> None:
        self._service = service

    def __getattr__(self, name: str) -> Any:
        return getattr(self._service, name)

    async def execute_async_handlers(self) -> None:
        """Execute all registered async shutdown handlers."""
        if hasattr(self._service, "_execute_async_handlers"):
            await self._service._execute_async_handlers()


def get_shutdown_manager() -> ShutdownManagerWrapper:
    """Get or create the global shutdown service instance."""
    global _global_shutdown_service
    if _global_shutdown_service is None:
        _global_shutdown_service = ShutdownService()
    return ShutdownManagerWrapper(_global_shutdown_service)


# Export for compatibility
__all__ = [
    "get_shutdown_manager",
    "is_global_shutdown_requested",
    "get_global_shutdown_reason",
    "request_global_shutdown",
    "register_global_shutdown_handler",
    "wait_for_global_shutdown",
    "wait_for_global_shutdown_async",
    "execute_async_handlers",
    "reset_global_shutdown_service",
    "reset_global_shutdown_service_if_stale",
]
