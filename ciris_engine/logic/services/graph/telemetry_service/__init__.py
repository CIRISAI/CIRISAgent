"""Telemetry Service Module.

This module provides telemetry collection, aggregation, and storage services
for the CIRIS agent platform.

The module is organized into the following components:
- service.py: Main GraphTelemetryService class
- aggregator.py: TelemetryAggregator for enterprise telemetry collection
- registry_collection.py: Registry collection helper functions
- service_lookup.py: Service lookup helper functions
- bus_collection.py: Bus collection helper functions
- adapter_collection.py: Adapter collection helper functions
- metrics_helpers.py: Metrics conversion and calculation helpers
- storage.py: Storage helpers for different memory types
- helpers.py: Helper functions for telemetry calculations and queries
- exceptions.py: Custom exceptions for telemetry operations
"""

from .service import GraphTelemetryService

# Re-export TelemetryAggregator and related types for backward compatibility
from .aggregator import (
    ConsolidationCandidate,
    GracePolicy,
    MemoryType,
    TelemetryAggregator,
)

# Re-export helper functions for direct access if needed
from .registry_collection import (
    collect_from_registry_provider,
    collect_from_registry_services,
    generate_semantic_service_name,
)

from .service_lookup import (
    NAME_MAP,
    RUNTIME_ATTRS,
    get_service_from_registry,
    get_service_from_runtime,
)

from .bus_collection import (
    BUS_ATTR_MAP,
    UPTIME_METRIC_MAP,
    collect_from_bus,
    collect_from_component,
)

from .adapter_collection import (
    collect_from_adapter_instances,
    collect_from_adapter_with_metrics,
    collect_from_bootstrap_adapters,
    collect_from_control_service,
    create_empty_telemetry,
    create_running_telemetry,
    create_telemetry_data,
    find_adapter_instance,
    get_adapter_metrics,
    get_control_service,
    is_adapter_running,
)

from .metrics_helpers import (
    aggregate_service_metrics,
    calculate_aggregates,
    compute_covenant_metrics,
    convert_dict_to_telemetry,
    extract_governance_metrics,
    extract_metric_value,
    get_fallback_metrics,
    process_service_metrics,
    status_to_telemetry,
    try_collect_metrics,
    try_collect_metrics_method,
    try_get_metrics_method,
    try_get_status_method,
)

__all__ = [
    # Main classes
    "GraphTelemetryService",
    "TelemetryAggregator",
    # Enums and data classes
    "MemoryType",
    "GracePolicy",
    "ConsolidationCandidate",
    # Registry collection functions
    "generate_semantic_service_name",
    "collect_from_registry_services",
    "collect_from_registry_provider",
    # Service lookup functions and mappings
    "RUNTIME_ATTRS",
    "NAME_MAP",
    "get_service_from_runtime",
    "get_service_from_registry",
    # Bus collection functions and mappings
    "BUS_ATTR_MAP",
    "UPTIME_METRIC_MAP",
    "collect_from_bus",
    "collect_from_component",
    # Adapter collection functions
    "get_control_service",
    "is_adapter_running",
    "find_adapter_instance",
    "get_adapter_metrics",
    "create_telemetry_data",
    "create_empty_telemetry",
    "create_running_telemetry",
    "collect_from_adapter_with_metrics",
    "collect_from_control_service",
    "collect_from_bootstrap_adapters",
    "collect_from_adapter_instances",
    # Metrics helper functions
    "convert_dict_to_telemetry",
    "try_get_metrics_method",
    "try_collect_metrics_method",
    "try_get_status_method",
    "try_collect_metrics",
    "get_fallback_metrics",
    "status_to_telemetry",
    "process_service_metrics",
    "aggregate_service_metrics",
    "extract_metric_value",
    "extract_governance_metrics",
    "compute_covenant_metrics",
    "calculate_aggregates",
]
