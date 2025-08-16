#!/usr/bin/env python3
"""
Modular metric scanner with pluggable mechanisms and inheritance tracking.
Each mechanism is a separate scanner that can walk inheritance chains.
"""

import ast
import json
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


class MetricMechanism(ABC):
    """Base class for metric scanning mechanisms."""

    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.metrics = {}

    @abstractmethod
    def scan(self) -> Dict[str, Any]:
        """Scan for metrics using this mechanism."""
        pass

    @abstractmethod
    def get_name(self) -> str:
        """Get the name of this mechanism."""
        pass

    def find_base_class(self, content: str, class_name: str) -> Optional[str]:
        """Find the base class of a given class."""
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef) and node.name == class_name:
                    if node.bases:
                        # Get first base class name
                        base = node.bases[0]
                        if isinstance(base, ast.Name):
                            return base.id
                        elif isinstance(base, ast.Attribute):
                            return base.attr
        except:
            pass
        return None

    def walk_inheritance_chain(self, file_path: Path, class_name: str) -> List[Tuple[Path, str]]:
        """Walk up the inheritance chain to find all parent classes."""
        chain = [(file_path, class_name)]
        visited = set()

        current_file = file_path
        current_class = class_name

        while current_file and current_class:
            key = (str(current_file), current_class)
            if key in visited:
                break
            visited.add(key)

            try:
                with open(current_file, "r") as f:
                    content = f.read()

                base_class = self.find_base_class(content, current_class)
                if not base_class or base_class in ["object", "ABC", "BaseModel"]:
                    break

                # Find file containing base class
                base_file = self.find_class_file(base_class)
                if base_file:
                    chain.append((base_file, base_class))
                    current_file = base_file
                    current_class = base_class
                else:
                    break
            except:
                break

        return chain

    def find_class_file(self, class_name: str) -> Optional[Path]:
        """Find the file containing a class definition."""
        for py_file in self.base_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue
            try:
                with open(py_file, "r") as f:
                    content = f.read()
                if f"class {class_name}" in content:
                    return py_file
            except:
                pass
        return None


