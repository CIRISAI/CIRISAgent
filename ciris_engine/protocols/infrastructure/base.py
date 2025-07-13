"""
Infrastructure protocols for the CIRIS Trinity Architecture.

These protocols define contracts for core runtime and infrastructure components.
These are the foundational systems that enable everything else to work.
"""
from typing import List, Any, TYPE_CHECKING
from abc import abstractmethod

from ciris_engine.protocols.runtime.base import ServiceProtocol

from ciris_engine.schemas.infrastructure.base import (
    RuntimeStats, ComponentHealthStatus, ServiceDependencies,
    BusMetrics, IdentityBaseline, IdentityVarianceMetric, ConfigurationFeedback,
    ConfigurationPattern, ConfigurationUpdate, ActiveAdapter,
    CheckpointInfo, ServiceRegistration
)

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry

# ============================================================================
# RUNTIME INFRASTRUCTURE
# ============================================================================

class RuntimeProtocol(ServiceProtocol):
    """Protocol for the main CIRIS runtime engine."""

    @abstractmethod
    async def run(self) -> None:
        """Run the main agent loop."""
        ...

    @abstractmethod
    async def pause(self) -> None:
        """Pause agent processing."""
        ...

    @abstractmethod
    async def resume(self) -> None:
        """Resume agent processing."""
        ...

    @abstractmethod
    async def shutdown(self, reason: str) -> None:
        """Shutdown the runtime gracefully."""
        ...

    @abstractmethod
    def get_runtime_stats(self) -> RuntimeStats:
        """Get runtime statistics."""
        ...

    @abstractmethod
    async def health_check(self) -> ComponentHealthStatus:
        """Check health of all components."""
        ...

class ServiceInitializerProtocol(ServiceProtocol):
    """Protocol for service initialization and dependency management."""

    @abstractmethod
    async def initialize_services(self) -> None:
        """Initialize all services in correct order."""
        ...

    @abstractmethod
    async def validate_dependencies(self) -> ServiceDependencies:
        """Validate all service dependencies are met."""
        ...

    @abstractmethod
    async def bootstrap(self) -> None:
        """Bootstrap minimal services for startup."""
        ...

    @abstractmethod
    def get_initialization_order(self) -> List[str]:
        """Get service initialization order."""
        ...

    @abstractmethod
    async def teardown_services(self) -> None:
        """Teardown services in reverse order."""
        ...

class BusManagerProtocol(ServiceProtocol):
    """Protocol for message bus management."""

    @abstractmethod
    async def send(self, service: str, action: str, payload: Any) -> None:
        """Send a message to a service."""
        ...

    @abstractmethod
    async def request(self, service: str, action: str, payload: Any) -> Any:
        """Send request and wait for response."""
        ...

    @abstractmethod
    async def subscribe(self, pattern: str, handler: Any) -> str:
        """Subscribe to message pattern."""
        ...

    @abstractmethod
    async def unsubscribe(self, _: str) -> None:
        """Unsubscribe from messages."""
        ...

    @abstractmethod
    def get_bus_metrics(self) -> BusMetrics:
        """Get message bus metrics."""
        ...

# ============================================================================
# PROCESSING INFRASTRUCTURE
# ============================================================================

# NOTE: Processor protocols moved to protocols/processors/
# - AgentProcessorProtocol: Main coordinator for all states
# - ProcessorProtocol: Base for state processors

class IdentityVarianceMonitorProtocol(ServiceProtocol):
    """Protocol for monitoring identity drift."""

    @abstractmethod
    async def measure_drift(self) -> float:
        """Measure current identity drift percentage."""
        ...

    @abstractmethod
    async def get_baseline(self) -> IdentityBaseline:
        """Get identity baseline."""
        ...

    @abstractmethod
    async def update_baseline(self, reason: str) -> None:
        """Update identity baseline."""
        ...

    @abstractmethod
    async def alert_on_variance(self, threshold: float) -> None:
        """Alert when variance exceeds threshold."""
        ...

    @abstractmethod
    def get_variance_history(self) -> List[IdentityVarianceMetric]:
        """Get history of identity variance."""
        ...

class ConfigurationFeedbackLoopProtocol(ServiceProtocol):
    """Protocol for configuration feedback and learning."""

    @abstractmethod
    async def collect_feedback(self) -> List[ConfigurationFeedback]:
        """Collect configuration feedback."""
        ...

    @abstractmethod
    async def analyze_patterns(self) -> List[ConfigurationPattern]:
        """Analyze configuration patterns."""
        ...

    @abstractmethod
    async def propose_updates(self) -> List[ConfigurationUpdate]:
        """Propose configuration updates."""
        ...

    @abstractmethod
    async def apply_learning(self, _: str) -> bool:
        """Apply learned configuration."""
        ...

# ============================================================================
# ADAPTER INFRASTRUCTURE
# ============================================================================

class AdapterManagerProtocol(ServiceProtocol):
    """Protocol for managing platform adapters."""

    @abstractmethod
    async def register_adapter(self, adapter_type: str, adapter: Any) -> None:
        """Register a platform adapter."""
        ...

    @abstractmethod
    async def start_adapter(self, adapter_type: str) -> None:
        """Start a specific adapter."""
        ...

    @abstractmethod
    async def stop_adapter(self, adapter_type: str) -> None:
        """Stop a specific adapter."""
        ...

    @abstractmethod
    def get_active_adapters(self) -> List[ActiveAdapter]:
        """Get all active adapters."""
        ...

    @abstractmethod
    async def route_message(self, message: Any) -> None:
        """Route message to appropriate adapter."""
        ...

# ============================================================================
# PERSISTENCE INFRASTRUCTURE
# ============================================================================

class PersistenceManagerProtocol(ServiceProtocol):
    """Protocol for managing data persistence."""

    @abstractmethod
    async def save_checkpoint(self, _: str) -> None:
        """Save system checkpoint."""
        ...

    @abstractmethod
    async def restore_checkpoint(self, _: str) -> None:
        """Restore from checkpoint."""
        ...

    @abstractmethod
    async def get_checkpoints(self) -> List[CheckpointInfo]:
        """List available checkpoints."""
        ...

    @abstractmethod
    async def cleanup_old_data(self, retention_days: int) -> int:
        """Clean up old data."""
        ...

# ============================================================================
# REGISTRY INFRASTRUCTURE
# ============================================================================

class ServiceRegistryProtocol(ServiceProtocol):
    """Protocol for service discovery and registration."""

    @abstractmethod
    async def register_service(self, service_name: str, _: Any) -> None:
        """Register a service."""
        ...

    @abstractmethod
    async def unregister_service(self, service_name: str) -> None:
        """Unregister a service."""
        ...

    @abstractmethod
    def get_service(self, service_name: str) -> ServiceRegistration:
        """Get service information."""
        ...

    @abstractmethod
    def list_services(self) -> "ServiceRegistry":
        """List all registered services."""
        ...

    @abstractmethod
    async def health_check_service(self, service_name: str) -> bool:
        """Health check a specific service."""
        ...
