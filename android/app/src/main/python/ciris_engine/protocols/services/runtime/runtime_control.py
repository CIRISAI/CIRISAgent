"""Runtime Control Service Protocol - Unified control plane for CIRIS runtime operations."""

from abc import abstractmethod
from typing import TYPE_CHECKING, Dict, List, Optional, Protocol

from ciris_engine.schemas.services.core.runtime import (
    AdapterInfo,
    AdapterOperationResponse,
    ConfigBackup,
    ConfigOperationResponse,
    ConfigSnapshot,
    ConfigValidationResponse,
    ProcessorControlResponse,
    ProcessorQueueStatus,
    RuntimeEvent,
    RuntimeStateSnapshot,
    RuntimeStatusResponse,
    ServiceHealthStatus,
    ServiceSelectionExplanation,
)
from ciris_engine.schemas.services.shutdown import EmergencyShutdownStatus, WASignedCommand

from ...runtime.base import ServiceProtocol

if TYPE_CHECKING:
    from ciris_engine.schemas.services.runtime_control import (
        CircuitBreakerResetResponse,
        CircuitBreakerStatus,
        ServicePriorityUpdateResponse,
    )


class RuntimeControlServiceProtocol(ServiceProtocol, Protocol):
    """
    Protocol for runtime control service.

    This service provides centralized control over the CIRIS runtime,
    including processor management, adapter lifecycle, configuration,
    and emergency operations. It's an adapter-provided service (not core).
    """

    # ========== Processor Control ==========

    @abstractmethod
    async def pause_processing(self) -> ProcessorControlResponse:
        """Pause the processor."""
        ...

    @abstractmethod
    async def resume_processing(self) -> ProcessorControlResponse:
        """Resume the processor."""
        ...

    @abstractmethod
    async def single_step(self) -> ProcessorControlResponse:
        """Execute one processing step for debugging."""
        ...

    @abstractmethod
    async def get_processor_queue_status(self) -> ProcessorQueueStatus:
        """Get detailed processor queue metrics."""
        ...

    @abstractmethod
    async def shutdown_runtime(self, reason: str) -> ProcessorControlResponse:
        """Initiate graceful runtime shutdown."""
        ...

    # ========== Adapter Management ==========

    @abstractmethod
    async def load_adapter(
        self,
        adapter_type: str,
        adapter_id: Optional[str] = None,
        config: Optional[Dict[str, object]] = None,
        auto_start: bool = True,
    ) -> AdapterOperationResponse:
        """Dynamically load a new adapter."""
        ...

    @abstractmethod
    async def unload_adapter(self, adapter_id: str, force: bool = False) -> AdapterOperationResponse:
        """Unload an adapter from runtime."""
        ...

    @abstractmethod
    async def list_adapters(self) -> List[AdapterInfo]:
        """List all loaded adapters."""
        ...

    @abstractmethod
    async def get_adapter_info(self, adapter_id: str) -> Optional[AdapterInfo]:
        """Get detailed information about a specific adapter."""
        ...

    # ========== Configuration Management ==========

    @abstractmethod
    async def get_config(self, path: Optional[str] = None, include_sensitive: bool = False) -> ConfigSnapshot:
        """Get configuration values."""
        ...

    @abstractmethod
    async def update_config(
        self,
        path: str,
        value: object,
        scope: str = "runtime",
        validation_level: str = "full",
        reason: Optional[str] = None,
    ) -> ConfigOperationResponse:
        """Update configuration value."""
        ...

    @abstractmethod
    async def validate_config(
        self, config_data: Dict[str, object], config_path: Optional[str] = None
    ) -> ConfigValidationResponse:
        """Validate configuration without applying."""
        ...

    @abstractmethod
    async def backup_config(self, backup_name: Optional[str] = None) -> ConfigOperationResponse:
        """Create configuration backup."""
        ...

    @abstractmethod
    async def restore_config(self, backup_name: str) -> ConfigOperationResponse:
        """Restore configuration from backup."""
        ...

    @abstractmethod
    async def list_config_backups(self) -> List[ConfigBackup]:
        """List available configuration backups."""
        ...

    # ========== Runtime Status ==========

    @abstractmethod
    async def get_runtime_status(self) -> RuntimeStatusResponse:
        """Get current runtime status summary."""
        ...

    @abstractmethod
    async def get_runtime_snapshot(self) -> RuntimeStateSnapshot:
        """Get complete runtime state snapshot."""
        ...

    @abstractmethod
    async def get_service_health_status(self) -> ServiceHealthStatus:
        """Get comprehensive service health report."""
        ...

    @abstractmethod
    def get_events_history(self, limit: int = 100) -> List[RuntimeEvent]:
        """Get recent runtime events for audit/debugging."""
        ...

    # ========== Service Management ==========

    @abstractmethod
    async def update_service_priority(
        self,
        provider_name: str,
        new_priority: str,
        new_priority_group: Optional[int] = None,
        new_strategy: Optional[str] = None,
    ) -> "ServicePriorityUpdateResponse":
        """Update service provider priority and selection strategy."""
        ...

    @abstractmethod
    async def reset_circuit_breakers(self, service_type: Optional[str] = None) -> "CircuitBreakerResetResponse":
        """Reset circuit breakers for services."""
        ...

    @abstractmethod
    async def get_circuit_breaker_status(self, service_type: Optional[str] = None) -> Dict[str, "CircuitBreakerStatus"]:
        """Get circuit breaker status for services."""
        ...

    @abstractmethod
    async def get_service_selection_explanation(self) -> ServiceSelectionExplanation:
        """Get explanation of service selection logic."""
        ...

    # ========== Emergency Operations ==========

    @abstractmethod
    async def handle_emergency_shutdown(self, command: WASignedCommand) -> EmergencyShutdownStatus:
        """Process WA-authorized emergency shutdown."""
        ...