class GetTelemetryMechanism(MetricMechanism):
    """Scanner for get_telemetry() and get_metrics() methods."""

    def get_name(self) -> str:
        return "get_telemetry() and get_metrics() methods"

    def scan(self) -> Dict[str, Any]:
        """Scan for metrics from get_telemetry() and get_metrics() methods."""
        results = {}

        # Scan ALL directories
        for py_file in self.base_path.rglob("*.py"):
            if "__pycache__" in str(py_file) or "test" in str(py_file).lower():
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                # Check for both get_telemetry and get_metrics
                has_telemetry = "def get_telemetry" in content or "async def get_telemetry" in content
                has_metrics = "def get_metrics" in content or "async def get_metrics" in content

                if not has_telemetry and not has_metrics:
                    continue

                # Extract service name
                service_name = self._extract_service_name(py_file, content)
                if not service_name:
                    continue

                # Parse method to find metrics
                metrics = []

                if has_telemetry:
                    telemetry_metrics = self._extract_telemetry_metrics(content, service_name)
                    metrics.extend(telemetry_metrics)

                if has_metrics:
                    # For get_metrics(), look for _collect_custom_metrics
                    custom_metrics = self._extract_custom_metrics_from_content(content, service_name)
                    metrics.extend(custom_metrics)

                    # Also add base metrics from BaseService
                    base_metrics = [
                        f"{service_name}.uptime_seconds",
                        f"{service_name}.request_count",
                        f"{service_name}.error_count",
                        f"{service_name}.error_rate",
                        f"{service_name}.healthy",
                    ]
                    metrics.extend(base_metrics)

                if metrics:
                    results[service_name] = list(set(metrics))  # Remove duplicates

            except Exception as e:
                pass

        return results

    def _extract_service_name(self, file_path: Path, content: str) -> Optional[str]:
        """Extract service name from file."""
        path_str = str(file_path).lower()
        file_name = file_path.stem.lower()

        # Comprehensive path-based mapping (check paths first)
        if "graph/memory_service" in path_str:
            return "memory"
        elif "graph/config_service" in path_str:
            return "config"
        elif "graph/telemetry_service" in path_str:
            return "telemetry"
        elif "graph/audit_service" in path_str:
            return "audit"
        elif "graph/incident_service" in path_str:
            return "incident_management"
        elif "graph/tsdb_consolidation" in path_str:
            return "tsdb_consolidation"
        elif "lifecycle/time" in path_str:
            return "time"
        elif "lifecycle/shutdown" in path_str:
            return "shutdown"
        elif "lifecycle/initialization" in path_str:
            return "initialization"
        elif "lifecycle/scheduler" in path_str:
            return "task_scheduler"
        elif "infrastructure/authentication" in path_str:
            return "authentication"
        elif "infrastructure/resource_monitor" in path_str:
            return "resource_monitor"
        elif "persistence/maintenance" in path_str:
            return "database_maintenance"
        elif "governance/wise_authority" in path_str:
            return "wise_authority"
        elif "governance/filter" in path_str:
            return "adaptive_filter"
        elif "governance/visibility" in path_str:
            return "visibility"
        elif "adaptation/self_observation" in path_str:
            return "self_observation"
        elif "runtime/llm_service" in path_str:
            return "llm"
        elif "runtime/control_service" in path_str:
            return "runtime_control"
        elif "secrets/service.py" in path_str:
            return "secrets"
        elif "tools/secrets_tool" in path_str:
            return "secrets_tool"

        # Fallback to file name patterns
        if file_name == "maintenance":
            return "database_maintenance"
        elif file_name == "time":
            return "time"
        elif file_name == "shutdown":
            return "shutdown"
        elif file_name == "initialization":
            return "initialization"
        elif file_name == "scheduler":
            return "task_scheduler"
        elif file_name == "authentication":
            return "authentication"
        elif file_name == "filter":
            return "adaptive_filter"
        elif file_name == "visibility":
            return "visibility"

        return None

    def _extract_custom_metrics_from_content(self, content: str, service_name: str) -> List[str]:
        """Extract metrics from _collect_custom_metrics in content."""
        metrics = []

        # Look for metrics.update() calls in _collect_custom_metrics
        if "_collect_custom_metrics" in content:
            # Find dictionary keys in metrics.update() calls
            pattern = r"metrics\.update\s*\(\s*\{([^}]+)\}"
            matches = re.findall(pattern, content, re.DOTALL)

            for match in matches:
                # Extract keys from the dictionary
                key_pattern = r'["\']([^"\']+)["\']\s*:'
                keys = re.findall(key_pattern, match)
                for key in keys:
                    metrics.append(f"{service_name}.{key}")

        return metrics

    def _extract_telemetry_metrics(self, content: str, service_name: str) -> List[str]:
        """Extract metrics from get_telemetry() method."""
        metrics = []

        # Find the get_telemetry method
        method_start = content.find("def get_telemetry")
        if method_start == -1:
            method_start = content.find("async def get_telemetry")

        if method_start == -1:
            return metrics

        # Get method body
        method_section = content[method_start : method_start + 3000]

        # Look for dictionary keys in return statement
        dict_pattern = r'["\']([\w_]+)["\']:\s*'
        for match in re.finditer(dict_pattern, method_section):
            key = match.group(1)
            # Filter to likely metric keys
            if key not in ["service_name", "healthy", "error"] and not key.startswith("_"):
                metric = f"{service_name}.{key}"
                metrics.append(metric)

        return metrics


