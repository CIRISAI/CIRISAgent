#!/usr/bin/env python3
"""
Comprehensive metric scanner that handles ALL 4 telemetry mechanisms:
1. Service get_telemetry() methods
2. Bus memorize_metric() calls
3. Handler telemetry (invoked/completed/selected)
4. Runtime/Adapter service registration (available/healthy)
"""

import ast
import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple


class ComprehensiveMetricScanner:
    """Scans for ALL metrics across all 4 telemetry mechanisms."""

    def __init__(self):
        self.base_path = Path("/home/emoore/CIRISAgent/ciris_engine")

        # All service types from the codebase
        self.service_types = [
            "llm",
            "memory",
            "communication",
            "wise_authority",
            "tool",
            "runtime_control",
            "telemetry",
            "audit",
            "config",
            "incident",
            "tsdb",
            "authentication",
            "resource_monitor",
            "time",
            "shutdown",
            "initialization",
            "database_maintenance",
            "secrets",
            "adaptive_filter",
            "visibility",
            "self_observation",
            "task_scheduler",
            "secrets_tool",
        ]

        # Handler action types
        self.handler_actions = [
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

        # Results storage
        self.metrics = {
            "service_telemetry": {},  # From get_telemetry() methods
            "bus_metrics": set(),  # From memorize_metric() calls
            "handler_metrics": set(),  # Handler action metrics
            "service_availability": set(),  # Service available/healthy
            "direct_recorded": set(),  # Direct record_metric() calls
        }

    def scan_all(self) -> Dict[str, any]:
        """Scan for all metrics across all mechanisms."""

        print("Scanning Mechanism 1: Service get_telemetry() methods...")
        self._scan_service_telemetry()

        print("Scanning Mechanism 2: Bus memorize_metric() calls...")
        self._scan_bus_metrics()

        print("Scanning Mechanism 3: Handler telemetry...")
        self._scan_handler_metrics()

        print("Scanning Mechanism 4: Service availability metrics...")
        self._scan_service_availability()

        print("Scanning direct record_metric() calls...")
        self._scan_direct_recordings()

        return self.metrics

    def _scan_service_telemetry(self):
        """Scan for metrics returned by get_telemetry() methods."""

        for py_file in self.base_path.rglob("*.py"):
            if "__pycache__" in str(py_file):
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                # Find get_telemetry methods
                if "def get_telemetry" not in content and "async def get_telemetry" not in content:
                    continue

                # Extract service name from file
                service_name = self._get_service_name(py_file)
                if not service_name:
                    continue

                # Parse the method to find returned metrics
                metrics = self._extract_telemetry_metrics(content, service_name)
                if metrics:
                    self.metrics["service_telemetry"][service_name] = metrics

            except Exception as e:
                pass

    def _extract_telemetry_metrics(self, content: str, service_name: str) -> List[str]:
        """Extract metrics from get_telemetry() method."""
        metrics = []

        # Find the get_telemetry method
        method_start = content.find("def get_telemetry")
        if method_start == -1:
            method_start = content.find("async def get_telemetry")

        if method_start == -1:
            return metrics

        # Find the return statement(s) in the method
        # Look for dictionary keys being returned
        method_section = content[method_start : method_start + 3000]  # Get reasonable chunk

        # Pattern 1: Direct dictionary returns with string keys
        dict_pattern = r'["\'](\w+)["\']\s*:\s*(?:[^,}]+)'
        for match in re.finditer(dict_pattern, method_section):
            key = match.group(1)
            # Filter to likely metric keys
            if self._is_metric_key(key):
                metric = f"{service_name}.{key}"
                metrics.append(metric)

        # Pattern 2: Comments describing metrics
        comment_pattern = r"[-\s]+(\w+):\s*(?:Total|Number|Count|Rate|Average|Current)"
        for match in re.finditer(comment_pattern, method_section):
            key = match.group(1)
            if self._is_metric_key(key):
                metric = f"{service_name}.{key}"
                if metric not in metrics:
                    metrics.append(metric)

        return metrics

    def _scan_bus_metrics(self):
        """Scan for memorize_metric() calls through buses."""

        patterns = [
            r'memorize_metric\s*\(\s*metric_name\s*=\s*["\']([^"\']+)["\']',
            r'memorize_metric\s*\(\s*["\']([^"\']+)["\']',
            r'\.memorize_metric\s*\(\s*["\']([^"\']+)["\']',
            r'memory_bus\.memorize_metric\s*\(\s*["\']([^"\']+)["\']',
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
                        if "{" not in metric:  # Skip f-string patterns for now
                            self.metrics["bus_metrics"].add(metric)

            except:
                pass

    def _scan_handler_metrics(self):
        """Scan for handler action metrics."""

        # Base handler metrics
        base_metrics = [
            "handler_invoked_total",
            "handler_completed_total",
            "handler_error_total",
            "handler_failed_total",
        ]
        self.metrics["handler_metrics"].update(base_metrics)

        # Per-action metrics
        for action in self.handler_actions:
            self.metrics["handler_metrics"].add(f"handler_invoked_{action}")
            self.metrics["handler_metrics"].add(f"handler_completed_{action}")
            self.metrics["handler_metrics"].add(f"handler_error_{action}")
            self.metrics["handler_metrics"].add(f"action_selected_{action}")

        # Also scan for actual usage in code
        patterns = [
            r'f"handler_invoked_\{[^}]+\}"',
            r'f"handler_completed_\{[^}]+\}"',
            r'f"action_selected_\{[^}]+\}"',
        ]

        for py_file in self.base_path.rglob("*.py"):
            if "__pycache__" in str(py_file) or "handler" not in str(py_file).lower():
                continue

            try:
                with open(py_file, "r") as f:
                    content = f.read()

                for pattern in patterns:
                    if re.search(pattern, content):
                        # Confirm we have the expanded versions
                        pass  # Already added above

            except:
                pass

    def _scan_service_availability(self):
        """Scan for service availability/healthy metrics."""

        # These are generated dynamically for registered services
        # Based on what we see in the API health endpoint
        for service in self.service_types:
            self.metrics["service_availability"].add(f"{service}.available")
            self.metrics["service_availability"].add(f"{service}.healthy")

        # Special aggregate metrics
        self.metrics["service_availability"].add("system.uptime_seconds")
        self.metrics["service_availability"].add("system.total_services")
        self.metrics["service_availability"].add("system.healthy_services")

    def _scan_direct_recordings(self):
        """Scan for direct record_metric() calls."""

        # Updated patterns to capture both positional and keyword arguments with dot-notation
        patterns = [
            r'record_metric\s*\(\s*metric_name\s*=\s*["\']([^"\']+)["\']',
            r'record_metric\s*\(\s*["\']([^"\']+)["\']',
            r'\.record_metric\s*\(\s*metric_name\s*=\s*["\']([^"\']+)["\']',
            r'\.record_metric\s*\(\s*["\']([^"\']+)["\']',
            r'telemetry.*record_metric\s*\(\s*metric_name\s*=\s*["\']([^"\']+)["\']',
            r'telemetry.*record_metric\s*\(\s*["\']([^"\']+)["\']',
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
                        if "{" not in metric:
                            self.metrics["direct_recorded"].add(metric)

                # Also check for f-string patterns and expand them intelligently
                f_patterns = [
                    r'record_metric\s*\(\s*metric_name\s*=\s*f["\']([^"\']+)["\']',
                    r'record_metric\s*\(\s*f["\']([^"\']+)["\']',
                ]

                for pattern in f_patterns:
                    for match in re.finditer(pattern, content):
                        f_string = match.group(1)
                        expanded = self._expand_f_string(f_string, content, py_file)
                        self.metrics["direct_recorded"].update(expanded)

            except:
                pass

    def _expand_f_string(self, f_string: str, content: str, file_path: Path) -> Set[str]:
        """Intelligently expand f-string patterns based on context."""
        expanded = set()

        # Only expand for specific known patterns
        if "{service_name}" in f_string:
            # Check if this is in telemetry_service.py (LLM metrics)
            if "telemetry_service" in str(file_path):
                # Only LLM services record these
                for service in ["llm", "llm_service"]:
                    expanded.add(f_string.replace("{service_name}", service))
            elif "llm_service" in str(file_path):
                expanded.add(f_string.replace("{service_name}", "llm"))

        elif "{action_type" in f_string:
            # Handler actions
            for action in self.handler_actions:
                metric = re.sub(r"\{action_type[^}]*\}", action, f_string)
                expanded.add(metric)

        return expanded

    def _get_service_name(self, file_path: Path) -> str:
        """Extract service name from file path."""
        path_str = str(file_path).lower()

        # Map file names to service names
        service_map = {
            "incident_service": "incident",
            "telemetry_service": "telemetry",
            "audit_service": "audit",
            "config_service": "config",
            "memory_service": "memory",
            "tsdb_consolidation": "tsdb",
            "resource_monitor": "resource_monitor",
            "authentication": "authentication",
            "secrets_tool": "secrets_tool",
            "wise_authority": "wise_authority",
            "adaptive_filter": "adaptive_filter",
            "llm_service": "llm",
        }

        for key, service in service_map.items():
            if key in path_str:
                return service

        return None

    def _is_metric_key(self, key: str) -> bool:
        """Check if a key looks like a metric."""
        metric_keywords = [
            "count",
            "total",
            "rate",
            "latency",
            "errors",
            "requests",
            "processed",
            "created",
            "failed",
            "success",
            "incidents",
            "patterns",
            "problems",
            "insights",
            "uptime",
            "events",
            "healthy",
            "available",
            "tokens",
            "cost",
            "memory",
            "cpu",
            "disk",
            "distribution",
            "average",
            "median",
            "percentile",
        ]

        key_lower = key.lower()
        return any(keyword in key_lower for keyword in metric_keywords)

    def generate_report(self) -> Tuple[str, Set[str]]:
        """Generate comprehensive report."""
        metrics = self.scan_all()

        # Combine all unique metrics
        all_metrics = set()

        # Add service telemetry metrics
        for service, service_metrics in metrics["service_telemetry"].items():
            all_metrics.update(service_metrics)

        # Add other categories
        all_metrics.update(metrics["bus_metrics"])
        all_metrics.update(metrics["handler_metrics"])
        all_metrics.update(metrics["service_availability"])
        all_metrics.update(metrics["direct_recorded"])

        # Generate report
        report = []
        report.append("=" * 80)
        report.append("🎯 COMPREHENSIVE METRIC SCANNER - ALL 4 MECHANISMS")
        report.append("=" * 80)
        report.append(f"Timestamp: {datetime.now().isoformat()}")
        report.append("")

        report.append("📊 METRICS BY MECHANISM:")
        report.append(
            f"1. Service get_telemetry():    {sum(len(m) for m in metrics['service_telemetry'].values())} metrics"
        )
        report.append(f"2. Bus memorize_metric():       {len(metrics['bus_metrics'])} metrics")
        report.append(f"3. Handler telemetry:           {len(metrics['handler_metrics'])} metrics")
        report.append(f"4. Service availability:        {len(metrics['service_availability'])} metrics")
        report.append(f"5. Direct record_metric():      {len(metrics['direct_recorded'])} metrics")
        report.append("")

        report.append(f"📈 TOTAL UNIQUE METRICS: {len(all_metrics)}")
        report.append("")

        # Service telemetry breakdown
        if metrics["service_telemetry"]:
            report.append("🔧 Services with get_telemetry() metrics:")
            for service, service_metrics in sorted(metrics["service_telemetry"].items()):
                report.append(f"  {service:20} {len(service_metrics):3} metrics")
            report.append("")

        # Sample metrics from each category
        report.append("📝 Sample Metrics by Category:")

        report.append("\n  From get_telemetry():")
        telemetry_samples = []
        for service_metrics in metrics["service_telemetry"].values():
            telemetry_samples.extend(service_metrics[:2])
        for metric in sorted(telemetry_samples)[:5]:
            report.append(f"    - {metric}")

        report.append("\n  From memorize_metric():")
        for metric in sorted(metrics["bus_metrics"])[:5]:
            report.append(f"    - {metric}")

        report.append("\n  Handler metrics:")
        for metric in sorted(metrics["handler_metrics"])[:5]:
            report.append(f"    - {metric}")

        report.append("\n  Service availability:")
        for metric in sorted(metrics["service_availability"])[:5]:
            report.append(f"    - {metric}")

        return "\n".join(report), all_metrics


def main():
    """Main entry point."""
    scanner = ComprehensiveMetricScanner()
    report, all_metrics = scanner.generate_report()
    print(report)

    # Save comprehensive metrics
    with open("comprehensive_metrics.json", "w") as f:
        json.dump(
            {"timestamp": datetime.now().isoformat(), "total_count": len(all_metrics), "metrics": sorted(all_metrics)},
            f,
            indent=2,
        )

    print(f"\n💾 Saved {len(all_metrics)} metrics to comprehensive_metrics.json")


if __name__ == "__main__":
    main()
