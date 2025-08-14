#!/usr/bin/env python3
"""
Verify what metrics are ACTUALLY being collected and exposed in CIRIS.
This will find the real truth about what's implemented.
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple


def find_metric_collections() -> Dict[str, Set[str]]:
    """Find where metrics are actually being collected in the code"""

    collected_metrics = {
        "telemetry_service": set(),
        "memory_service": set(),
        "api_routes": set(),
        "processors": set(),
        "services": set(),
    }

    # Check telemetry service for record_metric calls
    telemetry_file = Path("/home/emoore/CIRISAgent/ciris_engine/logic/services/graph/telemetry_service.py")
    if telemetry_file.exists():
        content = telemetry_file.read_text()
        # Find metric names in record_metric calls
        matches = re.findall(r'record_metric\(\s*["\']([^"\']+)["\']', content)
        collected_metrics["telemetry_service"].update(matches)

        # Find metrics in _record_resource_usage
        matches = re.findall(r'f["\']{\w+}\.([^"\']+)["\']', content)
        collected_metrics["telemetry_service"].update(matches)

    # Check memory service for memorize_metric calls
    memory_file = Path("/home/emoore/CIRISAgent/ciris_engine/logic/services/graph/memory_service.py")
    if memory_file.exists():
        content = memory_file.read_text()
        # Find metric names
        matches = re.findall(r'metric_name\s*==?\s*["\']([^"\']+)["\']', content)
        collected_metrics["memory_service"].update(matches)

    # Check LLM bus for metric collection
    llm_bus_file = Path("/home/emoore/CIRISAgent/ciris_engine/logic/buses/llm_bus.py")
    if llm_bus_file.exists():
        content = llm_bus_file.read_text()
        # Find self._metrics assignments
        matches = re.findall(r'self\._metrics\[["\']([^"\']+)["\']', content)
        collected_metrics["services"].update(matches)

        # Find metric field names
        matches = re.findall(
            r"(total_requests|failed_requests|total_latency_ms|consecutive_failures|failure_count|success_count)",
            content,
        )
        collected_metrics["services"].update(matches)

    # Check adapters for metric collection
    adapter_files = [
        "/home/emoore/CIRISAgent/ciris_engine/logic/adapters/discord/discord_adapter.py",
        "/home/emoore/CIRISAgent/ciris_engine/logic/adapters/cli/cli_adapter.py",
        "/home/emoore/CIRISAgent/ciris_engine/logic/adapters/api/adapter.py",
    ]

    for adapter_path in adapter_files:
        adapter_file = Path(adapter_path)
        if adapter_file.exists():
            content = adapter_file.read_text()
            # Find memorize_metric calls
            matches = re.findall(r'memorize_metric\(\s*metric_name=["\']([^"\']+)["\']', content)
            collected_metrics["services"].update(matches)

            # Find direct metric names
            matches = re.findall(r'metric_name\s*=\s*["\']([^"\']+)["\']', content)
            collected_metrics["services"].update(matches)

    # Check processors for metrics
    processor_dir = Path("/home/emoore/CIRISAgent/ciris_engine/logic/processors")
    if processor_dir.exists():
        for py_file in processor_dir.rglob("*.py"):
            content = py_file.read_text()
            # Find thoughts_processed, tasks_completed, etc.
            matches = re.findall(
                r"(thoughts_processed|tasks_completed|messages_processed|errors)\s*[=:]\s*\d+", content
            )
            collected_metrics["processors"].update(matches)

    return collected_metrics


def find_exposed_metrics() -> Dict[str, List[str]]:
    """Find what metrics are exposed via API endpoints"""

    exposed = {"overview_fields": [], "queryable_metrics": [], "resource_metrics": [], "detailed_metrics": []}

    # Check telemetry.py routes
    telemetry_routes = Path("/home/emoore/CIRISAgent/ciris_engine/logic/adapters/api/routes/telemetry.py")
    if telemetry_routes.exists():
        content = telemetry_routes.read_text()

        # Find SystemOverview fields
        if "class SystemOverview" in content:
            class_start = content.index("class SystemOverview")
            class_section = content[class_start : class_start + 2000]
            # Extract field names
            matches = re.findall(r"(\w+):\s*(?:int|float|str|bool|Optional)", class_section)
            exposed["overview_fields"] = matches[:30]  # First 30 fields

        # Find metrics queried in get_detailed_metrics
        if "metric_names = [" in content:
            list_start = content.index("metric_names = [")
            list_section = content[list_start : list_start + 500]
            matches = re.findall(r'["\']([^"\']+)["\']', list_section)
            exposed["detailed_metrics"] = matches

        # Find metrics queried elsewhere
        matches = re.findall(r'query_metrics\(\s*metric_name=["\']([^"\']+)["\']', content)
        exposed["queryable_metrics"].extend(matches)

    # Check system.py routes
    system_routes = Path("/home/emoore/CIRISAgent/ciris_engine/logic/adapters/api/routes/system.py")
    if system_routes.exists():
        content = system_routes.read_text()
        # Find resource metrics
        matches = re.findall(r"(cpu_percent|memory_mb|disk_usage|memory_percent)", content)
        exposed["resource_metrics"] = list(set(matches))

    return exposed


def find_telemetry_summary_metrics() -> List[str]:
    """Find what metrics are in telemetry summary"""

    summary_metrics = []

    # Check telemetry service for get_telemetry_summary
    telemetry_file = Path("/home/emoore/CIRISAgent/ciris_engine/logic/services/graph/telemetry_service.py")
    if telemetry_file.exists():
        content = telemetry_file.read_text()

        # Find TelemetrySummary class or method
        if "get_telemetry_summary" in content:
            method_start = content.index("get_telemetry_summary")
            method_section = content[method_start : method_start + 3000]

            # Find field assignments
            matches = re.findall(
                r"(\w+_24h|tokens_\w+|cost_\w+|carbon_\w+|energy_\w+|error_rate_percent)", method_section
            )
            summary_metrics = list(set(matches))

    return summary_metrics


def main():
    """Main verification function"""

    print("=" * 80)
    print("CIRIS METRICS: REALITY CHECK")
    print("What metrics are ACTUALLY collected and exposed?")
    print("=" * 80)

    # Find collected metrics
    collected = find_metric_collections()

    print("\n📊 METRICS BEING COLLECTED:")
    for source, metrics in collected.items():
        if metrics:
            print(f"\n  {source}: {len(metrics)} metrics")
            for metric in sorted(list(metrics)[:10]):
                print(f"    • {metric}")

    # Find exposed metrics
    exposed = find_exposed_metrics()

    print("\n🌐 METRICS EXPOSED VIA API:")
    print(f"\n  SystemOverview fields: {len(exposed['overview_fields'])}")
    for field in exposed["overview_fields"][:15]:
        print(f"    • {field}")

    print(f"\n  Detailed metrics endpoint: {len(exposed['detailed_metrics'])}")
    for metric in exposed["detailed_metrics"]:
        print(f"    • {metric}")

    print(f"\n  Resource metrics: {len(exposed['resource_metrics'])}")
    for metric in exposed["resource_metrics"]:
        print(f"    • {metric}")

    # Find telemetry summary
    summary_metrics = find_telemetry_summary_metrics()
    if summary_metrics:
        print(f"\n  Telemetry summary: {len(summary_metrics)} metrics")
        for metric in sorted(summary_metrics)[:10]:
            print(f"    • {metric}")

    # Calculate totals
    total_collected = sum(len(metrics) for metrics in collected.values())
    total_exposed = (
        len(exposed["overview_fields"])
        + len(exposed["detailed_metrics"])
        + len(exposed["resource_metrics"])
        + len(summary_metrics)
    )

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    print(
        f"""
