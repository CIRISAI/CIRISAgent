"""
Shutdown Service for CIRIS Trinity Architecture.

Manages graceful shutdown coordination across the system.
This replaces the shutdown_manager.py utility with a proper service.
"""

import asyncio
import logging
import threading
from threading import Lock
from typing import Awaitable, Callable, Dict, List, Optional

from ciris_engine.logic.services.base_infrastructure_service import BaseInfrastructureService
from ciris_engine.protocols.services import ShutdownServiceProtocol
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities
from ciris_engine.schemas.services.metadata import ServiceMetadata

logger = logging.getLogger(__name__)

#: How long an OWNED headless process waits for the runtime to finish stopping
#: after an emergency shutdown before it is interrupted (and, after the same again,
#: terminated). Never used on an embedded or desktop host (CIRISAgent#1240).
OWNED_PROCESS_EXIT_GRACE_SECONDS = 30.0


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
        #: The loop `_shutdown_event` is bound to. An asyncio.Event binds to the loop
        #: that first awaits it; awaiting it from a later loop (an in-process runtime
        #: RESTART -- mobile resume, CIRISAgent#1122) raises `RuntimeError: ... is
        #: bound to a different event loop`, and the restarted runtime never comes
        #: back. So the event is re-created whenever the running loop is not the one
        #: it was made for, carrying the requested-state over.
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        self._emergency_mode = False
        #: Owned-process exit watchdog cancel switch (headless server only, #1240).
        self._owned_exit_cancel: Optional[threading.Event] = None

        # v1.4.3 metric tracking
        self._shutdown_requests_total = 0
        self._shutdown_graceful_total = 0
        self._shutdown_emergency_total = 0

    async def start(self) -> None:
        """Start the service."""
        await super().start()
        try:
            self._event_for_current_loop()
        except RuntimeError:
            # Not in async context yet
            pass

    def _event_for_current_loop(self) -> asyncio.Event:
        """Return `_shutdown_event`, re-made if it belongs to another loop (#1122).

        A fresh event is created when there is none or when the running loop is
        not the one the existing event was made for; a pending shutdown request
        is carried over by setting it immediately. Must be called from a running
        loop (raises RuntimeError otherwise, like `asyncio.get_running_loop`).
        """
        loop = asyncio.get_running_loop()
        if self._shutdown_event is None or self._event_loop is not loop:
            if self._shutdown_event is not None and self._event_loop is not None:
                logger.info(
                    "ShutdownService: shutdown event re-created for a new event loop "
                    "(in-process runtime restart) -- pending request carried over: %s",
                    self._shutdown_requested,
                )
            self._shutdown_event = asyncio.Event()
            self._event_loop = loop
            if self._shutdown_requested:
                self._shutdown_event.set()
        return self._shutdown_event

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
        await self._event_for_current_loop().wait()

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
        Stop the agent runtime immediately, without the shutdown negotiation.

        Used by every forced/emergency entry point (``POST /system/shutdown``
        with ``force=True`` behind the WA-standing gate, and the WA-signed
        ``/emergency/shutdown`` command). It stops the AGENT, never the host
        (CIRISAgent#1240):

        1. sets the emergency flags here AND on the global shutdown service --
           the one the runtime loop watches (``request_global_shutdown``) -- so
           the shutdown processor skips negotiation and the runtime stops its
           processors, adapters and :8080;
        2. runs the registered shutdown handlers, bounded by ``timeout_seconds``;
        3. returns. It never calls ``sys.exit``, ``os._exit``, ``os.kill`` or
           ``execv``: on Android, iOS and the desktop install the process
           belongs to the host app.

        Only when the agent owns its process (headless server under a
        supervisor, ``device_class.agent_owns_process``) is a bounded exit
        watchdog armed, so a runtime that hangs while stopping still ends and
        the supervisor sees it.

        Args:
            reason: Why emergency shutdown was triggered
            timeout_seconds: Bound on the shutdown handlers (default 5s)
        """
        if not self._set_emergency_flags(reason):
            logger.warning(f"Emergency shutdown already in progress; ignoring duplicate: {reason}")
            return

        logger.critical(f"EMERGENCY SHUTDOWN: {reason}")

        # Wake any waiter on THIS instance.
        if self._shutdown_event:
            self._shutdown_event.set()

        # Route to the global shutdown service -- the one the runtime loop and
        # the shutdown processor read. When this instance IS the global one
        # (the runtime adopts it, see ServiceInitializer) the request below is a
        # de-duplicated no-op; when it is not, this is what actually stops the
        # loop (the defect CIRISAgent#1240 names).
        from ciris_engine.logic.utils.shutdown_manager import mark_global_shutdown_emergency, request_global_shutdown

        mark_global_shutdown_emergency()
        request_global_shutdown(f"EMERGENCY: {reason}")

        # Notify handlers, bounded.
        await self._execute_handlers_with_timeout(timeout_seconds)

        from ciris_engine.logic.runtime.device_class import agent_owns_process

        if agent_owns_process():
            self._arm_owned_process_exit(OWNED_PROCESS_EXIT_GRACE_SECONDS)
        else:
            logger.critical(
                "Emergency shutdown: embedded/desktop host -- stopping the agent runtime and :8080 only; "
                "the host process is not ours to end"
            )

    def _arm_owned_process_exit(self, grace_seconds: float) -> None:
        """Bounded exit for a process the agent OWNS (headless server only).

        The runtime normally finishes stopping well inside ``grace_seconds`` and
        ``main.py`` exits on its own. If it is still alive after the grace, the
        main thread is interrupted (``KeyboardInterrupt`` -> main.py's normal
        exit path); if it is STILL alive after a second grace, the supervisor-
        owned process is terminated so it cannot hang forever. Callers must have
        checked ``agent_owns_process()`` -- this is never armed on an embedded or
        desktop host.
        """
        import threading

        if self._owned_exit_cancel is not None:
            return
        cancel = threading.Event()
        self._owned_exit_cancel = cancel

        def _watchdog() -> None:
            if cancel.wait(grace_seconds):
                return
            import _thread

            logger.critical(
                "Emergency shutdown: runtime still alive after %.0fs on an owned headless process -- "
                "interrupting the main thread for a normal exit",
                grace_seconds,
            )
            _thread.interrupt_main()
            if cancel.wait(grace_seconds):
                return
            from ciris_engine.logic.utils.hard_kill import terminate_immediately

            terminate_immediately(
                f"emergency shutdown did not complete within {2 * grace_seconds:.0f}s (owned process)"
            )

        threading.Thread(target=_watchdog, name="OwnedProcessExitWatchdog", daemon=True).start()
        logger.warning("Emergency shutdown: owned headless process -- exit watchdog armed (%.0fs grace)", grace_seconds)

    def cancel_owned_process_exit(self) -> None:
        """Disarm the owned-process exit watchdog (tests; a completed in-process stop)."""
        if self._owned_exit_cancel is not None:
            self._owned_exit_cancel.set()
            self._owned_exit_cancel = None

    def mark_emergency(self) -> None:
        """Mark a (possibly already requested) shutdown as emergency: no negotiation."""
        with self._lock:
            self._emergency_mode = True

    def _set_emergency_flags(self, reason: str) -> bool:
        """Set emergency shutdown flags and update metrics.

        Returns False when an emergency shutdown is already in progress (the
        request is a duplicate). A pending GRACEFUL shutdown is escalated.
        """
        with self._lock:
            if self._emergency_mode and self._shutdown_requested:
                return False
            self._shutdown_requested = True
            self._shutdown_reason = f"EMERGENCY: {reason}"
            self._emergency_mode = True
            self._shutdown_requests_total += 1
            self._shutdown_emergency_total += 1
        return True

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
