#!/usr/bin/env python3
"""Fix metric tests to match v1.4.3 real metrics implementation."""

import re
from pathlib import Path
from typing import Dict, Set

# Map of service names to their actual v1.4.3 metrics
SERVICE_METRICS = {
    "wise_authority": {
        "wise_authority_deferrals_total",
        "wise_authority_deferrals_resolved",
        "wise_authority_guidance_requests",
        "wise_authority_uptime_seconds",
    },
    "adaptive_filter": {
        "filter_messages_processed",
        "filter_messages_blocked",
        "filter_triggers_activated",
        "filter_uptime_seconds",
    },
    "visibility": {
        "visibility_requests_total",
        "visibility_transparency_enabled",
        "visibility_feeds_active",
        "visibility_uptime_seconds",
    },
    "self_observation": {
        "self_observation_observations",
        "self_observation_patterns_detected",
        "self_observation_identity_variance",
        "self_observation_uptime_seconds",
    },
    "memory": {
        "memory_nodes_total",
        "memory_edges_total",
        "memory_operations_total",
        "memory_db_size_mb",
        "memory_uptime_seconds",
    },
    "config": {"config_cache_hits", "config_cache_misses", "config_values_total", "config_uptime_seconds"},
    "telemetry": {
        "telemetry_metrics_collected",
        "telemetry_services_monitored",
        "telemetry_cache_hits",
        "telemetry_collection_errors",
        "telemetry_uptime_seconds",
    },
    "audit": {"audit_events_total", "audit_events_by_severity", "audit_compliance_checks", "audit_uptime_seconds"},
    "incident_management": {
        "incident_events_total",
        "incident_active_incidents",
        "incident_severity_high",
        "incident_uptime_seconds",
    },
    "tsdb_consolidation": {
        "tsdb_consolidations_total",
        "tsdb_data_points",
        "tsdb_retention_days",
        "tsdb_uptime_seconds",
    },
    "secrets_tool": {
        "secrets_tool_invocations",
        "secrets_tool_retrieved",
        "secrets_tool_stored",
        "secrets_tool_uptime_seconds",
    },
    "authentication": {
        "auth_requests_total",
        "auth_successful",
        "auth_failed",
        "auth_sessions_active",
        "auth_uptime_seconds",
    },
    "resource_monitor": {
        "resource_cpu_percent",
        "resource_memory_mb",
        "resource_disk_gb",
        "resource_checks_total",
        "resource_uptime_seconds",
    },
    "database_maintenance": {
        "db_maintenance_runs",
        "db_optimization_completed",
        "db_cleanup_completed",
        "db_size_mb",
        "db_uptime_seconds",
    },
    "initialization": {
        "init_services_initialized",
        "init_initialization_time_ms",
        "init_dependencies_resolved",
        "init_uptime_seconds",
    },
    "shutdown": {
        "shutdown_graceful_stops",
        "shutdown_emergency_stops",
        "shutdown_pending_tasks",
        "shutdown_uptime_seconds",
    },
    "time": {"time_requests_total", "time_sync_adjustments", "time_drift_ms", "time_uptime_seconds"},
    "task_scheduler": {
        "scheduler_tasks_scheduled",
        "scheduler_tasks_completed",
        "scheduler_tasks_failed",
        "scheduler_queue_size",
        "scheduler_uptime_seconds",
    },
    "runtime_control": {
        "runtime_commands_received",
        "runtime_state_changes",
        "runtime_errors",
        "runtime_uptime_seconds",
    },
    "llm": {
        "llm_requests_total",
        "llm_tokens_input",
        "llm_tokens_output",
        "llm_tokens_total",
        "llm_cost_cents",
        "llm_errors_total",
        "llm_uptime_seconds",
    },
}

# Common metrics that are removed in v1.4.3
REMOVED_METRICS = {
    "healthy",
    "error_rate",
    "success_rate",
    "error_count",
    "tool_executions",
    "total_deferrals",
    "pending_deferrals",
    "resolved_deferrals",
    "messages_processed",
    "messages_flagged",
    "trigger_matches",
    "transparency_requests",
    "transparency_enabled",
    "feed_subscriptions",
    "observation_count",
    "pattern_detections",
    "variance_score",
}


def fix_test_file(filepath: Path) -> bool:
    """Fix a single test file to use v1.4.3 metrics."""
    content = filepath.read_text()
    original = content

    # Remove assertions for removed metrics
    for metric in REMOVED_METRICS:
        # Pattern 1: assert metrics["metric_name"] == value
        pattern1 = re.compile(rf'assert metrics\["{metric}"\].*?\n', re.MULTILINE)
        content = pattern1.sub("", content)

        # Pattern 2: assert "metric_name" in metrics
        pattern2 = re.compile(rf'assert "{metric}" in metrics.*?\n', re.MULTILINE)
        content = pattern2.sub("", content)

        # Pattern 3: metrics["metric_name"] in comparisons
        pattern3 = re.compile(rf'.*?metrics\["{metric}"\].*?\n', re.MULTILINE)
        content = pattern3.sub("", content)

    # Fix expected metric sets in tests
    for service, metrics in SERVICE_METRICS.items():
        # Look for expected metrics sets
        if service in filepath.name.lower() or service.replace("_", "") in filepath.name.lower():
            # Replace old metric expectations with new ones
            metrics_str = ", ".join(f'"{m}"' for m in sorted(metrics))

            # Pattern: expected = {...}
            pattern = re.compile(rf"expected\s*=\s*\{{[^}}]+\}}", re.MULTILINE | re.DOTALL)
            replacement = f"expected = {{{metrics_str}}}"
            content = pattern.sub(replacement, content)

            # Pattern: expected_metrics = {...}
            pattern2 = re.compile(rf"expected_metrics\s*=\s*\{{[^}}]+\}}", re.MULTILINE | re.DOTALL)
            content = pattern2.sub(replacement, content)

    # Remove empty test methods that only had removed assertions
    content = re.sub(r'(async )?def test_[^(]+\([^)]*\):\s*"""[^"]*"""\s*$', "", content, flags=re.MULTILINE)

    if content != original:
        filepath.write_text(content)
        return True
    return False


def main():
    """Fix all metric test files."""
    test_files = [
        "tests/test_metrics_governance_services.py",
        "tests/test_metrics_graph_services.py",
        "tests/test_metrics_infrastructure_services.py",
        "tests/test_metrics_runtime_services.py",
        "tests/test_metrics_tool_services.py",
        "tests/test_metrics_integration.py",
        "tests/test_base_service.py",
        "tests/ciris_engine/logic/services/tools/test_secrets_tool_service.py",
        "tests/ciris_engine/logic/persistence/test_maintenance_telemetry.py",
        "tests/ciris_engine/logic/secrets/test_secrets_service_telemetry.py",
    ]

    fixed_count = 0
    for test_file in test_files:
        filepath = Path(test_file)
        if filepath.exists():
            if fix_test_file(filepath):
                print(f"Fixed: {test_file}")
                fixed_count += 1
            else:
                print(f"No changes needed: {test_file}")
        else:
            print(f"Not found: {test_file}")

    print(f"\nFixed {fixed_count} test files")


if __name__ == "__main__":
    main()
