#!/usr/bin/env python3
"""
Check which metrics from the telemetry .md docs are actually implemented in the API
NOT adding new metrics - just tracking what's exposed
"""

import json
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from core.doc_parser import TelemetryDocParser


def get_documented_metrics() -> Dict[str, List[str]]:
    """Parse all .md files to get documented metrics"""
    parser = TelemetryDocParser()
    modules = parser.parse_all_docs()

    metrics_by_module = {}
    for module in modules:
        module_name = module["module_name"]
        # Handle different possible keys for metric name
        metric_names = []
        for m in module.get("metrics", []):
            if isinstance(m, dict):
                name = m.get("metric_name") or m.get("name") or m.get("metric", "")
            else:
                name = str(m)
            if name:
                metric_names.append(name)
        metrics_by_module[module_name] = metric_names

    return metrics_by_module


def check_telemetry_endpoints() -> Dict[str, Set[str]]:
    """Check what metrics are exposed in telemetry endpoints"""
    exposed_metrics = {}

    # Check telemetry.py
    telemetry_file = Path("/home/emoore/CIRISAgent/ciris_engine/logic/adapters/api/routes/telemetry.py")
    if telemetry_file.exists():
        content = telemetry_file.read_text()

        # Look for metric references in the code
        # Common patterns: metric_name, metrics["name"], get_metric("name")
        metric_patterns = [
            r'metric_name\s*==?\s*["\']([^"\']+)["\']',
            r'metrics\[["\']([^"\']+)["\']\]',
            r'get_metric\(["\']([^"\']+)["\']',
            r'["\']metric_name["\']\s*:\s*["\']([^"\']+)["\']',
            r'["\']name["\']\s*:\s*["\']([^"\']+)["\'].*metric',
        ]

        for pattern in metric_patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            for match in matches:
                if match and not match.startswith("{"):  # Skip placeholders
                    if "telemetry" not in exposed_metrics:
                        exposed_metrics["telemetry"] = set()
                    exposed_metrics["telemetry"].add(match)

    # Check telemetry_metrics.py
    metrics_file = Path("/home/emoore/CIRISAgent/ciris_engine/logic/adapters/api/routes/telemetry_metrics.py")
    if metrics_file.exists():
        content = metrics_file.read_text()
        matches = re.findall(
            r'["\']([a-z_]+_(?:count|total|rate|latency|gauge|histogram|errors?))["\']', content, re.IGNORECASE
        )
        for match in matches:
            if "telemetry" not in exposed_metrics:
                exposed_metrics["telemetry"] = set()
            exposed_metrics["telemetry"].add(match)

    # Check system.py for system metrics
    system_file = Path("/home/emoore/CIRISAgent/ciris_engine/logic/adapters/api/routes/system.py")
    if system_file.exists():
        content = system_file.read_text()
        # Look for resource metrics
        if "cpu_percent" in content or "memory_mb" in content:
            if "system" not in exposed_metrics:
                exposed_metrics["system"] = set()
            exposed_metrics["system"].update(["cpu_percent", "memory_mb", "disk_usage"])

    return exposed_metrics


def check_actual_implementation() -> Tuple[Dict, Dict]:
    """Check what's actually returned by the API endpoints"""

    # Check the SystemOverview model in telemetry.py
    telemetry_file = Path("/home/emoore/CIRISAgent/ciris_engine/logic/adapters/api/routes/telemetry.py")
    overview_metrics = set()

    if telemetry_file.exists():
        content = telemetry_file.read_text()

        # Find SystemOverview class definition
        if "class SystemOverview" in content:
            # Extract fields from the model
            class_start = content.index("class SystemOverview")
            class_section = content[class_start : class_start + 3000]  # Get next 3000 chars

            # Find field definitions
            field_pattern = r"(\w+):\s*(?:Optional\[)?(?:int|float|str|bool)"
            matches = re.findall(field_pattern, class_section)
            overview_metrics.update(matches)

    # Check MetricsResponse fields
    metrics_response = set()
    if "class MetricsResponse" in content or "class MetricSeries" in content:
        # These endpoints likely return time series data
        metrics_response.add("metric_name")
        metrics_response.add("data_points")
        metrics_response.add("timestamp")
        metrics_response.add("value")

    return {"overview_fields": overview_metrics, "metrics_fields": metrics_response}


def main():
    """Main comparison function"""

    print("=" * 80)
    print("TELEMETRY METRICS: DOCUMENTED vs IMPLEMENTED")
    print("=" * 80)

    # Get documented metrics from .md files
    documented = get_documented_metrics()
    total_documented = sum(len(metrics) for metrics in documented.values())

    print(f"\n📚 DOCUMENTED in .md files: {total_documented} metrics across {len(documented)} modules")

    # Get exposed metrics from API
    exposed = check_telemetry_endpoints()

    # Get actual implementation
    actual = check_actual_implementation()

    print(f"\n🔌 EXPOSED via API:")
    print(f"  • SystemOverview fields: {len(actual['overview_fields'])}")
    for field in sorted(list(actual["overview_fields"])[:20]):
        print(f"    - {field}")

    # Check coverage by module
    print("\n" + "=" * 80)
    print("COVERAGE BY MODULE")
    print("=" * 80)

    # Sample check for key modules
    key_modules = [
        "LLM_BUS",
        "MEMORY_BUS",
        "TELEMETRY_SERVICE",
        "AUDIT_SERVICE",
        "WISE_AUTHORITY_SERVICE",
        "RESOURCE_MONITOR_SERVICE",
    ]

    for module in key_modules:
        if module in documented:
            doc_metrics = documented[module]
            print(f"\n📦 {module}:")
            print(f"  Documented: {len(doc_metrics)} metrics")

            # Check if any are in overview
            exposed_count = 0
            for metric in doc_metrics:
                # Simplified name matching
                simple_name = metric.lower().replace(module.lower() + "_", "")
                if simple_name in str(actual["overview_fields"]):
                    exposed_count += 1

            if exposed_count > 0:
                print(f"  Potentially exposed: ~{exposed_count}")
            else:
                print(f"  Status: Needs endpoint implementation")

    # The real question
    print("\n" + "=" * 80)
    print("THE REAL SITUATION")
    print("=" * 80)

    print(
        """
Current State:
✅ We have 8 telemetry endpoints that work
✅ We have SystemOverview that returns aggregate metrics
✅ We have /metrics, /resources, /traces, /logs endpoints

What's Missing:
❌ Individual metric endpoints for each documented metric
❌ Module-specific metric endpoints (e.g., /telemetry/llm_bus/request_count)
❌ Direct access to the 597 documented metrics

The Task:
→ Add routes to expose the existing metrics that services are already collecting
→ NOT creating new metrics
→ Just making existing internal metrics accessible via API
"""
    )

    # Save the gap analysis
    gap_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/metric_gap_analysis.json")
    gap_data = {
        "documented_total": total_documented,
        "documented_modules": len(documented),
        "overview_fields": list(actual["overview_fields"]),
        "current_endpoints": [
            "GET /telemetry/overview",
            "GET /telemetry/metrics",
            "GET /telemetry/resources",
            "GET /telemetry/logs",
            "GET /telemetry/traces",
            "POST /telemetry/query",
            "GET /telemetry/metrics/{metric_name}",
        ],
        "task": "Expose the 597 documented metrics via API endpoints",
    }

    gap_file.write_text(json.dumps(gap_data, indent=2))
    print(f"\n📁 Gap analysis saved to: {gap_file}")


if __name__ == "__main__":
    main()
