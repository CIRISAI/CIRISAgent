#!/usr/bin/env python3
"""
Track which metrics from the .md documentation are exposed via the API
This is about making existing metrics queryable, not creating new ones
"""

import json
from pathlib import Path
from typing import Dict, List, Set

from core.doc_parser import TelemetryDocParser


class MetricExposureTracker:
    """Track which documented metrics are exposed via API"""

    def __init__(self):
        self.parser = TelemetryDocParser()
        self.docs_path = Path("/home/emoore/CIRISAgent/ciris_engine/docs/telemetry")

    def get_all_documented_metrics(self) -> Dict[str, List[Dict]]:
        """Get all metrics from documentation"""
        modules = self.parser.parse_all_docs()

        metrics_by_module = {}
        for module in modules:
            module_name = module["module_name"]
            metrics = []

            for m in module.get("metrics", []):
                metric_info = {
                    "name": m.get("metric_name", ""),
                    "type": m.get("metric_type", ""),
                    "access": m.get("access_pattern", ""),
                    "storage": m.get("storage_location", ""),
                }
                if metric_info["name"]:
                    metrics.append(metric_info)

            metrics_by_module[module_name] = metrics

        return metrics_by_module

    def check_metric_queryability(self, metric_name: str) -> Dict:
        """
        Check if a metric can be queried via /telemetry/metrics/{metric_name}

        For a metric to be queryable, it needs:
        1. To be collected by a service
        2. To be stored in telemetry service or graph
        3. To have a name that the telemetry service recognizes
        """

        # The telemetry service needs to have this metric registered
        # This would require checking if the service actually collects it

        return {
            "metric_name": metric_name,
            "queryable": False,  # Default to not queryable
            "reason": "Not yet registered with telemetry service",
            "endpoint": f"/v1/telemetry/metrics/{metric_name}",
        }

    def generate_implementation_plan(self) -> Dict:
        """Generate plan for exposing documented metrics"""

        all_metrics = self.get_all_documented_metrics()

        # Count metrics by type and access pattern
        metric_stats = {"total": 0, "by_type": {}, "by_access": {}, "by_module": {}}

        implementation_tasks = []

        for module_name, metrics in all_metrics.items():
            metric_stats["by_module"][module_name] = len(metrics)

            for metric in metrics:
                metric_stats["total"] += 1

                # Count by type
                m_type = metric["type"]
                metric_stats["by_type"][m_type] = metric_stats["by_type"].get(m_type, 0) + 1

                # Count by access pattern
                access = metric["access"]
                metric_stats["by_access"][access] = metric_stats["by_access"].get(access, 0) + 1

                # Create implementation task
                task = {
                    "module": module_name,
                    "metric": metric["name"],
                    "type": metric["type"],
                    "task": f"Register {metric['name']} with telemetry service",
                    "endpoint": f"/v1/telemetry/metrics/{metric['name']}",
                    "priority": "HIGH" if access == "HOT" else "MEDIUM" if access == "WARM" else "LOW",
                }
                implementation_tasks.append(task)

        # Sort tasks by priority
        priority_order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
        implementation_tasks.sort(key=lambda x: priority_order.get(x["priority"], 3))

        return {
            "statistics": metric_stats,
            "tasks": implementation_tasks[:20],  # Top 20 tasks
            "total_tasks": len(implementation_tasks),
        }


def main():
    """Main tracking function"""

    tracker = MetricExposureTracker()

    print("=" * 80)
    print("METRIC EXPOSURE TRACKING")
    print("Making documented metrics queryable via API")
    print("=" * 80)

    # Get all documented metrics
    all_metrics = tracker.get_all_documented_metrics()

    # Generate implementation plan
    plan = tracker.generate_implementation_plan()

    print(f"\n📊 DOCUMENTED METRICS:")
    print(f"  Total: {plan['statistics']['total']} metrics")
    print(f"  Modules: {len(plan['statistics']['by_module'])}")

    print(f"\n📈 BY TYPE:")
    for m_type, count in plan["statistics"]["by_type"].items():
        print(f"  • {m_type}: {count}")

    print(f"\n🔥 BY ACCESS PATTERN:")
    for access, count in plan["statistics"]["by_access"].items():
        print(f"  • {access}: {count}")

    print(f"\n📦 TOP MODULES BY METRIC COUNT:")
    sorted_modules = sorted(plan["statistics"]["by_module"].items(), key=lambda x: x[1], reverse=True)
    for module, count in sorted_modules[:10]:
        print(f"  • {module}: {count} metrics")

    print("\n" + "=" * 80)
    print("IMPLEMENTATION PLAN")
    print("To expose metrics via /telemetry/metrics/{metric_name}")
    print("=" * 80)

    print(f"\n🎯 TOP PRIORITY METRICS TO EXPOSE:")
    for i, task in enumerate(plan["tasks"][:10], 1):
        print(f"\n{i}. [{task['priority']}] {task['module']} - {task['metric']}")
        print(f"   Type: {task['type']}")
        print(f"   Endpoint: {task['endpoint']}")
        print(f"   Task: {task['task']}")

    print(f"\n📋 Total implementation tasks: {plan['total_tasks']}")

    # The key insight
    print("\n" + "=" * 80)
    print("KEY INSIGHT")
    print("=" * 80)

    print(
        """
Current State:
✅ /telemetry/metrics/{metric_name} endpoint EXISTS
✅ Telemetry service EXISTS and is running
❌ Individual metrics are NOT registered/queryable

What needs to happen:
1. Each service needs to register its metrics with telemetry service
2. Telemetry service needs a registry of available metrics
3. The /metrics/{metric_name} endpoint needs to query this registry

This is NOT about creating new metrics!
It's about making the existing internal metrics queryable via the API.
"""
    )

    # Save the plan
    plan_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/metric_exposure_plan.json")
    plan_file.write_text(json.dumps(plan, indent=2))
    print(f"\n📁 Implementation plan saved to: {plan_file}")


if __name__ == "__main__":
    main()
