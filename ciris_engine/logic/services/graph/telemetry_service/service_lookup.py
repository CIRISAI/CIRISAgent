"""
Service lookup helpers for TelemetryAggregator.

Contains functions for looking up services from runtime and registry.
"""

import logging
from typing import Any, List, Optional

logger = logging.getLogger(__name__)


# Map service names to runtime attributes
RUNTIME_ATTRS = {
    # Graph services
    "memory": "memory_service",
    "config": "config_service",
    "telemetry": "telemetry_service",
    "audit": "audit_service",
    "incident_management": "incident_management_service",
    "tsdb_consolidation": "tsdb_consolidation_service",
    # Infrastructure services
    "time": "time_service",
    "shutdown": "shutdown_service",
    "initialization": "initialization_service",
    "authentication": "authentication_service",
    "resource_monitor": "resource_monitor",
    "database_maintenance": "maintenance_service",
    "secrets": "secrets_service",
    # Governance services
    "wise_authority": "wa_auth_system",
    "adaptive_filter": "adaptive_filter_service",
    "visibility": "visibility_service",
    "self_observation": "self_observation_service",
    "consent": "consent_service",
    # Runtime services
    "llm": "llm_service",
    "runtime_control": "runtime_control_service",
    "task_scheduler": "task_scheduler",
    # Tool services
    "secrets_tool": "secrets_tool_service",
}


# Map expected names to actual registered class names
NAME_MAP = {
    # Graph services
    "memory": ["memoryservice", "localgraphmemoryservice"],
    "config": ["configservice", "graphconfigservice"],
    "telemetry": ["telemetryservice", "graphtelemetryservice"],
    "audit": ["auditservice"],
    "incident_management": ["incidentmanagementservice"],
    "tsdb_consolidation": ["tsdbconsolidationservice"],
    # Infrastructure services
    "time": ["timeservice"],
    "shutdown": ["shutdownservice"],
    "initialization": ["initializationservice"],
    "authentication": ["authenticationservice"],
    "resource_monitor": ["resourcemonitorservice"],
    "database_maintenance": ["databasemaintenanceservice"],
    "secrets": ["secretsservice"],
    # Governance services
    "wise_authority": ["wiseauthorityservice"],
    "adaptive_filter": ["adaptivefilterservice"],
    "visibility": ["visibilityservice"],
    "self_observation": ["selfobservationservice"],
    "consent": ["consentservice"],
    # Runtime services
    "llm": ["llmservice", "mockllmservice"],
    "runtime_control": ["runtimecontrolservice", "apiruntimecontrolservice"],
    "task_scheduler": ["taskschedulerservice"],
    # Tool services
    "secrets_tool": ["secretstoolservice"],
}


def get_service_from_runtime(runtime: Any, service_name: str) -> Optional[Any]:
    """Get service directly from runtime attributes."""
    if not runtime:
        logger.debug(f"[TELEMETRY] No runtime available for service {service_name}")
        return None

    attr_name = RUNTIME_ATTRS.get(service_name)
    if attr_name:
        service = getattr(runtime, attr_name, None)
        if service:
            logger.debug(
                f"Found {service_name} as runtime.{attr_name}: {service.__class__.__name__ if service else 'None'}"
            )
            # Extra debug - check if service has required telemetry methods
            has_get_metrics = hasattr(service, "get_metrics")
            has_collect_metrics = hasattr(service, "_collect_metrics")
            is_started = getattr(service, "_started", False)
            logger.debug(
                f"  Service {service_name} telemetry: get_metrics={has_get_metrics}, _collect_metrics={has_collect_metrics}, _started={is_started}"
            )
            return service
        else:
            logger.debug(f"[TELEMETRY] runtime.{attr_name} is None for {service_name}")
    else:
        logger.debug(f"[TELEMETRY] No runtime attr mapping for {service_name}")
    return None


def get_service_from_registry(runtime: Optional[Any], service_registry: Any, service_name: str) -> Optional[Any]:
    """Get service from runtime first, then registry by name."""
    # First try to get service directly from runtime
    if runtime:
        runtime_service = get_service_from_runtime(runtime, service_name)
        if runtime_service:
            logger.debug(
                f"Found {service_name} directly from runtime: {runtime_service.__class__.__name__ if runtime_service else 'None'}"
            )
            return runtime_service

    # Fall back to registry lookup
    all_services: List[Any] = service_registry.get_all_services() if service_registry else []
    logger.debug(f"[TELEMETRY] Looking for {service_name} in {len(all_services)} registered services")

    if service_name not in NAME_MAP:
        logger.debug(f"Service {service_name} not in name_map")
        return None

    # Check each service in registry
    for service in all_services:
        if hasattr(service, "__class__"):
            class_name = service.__class__.__name__.lower()
            # Check if class name matches any expected variant
            for variant in NAME_MAP[service_name]:
                if class_name == variant:
                    logger.debug(f"Found service {service_name} as {service.__class__.__name__}")
                    return service

    logger.debug(f"Service {service_name} not found in {len(all_services)} services")
    return None
