"""
Initialization manager compatibility module.

This module provides backwards compatibility for code that imports from
the old initialization_manager location. The functionality is now provided by
the InitializationService.
"""

import logging
from typing import Callable, Optional

from ciris_engine.logic.services.lifecycle.initialization import InitializationService
from ciris_engine.schemas.services.operations import InitializationPhase, InitializationStatus

logger = logging.getLogger(__name__)


# Re-export for compatibility
class InitializationError(Exception):
    """Error during initialization."""


# Re-export enums
__all__ = ["InitializationPhase", "InitializationStatus", "InitializationError", "get_initialization_manager"]

# Global instance for compatibility
_global_initialization_service: Optional[InitializationService] = None


def get_initialization_manager() -> InitializationService:
    """Get or create the global initialization service instance."""
    global _global_initialization_service
    if _global_initialization_service is None:
        from ciris_engine.logic.services.lifecycle.time import TimeService

        time_service = TimeService()
        _global_initialization_service = InitializationService(time_service=time_service)
    return _global_initialization_service


def register_initialization_callback(callback: Callable[[], None]) -> None:
    """Register an initialization callback."""
    # Legacy method - no longer supported
    logger.warning("register_initialization_callback is deprecated - use register_step instead")


async def initialize_components() -> None:
    """Initialize all registered components."""
    service = get_initialization_manager()
    await service.initialize()


def is_initialized() -> bool:
    """Check if the system has been initialized."""
    service = get_initialization_manager()
    return service._initialization_complete


def reset_initialization() -> None:
    """Reset initialization state (for testing)."""
    service = get_initialization_manager()
    service._initialization_complete = False
    service._completed_steps = []
    service._error = None


# Export for compatibility
__all__ = [
    "get_initialization_manager",
    "register_initialization_callback",
    "initialize_components",
    "is_initialized",
    "reset_initialization",
]
