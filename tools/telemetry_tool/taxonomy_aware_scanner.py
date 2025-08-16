#!/usr/bin/env python3
"""
Taxonomy-aware metric scanner that understands the full CIRIS architecture:
- Core Services (21 base services)
- Handlers (action handlers)
- Runtime Objects (processor, queue, etc.)
- Buses (6 message buses)
- Base Services (BaseService, BaseGraphService, etc.)
- Adapter Services (API, Discord, CLI)
- Dynamic Services (per-agent instances like discord_datum)
"""

import ast
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class ServiceTaxonomy:
    """Understanding of CIRIS service architecture."""

    # Core 21 services
    GRAPH_SERVICES = ["memory", "config", "telemetry", "audit", "incident_management", "tsdb_consolidation"]
    INFRASTRUCTURE_SERVICES = [
        "time",
        "shutdown",
        "initialization",
        "authentication",
        "resource_monitor",
        "database_maintenance",
        "secrets",
    ]
    GOVERNANCE_SERVICES = ["wise_authority", "adaptive_filter", "visibility", "self_observation"]
    RUNTIME_SERVICES = ["llm", "runtime_control", "task_scheduler"]
    TOOL_SERVICES = ["secrets_tool"]

    # Message buses
    BUSES = ["communication_bus", "memory_bus", "llm_bus", "tool_bus", "runtime_control_bus", "wise_bus"]

    # Handler actions
    HANDLER_ACTIONS = [
        "observe",
        "speak",
        "tool",
        "reject",
        "ponder",
        "defer",
        "memorize",
        "recall",
        "forget",
        "task_complete",
    ]

    # Runtime objects
    RUNTIME_OBJECTS = [
        "agent_processor",
        "processing_queue",
        "circuit_breaker",
        "service_registry",
        "service_initializer",
    ]

    # Base classes
    BASE_CLASSES = ["BaseService", "BaseGraphService", "BaseAdapter"]

    # Adapter types
    ADAPTER_TYPES = ["api", "discord", "cli"]

    @classmethod
    def categorize_service(cls, name: str) -> Tuple[str, str]:
        """Categorize a service by its taxonomy level and type."""
        name_lower = name.lower()

        # Check buses first
        for bus in cls.BUSES:
            if bus in name_lower:
                return ("BUS", bus)

        # Check core services
        for service in cls.GRAPH_SERVICES:
            if service in name_lower:
                return ("CORE_SERVICE", f"graph/{service}")

        for service in cls.INFRASTRUCTURE_SERVICES:
            if service in name_lower:
                return ("CORE_SERVICE", f"infrastructure/{service}")

        for service in cls.GOVERNANCE_SERVICES:
            if service in name_lower:
                return ("CORE_SERVICE", f"governance/{service}")

        for service in cls.RUNTIME_SERVICES:
            if service in name_lower:
                return ("CORE_SERVICE", f"runtime/{service}")

        for service in cls.TOOL_SERVICES:
            if service in name_lower:
                return ("CORE_SERVICE", f"tool/{service}")

        # Check handlers
        for action in cls.HANDLER_ACTIONS:
            if f"handler_{action}" in name_lower or f"{action}_handler" in name_lower:
                return ("HANDLER", action)

        # Check runtime objects
        for obj in cls.RUNTIME_OBJECTS:
            if obj in name_lower:
                return ("RUNTIME_OBJECT", obj)

        # Check adapters
        for adapter in cls.ADAPTER_TYPES:
            if adapter in name_lower:
                # Check if it's a dynamic instance
                if "_" in name and not name.endswith("_adapter"):
                    # e.g., discord_datum
                    parts = name.split("_")
                    if len(parts) == 2:
                        return ("DYNAMIC_ADAPTER", f"{parts[0]}/{parts[1]}")
                return ("ADAPTER", adapter)

        # Check base classes
        for base in cls.BASE_CLASSES:
            if base in name:
                return ("BASE_CLASS", base)

        return ("UNKNOWN", name)


