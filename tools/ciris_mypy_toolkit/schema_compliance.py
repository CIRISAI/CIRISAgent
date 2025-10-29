"""
Schema Compliance Module - Updated for v1 schemas and protocols
"""

import ast
import re
from typing import Any, Dict, List

# Import current v1 schemas and protocols
try:
    from ciris_engine import schemas
    from ciris_engine.protocols.services.core.tool import ToolService
    from ciris_engine.protocols.services.governance.communication import CommunicationService
    from ciris_engine.protocols.services.governance.wise_authority import WiseAuthorityService
    from ciris_engine.protocols.services.graph.audit import AuditService
    from ciris_engine.protocols.services.graph.memory import MemoryService
    from ciris_engine.protocols.services.runtime.llm import LLMService
except ImportError:
    schemas = None
    CommunicationService = None
    MemoryService = None
    LLMService = None
    AuditService = None
    ToolService = None
    WiseAuthorityService = None


class SchemaComplianceChecker:
    """Ensures 100% compliance with v1 schemas and protocols."""

    def __init__(self):
        self.v1_schemas = self._load_v1_schemas()
        self.protocol_interfaces = self._load_protocol_interfaces()

    def _load_v1_schemas(self) -> Dict[str, Any]:
        """Load all v1 schema definitions."""
        if not schemas:
            return {}

        schema_map = {}

        # Core schemas
        schema_map.update(
            {
                "BaseSchema": dict,  # Our foundational type
                "Task": schemas.Task,
                "Thought": schemas.Thought,
                "IncomingMessage": schemas.IncomingMessage,
                "ActionSelectionDMAResult": schemas.ActionSelectionDMAResult,
                "HandlerActionType": schemas.HandlerActionType,
            }
        )

        # Action parameter schemas
        action_params = [
            "ObserveParams",
            "SpeakParams",
            "ToolParams",
            "PonderParams",
            "RejectParams",
            "DeferParams",
            "MemorizeParams",
            "RecallParams",
            "ForgetParams",
        ]
        for param in action_params:
            if hasattr(schemas, param):
                schema_map[param] = getattr(schemas, param)

        return schema_map

    def _load_protocol_interfaces(self) -> Dict[str, Any]:
        """Load all protocol interface definitions."""
        return {
            "CommunicationService": CommunicationService,
            "MemoryService": MemoryService,
            "LLMService": LLMService,
            "AuditService": AuditService,
            "ToolService": ToolService,
            "WiseAuthorityService": WiseAuthorityService,
        }

    def check_schema_usage(self, file_path: str) -> Dict[str, Any]:
        """Check if file uses v1 schemas correctly."""
        try:
            with open(file_path, "r") as f:
                content = f.read()

            # Check for legacy schema usage
            # Note: Using re.IGNORECASE flag, so only uppercase patterns needed
            legacy_patterns = [
                r"Dict\[str,\s*Any\]",  # Should use BaseSchema
                r"Dict\[Any,\s*Any\]",  # Should use specific schema
            ]

            violations = []
            # Track matched positions to avoid duplicate counting
            matched_positions = set()
            for pattern in legacy_patterns:
                matches = re.finditer(pattern, content, re.IGNORECASE)
                for match in matches:
                    # Skip if we already matched this position
                    if match.start() in matched_positions:
                        continue
                    matched_positions.add(match.start())

                    line_num = content[: match.start()].count("\n") + 1
                    violations.append(
                        {
                            "line": line_num,
                            "issue": f"Legacy type annotation: {match.group()}",
                            "suggestion": "Use schemas.BaseSchema or specific v1 schema",
                        }
                    )

            # Check for proper schema imports
            has_schema_import = "from ciris_engine import schemas" in content
            uses_schemas = bool(re.search(r"schemas\.\w+", content))

            if uses_schemas and not has_schema_import:
                violations.append(
                    {
                        "line": 1,
                        "issue": "Uses schemas without proper import",
                        "suggestion": "Add: from ciris_engine import schemas",
                    }
                )

            return {"compliant": len(violations) == 0, "violations": violations, "total_issues": len(violations)}

        except Exception as e:
            return {
                "compliant": False,
                "violations": [{"line": 0, "issue": f"Error analyzing file: {e}", "suggestion": "Fix file syntax"}],
                "total_issues": 1,
            }

    def check_protocol_compliance(self, file_path: str) -> Dict[str, Any]:
        """Check if file implements protocols correctly."""
        try:
            with open(file_path, "r") as f:
                content = f.read()

            tree = ast.parse(content)
            violations = []

            # Check for protocol violations
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    # Check if class implements a service protocol
                    for base in node.bases:
                        if isinstance(base, ast.Name) and base.id in self.protocol_interfaces:
                            # Verify required methods are implemented
                            class_methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                            protocol_name = base.id

                            # For now, basic check - expand based on actual protocol requirements
                            if "Service" in protocol_name and "start" not in class_methods:
                                violations.append(
                                    {
                                        "line": node.lineno,
                                        "issue": f"Class {node.name} implements {protocol_name} but missing start() method",
                                        "suggestion": "Implement required protocol methods",
                                    }
                                )

            return {
                "protocol_compliant": len(violations) == 0,
                "violations": violations,
                "total_issues": len(violations),
            }

        except Exception as e:
            return {
                "protocol_compliant": False,
                "violations": [
                    {"line": 0, "issue": f"Error analyzing protocols: {e}", "suggestion": "Fix file syntax"}
                ],
                "total_issues": 1,
            }

    def generate_schema_fixes(self, violations: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Generate automatic fixes for schema compliance issues."""
        fixes = []

        for violation in violations:
            if "Legacy type annotation" in violation["issue"]:
                # Convert legacy Dict[str, Any] to schemas.BaseSchema
                fix = {
                    "type": "schema_modernization",
                    "line": violation["line"],
                    "old_pattern": r"Dict\[str,\s*Any\]",
                    "new_pattern": "schemas.BaseSchema",
                    "description": "Convert to v1 schema type",
                }
                fixes.append(fix)

        return fixes
