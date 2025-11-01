"""
Base message bus implementation
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, Generic, List, Optional, TypeVar

if TYPE_CHECKING:
    from ciris_engine.protocols.infrastructure.base import ServiceRegistryProtocol

from ciris_engine.protocols.services import Service
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.types import JSONDict

logger = logging.getLogger(__name__)


@dataclass
class BusMessage:
    """Base message for all buses"""

    id: str
    handler_name: str
    timestamp: datetime
    metadata: JSONDict


# Define the service type variable
ServiceT = TypeVar("ServiceT", bound=Service)


class BaseBus(ABC, Generic[ServiceT]):
    """
    Base class for all typed message buses.

    Each bus:
    - Handles one service type
    - Manages its own queue
    - Routes to appropriate services
    - Handles failures gracefully
    """

    def __init__(
        self, service_type: ServiceType, service_registry: "ServiceRegistryProtocol", max_queue_size: int = 1000
    ):
        self.service_type = service_type
        self.service_registry = service_registry
        self.max_queue_size = max_queue_size

        # Message queue
        self._queue: asyncio.Queue[BusMessage] = asyncio.Queue(maxsize=max_queue_size)

        # Processing state
        self._running = False
        self._process_task: Optional[asyncio.Task[None]] = None
        self._shutdown_event = asyncio.Event()

        # Metrics
        self._processed_count = 0
        self._failed_count = 0

        logger.info(f"{self.__class__.__name__} initialized for {service_type.value}")

    async def start(self) -> None:
        """Start the bus processing loop"""
        if self._running:
            logger.warning(f"{self.__class__.__name__} already running")
            return

        self._running = True
        self._process_task = asyncio.create_task(self._process_loop())
        logger.info(f"{self.__class__.__name__} started")

    async def stop(self) -> None:
        """Stop the bus processing loop"""
        self._running = False
        self._shutdown_event.set()
        if self._process_task:
            try:
                await asyncio.wait_for(self._process_task, timeout=2.0)
            except asyncio.TimeoutError:
                logger.warning(f"{self.__class__.__name__} shutdown timeout, cancelling")
                self._process_task.cancel()
                try:
                    await self._process_task
                except asyncio.CancelledError:
                    pass  # NOSONAR - Intentionally not re-raising in stop() method
        logger.info(f"{self.__class__.__name__} stopped")

    async def _process_loop(self) -> None:
        """Main processing loop - event-driven, no busy-looping"""
        while self._running:
            try:
                # Wait indefinitely for messages or shutdown
                get_task = asyncio.create_task(self._queue.get())
                shutdown_task = asyncio.create_task(self._shutdown_event.wait())

                done, pending = await asyncio.wait({get_task, shutdown_task}, return_when=asyncio.FIRST_COMPLETED)

                # Cancel pending tasks
                for task in pending:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass  # NOSONAR - Intentionally suppressing cancellation of pending tasks during cleanup

                # Check if shutdown was triggered
                if shutdown_task in done:
                    break

                # Process the message
                message = await get_task
                await self._process_message(message)
                self._processed_count += 1

            except asyncio.CancelledError:
                # Re-raise to allow proper cancellation
                raise
            except Exception as e:
                logger.error(f"Error processing message in {self.__class__.__name__}: {e}", exc_info=True)
                self._failed_count += 1

    @abstractmethod
    async def _process_message(self, message: BusMessage) -> None:
        """Process a single message - must be implemented by subclasses"""

    async def _handle_failed_message(self, message: BusMessage, error: Exception) -> None:
        """Handle a failed message - can be overridden"""
        logger.error(f"Failed to process message {message.id} in {self.__class__.__name__}: {error}")

    async def get_service(
        self, handler_name: str, required_capabilities: Optional[List[str]] = None
    ) -> Optional[ServiceT]:
        """Get a service instance for this bus's service type

        Args:
            handler_name: Kept for compatibility but ignored (all services are global)
            required_capabilities: Optional list of required capabilities

        Returns:
            Service instance or None
        """
        service = await self.service_registry.get_service(
            handler=handler_name,  # Ignored by registry, all services are global
            service_type=self.service_type,
            required_capabilities=required_capabilities,
        )
        # Trust the registry returns the right type
        return service

    def get_queue_size(self) -> int:
        """Get current queue size"""
        return self._queue.qsize()

    def get_stats(self) -> JSONDict:
        """Get bus statistics"""
        return {
            "service_type": self.service_type.value,
            "queue_size": self.get_queue_size(),
            "processed": self._processed_count,
            "failed": self._failed_count,
            "running": self._running,
        }

    async def _enqueue(self, message: BusMessage) -> bool:
        """Add a message to the queue"""
        try:
            # Try to add without blocking
            self._queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            logger.error(f"{self.__class__.__name__} queue full, dropping message {message.id}")
            return False
