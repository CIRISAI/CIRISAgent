"""
Core service management schemas.

Critical schemas for service container, status, and capabilities.
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from ciris_engine.schemas.services.metadata import ServiceMetadata
from ciris_engine.schemas.types import JSONDict

if TYPE_CHECKING:
    pass


class ServiceCapabilities(BaseModel):
    """Capabilities exposed by a service."""

    service_name: str = Field(..., description="Name of the service")
    actions: List[str] = Field(..., description="Actions this service can perform")
    version: str = Field(..., description="Service version")
    dependencies: List[str] = Field(default_factory=list, description="Required dependencies")
    metadata: Optional[ServiceMetadata] = Field(None, description="Additional capability metadata")


class ServiceStatus(BaseModel):
    """Status information for any service."""

    service_name: str = Field(..., description="Name of the service")
    service_type: str = Field(..., description="Type of service")
    is_healthy: bool = Field(..., description="Whether service is healthy")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    last_error: Optional[str] = Field(None, description="Last error if any")
    metrics: Dict[str, float] = Field(default_factory=dict, description="Service-specific metrics")
    custom_metrics: Optional[Dict[str, float]] = Field(None, description="Additional custom metrics")
    last_health_check: Optional[datetime] = Field(None, description="Last health check time")


class ServiceContainer(BaseModel):
    """Type-safe container for all CIRIS services."""

    # Core services - using Any to avoid circular imports
    llm_service: Optional[Any] = Field(None, description="LLM service for AI operations")
    memory_service: Optional[Any] = Field(None, description="Memory service for knowledge storage")
    audit_services: List[Any] = Field(default_factory=list, description="Audit services for compliance")
    tool_services: List[Any] = Field(default_factory=list, description="Tool services for capabilities")
    wa_services: List[Any] = Field(default_factory=list, description="Wise Authority services")

    # Security services
    secrets_service: Optional[Any] = Field(None, description="Secrets management service")
    wa_auth_system: Optional[Any] = Field(None, description="WA authentication system")

    # Infrastructure services
    telemetry_service: Optional[Any] = Field(None, description="Telemetry and monitoring")
    adaptive_filter_service: Optional[Any] = Field(None, description="Adaptive content filtering")
    agent_config_service: Optional[Any] = Field(None, description="Agent configuration management")
    transaction_orchestrator: Optional[Any] = Field(None, description="Transaction coordination")
    secrets_tool_service: Optional[Any] = Field(None, description="Secrets tool capabilities")
    maintenance_service: Optional[Any] = Field(None, description="System maintenance service")

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get_service_by_type(self, service_type: str) -> Optional[List[Any]]:
        """Get services by type name."""
        service_map = {
            "llm": [self.llm_service] if self.llm_service else [],
            "memory": [self.memory_service] if self.memory_service else [],
            "audit": self.audit_services,
            "tool": self.tool_services,
            "wise_authority": self.wa_services,
            "secrets": [self.secrets_service] if self.secrets_service else [],
            "wa_auth": [self.wa_auth_system] if self.wa_auth_system else [],
            "telemetry": [self.telemetry_service] if self.telemetry_service else [],
            "adaptive_filter": [self.adaptive_filter_service] if self.adaptive_filter_service else [],
            "agent_config": [self.agent_config_service] if self.agent_config_service else [],
            "transaction": [self.transaction_orchestrator] if self.transaction_orchestrator else [],
            "secrets_tool": [self.secrets_tool_service] if self.secrets_tool_service else [],
            "maintenance": [self.maintenance_service] if self.maintenance_service else [],
        }
        result = service_map.get(service_type, [])
        return result if isinstance(result, list) else []

    @property
    def audit_service(self) -> Optional[Any]:
        """Get primary audit service for backward compatibility."""
        return self.audit_services[0] if self.audit_services else None


class RuntimeMetrics(BaseModel):
    """Runtime metrics for monitoring."""

    uptime_seconds: float = Field(..., description="Total uptime")
    tasks_processed: int = Field(..., description="Total tasks processed")
    thoughts_generated: int = Field(..., description="Total thoughts generated")
    decisions_made: int = Field(..., description="Total decisions made")
    actions_performed: int = Field(..., description="Total actions performed")

    # Resource usage
    memory_usage_mb: float = Field(..., description="Memory usage in MB")
    cpu_usage_percent: float = Field(..., description="CPU usage percentage")

    # Error tracking
    error_count: int = Field(0, description="Total errors encountered")
    last_error: Optional[str] = Field(None, description="Last error message")

    # Performance
    average_task_duration_ms: float = Field(0.0, description="Average task duration")
    average_thought_duration_ms: float = Field(0.0, description="Average thought duration")


class BusMessage(BaseModel):
    """Message sent through the service bus."""

    id: str = Field(..., description="Unique message ID")
    from_service: str = Field(..., description="Sending service")
    to_service: str = Field(..., description="Target service")
    action: str = Field(..., description="Action to perform")
    payload: JSONDict = Field(..., description="Message payload")
    correlation_id: str = Field(..., description="Correlation ID for tracing")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reply_to: Optional[str] = Field(None, description="Where to send reply")


class ServiceRegistration(BaseModel):
    """Service registration information."""

    service_name: str = Field(..., description="Unique service name")
    service_type: str = Field(..., description="Type of service")
    capabilities: ServiceCapabilities = Field(..., description="Service capabilities")
    dependencies: List[str] = Field(default_factory=list, description="Required services")
    status: ServiceStatus = Field(..., description="Current status")
    registered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Health check
    health_check_endpoint: Optional[str] = Field(None, description="Health check endpoint")
    last_health_check: Optional[datetime] = Field(None, description="Last health check time")


# Re-export schemas from submodules

__all__ = [
    # Core service schemas
    "ServiceCapabilities",
    "ServiceStatus",
    "ServiceContainer",
    "RuntimeMetrics",
    "BusMessage",
    "ServiceRegistration",
    # Re-exported from submodules - will be populated by star imports
]
