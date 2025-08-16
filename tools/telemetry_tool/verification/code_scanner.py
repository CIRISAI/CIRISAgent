#!/usr/bin/env python3
"""
Code scanner implementation for finding metrics in source code.
Scans for memorize_metric, record_metric, and ServiceMetrics usage.
"""

import ast
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set

from .protocols import CodeScanner
from .schemas import MetricLocation, MetricPattern, MetricSource, MetricVerification, ModuleScanResult, ScannerConfig


class CodeMetricScanner(CodeScanner):
    """Implementation of code scanner for metrics."""

    def __init__(self, config: ScannerConfig):
        self.config = config
        self.base_path = Path(config.base_path)
        self.found_metrics: Dict[str, List[MetricLocation]] = defaultdict(list)
        self.patterns_found: Dict[str, MetricPattern] = {}

    async def scan(self, config: ScannerConfig) -> List[MetricVerification]:
        """Scan code for metrics."""
        verifications = []

        # Define modules to scan
        modules = self._get_module_paths()

        for module_name, module_path in modules.items():
            if module_path.exists():
                result = self.scan_module(module_path)

                # Convert to verifications
                for pattern_name, locations in self.found_metrics.items():
                    verification = MetricVerification(
                        metric_name=pattern_name,
                        module=module_name,
                        version="1.4.2",  # Current version
                        code_locations=locations,
                        patterns=[self.patterns_found.get(pattern_name)] if pattern_name in self.patterns_found else [],
                        is_in_code=True,
                    )
                    verifications.append(verification)

        return verifications

    def get_source_type(self) -> str:
        """Return the source type."""
        return "code"

    def scan_file(self, file_path: Path) -> List[MetricLocation]:
        """Scan a single file for metrics."""
        locations = []

        try:
            with open(file_path, "r") as f:
                content = f.read()
                lines = content.split("\n")

            # Try AST parsing first for better accuracy
            try:
                tree = ast.parse(content)
                locations.extend(self._scan_ast(tree, file_path, lines))
            except SyntaxError:
                # Fall back to regex if AST fails
                pass

            # Always do regex scan for patterns AST might miss
            locations.extend(self._scan_regex(content, file_path, lines))

            # Scan for ServiceMetrics schema usage
            locations.extend(self._scan_service_metrics(content, file_path, lines))

        except Exception as e:
            print(f"Error scanning {file_path}: {e}")

        return locations

    def scan_module(self, module_path: Path) -> ModuleScanResult:
        """Scan an entire module for metrics."""
        result = ModuleScanResult(
            module_name=module_path.name,
            files_scanned=0,
            metrics_found=0,
            unique_patterns=0,
            dynamic_patterns=0,
            scan_timestamp=datetime.now(),
        )

        files = list(module_path.rglob("*.py")) if module_path.is_dir() else [module_path]

        for file_path in files:
            if "__pycache__" in str(file_path):
                continue

            result.files_scanned += 1
            locations = self.scan_file(file_path)

            for location in locations:
                # Extract metric name from context
                metric_name = self._extract_metric_name(location.context)
                if metric_name:
                    self.found_metrics[metric_name].append(location)
                    result.metrics_found += 1

        result.unique_patterns = len(self.found_metrics)
        result.dynamic_patterns = sum(1 for p in self.patterns_found.values() if p.is_dynamic)

        return result

    def extract_patterns(self, code: str) -> List[MetricPattern]:
        """Extract metric patterns from code."""
        patterns = []

        # Look for f-string patterns
        f_string_pattern = r'f["\']([^"\']+)\{([^}]+)\}([^"\']*)["\']'
        for match in re.finditer(f_string_pattern, code):
            prefix = match.group(1)
            variable = match.group(2)
            suffix = match.group(3)

            pattern = MetricPattern(
                pattern=f"{prefix}{{{variable}}}{suffix}",
                is_dynamic=True,
                is_template=True,
                base_name=prefix,
                variables=[variable],
            )

            # Try to resolve common variables
            pattern.example_values = self._resolve_variable(variable, code)
            patterns.append(pattern)

        return patterns

    def resolve_dynamic_patterns(self, pattern: MetricPattern) -> List[str]:
        """Resolve dynamic patterns to concrete metric names."""
        resolved = []

        if not pattern.is_dynamic:
            return [pattern.pattern]

        # Common service names
        if "service" in pattern.variables[0].lower():
            services = [
                "llm",
                "memory",
                "telemetry",
                "audit",
                "config",
                "incident",
                "tsdb",
                "authentication",
                "resource_monitor",
                "wise_authority",
                "adaptive_filter",
                "visibility",
                "self_observation",
                "task_scheduler",
            ]
            for service in services:
                resolved.append(pattern.pattern.replace(f"{{{pattern.variables[0]}}}", service))

        # Common metric types
        elif "metric" in pattern.variables[0].lower() or "type" in pattern.variables[0].lower():
            types = ["tokens", "latency", "errors", "requests", "cache", "memory"]
            for metric_type in types:
                resolved.append(pattern.pattern.replace(f"{{{pattern.variables[0]}}}", metric_type))

        # Common operations
        elif "operation" in pattern.variables[0].lower() or "action" in pattern.variables[0].lower():
            operations = ["create", "read", "update", "delete", "query", "process"]
            for op in operations:
                resolved.append(pattern.pattern.replace(f"{{{pattern.variables[0]}}}", op))

        return resolved if resolved else [pattern.pattern]

    def _scan_ast(self, tree: ast.AST, file_path: Path, lines: List[str]) -> List[MetricLocation]:
        """Scan AST for metric calls."""
        locations = []

        class MetricVisitor(ast.NodeVisitor):
            def visit_Call(self, node):
                # Check for memorize_metric or record_metric calls
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in ["memorize_metric", "record_metric"]:
                        location = self._extract_location(node, file_path, lines)
                        if location:
                            locations.append(location)
                elif isinstance(node.func, ast.Name):
                    if node.func.id in ["memorize_metric", "record_metric"]:
                        location = self._extract_location(node, file_path, lines)
                        if location:
                            locations.append(location)

                self.generic_visit(node)

            def _extract_location(self, node, file_path, lines):
                """Extract location from AST node."""
                try:
                    # Get metric name from arguments
                    metric_name = None
                    for arg in node.args:
                        if isinstance(arg, ast.Constant):
                            metric_name = arg.value
                            break
                    for keyword in node.keywords:
                        if keyword.arg == "metric_name" and isinstance(keyword.value, ast.Constant):
                            metric_name = keyword.value.value
                            break

                    if metric_name:
                        line_num = node.lineno
                        context = lines[max(0, line_num - 2) : min(len(lines), line_num + 2)]
                        return MetricLocation(
                            file_path=str(file_path), line_number=line_num, context="\n".join(context)
                        )
                except:
                    pass
                return None

        visitor = MetricVisitor()
        visitor.visit(tree)
        return locations

    def _scan_regex(self, content: str, file_path: Path, lines: List[str]) -> List[MetricLocation]:
        """Scan using regex patterns."""
        locations = []

        for pattern in self.config.metric_patterns:
            for match in re.finditer(pattern, content):
                line_num = content[: match.start()].count("\n") + 1
                context_start = max(0, line_num - 3)
                context_end = min(len(lines), line_num + 3)
                context = "\n".join(lines[context_start:context_end])

                location = MetricLocation(file_path=str(file_path), line_number=line_num, context=context)
                locations.append(location)

                # Extract and store pattern if it's dynamic
                if 'f"' in match.group(0) or "f'" in match.group(0):
                    metric_pattern = self.extract_patterns(match.group(0))
                    if metric_pattern:
                        self.patterns_found[match.group(1)] = metric_pattern[0]

        return locations

    def _scan_service_metrics(self, content: str, file_path: Path, lines: List[str]) -> List[MetricLocation]:
        """Scan for ServiceMetrics schema usage."""
        locations = []

        # Look for ServiceMetrics instantiation
        pattern = r"ServiceMetrics\s*\([^)]*\)"
        for match in re.finditer(pattern, content):
            line_num = content[: match.start()].count("\n") + 1
            context = match.group(0)

            # Try to extract metric fields
            metrics_extracted = self._extract_metrics_from_schema(context)
            for metric_name in metrics_extracted:
                location = MetricLocation(file_path=str(file_path), line_number=line_num, context=context)
                locations.append(location)
                self.found_metrics[metric_name].append(location)

        return locations

    def _extract_metrics_from_schema(self, schema_text: str) -> List[str]:
        """Extract metric names from ServiceMetrics schema."""
        metrics = []

        # Common metric field patterns in ServiceMetrics
        field_patterns = [
            r"requests_handled\s*=\s*(\d+)",
            r"errors_count\s*=\s*(\d+)",
            r"latency_ms\s*=\s*(\d+)",
            r"tokens_used\s*=\s*(\d+)",
            r"cache_hits\s*=\s*(\d+)",
            r"cache_misses\s*=\s*(\d+)",
        ]

        for pattern in field_patterns:
            if re.search(pattern, schema_text):
                # Extract the field name as a metric
                field_name = pattern.split(r"\\s")[0]
                metrics.append(field_name)

        return metrics

    def _extract_metric_name(self, context: str) -> Optional[str]:
        """Extract metric name from context."""
        # Try to find quoted strings that look like metric names
        patterns = [
            r'["\']([a-z_\.]+(?:\.[a-z_]+)*)["\']',  # dot-separated names
            r'["\']([a-z_]+)["\']',  # simple names
        ]

        for pattern in patterns:
            match = re.search(pattern, context)
            if match:
                return match.group(1)

        return None

    def _resolve_variable(self, variable: str, code: str) -> List[str]:
        """Try to resolve what values a variable might have."""
        values = []

        # Look for variable assignment
        assignment_pattern = rf'{variable}\s*=\s*["\']([^"\']+)["\']'
        for match in re.finditer(assignment_pattern, code):
            values.append(match.group(1))

        # Look for loop iterations
        loop_pattern = rf"for\s+{variable}\s+in\s+\[([^\]]+)\]"
        for match in re.finditer(loop_pattern, code):
            items = match.group(1).split(",")
            for item in items:
                item = item.strip().strip('"').strip("'")
                if item:
                    values.append(item)

        return values

    def _get_module_paths(self) -> Dict[str, Path]:
        """Get all module paths to scan."""
        return {
            # Core Services
            "LLM_SERVICE": self.base_path / "logic/services/runtime/llm_service.py",
            "MEMORY_SERVICE": self.base_path / "logic/services/graph/memory_service.py",
            "TELEMETRY_SERVICE": self.base_path / "logic/services/graph/telemetry_service.py",
            "AUDIT_SERVICE": self.base_path / "logic/services/graph/audit_service.py",
            "CONFIG_SERVICE": self.base_path / "logic/services/graph/config_service.py",
            "INCIDENT_SERVICE": self.base_path / "logic/services/graph/incident_service.py",
            "TSDB_SERVICE": self.base_path / "logic/services/graph/tsdb_consolidation_service.py",
            # Infrastructure
            "AUTH_SERVICE": self.base_path / "logic/services/infrastructure/authentication.py",
            "RESOURCE_MONITOR": self.base_path / "logic/services/infrastructure/resource_monitor.py",
            "TIME_SERVICE": self.base_path / "logic/services/infrastructure/time.py",
            "SHUTDOWN_SERVICE": self.base_path / "logic/services/infrastructure/shutdown.py",
            "INIT_SERVICE": self.base_path / "logic/services/infrastructure/initialization.py",
            "DATABASE_MAINTENANCE": self.base_path / "logic/services/infrastructure/database_maintenance.py",
            "SECRETS_SERVICE": self.base_path / "logic/services/infrastructure/secrets.py",
            # Governance
            "WISE_AUTHORITY": self.base_path / "logic/services/governance/wise_authority.py",
            "ADAPTIVE_FILTER": self.base_path / "logic/services/governance/filter.py",
            "VISIBILITY": self.base_path / "logic/services/governance/visibility.py",
            "SELF_OBSERVATION": self.base_path / "logic/services/governance/self_observation.py",
            # Runtime
            "TASK_SCHEDULER": self.base_path / "logic/services/runtime/scheduler.py",
            "RUNTIME_CONTROL": self.base_path / "logic/services/runtime/runtime_control.py",
            # Tool Services
            "SECRETS_TOOL": self.base_path / "logic/services/tools/secrets_tool_service.py",
            # Handlers & Infrastructure
            "HANDLERS": self.base_path / "logic/infrastructure/handlers",
            "BUSES": self.base_path / "logic/buses",
            "ADAPTERS": self.base_path / "logic/adapters",
            "AGENT_PROCESSOR": self.base_path / "logic/processor",
        }
