"""
Service Property Accessor Mixin for CIRISRuntime.

Provides property accessors that delegate to the ServiceInitializer.
This keeps the main runtime class cleaner and separates service access patterns.
"""

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from ciris_engine.logic.registries.base import ServiceRegistry
    from ciris_engine.protocols.infrastructure.base import BusManagerProtocol
    from ciris_engine.protocols.services.adaptation.self_observation import SelfObservationServiceProtocol
    from ciris_engine.protocols.services.governance.filter import AdaptiveFilterServiceProtocol
    from ciris_engine.protocols.services.governance.visibility import VisibilityServiceProtocol
    from ciris_engine.protocols.services.graph.audit import AuditServiceProtocol
    from ciris_engine.protocols.services.graph.config import GraphConfigServiceProtocol
    from ciris_engine.protocols.services.graph.incident_management import IncidentManagementServiceProtocol
    from ciris_engine.protocols.services.graph.memory import MemoryServiceProtocol
    from ciris_engine.protocols.services.graph.telemetry import TelemetryServiceProtocol
    from ciris_engine.protocols.services.graph.tsdb_consolidation import TSDBConsolidationServiceProtocol
    from ciris_engine.protocols.services.infrastructure.authentication import AuthenticationServiceProtocol
    from ciris_engine.protocols.services.infrastructure.database_maintenance import DatabaseMaintenanceServiceProtocol
    from ciris_engine.protocols.services.infrastructure.resource_monitor import ResourceMonitorServiceProtocol
    from ciris_engine.protocols.services.lifecycle.initialization import InitializationServiceProtocol
    from ciris_engine.protocols.services.lifecycle.scheduler import TaskSchedulerServiceProtocol
    from ciris_engine.protocols.services.lifecycle.shutdown import ShutdownServiceProtocol
    from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
    from ciris_engine.protocols.services.runtime.llm import LLMServiceProtocol
    from ciris_engine.protocols.services.runtime.runtime_control import RuntimeControlServiceProtocol
    from ciris_engine.protocols.services.runtime.secrets import SecretsServiceProtocol
    from ciris_engine.protocols.services.runtime.tool import ToolServiceProtocol


class ServicePropertyMixin:
    """
    Mixin class providing property accessors to services via service_initializer.

    This mixin assumes the class has a `service_initializer` attribute that provides
    access to all core services. The properties delegate to service_initializer,
    keeping the main runtime class focused on orchestration logic.
    """

    @property
    def service_registry(self) -> Optional["ServiceRegistry"]:
        """Access to the service registry for multi-provider services."""
        return self.service_initializer.service_registry if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def bus_manager(self) -> Optional["BusManagerProtocol"]:
        """Access to the bus manager for message routing."""
        return self.service_initializer.bus_manager if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def memory_service(self) -> Optional["MemoryServiceProtocol"]:
        """Access to memory service for graph operations."""
        return self.service_initializer.memory_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def resource_monitor(self) -> Optional["ResourceMonitorServiceProtocol"]:
        """Access to resource monitor service - CRITICAL for mission-critical systems."""
        return self.service_initializer.resource_monitor_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def secrets_service(self) -> Optional["SecretsServiceProtocol"]:
        """Access to secrets service for credential management."""
        return self.service_initializer.secrets_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def wa_auth_system(self) -> Optional[Any]:
        """WiseAuthorityService - complex system without unified protocol."""
        return self.service_initializer.wa_auth_system if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def telemetry_service(self) -> Optional["TelemetryServiceProtocol"]:
        """Access to telemetry service for metrics and monitoring."""
        return self.service_initializer.telemetry_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def llm_service(self) -> Optional["LLMServiceProtocol"]:
        """Access to LLM service for language model operations."""
        return self.service_initializer.llm_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def audit_service(self) -> Optional["AuditServiceProtocol"]:
        """Access to audit service for logging and compliance."""
        return self.service_initializer.audit_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def adaptive_filter_service(self) -> Optional["AdaptiveFilterServiceProtocol"]:
        """Access to adaptive filter service for content filtering."""
        return self.service_initializer.adaptive_filter_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def config_manager(self) -> Optional["GraphConfigServiceProtocol"]:
        """Return GraphConfigService for RuntimeControlService compatibility."""
        return self.service_initializer.config_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def secrets_tool_service(self) -> Optional["ToolServiceProtocol"]:
        """Access to secrets tool service for secure operations."""
        return self.service_initializer.secrets_tool_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def time_service(self) -> Optional["TimeServiceProtocol"]:
        """Access to time service for consistent timestamps."""
        return self.service_initializer.time_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def config_service(self) -> Optional["GraphConfigServiceProtocol"]:
        """Access to configuration service."""
        return self.service_initializer.config_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def task_scheduler(self) -> Optional["TaskSchedulerServiceProtocol"]:
        """Access to task scheduler service."""
        return self.service_initializer.task_scheduler_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def authentication_service(self) -> Optional["AuthenticationServiceProtocol"]:
        """Access to authentication service."""
        return self.service_initializer.auth_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def incident_management_service(self) -> Optional["IncidentManagementServiceProtocol"]:
        """Access to incident management service."""
        return self.service_initializer.incident_management_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def runtime_control_service(self) -> Optional["RuntimeControlServiceProtocol"]:
        """Access to runtime control service."""
        return self.service_initializer.runtime_control_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def maintenance_service(self) -> Optional["DatabaseMaintenanceServiceProtocol"]:
        """Access to database maintenance service."""
        return self.service_initializer.maintenance_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def database_maintenance_service(self) -> Optional["DatabaseMaintenanceServiceProtocol"]:
        """Alias for maintenance_service - used by API adapter service injection.

        The API adapter's service configuration expects 'database_maintenance_service'
        while the internal runtime property is named 'maintenance_service'. This alias
        maintains backward compatibility and ensures all 22 core services are accessible.
        """
        return self.maintenance_service

    @property
    def shutdown_service(self) -> Optional["ShutdownServiceProtocol"]:
        """Access to shutdown service."""
        return self.service_initializer.shutdown_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def initialization_service(self) -> Optional["InitializationServiceProtocol"]:
        """Access to initialization service."""
        return self.service_initializer.initialization_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def tsdb_consolidation_service(self) -> Optional["TSDBConsolidationServiceProtocol"]:
        """Access to TSDB consolidation service."""
        return self.service_initializer.tsdb_consolidation_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def self_observation_service(self) -> Optional["SelfObservationServiceProtocol"]:
        """Access to self observation service."""
        return self.service_initializer.self_observation_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def visibility_service(self) -> Optional["VisibilityServiceProtocol"]:
        """Access to visibility service."""
        return self.service_initializer.visibility_service if self.service_initializer else None  # type: ignore[attr-defined]

    @property
    def consent_service(self) -> Optional[Any]:
        """Access to consent service - manages user consent, data retention, and DSAR automation."""
        return self.service_initializer.consent_service if self.service_initializer else None  # type: ignore[attr-defined]
