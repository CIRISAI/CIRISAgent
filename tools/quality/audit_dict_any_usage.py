#!/usr/bin/env python3
"""
Audit Dict[str, Any] usage across the CIRIS codebase.
Categorizes usage patterns and suggests Pydantic model replacements.
"""

import ast
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Dict, List


class DictAnyAuditor(ast.NodeVisitor):
    """AST visitor to find Dict[str, Any] usage patterns."""

    def __init__(self, filepath: str, source_lines: List[str]):
        self.filepath = filepath
        self.source_lines = source_lines  # Store source lines to check for comments
        self.findings: List[Dict[str, any]] = []
        self.current_class = None
        self.current_function = None
        self.in_docstring = False

    def visit_ClassDef(self, node: ast.ClassDef):
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef):
        old_func = self.current_function
        self.current_function = node.name
        self.generic_visit(node)
        self.current_function = old_func

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)

    def _is_dict_str_any(self, node: ast.AST) -> bool:
        """Check if node represents Dict[str, Any]."""
        if isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id == "Dict":
                if isinstance(node.slice, ast.Tuple) and len(node.slice.elts) == 2:
                    first, second = node.slice.elts
                    if (
                        isinstance(first, ast.Name)
                        and first.id == "str"
                        and isinstance(second, ast.Name)
                        and second.id == "Any"
                    ):
                        return True
        return False

    def _is_in_comment(self, lineno: int) -> bool:
        """Check if the line is a comment or contains the Dict[str, Any] in a comment."""
        if lineno <= 0 or lineno > len(self.source_lines):
            return False

        line = self.source_lines[lineno - 1]  # Lines are 1-indexed

        # Strip leading whitespace and check if it's a comment line
        stripped = line.strip()
        if stripped.startswith("#"):
            return True

        # Check if Dict[str, Any] appears after a # comment
        if "#" in line:
            comment_pos = line.find("#")
            dict_pos = line.find("Dict[str, Any]")
            if dict_pos >= 0 and dict_pos > comment_pos:
                return True

        return False

    def _is_in_docstring_context(self, node: ast.AST) -> bool:
        """Check if node is within a docstring."""
        # Check if the node appears to be in a docstring based on parent context
        parent = getattr(node, "parent", None)
        if parent:
            # Check if parent is an Expr node (typical for docstrings)
            if isinstance(parent, ast.Expr) and isinstance(parent.value, ast.Constant):
                if isinstance(parent.value.value, str):
                    return True
            # Check if we're in a string that could be a docstring
            if isinstance(parent, ast.Constant) and isinstance(parent.value, str):
                return True
        return False

    def _get_context(self, node: ast.AST) -> str:
        """Determine the context of Dict[str, Any] usage."""
        parent = getattr(node, "parent", None)
        if not parent:
            return "unknown"

        if isinstance(parent, ast.AnnAssign):
            return "variable_annotation"
        elif isinstance(parent, ast.arg):
            return "function_parameter"
        elif isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return "return_type"
        elif isinstance(parent, ast.Assign):
            return "type_alias"
        else:
            return "other"

    def visit_Subscript(self, node: ast.Subscript):
        if self._is_dict_str_any(node):
            # Skip if this is in a comment or docstring
            if self._is_in_comment(node.lineno):
                self.generic_visit(node)
                return

            if self._is_in_docstring_context(node):
                self.generic_visit(node)
                return

            context = self._get_context(node)

            # Try to determine what the dict is used for
            usage_hint = self._determine_usage_hint(node)

            self.findings.append(
                {
                    "file": self.filepath,
                    "line": node.lineno,
                    "class": self.current_class,
                    "function": self.current_function,
                    "context": context,
                    "usage_hint": usage_hint,
                }
            )
        self.generic_visit(node)

    def _determine_usage_hint(self, node: ast.AST) -> str:
        """Try to determine what the Dict[str, Any] is used for based on context."""
        # Look for common patterns in variable/parameter names
        parent = getattr(node, "parent", None)
        if parent:
            if isinstance(parent, ast.AnnAssign) and parent.target:
                if isinstance(parent.target, ast.Name):
                    name = parent.target.id.lower()
                    return self._classify_by_name(name)
            elif isinstance(parent, ast.arg):
                name = parent.arg.lower()
                return self._classify_by_name(name)

        return "generic_data"

    def _classify_by_name(self, name: str) -> str:
        """Classify usage based on variable/parameter name."""
        if "config" in name:
            return "configuration"
        elif "response" in name or "result" in name:
            return "api_response"
        elif "request" in name or "payload" in name:
            return "api_request"
        elif "data" in name:
            return "generic_data"
        elif "context" in name or "ctx" in name:
            return "context_data"
        elif "metadata" in name or "meta" in name:
            return "metadata"
        elif "params" in name or "args" in name or "kwargs" in name:
            return "parameters"
        elif "state" in name:
            return "state_data"
        elif "event" in name:
            return "event_data"
        elif "message" in name or "msg" in name:
            return "message_data"
        else:
            return "generic_data"


