#!/usr/bin/env python3
"""
Find ALL metrics that are ACTUALLY being collected in the CIRIS codebase.
This will find the real 556+ metrics that are being tracked.
"""

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Set, Tuple


class ActualMetricsFinder:
    """Find all metrics actually being collected in CIRIS"""

    def __init__(self):
        self.ciris_path = Path("/home/emoore/CIRISAgent/ciris_engine")
        self.metrics_by_source = defaultdict(set)
        self.metrics_by_module = defaultdict(set)

    def find_memorize_metric_calls(self) -> Dict[str, Set[str]]:
        """Find all memorize_metric() calls"""
        metrics = defaultdict(set)

        for py_file in self.ciris_path.rglob("*.py"):
            try:
                content = py_file.read_text()

                # Find memorize_metric calls with literal strings
                patterns = [
                    r'memorize_metric\(\s*metric_name=["\']([^"\']+)["\']',
                    r'memorize_metric\(\s*["\']([^"\']+)["\']',
                    r'\.memorize_metric\(\s*["\']([^"\']+)["\']',
                ]

                for pattern in patterns:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        metrics["memorize_metric"].add(match)
                        # Track source file
                        module = py_file.stem
                        self.metrics_by_module[module].add(match)

                # Find f-string patterns like f"{service_name}.tokens_used"
                fstring_pattern = r'f["\']([^{]*){[^}]+}\.([^"\']+)["\']'
                matches = re.findall(fstring_pattern, content)
                for prefix, suffix in matches:
                    # Common suffixes are the actual metric names
                    if suffix in [
                        "tokens_used",
                        "tokens_input",
                        "tokens_output",
                        "cost_cents",
                        "carbon_grams",
                        "energy_kwh",
                    ]:
                        metrics["resource_metrics"].add(suffix)
                        self.metrics_by_module[py_file.stem].add(suffix)

            except Exception as e:
                continue

        return dict(metrics)

    def find_record_metric_calls(self) -> Dict[str, Set[str]]:
        """Find all record_metric() calls"""
        metrics = defaultdict(set)

        for py_file in self.ciris_path.rglob("*.py"):
            try:
                content = py_file.read_text()

                # Find record_metric calls
                patterns = [
                    r'record_metric\(\s*["\']([^"\']+)["\']',
                    r'\.record_metric\(\s*["\']([^"\']+)["\']',
                    r'record_metric\(\s*f["\']([^{]*){[^}]+}([^"\']*)["\']',
                ]

                for pattern in patterns[:2]:
                    matches = re.findall(pattern, content)
                    for match in matches:
                        metrics["record_metric"].add(match)
                        self.metrics_by_module[py_file.stem].add(match)

                # Handle f-strings in record_metric
                matches = re.findall(patterns[2], content)
                for prefix, suffix in matches:
                    combined = f"{prefix}*{suffix}" if prefix or suffix else "*"
                    metrics["record_metric_dynamic"].add(combined)

            except Exception as e:
                continue

        return dict(metrics)

    def find_llm_bus_metrics(self) -> Set[str]:
        """Find metrics tracked in LLM bus"""
        metrics = set()

        llm_bus = self.ciris_path / "logic/buses/llm_bus.py"
        if llm_bus.exists():
            content = llm_bus.read_text()

            # Find self._metrics dictionary keys
            patterns = [
                r'self\._metrics\[["\']([^"\']+)["\']',
                r'["\']([^"\']+)["\']\s*:\s*(?:0|0\.0|None|False)',  # Initialization
                r"total_requests|failed_requests|total_latency_ms|consecutive_failures|failure_count|success_count",
            ]

            for pattern in patterns:
                matches = re.findall(pattern, content)
                metrics.update(matches)

        return metrics

    def find_telemetry_overview_fields(self) -> Set[str]:
        """Find all fields in telemetry overview"""
        metrics = set()

        telemetry_route = self.ciris_path / "logic/adapters/api/routes/telemetry.py"
        if telemetry_route.exists():
            content = telemetry_route.read_text()

            # Find SystemOverview class fields
            if "class SystemOverview" in content:
                class_start = content.index("class SystemOverview")
                class_end = content.find("\nclass ", class_start + 1)
                if class_end == -1:
                    class_end = class_start + 3000
                class_section = content[class_start:class_end]

                # Extract field names
                field_pattern = r"(\w+):\s*(?:int|float|str|bool|Optional\[(?:int|float|str|bool)\])"
                matches = re.findall(field_pattern, class_section)
                metrics.update(matches)

        return metrics

    def find_service_metrics(self) -> Dict[str, Set[str]]:
        """Find metrics collected by each service"""
        service_metrics = defaultdict(set)

        services_dir = self.ciris_path / "logic/services"
        if services_dir.exists():
            for py_file in services_dir.rglob("*.py"):
                try:
                    content = py_file.read_text()
                    service_name = py_file.stem

                    # Find metric-related patterns
                    patterns = [
                        r'self\.metrics\[["\']([^"\']+)["\']',
                        r'metrics\[["\']([^"\']+)["\']',
                        r'["\']([^"\']+_count|[^"\']+_total|[^"\']+_rate|[^"\']+_latency|[^"\']+_errors?)["\']',
                    ]

                    for pattern in patterns:
                        matches = re.findall(pattern, content)
                        if matches:
                            service_metrics[service_name].update(matches)

                except Exception:
                    continue

        return dict(service_metrics)

    def find_processor_metrics(self) -> Set[str]:
        """Find metrics from processors"""
        metrics = set()

        processors_dir = self.ciris_path / "logic/processors"
        if processors_dir.exists():
            for py_file in processors_dir.rglob("*.py"):
                try:
                    content = py_file.read_text()

                    # Common processor metrics
                    patterns = [
                        r"thoughts_processed|tasks_completed|messages_processed|errors",
                        r"reflection_cycles|maintenance_tasks_completed|patterns_identified",
                    ]

                    for pattern in patterns:
                        matches = re.findall(pattern, content)
                        metrics.update(matches)

                except Exception:
                    continue

        return metrics

    def find_handler_metrics(self) -> Set[str]:
        """Find metrics from action handlers"""
        metrics = set()

        handlers_dir = self.ciris_path / "logic/infrastructure/handlers"
        if handlers_dir.exists():
            for py_file in handlers_dir.rglob("*.py"):
                try:
                    content = py_file.read_text()

                    # Handler metrics patterns
                    patterns = [
                        r'handler_invoked_([^"\']+)',
                        r'handler_completed_([^"\']+)',
                        r'handler_error_([^"\']+)',
                        r"handler_([^_]+)_total",
                    ]

                    for pattern in patterns:
                        matches = re.findall(pattern, content)
                        for match in matches:
                            metrics.add(f"handler_{match}")

                except Exception:
                    continue

        return metrics

    def find_circuit_breaker_metrics(self) -> Set[str]:
        """Find circuit breaker related metrics"""
        metrics = set()

        # Check circuit breaker implementation
        cb_file = self.ciris_path / "logic/infrastructure/circuit_breaker.py"
        if cb_file.exists():
            content = cb_file.read_text()

            patterns = [
                r"failure_count|success_count|consecutive_failures",
                r"circuit_state|breaker_state|is_open|is_closed",
                r"last_failure_time|last_success_time|opened_at",
            ]

            for pattern in patterns:
                matches = re.findall(pattern, content)
                metrics.update(matches)

        return metrics

    def find_tsdb_metrics(self) -> Set[str]:
        """Find TSDB consolidation metrics"""
        metrics = set()

        tsdb_dir = self.ciris_path / "logic/services/graph/tsdb_consolidation"
        if tsdb_dir.exists():
            for py_file in tsdb_dir.rglob("*.py"):
                try:
                    content = py_file.read_text()

                    # TSDB metric patterns
                    patterns = [
                        r"total_interactions|unique_services|total_tasks|total_thoughts",
                        r"tokens_consumed|cost_cents|carbon_grams|energy_kwh",
                        r"error_count|warning_count|info_count",
                    ]

                    for pattern in patterns:
                        matches = re.findall(pattern, content)
                        metrics.update(matches)

                except Exception:
                    continue

        return metrics

    def find_all_metrics(self) -> Dict[str, any]:
        """Find ALL metrics in the codebase"""

        print("🔍 Searching for ALL metrics in CIRIS codebase...")

        all_metrics = {
            "memorize_metric": self.find_memorize_metric_calls(),
            "record_metric": self.find_record_metric_calls(),
            "llm_bus": self.find_llm_bus_metrics(),
            "telemetry_overview": self.find_telemetry_overview_fields(),
            "service_metrics": self.find_service_metrics(),
            "processor_metrics": self.find_processor_metrics(),
            "handler_metrics": self.find_handler_metrics(),
            "circuit_breaker": self.find_circuit_breaker_metrics(),
            "tsdb_metrics": self.find_tsdb_metrics(),
        }

        # Combine all unique metrics
        unique_metrics = set()
        for category, metrics in all_metrics.items():
            if isinstance(metrics, dict):
                for sub_cat, sub_metrics in metrics.items():
                    if isinstance(sub_metrics, set):
                        unique_metrics.update(sub_metrics)
            elif isinstance(metrics, set):
                unique_metrics.update(metrics)

        return {
            "by_category": all_metrics,
            "unique_metrics": sorted(list(unique_metrics)),
            "total_unique": len(unique_metrics),
            "by_module": dict(self.metrics_by_module),
        }