✅ ACTUAL IMPLEMENTATION:
  • Metrics being collected: ~{total_collected}
  • Metrics exposed via API: ~{total_exposed}
  • SystemOverview fields: {len(exposed['overview_fields'])}
  • Detailed metrics queryable: {len(exposed['detailed_metrics'])}

📝 DOCUMENTED IN .md FILES:
  • Total documented: 485 metrics
  • Across 35 modules

🎯 THE REAL SITUATION:
  • We ARE collecting many metrics (via memorize_metric)
  • We ARE exposing aggregate metrics (SystemOverview)
  • We ARE exposing some detailed metrics
  • The /telemetry/metrics/{{metric_name}} endpoint EXISTS

❓ THE QUESTION:
  Are the 485 documented metrics just aspirational documentation?
  Or are they actually being collected somewhere we haven't found?
"""
    )

    # Save findings
    findings = {
        "collected": {k: list(v) for k, v in collected.items()},
        "exposed": exposed,
        "summary_metrics": summary_metrics,
        "total_collected": total_collected,
        "total_exposed": total_exposed,
        "documented": 485,
    }

    findings_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/actual_metrics_reality.json")
    findings_file.write_text(json.dumps(findings, indent=2))
    print(f"\n📁 Reality check saved to: {findings_file}")


if __name__ == "__main__":
    main()
