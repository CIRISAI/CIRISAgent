#!/usr/bin/env python3
"""
Simplified Telemetry Analyzer - Just count the sources and categorize them.
"""

import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Set


class SimpleTelemetryAnalyzer:
    """Count metric sources definitively."""

    def __init__(self):
        self.project_root = Path("/home/emoore/CIRISAgent")
        self.sources_by_category = {}

    def analyze(self):
        """Find and categorize all metric sources."""

        # Find all files with metric methods
        cmd = 'grep -r "def get_metrics\\|def _collect_metrics\\|def _collect_custom_metrics\\|def get_telemetry" ciris_engine --include="*.py" -l 2>/dev/null'
        files = os.popen(cmd).read().strip().split("\n")

        all_sources = []

        for file_path in files:
            if file_path and os.path.exists(file_path):
                source_name = self._get_source_name(file_path)
                category = self._categorize(file_path)

                if category not in self.sources_by_category:
                    self.sources_by_category[category] = []

                # Check what type of metrics this source has
                has_get_metrics = self._check_pattern(file_path, "def get_metrics")
                has_collect = self._check_pattern(file_path, "def _collect_metrics")
                has_custom = self._check_pattern(file_path, "def _collect_custom_metrics")
                has_telemetry = self._check_pattern(file_path, "def get_telemetry")

                metric_type = []
                if has_get_metrics:
                    metric_type.append("get_metrics")
                if has_collect:
                    metric_type.append("_collect_metrics")
                if has_custom:
                    metric_type.append("_collect_custom_metrics")
                if has_telemetry:
                    metric_type.append("get_telemetry")

                self.sources_by_category[category].append(
                    {
                        "name": source_name,
                        "path": file_path.replace(str(self.project_root) + "/", ""),
                        "methods": metric_type,
                    }
                )
                all_sources.append(source_name)

        return len(set(all_sources))

    def _check_pattern(self, file_path: str, pattern: str) -> bool:
        """Check if a pattern exists in file."""
        try:
            with open(file_path, "r") as f:
                content = f.read()
                return pattern in content
        except:
            return False

    def _get_source_name(self, file_path: str) -> str:
        """Extract clean source name."""
        path = Path(file_path)
        name = path.stem

        # Map common patterns
        mappings = {
            "base_service": "BaseService",
            "base_graph_service": "BaseGraphService",
            "base_infrastructure_service": "BaseInfrastructureService",
            "base_scheduled_service": "BaseScheduledService",
            "llm_service": "LLMService",
            "memory_service": "MemoryService",
            "telemetry_service": "TelemetryService",
            "audit_service": "AuditService",
            "config_service": "ConfigService",
            "incident_service": "IncidentManagementService",
            "tsdb_consolidation": "TSDBConsolidationService",
            "authentication": "AuthenticationService",
            "resource_monitor": "ResourceMonitorService",
            "wise_authority": "WiseAuthorityService",
            "filter": "AdaptiveFilterService",
            "visibility": "VisibilityService",
            "self_observation": "SelfObservationService",
            "control_service": "RuntimeControlService",
            "scheduler": "TaskSchedulerService",
            "secrets_tool_service": "SecretsToolService",
            "shutdown": "ShutdownService",
            "initialization": "InitializationService",
            "time": "TimeService",
            "maintenance": "DatabaseMaintenanceService",
            "circuit_breaker": "CircuitBreaker",
            "llm_bus": "LLMBus",
            "memory_bus": "MemoryBus",
            "communication_bus": "CommunicationBus",
            "tool_bus": "ToolBus",
            "runtime_control_bus": "RuntimeControlBus",
            "wise_bus": "WiseBus",
            "discord_adapter": "DiscordAdapter",
            "cli_adapter": "CLIAdapter",
            "main_processor": "MainProcessor",
            "base_processor": "BaseProcessor",
            "queue_status": "QueueStatus",
            "correlations": "Correlations",
            "service_initializer": "ServiceInitializer",
        }

        for key, value in mappings.items():
            if key in name:
                return value

        # Handle API adapter specially
        if "api/adapter" in str(path):
            return "APIAdapter"
        elif "api/routes/telemetry.py" in str(path):
            return "TelemetryRoute"
        elif "api/routes/telemetry_helpers" in str(path):
            return "TelemetryHelpers"
        elif "api/routes/telemetry_logs_reader" in str(path):
            return "TelemetryLogsReader"
        elif "secrets/service" in str(path):
            return "SecretsService"
        elif "hot_cold_config" in str(path):
            return "HotColdConfig"

        # Default: capitalize name
        return "".join(word.capitalize() for word in name.split("_"))

    def _categorize(self, file_path: str) -> str:
        """Categorize a source."""
        path = str(file_path)

        if "/services/base" in path:
            return "Base Services"
        elif "/services/graph/" in path:
            return "Graph Services"
        elif "/services/infrastructure/" in path or "/services/lifecycle/" in path:
            return "Infrastructure Services"
        elif "/services/governance/" in path or "/services/adaptation/" in path:
            return "Governance Services"
        elif "/services/runtime/" in path:
            return "Runtime Services"
        elif "/services/tools/" in path:
            return "Tool Services"
        elif "/buses/" in path:
            return "Message Buses"
        elif "/adapters/" in path:
            return "Adapters"
        elif "/processors/" in path:
            return "Processors"
        elif "/handlers/" in path:
            return "Handlers"
        elif "/registries/" in path:
            return "Registries"
        elif "/routes/" in path:
            return "API Routes"
        else:
            return "Other"

    def print_report(self):
        """Print the analysis."""
        total = self.analyze()

        print("\n" + "=" * 80)
        print("📊 CIRIS v1.4.3 METRIC SOURCES - DEFINITIVE COUNT")
        print("=" * 80)
        print(f"Generated: {datetime.now().isoformat()}\n")

        # Count totals by category
        category_totals = {}
        all_sources = set()

        for category, sources in sorted(self.sources_by_category.items()):
            category_totals[category] = len(sources)
            for source in sources:
                all_sources.add(source["name"])

        # Print by category
        for category in [
            "Base Services",
            "Graph Services",
            "Infrastructure Services",
            "Governance Services",
            "Runtime Services",
            "Tool Services",
            "Message Buses",
            "Adapters",
            "API Routes",
            "Processors",
            "Handlers",
            "Registries",
            "Other",
        ]:
            if category not in self.sources_by_category:
                continue

            sources = self.sources_by_category[category]
            if not sources:
                continue

            print(f"\n📦 {category} ({len(sources)} sources):")
            print("-" * 60)

            for source in sorted(sources, key=lambda x: x["name"]):
                methods = ", ".join(source["methods"])
                print(f"  • {source['name']:35} [{methods}]")

        # Print summary
        print("\n" + "=" * 80)
        print("🎯 THE DEFINITIVE ANSWER:")
        print("-" * 60)
        print(f"  Total Unique Metric Sources: {len(all_sources)}")
        print(f"  Total Files with Metrics:    {sum(category_totals.values())}")
        print("\n  Breakdown by Category:")
        for category, count in sorted(category_totals.items()):
            print(f"    • {category:25} {count:2} sources")

        print("\n" + "=" * 80)
        print(f"  ✅ CIRIS v1.4.3 has {len(all_sources)} unique metric sources")
        print("=" * 80)


if __name__ == "__main__":
    analyzer = SimpleTelemetryAnalyzer()
    analyzer.print_report()
