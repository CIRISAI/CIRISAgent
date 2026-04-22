"""
Shutdown manager compatibility module.

This module provides backwards compatibility for code that imports from
the old shutdown_manager location. The functionality is now provided by
the ShutdownService.
"""

import logging
from typing import Any, Callable, Optional

from ciris_engine.logic.services.lifecycle.shutdown import ShutdownService

logger = logging.getLogger(__name__)

# Global instance for compatibility
_global_shutdown_service: Optional[ShutdownService] = None


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
]
