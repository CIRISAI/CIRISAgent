"""
Hot/Cold Path Telemetry Configuration

Defines which code paths are HOT (mission-critical, high-frequency) vs COLD (background, low-frequency)
and enforces telemetry requirements based on the ciris_mypy_toolkit analysis.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Set


@dataclass
class PathConfig:
    """Configuration for a specific code path."""

    path_type: str  # hot, cold, critical
    telemetry_required: bool
    retention_policy: str  # raw, aggregated, sampled
    alert_threshold_ms: float  # Alert if execution exceeds this
    sampling_rate: float = 1.0  # 1.0 = 100% sampling


@dataclass
class ModulePathConfig:
    """Hot/cold path configuration for a module."""

    module_name: str
    hot_types: Set[str] = field(default_factory=set)
    cold_types: Set[str] = field(default_factory=set)
    critical_functions: Set[str] = field(default_factory=set)
    telemetry_points: List[str] = field(default_factory=list)


# Global hot/cold path configuration based on ciris_mypy_toolkit analysis
HOT_COLD_PATH_CONFIG: Dict[str, PathConfig] = {
    # CRITICAL PATHS - Always monitor with full telemetry
    "audit_log": PathConfig("critical", True, "raw", 10.0),
    "security_check": PathConfig("critical", True, "raw", 5.0),
    "auth_verification": PathConfig("critical", True, "raw", 5.0),
    "error_handler": PathConfig("critical", True, "raw", 20.0),
    "circuit_breaker": PathConfig("critical", True, "raw", 1.0),
    # HOT PATHS - Core agent processing
    "thought_processing": PathConfig("hot", True, "raw", 100.0),
    "action_selection": PathConfig("hot", True, "raw", 50.0),
    "handler_invocation": PathConfig("hot", True, "raw", 200.0),
    "dma_execution": PathConfig("hot", True, "raw", 150.0),
    "conscience_check": PathConfig("hot", True, "raw", 30.0),
    # WARM PATHS - Important but less frequent
    "context_building": PathConfig("hot", True, "aggregated", 300.0, 0.5),
    "service_lookup": PathConfig("hot", True, "aggregated", 50.0, 0.5),
    "message_processing": PathConfig("hot", True, "aggregated", 100.0, 0.8),
    # COLD PATHS - Background operations
    "memory_operation": PathConfig("cold", False, "aggregated", 1000.0, 0.1),
    "persistence_fetch": PathConfig("cold", False, "aggregated", 500.0, 0.2),
    "context_fetch": PathConfig("cold", False, "sampled", 300.0, 0.1),
    "telemetry_aggregation": PathConfig("cold", False, "sampled", 5000.0, 0.05),
}

# Module-specific configurations
MODULE_CONFIGS: Dict[str, ModulePathConfig] = {
    "ciris_engine.processor.thought_processor": ModulePathConfig(
        module_name="thought_processor",
        hot_types={"Thought", "ActionSelectionDMAResult", "ThoughtContext", "DMAResults"},
        cold_types={"ConscienceResult", "EpistemicData"},
        critical_functions={"process_thought", "_handle_special_cases"},
        telemetry_points=["thought_processing_started", "thought_processing_completed", "action_selected"],
    ),
    "ciris_engine.action_handlers": ModulePathConfig(
        module_name="action_handlers",
        hot_types={"ActionSelectionDMAResult", "DispatchContext", "HandlerActionType"},
        cold_types={"AuditLogEntry", "ServiceCorrelation"},
        critical_functions={"dispatch", "handle"},
        telemetry_points=["handler_invoked", "handler_completed", "handler_error"],
    ),
    "ciris_engine.services": ModulePathConfig(
        module_name="services",
        hot_types={"ServiceProvider", "ServiceType"},
        cold_types={"ServiceHealth", "ServiceMetrics"},
        critical_functions={"get_service", "register_service"},
        telemetry_points=["service_lookup", "service_registered", "service_health_check"],
    ),
    "ciris_engine.dma": ModulePathConfig(
        module_name="dma",
        hot_types={"EthicalDMAResult", "CSDMAResult", "DSDMAResult"},
        cold_types={"DMAMetrics", "DMAHistory"},
        critical_functions={"evaluate", "run_dma_with_retries"},
        telemetry_points=["dma_started", "dma_completed", "dma_failed"],
    ),
}


def get_path_config(metric_name: str) -> PathConfig:
    """Get the path configuration for a metric."""
    # Check exact matches first
    if metric_name in HOT_COLD_PATH_CONFIG:
        return HOT_COLD_PATH_CONFIG[metric_name]

    # Check prefixes
    for path_name, config in HOT_COLD_PATH_CONFIG.items():
        if metric_name.startswith(path_name):
            return config

    # Default to normal path
    return PathConfig("normal", False, "aggregated", 1000.0, 0.1)


def is_hot_path(module: str, type_name: str) -> bool:
    """Check if a type in a module is on the hot path."""
    for module_pattern, config in MODULE_CONFIGS.items():
        if module_pattern in module:
            return type_name in config.hot_types
    return False


def is_critical_function(module: str, function_name: str) -> bool:
    """Check if a function is critical and requires telemetry."""
    for module_pattern, config in MODULE_CONFIGS.items():
        if module_pattern in module:
            return function_name in config.critical_functions
    return False


def get_telemetry_requirements(module: str, operation: str) -> dict[str, Any]:
    """Get telemetry requirements for a module operation."""
    path_config = get_path_config(operation)

    return {
        "enabled": path_config.telemetry_required,
        "path_type": path_config.path_type,
        "retention_policy": path_config.retention_policy,
        "sampling_rate": path_config.sampling_rate,
        "alert_threshold_ms": path_config.alert_threshold_ms,
    }