class CustomMetricsMechanism(MetricMechanism):
    """Scanner for _collect_custom_metrics() and _collect_metrics() implementations."""

    def get_name(self) -> str:
        return "Pull metrics (_collect_metrics/_collect_custom_metrics)"

    def scan(self) -> Dict[str, Any]:
        """Scan for metrics from _collect_metrics() and _collect_custom_metrics() with inheritance."""
        results = {}

        # Scan ALL service directories comprehensively
        paths_to_scan = [
            self.base_path / "logic" / "services" / "graph",
            self.base_path / "logic" / "services" / "infrastructure",
            self.base_path / "logic" / "services" / "lifecycle",
            self.base_path / "logic" / "services" / "governance",
            self.base_path / "logic" / "services" / "runtime",
            self.base_path / "logic" / "services" / "tools",
            self.base_path / "logic" / "services" / "adaptation",
            self.base_path / "logic" / "persistence",
            self.base_path / "logic" / "secrets",
        ]

        for scan_path in paths_to_scan:
            if not scan_path.exists():
                continue

            for py_file in scan_path.rglob("*.py"):
                if "__pycache__" in str(py_file) or "__init__" in str(py_file):
                    continue

                try:
                    with open(py_file, "r") as f:
                        content = f.read()

                    # Find all classes with _collect_custom_metrics or _collect_metrics
                    classes = self._find_classes_with_metrics(content)

                    for class_name in classes:
                        service_name = self._extract_service_from_class(py_file, class_name, content)
                        if not service_name:
                            continue

                        # Get metrics from this class and all parent classes
                        all_metrics = self._collect_metrics_with_inheritance(py_file, class_name)

                        if all_metrics:
                            results[service_name] = {
                                "metrics": all_metrics,
                                "mechanism": "PULL",
                                "storage": "NONE",
                                "availability": "on_request",
                                "version": "1.4.3",
                            }

                except Exception as e:
                    pass

        return results

    def _find_classes_with_metrics(self, content: str) -> List[str]:
        """Find all classes that have _collect_metrics or _collect_custom_metrics methods."""
        classes = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    for item in node.body:
                        if isinstance(item, ast.FunctionDef) and item.name in [
                            "_collect_metrics",
                            "_collect_custom_metrics",
                        ]:
                            classes.append(node.name)
                            break
        except:
            pass
        return classes

    def _extract_service_from_class(self, file_path: Path, class_name: str, content: str) -> Optional[str]:
        """Extract service name from class name or file path."""
        # Comprehensive class name mapping
        class_map = {
            "LocalGraphMemoryService": "memory",
            "GraphConfigService": "config",
            "GraphTelemetryService": "telemetry",
            "AuditService": "audit",
            "IncidentService": "incident_management",
            "SecretsToolService": "secrets_tool",
            "TimeService": "time",
            "ShutdownService": "shutdown",
            "InitializationService": "initialization",
            "AuthenticationService": "authentication",
            "ResourceMonitorService": "resource_monitor",
            "DatabaseMaintenanceService": "database_maintenance",
            "WiseAuthorityService": "wise_authority",
            "AdaptiveFilterService": "adaptive_filter",
            "VisibilityService": "visibility",
            "SelfObservationService": "self_observation",
            "LLMService": "llm",
            "RuntimeControlService": "runtime_control",
            "TaskScheduler": "task_scheduler",
            "TaskSchedulerService": "task_scheduler",
            "TSDBConsolidationService": "tsdb_consolidation",
            "SecretsService": "secrets",
        }

        if class_name in class_map:
            return class_map[class_name]

        # Use path-based extraction
        path_str = str(file_path).lower()

        # Check specific path patterns
        if "graph/memory_service" in path_str:
            return "memory"
        elif "graph/config_service" in path_str:
            return "config"
        elif "graph/telemetry_service" in path_str:
            return "telemetry"
        elif "graph/audit_service" in path_str:
            return "audit"
        elif "graph/incident_service" in path_str:
            return "incident_management"
        elif "graph/tsdb_consolidation" in path_str:
            return "tsdb_consolidation"
        elif "lifecycle/time" in path_str:
            return "time"
        elif "lifecycle/shutdown" in path_str:
            return "shutdown"
        elif "lifecycle/initialization" in path_str:
            return "initialization"
        elif "lifecycle/scheduler" in path_str:
            return "task_scheduler"
        elif "infrastructure/authentication" in path_str:
            return "authentication"
        elif "infrastructure/resource_monitor" in path_str:
            return "resource_monitor"
        elif "persistence/maintenance" in path_str:
            return "database_maintenance"
        elif "governance/wise_authority" in path_str:
            return "wise_authority"
        elif "governance/filter" in path_str:
            return "adaptive_filter"
        elif "governance/visibility" in path_str:
            return "visibility"
        elif "adaptation/self_observation" in path_str:
            return "self_observation"
        elif "runtime/llm_service" in path_str:
            return "llm"
        elif "runtime/control_service" in path_str:
            return "runtime_control"
        elif "secrets/service.py" in path_str:
            return "secrets"
        elif "tools/secrets_tool" in path_str:
            return "secrets_tool"

        return None

    def _collect_metrics_with_inheritance(self, file_path: Path, class_name: str) -> List[str]:
        """Collect metrics from class and all parent classes."""
        all_metrics = []

        # Walk inheritance chain
        chain = self.walk_inheritance_chain(file_path, class_name)

        for class_file, class_name in chain:
            try:
                with open(class_file, "r") as f:
                    content = f.read()

                # Extract metrics from _collect_custom_metrics in this class
                metrics = self._extract_custom_metrics(content, class_name)
                all_metrics.extend(metrics)

                # Also check for base metrics from BaseService
                if "BaseService" in class_name or "base_service" in str(class_file).lower():
                    # BaseService provides these metrics
                    base_metrics = ["uptime_seconds", "request_count", "error_count", "error_rate", "healthy"]
                    all_metrics.extend(base_metrics)

            except:
                pass

        return list(set(all_metrics))  # Remove duplicates

    def _extract_custom_metrics(self, content: str, class_name: str) -> List[str]:
        """Extract metrics from _collect_custom_metrics method."""
        metrics = []

        # Find the method in this class
        pattern = rf"class {class_name}.*?def _collect_custom_metrics.*?return"
        match = re.search(pattern, content, re.DOTALL)

        if match:
            method_body = match.group(0)

            # Look for metrics being added to dict
            # Pattern 1: metrics["key"] = value
            pattern1 = r'metrics\[["\']([\w_]+)["\']\]\s*='
            for m in re.finditer(pattern1, method_body):
                metrics.append(m.group(1))

            # Pattern 2: metrics.update({"key": value})
            pattern2 = r'["\']([\w_]+)["\']:\s*(?:float|int|str)?\('
            for m in re.finditer(pattern2, method_body):
                key = m.group(1)
                if key not in ["self", "metrics"]:
                    metrics.append(key)

        return metrics


