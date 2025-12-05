"""
Shutdown Service for CIRIS Trinity Architecture.

Manages graceful shutdown coordination across the system.
This replaces the shutdown_manager.py utility with a proper service.
"""

import asyncio
import logging
from threading import Lock
from typing import Any, Awaitable, Callable, Dict, List, Optional

from ciris_engine.logic.services.base_infrastructure_service import BaseInfrastructureService
from ciris_engine.protocols.services import ShutdownServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.metadata import ServiceMetadata

logger = logging.getLogger(__name__)


class ShutdownService(BaseInfrastructureService, ShutdownServiceProtocol):
    """Service for coordinating graceful shutdown."""

    def __init__(self) -> None:
        """Initialize the shutdown service."""
        # Initialize base class without time_service (we ARE a critical infrastructure service)
        super().__init__(service_name="ShutdownService", version="1.0.0")

        # Shutdown-specific attributes
        self._shutdown_requested = False
        self._shutdown_reason: Optional[str] = None
        self._shutdown_handlers: List[Callable[[], None]] = []
        self._async_shutdown_handlers: List[Callable[[], Awaitable[None]]] = []
        self._lock = Lock()
        self._shutdown_event: Optional[asyncio.Event] = None
        self._emergency_mode = False
        self._force_kill_task: Optional[asyncio.Task[Any]] = None

        # v1.4.3 metric tracking
        self._shutdown_requests_total = 0
        self._shutdown_graceful_total = 0
        self._shutdown_emergency_total = 0

    async def start(self) -> None:
        """Start the service."""
        await super().start()
        try:
            # Create shutdown event if in async context
            self._shutdown_event = asyncio.Event()
        except RuntimeError:
            # Not in async context yet
            pass

    async def stop(self) -> None:
        """Stop the service."""
        await super().stop()

    # Required abstract methods from BaseService

    def get_service_type(self) -> ServiceType:
        """Get the service type enum value."""
        return ServiceType.SHUTDOWN

    def _get_actions(self) -> List[str]:
        """Get list of actions this service provides."""
        return [
            "request_shutdown",
            "register_shutdown_handler",
            "is_shutdown_requested",
            "get_shutdown_reason",
            "emergency_shutdown",
        ]

    def _check_dependencies(self) -> bool:
        """Check if all required dependencies are available."""
        # ShutdownService has no dependencies
        return True

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities with custom metadata."""
        # Get metadata from parent's _get_metadata()
        service_metadata = self._get_metadata()

        # Set infrastructure-specific fields
        if service_metadata:
            service_metadata.category = "infrastructure"
            service_metadata.critical = True
            service_metadata.description = "Coordinates graceful system shutdown"

        return ServiceCapabilities(
            service_name=self.service_name,
            actions=self._get_actions(),
            version=self._version,
            dependencies=list(self._dependencies),
            metadata=service_metadata,
        )

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect shutdown-specific metrics."""
        metrics = super()._collect_custom_metrics()

        with self._lock:
            handler_count = len(self._shutdown_handlers) + len(self._async_shutdown_handlers)

        metrics.update(
            {
                "shutdown_requested": float(self._shutdown_requested),
                "registered_handlers": float(handler_count),
                "emergency_mode": float(self._emergency_mode),
            }
        )

        return metrics

    async def get_metrics(self) -> Dict[str, float]:
        """
        Get all shutdown service metrics including base, custom, and v1.4.3 specific.
        """
        # Get all base + custom metrics
        metrics = self._collect_metrics()

        with self._lock:
            shutdown_requests_total = float(self._shutdown_requests_total)
            shutdown_graceful_total = float(self._shutdown_graceful_total)
            shutdown_emergency_total = float(self._shutdown_emergency_total)

        # Calculate uptime from base service
        shutdown_uptime_seconds = self._calculate_uptime()

        # Add v1.4.3 specific metrics
        metrics.update(
            {
                "shutdown_requests_total": shutdown_requests_total,
                "shutdown_graceful_total": shutdown_graceful_total,
                "shutdown_emergency_total": shutdown_emergency_total,
                "shutdown_uptime_seconds": shutdown_uptime_seconds,
            }
        )

        return metrics

    async def request_shutdown(self, reason: str) -> None:
        """
        Request system shutdown (async version).

        Args:
            reason: Human-readable reason for shutdown
        """
        # Call the sync version but ensure it's properly awaitable
        self._request_shutdown_sync(reason)
        # No need to return anything - this method is async void

    def _request_shutdown_sync(self, reason: str) -> None:
        """
        Request system shutdown (sync version).

        Args:
            reason: Human-readable reason for shutdown
        """
        with self._lock:
            if self._shutdown_requested:
                logger.debug(f"Shutdown already requested, ignoring duplicate: {reason}")
                return

            self._shutdown_requested = True
            self._shutdown_reason = reason
            self._shutdown_requests_total += 1
            self._shutdown_graceful_total += 1

        logger.critical(f"SYSTEM SHUTDOWN REQUESTED: {reason}")

        # Set event if available
        if self._shutdown_event:
            self._shutdown_event.set()

        # Execute sync handlers
        self._execute_sync_handlers()

    def register_shutdown_handler(self, handler: Callable[[], None]) -> None:
        """
        Register a shutdown handler.

        Args:
            handler: Function to call during shutdown
        """
        with self._lock:
            self._shutdown_handlers.append(handler)
            logger.debug(f"Registered shutdown handler: {handler.__name__}")

    def _register_async_shutdown_handler(self, handler: Callable[[], Awaitable[None]]) -> None:
        """
        Register an async shutdown handler (internal method).

        Args:
            handler: Async function to call during shutdown
        """
        with self._lock:
            self._async_shutdown_handlers.append(handler)
            logger.debug(f"Registered async shutdown handler: {handler.__name__}")

    def is_shutdown_requested(self) -> bool:
        """Check if shutdown has been requested."""
        return self._shutdown_requested

    def is_force_shutdown(self) -> bool:
        """Check if this is a forced/emergency shutdown."""
        with self._lock:
            return self._emergency_mode

    async def _wait_for_shutdown(self) -> None:
        """Wait for shutdown signal (async) - internal method."""
        if not self._shutdown_event:
            # Create event if not exists
            self._shutdown_event = asyncio.Event()

            # If shutdown already requested, set the event
            if self._shutdown_requested:
                self._shutdown_event.set()

        await self._shutdown_event.wait()

    def get_shutdown_reason(self) -> Optional[str]:
        """Get the reason for shutdown."""
        return self._shutdown_reason

    def _execute_sync_handlers(self) -> None:
        """Execute all registered synchronous shutdown handlers."""
        with self._lock:
            handlers = self._shutdown_handlers.copy()

        for handler in handlers:
            try:
                handler()
                logger.debug(f"Executed shutdown handler: {handler.__name__}")
            except Exception as e:
                logger.error(f"Error in shutdown handler {handler.__name__}: {e}")

    async def _execute_async_handlers(self) -> None:
        """Execute all registered asynchronous shutdown handlers - internal method."""
        with self._lock:
            handlers = self._async_shutdown_handlers.copy()

        for handler in handlers:
            try:
                if asyncio.iscoroutinefunction(handler):
                    await handler()
                else:
                    handler()
                logger.debug(f"Executed async shutdown handler: {handler.__name__}")
            except Exception as e:
                logger.error(f"Error in async shutdown handler {handler.__name__}: {e}")

    def wait_for_shutdown(self) -> None:
        """Wait for shutdown to be requested (blocking)."""
        import time

        while not self._shutdown_requested:
            time.sleep(0.1)

    async def wait_for_shutdown_async(self) -> None:
        """Wait for shutdown to be requested (async)."""
        await self._wait_for_shutdown()

    async def emergency_shutdown(self, reason: str, timeout_seconds: int = 5) -> None:
        """
        Execute emergency shutdown without negotiation.

        This method is used by the emergency shutdown endpoint to force
        immediate system termination with minimal cleanup.

        Args:
            reason: Why emergency shutdown was triggered
            timeout_seconds: Grace period before force kill (default 5s)
        """
        logger.critical(f"EMERGENCY SHUTDOWN: {reason}")

        # Set emergency flags
        self._set_emergency_flags(reason)

        # Set shutdown event immediately
        if self._shutdown_event:
            self._shutdown_event.set()

        # Notify all handlers with timeout
        await self._execute_handlers_with_timeout(timeout_seconds)

        # Start force kill timer
        self._force_kill_task = asyncio.create_task(self._force_kill_after_timeout(timeout_seconds))

        # Try graceful exit first
        logger.info("Attempting graceful exit...")
        import sys

        sys.exit(1)

    def _set_emergency_flags(self, reason: str) -> None:
        """Set emergency shutdown flags and update metrics."""
        with self._lock:
            self._shutdown_requested = True
            self._shutdown_reason = f"EMERGENCY: {reason}"
            self._emergency_mode = True
            self._shutdown_requests_total += 1
            self._shutdown_emergency_total += 1

    async def _execute_handlers_with_timeout(self, timeout_seconds: int) -> None:
        """Execute shutdown handlers with timeout protection."""
        try:
            # Execute sync handlers first (quick)
            self._execute_sync_handlers()

            # Execute async handlers with timeout
            await asyncio.wait_for(
                self._execute_async_handlers(), timeout=timeout_seconds / 2  # Use half timeout for handlers
            )
        except asyncio.TimeoutError:
            logger.warning("Emergency shutdown handlers timed out")
        except Exception as e:
            logger.error(f"Error during emergency shutdown: {e}")

    async def _force_kill_after_timeout(self, timeout_seconds: int) -> None:
        """Force process termination after timeout period."""
        await asyncio.sleep(timeout_seconds)
        logger.critical("Emergency shutdown timeout reached - forcing termination")

        import os
        import signal

        # Safety check: only kill our own process
        pid = os.getpid()
        logger.critical(f"Sending SIGKILL to process {pid}")

        self._send_kill_signal(pid, signal)

    def _send_kill_signal(self, pid: int, signal: Any) -> None:
        """Send kill signal to process with platform-specific handling."""
        try:
            self._try_primary_signal(pid, signal)
        except (OSError, AttributeError) as e:
            logger.error(f"Failed to force kill process: {e}")
            self._try_fallback_signal(pid, signal)

    def _try_primary_signal(self, pid: int, signal: Any) -> None:
        """Try to send primary kill signal (SIGKILL or SIGTERM)."""
        import os

        # Use platform-specific signals
        # SIGKILL doesn't exist on Windows - use SIGTERM or sys.exit
        if hasattr(signal, "SIGKILL"):
            # NOSONAR: Safe - only sending signal to our own process (os.getpid())
            os.kill(pid, signal.SIGKILL)  # NOSONAR python:S4828
        elif hasattr(signal, "SIGTERM"):
            # NOSONAR: Safe - only sending signal to our own process (os.getpid())
            os.kill(pid, signal.SIGTERM)  # NOSONAR python:S4828
        else:
            # Windows fallback - just exit
            import sys

            sys.exit(1)

    def _try_fallback_signal(self, pid: int, signal: Any) -> None:
        """Try fallback kill signal if primary fails."""
        import os

        try:
            if hasattr(signal, "SIGTERM"):
                # NOSONAR: Safe - only sending signal to our own process (os.getpid())
                os.kill(pid, signal.SIGTERM)  # NOSONAR python:S4828
            else:
                # Windows fallback
                import sys

                sys.exit(1)
        except (OSError, AttributeError):
            # Last resort
            import sys

            sys.exit(1)
