#!/usr/bin/env python3
"""
Complete module-by-module metric analysis
Finds ALL metrics in docs vs code for every module
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple

from core.doc_parser import TelemetryDocParser


class CompleteMetricAnalysis:
    """Complete analysis of all metrics across all modules"""

    def __init__(self):
        self.ciris_path = Path("/home/emoore/CIRISAgent/ciris_engine")
        self.parser = TelemetryDocParser()
        self.documented_metrics = self.get_documented_metrics()

    def get_documented_metrics(self) -> Dict[str, Set[str]]:
        """Get all metrics from .md documentation"""
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

    def find_metrics_in_file(self, file_path: Path) -> Set[str]:
        """Find metrics in a specific file"""
        metrics = set()

        if not file_path.exists():
            return metrics

        content = file_path.read_text()

        # Common metric patterns
        patterns = [
            # Direct metric names
            r'["\'](\w+_count)["\']',
            r'["\'](\w+_total)["\']',
            r'["\'](\w+_rate)["\']',
            r'["\'](\w+_latency)["\']',
            r'["\'](\w+_latency_ms)["\']',
            r'["\'](\w+_seconds)["\']',
            r'["\'](\w+_errors?)["\']',
            # Metric recording
            r'record_metric\(["\']([^"\']+)["\']',
            r'memorize_metric\([^)]*metric_name=["\']([^"\']+)["\']',
            # Metric fields
            r"self\.(\w+_count)\s*=",
            r"self\.(\w+_total)\s*=",
            r"self\._(\w+_count)\s*=",
            r"self\._(\w+_total)\s*=",
            # Common metric names
            r"(uptime_seconds|error_count|request_count|error_rate|healthy)",
            r"(availability|health_status|circuit_breaker_state)",
            r"(tokens_used|tokens_input|tokens_output|cost_cents|carbon_grams|energy_kwh)",
            r"(queue_size|processed|failed|running)",
            r"(node_count|edge_count|graph_node_count)",
            r"(consecutive_failures|failure_count|success_count)",
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.IGNORECASE)
            metrics.update(matches)

        # Clean up metrics - remove generic ones
        cleaned = set()
        for m in metrics:
            if len(m) > 2 and not m.startswith("_"):
                cleaned.add(m)

        return cleaned

    def analyze_buses(self) -> Dict[str, Dict]:
        """Analyze all bus modules"""
        results = {}

        bus_mapping = {
            "LLM_BUS": "logic/buses/llm_bus.py",
            "MEMORY_BUS": "logic/buses/memory_bus.py",
            "COMMUNICATION_BUS": "logic/buses/communication_bus.py",
            "WISE_BUS": "logic/buses/wise_bus.py",
            "TOOL_BUS": "logic/buses/tool_bus.py",
            "RUNTIME_CONTROL_BUS": "logic/buses/runtime_control_bus.py",
        }

        # Also check base_bus.py for common metrics
        base_bus = self.ciris_path / "logic/buses/base_bus.py"
        base_metrics = self.find_metrics_in_file(base_bus)

        for module_name, file_path in bus_mapping.items():
            full_path = self.ciris_path / file_path
            actual_metrics = self.find_metrics_in_file(full_path)

            # Buses inherit from base_bus
            if module_name in ["COMMUNICATION_BUS", "WISE_BUS"]:
                actual_metrics.update(base_metrics)

            documented = self.documented_metrics.get(module_name, set())

            results[module_name] = self.compare_metrics(module_name, documented, actual_metrics)

        return results

    def analyze_services(self) -> Dict[str, Dict]:
        """Analyze all service modules"""
        results = {}

        # Service file mappings
        service_mapping = {
            # Graph services
            "MEMORY_SERVICE": "logic/services/graph/memory_service.py",
            "CONFIG_SERVICE": "logic/services/graph/config_service.py",
            "TELEMETRY_SERVICE": "logic/services/graph/telemetry_service.py",
            "AUDIT_SERVICE": "logic/services/graph/audit_service.py",
            "INCIDENT_SERVICE": "logic/services/graph/incident_service.py",
            "TSDB_CONSOLIDATION_SERVICE": "logic/services/graph/tsdb_consolidation/service.py",
            # Infrastructure services
            "TIME_SERVICE": "logic/services/infrastructure/time_service.py",
            "SHUTDOWN_SERVICE": "logic/services/lifecycle/shutdown.py",
            "INITIALIZATION_SERVICE": "logic/services/lifecycle/initialization.py",
            "AUTHENTICATION_SERVICE": "logic/services/infrastructure/authentication.py",
            "RESOURCE_MONITOR_SERVICE": "logic/services/infrastructure/resource_monitor_service.py",
            "DATABASE_MAINTENANCE_SERVICE": "logic/services/infrastructure/database_maintenance.py",
            "SECRETS_SERVICE": "logic/services/infrastructure/secrets.py",
            # Governance services
            "WISE_AUTHORITY_SERVICE": "logic/services/governance/wise_authority.py",
            "ADAPTIVE_FILTER_SERVICE": "logic/services/governance/filter.py",
            "VISIBILITY_SERVICE": "logic/services/governance/visibility.py",
            "SELF_OBSERVATION_SERVICE": "logic/services/adaptation/self_observation.py",
            # Runtime services
            "LLM_SERVICE": "logic/services/runtime/llm_service.py",
            "RUNTIME_CONTROL_SERVICE": "logic/services/runtime/control_service.py",
            "TASK_SCHEDULER_SERVICE": "logic/services/runtime/task_scheduler.py",
            # Tool services
            "SECRETS_TOOL_SERVICE": "logic/services/tools/secrets_tool.py",
        }

        # Check base service for common metrics
        base_service = self.ciris_path / "logic/services/base_service.py"
        base_metrics = self.find_metrics_in_file(base_service)

        for module_name, file_path in service_mapping.items():
            full_path = self.ciris_path / file_path
            actual_metrics = self.find_metrics_in_file(full_path)

            # All services inherit base metrics
            actual_metrics.update(base_metrics)

            documented = self.documented_metrics.get(module_name, set())

            results[module_name] = self.compare_metrics(module_name, documented, actual_metrics)

        return results

    def analyze_components(self) -> Dict[str, Dict]:
        """Analyze component modules"""
        results = {}

        component_mapping = {
            "CIRCUIT_BREAKER_COMPONENT": "logic/infrastructure/circuit_breaker.py",
            "PROCESSING_QUEUE_COMPONENT": "logic/infrastructure/processing_queue.py",
            "SERVICE_REGISTRY_REGISTRY": "logic/registries/service_registry.py",
            "SERVICE_INITIALIZER_COMPONENT": "logic/infrastructure/service_initializer.py",
            "AGENT_PROCESSOR_PROCESSOR": "logic/processors/core/main_processor.py",
        }

        for module_name, file_path in component_mapping.items():
            full_path = self.ciris_path / file_path
            actual_metrics = self.find_metrics_in_file(full_path)

            documented = self.documented_metrics.get(module_name, set())

            results[module_name] = self.compare_metrics(module_name, documented, actual_metrics)

        return results

    def analyze_adapters(self) -> Dict[str, Dict]:
        """Analyze adapter modules"""
        results = {}

        adapter_mapping = {
            "DISCORD_ADAPTER": "logic/adapters/discord/discord_adapter.py",
            "API_ADAPTER": "logic/adapters/api/adapter.py",
            "CLI_ADAPTER": "logic/adapters/cli/cli_adapter.py",
        }

        for module_name, file_path in adapter_mapping.items():
            full_path = self.ciris_path / file_path
            actual_metrics = self.find_metrics_in_file(full_path)

            documented = self.documented_metrics.get(module_name, set())

            results[module_name] = self.compare_metrics(module_name, documented, actual_metrics)

        return results

    def compare_metrics(self, module_name: str, documented: Set[str], actual: Set[str]) -> Dict:
        """Compare documented vs actual metrics"""

        in_both = documented & actual
        only_docs = documented - actual
        only_code = actual - documented

        return {
            "module": module_name,
            "documented_count": len(documented),
            "actual_count": len(actual),
            "in_both_count": len(in_both),
            "only_docs_count": len(only_docs),
            "only_code_count": len(only_code),
            "match_percentage": len(in_both) / len(documented) * 100 if documented else 0,
            "in_both": sorted(list(in_both)),
            "only_in_docs": sorted(list(only_docs)),
            "only_in_code": sorted(list(only_code)),
        }

    def run_complete_analysis(self) -> Dict:
        """Run analysis for all modules"""

        all_results = {}

        print("Analyzing buses...")
        bus_results = self.analyze_buses()
        all_results.update(bus_results)

        print("Analyzing services...")
        service_results = self.analyze_services()
        all_results.update(service_results)

        print("Analyzing components...")
        component_results = self.analyze_components()
        all_results.update(component_results)

        print("Analyzing adapters...")
        adapter_results = self.analyze_adapters()
        all_results.update(adapter_results)

        return all_results


def main():
    """Run complete metric analysis"""
    analyzer = CompleteMetricAnalysis()

    print("=" * 80)
    print("COMPLETE MODULE-BY-MODULE METRIC ANALYSIS")
    print("=" * 80)

    results = analyzer.run_complete_analysis()

    # Calculate totals
    total_documented = 0
    total_actual = 0
    total_matched = 0

    # Summary by category
    categories = {
        "Buses": ["LLM_BUS", "MEMORY_BUS", "COMMUNICATION_BUS", "WISE_BUS", "TOOL_BUS", "RUNTIME_CONTROL_BUS"],
        "Graph Services": [
            "MEMORY_SERVICE",
            "CONFIG_SERVICE",
            "TELEMETRY_SERVICE",
            "AUDIT_SERVICE",
            "INCIDENT_SERVICE",
            "TSDB_CONSOLIDATION_SERVICE",
        ],
        "Infrastructure": [
            "TIME_SERVICE",
            "SHUTDOWN_SERVICE",
            "INITIALIZATION_SERVICE",
            "AUTHENTICATION_SERVICE",
            "RESOURCE_MONITOR_SERVICE",
            "DATABASE_MAINTENANCE_SERVICE",
            "SECRETS_SERVICE",
        ],
        "Governance": [
            "WISE_AUTHORITY_SERVICE",
            "ADAPTIVE_FILTER_SERVICE",
            "VISIBILITY_SERVICE",
            "SELF_OBSERVATION_SERVICE",
        ],
        "Runtime": ["LLM_SERVICE", "RUNTIME_CONTROL_SERVICE", "TASK_SCHEDULER_SERVICE"],
        "Components": [
            "CIRCUIT_BREAKER_COMPONENT",
            "PROCESSING_QUEUE_COMPONENT",
            "SERVICE_REGISTRY_REGISTRY",
            "SERVICE_INITIALIZER_COMPONENT",
            "AGENT_PROCESSOR_PROCESSOR",
        ],
        "Adapters": ["DISCORD_ADAPTER", "API_ADAPTER", "CLI_ADAPTER"],
    }

    for category, modules in categories.items():
        print(f"\n📦 {category}")
        print("-" * 60)

        for module_name in modules:
            if module_name in results:
                r = results[module_name]
                total_documented += r["documented_count"]
                total_actual += r["actual_count"]
                total_matched += r["in_both_count"]

                status = "✅" if r["match_percentage"] >= 80 else "⚠️" if r["match_percentage"] >= 40 else "❌"

                print(
                    f"{status} {module_name:30} Doc:{r['documented_count']:3} Code:{r['actual_count']:3} "
                    f"Match:{r['in_both_count']:3} ({r['match_percentage']:.0f}%)"
                )

                if r["only_docs_count"] > 0:
                    print(
                        f"   📝 Missing in code: {', '.join(r['only_in_docs'][:3])}"
                        f"{' ...' if r['only_docs_count'] > 3 else ''}"
                    )

                if r["only_code_count"] > 0:
                    print(
                        f"   💻 Missing in docs: {', '.join(r['only_in_code'][:3])}"
                        f"{' ...' if r['only_code_count'] > 3 else ''}"
                    )

    print("\n" + "=" * 80)
    print("TOTALS")
    print("=" * 80)
    print(f"📚 Total Documented: {total_documented}")
    print(f"💻 Total in Code: {total_actual}")
    print(f"✅ Total Matched: {total_matched}")
    print(f"📊 Overall Match Rate: {total_matched/total_documented*100:.1f}%")

    # Save detailed results
    output_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/complete_metric_analysis.json")
    with output_file.open("w") as f:
        json.dump(results, f, indent=2)

    print(f"\n📁 Detailed results saved to: {output_file}")


if __name__ == "__main__":
    main()
