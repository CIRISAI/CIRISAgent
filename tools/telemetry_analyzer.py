#!/usr/bin/env python3
"""
Telemetry Analyzer - Rigorously count and categorize metric sources.

IMPORTANT: This tool counts SOURCE TYPES, not instances.
- Adapters can have multiple instances (e.g., discord_datum, discord_ciris)
- Each adapter instance provides the SAME metrics structure
- We count the TYPE (e.g., DiscordAdapter), not instances
"""

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Set, Tuple


class SimpleTelemetryAnalyzer:
    """Count metric source TYPES definitively."""

    def __init__(self):
        self.project_root = Path("/home/emoore/CIRISAgent")
        self.sources_by_category = {}
        self.duplicate_analysis = {}
        self.instance_vs_type_notes = []

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
        """Extract clean source name from actual class definitions."""
        path = Path(file_path)
        name = path.stem

        # Read file to find actual class names with metric methods
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Find classes that actually have metric methods
            class_pattern = r"class\s+(\w+).*?:"
            method_patterns = [
                r"def get_metrics",
                r"def _collect_metrics",
                r"def _collect_custom_metrics",
                r"def get_telemetry",
                r"def collect_telemetry",
            ]

            import re

            classes = re.findall(class_pattern, content)

            # Find which class has the metric methods
            for cls in classes:
                # Find the class definition and check if it has metric methods
                class_match = re.search(rf"class\s+{cls}.*?(?=class\s|\Z)", content, re.DOTALL)
                if class_match:
                    class_body = class_match.group()
                    for pattern in method_patterns:
                        if pattern in class_body:
                            return cls  # Return the actual class name
        except:
            pass

        # Fallback: Map common patterns
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
        elif "registries/base" in str(path):
            return "ServiceRegistry"
        elif "processors/core/base" in str(path):
            return "BaseProcessor"
        elif "processors/core/main" in str(path):
            return "AgentProcessor"

        # Default: capitalize name
        return "".join(word.capitalize() for word in name.split("_"))

    def _categorize(self, file_path: str) -> str:
        """Categorize a source with rigorous classification."""
        path = str(file_path)

        # CRITICAL: Distinguish between types and instances
        # Base/Abstract classes - these are TYPES not instances
        if "/services/base" in path or "base_" in Path(file_path).name:
            return "Base Classes (Abstract)"

        # Core Services - actual service implementations
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

        # Infrastructure Components
        elif "/buses/" in path:
            return "Message Buses"
        elif "/registries/" in path:
            if "circuit_breaker" in path:
                return "Core Components"
            else:
                return "Core Components"
        elif "/processors/" in path:
            return "Core Components"
        elif "/runtime/service_initializer" in path:
            return "Core Components"

        # Adapters - These can have MULTIPLE INSTANCES
        elif "/adapters/" in path:
            # Note: Each adapter TYPE can spawn multiple instances
            self.instance_vs_type_notes.append(
                f"Adapter found: {Path(file_path).name} - can have multiple instances at runtime"
            )
            return "Adapters (Types)"

        # Helpers and utilities - NOT true metric sources
        elif "/routes/" in path:
            return "Helpers/Routes (Not Sources)"
        elif "example" in path.lower():
            return "Examples (Not Sources)"
        elif "/telemetry/" in path and "hot_cold" in path:
            return "Configuration (Not Sources)"
        elif "/persistence/" in path:
            # Database maintenance is a real service
            if "maintenance" in path:
                return "Infrastructure Services"
            else:
                return "Other"
        elif "/secrets/" in path:
            # Secrets service is real
            return "Infrastructure Services"
        else:
            return "Other"

    def print_report(self):
        """Print the rigorous analysis."""
        total = self.analyze()

        print("\n" + "=" * 80)
        print("📊 CIRIS v1.4.3 METRIC SOURCE TYPES - RIGOROUS COUNT")
        print("=" * 80)
        print(f"Generated: {datetime.now().isoformat()}\n")

        # CRITICAL CLARIFICATION
        print("⚠️  CRITICAL UNDERSTANDING:")
        print("-" * 60)
        print("• This counts SOURCE TYPES, not instances")
        print("• Adapters can have MULTIPLE runtime instances:")
        print("  - discord_datum, discord_ciris (both DiscordAdapter type)")
        print("  - api_datum, api_ciris (both APIAdapter type)")
        print("• Each instance shares the SAME metrics structure")
        print("• We count the TYPE once, regardless of instances\n")

        # Count totals by category
        category_totals = {}
        all_sources = set()
        true_sources = set()  # Only count real metric sources

        for category, sources in sorted(self.sources_by_category.items()):
            category_totals[category] = len(sources)
            for source in sources:
                all_sources.add(source["name"])
                # Exclude non-sources from true count
                if "Not Sources" not in category and "Abstract" not in category:
                    true_sources.add(source["name"])

        # Define category order with clear groupings
        category_order = [
            # Real metric sources
            "Graph Services",
            "Infrastructure Services",
            "Governance Services",
            "Runtime Services",
            "Tool Services",
            "Message Buses",
            "Core Components",
            "Adapters (Types)",
            # Abstract/base classes
            "Base Classes (Abstract)",
            # Not real sources
            "Helpers/Routes (Not Sources)",
            "Examples (Not Sources)",
            "Configuration (Not Sources)",
            # Uncategorized
            "Other",
        ]

        print("\n🔍 DETAILED BREAKDOWN BY CATEGORY:")
        print("=" * 80)

        # Track which are real sources
        real_source_categories = [
            "Graph Services",
            "Infrastructure Services",
            "Governance Services",
            "Runtime Services",
            "Tool Services",
            "Message Buses",
            "Core Components",
            "Adapters (Types)",
        ]

        real_source_count = 0

        for category in category_order:
            if category not in self.sources_by_category:
                continue

            sources = self.sources_by_category[category]
            if not sources:
                continue

            # Mark real vs non-real sources
            if category in real_source_categories:
                emoji = "✅"
                real_source_count += len(sources)
            elif "Abstract" in category:
                emoji = "📐"
            else:
                emoji = "❌"

            print(f"\n{emoji} {category} ({len(sources)} types):")
            print("-" * 60)

            for source in sorted(sources, key=lambda x: x["name"]):
                methods = ", ".join(source["methods"])
                print(f"  • {source['name']:35} [{methods}]")

        # Identify duplicates or confusion
        print("\n\n🔄 DUPLICATE/CONFUSION ANALYSIS:")
        print("=" * 80)

        # Check for TimeService duplication
        time_service_locations = []
        for category, sources in self.sources_by_category.items():
            for source in sources:
                if source["name"] == "TimeService":
                    time_service_locations.append((category, source["path"]))

        if len(time_service_locations) > 1:
            print("⚠️  TimeService found in multiple categories:")
            for cat, path in time_service_locations:
                print(f"   - {cat}: {path}")

        # Check for Secrets confusion
        secrets_services = []
        for category, sources in self.sources_by_category.items():
            for source in sources:
                if "Secret" in source["name"]:
                    secrets_services.append((source["name"], category))

        if len(secrets_services) > 1:
            print("\n⚠️  Multiple Secrets-related services:")
            for name, cat in secrets_services:
                print(f"   - {name} in {cat}")

        # Print adapter instance notes
        if self.instance_vs_type_notes:
            print("\n\n📝 ADAPTER INSTANCE VS TYPE NOTES:")
            print("=" * 80)
            for note in set(self.instance_vs_type_notes):
                print(f"• {note}")

        # Print final summary
        print("\n\n" + "=" * 80)
        print("🎯 THE DEFINITIVE ANSWER:")
        print("-" * 60)
        print(f"  Total Files Analyzed:        {sum(category_totals.values())}")
        print(f"  All Unique Class Names:      {len(all_sources)}")
        print(f"  TRUE METRIC SOURCE TYPES:    {len(true_sources)}")
        print("\n  Real Source Breakdown:")

        for category in real_source_categories:
            if category in category_totals:
                print(f"    • {category:25} {category_totals[category]:2} types")

        print(f"\n  Total Real Sources: {real_source_count}")

        print("\n  Excluded from count:")
        for category in category_order:
            if category not in real_source_categories and category in category_totals:
                print(f"    ❌ {category:25} {category_totals[category]:2} files")

        print("\n" + "=" * 80)
        print(f"  ✅ CIRIS v1.4.3 has {len(true_sources)} unique metric SOURCE TYPES")
        print("  📌 These TYPES can spawn multiple INSTANCES at runtime")
        print("=" * 80)


if __name__ == "__main__":
    analyzer = SimpleTelemetryAnalyzer()
    analyzer.print_report()