def add_parent_references(tree: ast.AST):
    """Add parent references to AST nodes."""
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            setattr(child, "parent", parent)


def audit_file(filepath: Path) -> List[Dict[str, any]]:
    """Audit a single Python file for Dict[str, Any] usage."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
            source_lines = content.splitlines()

        tree = ast.parse(content, filename=str(filepath))
        add_parent_references(tree)

        auditor = DictAnyAuditor(str(filepath), source_lines)
        auditor.visit(tree)

        return auditor.findings
    except Exception as e:
        print(f"Error processing {filepath}: {e}")
        return []


def generate_pydantic_model_suggestions(findings_by_category: Dict[str, List[Dict]]) -> Dict[str, str]:
    """Generate Pydantic model suggestions for each category."""
    suggestions = {}

    templates = {
        "configuration": '''from pydantic import BaseModel, Field
from typing import Optional

class {name}Config(BaseModel):
    """Configuration model for {context}."""
    # TODO: Add specific fields based on actual usage
    class Config:
        extra = "forbid"  # Strict validation
''',
        "api_response": '''from pydantic import BaseModel, Field
from typing import Optional, List

class {name}Response(BaseModel):
    """API response model for {context}."""
    success: bool = Field(..., description="Whether the operation succeeded")
    message: Optional[str] = Field(None, description="Response message")
    data: Optional[{data_type}] = Field(None, description="Response data")

    class Config:
        extra = "forbid"
''',
        "api_request": '''from pydantic import BaseModel, Field
from typing import Optional

class {name}Request(BaseModel):
    """API request model for {context}."""
    # TODO: Add specific fields based on actual usage

    class Config:
        extra = "forbid"
''',
        "context_data": '''from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class {name}Context(BaseModel):
    """Context data model for {context}."""
    # TODO: Replace with specific fields
    # Temporary during migration:
    extra_data: Dict[str, Any] = Field(default_factory=dict)

    class Config:
        extra = "allow"  # Temporarily allow extra fields during migration
''',
        "generic_data": '''from pydantic import BaseModel
from typing import Optional

class {name}Data(BaseModel):
    """Data model for {context}."""
    # TODO: Analyze usage and add specific fields

    class Config:
        extra = "forbid"
''',
    }

    for category, items in findings_by_category.items():
        if items:
            # Use the first item to generate a context-aware suggestion
            first_item = items[0]
            context = f"{first_item.get('class', 'module')}.{first_item.get('function', 'level')}"
            name = category.title().replace("_", "")

            template = templates.get(category, templates["generic_data"])
            suggestions[category] = template.format(
                name=name, context=context, data_type="Any  # TODO: Replace with specific type"
            )

    return suggestions


def main():
    """Main audit function."""
    # Find all Python files
    python_files = []
    production_files = []
    test_files = []
    tool_files = []

    for root, dirs, files in os.walk("."):
        # Skip virtual environments and cache directories
        dirs[:] = [d for d in dirs if d not in {".venv", "venv", "__pycache__", ".git", ".mypy_cache"}]

        for file in files:
            if file.endswith(".py"):
                filepath = Path(root) / file
                python_files.append(filepath)

                # Categorize by location
                path_str = str(filepath)
                if path_str.startswith("./tests/") or path_str.startswith("tests/"):
                    test_files.append(filepath)
                elif path_str.startswith("./tools/") or path_str.startswith("tools/"):
                    tool_files.append(filepath)
                elif path_str.startswith("./ciris_engine/") or path_str.startswith("ciris_engine/"):
                    production_files.append(filepath)
                elif not path_str.startswith("./") or path_str.count("/") == 1:
                    # Root level files or other production code
                    if "test" not in path_str.lower():
                        production_files.append(filepath)

    print("Scanning Python files:")
    print(f"  Production: {len(production_files)}")
    print(f"  Tests: {len(test_files)}")
    print(f"  Tools: {len(tool_files)}")
    print(f"  Total: {len(python_files)}")
    print()

    # Collect findings separated by type
    production_findings = []
    test_findings = []
    tool_findings = []

    for filepath in production_files:
        findings = audit_file(filepath)
        production_findings.extend(findings)

    for filepath in test_files:
        findings = audit_file(filepath)
        test_findings.extend(findings)

    for filepath in tool_files:
        findings = audit_file(filepath)
        tool_findings.extend(findings)

    all_findings = production_findings + test_findings + tool_findings

    # Categorize findings
    findings_by_category = defaultdict(list)
    findings_by_file = defaultdict(list)
    prod_findings_by_category = defaultdict(list)
    prod_findings_by_file = defaultdict(list)

    for finding in production_findings:
        prod_findings_by_category[finding["usage_hint"]].append(finding)
        prod_findings_by_file[finding["file"]].append(finding)

    for finding in all_findings:
        findings_by_category[finding["usage_hint"]].append(finding)
        findings_by_file[finding["file"]].append(finding)

    # Generate report
    print(f"\n{'='*80}")
    print("Dict[str, Any] Usage Audit Report")
    print(f"{'='*80}")

    # PRODUCTION CODE SUMMARY (what actually matters)
    print("\n🚨 PRODUCTION CODE VIOLATIONS:")
    print(f"  Occurrences: {len(production_findings)}")
    print(f"  Files affected: {len(prod_findings_by_file)}")

    if production_findings:
        print("\n  Category Breakdown:")
        for category, items in sorted(prod_findings_by_category.items(), key=lambda x: len(x[1]), reverse=True):
            percentage = (len(items) / len(production_findings)) * 100 if production_findings else 0
            print(f"    {category:<20} {len(items):>3} ({percentage:.1f}%)")

    # Test/Tool summary (for reference only)
    print("\n📊 NON-PRODUCTION CODE (Tests/Tools):")
    print(f"  Tests: {len(test_findings)} occurrences")
    print(f"  Tools: {len(tool_findings)} occurrences")

    print("\n📈 TOTAL ACROSS ALL CODE:")
    print(f"  Total occurrences: {len(all_findings)}")
    print(f"  Total files: {len(findings_by_file)}")

    # Top 10 PRODUCTION files with most occurrences
    print("\n\nTop 10 PRODUCTION files with most Dict[str, Any] usage:")
    print(f"{'-'*60}")
    top_prod_files = sorted(prod_findings_by_file.items(), key=lambda x: len(x[1]), reverse=True)[:10]
    for filepath, items in top_prod_files:
        print(f"{filepath:<50} {len(items)} occurrences")

    # Generate Pydantic model suggestions FOR PRODUCTION CODE ONLY
    if production_findings:
        print("\n\nSuggested Pydantic Models for PRODUCTION CODE:")
        print(f"{'='*80}")
        suggestions = generate_pydantic_model_suggestions(prod_findings_by_category)

        for category, suggestion in suggestions.items():
            print(f"\n## Category: {category}")
            print(f"Production files to update: {len(prod_findings_by_category[category])}")
            print("Suggested model:\n")
            print(suggestion)

    # Save detailed findings to JSON
    output_file = "dict_any_audit_results.json"
    with open(output_file, "w") as f:
        json.dump(
            {
                "production": {
                    "occurrences": len(production_findings),
                    "files_affected": len(prod_findings_by_file),
                    "categories": {k: len(v) for k, v in prod_findings_by_category.items()},
                    "findings": production_findings,
                },
                "tests": {"occurrences": len(test_findings), "findings": test_findings},
                "tools": {"occurrences": len(tool_findings), "findings": tool_findings},
                "total_all_code": {"occurrences": len(all_findings), "files_affected": len(findings_by_file)},
            },
            f,
            indent=2,
        )
        # Add newline at end of file to satisfy pre-commit hooks
        f.write("\n")

    print(f"\n\nDetailed findings saved to: {output_file}")

    # Generate migration priority list FOR PRODUCTION CODE
    if production_findings:
        print("\n\nMigration Priority (PRODUCTION CODE ONLY):")
        print(f"{'='*80}")
        print("1. High Priority (Core Services):")
        core_services = ["services/graph/", "services/runtime/", "services/governance/"]
        for service in core_services:
            count = sum(1 for f in production_findings if service in f["file"])
            if count > 0:
                print(f"   - {service}: {count} occurrences")

        print("\n2. Medium Priority (API/Adapters):")
        adapters = ["adapters/api/", "adapters/discord/", "adapters/cli/"]
        for adapter in adapters:
            count = sum(1 for f in production_findings if adapter in f["file"])
            if count > 0:
                print(f"   - {adapter}: {count} occurrences")

        print("\n3. Other Production Code:")
        # Count production findings not in services or adapters
        other_count = sum(
            1 for f in production_findings if not any(path in f["file"] for path in core_services + adapters)
        )
        if other_count > 0:
            print(f"   - Other files: {other_count} occurrences")

    # Final summary
    print(f"\n\n{'='*80}")
    if len(production_findings) == 0:
        print("✅ CONGRATULATIONS! Zero Dict[str, Any] in production code!")
    else:
        print(f"⚠️  ACTION REQUIRED: {len(production_findings)} Dict[str, Any] violations in production code")
        print("   These violate the 'No Dicts' principle and must be fixed.")


if __name__ == "__main__":
    main()
