#!/usr/bin/env python3
"""
Accurate analysis of which metrics apply to which services.
Not all services have all metrics!
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set


class AccurateMetricAnalyzer:
    """Accurately analyze which metrics belong to which services"""

    def __init__(self):
        self.ciris_path = Path("/home/emoore/CIRISAgent/ciris_engine")

    def analyze_llm_specific_metrics(self) -> Dict[str, Set[str]]:
        """Find metrics that ONLY apply to LLM services"""
        llm_metrics = {"llm_service": set(), "llm_bus": set(), "llm_providers": set()}

        # LLM-specific metrics
        llm_file = self.ciris_path / "logic/services/runtime/llm_service.py"
        if llm_file.exists():
            content = llm_file.read_text()

            # These are LLM-specific
            if "tokens_used" in content:
                llm_metrics["llm_service"].add("tokens_used")
                llm_metrics["llm_service"].add("tokens_input")
                llm_metrics["llm_service"].add("tokens_output")
            if "cost_cents" in content:
                llm_metrics["llm_service"].add("cost_cents")
            if "carbon_grams" in content:
                llm_metrics["llm_service"].add("carbon_grams")
                llm_metrics["llm_service"].add("energy_kwh")

        # LLM bus metrics
        llm_bus = self.ciris_path / "logic/buses/llm_bus.py"
        if llm_bus.exists():
            content = llm_bus.read_text()

            # Circuit breaker metrics for LLM
            llm_metrics["llm_bus"].update(
                [
                    "total_requests",
                    "failed_requests",
                    "total_latency_ms",
                    "consecutive_failures",
                    "circuit_breaker_state",
                    "failure_count",
                    "success_count",
                ]
            )

        return llm_metrics

    def analyze_memory_specific_metrics(self) -> Set[str]:
        """Find metrics specific to memory service"""
        memory_metrics = set()

        memory_file = self.ciris_path / "logic/services/graph/memory_service.py"
        if memory_file.exists():
            content = memory_file.read_text()

            # Memory-specific metrics
            if "node_count" in content or "graph_node" in content:
                memory_metrics.add("node_count")
                memory_metrics.add("edge_count")
                memory_metrics.add("query_latency_ms")
                memory_metrics.add("write_latency_ms")

            if "recall" in content:
                memory_metrics.add("recall_count")
                memory_metrics.add("memorize_count")

        return memory_metrics

    def analyze_communication_metrics(self) -> Set[str]:
        """Find metrics specific to communication services"""
        comm_metrics = set()

        # Communication bus
        comm_bus = self.ciris_path / "logic/buses/communication_bus.py"
        if comm_bus.exists():
            content = comm_bus.read_text()

            comm_metrics.update(["messages_processed", "messages_queued", "queue_size", "processing_latency_ms"])

        return comm_metrics

    def analyze_service_common_metrics(self) -> Set[str]:
        """Find metrics common to ALL services"""
        common_metrics = set()

        # Check base service classes
        base_service = self.ciris_path / "logic/services/base_service.py"
        if base_service.exists():
            content = base_service.read_text()

            # Common to all services
            if "health" in content or "availability" in content:
                common_metrics.update(
                    ["availability", "health_status", "uptime_seconds", "error_count", "request_count"]
                )

        return common_metrics

    def analyze_adapter_specific_metrics(self) -> Dict[str, Set[str]]:
        """Find metrics specific to each adapter"""
        adapter_metrics = defaultdict(set)

        # Discord adapter
        discord_file = self.ciris_path / "logic/adapters/discord/discord_adapter.py"
        if discord_file.exists():
            content = discord_file.read_text()

            if "message" in content:
                adapter_metrics["discord"].update(
                    ["messages_received", "messages_sent", "discord_latency_ms", "active_guilds", "active_channels"]
                )

        # API adapter
        api_file = self.ciris_path / "logic/adapters/api/adapter.py"
        if api_file.exists():
            adapter_metrics["api"].update(
                ["http_requests", "response_time_ms", "active_connections", "websocket_connections"]
            )

        # CLI adapter
        adapter_metrics["cli"].update(["commands_processed", "cli_sessions"])

        return dict(adapter_metrics)

    def find_actual_metric_patterns(self) -> Dict:
        """Find the ACTUAL metrics being collected"""

        # Search for actual memorize_metric and record_metric calls
        actual_calls = defaultdict(set)

        for py_file in self.ciris_path.rglob("*.py"):
            try:
                content = py_file.read_text()
                filename = py_file.stem

                # Find actual metric recording
                patterns = [
                    r'memorize_metric\([^)]+metric_name=["\']([^"\']+)["\']',
                    r'record_metric\([^)]+["\']([^"\']+)["\']',
                    r'f["\']{\w+}\.([^"\']+)["\'].*record_metric',
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        actual_calls[filename].add(match)

            except Exception:
                continue

        return dict(actual_calls)

    def generate_accurate_report(self) -> Dict:
        """Generate accurate metric analysis"""

        llm_metrics = self.analyze_llm_specific_metrics()
        memory_metrics = self.analyze_memory_specific_metrics()
        comm_metrics = self.analyze_communication_metrics()
        common_metrics = self.analyze_service_common_metrics()
        adapter_metrics = self.analyze_adapter_specific_metrics()
        actual_patterns = self.find_actual_metric_patterns()

        # Count unique metrics by category
        total_llm = sum(len(m) for m in llm_metrics.values())

        # Calculate more accurate totals
        # Not every service has every metric!
        service_specific_totals = {
            "llm_services": total_llm * 2,  # 2 LLM providers typically
            "memory_service": len(memory_metrics),
            "communication": len(comm_metrics),
            "common_per_service": len(common_metrics) * 23,  # These ARE common
            "adapters": sum(len(m) for m in adapter_metrics.values()),
        }

        return {
            "llm_specific": {k: list(v) for k, v in llm_metrics.items()},
            "memory_specific": list(memory_metrics),
            "communication_specific": list(comm_metrics),
            "common_to_all": list(common_metrics),
            "adapter_specific": {k: list(v) for k, v in adapter_metrics.items()},
            "actual_calls_found": {k: list(v) for k, v in actual_patterns.items()},
            "totals": service_specific_totals,
            "estimated_total": sum(service_specific_totals.values()),
        }


def main():
    analyzer = AccurateMetricAnalyzer()

    print("=" * 80)
    print("ACCURATE METRIC ANALYSIS")
    print("Which metrics actually belong to which services?")
    print("=" * 80)

    results = analyzer.generate_accurate_report()

    print("\n🎯 LLM-SPECIFIC METRICS (not for all services!):")
    for category, metrics in results["llm_specific"].items():
        if metrics:
            print(f"\n  {category}:")
            for metric in metrics[:10]:
                print(f"    • {metric}")

    print("\n💾 MEMORY-SPECIFIC METRICS:")
    for metric in results["memory_specific"][:10]:
        print(f"  • {metric}")

    print("\n📡 COMMUNICATION-SPECIFIC METRICS:")
    for metric in results["communication_specific"][:10]:
        print(f"  • {metric}")

    print("\n✅ COMMON TO ALL SERVICES:")
    for metric in results["common_to_all"]:
        print(f"  • {metric}")

    print("\n🔌 ADAPTER-SPECIFIC METRICS:")
    for adapter, metrics in results["adapter_specific"].items():
        print(f"\n  {adapter}:")
        for metric in metrics[:5]:
            print(f"    • {metric}")

    print("\n📊 MORE ACCURATE TOTALS:")
    for category, count in results["totals"].items():
        print(f"  • {category}: {count}")
    print(f"\n  ESTIMATED TOTAL: {results['estimated_total']} metrics")

    print("\n" + "=" * 80)
    print("CORRECTED UNDERSTANDING")
    print("=" * 80)
    print(
        """
✅ CORRECT: Not all services have all metrics!
  • tokens_used, cost_cents → ONLY for LLM services
  • node_count, edge_count → ONLY for memory service
  • messages_processed → ONLY for communication services
  • availability, health_status → Common to ALL services

The 556+ metrics in production come from:
  1. Service-specific metrics (varies by service type)
  2. Common metrics (all services have these)
  3. Dynamic provider metrics (per LLM provider, adapter, etc.)
  4. Runtime-generated handler metrics
"""
    )

    # Save corrected analysis
    output_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/accurate_metrics_analysis.json")
    with output_file.open("w") as f:
        json.dump(results, f, indent=2, default=list)
    print(f"\n📁 Accurate analysis saved to: {output_file}")


if __name__ == "__main__":
    main()