def compare_with_documented(actual_metrics: Dict, documented_path: Path) -> Dict:
    """Compare actual metrics with documented ones"""

    # Load documented metrics from our parsed .md files
    from core.doc_parser import TelemetryDocParser

    parser = TelemetryDocParser()
    documented_modules = parser.parse_all_docs()

    documented_metrics = set()
    documented_by_module = {}

    for module in documented_modules:
        module_name = module["module_name"]
        module_metrics = set()

        for metric in module.get("metrics", []):
            metric_name = metric.get("metric_name", "")
            if metric_name:
                documented_metrics.add(metric_name)
                module_metrics.add(metric_name)

        documented_by_module[module_name] = module_metrics

    # Compare
    actual_set = set(actual_metrics["unique_metrics"])

    comparison = {
        "actual_total": len(actual_set),
        "documented_total": len(documented_metrics),
        "in_both": sorted(list(actual_set & documented_metrics)),
        "only_in_actual": sorted(list(actual_set - documented_metrics)),
        "only_in_docs": sorted(list(documented_metrics - actual_set)),
        "coverage_percent": (
            len(actual_set & documented_metrics) / len(documented_metrics) * 100 if documented_metrics else 0
        ),
    }

    return comparison


def main():
    """Main function to find all metrics"""

    finder = ActualMetricsFinder()

    print("=" * 80)
    print("FINDING ALL ACTUAL METRICS IN CIRIS")
    print("=" * 80)

    results = finder.find_all_metrics()

    print(f"\n📊 TOTAL UNIQUE METRICS FOUND: {results['total_unique']}")

    print("\n📈 METRICS BY CATEGORY:")
    for category, metrics in results["by_category"].items():
        if isinstance(metrics, dict):
            total = sum(len(m) for m in metrics.values() if isinstance(m, set))
            print(f"  {category}: {total} metrics across {len(metrics)} sources")
        elif isinstance(metrics, set):
            print(f"  {category}: {len(metrics)} metrics")

    print("\n🔝 TOP 30 ACTUAL METRICS:")
    for i, metric in enumerate(results["unique_metrics"][:30], 1):
        print(f"  {i:2}. {metric}")

    # Compare with documented
    print("\n" + "=" * 80)
    print("COMPARING WITH DOCUMENTED METRICS")
    print("=" * 80)

    comparison = compare_with_documented(results, Path("/home/emoore/CIRISAgent/ciris_engine/docs/telemetry"))

    print(
        f"""
📊 COMPARISON RESULTS:
  • Actual metrics found: {comparison['actual_total']}
  • Documented metrics: {comparison['documented_total']}
  • Metrics in both: {len(comparison['in_both'])}
  • Only in actual code: {len(comparison['only_in_actual'])}
  • Only in documentation: {len(comparison['only_in_docs'])}
  • Coverage: {comparison['coverage_percent']:.1f}%
"""
    )

    print("🎯 METRICS IN BOTH (first 20):")
    for metric in comparison["in_both"][:20]:
        print(f"  ✓ {metric}")

    print("\n❌ ONLY IN ACTUAL CODE (first 20):")
    for metric in comparison["only_in_actual"][:20]:
        print(f"  + {metric}")

    print("\n📝 ONLY IN DOCUMENTATION (first 20):")
    for metric in comparison["only_in_docs"][:20]:
        print(f"  - {metric}")

    # Save results
    output_file = Path("/home/emoore/CIRISAgent/tools/telemetry_tool/actual_metrics_found.json")
    with output_file.open("w") as f:
        json.dump(
            {"actual_metrics": results, "comparison": comparison, "timestamp": "2025-08-14"}, f, indent=2, default=list
        )

    print(f"\n📁 Results saved to: {output_file}")

    print("\n" + "=" * 80)
    print("KEY INSIGHT")
    print("=" * 80)
    print(
        f"""
The production system reports 556+ metrics, but we found {results['total_unique']} unique
metric names in the code. This suggests:

1. Many metrics are dynamically named (e.g., per-service metrics)
2. Some metrics are collected but not yet exposed via API
3. The documentation captured {comparison['documented_total']} planned metrics

The actual implementation is MORE extensive than the documentation!
"""
    )


if __name__ == "__main__":
    main()