class MemorizeMetricMechanism(MetricMechanism):
    """Scanner for memorize_metric() calls."""

    def get_name(self) -> str:
        return "memorize_metric() calls"

    def scan(self) -> Dict[str, Any]:
        """Scan for metrics pushed via memorize_metric()."""
        metrics = set()

        patterns = [
            r'memorize_metric\s*\(\s*metric_name\s*=\s*["\']([\w\.]+)["\']',
            r'memorize_metric\s*\(\s*["\']([\w\.]+)["\']',
            r'\.memorize_metric\s*\(\s*["\']([\w\.]+)["\']',
        ]

        for py_file in self.base_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                for pattern in patterns:
                    for match in re.finditer(pattern, content):
                        metric = match.group(1)
                        if "{" not in metric:  # Skip f-string patterns
                            metrics.add(metric)

            except:
                pass

        return {"all": list(metrics)}


class RecordMetricMechanism(MetricMechanism):
    """Scanner for record_metric() calls - these go to TSDB."""

    def get_name(self) -> str:
        return "Push metrics (record_metric -> TSDB)"

    def scan(self) -> Dict[str, Any]:
        """Scan for metrics recorded directly to TSDB."""
        metrics_by_file = defaultdict(list)

        patterns = [
            r'record_metric\s*\(\s*metric_name\s*=\s*["\']([\w\.]+)["\']',
            r'record_metric\s*\(\s*["\']([\w\.]+)["\']',
            r'\.record_metric\s*\(\s*metric_name\s*=\s*["\']([\w\.]+)["\']',
        ]

        for py_file in self.base_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                file_metrics = set()
                for pattern in patterns:
                    for match in re.finditer(pattern, content):
                        metric = match.group(1)
                        if "{" not in metric:
                            file_metrics.add(metric)

                if file_metrics:
                    service_name = self._extract_service_from_path(py_file)
                    for metric in file_metrics:
                        metrics_by_file[service_name].append(
                            {
                                "name": metric,
                                "mechanism": "PUSH",
                                "storage": "TSDB",
                                "availability": "historical",
                                "location": str(py_file.relative_to(self.base_path)),
                                "version": "1.4.2+",
                            }
                        )

            except:
                pass

        return dict(metrics_by_file)

    def _extract_service_from_path(self, file_path: Path) -> str:
        """Extract service name from file path."""
        path_str = str(file_path).lower()
        if "llm_bus" in path_str:
            return "llm_bus"
        elif "telemetry" in path_str:
            return "telemetry_service"
        else:
            return "unknown"


