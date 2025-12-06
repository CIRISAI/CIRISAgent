"""
Runtime Control message bus - handles all runtime control operations with safety checks
"""

import asyncio
import logging
from enum import Enum
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

from ciris_engine.protocols.services import RuntimeControlService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.infrastructure.base import BusMetrics
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core.runtime import (
    AdapterInfo,
    AdapterStatus,
    ConfigSnapshot,
    ProcessorControlResponse,
    ProcessorQueueStatus,
    ProcessorStatus,
)

from .base_bus import BaseBus, BusMessage

logger = logging.getLogger(__name__)


class OperationPriority(str, Enum):
    """Priority levels for runtime operations"""

    CRITICAL = "critical"  # Shutdown, emergency stop
    HIGH = "high"  # Configuration changes
    NORMAL = "normal"  # Status queries
    LOW = "low"  # Metrics, non-essential ops


class RuntimeControlBus(BaseBus[RuntimeControlService]):
    """
    Message bus for all runtime control operations.

    CRITICAL: This bus manages system lifecycle and must:
    - Serialize configuration changes
    - Validate operations before execution
    - Maintain operation ordering
    - Provide graceful degradation
    """

    def __init__(
        self,
        service_registry: "ServiceRegistry",
        time_service: TimeServiceProtocol,
        telemetry_service: Optional[Any] = None,
    ):
        super().__init__(service_type=ServiceType.RUNTIME_CONTROL, service_registry=service_registry)
        self._time_service = time_service
        self._start_time = time_service.now() if time_service else None
        # Track ongoing operations to prevent conflicts
        self._active_operations: Dict[str, asyncio.Task[Any]] = {}
        self._operation_lock = asyncio.Lock()
        self._shutting_down = False

        # Metrics tracking for v1.4.3
        self._commands_sent = 0
        self._state_broadcasts = 0
        self._emergency_stops = 0

    async def get_processor_queue_status(self, handler_name: str = "default") -> ProcessorQueueStatus:
        """Get processor queue status"""
        service = await self.get_service(
            handler_name=handler_name, required_capabilities=["get_processor_queue_status"]
        )

        if not service:
            logger.error(f"No runtime control service available for {handler_name}")
            # Return empty status on error
            return ProcessorQueueStatus(
                processor_name=handler_name,
                queue_size=0,
                max_size=1000,
                processing_rate=0.0,
                average_latency_ms=0.0,
                oldest_message_age_seconds=None,
            )

        try:
            self._commands_sent += 1
            return await service.get_processor_queue_status()
        except Exception as e:
            logger.error(f"Failed to get queue status: {e}", exc_info=True)
            # Return empty status on exception
            return ProcessorQueueStatus(
                processor_name=handler_name,
                queue_size=0,
                max_size=1000,
                processing_rate=0.0,
                average_latency_ms=0.0,
                oldest_message_age_seconds=None,
            )

    async def shutdown_runtime(self, reason: str, handler_name: str = "default") -> ProcessorControlResponse:
        """Shutdown the runtime gracefully"""
        async with self._operation_lock:
            if self._shutting_down:
                logger.info("Shutdown already in progress")
                return ProcessorControlResponse(
                    success=True,
                    processor_name=handler_name,
                    operation="shutdown",
                    new_status=ProcessorStatus.STOPPED,
                    error=None,
                )

            service = await self.get_service(handler_name=handler_name, required_capabilities=["shutdown_runtime"])

            if not service:
                logger.error(f"No runtime control service available for {handler_name}")
                return ProcessorControlResponse(
                    success=False,
                    processor_name=handler_name,
                    operation="shutdown",
                    new_status=ProcessorStatus.ERROR,
                    error="Service unavailable",
                )

            try:
                logger.warning(f"RUNTIME SHUTDOWN triggered by {handler_name}: reason='{reason}'")
                self._shutting_down = True
                self._emergency_stops += 1

                # Cancel all active operations
                for op_name, task in self._active_operations.items():
                    logger.info(f"Cancelling active operation: {op_name}")
                    task.cancel()

                self._active_operations.clear()

                response = await service.shutdown_runtime(reason)

                return response
            except Exception as e:
                logger.error(f"Exception during shutdown: {e}", exc_info=True)
                return ProcessorControlResponse(
                    success=False,
                    processor_name=handler_name,
                    operation="shutdown",
                    new_status=ProcessorStatus.ERROR,
                    error=str(e),
                )

    async def get_config(
        self, path: Optional[str] = None, include_sensitive: bool = False, handler_name: str = "default"
    ) -> ConfigSnapshot:
        """Get configuration value(s)"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["get_config"])

        if not service:
            logger.error(f"No runtime control service available for {handler_name}")
            return ConfigSnapshot(
                configs={}, version="unknown", metadata={"error": "Runtime control service unavailable"}
            )

        try:
            self._commands_sent += 1
            return await service.get_config(path, include_sensitive)
        except Exception as e:
            logger.error(f"Failed to get config: {e}", exc_info=True)
            return ConfigSnapshot(configs={}, version="unknown", metadata={"error": str(e)})

    async def get_runtime_status(self, handler_name: str = "default") -> JSONDict:
        """Get runtime status - safe to call anytime"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["get_runtime_status"])

        if not service:
            logger.error(f"No runtime control service available for {handler_name}")
            return {"status": "error", "message": "Runtime control service unavailable"}

        try:
            self._commands_sent += 1
            response = await service.get_runtime_status()
            self._state_broadcasts += 1

            # Convert RuntimeStatusResponse to dict and add bus-level status
            status_dict: JSONDict = {
                "is_running": response.is_running,
                "uptime_seconds": response.uptime_seconds,
                "processor_count": response.processor_count,
                "adapter_count": response.adapter_count,
                "total_messages_processed": response.total_messages_processed,
                "current_load": response.current_load,
                "bus_status": {
                    "active_operations": list(self._active_operations.keys()),
                    "shutting_down": self._shutting_down,
                },
            }

            return status_dict
        except Exception as e:
            logger.error(f"Failed to get runtime status: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    async def load_adapter(
        self,
        adapter_type: str,
        adapter_id: str,
        config: JSONDict,
        auto_start: bool = True,
        handler_name: str = "default",
    ) -> AdapterInfo:
        """Load a new adapter instance"""
        if self._shutting_down:
            logger.warning("Cannot load adapter during shutdown")
            return AdapterInfo(
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                status=AdapterStatus.ERROR,
                started_at=self._time_service.now(),
                messages_processed=0,
                error_count=0,
                last_error="System shutting down",
                tools=None,
            )

        service = await self.get_service(handler_name=handler_name, required_capabilities=["load_adapter"])

        if not service:
            logger.error(f"No runtime control service available for {handler_name}")
            return AdapterInfo(
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                status=AdapterStatus.ERROR,
                started_at=self._time_service.now(),
                messages_processed=0,
                error_count=0,
                last_error="Service unavailable",
                tools=None,
            )

        try:
            logger.info(f"Loading adapter {adapter_id} of type {adapter_type}")
            self._commands_sent += 1
            # Cast config to Dict[str, object] for protocol compatibility
            operation_response = await service.load_adapter(
                adapter_type, adapter_id, cast(Dict[str, object], config), auto_start
            )
            # Convert AdapterOperationResponse to AdapterInfo
            return AdapterInfo(
                adapter_id=operation_response.adapter_id,
                adapter_type=operation_response.adapter_type,
                status=operation_response.status,
                started_at=operation_response.timestamp if operation_response.success else None,
                messages_processed=0,
                error_count=0 if operation_response.success else 1,
                last_error=operation_response.error,
                tools=None,
            )
        except Exception as e:
            logger.error(f"Failed to load adapter: {e}", exc_info=True)
            return AdapterInfo(
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                status=AdapterStatus.ERROR,
                started_at=self._time_service.now(),
                messages_processed=0,
                error_count=1,
                last_error=str(e),
                tools=None,
            )

    async def unload_adapter(self, adapter_id: str, force: bool = False, handler_name: str = "default") -> AdapterInfo:
        """Unload an adapter instance"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["unload_adapter"])

        if not service:
            logger.error(f"No runtime control service available for {handler_name}")
            return AdapterInfo(
                adapter_id=adapter_id,
                adapter_type="unknown",
                status=AdapterStatus.ERROR,
                started_at=self._time_service.now(),
                messages_processed=0,
                error_count=1,
                last_error="Service unavailable",
                tools=None,
            )

        try:
            logger.info(f"Unloading adapter {adapter_id}")
            operation_response = await service.unload_adapter(adapter_id, force)
            # Convert AdapterOperationResponse to AdapterInfo
            return AdapterInfo(
                adapter_id=operation_response.adapter_id,
                adapter_type=operation_response.adapter_type,
                status=operation_response.status,
                started_at=None,  # Adapter is unloaded
                messages_processed=0,
                error_count=0 if operation_response.success else 1,
                last_error=operation_response.error,
                tools=None,
            )
        except Exception as e:
            logger.error(f"Failed to unload adapter: {e}", exc_info=True)
            return AdapterInfo(
                adapter_id=adapter_id,
                adapter_type="unknown",
                status=AdapterStatus.ERROR,
                started_at=self._time_service.now(),
                messages_processed=0,
                error_count=1,
                last_error=str(e),
                tools=None,
            )

    async def list_adapters(self, handler_name: str = "default") -> List[AdapterInfo]:
        """List all loaded adapters"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["list_adapters"])

        if not service:
            logger.error(f"No runtime control service available for {handler_name}")
            return []

        try:
            return await service.list_adapters()
        except Exception as e:
            logger.error(f"Failed to list adapters: {e}", exc_info=True)
            return []

    async def pause_processing(self, handler_name: str = "default") -> bool:
        """Pause processor execution"""
        # Maps to pause_processing in the actual service
        if self._shutting_down:
            logger.warning("Cannot pause processor during shutdown")
            return False

        async with self._operation_lock:
            service = await self.get_service(handler_name=handler_name, required_capabilities=["pause_processing"])

            if not service:
                logger.error(f"No runtime control service available for {handler_name}")
                return False

            try:
                logger.info(f"Pausing processor requested by {handler_name}")
                self._commands_sent += 1
                response = await service.pause_processing()
                result = response.success

                if result:
                    logger.info("Processor paused successfully")
                else:
                    logger.error("Failed to pause processor")

                return result
            except Exception as e:
                logger.error(f"Exception pausing processor: {e}", exc_info=True)
                return False

    async def resume_processing(self, handler_name: str = "default") -> bool:
        """Resume processor execution from paused state"""
        # Maps to resume_processing in the actual service
        if self._shutting_down:
            logger.warning("Cannot resume processor during shutdown")
            return False

        async with self._operation_lock:
            service = await self.get_service(handler_name=handler_name, required_capabilities=["resume_processing"])

            if not service:
                logger.error(f"No runtime control service available for {handler_name}")
                return False

            try:
                logger.info(f"Resuming processor requested by {handler_name}")
                self._commands_sent += 1
                response = await service.resume_processing()
                result = response.success

                if result:
                    logger.info("Processor resumed successfully")
                else:
                    logger.error("Failed to resume processor")

                return result
            except Exception as e:
                logger.error(f"Exception resuming processor: {e}", exc_info=True)
                return False

    async def single_step(self, handler_name: str = "default") -> Optional[ProcessorControlResponse]:
        """Execute a single thought processing step"""
        # Maps to single_step returning ProcessorControlResponse
        if self._shutting_down:
            logger.warning("Cannot single-step during shutdown")
            return None

        async with self._operation_lock:
            service = await self.get_service(handler_name=handler_name, required_capabilities=["single_step"])

            if not service:
                logger.error(f"No runtime control service available for {handler_name}")
                return None

            try:
                logger.debug(f"Single step requested by {handler_name}")
                self._commands_sent += 1
                response = await service.single_step()

                if response.success:
                    logger.info("Single step completed")
                    return response
                else:
                    logger.debug("Single step failed or no thoughts to process")
                    return None
            except Exception as e:
                logger.error(f"Exception during single step: {e}", exc_info=True)
                return None

    async def get_adapter_info(self, adapter_id: str, handler_name: str = "default") -> AdapterInfo:
        """Get detailed information about a specific adapter"""
        service = await self.get_service(handler_name=handler_name, required_capabilities=["get_adapter_info"])

        if not service:
            logger.error(f"No runtime control service available for {handler_name}")
            return AdapterInfo(
                adapter_id=adapter_id,
                adapter_type="unknown",
                status=AdapterStatus.ERROR,
                started_at=self._time_service.now(),
                messages_processed=0,
                error_count=1,
                last_error="Service unavailable",
                tools=None,
            )

        try:
            result = await service.get_adapter_info(adapter_id)
            if result is None:
                # If service returns None, create an error AdapterInfo
                return AdapterInfo(
                    adapter_id=adapter_id,
                    adapter_type="unknown",
                    status=AdapterStatus.ERROR,
                    started_at=None,
                    messages_processed=0,
                    error_count=1,
                    last_error="Adapter not found",
                    tools=None,
                )
            return result
        except Exception as e:
            logger.error(f"Failed to get adapter info: {e}", exc_info=True)
            return AdapterInfo(
                adapter_id=adapter_id,
                adapter_type="unknown",
                status=AdapterStatus.ERROR,
                started_at=self._time_service.now(),
                messages_processed=0,
                error_count=1,
                last_error=str(e),
                tools=None,
            )

    async def is_healthy(self, handler_name: str = "default") -> bool:
        """Check if runtime control service is healthy"""
        service = await self.get_service(handler_name=handler_name)
        if not service:
            return False
        try:
            return await service.is_healthy() and not self._shutting_down
        except Exception as e:
            logger.error(f"Failed to check health: {e}")
            return False

    async def get_capabilities(self, handler_name: str = "default") -> List[str]:
        """Get runtime control service capabilities"""
        service = await self.get_service(handler_name=handler_name)
        if not service:
            return []
        try:
            capabilities = service.get_capabilities()
            # ServiceCapabilities is not awaitable, it's a synchronous method
            # Extract the actions list from the capabilities
            return capabilities.actions
        except Exception as e:
            logger.error(f"Failed to get capabilities: {e}")
            return []

    def _collect_metrics(self) -> Dict[str, float]:
        """Collect base metrics for the runtime control bus."""
        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        return {
            "runtime_control_commands": float(self._commands_sent),
            "runtime_control_state_queries": float(self._state_broadcasts),
            "runtime_control_emergency_stops": float(self._emergency_stops),
            "runtime_control_uptime_seconds": uptime_seconds,
        }

    def get_metrics(self) -> BusMetrics:
        """Get all runtime control bus metrics as typed BusMetrics schema."""
        # Calculate uptime
        uptime_seconds = 0.0
        if hasattr(self, "_time_service") and self._time_service:
            if hasattr(self, "_start_time") and self._start_time:
                uptime_seconds = (self._time_service.now() - self._start_time).total_seconds()

        # Count active operations
        active_operations_count = len(self._active_operations)

        # Map to BusMetrics schema
        return BusMetrics(
            messages_sent=self._commands_sent,  # Control commands sent
            messages_received=self._commands_sent,  # Synchronous
            messages_dropped=0,  # Not tracked yet
            average_latency_ms=0.0,  # Not tracked yet
            active_subscriptions=1,  # Single runtime control service
            queue_depth=self.get_queue_size(),
            errors_last_hour=0,  # Not tracked yet
            busiest_service=None,  # Single service
            additional_metrics={
                "runtime_control_commands": self._commands_sent,
                "runtime_control_state_queries": self._state_broadcasts,
                "runtime_control_emergency_stops": self._emergency_stops,
                "runtime_control_uptime_seconds": uptime_seconds,
                "runtime_control_active_operations": active_operations_count,
                "runtime_control_shutting_down": 1 if self._shutting_down else 0,
            },
        )

    async def _process_message(self, message: BusMessage) -> None:
        """Process runtime control messages - most should be synchronous"""
        logger.warning(f"Runtime control operations should generally be synchronous: {type(message)}")