class TaxonomyAwareScanner:
    """Scanner that understands service taxonomy and metric origins."""

    def __init__(self, base_path: str = "/home/emoore/CIRISAgent/ciris_engine"):
        self.base_path = Path(base_path)
        self.taxonomy = ServiceTaxonomy()
        self.results = {
            "core_services": defaultdict(lambda: {"pull": [], "push": []}),
            "handlers": defaultdict(lambda: {"pull": [], "push": []}),
            "runtime_objects": defaultdict(lambda: {"pull": [], "push": []}),
            "buses": defaultdict(lambda: {"pull": [], "push": []}),
            "base_classes": defaultdict(lambda: {"pull": [], "push": []}),
            "adapters": defaultdict(lambda: {"pull": [], "push": []}),
            "dynamic_adapters": defaultdict(lambda: {"pull": [], "push": []}),
        }

    def scan_all(self) -> Dict[str, Any]:
        """Scan entire codebase with taxonomy awareness."""

        print("Scanning with taxonomy awareness...")

        # Scan all Python files
        for py_file in self.base_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                # Identify what this file contains
                self._scan_file(py_file, content)

            except Exception as e:
                pass

        return self.results

    def _scan_file(self, file_path: Path, content: str):
        """Scan a single file for metrics."""

        # Find all classes in the file
        classes = self._find_classes(content)

        for class_name in classes:
            # Categorize the class
            category, subtype = self.taxonomy.categorize_service(class_name)

            # Find PULL metrics (get_telemetry, _collect_metrics)
            pull_metrics = self._find_pull_metrics(content, class_name)
            if pull_metrics:
                self._store_metrics(category, subtype, "pull", pull_metrics, file_path)

            # Find PUSH metrics (record_metric, memorize_metric)
            push_metrics = self._find_push_metrics(content, class_name)
            if push_metrics:
                self._store_metrics(category, subtype, "push", push_metrics, file_path)

        # Also scan for handler metrics at module level
        handler_metrics = self._find_handler_metrics(content)
        if handler_metrics:
            self._store_metrics("HANDLER", "module_level", "push", handler_metrics, file_path)

    def _find_classes(self, content: str) -> List[str]:
        """Find all class names in content."""
        classes = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    classes.append(node.name)
        except:
            # Fallback to regex
            pattern = r"class\s+(\w+)"
            classes = re.findall(pattern, content)
        return classes

    def _find_pull_metrics(self, content: str, class_name: str) -> List[Dict[str, str]]:
        """Find PULL metrics (get_telemetry, _collect_metrics)."""
        metrics = []

        # Look for get_telemetry method
        if re.search(rf"class {class_name}.*?def get_telemetry", content, re.DOTALL):
            # Extract metrics from return statement
            pattern = r'["\']([\w_\.]+)["\']:\s*'
            for match in re.finditer(pattern, content):
                metric = match.group(1)
                if metric not in ["service_name", "healthy", "error"] and not metric.startswith("_"):
                    metrics.append({"name": metric, "method": "get_telemetry", "type": "PULL"})

        # Look for _collect_custom_metrics
        if re.search(rf"class {class_name}.*?def _collect_custom_metrics", content, re.DOTALL):
            # Extract metrics from dict updates
            pattern = r'["\']([\w_]+)["\']:\s*(?:float|int)?\('
            for match in re.finditer(pattern, content):
                metric = match.group(1)
                if metric not in ["self", "metrics"]:
                    metrics.append({"name": metric, "method": "_collect_custom_metrics", "type": "PULL"})

        return metrics

    def _find_push_metrics(self, content: str, class_name: str) -> List[Dict[str, str]]:
        """Find PUSH metrics (record_metric, memorize_metric)."""
        metrics = []

        # Look for record_metric calls
        patterns = [
            r'record_metric\s*\(\s*metric_name\s*=\s*["\']([\w\.]+)["\']',
            r'record_metric\s*\(\s*["\']([\w\.]+)["\']',
            r'memorize_metric\s*\(\s*metric_name\s*=\s*["\']([\w\.]+)["\']',
        ]

        for pattern in patterns:
            for match in re.finditer(pattern, content):
                metric = match.group(1)
                if "{" not in metric:  # Skip f-strings
                    metrics.append(
                        {
                            "name": metric,
                            "method": "record_metric" if "record" in pattern else "memorize_metric",
                            "type": "PUSH",
                            "storage": "TSDB",
                        }
                    )

        return metrics

    def _find_handler_metrics(self, content: str) -> List[Dict[str, str]]:
        """Find handler-specific metrics."""
        metrics = []

        # Handler metrics follow patterns
        for action in ServiceTaxonomy.HANDLER_ACTIONS:
            if f"handler_invoked_{action}" in content:
                metrics.append({"name": f"handler_invoked_{action}", "type": "PUSH", "category": "handler"})
            if f"handler_completed_{action}" in content:
                metrics.append({"name": f"handler_completed_{action}", "type": "PUSH", "category": "handler"})
            if f"action_selected_{action}" in content:
                metrics.append({"name": f"action_selected_{action}", "type": "PUSH", "category": "handler"})

        return metrics

    def _store_metrics(self, category: str, subtype: str, metric_type: str, metrics: List[Dict], file_path: Path):
        """Store metrics in the appropriate category."""

        category_map = {
            "CORE_SERVICE": "core_services",
            "HANDLER": "handlers",
            "RUNTIME_OBJECT": "runtime_objects",
            "BUS": "buses",
            "BASE_CLASS": "base_classes",
            "ADAPTER": "adapters",
            "DYNAMIC_ADAPTER": "dynamic_adapters",
        }

        if category in category_map:
            storage = self.results[category_map[category]]
            for metric in metrics:
                metric["location"] = str(file_path.relative_to(self.base_path))
                storage[subtype][metric_type].append(metric)

    def generate_report(self) -> str:
        """Generate a comprehensive taxonomy-aware report."""
        report = []
        report.append("=" * 80)
        report.append("🎯 CIRIS TELEMETRY TAXONOMY REPORT - v1.4.3")
        report.append("=" * 80)
        report.append(f"Timestamp: {datetime.now().isoformat()}")
        report.append("")

        # Core Services (21)
        report.append("📦 CORE SERVICES (21 base services):")
        report.append("-" * 40)
        for service_type in ["graph", "infrastructure", "governance", "runtime", "tool"]:
            services = [k for k in self.results["core_services"].keys() if k.startswith(service_type)]
            if services:
                report.append(f"\n{service_type.upper()} Services:")
                for service in services:
                    data = self.results["core_services"][service]
                    pull_count = len(data["pull"])
                    push_count = len(data["push"])
                    report.append(f"  • {service:30} PULL: {pull_count:3} | PUSH: {push_count:3}")

        # Buses (6)
        if self.results["buses"]:
            report.append("\n📡 MESSAGE BUSES (6 buses):")
            report.append("-" * 40)
            for bus, data in self.results["buses"].items():
                pull_count = len(data["pull"])
                push_count = len(data["push"])
                report.append(f"  • {bus:30} PULL: {pull_count:3} | PUSH: {push_count:3}")

        # Handlers
        if self.results["handlers"]:
            report.append("\n⚡ HANDLERS (action handlers):")
            report.append("-" * 40)
            total_handler_metrics = sum(
                len(data["push"]) + len(data["pull"]) for data in self.results["handlers"].values()
            )
            report.append(f"  Total handler metrics: {total_handler_metrics}")

        # Runtime Objects
        if self.results["runtime_objects"]:
            report.append("\n⚙️ RUNTIME OBJECTS:")
            report.append("-" * 40)
            for obj, data in self.results["runtime_objects"].items():
                pull_count = len(data["pull"])
                push_count = len(data["push"])
                report.append(f"  • {obj:30} PULL: {pull_count:3} | PUSH: {push_count:3}")

        # Adapters
        if self.results["adapters"]:
            report.append("\n🔌 ADAPTERS (API, Discord, CLI):")
            report.append("-" * 40)
            for adapter, data in self.results["adapters"].items():
                pull_count = len(data["pull"])
                push_count = len(data["push"])
                report.append(f"  • {adapter:30} PULL: {pull_count:3} | PUSH: {push_count:3}")

        # Dynamic Adapters
        if self.results["dynamic_adapters"]:
            report.append("\n🔄 DYNAMIC ADAPTERS (per-agent instances):")
            report.append("-" * 40)
            for instance, data in self.results["dynamic_adapters"].items():
                pull_count = len(data["pull"])
                push_count = len(data["push"])
                report.append(f"  • {instance:30} PULL: {pull_count:3} | PUSH: {push_count:3}")

        # Summary
        report.append("\n" + "=" * 80)
        report.append("📊 SUMMARY:")

        total_pull = sum(len(data["pull"]) for category in self.results.values() for data in category.values())
        total_push = sum(len(data["push"]) for category in self.results.values() for data in category.values())

        report.append(f"  Total PULL metrics: {total_pull}")
        report.append(f"  Total PUSH metrics: {total_push}")
        report.append("")
        report.append("💡 KEY INSIGHTS:")
        report.append("  • PULL metrics: Real-time, on-demand, not persisted")
        report.append("  • PUSH metrics: Stored in TSDB, historical queries available")
        report.append("  • Dynamic adapters create metrics per agent instance (e.g., discord_datum)")
        report.append("  • Base classes provide inherited metrics to all subclasses")
        report.append("=" * 80)

        return "\n".join(report)


def main():
    """Main entry point."""
    scanner = TaxonomyAwareScanner()
    results = scanner.scan_all()
    report = scanner.generate_report()
    print(report)

    # Save detailed results
    with open("taxonomy_scan_results.json", "w") as f:
        # Clean up for JSON serialization
        clean_results = {}
        for category, data in results.items():
            clean_results[category] = {}
            for key, metrics in data.items():
                clean_results[category][key] = metrics

        json.dump({"timestamp": datetime.now().isoformat(), "version": "1.4.3", "results": clean_results}, f, indent=2)

    print("\n💾 Saved detailed results to taxonomy_scan_results.json")


if __name__ == "__main__":
    main()
