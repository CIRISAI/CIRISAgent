"""
Telemetry Documentation Parser

Extracts telemetry data from the 35 .md documentation files we created.
Parses metrics, data structures, API patterns, and mission-critical information.
"""

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TelemetryDocParser:
    """Parse telemetry documentation files to extract metrics and metadata"""

    def __init__(self):
        self.base_path = Path("/home/emoore/CIRISAgent/ciris_engine/docs/telemetry")
        self.doc_paths = {
            "buses": self.base_path / "buses",
            "services/graph": self.base_path / "services/graph",
            "services/infrastructure": self.base_path / "services/infrastructure",
            "services/governance": self.base_path / "services/governance",
            "services/runtime": self.base_path / "services/runtime",
            "services/tools": self.base_path / "services/tools",
            "components": self.base_path / "components",
            "adapters": self.base_path / "adapters",
        }

    def parse_all_docs(self) -> List[Dict[str, Any]]:
        """Parse all 35 telemetry documentation files"""
        all_modules = []

        # Define the 35 modules and their locations
        modules_to_parse = [
            # Buses (6)
            ("buses", "LLM_BUS_TELEMETRY.md", "BUS"),
            ("buses", "MEMORY_BUS_TELEMETRY.md", "BUS"),
            ("buses", "COMMUNICATION_BUS_TELEMETRY.md", "BUS"),
            ("buses", "WISE_BUS_TELEMETRY.md", "BUS"),
            ("buses", "TOOL_BUS_TELEMETRY.md", "BUS"),
            ("buses", "RUNTIME_CONTROL_BUS_TELEMETRY.md", "BUS"),
            # Graph Services (6)
            ("services/graph", "MEMORY_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/graph", "CONFIG_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/graph", "TELEMETRY_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/graph", "AUDIT_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/graph", "INCIDENT_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/graph", "TSDB_CONSOLIDATION_SERVICE_TELEMETRY.md", "SERVICE"),
            # Infrastructure Services (7)
            ("services/infrastructure", "TIME_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/infrastructure", "SHUTDOWN_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/infrastructure", "INITIALIZATION_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/infrastructure", "AUTHENTICATION_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/infrastructure", "RESOURCE_MONITOR_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/infrastructure", "DATABASE_MAINTENANCE_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/infrastructure", "SECRETS_SERVICE_TELEMETRY.md", "SERVICE"),
            # Governance Services (4)
            ("services/governance", "WISE_AUTHORITY_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/governance", "ADAPTIVE_FILTER_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/governance", "VISIBILITY_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/governance", "SELF_OBSERVATION_SERVICE_TELEMETRY.md", "SERVICE"),
            # Runtime Services (3)
            ("services/runtime", "LLM_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/runtime", "RUNTIME_CONTROL_SERVICE_TELEMETRY.md", "SERVICE"),
            ("services/runtime", "TASK_SCHEDULER_SERVICE_TELEMETRY.md", "SERVICE"),
            # Tool Services (1)
            ("services/tools", "SECRETS_TOOL_SERVICE_TELEMETRY.md", "SERVICE"),
            # Components (5)
            ("components", "SERVICE_REGISTRY_REGISTRY_TELEMETRY.md", "REGISTRY"),
            ("components", "CIRCUIT_BREAKER_COMPONENT_TELEMETRY.md", "COMPONENT"),
            ("components", "PROCESSING_QUEUE_COMPONENT_TELEMETRY.md", "COMPONENT"),
            ("components", "AGENT_PROCESSOR_PROCESSOR_TELEMETRY.md", "PROCESSOR"),
            ("components", "SERVICE_INITIALIZER_COMPONENT_TELEMETRY.md", "COMPONENT"),
            # Adapters (3)
            ("adapters", "DISCORD_ADAPTER_TELEMETRY.md", "ADAPTER"),
            ("adapters", "API_ADAPTER_TELEMETRY.md", "ADAPTER"),
            ("adapters", "CLI_ADAPTER_TELEMETRY.md", "ADAPTER"),
        ]

        for dir_path, filename, module_type in modules_to_parse:
            doc_path = self.doc_paths[dir_path] / filename
            if doc_path.exists():
                logger.info(f"Parsing {filename}")
                module_data = self.parse_doc(doc_path, module_type)
                if module_data:
                    all_modules.append(module_data)
            else:
                logger.warning(f"Documentation file not found: {doc_path}")

        return all_modules

    def parse_doc(self, doc_path: Path, module_type: str) -> Optional[Dict[str, Any]]:
        """Parse a single telemetry documentation file"""
        try:
            content = doc_path.read_text()

            # Extract module name from filename
            module_name = doc_path.stem.replace("_TELEMETRY", "")

            # Parse sections
            overview = self._extract_section(content, "## Overview", "##")
            metrics = self._parse_metrics_table(content)
            data_structures = self._extract_data_structures(content)
            api_patterns = self._extract_api_patterns(content)
            storage_info = self._extract_storage_info(content)
            limitations = self._extract_section(content, "## Known Limitations", "##")

            # Count metrics by access pattern
            hot_count = sum(1 for m in metrics if m.get("access_pattern") == "HOT")
            warm_count = sum(1 for m in metrics if m.get("access_pattern") == "WARM")
            cold_count = sum(1 for m in metrics if m.get("access_pattern") == "COLD")

            # Determine source file path
            source_path = self._infer_source_path(module_name, module_type)

            return {
                "module_name": module_name,
                "module_type": module_type,
                "doc_path": str(doc_path),
                "module_path": source_path,
                "overview": overview,
                "metrics": metrics,
                "data_structures": data_structures,
                "api_patterns": api_patterns,
                "storage_info": storage_info,
                "limitations": limitations,
                "total_metrics": len(metrics),
                "hot_metrics": hot_count,
                "warm_metrics": warm_count,
                "cold_metrics": cold_count,
            }

        except Exception as e:
            logger.error(f"Error parsing {doc_path}: {e}")
            return None

    def _parse_metrics_table(self, content: str) -> List[Dict[str, Any]]:
        """Parse the metrics table from the documentation"""
        metrics = []

        # Find the telemetry data collected table
        table_pattern = r"\| Metric Name \|.*?\n\|(.*?)\n\n"
        table_match = re.search(table_pattern, content, re.DOTALL)

        if not table_match:
            # Try alternate table format
            table_pattern = r"## Telemetry Data Collected.*?\n(.*?)(?=\n##|\Z)"
            table_match = re.search(table_pattern, content, re.DOTALL)

        if table_match:
            table_content = table_match.group(1) if table_match.lastindex else table_match.group(0)

            # Parse table rows
            row_pattern = r"\| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|"
            for match in re.finditer(row_pattern, table_content):
                if match and not match.group(1).strip().startswith("-"):
                    metric = {
                        "metric_name": match.group(1).strip(),
                        "metric_type": match.group(2).strip(),
                        "storage_location": match.group(3).strip(),
                        "update_frequency": match.group(4).strip(),
                        "access_method": match.group(5).strip(),
                    }

                    # Classify access pattern based on update frequency
                    metric["access_pattern"] = self._classify_access_pattern(
                        metric["update_frequency"], metric["storage_location"]
                    )

                    metrics.append(metric)

        return metrics

    def _classify_access_pattern(self, update_freq: str, storage: str) -> str:
        """Classify metric as HOT, WARM, or COLD based on update frequency and storage"""
        freq_lower = update_freq.lower()
        storage_lower = storage.lower()

        # HOT: Real-time, sub-second updates, in-memory
        if any(term in freq_lower for term in ["real-time", "realtime", "1 second", "100ms", "immediate"]):
            return "HOT"
        elif "memory" in storage_lower and "graph" not in storage_lower:
            return "HOT"

        # COLD: Historical, on-demand, graph/database storage
        elif any(term in freq_lower for term in ["on-demand", "daily", "hourly", "periodic"]):
            return "COLD"
        elif "graph" in storage_lower or "database" in storage_lower:
            return "COLD"

        # WARM: Everything else
        else:
            return "WARM"

    def _extract_section(self, content: str, start_marker: str, end_marker: str) -> str:
        """Extract content between section markers"""
        pattern = f"{re.escape(start_marker)}(.*?)(?={re.escape(end_marker)}|\\Z)"
        match = re.search(pattern, content, re.DOTALL)
        return match.group(1).strip() if match else ""

    def _extract_data_structures(self, content: str) -> List[Dict[str, str]]:
        """Extract data structure definitions from the documentation"""
        structures = []

        # Find data structures section
        section = self._extract_section(content, "## Data Structures", "##")
        if not section:
            section = self._extract_section(content, "### Data Structures", "###")

        if section:
            # Extract code blocks with structure names
            pattern = r"###\s+([^\n]+)\n```(?:python|json)?\n(.*?)\n```"
            for match in re.finditer(pattern, section, re.DOTALL):
                structures.append({"name": match.group(1).strip(), "definition": match.group(2).strip()})

        return structures

    def _extract_api_patterns(self, content: str) -> Dict[str, Any]:
        """Extract API access patterns from the documentation"""
        api_info = {"current_access": None, "recommended_endpoints": []}

        # Extract current access pattern
        current = self._extract_section(content, "### Current Access", "###")
        if current:
            api_info["current_access"] = current

        # Extract recommended endpoints
        recommended = self._extract_section(content, "### Recommended Endpoint", "##")
        if not recommended:
            recommended = self._extract_section(content, "### Recommended Endpoints", "##")

        if recommended:
            # Parse endpoint definitions
            endpoint_pattern = r"```\n((?:GET|POST|PUT|DELETE|PATCH|WS)\s+[^\n]+)\n"
            for match in re.finditer(endpoint_pattern, recommended):
                api_info["recommended_endpoints"].append(match.group(1).strip())

        return api_info

    def _extract_storage_info(self, content: str) -> Dict[str, Any]:
        """Extract storage information from the documentation"""
        storage = {"graph_storage": False, "in_memory": False, "database": False, "redis": False, "file": False}

        # Check for storage patterns in content
        content_lower = content.lower()

        if "graph storage" in content_lower or "graph memory" in content_lower:
            storage["graph_storage"] = True
        if "in-memory" in content_lower or "in memory" in content_lower:
            storage["in_memory"] = True
        if "database" in content_lower or "sqlite" in content_lower:
            storage["database"] = True
        if "redis" in content_lower:
            storage["redis"] = True
        if "file" in content_lower or "log" in content_lower:
            storage["file"] = True

        return storage

    def _infer_source_path(self, module_name: str, module_type: str) -> str:
        """Infer the source code path from module name and type"""
        base = "ciris_engine/logic"

        # Clean up module name
        name = module_name.lower().replace("_telemetry", "")

        if module_type == "BUS":
            return f"{base}/buses/{name}.py"
        elif module_type == "SERVICE":
            # Services are in various subdirectories
            if (
                "memory" in name
                or "config" in name
                or "telemetry" in name
                or "audit" in name
                or "incident" in name
                or "tsdb" in name
            ):
                return f"{base}/services/graph/{name}.py"
            elif any(
                x in name
                for x in ["time", "shutdown", "initialization", "authentication", "resource", "database", "secrets"]
            ):
                return f"{base}/services/infrastructure/{name}.py"
            elif any(x in name for x in ["wise", "adaptive", "visibility", "self_observation"]):
                return f"{base}/services/governance/{name}.py"
            elif any(x in name for x in ["llm", "runtime", "task"]):
                return f"{base}/services/runtime/{name}.py"
            elif "tool" in name:
                return f"{base}/services/tools/{name}.py"
        elif module_type == "COMPONENT":
            if "circuit" in name:
                return f"{base}/registries/circuit_breaker.py"
            elif "queue" in name:
                return f"{base}/runtime/processing_queue.py"
            elif "initializer" in name:
                return f"{base}/initialization/service_initializer.py"
        elif module_type == "REGISTRY":
            return f"{base}/registries/base.py"
        elif module_type == "PROCESSOR":
            return f"{base}/core/agent_processor.py"
        elif module_type == "ADAPTER":
            adapter_name = name.replace("_adapter", "").lower()
            return f"{base}/adapters/{adapter_name}/adapter.py"

        return f"{base}/{name}.py"
