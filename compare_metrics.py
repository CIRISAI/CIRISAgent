#!/usr/bin/env python3
"""
Compare metric names from telemetry tool implementation with telemetry_service.py
"""

import json
import re
from pathlib import Path


def get_metrics_from_telemetry_tool():
    """Extract metric names from the telemetry tool's MDD database."""
    metrics = set()

    # Read the implementation summary to get documented metrics
    implementation_file = Path("tools/telemetry_tool/IMPLEMENTATION_SUMMARY.md")
    if implementation_file.exists():
        content = implementation_file.read_text()
        # Extract metrics mentioned in the file
        # Look for patterns like "llm.tokens.total" or "handler_completed_total"
        pattern = r'"([a-z_\.]+(?:_[a-z]+)*)"'
        matches = re.findall(pattern, content)
        metrics.update(matches)

    # Read the MDD database if it exists
    mdd_file = Path("tools/telemetry_tool/mdd.db")
    if mdd_file.exists():
        import sqlite3

        conn = sqlite3.connect(str(mdd_file))
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT metric_name FROM metrics WHERE status != 'SKIP'")
        for row in cursor.fetchall():
            metrics.add(row[0])
        conn.close()

    # Also check the telemetry reality report
    reality_file = Path("tools/telemetry_tool/TELEMETRY_REALITY_REPORT.md")
    if reality_file.exists():
        content = reality_file.read_text()
        # Look for metric names in quotes
        pattern = r'["\'`]([a-z_\.]+(?:_[a-z]+)*)["\'`]'
        matches = re.findall(pattern, content)
        metrics.update(matches)

    return metrics


def get_metrics_from_telemetry_service():
    """Extract metric names from telemetry_service.py."""
    metrics = set()

    service_file = Path("ciris_engine/logic/services/graph/telemetry_service.py")
    if service_file.exists():
        content = service_file.read_text()

        # Find metric_types list
        pattern = r"metric_types\s*=\s*\[(.*?)\]"
        match = re.search(pattern, content, re.DOTALL)
        if match:
            list_content = match.group(1)
            # Extract metric names from tuples
            tuple_pattern = r'\("([^"]+)"'
            matches = re.findall(tuple_pattern, list_content)
            metrics.update(matches)

        # Also find any query_metrics calls
        query_pattern = r'query_metrics\([^)]*metric_name\s*=\s*["\']([\w\.]+)'
        matches = re.findall(query_pattern, content)
        metrics.update(matches)

        # Find record_metric calls
        record_pattern = r'record_metric\(["\']([^"\']+)'
        matches = re.findall(record_pattern, content)
        metrics.update(matches)

    return metrics


def get_metrics_from_api_routes():
    """Extract metric names from API telemetry routes."""
    metrics = set()

    routes_file = Path("ciris_engine/logic/adapters/api/routes/telemetry.py")
    if routes_file.exists():
        content = routes_file.read_text()

        # Find metric_names lists
        pattern = r"metric_names\s*=\s*\[(.*?)\]"
        matches = re.findall(pattern, content, re.DOTALL)
        for match in matches:
            # Extract metric names from the list
            name_pattern = r'["\']([\w\.]+)["\']'
            names = re.findall(name_pattern, match)
            metrics.update(names)

    return metrics


def get_actual_metrics_from_production():
    """Get the actual metric names we found in production TSDB nodes."""
    # These are the metrics we discovered via curl query
    production_metrics = {
        "llm.tokens.output",
        "llm.tokens.input",
        "llm.tokens.total",
        "llm.latency.ms",
        "llm.environmental.energy_kwh",
        "llm.environmental.carbon_grams",
        "llm.cost.cents",
        "llm_tokens_used",
        "llm_api_call_structured",
        "thought_processing_completed",
        "thought_processing_started",
        "handler_invoked_total",
        "handler_completed_total",
        "handler_invoked_task_complete",
        "handler_invoked_memorize",
        "handler_completed_task_complete",
        "handler_completed_memorize",
        "action_selected_task_complete",
        "action_selected_memorize",
    }
    return production_metrics


def main():
    """Compare metrics from different sources."""
    print("=" * 80)
    print("CIRIS Telemetry Metrics Comparison")
    print("=" * 80)

    # Get metrics from different sources
    tool_metrics = get_metrics_from_telemetry_tool()
    service_metrics = get_metrics_from_telemetry_service()
    api_metrics = get_metrics_from_api_routes()
    production_metrics = get_actual_metrics_from_production()

    print(f"\n📊 Metrics Found:")
    print(f"  - Telemetry Tool Documented: {len(tool_metrics)}")
    print(f"  - Telemetry Service Queries: {len(service_metrics)}")
    print(f"  - API Routes Queries: {len(api_metrics)}")
    print(f"  - Production TSDB Nodes: {len(production_metrics)}")

    # Find metrics that exist in production but not being queried
    print("\n✅ Metrics in Production TSDB:")
    for metric in sorted(production_metrics):
        in_service = "✓" if metric in service_metrics else "✗"
        in_api = "✓" if metric in api_metrics else "✗"
        in_tool = "✓" if metric in tool_metrics else "✗"
        print(f"  {metric:40} Service:{in_service} API:{in_api} Tool:{in_tool}")

    # Find metrics being queried but don't exist
    all_queried = service_metrics.union(api_metrics)
    missing_metrics = all_queried - production_metrics

    if missing_metrics:
        print("\n❌ Metrics Being Queried But Don't Exist in Production:")
        for metric in sorted(missing_metrics):
            sources = []
            if metric in service_metrics:
                sources.append("Service")
            if metric in api_metrics:
                sources.append("API")
            print(f"  {metric:40} (queried by: {', '.join(sources)})")

    # Find metrics in production not being queried
    unqueried = production_metrics - all_queried
    if unqueried:
        print("\n⚠️ Metrics in Production But Not Being Queried:")
        for metric in sorted(unqueried):
            print(f"  {metric}")

    # Summary
    print("\n📈 Summary:")
    coverage = len(production_metrics.intersection(all_queried)) / len(production_metrics) * 100
    print(f"  Query Coverage: {coverage:.1f}% of production metrics are being queried")

    false_queries = len(missing_metrics)
    print(f"  False Queries: {false_queries} metrics being queried don't exist")

    print("\n💡 Recommendations:")
    if missing_metrics:
        print("  1. Remove or fix queries for non-existent metrics:")
        for metric in list(missing_metrics)[:5]:
            print(f"     - {metric}")

    if unqueried:
        print("  2. Add queries for these production metrics:")
        for metric in list(unqueried)[:5]:
            print(f"     - {metric}")

    # Export to JSON for further analysis
    comparison_data = {
        "production_metrics": sorted(production_metrics),
        "service_queries": sorted(service_metrics),
        "api_queries": sorted(api_metrics),
        "tool_documented": sorted(tool_metrics),
        "missing_in_production": sorted(missing_metrics),
        "unqueried_production": sorted(unqueried),
        "coverage_percent": coverage,
    }

    with open("metric_comparison_report.json", "w") as f:
        json.dump(comparison_data, f, indent=2)

    print("\n✅ Full comparison saved to metric_comparison_report.json")


if __name__ == "__main__":
    main()
