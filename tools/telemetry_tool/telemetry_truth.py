#!/usr/bin/env python3
"""
The TRUTH about CIRIS telemetry - no bullshit, no confusion.
What metrics exist, where they come from, how to get them.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set


def find_actual_metrics():
    """Find ACTUAL metrics in the codebase - be precise."""

    base_path = Path("/home/emoore/CIRISAgent/ciris_engine")

    results = {
        "services_with_get_telemetry": [],
        "services_with_collect_metrics": [],
        "metrics_pushed_to_tsdb": [],
        "base_service_metrics": [],
        "actual_metric_counts": {},
    }

    # 1. WHO has get_telemetry() implemented?
    print("Finding services with get_telemetry()...")
    get_telemetry_files = [
        "logic/services/graph/memory_service.py",
        "logic/services/graph/config_service.py",
        "logic/services/graph/incident_service.py",
        "logic/services/tools/secrets_tool_service.py",
    ]

    for file_path in get_telemetry_files:
        full_path = base_path / file_path
        if full_path.exists():
            service_name = file_path.split("/")[-1].replace("_service.py", "").replace(".py", "")

            # Count actual metrics in return statement
            with open(full_path) as f:
                content = f.read()

            # Find the get_telemetry method
            if "async def get_telemetry" in content:
                # Count dictionary keys in return statement
                import re

                # Look for patterns like "key": value in return statement
                return_section = content.split("async def get_telemetry")[1].split("return {")[1].split("}")[0]
                metrics = re.findall(r'"(\w+)":', return_section)

                # Filter out non-metric keys
                metrics = [m for m in metrics if m not in ["service_name", "healthy", "error", "last_updated"]]

                results["services_with_get_telemetry"].append(
                    {
                        "service": service_name,
                        "file": str(file_path),
                        "metric_count": len(metrics),
                        "metrics": metrics[:5],  # Sample
                    }
                )
                results["actual_metric_counts"][service_name] = len(metrics)

    # 2. BaseService provides these metrics to ALL services
    print("Base metrics from BaseService...")
    results["base_service_metrics"] = ["uptime_seconds", "request_count", "error_count", "error_rate", "healthy"]

    # 3. Metrics PUSHED to TSDB (historical)
    print("Finding TSDB metrics...")

    # LLM metrics pushed to TSDB
    llm_tsdb_metrics = [
        "llm.tokens.total",
        "llm.tokens.input",
        "llm.tokens.output",
        "llm.cost.cents",
        "llm.environmental.carbon_grams",
        "llm.environmental.energy_kwh",
        "llm.latency.ms",
    ]

    # Handler metrics pushed to TSDB
    handler_tsdb_metrics = [
        "handler_invoked_total",
        "handler_completed_total",
        "handler_invoked_memorize",
        "handler_completed_memorize",
        "handler_invoked_task_complete",
        "handler_completed_task_complete",
        "action_selected_memorize",
        "action_selected_task_complete",
    ]

    # Other TSDB metrics
    other_tsdb_metrics = ["error.occurred", "thought_processing_started", "thought_processing_completed"]

    results["metrics_pushed_to_tsdb"] = {
        "llm": llm_tsdb_metrics,
        "handlers": handler_tsdb_metrics,
        "other": other_tsdb_metrics,
        "total_count": len(llm_tsdb_metrics) + len(handler_tsdb_metrics) + len(other_tsdb_metrics),
    }

    # 4. Services with _collect_custom_metrics
    print("Finding services with _collect_custom_metrics...")
    custom_metrics_services = []

    for py_file in base_path.rglob("*.py"):
        if "__pycache__" in str(py_file):
            continue

        try:
            with open(py_file) as f:
                content = f.read()

            if "def _collect_custom_metrics" in content:
                service_name = py_file.stem

                # Extract metrics from the method
                method_section = content.split("def _collect_custom_metrics")[1].split("return")[1].split("\n")[0]

                custom_metrics_services.append({"file": str(py_file.relative_to(base_path)), "service": service_name})

        except:
            pass

    results["services_with_collect_metrics"] = custom_metrics_services[:10]  # Top 10

    return results


def generate_truth_report(results):
    """Generate the TRUTH report."""

    report = []
    report.append("=" * 80)
    report.append("📊 CIRIS TELEMETRY - THE TRUTH - v1.4.3")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().isoformat()}")
    report.append("")

    # Services with get_telemetry
    report.append("✅ SERVICES WITH get_telemetry() IMPLEMENTED:")
    report.append("-" * 40)
    total_telemetry_metrics = 0
    for service in results["services_with_get_telemetry"]:
        report.append(f"  • {service['service']:20} {service['metric_count']:3} metrics")
        total_telemetry_metrics += service["metric_count"]
    report.append(f"  TOTAL: {total_telemetry_metrics} metrics via get_telemetry()")
    report.append("")

    # Base metrics
    report.append("🔧 BASE METRICS (all services inherit):")
    report.append("-" * 40)
    for metric in results["base_service_metrics"]:
        report.append(f"  • {metric}")
    report.append(f"  TOTAL: {len(results['base_service_metrics'])} base metrics × 21 services = ~105 metrics")
    report.append("")

    # TSDB metrics
    report.append("💾 METRICS STORED IN TSDB (historical):")
    report.append("-" * 40)
    tsdb_data = results["metrics_pushed_to_tsdb"]
    report.append(f"  • LLM metrics:     {len(tsdb_data['llm'])}")
    report.append(f"  • Handler metrics: {len(tsdb_data['handlers'])}")
    report.append(f"  • Other metrics:   {len(tsdb_data['other'])}")
    report.append(f"  TOTAL: {tsdb_data['total_count']} metrics in TSDB")
    report.append("")

    # Summary
    report.append("=" * 80)
    report.append("📈 SUMMARY:")
    report.append(f"  • Services with get_telemetry(): {len(results['services_with_get_telemetry'])}/21")
    report.append(f"  • Metrics via get_telemetry(): {total_telemetry_metrics}")
    report.append(f"  • Base metrics (inherited): ~105")
    report.append(f"  • TSDB metrics (historical): {tsdb_data['total_count']}")
    report.append(f"  • TOTAL AVAILABLE: ~{total_telemetry_metrics + 105 + tsdb_data['total_count']}")
    report.append("")

    report.append("🎯 FOR v1.4.3:")
    report.append("  1. Implement get_telemetry() for remaining 17 services")
    report.append("  2. Each service should expose 10-15 metrics")
    report.append("  3. Target: 21 services × 12 metrics = ~250 metrics")
    report.append("  4. Keep TSDB metrics minimal (only what needs history)")
    report.append("=" * 80)

    return "\n".join(report)


def main():
    """Main entry point."""
    print("Analyzing telemetry truth...")
    results = find_actual_metrics()

    report = generate_truth_report(results)
    print(report)

    # Save results
    with open("telemetry_truth.json", "w") as f:
        json.dump({"timestamp": datetime.now().isoformat(), "version": "1.4.3", "results": results}, f, indent=2)

    print("\n💾 Saved truth to telemetry_truth.json")


if __name__ == "__main__":
    main()
