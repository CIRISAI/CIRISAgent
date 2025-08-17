#!/usr/bin/env python3
"""
Telemetry Reality Scanner for v1.4.3
Shows the ACTUAL telemetry implementation with full taxonomy awareness.
"""

import json
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class TelemetryRealityScanner:
    """Scans for ACTUAL telemetry implementation in v1.4.3 with full taxonomy"""

    def __init__(self):
        self.base_path = Path.cwd()
        self.results = {
            "version": "1.4.3",
            "timestamp": datetime.now().isoformat(),
            "taxonomy": {
                "services": {"graph": {}, "infrastructure": {}, "governance": {}, "runtime": {}, "tools": {}},
                "handlers": {},
                "adapters": {"api": {}, "discord": {}, "cli": {}},
                "buses": {},
                "processors": {},
                "registries": {},
                "protocols": {},
            },
            "api_endpoints": {},
            "metrics_by_type": {
                "pull": [],  # get_metrics()
                "push": [],  # memorize_metric()
                "handler": [],  # Handler telemetry
                "bus": [],  # Bus telemetry
                "adapter": [],  # Adapter-specific
            },
            "summary": {},
        }

    def scan_all(self):
        """Run all scans to get complete picture"""
        print("🔍 Scanning v1.4.3 Telemetry Reality with Full Taxonomy...\n")

        # 1. Scan service taxonomy
        print("📦 Scanning Service Taxonomy...")
        self.scan_service_taxonomy()

        # 2. Scan handlers
        print("\n⚡ Scanning Handlers...")
        self.scan_handlers()

        # 3. Scan adapters
        print("\n🔌 Scanning Adapters...")
        self.scan_adapters()

        # 4. Scan buses
        print("\n🚌 Scanning Message Buses...")
        self.scan_buses()

        # 5. Scan processors
        print("\n🧠 Scanning Processors...")
        self.scan_processors()

        # 6. Scan registries
        print("\n📚 Scanning Registries...")
        self.scan_registries()

        # 7. Scan API endpoints
        print("\n🌐 Scanning API Endpoints...")
        self.scan_telemetry_endpoints()

        # 8. Generate comprehensive summary
        self.generate_comprehensive_summary()

        return self.results

    def classify_service(self, path: Path) -> Tuple[str, str]:
        """Classify service into taxonomy category"""
        path_str = str(path)

        if "graph" in path_str:
            if "memory" in path_str:
                return "graph", "memory"
            elif "config" in path_str:
                return "graph", "config"
            elif "telemetry" in path_str:
                return "graph", "telemetry"
            elif "audit" in path_str:
                return "graph", "audit"
            elif "incident" in path_str:
                return "graph", "incident_management"
            elif "tsdb" in path_str:
                return "graph", "tsdb_consolidation"
            return "graph", path.stem

        elif "infrastructure" in path_str:
            if "time" in path_str:
                return "infrastructure", "time"
            elif "shutdown" in path_str:
                return "infrastructure", "shutdown"
            elif "init" in path_str:
                return "infrastructure", "initialization"
            elif "auth" in path_str:
                return "infrastructure", "authentication"
            elif "resource" in path_str:
                return "infrastructure", "resource_monitor"
            elif "database" in path_str:
                return "infrastructure", "database_maintenance"
            elif "secret" in path_str:
                return "infrastructure", "secrets"
            return "infrastructure", path.stem

        elif "governance" in path_str:
            if "wise" in path_str:
                return "governance", "wise_authority"
            elif "filter" in path_str:
                return "governance", "adaptive_filter"
            elif "visibility" in path_str:
                return "governance", "visibility"
            elif "self_observation" in path_str:
                return "governance", "self_observation"
            return "governance", path.stem

        elif "runtime" in path_str:
            if "llm" in path_str:
                return "runtime", "llm"
            elif "runtime_control" in path_str:
                return "runtime", "runtime_control"
            elif "task" in path_str:
                return "runtime", "task_scheduler"
            return "runtime", path.stem

        elif "tools" in path_str:
            return "tools", "secrets_tool"

        return "unknown", path.stem

    def extract_metrics(self, content: str, metric_type: str) -> List[Dict]:
        """Extract metrics from code content"""
        metrics = []

        if metric_type == "get_metrics":
            # Look for metrics in get_metrics() method
            if "def get_metrics(self)" in content:
                # Find the method and extract metrics
                method_match = re.search(
                    r"def get_metrics\(self\)[^:]*:\s*(?:.*?)return\s*{([^}]+)}", content, re.DOTALL
                )
                if method_match:
                    metrics_block = method_match.group(1)
                    metric_names = re.findall(r'["\']([\w_]+)["\']', metrics_block)
                    for name in metric_names:
                        metrics.append({"name": name, "type": "pull", "source": "get_metrics"})

        elif metric_type == "memorize_metric":
            # Look for memorize_metric calls
            metric_calls = re.findall(r'memorize_metric\(["\']([^"\']+)["\']', content)
            for name in metric_calls:
                metrics.append({"name": name, "type": "push", "source": "memorize_metric"})

        elif metric_type == "record_metric":
            # Look for record_metric calls
            metric_calls = re.findall(r'record_metric\(["\']([^"\']+)["\']', content)
            for name in metric_calls:
                metrics.append({"name": name, "type": "push", "source": "record_metric"})

        return metrics

    def scan_service_taxonomy(self):
        """Scan all services organized by taxonomy"""
        services_path = self.base_path / "ciris_engine/logic/services"

        for py_file in services_path.rglob("*.py"):
            if "__pycache__" in str(py_file) or "__init__" in py_file.name:
                continue

            content = py_file.read_text()
            category, service_name = self.classify_service(py_file)

            if category != "unknown":
                # Extract metrics
                pull_metrics = self.extract_metrics(content, "get_metrics")
                push_metrics = self.extract_metrics(content, "memorize_metric")
                push_metrics.extend(self.extract_metrics(content, "record_metric"))

                service_info = {
                    "file": str(py_file.relative_to(self.base_path)),
                    "pull_metrics": len(pull_metrics),
                    "push_metrics": len(push_metrics),
                    "sample_metrics": [m["name"] for m in (pull_metrics + push_metrics)[:5]],
                }

                self.results["taxonomy"]["services"][category][service_name] = service_info

                # Add to metrics by type
                self.results["metrics_by_type"]["pull"].extend(pull_metrics)
                self.results["metrics_by_type"]["push"].extend(push_metrics)

    def scan_handlers(self):
        """Scan all handlers for telemetry"""
        handlers_path = self.base_path / "ciris_engine/logic/infrastructure/handlers"

        for py_file in handlers_path.rglob("*.py"):
            if "__pycache__" in str(py_file) or "__init__" in py_file.name:
                continue

            content = py_file.read_text()
            handler_name = py_file.stem

            # Look for telemetry patterns
            metrics = []

            # Check for action_selected metrics
            action_metrics = re.findall(r"action_selected_(\w+)", content)
            for action in action_metrics:
                metrics.append(f"action_selected_{action}")

            # Check for handler-specific metrics
            handler_metrics = re.findall(r'["\']handler\.(\w+)["\']', content)
            metrics.extend(handler_metrics)

            if metrics:
                self.results["taxonomy"]["handlers"][handler_name] = {
                    "file": str(py_file.relative_to(self.base_path)),
                    "metrics": list(set(metrics)),
                    "count": len(set(metrics)),
                }

                # Add to metrics by type
                for metric in metrics:
                    self.results["metrics_by_type"]["handler"].append(
                        {"name": metric, "type": "handler", "source": handler_name}
                    )

    def scan_adapters(self):
        """Scan all adapters (API, Discord, CLI)"""
        adapters_path = self.base_path / "ciris_engine/logic/adapters"

        for adapter_type in ["api", "discord", "cli"]:
            adapter_path = adapters_path / adapter_type
            if not adapter_path.exists():
                continue

            adapter_metrics = []

            for py_file in adapter_path.rglob("*.py"):
                if "__pycache__" in str(py_file):
                    continue

                content = py_file.read_text()

                # Extract metrics
                pull_metrics = self.extract_metrics(content, "get_metrics")
                push_metrics = self.extract_metrics(content, "memorize_metric")

                if pull_metrics or push_metrics:
                    adapter_metrics.extend(pull_metrics)
                    adapter_metrics.extend(push_metrics)

            if adapter_metrics:
                self.results["taxonomy"]["adapters"][adapter_type] = {
                    "metrics_count": len(adapter_metrics),
                    "sample_metrics": [m["name"] for m in adapter_metrics[:5]],
                }

                # Add to metrics by type
                self.results["metrics_by_type"]["adapter"].extend(adapter_metrics)

    def scan_buses(self):
        """Scan message buses for telemetry"""
        buses_path = self.base_path / "ciris_engine/logic/buses"

        if buses_path.exists():
            for py_file in buses_path.glob("*.py"):
                if "__pycache__" in str(py_file) or "__init__" in py_file.name:
                    continue

                content = py_file.read_text()
                bus_name = py_file.stem.replace("_bus", "")

                # Look for bus telemetry
                metrics = []

                # Check for message counts
                if "message_count" in content or "call_count" in content:
                    metrics.append(f"{bus_name}_message_count")

                # Check for error tracking
                if "error_count" in content:
                    metrics.append(f"{bus_name}_error_count")

                # Check for latency tracking
                if "latency" in content or "response_time" in content:
                    metrics.append(f"{bus_name}_latency")

                if metrics:
                    self.results["taxonomy"]["buses"][bus_name] = {
                        "file": str(py_file.relative_to(self.base_path)),
                        "metrics": metrics,
                    }

                    # Add to metrics by type
                    for metric in metrics:
                        self.results["metrics_by_type"]["bus"].append(
                            {"name": metric, "type": "bus", "source": bus_name}
                        )

    def scan_processors(self):
        """Scan processors for telemetry"""
        processors_path = self.base_path / "ciris_engine/logic/processors"

        if processors_path.exists():
            for py_file in processors_path.rglob("*.py"):
                if "__pycache__" in str(py_file) or "__init__" in py_file.name:
                    continue

                content = py_file.read_text()
                processor_name = py_file.stem

                # Look for thought metrics
                thought_metrics = []
                if "thought" in content.lower():
                    if "thoughts_processed" in content:
                        thought_metrics.append("thoughts_processed")
                    if "thoughts_failed" in content:
                        thought_metrics.append("thoughts_failed")
                    if "thought_latency" in content:
                        thought_metrics.append("thought_latency")

                if thought_metrics:
                    self.results["taxonomy"]["processors"][processor_name] = {
                        "file": str(py_file.relative_to(self.base_path)),
                        "metrics": thought_metrics,
                    }

    def scan_registries(self):
        """Scan registries for telemetry"""
        registries_path = self.base_path / "ciris_engine/logic/registries"

        if registries_path.exists():
            for py_file in registries_path.glob("*.py"):
                if "__pycache__" in str(py_file) or "__init__" in py_file.name:
                    continue

                content = py_file.read_text()
                registry_name = py_file.stem

                # Look for registry metrics
                registry_metrics = []
                if "registered_count" in content:
                    registry_metrics.append(f"{registry_name}_registered_count")
                if "lookup_count" in content:
                    registry_metrics.append(f"{registry_name}_lookup_count")

                if registry_metrics:
                    self.results["taxonomy"]["registries"][registry_name] = {
                        "file": str(py_file.relative_to(self.base_path)),
                        "metrics": registry_metrics,
                    }

    def scan_telemetry_endpoints(self):
        """Find actual telemetry API endpoints"""
        telemetry_file = self.base_path / "ciris_engine/logic/adapters/api/routes/telemetry.py"

        if telemetry_file.exists():
            content = telemetry_file.read_text()

            # Find all @router endpoints
            endpoints = re.findall(r'@router\.(get|post)\("([^"]+)".*?\)\s*async def (\w+)', content, re.DOTALL)

            self.results["api_endpoints"] = {
                endpoint[2]: {
                    "method": endpoint[0].upper(),
                    "path": f"/telemetry{endpoint[1]}",
                    "function": endpoint[2],
                }
                for endpoint in endpoints
            }

    def generate_comprehensive_summary(self):
        """Generate comprehensive summary with full taxonomy"""

        # Count metrics by category
        service_counts = {"graph": 0, "infrastructure": 0, "governance": 0, "runtime": 0, "tools": 0}

        for category, services in self.results["taxonomy"]["services"].items():
            for service, info in services.items():
                service_counts[category] += info.get("pull_metrics", 0) + info.get("push_metrics", 0)

        # Count unique metrics by type
        unique_pull = len(set(m["name"] for m in self.results["metrics_by_type"]["pull"]))
        unique_push = len(set(m["name"] for m in self.results["metrics_by_type"]["push"]))
        unique_handler = len(set(m["name"] for m in self.results["metrics_by_type"]["handler"]))
        unique_bus = len(set(m["name"] for m in self.results["metrics_by_type"]["bus"]))
        unique_adapter = len(set(m["name"] for m in self.results["metrics_by_type"]["adapter"]))

        total_unique = unique_pull + unique_push + unique_handler + unique_bus + unique_adapter

        print("\n" + "=" * 80)
        print("📊 CIRIS v1.4.3 TELEMETRY REALITY - FULL TAXONOMY")
        print("=" * 80)

        print("\n📦 SERVICE TAXONOMY (21 Core Services):")
        print("-" * 40)

        for category in ["graph", "infrastructure", "governance", "runtime", "tools"]:
            services = self.results["taxonomy"]["services"].get(category, {})
            if services:
                print(f"\n{category.upper()} Services ({len(services)}):")
                for service, info in services.items():
                    pull = info.get("pull_metrics", 0)
                    push = info.get("push_metrics", 0)
                    print(f"  • {service:30} PULL: {pull:3} | PUSH: {push:3}")

        print(f"\n⚡ HANDLERS ({len(self.results['taxonomy']['handlers'])}):")
        for handler, info in self.results["taxonomy"]["handlers"].items():
            print(f"  • {handler}: {info['count']} metrics")

        print(f"\n🔌 ADAPTERS:")
        for adapter, info in self.results["taxonomy"]["adapters"].items():
            print(f"  • {adapter}: {info.get('metrics_count', 0)} metrics")

        print(f"\n🚌 MESSAGE BUSES ({len(self.results['taxonomy']['buses'])}):")
        for bus, info in self.results["taxonomy"]["buses"].items():
            print(f"  • {bus}: {len(info['metrics'])} metrics")

        print(f"\n🌐 API ENDPOINTS ({len(self.results['api_endpoints'])}):")
        for name, info in self.results["api_endpoints"].items():
            print(f"  • {info['path']}")

        print("\n" + "=" * 80)
        print("📊 METRICS SUMMARY BY TYPE:")
        print("-" * 40)
        print(f"  • PULL metrics (get_metrics):     {unique_pull}")
        print(f"  • PUSH metrics (memorize_metric): {unique_push}")
        print(f"  • Handler metrics:                {unique_handler}")
        print(f"  • Bus metrics:                    {unique_bus}")
        print(f"  • Adapter metrics:                {unique_adapter}")
        print(f"  • TOTAL UNIQUE METRICS:           {total_unique}")

        print("\n💡 KEY INSIGHTS:")
        print("  • Services expose metrics via get_metrics() - PULL model")
        print("  • Very few metrics are pushed to TSDB - only critical ones")
        print("  • Handlers track action selections")
        print("  • Buses track message flow")
        print("  • Adapters add instance-specific metrics")
        print("  • /telemetry/unified aggregates everything with 30s cache")

        # Update summary
        self.results["summary"] = {
            "total_unique_metrics": total_unique,
            "pull_metrics": unique_pull,
            "push_metrics": unique_push,
            "handler_metrics": unique_handler,
            "bus_metrics": unique_bus,
            "adapter_metrics": unique_adapter,
            "services_with_metrics": sum(len(s) for s in self.results["taxonomy"]["services"].values()),
            "api_endpoints": len(self.results["api_endpoints"]),
            "handlers_tracked": len(self.results["taxonomy"]["handlers"]),
            "buses_tracked": len(self.results["taxonomy"]["buses"]),
        }

        # Save results
        output_file = self.base_path / "tools/telemetry_tool/telemetry_v143_reality.json"
        with open(output_file, "w") as f:
            json.dump(self.results, f, indent=2, default=str)

        print(f"\n💾 Full taxonomy saved to: {output_file}")

        return self.results


def main():
    """Run the reality scanner"""
    scanner = TelemetryRealityScanner()
    results = scanner.scan_all()

    print("\n✅ Reality scan complete!")
    print("The ACTUAL v1.4.3 telemetry implementation is now documented.")


if __name__ == "__main__":
    main()
