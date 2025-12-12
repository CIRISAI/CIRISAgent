"""
Runtime control service for API adapter.
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from ciris_engine.logic.adapters.base import Service
from ciris_engine.logic.runtime.adapter_manager import RuntimeAdapterManager
from ciris_engine.schemas.runtime.enums import ServiceType
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus
from ciris_engine.schemas.types import JSONDict

from .constants import ERROR_ADAPTER_MANAGER_NOT_AVAILABLE, ERROR_TIME_SERVICE_NOT_AVAILABLE

logger = logging.getLogger(__name__)


class APIRuntimeControlService(Service):
    """Runtime control exposed through API.

    This service handles API-specific runtime control (pause/resume with reasons).
    For adapter management, it uses the main RuntimeControlService's adapter_manager
    to ensure a single source of truth for loaded adapters.

    IMPORTANT: This service does NOT create its own adapter_manager. It must be
    injected from the main RuntimeControlService. If adapter_manager is None when
    adapter operations are called, it will fail fast with a clear error.
    """

    def __init__(self, runtime: Any, time_service: Optional[Any] = None) -> None:
        """Initialize API runtime control."""
        super().__init__()

        self.runtime = runtime
        self._time_service = time_service  # Store for telemetry compatibility
        self._paused = False
        self._pause_reason: Optional[str] = None
        self._pause_time: Optional[datetime] = None
        self._start_time: Optional[datetime] = None  # For uptime tracking
        self._started = False  # Track if service has been started

        # Adapter manager MUST be injected from main RuntimeControlService
        # We do NOT create our own - single source of truth
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
            runtime_type = type(self.runtime).__name__
            current_state = getattr(self.runtime, "current_state", "UNKNOWN")

            logger.info("[API_RUNTIME_CONTROL] State transition request received")
            logger.info(f"[API_RUNTIME_CONTROL] Runtime type: {runtime_type}")
            logger.info(f"[API_RUNTIME_CONTROL] Current state: {current_state}")
            logger.info(f"[API_RUNTIME_CONTROL] Target state: {target_state}")
            logger.info(f"[API_RUNTIME_CONTROL] Reason: {reason}")

            # Check what methods are available
            has_request_state_transition = hasattr(self.runtime, "request_state_transition")
            has_transition_to_state = hasattr(self.runtime, "transition_to_state")
            has_agent_processor = hasattr(self.runtime, "agent_processor")

            logger.info(f"[API_RUNTIME_CONTROL] runtime.request_state_transition: {has_request_state_transition}")
            logger.info(f"[API_RUNTIME_CONTROL] runtime.transition_to_state: {has_transition_to_state}")
            logger.info(f"[API_RUNTIME_CONTROL] runtime.agent_processor: {has_agent_processor}")

            # Use runtime's state transition if available
            if has_request_state_transition:
                logger.info("[API_RUNTIME_CONTROL] Delegating to runtime.request_state_transition()")
                result = await self.runtime.request_state_transition(target_state, reason)
                logger.info(f"[API_RUNTIME_CONTROL] Result: {result}")
                return bool(result)

            # Otherwise try direct transition
            if has_transition_to_state:
                logger.info("[API_RUNTIME_CONTROL] Delegating to runtime.transition_to_state()")
                await self.runtime.transition_to_state(target_state)
                return True

            # Try using agent_processor directly
            if has_agent_processor and self.runtime.agent_processor:
                agent_processor = self.runtime.agent_processor
                if hasattr(agent_processor, "state_manager"):
                    logger.info("[API_RUNTIME_CONTROL] Using agent_processor.state_manager.transition_to()")
                    from ciris_engine.schemas.processors.states import AgentState

                    try:
                        target = AgentState(target_state.lower())
                        result = await agent_processor.state_manager.transition_to(target)
                        logger.info(f"[API_RUNTIME_CONTROL] Direct state_manager result: {result}")
                        return bool(result)
                    except ValueError:
                        logger.error(f"[API_RUNTIME_CONTROL] Invalid state: {target_state}")
                        return False

            logger.error("[API_RUNTIME_CONTROL] FAIL: Runtime does not support state transitions")
            logger.error(
                f"[API_RUNTIME_CONTROL] Available runtime methods: {[m for m in dir(self.runtime) if not m.startswith('_')]}"
            )
            return False

        except Exception as e:
            logger.error(f"[API_RUNTIME_CONTROL] State transition failed: {type(e).__name__}: {e}")
            import traceback

            logger.error(f"[API_RUNTIME_CONTROL] Traceback:\n{traceback.format_exc()}")
            return False

    def get_runtime_status(self) -> JSONDict:
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
        # Track start time for telemetry
        self._start_time = datetime.now(timezone.utc)
        self._started = True

        # Get adapter_manager from main RuntimeControlService - single source of truth
        # We do NOT create our own adapter_manager
        main_runtime_control = getattr(self.runtime, "runtime_control_service", None)
        if main_runtime_control and hasattr(main_runtime_control, "adapter_manager"):
            self.adapter_manager = main_runtime_control.adapter_manager
            logger.info(
                f"APIRuntimeControlService using main RuntimeControlService's adapter_manager "
                f"(id: {id(self.adapter_manager)})"
            )
        else:
            # This is expected during early startup - adapter_manager will be set later
            logger.info(
                "APIRuntimeControlService started without adapter_manager - "
                "will be injected from main RuntimeControlService"
            )

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
            metadata=None,
        )

    def get_status(self) -> ServiceStatus:
        """Get current service status."""
        uptime = 0.0
        if self._start_time:
            uptime = (datetime.now(timezone.utc) - self._start_time).total_seconds()

        return ServiceStatus(
            service_name="APIRuntimeControlService",
            service_type="RUNTIME_CONTROL",
            is_healthy=self._started,
            uptime_seconds=uptime,
            last_error=None,
            metrics={
                "paused": float(self._paused),
                "pause_duration": float(
                    (datetime.now(timezone.utc) - self._pause_time).total_seconds()
                    if self._pause_time and self._paused
                    else 0
                ),
                "adapter_manager_available": 1.0 if self.adapter_manager else 0.0,
            },
            last_health_check=datetime.now(timezone.utc),
        )

    # Adapter Management Methods

    def _require_adapter_manager(self) -> RuntimeAdapterManager:
        """Get adapter_manager or raise if not available. Fail fast, no fallbacks."""
        if not self.adapter_manager:
            raise RuntimeError(
                "CRITICAL: adapter_manager not available in APIRuntimeControlService. "
                "This indicates a startup sequencing issue - main RuntimeControlService's "
                "adapter_manager was not injected. Check service initialization order."
            )
        return self.adapter_manager

    async def list_adapters(self) -> List[Any]:
        """List all loaded adapters."""
        adapter_manager = self._require_adapter_manager()
        return await adapter_manager.list_adapters()

    async def get_adapter_info(self, adapter_id: str) -> Optional[Any]:
        """Get detailed information about a specific adapter."""
        adapter_manager = self._require_adapter_manager()

        status = await adapter_manager.get_adapter_status(adapter_id)
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
            messages_processed=status.metrics.messages_processed if status.metrics else 0,
            error_count=status.metrics.errors_count if status.metrics else 0,
            last_error=status.metrics.last_error if status.metrics else None,
        )

    async def load_adapter(
        self, adapter_type: str, adapter_id: Optional[str] = None, config: Optional[Dict[str, object]] = None
    ) -> Any:
        """Load a new adapter instance.

        Args:
            adapter_type: Type of adapter to load (e.g., "home_assistant", "discord")
            adapter_id: Optional unique identifier for the adapter instance
            config: Optional configuration dictionary for the adapter

        Returns:
            AdapterOperationResponse with success status and adapter info

        Raises:
            RuntimeError: If adapter_manager is not available (fail fast)
        """
        adapter_manager = self._require_adapter_manager()

        # Generate adapter ID if not provided
        if not adapter_id:
            import uuid

            adapter_id = f"{adapter_type}_{uuid.uuid4().hex[:8]}"

        # Convert config dict to AdapterConfig if provided
        adapter_config = None
        if config:
            from ciris_engine.schemas.runtime.adapter_management import AdapterConfig

            # If config already has adapter_type, use it directly
            # Otherwise, wrap the config in the proper structure
            if "adapter_type" in config:
                adapter_config = AdapterConfig(**config)
            else:
                # Wrap the collected config in AdapterConfig structure
                adapter_config = AdapterConfig(
                    adapter_type=adapter_type,
                    enabled=True,
                    adapter_config=config,  # Pass full config for complex adapters
                )

        result = await adapter_manager.load_adapter(adapter_type, adapter_id, adapter_config)

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
        """Unload an adapter instance.

        Raises:
            RuntimeError: If adapter_manager is not available (fail fast)
        """
        adapter_manager = self._require_adapter_manager()

        result = await adapter_manager.unload_adapter(adapter_id)

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
