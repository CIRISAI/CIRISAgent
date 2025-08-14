#!/usr/bin/env python3
"""
Service-by-service metric comparison tool
Shows exactly what's in docs vs what's in code for each service
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

from core.doc_parser import TelemetryDocParser


class ServiceMetricComparison:
    """Compare documented vs actual metrics service by service"""

    def __init__(self):
        self.ciris_path = Path("/home/emoore/CIRISAgent/ciris_engine")
        self.parser = TelemetryDocParser()

    def get_documented_metrics(self) -> Dict[str, Set[str]]:
        """Get metrics from .md documentation"""
        modules = self.parser.parse_all_docs()

        metrics_by_module = {}
        for module in modules:
            module_name = module["module_name"]
            metrics = set()

            for metric in module.get("metrics", []):
                metric_name = metric.get("metric_name", "")
                if metric_name:
                    metrics.add(metric_name)

            metrics_by_module[module_name] = metrics

        return metrics_by_module

    def find_llm_bus_metrics(self) -> Set[str]:
        """Find actual metrics in LLM bus code"""
        metrics = set()

        llm_bus = self.ciris_path / "logic/buses/llm_bus.py"
        if llm_bus.exists():
            content = llm_bus.read_text()

            # Find ServiceMetrics dataclass fields
            if "class ServiceMetrics" in content:
                # These are the actual metrics tracked
                metrics.update(
                    [
                        "total_requests",
                        "failed_requests",
                        "total_latency_ms",
                        "consecutive_failures",
                        "last_request_time",
                        "last_failure_time",
                    ]
                )

            # Find circuit breaker metrics
            if "circuit_breaker" in content.lower():
                metrics.update(["circuit_breaker_state", "failure_count", "success_count"])

            # Find telemetry recording calls
            telemetry_patterns = [
                r'record_metric\(["\']([^"\']+)["\']',
                r'"llm\.([^"]+)"',  # llm.tokens.total etc
            ]

            for pattern in telemetry_patterns:
                matches = re.findall(pattern, content)
                for match in matches:
                    if "tokens" in match:
                        metrics.update(["tokens_used", "tokens_input", "tokens_output"])
                    elif "cost" in match:
                        metrics.add("cost_cents")
                    elif "carbon" in match:
                        metrics.add("carbon_grams")
                    elif "energy" in match:
                        metrics.add("energy_kwh")
                    elif "latency" in match:
                        metrics.add("latency_ms")

            # Check for average_latency_ms calculation
            if "average_latency" in content or "avg_latency" in content:
                metrics.add("average_latency_ms")

            # Check for round_robin_index
            if "round_robin" in content:
                metrics.add("round_robin_index")

        return metrics

    def find_memory_bus_metrics(self) -> Set[str]:
        """Find actual metrics in Memory bus code"""
        metrics = set()

        memory_bus = self.ciris_path / "logic/buses/memory_bus.py"
        if memory_bus.exists():
            content = memory_bus.read_text()

            # Check for service availability
            if "get_service" in content or "is_available" in content:
                metrics.add("service_availability")

            # Check for operation counting (even if implicit)
            if "memorize" in content or "recall" in content:
                # These operations happen but may not be explicitly counted
                pass  # operation_count is implicit, not explicitly tracked

        return metrics

    def find_memory_service_metrics(self) -> Set[str]:
        """Find actual metrics in Memory service code"""
        metrics = set()

        memory_service = self.ciris_path / "logic/services/graph/memory_service.py"
        if memory_service.exists():
            content = memory_service.read_text()

            # Check for node counting
            if "node_count" in content or "graph_node_count" in content:
                metrics.add("graph_node_count")

            # Check for secrets
            if "secrets_enabled" in content or "secrets_service" in content:
                metrics.add("secrets_enabled")

            # Check for storage backend
            if "storage_backend" in content or "sqlite" in content:
                metrics.add("storage_backend")

            # Base service metrics
            if "BaseService" in content or "base_service" in content:
                metrics.update(["uptime_seconds", "request_count", "error_count", "error_rate", "healthy"])

            # Graph operations (may be implicit)
            if "CREATE TABLE nodes" in content or "INSERT INTO nodes" in content:
                metrics.update(["nodes_created", "edges_created"])

            if "correlations" in content:
                metrics.add("correlations_count")

            if "time_series" in content or "TSDBGraphNode" in content:
                metrics.add("time_series_points")

            if "node_type" in content:
                metrics.add("nodes_by_type")

        return metrics

    def find_communication_bus_metrics(self) -> Set[str]:
        """Find actual metrics in Communication bus code"""
        metrics = set()

        # Check both communication_bus.py and base_bus.py
        bus_files = [self.ciris_path / "logic/buses/communication_bus.py", self.ciris_path / "logic/buses/base_bus.py"]

        for bus_file in bus_files:
            if bus_file.exists():
                content = bus_file.read_text()

                # Check for actual metric tracking
                if "_processed_count" in content or "processed_count" in content:
                    metrics.add("processed")

                if "_failed_count" in content or "failed_count" in content:
                    metrics.add("failed")

                # Queue metrics
                if "_queue" in content or "self.queue" in content:
                    if "qsize()" in content or "queue.qsize" in content:
                        metrics.add("queue_size")

                # Running state
                if "_running" in content or "self.running" in content:
                    metrics.add("running")

                # Service type
                if "service_type" in content or "ServiceType.COMMUNICATION" in content:
                    metrics.add("service_type")

        return metrics

    def compare_service(self, service_name: str, documented: Set[str], actual: Set[str]) -> Dict:
        """Compare metrics for a single service"""

        in_both = documented & actual
        only_docs = documented - actual
        only_code = actual - documented

        return {
            "service": service_name,
            "documented_count": len(documented),
            "actual_count": len(actual),
            "in_both": sorted(list(in_both)),
            "only_in_docs": sorted(list(only_docs)),
            "only_in_code": sorted(list(only_code)),
            "match_percentage": len(in_both) / len(documented) * 100 if documented else 0,
        }

    def run_comparison(self) -> List[Dict]:
        """Run comparison for key services"""

        documented = self.get_documented_metrics()
        results = []

        # LLM_BUS
        llm_bus_actual = self.find_llm_bus_metrics()
        llm_bus_docs = documented.get("LLM_BUS", set())
        results.append(self.compare_service("LLM_BUS", llm_bus_docs, llm_bus_actual))

        # MEMORY_BUS
        memory_bus_actual = self.find_memory_bus_metrics()
        memory_bus_docs = documented.get("MEMORY_BUS", set())
        results.append(self.compare_service("MEMORY_BUS", memory_bus_docs, memory_bus_actual))

        # MEMORY_SERVICE
        memory_svc_actual = self.find_memory_service_metrics()
        memory_svc_docs = documented.get("MEMORY_SERVICE", set())
        results.append(self.compare_service("MEMORY_SERVICE", memory_svc_docs, memory_svc_actual))

        # COMMUNICATION_BUS
        comm_bus_actual = self.find_communication_bus_metrics()
        comm_bus_docs = documented.get("COMMUNICATION_BUS", set())
        results.append(self.compare_service("COMMUNICATION_BUS", comm_bus_docs, comm_bus_actual))

        return results


def main():
    """Run service-by-service comparison"""
    tool = ServiceMetricComparison()

    print("=" * 80)
    print("SERVICE-BY-SERVICE METRIC COMPARISON")
    print("Documented (.md) vs Actual (code)")
    print("=" * 80)

    results = tool.run_comparison()

    for result in results:
        print(f"\n📦 {result['service']}")
        print(f"  Documented: {result['documented_count']}")
        print(f"  Actual in code: {result['actual_count']}")
        print(f"  Match: {result['match_percentage']:.1f}%")

        if result["in_both"]:
            print(f"\n  ✅ In BOTH (docs & code): {len(result['in_both'])}")
            for metric in result["in_both"][:5]:
                print(f"    • {metric}")
            if len(result["in_both"]) > 5:
                print(f"    ... and {len(result['in_both']) - 5} more")

        if result["only_in_docs"]:
            print(f"\n  📝 Only in DOCS (not in code): {len(result['only_in_docs'])}")
            for metric in result["only_in_docs"][:5]:
                print(f"    • {metric}")
            if len(result["only_in_docs"]) > 5:
                print(f"    ... and {len(result['only_in_docs']) - 5} more")

        if result["only_in_code"]:
            print(f"\n  💻 Only in CODE (not in docs): {len(result['only_in_code'])}")
            for metric in result["only_in_code"][:5]:
                print(f"    • {metric}")
            if len(result["only_in_code"]) > 5:
                print(f"    ... and {len(result['only_in_code']) - 5} more")

        print("-" * 40)

    # Save detailed results
    output_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/service_comparison_detailed.json")
    with output_file.open("w") as f:
        json.dump(results, f, indent=2)

    print(f"\n📁 Detailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
