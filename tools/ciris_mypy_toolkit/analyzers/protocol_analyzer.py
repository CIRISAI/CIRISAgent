"""
Protocol Analyzer - Validates Protocol-Module-Schema alignment

The Protocol-Module-Schema architecture ensures:
1. Every service module implements its protocol exactly
2. All data flows through typed schemas (no Dict[str, Any])
3. Complete type safety with no runtime surprises
"""

import ast
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
try:
    from config.protocol_whitelist import is_whitelisted
except ImportError:
    # Fallback if whitelist not available
    def is_whitelisted(service_name: str, line: str, context: str) -> bool:
        return False


class ProtocolAnalyzer:
    """Analyzes protocol-module-schema alignment in the codebase."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        # CIRIS-specific paths - updated to match new structure
        self.protocols_path = self.project_root / "protocols"
        self.services_path = self.project_root / "logic" / "services"
        self.modules_path = self.project_root / "logic"
        self.schemas_path = self.project_root / "schemas"
        # Additional paths where services might be
        self.memory_path = self.project_root / "logic" / "services" / "memory_service"
        self.telemetry_path = self.project_root / "logic" / "telemetry"
        self.audit_path = self.project_root / "logic" / "audit"
        self.secrets_path = self.project_root / "logic" / "secrets"
        self.runtime_path = self.project_root / "logic" / "runtime"
        # New lifecycle services path
        self.lifecycle_path = self.project_root / "logic" / "services" / "lifecycle"
        # New infrastructure services path
        self.infrastructure_path = self.project_root / "logic" / "services" / "infrastructure"
        # New graph services path
        self.graph_path = self.project_root / "logic" / "services" / "graph"
        # New core services path
        self.core_path = self.project_root / "logic" / "services" / "core"
        # New special services path
        self.special_path = self.project_root / "logic" / "services" / "special"

        # The actual 22 CIRIS core services as per CLAUDE.md
        self.known_services = {
            # Graph Services (6)
            "MemoryService",
            "GraphConfigService",
            "TelemetryService",
            "AuditService",
            "IncidentManagementService",
            "TSDBConsolidationService",
            # Infrastructure Services (7)
            "TimeService",
            "ShutdownService",
            "InitializationService",
            "AuthenticationService",
            "ResourceMonitorService",
            "DatabaseMaintenanceService",
            "SecretsService",
            # Governance Services (4)
            "WiseAuthorityService",
            "AdaptiveFilterService",
            "VisibilityService",
            "SelfObservationService",
            # Runtime Services (3)
            "LLMService",
            "RuntimeControlService",
            "TaskSchedulerService",
            # Tool Services (1)
            "SecretsToolService",
        }

    def check_all_services(self) -> Dict[str, Any]:
        """Check all services for protocol alignment."""
        results = {
            "total_services": 0,
            "aligned_services": 0,
            "misaligned_services": 0,
            "no_untyped_dicts": True,
            "issues": [],
            "services": {},
        }

        # Check each known service
        results["total_services"] = len(self.known_services)

        for service_name in self.known_services:
            service_results = self.check_service_alignment(service_name)
            results["services"][service_name] = service_results

            if service_results["is_aligned"]:
                results["aligned_services"] += 1
            else:
                results["misaligned_services"] += 1
                results["issues"].extend(service_results["issues"])

            if not service_results["no_untyped_dicts"]:
                results["no_untyped_dicts"] = False

        return results

    def check_service_alignment(self, service_name: str) -> Dict[str, Any]:
        """Check if a specific service follows the protocol-first pattern."""
        results = {
            "service": service_name,
            "is_aligned": True,
            "no_untyped_dicts": True,
            "issues": [],
            "protocol_methods": [],
            "module_methods": [],
            "missing_methods": [],
            "extra_methods": [],
            "untyped_parameters": [],
            "untyped_returns": [],
        }

        # Find all protocol definitions (including base protocols like ServiceProtocol)
        all_protocol_methods = set()
        protocol_infos = []

        # Primary protocol
        protocol_info = self._find_protocol(service_name)
        if not protocol_info:
            results["is_aligned"] = False
            results["issues"].append(
                {
                    "service": service_name,
                    "type": "missing_protocol",
                    "message": f"No protocol found for {service_name}",
                }
            )
            return results

        protocol_infos.append(protocol_info)
        all_protocol_methods.update(protocol_info["methods"])

        # Find module implementation
        module_info = self._find_module(service_name)
        if not module_info:
            results["is_aligned"] = False
            results["issues"].append(
                {
                    "service": service_name,
                    "type": "missing_module",
                    "message": f"No module implementation found for {service_name}",
                }
            )
            return results

        # Check all base classes for additional protocols
        if "base_classes" in module_info:
            all_protocols = self._find_protocols()
            for base_class in module_info["base_classes"]:
                if base_class in all_protocols and base_class not in [p.get("name") for p in protocol_infos]:
                    base_protocol_info = all_protocols[base_class]
                    protocol_infos.append(base_protocol_info)
                    all_protocol_methods.update(base_protocol_info["methods"])

        # Compare protocol methods with module methods
        protocol_methods = all_protocol_methods  # Use all collected protocol methods
        module_methods = set(module_info["methods"])

        results["protocol_methods"] = list(protocol_methods)
        results["module_methods"] = list(module_methods)

        # Find missing methods (in protocol but not in module)
        missing = protocol_methods - module_methods
        if missing:
            results["is_aligned"] = False
            results["missing_methods"] = list(missing)
            for method in missing:
                results["issues"].append(
                    {
                        "service": service_name,
                        "type": "missing_method",
                        "message": f"Module missing protocol method: {method}",
                    }
                )

        # Find extra methods (in module but not in protocol)
        # Note: Private methods (_method) and special methods (__method__) are allowed
        # CIRIS requires 100% protocol alignment - no extra public methods allowed
        extra = {m for m in module_methods if not m.startswith("_")} - protocol_methods
        if extra:
            results["is_aligned"] = False
            results["extra_methods"] = list(extra)
            for method in extra:
                results["issues"].append(
                    {
                        "service": service_name,
                        "type": "extra_method",
                        "message": f"Module has method not in protocol: {method} - CIRIS requires 100% protocol alignment",
                    }
                )

        # Check for Dict[str, Any] usage
        untyped_usages = self._find_untyped_dicts(module_info["file_path"])
        if untyped_usages:
            # Filter out whitelisted usages
            non_whitelisted = []
            for usage in untyped_usages:
                if not is_whitelisted(service_name, str(usage["line"]), usage["context"]):
                    non_whitelisted.append(usage)

            if non_whitelisted:
                results["no_untyped_dicts"] = False
                results["is_aligned"] = False
                for usage in non_whitelisted:
                    results["issues"].append(
                        {
                            "service": service_name,
                            "type": "untyped_dict",
                            "message": f"Uses Dict[str, Any] at line {usage['line']}: {usage['context']}",
                        }
                    )

        return results

    def _find_protocols(self) -> Dict[str, Dict[str, Any]]:
        """Find all protocol definitions."""
        protocols = {}

        # Look in protocols directory
        if self.protocols_path.exists():
            for file_path in self.protocols_path.rglob("*.py"):
                if file_path.name.startswith("_"):
                    continue

                tree = ast.parse(file_path.read_text())
                for node in ast.walk(tree):
                    if isinstance(node, ast.ClassDef):
                        # Check if the class inherits from Protocol (typing.Protocol) or ends with Protocol
                        is_protocol = False
                        for base in node.bases:
                            if isinstance(base, ast.Name):
                                if base.id == "Protocol" or base.id.endswith("Protocol"):
                                    is_protocol = True
                                    break
                            elif isinstance(base, ast.Attribute) and base.attr == "Protocol":
                                is_protocol = True
                                break

                        if is_protocol:
                            protocol_name = node.name
                            # Include service protocols - must inherit from ServiceProtocol or GraphServiceProtocol
                            # and either end with Service, ServiceProtocol, or be a known service protocol
                            is_service_protocol = False

                            # Include ServiceProtocol itself as it's the root protocol
                            if protocol_name == "ServiceProtocol":
                                is_service_protocol = True

                            # Check if it inherits from ServiceProtocol or GraphServiceProtocol
                            for base in node.bases:
                                if isinstance(base, ast.Name) and base.id in [
                                    "ServiceProtocol",
                                    "GraphServiceProtocol",
                                    "CoreServiceProtocol",
                                ]:
                                    is_service_protocol = True
                                    break

                            # Also include known service protocols
                            known_service_protocols = [
                                # Graph Service Protocols
                                "GraphMemoryServiceProtocol",
                                "GraphConfigServiceProtocol",
                                "TelemetryServiceProtocol",
                                "AuditServiceProtocol",
                                "IncidentManagementServiceProtocol",
                                "TSDBConsolidationServiceProtocol",
                                # Infrastructure Service Protocols
                                "TimeServiceProtocol",
                                "ShutdownServiceProtocol",
                                "InitializationServiceProtocol",
                                "AuthenticationServiceProtocol",
                                "ResourceMonitorServiceProtocol",
                                "DatabaseMaintenanceServiceProtocol",
                                "SecretsServiceProtocol",
                                # Governance Service Protocols
                                "WiseAuthorityServiceProtocol",
                                "AdaptiveFilterServiceProtocol",
                                "VisibilityServiceProtocol",
                                "SelfObservationServiceProtocol",
                                # Runtime Service Protocols
                                "LLMServiceProtocol",
                                "RuntimeControlServiceProtocol",
                                "TaskSchedulerServiceProtocol",
                                # Tool Service Protocols
                                "ToolServiceProtocol",
                                # Bus-based Service Protocols (not standalone)
                                "CommunicationServiceProtocol",
                                "MemoryServiceProtocol",
                            ]

                            if is_service_protocol or protocol_name in known_service_protocols:
                                methods = [
                                    n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                                ]

                                # Get base protocol methods
                                base_methods = set()
                                for base in node.bases:
                                    if isinstance(base, ast.Name):
                                        if base.id == "ServiceProtocol":
                                            # Add standard ServiceProtocol methods
                                            base_methods.update(
                                                [
                                                    "start",
                                                    "stop",
                                                    "get_capabilities",
                                                    "get_status",
                                                    "is_healthy",
                                                    "get_service_type",
                                                ]
                                            )
                                        elif base.id == "GraphServiceProtocol":
                                            # GraphServiceProtocol inherits from ServiceProtocol
                                            base_methods.update(
                                                [
                                                    "start",
                                                    "stop",
                                                    "get_capabilities",
                                                    "get_status",
                                                    "is_healthy",
                                                    "get_service_type",
                                                ]
                                            )
                                            # Plus its own methods
                                            base_methods.update(["store_in_graph", "query_graph", "get_node_type"])

                                # Combine direct methods with inherited methods
                                all_methods = list(set(methods) | base_methods)

                                protocols[protocol_name] = {
                                    "name": protocol_name,
                                    "file_path": file_path,
                                    "methods": all_methods,
                                    "line": node.lineno,
                                }

        return protocols

    def _find_protocol(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Find a specific protocol definition."""
        protocols = self._find_protocols()

        # Try exact match
        if service_name in protocols:
            return protocols[service_name]

        # Try with Protocol suffix
        protocol_name = f"{service_name}Protocol"
        if protocol_name in protocols:
            return protocols[protocol_name]

        # Try removing Service suffix and adding Protocol
        if service_name.endswith("Service"):
            base_name = service_name[:-7]  # Remove "Service"
            protocol_name = f"{base_name}ServiceProtocol"
            if protocol_name in protocols:
                return protocols[protocol_name]

        # Special case for tool services - they implement ToolServiceProtocol
        if service_name.endswith("ToolService"):
            if "ToolServiceProtocol" in protocols:
                return protocols["ToolServiceProtocol"]

        return None

    def _get_inherited_methods(self, base_class_name: str, search_paths: List[Path]) -> Set[str]:
        """Get all methods from a base class."""
        methods = set()

        # Known base class methods
        if base_class_name == "BaseGraphService":
            methods.update(
                [
                    "store_in_graph",
                    "query_graph",
                    "get_node_type",
                    "start",
                    "stop",
                    "get_capabilities",
                    "get_status",
                    "is_healthy",
                    "get_service_type",
                    "_set_memory_bus",
                    "_set_time_service",
                ]
            )
        elif base_class_name == "BaseService":
            methods.update(["start", "stop", "get_capabilities", "get_status", "is_healthy", "get_service_type"])

        # Try to find the base class definition
        for path in search_paths:
            if path.exists():
                for file_path in path.rglob("*.py"):
                    if file_path.name.startswith("_"):
                        continue
                    try:
                        tree = ast.parse(file_path.read_text())
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef) and node.name == base_class_name:
                                for n in node.body:
                                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                                        methods.add(n.name)
                                # Recursively get methods from this class's bases
                                for base in node.bases:
                                    if isinstance(base, ast.Name):
                                        methods.update(self._get_inherited_methods(base.id, search_paths))
                                return methods
                    except:
                        continue

        return methods

    def _find_module(self, service_name: str) -> Optional[Dict[str, Any]]:
        """Find a module implementation."""
        # Look in all service directories
        search_paths = [
            self.services_path,
            self.modules_path,
            self.memory_path,
            self.telemetry_path,
            self.audit_path,
            self.secrets_path,
            self.runtime_path,
            self.lifecycle_path,
            self.infrastructure_path,
            self.graph_path,
            self.core_path,
            self.special_path,
        ]

        for path in search_paths:
            if path.exists():
                for file_path in path.rglob("*.py"):
                    if file_path.name.startswith("_"):
                        continue

                    try:
                        tree = ast.parse(file_path.read_text())
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef):
                                # Check if class name matches or inherits from protocol
                                if node.name == service_name or any(
                                    self._is_protocol_base(base, service_name) for base in node.bases
                                ):
                                    # Get direct methods
                                    methods = set(
                                        n.name
                                        for n in node.body
                                        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                                    )

                                    # Also get the base classes this service inherits from
                                    base_classes = []
                                    for base in node.bases:
                                        if isinstance(base, ast.Name):
                                            base_classes.append(base.id)
                                            # Get inherited methods
                                            methods.update(self._get_inherited_methods(base.id, search_paths))
                                        elif isinstance(base, ast.Attribute):
                                            base_classes.append(base.attr)
                                            # Get inherited methods
                                            methods.update(self._get_inherited_methods(base.attr, search_paths))

                                    return {
                                        "file_path": file_path,
                                        "methods": list(methods),
                                        "line": node.lineno,
                                        "class_name": node.name,
                                        "base_classes": base_classes,
                                    }
                    except Exception:
                        # Skip files that can't be parsed
                        continue

        return None

    def _is_protocol_base(self, base: ast.AST, service_name: str) -> bool:
        """Check if a base class is the protocol for this service."""
        if isinstance(base, ast.Name):
            return base.id in [service_name + "Protocol", service_name]
        elif isinstance(base, ast.Attribute):
            return base.attr in [service_name + "Protocol", service_name]
        return False

    def _find_untyped_dicts(self, file_path: Path) -> List[Dict[str, Any]]:
        """Find all uses of Dict[str, Any] in a file."""
        untyped_usages = []

        try:
            content = file_path.read_text()
            lines = content.split("\n")

            # Look for Dict[str, Any] patterns
            patterns = ["Dict[str, Any]", "dict[str, Any]", "Dict[str,Any]", "dict[str,Any]", ": Any", "-> Any"]

            for i, line in enumerate(lines, 1):
                for pattern in patterns:
                    if pattern in line and not line.strip().startswith("#"):
                        untyped_usages.append({"line": i, "context": line.strip(), "pattern": pattern})
        except Exception:
            # Ignore files that can't be read
            pass

        return untyped_usages

    def list_all_protocols(self) -> Dict[str, List[str]]:
        """List all protocols found in the codebase, categorized."""
        all_protocols = self._find_protocols()

        # Categorize protocols
        categorized = {
            "service_protocols": [],
            "handler_protocols": [],
            "adapter_protocols": [],
            "dma_protocols": [],
            "processor_protocols": [],
            "other_protocols": [],
        }

        for protocol_name in sorted(all_protocols.keys()):
            if protocol_name.endswith("ServiceProtocol") or protocol_name == "ServiceProtocol":
                categorized["service_protocols"].append(protocol_name)
            elif protocol_name.endswith("HandlerProtocol"):
                categorized["handler_protocols"].append(protocol_name)
            elif protocol_name.endswith("AdapterProtocol"):
                categorized["adapter_protocols"].append(protocol_name)
            elif "DMA" in protocol_name and protocol_name.endswith("Protocol"):
                categorized["dma_protocols"].append(protocol_name)
            elif protocol_name.endswith("ProcessorProtocol"):
                categorized["processor_protocols"].append(protocol_name)
            else:
                categorized["other_protocols"].append(protocol_name)

        return categorized
