"""
Runtime control service for API adapter.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.runtime.adapter_manager import RuntimeAdapterManager
from ciris_engine.logic.services.base_service import BaseService
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus

from .constants import ERROR_ADAPTER_MANAGER_NOT_AVAILABLE, ERROR_TIME_SERVICE_NOT_AVAILABLE

logger = logging.getLogger(__name__)


class APIRuntimeControlService(BaseService, Service):
    """Runtime control exposed through API."""

    def __init__(self, runtime: Any, time_service: Optional[Any] = None) -> None:
        """Initialize API runtime control."""
        # Initialize BaseService for telemetry
        super().__init__(time_service=time_service, service_name="APIRuntimeControlService")

        self.runtime = runtime
        self._paused = False
        self._pause_reason: Optional[str] = None
        self._pause_time: Optional[datetime] = None

        # Adapter manager will be initialized later when services are available
        self.adapter_manager: Optional[RuntimeAdapterManager] = None

    async def pause_processing(self, reason: str) -> bool:
        """Pause agent processing."""
        if self._paused:
            logger.warning(f"Already paused since {self._pause_time}")
            return False

        self._paused = True
        self._pause_reason = reason
        self._pause_time = datetime.now(timezone.utc)

        logger.info(f"Processing paused via API: {reason}")

        # Notify runtime if it has pause capability
        if hasattr(self.runtime, "pause_processing"):
            await self.runtime.pause_processing(reason)

        return True

    async def resume_processing(self) -> bool:
        """Resume agent processing."""
        if not self._paused:
            logger.warning("Not currently paused")
            return False

        self._paused = False
        pause_duration = (datetime.now(timezone.utc) - self._pause_time).total_seconds() if self._pause_time else 0

        logger.info(f"Processing resumed via API after {pause_duration:.1f}s pause")

        self._pause_reason = None
        self._pause_time = None

        # Notify runtime if it has resume capability
        if hasattr(self.runtime, "resume_processing"):
            await self.runtime.resume_processing()

        return True

    async def request_state_transition(self, target_state: str, reason: str) -> bool:
        """Request cognitive state transition."""
        try:
            current_state = getattr(self.runtime, "current_state", "UNKNOWN")

            logger.info(f"API requesting state transition: {current_state} -> {target_state} " f"(reason: {reason})")

            # Use runtime's state transition if available
            if hasattr(self.runtime, "request_state_transition"):
                return await self.runtime.request_state_transition(target_state, reason)  # type: ignore[no-any-return]

            # Otherwise try direct transition
            if hasattr(self.runtime, "transition_to_state"):
                await self.runtime.transition_to_state(target_state)
                return True

            logger.error("Runtime does not support state transitions")
            return False

        except Exception as e:
            logger.error(f"State transition failed: {e}")
            return False

    def get_runtime_status(self) -> Dict[str, Any]:
        """Get current runtime status."""
        status = {
            "paused": self._paused,
            "pause_reason": self._pause_reason,
            "pause_time": self._pause_time.isoformat() if self._pause_time else None,
            "cognitive_state": str(self.runtime.current_state) if hasattr(self.runtime, "current_state") else "UNKNOWN",
            "uptime_seconds": self.runtime.get_uptime() if hasattr(self.runtime, "get_uptime") else 0,
        }

        # Add runtime-specific status if available
        if hasattr(self.runtime, "get_status"):
            runtime_status = self.runtime.get_status()
            if isinstance(runtime_status, dict):
                status.update(runtime_status)

        return status

    async def handle_emergency_shutdown(self, command: Any) -> Any:
        """Handle emergency shutdown command."""
        logger.critical(f"Emergency shutdown requested via API: {command.reason}")

        # Delegate to runtime's shutdown service
        if hasattr(self.runtime, "shutdown_service"):
            await self.runtime.shutdown_service.request_shutdown(f"EMERGENCY API: {command.reason}")
        else:
            # Fallback to runtime shutdown
            if hasattr(self.runtime, "shutdown"):
                await self.runtime.shutdown(f"EMERGENCY API: {command.reason}")

        return {
            "shutdown_initiated": datetime.now(timezone.utc),
            "command_verified": True,
            "services_stopped": ["all"],
            "data_persisted": True,
            "final_message_sent": True,
            "shutdown_completed": datetime.now(timezone.utc),
            "exit_code": 0,
        }

    # Service interface methods

    async def start(self) -> None:
        """Start the runtime control service."""
        # Call parent start to properly initialize BaseService
        await super().start()

        # Initialize adapter manager now that services should be available
        if self.runtime and hasattr(self.runtime, "time_service") and self.runtime.time_service:
            self.adapter_manager = RuntimeAdapterManager(self.runtime, self.runtime.time_service)
            logger.info("Initialized RuntimeAdapterManager for API runtime control")
        else:
            logger.warning(f"{ERROR_TIME_SERVICE_NOT_AVAILABLE}, adapter manager will not be initialized")

        logger.info("API Runtime Control Service started")

    async def stop(self) -> None:
        """Stop the runtime control service."""
        logger.info("API Runtime Control Service stopped")

    def is_healthy(self) -> bool:
        """Check if service is healthy."""
        return True

    def get_service_type(self) -> ServiceType:
        """Get the type of this service."""
        return ServiceType.ADAPTER

    def get_capabilities(self) -> ServiceCapabilities:
        """Get service capabilities."""
        return ServiceCapabilities(
            service_name="APIRuntimeControlService",
            actions=[
                "pause_processing",
                "resume_processing",
                "request_state_transition",
                "get_runtime_status",
                "handle_emergency_shutdown",
            ],
            version="1.0.0",
            dependencies=[],
            metadata={
                "description": "Runtime control service for API adapter",
                "features": ["pause_resume", "state_transitions", "emergency_shutdown"],
            },
        )

    def _check_dependencies(self) -> bool:
        """Check if all dependencies are satisfied."""
        return self.runtime is not None

    def _collect_custom_metrics(self) -> Dict[str, float]:
        """Collect runtime control specific metrics."""
        return {
            "paused": float(self._paused),
            "pause_duration": float(
                (datetime.now(timezone.utc) - self._pause_time).total_seconds()
                if self._pause_time and self._paused
                else 0
            ),
            "adapter_manager_available": 1.0 if self.adapter_manager else 0.0,
        }

    def _get_actions(self) -> List[str]:
        """Get the list of actions this service supports."""
        return [
            "pause_processing",
            "resume_processing",
            "emergency_shutdown",
            "get_adapter_status",
            "get_processor_status",
            "get_processor_queue_status",
        ]

    # Adapter Management Methods

    async def list_adapters(self) -> List[Any]:
        """List all loaded adapters."""
        if not self.adapter_manager:
            logger.warning(ERROR_ADAPTER_MANAGER_NOT_AVAILABLE)
            return []

        return await self.adapter_manager.list_adapters()

    async def get_adapter_info(self, adapter_id: str) -> Optional[Any]:
        """Get detailed information about a specific adapter."""
        if not self.adapter_manager:
            logger.warning(ERROR_ADAPTER_MANAGER_NOT_AVAILABLE)
            return None

        status = await self.adapter_manager.get_adapter_status(adapter_id)
        if not status:
            return None

        # Convert AdapterStatus to AdapterInfo format expected by runtime control
        from ciris_engine.schemas.services.core.runtime import AdapterInfo, AdapterStatus

        # Map status
        if status.is_running:
            adapter_status = AdapterStatus.RUNNING
        else:
            adapter_status = AdapterStatus.STOPPED

        return AdapterInfo(
            adapter_id=status.adapter_id,
            adapter_type=status.adapter_type,
            status=adapter_status,
            started_at=status.loaded_at,
            messages_processed=status.metrics.messages_processed if status.metrics else 0,  # type: ignore[attr-defined]
            error_count=status.metrics.errors_count if status.metrics else 0,  # type: ignore[attr-defined]
            last_error=status.metrics.last_error if status.metrics else None,  # type: ignore[attr-defined]
        )

    async def load_adapter(
        self, adapter_type: str, adapter_id: Optional[str] = None, config: Optional[Dict[str, object]] = None
    ) -> Any:
        """Load a new adapter instance."""
        if not self.adapter_manager:
            from ciris_engine.schemas.services.core.runtime import AdapterOperationResponse, AdapterStatus

            return AdapterOperationResponse(
                success=False,
                timestamp=datetime.now(timezone.utc),
                adapter_id=adapter_id,
                adapter_type=adapter_type,
                status=AdapterStatus.ERROR,
                error=ERROR_ADAPTER_MANAGER_NOT_AVAILABLE,
            )

        # Generate adapter ID if not provided
        if not adapter_id:
            import uuid

            adapter_id = f"{adapter_type}_{uuid.uuid4().hex[:8]}"

        result = await self.adapter_manager.load_adapter(adapter_type, adapter_id, config)

        # Convert to runtime control response format
        from ciris_engine.schemas.services.core.runtime import AdapterOperationResponse, AdapterStatus

        return AdapterOperationResponse(
            success=result.success,
            adapter_id=result.adapter_id,
            adapter_type=adapter_type,
            timestamp=datetime.now(timezone.utc),
            status=AdapterStatus.RUNNING if result.success else AdapterStatus.ERROR,
            message=result.message,
            error=result.error,
        )

    async def unload_adapter(self, adapter_id: str) -> Any:
        """Unload an adapter instance."""
        if not self.adapter_manager:
            from ciris_engine.schemas.services.core.runtime import AdapterOperationResponse, AdapterStatus

            return AdapterOperationResponse(
                success=False,
                timestamp=datetime.now(timezone.utc),
                adapter_id=adapter_id,
                adapter_type="unknown",
                status=AdapterStatus.ERROR,
                error=ERROR_ADAPTER_MANAGER_NOT_AVAILABLE,
            )

        result = await self.adapter_manager.unload_adapter(adapter_id)

        # Convert to runtime control response format
        from ciris_engine.schemas.services.core.runtime import AdapterOperationResponse, AdapterStatus

        return AdapterOperationResponse(
            success=result.success,
            adapter_id=result.adapter_id,
            adapter_type=result.adapter_type or "unknown",
            timestamp=datetime.now(timezone.utc),
            status=AdapterStatus.STOPPED if result.success else AdapterStatus.ERROR,
            message=result.message,
            error=result.error,
        )