class HandlerMetricMechanism(MetricMechanism):
    """Scanner for handler action metrics."""

    def get_name(self) -> str:
        return "Handler action metrics"

    def scan(self) -> Dict[str, Any]:
        """Scan for handler metrics."""
        handler_actions = [
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

        metrics = set()

        # Base handler metrics
        base_metrics = [
            "handler_invoked_total",
            "handler_completed_total",
            "handler_error_total",
            "handler_failed_total",
        ]
        metrics.update(base_metrics)

        # Per-action metrics
        for action in handler_actions:
            metrics.add(f"handler_invoked_{action}")
            metrics.add(f"handler_completed_{action}")
            metrics.add(f"handler_error_{action}")
            metrics.add(f"action_selected_{action}")

        return {"all": list(metrics)}


class ModularMetricScanner:
    """Main scanner that orchestrates all mechanisms."""

    def __init__(self, base_path: str = "/home/emoore/CIRISAgent/ciris_engine"):
        self.base_path = Path(base_path)
        # Add all service directories to scan
        self.service_paths = [
            self.base_path / "logic" / "services",
            self.base_path / "logic" / "persistence",  # For database_maintenance
            self.base_path / "logic" / "secrets",  # For secrets service
        ]
        self.mechanisms = [
            GetTelemetryMechanism(self.base_path),
            CustomMetricsMechanism(self.base_path),
            MemorizeMetricMechanism(self.base_path),
            RecordMetricMechanism(self.base_path),
            HandlerMetricMechanism(self.base_path),
        ]

    def scan_all(self) -> Dict[str, Any]:
        """Run all scanning mechanisms."""
        results = {}

        for mechanism in self.mechanisms:
            print(f"Scanning {mechanism.get_name()}...")
            mechanism_results = mechanism.scan()
            results[mechanism.get_name()] = mechanism_results

        return results

    def generate_report(self) -> Tuple[str, Dict]:
        """Generate comprehensive report showing WHERE, HOW, WHY."""
        scan_results = self.scan_all()

        # Categorize metrics
        pull_metrics = []
        push_metrics = []

        for mechanism_name, data in scan_results.items():
            if "Pull" in mechanism_name or "get_telemetry" in mechanism_name:
                pull_metrics.append((mechanism_name, data))
            elif "Push" in mechanism_name or "record_metric" in mechanism_name:
                push_metrics.append((mechanism_name, data))

        # Generate report
        report = []
        report.append("=" * 80)
        report.append("🎯 TELEMETRY ARCHITECTURE ANALYSIS - v1.4.3")
        report.append("=" * 80)
        report.append(f"Timestamp: {datetime.now().isoformat()}")
        report.append("")

        report.append("📊 METRIC COLLECTION MECHANISMS:")
        report.append("")
        report.append("PULL METRICS (Query on demand, not stored):")
        for mechanism_name, data in pull_metrics:
            count = self._count_metrics(data)
            report.append(f"  • {mechanism_name}: {count} metrics")
            if isinstance(data, dict) and data:
                for service, info in list(data.items())[:3]:
                    if isinstance(info, dict) and "metrics" in info:
                        report.append(f"    - {service}: {len(info['metrics'])} metrics")

        report.append("")
        report.append("PUSH METRICS (Stored in TSDB, historical):")
        for mechanism_name, data in push_metrics:
            count = self._count_metrics(data)
            report.append(f"  • {mechanism_name}: {count} metrics")
            if isinstance(data, dict) and data:
                for service, metrics in list(data.items())[:3]:
                    if isinstance(metrics, list):
                        report.append(f"    - {service}: {len(metrics)} metrics")

        report.append("")
        report.append("=" * 80)
        report.append("KEY INSIGHTS:")
        report.append("  • PULL metrics: Available via API, real-time, not persisted")
        report.append("  • PUSH metrics: Stored in TSDB, queryable historically")
        report.append("  • Version 1.4.3: Focus on expanding PULL metrics via get_telemetry()")
        report.append("=" * 80)

        return "\n".join(report), scan_results

    def _count_metrics(self, data: Any) -> int:
        """Count metrics in various data structures."""
        if isinstance(data, dict):
            count = 0
            for value in data.values():
                if isinstance(value, list):
                    count += len(value)
                elif isinstance(value, dict):
                    if "metrics" in value and isinstance(value["metrics"], list):
                        count += len(value["metrics"])
                    else:
                        count += 1
            return count
        return 0


def main():
    """Main entry point."""
    scanner = ModularMetricScanner()
    report, results = scanner.generate_report()
    print(report)

    # Save results
    with open("modular_scan_results.json", "w") as f:
        # Convert sets to lists for JSON serialization
        clean_results = {}
        for mechanism, data in results.items():
            if isinstance(data, dict):
                clean_data = {}
                for key, value in data.items():
                    if isinstance(value, set):
                        clean_data[key] = list(value)
                    else:
                        clean_data[key] = value
                clean_results[mechanism] = clean_data
            else:
                clean_results[mechanism] = data

        json.dump({"timestamp": datetime.now().isoformat(), "results": clean_results}, f, indent=2)

    print("\n💾 Saved results to modular_scan_results.json")


if __name__ == "__main__":
    main()
